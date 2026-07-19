from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from greenflex.config import get_settings
from greenflex.container import ServiceContainer
from greenflex.domain import (
    TERMINAL_ORDER_STATUSES,
    DomainError,
    ExecutionMode,
    ItemStatus,
    ModelTier,
    OrderStatus,
    Provenance,
    utc_now,
)
from greenflex.models import (
    AuditEventRecord,
    ExecutionRecord,
    ModelRecord,
    OrderItemRecord,
    OrderRecord,
    PassportRecord,
    QuoteRecord,
)
from greenflex.ports import GenerationRequest
from greenflex.schemas import (
    BatchItemInput,
    ModelCatalogItem,
    OrderItemView,
    OrderView,
    PassportView,
    PreviewRequest,
    PreviewResponse,
    QuoteOption,
    QuoteRequest,
)
from greenflex.telemetry import TelemetryCapture
from greenflex.units import (
    basis_points_to_percent,
    micro_to_decimal_string,
    micro_wh_to_carbon_micro_g,
)

DEFAULT_TENANT_ID = "local-demo"
PUE_BPS = 12_000
QUOTE_TTL_MINUTES = 15
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def estimate_input_tokens(items: list[BatchItemInput]) -> int:
    characters = sum(len(item.prompt) + len(item.system_prompt or "") for item in items)
    return max(len(items), math.ceil(characters / 3))


def parse_batch_upload(filename: str, payload: bytes) -> list[BatchItemInput]:
    if len(payload) > MAX_UPLOAD_BYTES:
        raise DomainError("upload_too_large", "上传文件不能超过 5MB。", 413)
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DomainError("invalid_encoding", "上传文件必须使用 UTF-8 编码。") from exc

    lowered = filename.lower()
    raw_items: list[dict[str, object]] = []
    if lowered.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        required = {"client_item_id", "prompt"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise DomainError("invalid_upload_schema", "CSV 必须包含 client_item_id 和 prompt 列。")
        for row in reader:
            raw_items.append(
                {
                    "client_item_id": row.get("client_item_id", ""),
                    "prompt": row.get("prompt", ""),
                    "system_prompt": row.get("system_prompt") or None,
                    "max_output_tokens": row.get("max_output_tokens") or 256,
                }
            )
    elif lowered.endswith(".jsonl"):
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DomainError(
                    "invalid_jsonl",
                    f"JSONL 第 {line_number} 行不是有效 JSON。",
                ) from exc
            if not isinstance(value, dict):
                raise DomainError("invalid_jsonl", f"JSONL 第 {line_number} 行必须是对象。")
            raw_items.append(value)
    else:
        raise DomainError("unsupported_file_type", "仅支持 .csv 和 .jsonl 文件。")

    if not raw_items:
        raise DomainError("empty_upload", "上传文件中没有任务。")
    if len(raw_items) > 500:
        raise DomainError("too_many_items", "单个订单最多包含 500 条任务。")
    try:
        items = [BatchItemInput.model_validate(item) for item in raw_items]
    except ValueError as exc:
        raise DomainError("invalid_upload_item", "上传文件包含不合法的任务字段。") from exc
    identifiers = [item.client_item_id for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise DomainError("duplicate_client_item_id", "client_item_id 不能重复。")
    return items


def estimate_runtime_seconds(model: ModelRecord, items: list[BatchItemInput]) -> int:
    output_tokens = sum(item.max_output_tokens for item in items)
    generation = math.ceil(output_tokens / max(model.estimated_tokens_per_second, 1))
    return max(1, generation + len(items))


async def list_models(
    session: AsyncSession,
    container: ServiceContainer,
) -> list[ModelCatalogItem]:
    available = await container.inference.available_models()
    models = (await session.scalars(select(ModelRecord).where(ModelRecord.enabled.is_(True)))).all()
    catalog_changed = False
    for model in models:
        digest = available.get(model.runtime_name)
        if digest not in {None, "installed"} and digest != model.digest:
            model.digest = digest
            catalog_changed = True
    if catalog_changed:
        await session.commit()
    return [
        ModelCatalogItem(
            id=model.id,
            display_name=model.display_name,
            runtime_name=model.runtime_name,
            tier=ModelTier(model.tier),
            parameter_b=model.parameter_b,
            context_limit=model.context_limit,
            recommended_for=json.loads(model.recommended_for_json),
            input_rate_rmb_per_million=micro_to_decimal_string(
                model.input_rate_micro_rmb_per_million
            ),
            output_rate_rmb_per_million=micro_to_decimal_string(
                model.output_rate_micro_rmb_per_million
            ),
            available=model.runtime_name in available,
            availability_detail=(
                f"已安装 · {available[model.runtime_name][:19]}"
                if model.runtime_name in available
                else "未安装或运行时离线"
            ),
        )
        for model in models
    ]


async def preview(
    session: AsyncSession,
    container: ServiceContainer,
    request: PreviewRequest,
) -> PreviewResponse:
    model = await session.get(ModelRecord, request.model_id)
    if model is None or not model.enabled:
        raise DomainError("model_not_found", "指定模型不存在或已停用。", 404)
    available = await container.inference.available_models()
    if model.runtime_name not in available:
        raise DomainError("inference_unavailable", "所选本地模型尚未安装或 Ollama 未运行。", 503)

    settings = get_settings()
    capture = TelemetryCapture(
        container.telemetry,
        idle_seconds=settings.telemetry_idle_seconds,
    )
    async with capture:
        result = await container.inference.generate(
            GenerationRequest(
                model_name=model.runtime_name,
                prompt=request.prompt,
                system_prompt=request.system_prompt,
                max_output_tokens=request.max_output_tokens,
            )
        )
    measurement = capture.measurement()
    measured = measurement.gross_energy_micro_wh is not None
    return PreviewResponse(
        model_id=model.id,
        output=result.output,
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.output_tokens,
        latency_ms=micro_to_decimal_string(result.duration_us * 1_000, places=3),
        gross_gpu_energy_wh=(
            micro_to_decimal_string(measurement.gross_energy_micro_wh)
            if measurement.gross_energy_micro_wh is not None
            else None
        ),
        incremental_gpu_energy_wh=(
            micro_to_decimal_string(measurement.incremental_energy_micro_wh)
            if measurement.incremental_energy_micro_wh is not None
            else None
        ),
        telemetry_provenance=Provenance.MEASURED if measured else Provenance.ESTIMATED,
        telemetry_source=measurement.source,
    )


async def create_quotes(
    session: AsyncSession,
    container: ServiceContainer,
    request: QuoteRequest,
    *,
    now: datetime | None = None,
) -> list[QuoteOption]:
    created_at = _aware_utc(now or utc_now())
    query = select(ModelRecord).where(ModelRecord.enabled.is_(True))
    if request.model_id is not None:
        query = query.where(ModelRecord.id == request.model_id)
    if request.tier is not None:
        query = query.where(ModelRecord.tier == request.tier.value)
    models = (await session.scalars(query)).all()
    if not models:
        raise DomainError("model_not_found", "没有符合条件的模型。", 404)

    input_tokens = estimate_input_tokens(request.items)
    output_tokens = sum(item.max_output_tokens for item in request.items)
    content_json = json.dumps(
        [item.model_dump(mode="json") for item in request.items],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    deadline = _aware_utc(request.deadline) if request.deadline is not None else None
    modes = [ExecutionMode.IMMEDIATE]
    if deadline is not None:
        modes.append(ExecutionMode.FLEXIBLE)

    records: list[QuoteRecord] = []
    for model in models:
        runtime_seconds = estimate_runtime_seconds(model, request.items)
        for mode in modes:
            try:
                slot = container.scheduling.choose_slot(
                    mode=mode,
                    now=created_at,
                    runtime_seconds=runtime_seconds,
                    deadline=deadline,
                )
            except DomainError:
                if mode is ExecutionMode.FLEXIBLE:
                    continue
                raise
            flexibility = max(0, int(((deadline or created_at) - created_at).total_seconds()))
            discount_bps = container.pricing.discount_bps(mode, flexibility)
            base_price = container.pricing.settle_micro_rmb(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_rate=model.input_rate_micro_rmb_per_million,
                output_rate=model.output_rate_micro_rmb_per_million,
                discount_bps=0,
            )
            total_price = container.pricing.settle_micro_rmb(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_rate=model.input_rate_micro_rmb_per_million,
                output_rate=model.output_rate_micro_rmb_per_million,
                discount_bps=discount_bps,
            )
            gpu_energy = model.estimated_energy_micro_wh_per_1k_output * output_tokens // 1_000
            facility_energy = gpu_energy * PUE_BPS // 10_000
            carbon = micro_wh_to_carbon_micro_g(
                facility_energy,
                slot.signal.carbon_g_per_kwh,
            )
            records.append(
                QuoteRecord(
                    id=str(uuid4()),
                    tenant_id=DEFAULT_TENANT_ID,
                    model_id=model.id,
                    execution_mode=mode.value,
                    item_count=len(request.items),
                    input_tokens_est=input_tokens,
                    output_tokens_est=output_tokens,
                    content_json=content_json,
                    scheduled_start=slot.start,
                    scheduled_end=slot.end,
                    deadline=deadline,
                    base_price_micro_rmb=base_price,
                    discount_bps=discount_bps,
                    discount_micro_rmb=base_price - total_price,
                    vpp_rebate_micro_rmb=0,
                    total_price_micro_rmb=total_price,
                    facility_energy_micro_wh_est=facility_energy,
                    carbon_micro_g_est=carbon,
                    renewable_share_bps=slot.signal.renewable_share_bps,
                    signal_version=slot.signal.source_version,
                    pricing_version=container.pricing.version,
                    created_at=created_at,
                    expires_at=created_at + timedelta(minutes=QUOTE_TTL_MINUTES),
                    model=model,
                )
            )
    if not records:
        raise DomainError("no_feasible_schedule", "没有满足截止时间的报价。", 409)
    session.add_all(records)
    await session.commit()
    return [_quote_view(record) for record in records]


def _quote_view(record: QuoteRecord) -> QuoteOption:
    return QuoteOption(
        quote_id=record.id,
        model_id=record.model_id,
        model_name=record.model.display_name,
        tier=ModelTier(record.model.tier),
        execution_mode=ExecutionMode(record.execution_mode),
        item_count=record.item_count,
        estimated_input_tokens=record.input_tokens_est,
        estimated_output_tokens=record.output_tokens_est,
        scheduled_start=_aware_utc(record.scheduled_start),
        scheduled_end=_aware_utc(record.scheduled_end),
        deadline=_aware_utc(record.deadline) if record.deadline is not None else None,
        base_price_rmb=micro_to_decimal_string(record.base_price_micro_rmb),
        discount_percent=basis_points_to_percent(record.discount_bps),
        discount_rmb=micro_to_decimal_string(record.discount_micro_rmb),
        vpp_rebate_rmb=micro_to_decimal_string(record.vpp_rebate_micro_rmb),
        total_price_rmb=micro_to_decimal_string(record.total_price_micro_rmb),
        facility_energy_wh_est=micro_to_decimal_string(record.facility_energy_micro_wh_est),
        carbon_g_est=micro_to_decimal_string(record.carbon_micro_g_est),
        renewable_share_percent=basis_points_to_percent(record.renewable_share_bps),
        pricing_version=record.pricing_version,
        signal_version=record.signal_version,
        expires_at=_aware_utc(record.expires_at),
    )


async def create_order(
    session: AsyncSession,
    quote_id: str,
    *,
    now: datetime | None = None,
) -> OrderView:
    existing = await session.scalar(
        select(OrderRecord)
        .where(OrderRecord.quote_id == quote_id)
        .options(selectinload(OrderRecord.items), selectinload(OrderRecord.model))
    )
    if existing is not None:
        return order_view(existing, include_items=True)

    quote = await session.scalar(
        select(QuoteRecord)
        .where(QuoteRecord.id == quote_id)
        .options(selectinload(QuoteRecord.model))
    )
    if quote is None:
        raise DomainError("quote_not_found", "报价不存在。", 404)
    created_at = _aware_utc(now or utc_now())
    if _aware_utc(quote.expires_at) < created_at:
        raise DomainError("quote_expired", "报价已过期, 请重新获取。", 409)

    status = (
        OrderStatus.SCHEDULED
        if _aware_utc(quote.scheduled_start) > created_at + timedelta(seconds=1)
        else OrderStatus.QUEUED
    )
    order = OrderRecord(
        id=str(uuid4()),
        tenant_id=quote.tenant_id,
        quote_id=quote.id,
        model_id=quote.model_id,
        execution_mode=quote.execution_mode,
        status=status.value,
        scheduled_start=quote.scheduled_start,
        deadline=quote.deadline,
        quoted_price_micro_rmb=quote.total_price_micro_rmb,
        created_at=created_at,
        model=quote.model,
    )
    items = [BatchItemInput.model_validate(item) for item in json.loads(quote.content_json)]
    order.items = [
        OrderItemRecord(
            id=str(uuid4()),
            position=position,
            client_item_id=item.client_item_id,
            prompt=item.prompt,
            system_prompt=item.system_prompt,
            max_output_tokens=item.max_output_tokens,
            status=ItemStatus.PENDING.value,
        )
        for position, item in enumerate(items)
    ]
    session.add(order)
    session.add(
        AuditEventRecord(
            id=str(uuid4()),
            entity_type="order",
            entity_id=order.id,
            event_type=f"order_{status.value}",
            created_at=created_at,
        )
    )
    await session.commit()
    loaded = await get_order(session, order.id)
    return order_view(loaded, include_items=True)


async def list_orders(session: AsyncSession) -> list[OrderView]:
    orders = (
        await session.scalars(
            select(OrderRecord)
            .where(OrderRecord.tenant_id == DEFAULT_TENANT_ID)
            .options(selectinload(OrderRecord.items), selectinload(OrderRecord.model))
            .order_by(OrderRecord.created_at.desc())
        )
    ).all()
    return [order_view(order) for order in orders]


async def get_order(session: AsyncSession, order_id: str) -> OrderRecord:
    order = await session.scalar(
        select(OrderRecord)
        .where(OrderRecord.id == order_id, OrderRecord.tenant_id == DEFAULT_TENANT_ID)
        .options(selectinload(OrderRecord.items), selectinload(OrderRecord.model))
    )
    if order is None:
        raise DomainError("order_not_found", "订单不存在。", 404)
    return order


def order_view(order: OrderRecord, *, include_items: bool = False) -> OrderView:
    succeeded = sum(item.status == ItemStatus.SUCCEEDED.value for item in order.items)
    failed = sum(item.status == ItemStatus.FAILED.value for item in order.items)
    return OrderView(
        id=order.id,
        quote_id=order.quote_id,
        model_id=order.model_id,
        model_name=order.model.display_name,
        execution_mode=ExecutionMode(order.execution_mode),
        status=OrderStatus(order.status),
        scheduled_start=_aware_utc(order.scheduled_start),
        deadline=_aware_utc(order.deadline) if order.deadline is not None else None,
        quoted_price_rmb=micro_to_decimal_string(order.quoted_price_micro_rmb),
        actual_price_rmb=(
            micro_to_decimal_string(order.actual_price_micro_rmb)
            if order.actual_price_micro_rmb is not None
            else None
        ),
        item_count=len(order.items),
        succeeded_count=succeeded,
        failed_count=failed,
        gross_gpu_energy_wh=(
            micro_to_decimal_string(order.gross_gpu_energy_micro_wh)
            if order.gross_gpu_energy_micro_wh is not None
            else None
        ),
        incremental_gpu_energy_wh=(
            micro_to_decimal_string(order.incremental_gpu_energy_micro_wh)
            if order.incremental_gpu_energy_micro_wh is not None
            else None
        ),
        location_carbon_g=(
            micro_to_decimal_string(order.location_carbon_micro_g)
            if order.location_carbon_micro_g is not None
            else None
        ),
        content_purged=order.content_purged,
        created_at=_aware_utc(order.created_at),
        started_at=_aware_utc(order.started_at) if order.started_at is not None else None,
        completed_at=_aware_utc(order.completed_at) if order.completed_at is not None else None,
        items=[_item_view(item) for item in order.items] if include_items else None,
    )


def _item_view(item: OrderItemRecord) -> OrderItemView:
    return OrderItemView(
        client_item_id=item.client_item_id,
        status=ItemStatus(item.status),
        output=item.output,
        prompt_tokens=item.prompt_tokens,
        output_tokens=item.output_tokens,
        duration_ms=(
            micro_to_decimal_string(item.duration_us * 1_000, places=3)
            if item.duration_us is not None
            else None
        ),
        error_code=item.error_code,
    )


async def cancel_order(session: AsyncSession, order_id: str) -> OrderView:
    order = await get_order(session, order_id)
    if OrderStatus(order.status) not in {OrderStatus.QUEUED, OrderStatus.SCHEDULED}:
        raise DomainError("order_not_cancellable", "只有排队或已计划订单可以取消。", 409)
    order.status = OrderStatus.CANCELLED.value
    completed_at = utc_now()
    order.completed_at = completed_at
    session.add(
        AuditEventRecord(
            id=str(uuid4()),
            entity_type="order",
            entity_id=order.id,
            event_type="order_cancelled",
            created_at=completed_at,
        )
    )
    await session.commit()
    return order_view(order, include_items=True)


async def purge_order_content(session: AsyncSession, order_id: str) -> OrderView:
    return await purge_order_content_at(session, order_id, get_settings().artifact_dir)


async def purge_order_content_at(
    session: AsyncSession,
    order_id: str,
    artifact_dir: Path,
) -> OrderView:
    order = await get_order(session, order_id)
    if OrderStatus(order.status) not in TERMINAL_ORDER_STATUSES:
        raise DomainError("order_not_terminal", "只能清除已结束订单的内容。", 409)
    for item in order.items:
        item.prompt = None
        item.system_prompt = None
        item.output = None
    execution = await session.scalar(
        select(ExecutionRecord).where(ExecutionRecord.order_id == order.id)
    )
    if execution is not None and execution.raw_artifact_path is not None:
        await _delete_runtime_artifact(execution.raw_artifact_path, artifact_dir)
        execution.raw_artifact_path = None
    order.content_purged = True
    purged_at = utc_now()
    session.add(
        AuditEventRecord(
            id=str(uuid4()),
            entity_type="order",
            entity_id=order.id,
            event_type="order_content_purged",
            metadata_json=json.dumps(
                {"telemetry_artifact_deleted": execution is not None},
                separators=(",", ":"),
            ),
            created_at=purged_at,
        )
    )
    await session.commit()
    return order_view(order, include_items=True)


async def results_csv(session: AsyncSession, order_id: str) -> bytes:
    order = await get_order(session, order_id)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        ["client_item_id", "status", "output", "prompt_tokens", "output_tokens", "error_code"]
    )
    for item in order.items:
        writer.writerow(
            [
                item.client_item_id,
                item.status,
                item.output or "",
                item.prompt_tokens or "",
                item.output_tokens or "",
                item.error_code or "",
            ]
        )
    return output.getvalue().encode("utf-8-sig")


async def get_passport(session: AsyncSession, passport_id: str) -> PassportView:
    record = await session.get(PassportRecord, passport_id)
    if record is None:
        raise DomainError("passport_not_found", "凭证尚未生成或不存在。", 404)
    return PassportView(
        passport_id=record.id,
        order_id=record.order_id,
        payload_sha256=record.payload_sha256,
        payload=json.loads(record.payload_json),
        created_at=_aware_utc(record.created_at),
    )


def passport_hash(payload: dict[str, Any]) -> tuple[str, str]:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return serialized, hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def count_orders(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(OrderRecord)) or 0)


async def _delete_runtime_artifact(raw_path: str, artifact_dir: Path) -> None:
    artifact_root, candidate = await asyncio.gather(
        asyncio.to_thread(artifact_dir.resolve),
        asyncio.to_thread(Path(raw_path).resolve),
    )
    if candidate.is_relative_to(artifact_root):
        await asyncio.to_thread(candidate.unlink, missing_ok=True)
