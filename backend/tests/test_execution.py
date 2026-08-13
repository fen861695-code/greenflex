from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload

from greenflex.catalog import seed_catalog
from greenflex.config import Settings
from greenflex.container import ServiceContainer
from greenflex.db import Base
from greenflex.domain import DomainError, OrderStatus
from greenflex.energy_estimator import EnergyEstimator
from greenflex.execution import PersistentOrderWorker
from greenflex.gpu_calibrator import GpuCalibrator
from greenflex.models import ExecutionRecord, OrderRecord, PassportRecord
from greenflex.policies import LowestImpactSlotPolicy, TieredPricingPolicy
from greenflex.ports import GenerationRequest, GenerationResult, PowerSample
from greenflex.recommendation import GreenRouterRuleV1
from greenflex.schemas import BatchItemInput, QuoteRequest
from greenflex.services import create_order, create_quotes, purge_order_content_at
from greenflex.signals import SyntheticEnergySignalProvider


class FakeInferenceProvider:
    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    async def available_models(self) -> dict[str, str]:
        return {"qwen2.5:0.5b": "sha256:fixture"}

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls[request.prompt] = self.calls.get(request.prompt, 0) + 1
        await asyncio.sleep(0.01)
        if request.prompt == "synthetic-failure":
            raise DomainError("temporary_runtime_failure", "fixture failure", 503)
        return GenerationResult(
            output="synthetic-result",
            prompt_tokens=9,
            output_tokens=13,
            duration_us=10_000,
        )


class FakeTelemetryProvider:
    source = "fixture-telemetry"

    async def idle_power_mw(self, duration_seconds: float = 3.0) -> int | None:
        del duration_seconds
        return 20_000

    async def samples(self) -> AsyncGenerator[PowerSample]:
        for index in range(5):
            yield PowerSample(
                captured_at=datetime.now(UTC),
                power_mw=40_000 + index * 1_000,
                utilization_bps=5_000,
                memory_used_mb=1_024,
            )
            await asyncio.sleep(0.005)


async def _database(
    path: Path,
) -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        await seed_catalog(session)
    return factory, engine


async def test_worker_retries_settles_and_issues_content_free_passport(tmp_path: Path) -> None:
    factory, engine = await _database(tmp_path / "worker.db")
    inference = FakeInferenceProvider()
    signals = SyntheticEnergySignalProvider()
    container = ServiceContainer(
        inference=inference,
        telemetry=FakeTelemetryProvider(),
        signals=signals,
        pricing=TieredPricingPolicy(),
        scheduling=LowestImpactSlotPolicy(signals),
        recommendation=GreenRouterRuleV1(shadow_mode=True),
        energy_estimator=EnergyEstimator(benchmarks=[], gpu_profiles=[]),
        gpu_calibrator=GpuCalibrator(estimator=EnergyEstimator(benchmarks=[], gpu_profiles=[]), gpu_profiles=[]),
    )
    now = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    async with factory() as session:
        quotes = await create_quotes(
            session,
            container,
            QuoteRequest(
                items=[
                    BatchItemInput(
                        client_item_id="success-001",
                        prompt="synthetic-success",
                        max_output_tokens=32,
                    ),
                    BatchItemInput(
                        client_item_id="failure-001",
                        prompt="synthetic-failure",
                        max_output_tokens=32,
                    ),
                ],
                model_id="qwen2.5-0.5b-q4",
            ),
            now=now,
        )
        order_view = await create_order(session, quotes[0].quote_id, now=now)

    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'worker.db').as_posix()}",
        artifact_dir=tmp_path / "artifacts",
        telemetry_idle_seconds=0.5,
        worker_poll_seconds=0.1,
    )
    worker = PersistentOrderWorker(
        factory,
        container,
        settings,
        owner="fixture-worker",
        clock=lambda: now,
    )
    assert await worker.run_once() is True
    assert await worker.run_once() is False

    async with factory() as session:
        order = await session.scalar(
            select(OrderRecord)
            .where(OrderRecord.id == order_view.id)
            .options(selectinload(OrderRecord.items))
        )
        passport = await session.scalar(
            select(PassportRecord).where(PassportRecord.order_id == order_view.id)
        )
        execution = await session.scalar(
            select(ExecutionRecord).where(ExecutionRecord.order_id == order_view.id)
        )

    assert order is not None
    assert order.status == OrderStatus.PARTIAL_SUCCESS.value
    assert order.actual_price_micro_rmb is not None
    assert order.gross_gpu_energy_micro_wh is not None
    assert inference.calls == {"synthetic-success": 1, "synthetic-failure": 2}
    assert passport is not None
    assert execution is not None
    assert execution.telemetry_provenance == "measured"
    assert execution.raw_artifact_sha256 is not None
    assert execution.raw_artifact_path is not None
    assert await asyncio.to_thread(Path(execution.raw_artifact_path).is_file)

    payload = json.loads(passport.payload_json)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "synthetic-success" not in serialized
    assert "synthetic-failure" not in serialized
    assert "synthetic-result" not in serialized
    assert payload["claims"]["official_certification"] is False
    assert payload["green_grade"]["provenance"] == "simulated"

    artifact_path = Path(execution.raw_artifact_path)
    async with factory() as session:
        await purge_order_content_at(session, order_view.id, settings.artifact_dir)
    assert not await asyncio.to_thread(artifact_path.exists)
    async with factory() as session:
        purged_execution = await session.scalar(
            select(ExecutionRecord).where(ExecutionRecord.order_id == order_view.id)
        )
    assert purged_execution is not None
    assert purged_execution.raw_artifact_path is None
    assert purged_execution.raw_artifact_sha256 == execution.raw_artifact_sha256
    await engine.dispose()
