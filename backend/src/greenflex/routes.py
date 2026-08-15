from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from greenflex.container import ServiceContainer
from greenflex.db import get_session
from greenflex.domain import DomainError, ModelTier
from greenflex.models import PassportRecord
from greenflex.runtime_settings import validate_api_key
from greenflex.schemas import (
    CarbonCalendarDay,
    CarbonCalendarHour,
    CarbonCalendarResponse,
    ChatRequest,
    ChatResponse,
    CloudApiProviderStatus,
    CloudApiSettingsResponse,
    CloudApiSettingsUpdate,
    CreateOrderRequest,
    GridRegionInfo,
    GridRegionResponse,
    ModelCatalogItem,
    OrderView,
    PassportView,
    PreviewRequest,
    PreviewResponse,
    QuoteRequest,
    QuoteResponse,
    RecommendationRequest,
    RecommendationResponse,
)
from greenflex.services import (
    cancel_order,
    chat,
    create_order,
    create_quotes,
    create_recommendation,
    get_order,
    get_passport,
    list_models,
    list_orders,
    order_view,
    parse_batch_upload,
    preview,
    purge_order_content,
    results_csv,
)
from greenflex.signals import GRID_REGIONS, SyntheticEnergySignalProvider

router = APIRouter(prefix="/api/v1")
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


ContainerDep = Annotated[ServiceContainer, Depends(get_container)]


def verify_admin_token(
    container: ContainerDep,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    """Verify the admin token for settings write operations."""
    expected = container.admin_token
    if not expected:
        return  # No token configured (should not happen in normal operation)
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise DomainError("admin_token_required", "需要管理员令牌才能修改设置。", 401)


@router.get("/models", response_model=list[ModelCatalogItem])
async def models(session: SessionDep, container: ContainerDep) -> list[ModelCatalogItem]:
    return await list_models(session, container)


@router.get("/signals/calendar", response_model=CarbonCalendarResponse)
async def signals_calendar(
    container: ContainerDep,
    days: Annotated[int, Query(ge=1, le=14)] = 7,
    region: Annotated[str | None, Query()] = None,
) -> CarbonCalendarResponse:
    provider = (
        SyntheticEnergySignalProvider(region=region)
        if region and region in GRID_REGIONS
        else container.signals
    )
    now = datetime.now(UTC).astimezone()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    result_days: list[CarbonCalendarDay] = []
    for day_offset in range(days):
        day_start = today + timedelta(days=day_offset)
        hours: list[CarbonCalendarHour] = []
        for hour in range(24):
            instant = day_start + timedelta(hours=hour)
            signal = provider.signal_at(instant)
            hours.append(
                CarbonCalendarHour(
                    hour=hour,
                    carbon_g_per_kwh=signal.carbon_g_per_kwh,
                    price_micro_rmb_per_kwh=signal.price_micro_rmb_per_kwh,
                    renewable_share_bps=signal.renewable_share_bps,
                )
            )
        result_days.append(CarbonCalendarDay(date=day_start.strftime("%Y-%m-%d"), hours=hours))
    return CarbonCalendarResponse(
        region=provider.region.code,
        signal_version=provider.version,
        days=result_days,
    )


@router.get("/signals/regions", response_model=GridRegionResponse)
async def signals_regions(container: ContainerDep) -> GridRegionResponse:
    return GridRegionResponse(
        current=container.signals.region.code,
        regions=[
            GridRegionInfo(
                code=r.code,
                name_zh=r.name_zh,
                carbon_g_per_kwh=r.carbon_g_per_kwh,
                renewable_share_bps=r.renewable_share_bps,
            )
            for r in SyntheticEnergySignalProvider.available_regions()
        ],
    )


@router.post("/previews", response_model=PreviewResponse)
async def previews(
    payload: PreviewRequest,
    session: SessionDep,
    container: ContainerDep,
) -> PreviewResponse:
    return await preview(session, container, payload)


@router.post("/recommendations", response_model=RecommendationResponse)
async def recommendations(
    payload: RecommendationRequest,
    session: SessionDep,
    container: ContainerDep,
) -> RecommendationResponse:
    return await create_recommendation(session, container, payload)


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ChatRequest,
    session: SessionDep,
    container: ContainerDep,
) -> ChatResponse:
    return await chat(session, container, payload)


@router.get("/settings/cloud-api", response_model=CloudApiSettingsResponse)
async def get_cloud_api_settings(container: ContainerDep) -> CloudApiSettingsResponse:
    store = container.runtime_settings
    if store is None:
        return CloudApiSettingsResponse(providers=[], timeout_seconds=120)
    providers = [CloudApiProviderStatus(**p) for p in store.provider_status()]
    return CloudApiSettingsResponse(
        providers=providers,
        timeout_seconds=store.get_timeout(),
    )


@router.get("/settings/admin-token-status")
async def admin_token_status(
    container: ContainerDep,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> dict[str, bool]:
    """Check whether the provided admin token is valid."""
    expected = container.admin_token
    if not expected:
        return {"valid": True}
    return {"valid": bool(x_admin_token and hmac.compare_digest(x_admin_token, expected))}


@router.put("/settings/cloud-api", response_model=CloudApiSettingsResponse)
async def update_cloud_api_settings(
    payload: CloudApiSettingsUpdate,
    container: ContainerDep,
    _: Annotated[None, Depends(verify_admin_token)],
) -> CloudApiSettingsResponse:
    store = container.runtime_settings
    if store is None:
        return CloudApiSettingsResponse(providers=[], timeout_seconds=120)

    # Validate API key formats before saving
    key_fields = (
        "openai_api_key",
        "anthropic_api_key",
        "deepseek_api_key",
        "alibaba_api_key",
        "bytedance_api_key",
        "google_api_key",
    )
    for field_name in key_fields:
        val = getattr(payload, field_name, None)
        if val and val.strip() and not validate_api_key(val):
            raise DomainError(
                "invalid_api_key",
                f"API Key 格式无效（字段 {field_name}），应为 8-256 位字母、数字、连字符或下划线。",
                422,
            )

    updates: dict[str, str | None] = {}
    for field_name in (
        *key_fields,
        "openai_base_url",
        "anthropic_base_url",
        "deepseek_base_url",
        "alibaba_base_url",
        "bytedance_base_url",
        "google_base_url",
    ):
        val = getattr(payload, field_name, None)
        if val is not None:
            updates[field_name] = val.strip() if isinstance(val, str) else val
    if payload.timeout_seconds is not None:
        updates["cloud_api_timeout_seconds"] = str(payload.timeout_seconds)
    if updates:
        store.update(updates)
    providers = [CloudApiProviderStatus(**p) for p in store.provider_status()]
    return CloudApiSettingsResponse(
        providers=providers,
        timeout_seconds=store.get_timeout(),
    )


@router.post("/quotes", response_model=QuoteResponse)
async def quotes(
    payload: QuoteRequest,
    session: SessionDep,
    container: ContainerDep,
) -> QuoteResponse:
    return QuoteResponse(options=await create_quotes(session, container, payload))


@router.post("/quotes/upload", response_model=QuoteResponse)
async def upload_quote(
    session: SessionDep,
    container: ContainerDep,
    file: Annotated[UploadFile, File()],
    model_id: Annotated[str | None, Form()] = None,
    tier: Annotated[ModelTier | None, Form()] = None,
    deadline: Annotated[datetime | None, Form()] = None,
) -> QuoteResponse:
    content = await file.read(5 * 1024 * 1024 + 1)
    items = parse_batch_upload(file.filename or "upload", content)
    request = QuoteRequest(items=items, model_id=model_id, tier=tier, deadline=deadline)
    return QuoteResponse(options=await create_quotes(session, container, request))


@router.post("/orders", response_model=OrderView)
async def orders_create(payload: CreateOrderRequest, session: SessionDep) -> OrderView:
    return await create_order(session, payload.quote_id)


@router.get("/orders", response_model=list[OrderView])
async def orders_list(session: SessionDep) -> list[OrderView]:
    return await list_orders(session)


@router.get("/orders/{order_id}", response_model=OrderView)
async def orders_get(order_id: str, session: SessionDep) -> OrderView:
    return order_view(await get_order(session, order_id), include_items=True)


@router.post("/orders/{order_id}/cancel", response_model=OrderView)
async def orders_cancel(order_id: str, session: SessionDep) -> OrderView:
    return await cancel_order(session, order_id)


@router.delete("/orders/{order_id}/content", response_model=OrderView)
async def orders_purge(order_id: str, session: SessionDep) -> OrderView:
    return await purge_order_content(session, order_id)


@router.get("/orders/{order_id}/results")
async def orders_results(order_id: str, session: SessionDep) -> Response:
    content = await results_csv(session, order_id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="greenflex-{order_id}.csv"'},
    )


@router.get("/passports/{passport_id}", response_model=PassportView)
async def passports_get(passport_id: str, session: SessionDep) -> PassportView:
    return await get_passport(session, passport_id)


@router.get("/orders/{order_id}/passport", response_model=PassportView)
async def passport_by_order(order_id: str, session: SessionDep) -> PassportView:
    record = await session.scalar(select(PassportRecord).where(PassportRecord.order_id == order_id))
    if record is None:
        return await get_passport(session, "missing")
    return await get_passport(session, record.id)
