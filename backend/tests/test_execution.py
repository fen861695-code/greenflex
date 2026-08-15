from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
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
from greenflex.domain import DomainError, ItemStatus, OrderStatus
from greenflex.execution import PersistentOrderWorker
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
                model_id="gemma3-1b-q4",
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


async def test_worker_processes_batch_concurrently(tmp_path: Path) -> None:
    """Multiple items in the same batch should be inferred concurrently."""
    factory, engine = await _database(tmp_path / "batch.db")
    inference = FakeInferenceProvider()
    signals = SyntheticEnergySignalProvider()
    container = ServiceContainer(
        inference=inference,
        telemetry=FakeTelemetryProvider(),
        signals=signals,
        pricing=TieredPricingPolicy(),
        scheduling=LowestImpactSlotPolicy(signals),
        recommendation=GreenRouterRuleV1(shadow_mode=True),
    )
    settings = Settings(artifact_dir=str(tmp_path / "artifacts"))
    worker = PersistentOrderWorker(
        factory, container, settings, owner="test-worker", clock=lambda: now
    )

    now = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    async with factory() as session:
        quotes = await create_quotes(
            session,
            container,
            QuoteRequest(
                items=[
                    BatchItemInput(
                        client_item_id=f"item-{i}", prompt=f"prompt-{i}", max_output_tokens=32
                    )
                    for i in range(4)
                ],
            ),
            now=now,
        )
        immediate = next(q for q in quotes if q.execution_mode == "immediate")
        order_view = await create_order(session, immediate.quote_id, now=now)

    assert await worker.run_once() is True

    async with factory() as session:
        order = await session.scalar(
            select(OrderRecord)
            .where(OrderRecord.id == order_view.id)
            .options(selectinload(OrderRecord.items))
        )

    assert order is not None
    assert order.status == OrderStatus.SUCCEEDED.value
    succeeded = sum(1 for item in order.items if item.status == ItemStatus.SUCCEEDED.value)
    failed = sum(1 for item in order.items if item.status == ItemStatus.FAILED.value)
    assert succeeded == 4
    assert failed == 0
    # Each unique prompt should have been called exactly once (no retry needed)
    for i in range(4):
        assert inference.calls[f"prompt-{i}"] == 1
    await engine.dispose()


async def test_worker_all_items_fail(tmp_path: Path) -> None:
    """When all items fail, order should be FAILED."""
    factory, engine = await _database(tmp_path / "allfail.db")
    inference = FakeInferenceProvider()
    signals = SyntheticEnergySignalProvider()
    container = ServiceContainer(
        inference=inference,
        telemetry=FakeTelemetryProvider(),
        signals=signals,
        pricing=TieredPricingPolicy(),
        scheduling=LowestImpactSlotPolicy(signals),
        recommendation=GreenRouterRuleV1(shadow_mode=True),
    )
    now = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    async with factory() as session:
        quotes = await create_quotes(
            session,
            container,
            QuoteRequest(
                items=[
                    BatchItemInput(
                        client_item_id="fail-1", prompt="synthetic-failure", max_output_tokens=32
                    ),
                    BatchItemInput(
                        client_item_id="fail-2", prompt="synthetic-failure", max_output_tokens=32
                    ),
                ],
            ),
            now=now,
        )
        immediate = next(q for q in quotes if q.execution_mode == "immediate")
        order_view = await create_order(session, immediate.quote_id, now=now)

    settings = Settings(artifact_dir=str(tmp_path / "artifacts"))
    worker = PersistentOrderWorker(
        factory, container, settings, owner="test-worker", clock=lambda: now
    )

    assert await worker.run_once() is True

    async with factory() as session:
        order = await session.scalar(
            select(OrderRecord)
            .where(OrderRecord.id == order_view.id)
            .options(selectinload(OrderRecord.items))
        )

    assert order is not None
    assert order.status == OrderStatus.FAILED.value
    succeeded = sum(1 for item in order.items if item.status == ItemStatus.SUCCEEDED.value)
    failed = sum(1 for item in order.items if item.status == ItemStatus.FAILED.value)
    assert succeeded == 0
    assert failed == 2
    # Each failure should have been retried once
    assert inference.calls["synthetic-failure"] == 4  # 2 items * 2 attempts
    await engine.dispose()


async def test_worker_skips_already_completed_order(tmp_path: Path) -> None:
    """Processing an order with no pending items should not error."""
    factory, engine = await _database(tmp_path / "skip.db")
    inference = FakeInferenceProvider()
    signals = SyntheticEnergySignalProvider()
    container = ServiceContainer(
        inference=inference,
        telemetry=FakeTelemetryProvider(),
        signals=signals,
        pricing=TieredPricingPolicy(),
        scheduling=LowestImpactSlotPolicy(signals),
        recommendation=GreenRouterRuleV1(shadow_mode=True),
    )
    now = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    async with factory() as session:
        quotes = await create_quotes(
            session,
            container,
            QuoteRequest(
                items=[
                    BatchItemInput(client_item_id="item-1", prompt="prompt-1", max_output_tokens=32)
                ],
            ),
            now=now,
        )
        immediate = next(q for q in quotes if q.execution_mode == "immediate")
        await create_order(session, immediate.quote_id, now=now)

    settings = Settings(artifact_dir=str(tmp_path / "artifacts"))
    worker = PersistentOrderWorker(
        factory, container, settings, owner="test-worker", clock=lambda: now
    )

    # First run completes the order
    assert await worker.run_once() is True
    # Second run should find no pending orders
    assert await worker.run_once() is False

    # Inference should only have been called once
    assert inference.calls["prompt-1"] == 1
    await engine.dispose()
