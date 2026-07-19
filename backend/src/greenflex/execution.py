from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from greenflex.config import Settings
from greenflex.container import ServiceContainer
from greenflex.domain import DomainError, ItemStatus, OrderStatus, Provenance, utc_now
from greenflex.models import (
    AuditEventRecord,
    ExecutionRecord,
    OrderItemRecord,
    OrderRecord,
    PassportRecord,
)
from greenflex.ports import GenerationRequest, GenerationResult
from greenflex.services import PUE_BPS, passport_hash
from greenflex.telemetry import TelemetryCapture, TelemetryMeasurement, write_telemetry_artifact
from greenflex.units import micro_wh_to_carbon_micro_g

Clock = Callable[[], datetime]


class PersistentOrderWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        container: ServiceContainer,
        settings: Settings,
        *,
        owner: str,
        clock: Clock = utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._container = container
        self._settings = settings
        self._owner = owner
        self._clock = clock
        self._logger = structlog.get_logger("greenflex.worker")

    async def run_once(self) -> bool:
        async with self._session_factory() as session:
            order_id = await self._lease_next(session)
        if order_id is None:
            return False
        try:
            await self._process_order(order_id)
        except Exception:
            self._logger.exception("order_execution_interrupted", order_id=order_id)
            await self._release_expired_lease(order_id)
        return True

    async def run(self, stop_event: asyncio.Event) -> None:
        self._logger.info("worker_started", owner=self._owner)
        while not stop_event.is_set():
            worked = await self.run_once()
            if worked:
                continue
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self._settings.worker_poll_seconds,
                )
            except TimeoutError:
                continue
        self._logger.info("worker_stopped", owner=self._owner)

    async def _lease_next(self, session: AsyncSession) -> str | None:
        now = _aware_utc(self._clock())
        runnable = _runnable_condition(now)
        order_id = await session.scalar(
            select(OrderRecord.id)
            .where(runnable)
            .order_by(OrderRecord.scheduled_start, OrderRecord.created_at)
            .limit(1)
        )
        if order_id is None:
            return None
        result = await session.execute(
            update(OrderRecord)
            .where(OrderRecord.id == order_id, _runnable_condition(now))
            .values(
                status=OrderStatus.RUNNING.value,
                lease_owner=self._owner,
                lease_expires_at=now + timedelta(seconds=self._settings.worker_lease_seconds),
                started_at=func.coalesce(OrderRecord.started_at, now),
            )
        )
        if result.rowcount != 1:  # type: ignore[attr-defined]
            await session.rollback()
            return None
        await session.commit()
        return order_id

    async def _process_order(self, order_id: str) -> None:
        async with self._session_factory() as session:
            order = await session.scalar(
                select(OrderRecord)
                .where(OrderRecord.id == order_id, OrderRecord.lease_owner == self._owner)
                .options(
                    selectinload(OrderRecord.items),
                    selectinload(OrderRecord.model),
                    selectinload(OrderRecord.quote),
                )
            )
            if order is None or OrderStatus(order.status) is not OrderStatus.RUNNING:
                return

            capture = TelemetryCapture(
                self._container.telemetry,
                idle_seconds=self._settings.telemetry_idle_seconds,
            )
            async with capture:
                for item in order.items:
                    if ItemStatus(item.status) in {ItemStatus.SUCCEEDED, ItemStatus.FAILED}:
                        continue
                    await self._execute_item(session, order, item)
            await self._finalize_order(session, order, capture.measurement())

    async def _execute_item(
        self,
        session: AsyncSession,
        order: OrderRecord,
        item: OrderItemRecord,
    ) -> None:
        if item.prompt is None:
            item.status = ItemStatus.FAILED.value
            item.error_code = "content_unavailable"
            await self._renew_and_commit(session, order)
            return

        item.status = ItemStatus.RUNNING.value
        item.error_code = None
        await self._renew_and_commit(session, order)
        request = GenerationRequest(
            model_name=order.model.runtime_name,
            prompt=item.prompt,
            system_prompt=item.system_prompt,
            max_output_tokens=item.max_output_tokens,
        )

        result: GenerationResult | None = None
        error_code = "inference_failed"
        for attempt in range(2):
            try:
                result = await self._container.inference.generate(request)
                break
            except DomainError as exc:
                error_code = exc.code
            except Exception:
                error_code = "inference_failed"
            if attempt == 0:
                await asyncio.sleep(0.2)

        if result is None:
            item.status = ItemStatus.FAILED.value
            item.error_code = error_code
        else:
            item.status = ItemStatus.SUCCEEDED.value
            item.output = result.output
            item.prompt_tokens = result.prompt_tokens
            item.output_tokens = result.output_tokens
            item.duration_us = result.duration_us
            item.error_code = None
        await self._renew_and_commit(session, order)

    async def _renew_and_commit(self, session: AsyncSession, order: OrderRecord) -> None:
        now = _aware_utc(self._clock())
        order.lease_expires_at = now + timedelta(seconds=self._settings.worker_lease_seconds)
        await session.commit()

    async def _finalize_order(
        self,
        session: AsyncSession,
        order: OrderRecord,
        measurement: TelemetryMeasurement,
    ) -> None:
        now = _aware_utc(self._clock())
        succeeded = [item for item in order.items if item.status == ItemStatus.SUCCEEDED.value]
        failed = [item for item in order.items if item.status == ItemStatus.FAILED.value]
        input_tokens = sum(item.prompt_tokens or 0 for item in succeeded)
        output_tokens = sum(item.output_tokens or 0 for item in succeeded)

        if succeeded and failed:
            final_status = OrderStatus.PARTIAL_SUCCESS
        elif succeeded:
            final_status = OrderStatus.SUCCEEDED
        else:
            final_status = OrderStatus.FAILED

        order.actual_price_micro_rmb = self._container.pricing.settle_micro_rmb(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_rate=order.model.input_rate_micro_rmb_per_million,
            output_rate=order.model.output_rate_micro_rmb_per_million,
            discount_bps=order.quote.discount_bps,
        )
        measured = measurement.gross_energy_micro_wh is not None
        gross_energy = measurement.gross_energy_micro_wh
        incremental_energy = measurement.incremental_energy_micro_wh
        telemetry_source = measurement.source
        if gross_energy is None:
            gross_energy = (
                order.model.estimated_energy_micro_wh_per_1k_output * output_tokens // 1_000
            )
            incremental_energy = None
            telemetry_source = f"{measurement.source}:catalog-estimate"

        facility_energy = gross_energy * PUE_BPS // 10_000
        signal = self._container.signals.signal_at(order.started_at or now)
        location_carbon = micro_wh_to_carbon_micro_g(
            facility_energy,
            signal.carbon_g_per_kwh,
        )
        order.status = final_status.value
        order.gross_gpu_energy_micro_wh = gross_energy
        order.incremental_gpu_energy_micro_wh = incremental_energy
        order.facility_energy_micro_wh = facility_energy
        order.location_carbon_micro_g = location_carbon
        order.completed_at = now
        order.lease_owner = None
        order.lease_expires_at = None

        artifact = write_telemetry_artifact(
            measurement.samples,
            self._settings.artifact_dir,
            order.id,
        )
        execution = ExecutionRecord(
            id=str(uuid4()),
            order_id=order.id,
            telemetry_source=telemetry_source,
            telemetry_provenance=(
                Provenance.MEASURED.value if measured else Provenance.ESTIMATED.value
            ),
            idle_power_mw=measurement.idle_power_mw,
            average_power_mw=measurement.average_power_mw,
            peak_power_mw=measurement.peak_power_mw,
            sample_count=len(measurement.samples),
            raw_artifact_path=artifact[0] if artifact else None,
            raw_artifact_sha256=artifact[1] if artifact else None,
            created_at=now,
        )
        session.add(execution)

        payload = _passport_payload(
            order,
            execution,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            signal_carbon_g_per_kwh=signal.carbon_g_per_kwh,
            renewable_share_bps=signal.renewable_share_bps,
            signal_version=signal.source_version,
        )
        serialized, digest = passport_hash(payload)
        session.add(
            PassportRecord(
                id=str(uuid4()),
                order_id=order.id,
                payload_json=serialized,
                payload_sha256=digest,
                created_at=now,
            )
        )
        session.add(
            AuditEventRecord(
                id=str(uuid4()),
                entity_type="order",
                entity_id=order.id,
                event_type=f"order_{final_status.value}",
                metadata_json=json.dumps(
                    {"succeeded_count": len(succeeded), "failed_count": len(failed)},
                    separators=(",", ":"),
                ),
                created_at=now,
            )
        )
        await session.commit()
        self._logger.info(
            "order_execution_completed",
            order_id=order.id,
            status=final_status.value,
            item_count=len(order.items),
        )

    async def _release_expired_lease(self, order_id: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(OrderRecord)
                .where(
                    OrderRecord.id == order_id,
                    OrderRecord.lease_owner == self._owner,
                    OrderRecord.status == OrderStatus.RUNNING.value,
                )
                .values(lease_expires_at=_aware_utc(self._clock()))
            )
            await session.commit()


def _runnable_condition(now: datetime) -> Any:
    return or_(
        and_(
            OrderRecord.status.in_([OrderStatus.QUEUED.value, OrderStatus.SCHEDULED.value]),
            OrderRecord.scheduled_start <= now,
        ),
        and_(
            OrderRecord.status == OrderStatus.RUNNING.value,
            or_(OrderRecord.lease_expires_at.is_(None), OrderRecord.lease_expires_at <= now),
        ),
    )


def _passport_payload(
    order: OrderRecord,
    execution: ExecutionRecord,
    *,
    input_tokens: int,
    output_tokens: int,
    signal_carbon_g_per_kwh: int,
    renewable_share_bps: int,
    signal_version: str,
) -> dict[str, object]:
    input_digest = _content_digest(
        [
            {
                "client_item_id": item.client_item_id,
                "prompt_sha256": _text_digest(item.prompt),
                "system_prompt_sha256": _text_digest(item.system_prompt),
                "max_output_tokens": item.max_output_tokens,
            }
            for item in order.items
        ]
    )
    result_digest = _content_digest(
        [
            {
                "client_item_id": item.client_item_id,
                "status": item.status,
                "output_sha256": _text_digest(item.output),
                "error_code": item.error_code,
            }
            for item in order.items
        ]
    )
    return {
        "schema_version": "token-passport-v1",
        "passport_kind": "simulated-green-token-passport",
        "order": {
            "order_id": order.id,
            "status": order.status,
            "execution_mode": order.execution_mode,
            "scheduled_start": _aware_utc(order.scheduled_start).isoformat(),
            "started_at": _aware_utc(order.started_at).isoformat() if order.started_at else None,
            "completed_at": (
                _aware_utc(order.completed_at).isoformat() if order.completed_at else None
            ),
        },
        "model": {
            "catalog_id": order.model_id,
            "runtime_name": order.model.runtime_name,
            "digest": order.model.digest,
        },
        "content_integrity": {
            "input_manifest_sha256": input_digest,
            "result_manifest_sha256": result_digest,
            "raw_content_included": False,
        },
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "token_provenance": Provenance.MEASURED.value,
        },
        "gpu_energy": {
            "gross_micro_wh": order.gross_gpu_energy_micro_wh,
            "incremental_micro_wh": order.incremental_gpu_energy_micro_wh,
            "provenance": execution.telemetry_provenance,
            "source": execution.telemetry_source,
            "idle_power_mw": execution.idle_power_mw,
            "average_power_mw": execution.average_power_mw,
            "peak_power_mw": execution.peak_power_mw,
            "sample_count": execution.sample_count,
            "artifact_sha256": execution.raw_artifact_sha256,
        },
        "facility_energy": {
            "micro_wh": order.facility_energy_micro_wh,
            "pue_basis_points": PUE_BPS,
            "provenance": Provenance.ESTIMATED.value,
            "pue_source": "simulated-pue-v1",
        },
        "location_carbon": {
            "micro_g_co2e": order.location_carbon_micro_g,
            "carbon_g_per_kwh": signal_carbon_g_per_kwh,
            "provenance": Provenance.ESTIMATED.value,
            "factor_provenance": Provenance.SIMULATED.value,
            "signal_version": signal_version,
        },
        "green_grade": {
            "grade": _simulated_green_grade(renewable_share_bps),
            "renewable_share_bps": renewable_share_bps,
            "provenance": Provenance.SIMULATED.value,
            "method_version": "green-grade-sim-v1",
        },
        "bill": {
            "currency": "CNY",
            "quoted_micro_rmb": order.quoted_price_micro_rmb,
            "actual_micro_rmb": order.actual_price_micro_rmb,
            "pricing_version": order.quote.pricing_version,
            "discount_bps": order.quote.discount_bps,
            "vpp_rebate_micro_rmb": 0,
            "provenance": Provenance.SIMULATED.value,
        },
        "claims": {
            "official_certification": False,
            "zero_carbon": False,
            "market_based_claim": False,
        },
    }


def _content_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text_digest(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value is not None else None


def _simulated_green_grade(renewable_share_bps: int) -> str:
    if renewable_share_bps >= 6_000:
        return "A"
    if renewable_share_bps >= 4_500:
        return "B"
    if renewable_share_bps >= 3_000:
        return "C"
    if renewable_share_bps >= 1_500:
        return "D"
    return "E"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
