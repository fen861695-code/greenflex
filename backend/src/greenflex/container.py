from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from greenflex.adapters import NvidiaSmiTelemetryProvider, OllamaInferenceProvider
from greenflex.ai_act_compliance import AIActComplianceReport, GreenFlexComplianceInfo
from greenflex.carbon_intensity_service import CarbonIntensityService
from greenflex.c2pa import C2PAVerifier, TokenPassportC2PA
from greenflex.config import get_settings
from greenflex.energy_estimator import EnergyEstimator, get_default_benchmarks
from greenflex.gpu_calibrator import GpuCalibrator
from greenflex.policies import LowestImpactSlotPolicy, TieredPricingPolicy
from greenflex.ports import InferenceProvider, TelemetryProvider
from greenflex.recommendation import GreenRouterRuleV1
from greenflex.rl_router import RLRouter, RLMode
from greenflex.signals import SyntheticEnergySignalProvider


@dataclass(slots=True)
class ServiceContainer:
    inference: InferenceProvider
    telemetry: TelemetryProvider
    signals: SyntheticEnergySignalProvider
    pricing: TieredPricingPolicy
    scheduling: LowestImpactSlotPolicy
    recommendation: GreenRouterRuleV1
    energy_estimator: EnergyEstimator
    gpu_calibrator: GpuCalibrator
    carbon_service: CarbonIntensityService | None = None
    # New v2 features
    rl_router: RLRouter | None = None
    c2pa_verifier: C2PAVerifier | None = None
    compliance_info: GreenFlexComplianceInfo | None = None


def build_container(session: Any | None = None) -> ServiceContainer:
    """Build service container with all dependencies wired.

    If a database session is provided, carbon intensity service is initialized
    with real-time API support. Otherwise, synthetic signals are used.
    """
    settings = get_settings()
    signals = SyntheticEnergySignalProvider()

    # Build energy estimator with default benchmark data
    benchmarks = get_default_benchmarks()
    benchmark_records = []
    for b in benchmarks:
        from greenflex.models import ModelEnergyBenchmarkRecord

        benchmark_records.append(ModelEnergyBenchmarkRecord(**b))

    estimator = EnergyEstimator(
        benchmarks=benchmark_records,
        gpu_profiles=[],
        local_gpu_model=settings.local_gpu_model,
    )

    calibrator = GpuCalibrator(
        estimator=estimator,
        gpu_profiles=[],
        local_gpu_model=settings.local_gpu_model,
    )

    # Carbon intensity service (requires DB session for caching)
    carbon_service = None
    if session is not None:
        provider_chain = [
            p.strip() for p in settings.carbon_provider_chain.split(",") if p.strip()
        ]
        carbon_service = CarbonIntensityService(
            session=session,
            electricity_maps_api_key=settings.electricity_maps_api_key,
            region_code=settings.carbon_intensity_region,
            electricity_maps_zone=settings.electricity_maps_zone,
            cache_ttl_minutes=settings.carbon_intensity_cache_ttl_minutes,
            provider_chain=provider_chain,
        )

    # RL Router (shadow mode by default)
    rl_router = None
    if settings.rl_router_enabled:
        rl_router = RLRouter(mode=RLMode.SHADOW)
        # Candidate models will be populated from catalog at runtime

    # C2PA verifier
    c2pa_verifier = C2PAVerifier(secret_key=settings.c2pa_secret_key)

    # AI Act compliance info
    compliance_info = GreenFlexComplianceInfo(
        version="0.1.0",
        deployment_type="local-first single-tenant",
        api_bound="127.0.0.1 only",
        c2pa_support=True,
        energy_reporting=True,
        carbon_reporting=True,
    )

    return ServiceContainer(
        inference=OllamaInferenceProvider(
            settings.ollama_base_url,
            connect_timeout_seconds=settings.ollama_connect_timeout_seconds,
            request_timeout_seconds=settings.ollama_request_timeout_seconds,
        ),
        telemetry=NvidiaSmiTelemetryProvider(interval_ms=settings.telemetry_interval_ms),
        signals=signals,
        pricing=TieredPricingPolicy(),
        scheduling=LowestImpactSlotPolicy(signals),
        recommendation=GreenRouterRuleV1(
            shadow_mode=True,
            energy_estimator=estimator if settings.energy_estimator_enabled else None,
        ),
        energy_estimator=estimator,
        gpu_calibrator=calibrator,
        carbon_service=carbon_service,
        rl_router=rl_router,
        c2pa_verifier=c2pa_verifier,
        compliance_info=compliance_info,
    )
