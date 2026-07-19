from __future__ import annotations

from dataclasses import dataclass

from greenflex.policies import LowestImpactSlotPolicy, TieredPricingPolicy
from greenflex.ports import InferenceProvider, TelemetryProvider
from greenflex.providers import UnavailableInferenceProvider, UnavailableTelemetryProvider
from greenflex.signals import SyntheticEnergySignalProvider


@dataclass(slots=True)
class ServiceContainer:
    inference: InferenceProvider
    telemetry: TelemetryProvider
    signals: SyntheticEnergySignalProvider
    pricing: TieredPricingPolicy
    scheduling: LowestImpactSlotPolicy


def build_container() -> ServiceContainer:
    signals = SyntheticEnergySignalProvider()
    return ServiceContainer(
        inference=UnavailableInferenceProvider(),
        telemetry=UnavailableTelemetryProvider(),
        signals=signals,
        pricing=TieredPricingPolicy(),
        scheduling=LowestImpactSlotPolicy(signals),
    )
