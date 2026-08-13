from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
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
    RecommendationRequest,
    RecommendationResponse,
)
from greenflex.services import (
    cancel_order,
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


@router.post("/recommendations", response_model=RecommendationResponse)
async def recommendations(
    payload: RecommendationRequest,
    session: SessionDep,
    container: ContainerDep,
) -> RecommendationResponse:
    return await create_recommendation(session, container, payload)


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


# ---------------------------------------------------------------------------
# Carbon intensity endpoints (v2)
# ---------------------------------------------------------------------------
@router.get("/carbon-intensity/current")
async def carbon_intensity_current(
    session: SessionDep,
    container: ContainerDep,
) -> dict:
    """Get current grid carbon intensity with provenance."""
    from greenflex.carbon_intensity_service import CarbonIntensityService

    if container.carbon_service is None:
        # Fallback to synthetic signal
        signal = container.signals.signal_at(datetime.now())
        return {
            "carbon_g_per_kwh": signal.carbon_g_per_kwh,
            "renewable_share_bps": signal.renewable_share_bps,
            "price_micro_rmb_per_kwh": signal.price_micro_rmb_per_kwh,
            "data_source": signal.source_version,
            "provenance": signal.provenance,
            "interval_start": signal.interval_start.isoformat(),
        }

    signal = await container.carbon_service.get_current_signal()
    return {
        "carbon_g_per_kwh": signal.carbon_g_per_kwh,
        "renewable_share_bps": signal.renewable_share_bps,
        "price_micro_rmb_per_kwh": signal.price_micro_rmb_per_kwh,
        "data_source": signal.source_version,
        "provenance": signal.provenance,
        "interval_start": signal.interval_start.isoformat(),
    }


@router.get("/carbon-intensity/status")
async def carbon_intensity_status(
    session: SessionDep,
    container: ContainerDep,
) -> dict:
    """Get carbon intensity service status and provider chain."""
    if container.carbon_service is None:
        return {
            "active_provider": "SyntheticEnergySignalProvider",
            "region": "CN-HN",
            "cache_ttl_minutes": 15,
            "providers": [
                {"name": "SyntheticEnergySignalProvider", "available": True, "version": "synthetic-cn-east-v2"}
            ],
        }
    return await container.carbon_service.get_provider_status()


# ---------------------------------------------------------------------------
# Energy data endpoints (v2)
# ---------------------------------------------------------------------------
@router.get("/energy/benchmarks")
async def energy_benchmarks(
    session: SessionDep,
    container: ContainerDep,
) -> list[dict]:
    """List available model energy benchmark data."""
    from greenflex.models import ModelEnergyBenchmarkRecord

    records = await session.scalars(select(ModelEnergyBenchmarkRecord))
    return [
        {
            "id": r.id,
            "model_family": r.model_family,
            "parameter_count_b": r.parameter_count_b,
            "quantization_bits": r.quantization_bits,
            "gpu_model": r.gpu_model,
            "avg_power_watts": r.avg_power_watts,
            "throughput_tokens_per_second": r.throughput_tokens_per_second,
            "energy_wh_per_1k_output": r.energy_wh_per_1k_output,
            "dataset_source": r.dataset_source,
            "provenance_tier": r.provenance_tier,
            "confidence_bps": r.confidence_bps,
        }
        for r in records
    ]


@router.get("/energy/gpu-profiles")
async def energy_gpu_profiles(
    session: SessionDep,
    container: ContainerDep,
) -> list[dict]:
    """List GPU energy efficiency profiles."""
    from greenflex.models import GpuEnergyProfileRecord

    records = await session.scalars(select(GpuEnergyProfileRecord))
    return [
        {
            "id": r.id,
            "gpu_model": r.gpu_model,
            "tdp_watts": r.tdp_watts,
            "efficiency_factor": r.efficiency_factor,
            "calibration_sample_count": r.calibration_sample_count,
            "last_calibrated_at": r.last_calibrated_at.isoformat() if r.last_calibrated_at else None,
            "calibration_provenance": r.calibration_provenance,
        }
        for r in records
    ]


@router.post("/energy/gpu-profiles/calibrate")
async def energy_gpu_calibrate(
    session: SessionDep,
    container: ContainerDep,
    payload: dict,
) -> dict:
    """Trigger GPU energy efficiency calibration from a local measurement.

    Request body:
      - model_id: model that was measured
      - measured_energy_micro_wh_per_1k: measured energy
      - measured_tokens_per_second: measured throughput
      - gpu_model: GPU model (optional, auto-detected)
    """
    from greenflex.gpu_calibrator import GpuCalibrator
    from greenflex.models import ModelRecord

    model_id = payload.get("model_id")
    measured_energy = payload.get("measured_energy_micro_wh_per_1k")
    measured_tps = payload.get("measured_tokens_per_second")

    if not model_id or not measured_energy or not measured_tps:
        return {"error": "model_id, measured_energy_micro_wh_per_1k, measured_tokens_per_second required"}

    model = await session.get(ModelRecord, model_id)
    if model is None:
        return {"error": f"Model {model_id} not found"}

    result = container.gpu_calibrator.calibrate_from_measurement(
        model=model,
        measured_energy_micro_wh_per_1k=int(measured_energy),
        measured_tokens_per_second=int(measured_tps),
    )

    # Promote model to L1
    container.gpu_calibrator.promote_model_to_l1(
        model,
        measured_energy_micro_wh_per_1k=int(measured_energy),
        measured_tokens_per_second=int(measured_tps),
    )

    # Save profile
    profile = container.gpu_calibrator.build_profile_record(
        gpu_model=result.gpu_model,
        efficiency_factor=result.new_efficiency_factor,
        sample_count=result.sample_count,
    )
    session.add(profile)
    await session.commit()

    return {
        "gpu_model": result.gpu_model,
        "old_efficiency_factor": result.old_efficiency_factor,
        "new_efficiency_factor": result.new_efficiency_factor,
        "sample_count": result.sample_count,
        "correction_ratio": result.correction_ratio,
        "confidence_bps": result.confidence_bps,
        "model_promoted_to_l1": True,
    }


# ---------------------------------------------------------------------------
# RL Router endpoints (v2)
# ---------------------------------------------------------------------------

@router.get("/rl/status")
async def rl_status(container: ContainerDep) -> dict:
    """Get RL router status and configuration."""
    if container.rl_router is None:
        return {"enabled": False, "message": "RL router is disabled"}
    stats = container.rl_router.get_stats()
    return {"enabled": True, **stats}


@router.post("/rl/mode")
async def rl_set_mode(mode: str, container: ContainerDep) -> dict:
    """Set RL router operating mode.

    Modes: disabled, shadow, advisory, autonomous
    Autonomous requires a deployed, evaluated policy.
    """
    if container.rl_router is None:
        return {"enabled": False, "message": "RL router is disabled"}
    from greenflex.rl_router import RLMode
    try:
        rl_mode = RLMode(mode)
        container.rl_router.set_mode(rl_mode)
        return {"status": "ok", "mode": mode}
    except ValueError as e:
        return {"status": "error", "message": str(e)}


@router.post("/rl/train")
async def rl_train(container: ContainerDep) -> dict:
    """Trigger RL policy training step."""
    if container.rl_router is None:
        return {"enabled": False, "message": "RL router is disabled"}
    result = container.rl_router.train_step()
    return result


@router.get("/rl/decisions")
async def rl_decisions(container: ContainerDep, limit: int = 50) -> list[dict]:
    """Get recent RL routing decisions."""
    if container.rl_router is None:
        return []
    return container.rl_router.decision_log[-limit:]


# ---------------------------------------------------------------------------
# C2PA endpoints (v2)
# ---------------------------------------------------------------------------

@router.get("/passports/{passport_id}/c2pa")
async def passport_c2pa(passport_id: str, session: SessionDep) -> dict:
    """Get C2PA-compatible manifest for a passport."""
    from greenflex.c2pa import TokenPassportC2PA
    from greenflex.models import PassportRecord

    result = await session.execute(
        select(PassportRecord).where(PassportRecord.id == passport_id)
    )
    passport = result.scalar_one_or_none()
    if passport is None:
        raise HTTPException(status_code=404, detail="Passport not found")

    # Build C2PA passport from record
    c2pa_passport = TokenPassportC2PA(
        passport_id=passport.id,
        model_id=passport.model_id or "",
        input_tokens=passport.input_tokens or 0,
        output_tokens=passport.output_tokens or 0,
        total_tokens=(passport.input_tokens or 0) + (passport.output_tokens or 0),
        energy_micro_wh=passport.energy_micro_wh or 0,
        carbon_micro_g=passport.carbon_micro_g or 0,
        order_id=passport.order_id,
        created_at=passport.created_at.isoformat() if passport.created_at else "",
    )
    c2pa_passport.generate_c2pa_manifest()
    return c2pa_passport.to_dict()


@router.post("/c2pa/verify")
async def c2pa_verify(payload: dict, container: ContainerDep) -> dict:
    """Verify a C2PA manifest.

    Request body: JSON containing a passport with c2pa_manifest field.
    """
    if container.c2pa_verifier is None:
        return {"valid": False, "error": "C2PA verifier not available"}
    return container.c2pa_verifier.verify_dict(payload)


# ---------------------------------------------------------------------------
# AI Act Compliance endpoints (v2)
# ---------------------------------------------------------------------------

@router.get("/compliance/ai-act")
async def ai_act_compliance(container: ContainerDep) -> dict:
    """Generate EU AI Act compliance report for GreenFlex platform."""
    from greenflex.ai_act_compliance import generate_compliance_report
    report = generate_compliance_report(
        platform_info=container.compliance_info,
    )
    return report.to_dict()


@router.get("/compliance/ai-act/markdown")
async def ai_act_compliance_markdown(container: ContainerDep) -> Response:
    """Generate EU AI Act compliance report as Markdown."""
    from greenflex.ai_act_compliance import generate_compliance_report
    report = generate_compliance_report(
        platform_info=container.compliance_info,
    )
    return Response(
        content=report.to_markdown(),
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=ai-act-compliance-report.md"},
    )


@router.get("/compliance/ai-act/{model_id}")
async def ai_act_compliance_model(model_id: str, session: SessionDep, container: ContainerDep) -> dict:
    """Generate EU AI Act compliance report for a specific model."""
    from greenflex.ai_act_compliance import ModelComplianceInfo, generate_compliance_report
    from greenflex.models import ModelRecord

    result = await session.execute(
        select(ModelRecord).where(ModelRecord.id == model_id)
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")

    model_info = ModelComplianceInfo(
        model_id=model.id,
        model_name=model.display_name or model.id,
        parameter_count_b=model.parameter_count_b,
        intended_use="general purpose text generation",
        energy_provenance_tier=model.energy_data_provenance or "insufficient_data",
        typical_energy_wh_per_1k_output=(model.estimated_energy_micro_wh_per_1k_output or 0) / 1_000_000,
    )
    report = generate_compliance_report(
        model_info=model_info,
        platform_info=container.compliance_info,
    )
    return report.to_dict()
