from __future__ import annotations

from dataclasses import dataclass

from greenflex.adapters import NvidiaSmiTelemetryProvider, OllamaInferenceProvider
from greenflex.config import get_settings
from greenflex.policies import LowestImpactSlotPolicy, TieredPricingPolicy
from greenflex.ports import InferenceProvider, TelemetryProvider
from greenflex.signals import SyntheticEnergySignalProvider


@dataclass(slots=True)
class ServiceContainer:
    inference: InferenceProvider
    telemetry: TelemetryProvider
    signals: SyntheticEnergySignalProvider
    pricing: TieredPricingPolicy
    scheduling: LowestImpactSlotPolicy


def build_container() -> ServiceContainer:
    settings = get_settings()
    signals = SyntheticEnergySignalProvider()
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
    )
