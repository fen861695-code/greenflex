from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from greenflex.container import ServiceContainer
from greenflex.db import get_session
from greenflex.domain import ModelTier
from greenflex.models import PassportRecord
from greenflex.schemas import (
    CreateOrderRequest,
    ModelCatalogItem,
    OrderView,
    PassportView,
    PreviewRequest,
    PreviewResponse,
    QuoteRequest,
    QuoteResponse,
)
from greenflex.services import (
    cancel_order,
    create_order,
    create_quotes,
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

router = APIRouter(prefix="/api/v1")
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


ContainerDep = Annotated[ServiceContainer, Depends(get_container)]


@router.get("/models", response_model=list[ModelCatalogItem])
async def models(session: SessionDep, container: ContainerDep) -> list[ModelCatalogItem]:
    return await list_models(session, container)


@router.post("/previews", response_model=PreviewResponse)
async def previews(
    payload: PreviewRequest,
    session: SessionDep,
    container: ContainerDep,
) -> PreviewResponse:
    return await preview(session, container, payload)


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
