from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from greenflex.domain import (
    EnergySignal,
    ExecutionMode,
    QualityRequirement,
    QualityRiskLevel,
    RecommendationMode,
    ScheduleSlot,
    TaskType,
)


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    model_name: str
    prompt: str
    system_prompt: str | None
    max_output_tokens: int
    temperature: float = 0.2


@dataclass(frozen=True, slots=True)
class GenerationResult:
    output: str
    prompt_tokens: int
    output_tokens: int
    duration_us: int


@dataclass(frozen=True, slots=True)
class PowerSample:
    captured_at: datetime
    power_mw: int
    utilization_bps: int
    memory_used_mb: int


class InferenceProvider(Protocol):
    async def available_models(self) -> dict[str, str]: ...

    async def generate(self, request: GenerationRequest) -> GenerationResult: ...


class TelemetryProvider(Protocol):
    source: str

    async def idle_power_mw(self, duration_seconds: float = 3.0) -> int | None: ...

    def samples(self) -> AsyncGenerator[PowerSample]: ...


class EnergySignalProvider(Protocol):
    def signal_at(self, instant: datetime) -> EnergySignal: ...

    def signals_between(self, start: datetime, end: datetime) -> Sequence[EnergySignal]: ...


class SchedulingPolicy(Protocol):
    def choose_slot(
        self,
        *,
        mode: ExecutionMode,
        now: datetime,
        runtime_seconds: int,
        deadline: datetime | None,
    ) -> ScheduleSlot: ...


class PricingPolicy(Protocol):
    def discount_bps(self, mode: ExecutionMode, flexibility_seconds: int) -> int: ...


class BillingPolicy(Protocol):
    def settle_micro_rmb(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        input_rate: int,
        output_rate: int,
        discount_bps: int,
    ) -> int: ...


class PassportIssuer(Protocol):
    async def issue(self, order_id: str) -> str: ...


@dataclass(frozen=True, slots=True)
class RecommendationInput:
    """Input to the recommendation policy."""

    mode: RecommendationMode
    task_type: TaskType
    estimated_input_tokens: int
    estimated_output_tokens: int
    item_count: int
    quality_requirement: QualityRequirement
    budget_micro_rmb: int | None = None
    deadline: datetime | None = None
    execution_mode: ExecutionMode = ExecutionMode.IMMEDIATE
    candidate_model_ids: frozenset[str] | None = None
    prompt_preview: str | None = None  # not stored, used for feature extraction only


@dataclass(frozen=True, slots=True)
class ModelScore:
    """Scored candidate model."""

    model_id: str
    tier: str
    quality_risk: QualityRiskLevel
    estimated_price_micro_rmb: int
    estimated_energy_micro_wh: int
    estimated_carbon_micro_g: int
    estimated_execution_seconds: int
    estimated_wait_seconds: int
    composite_score: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    # --- Energy data provenance (L1-L3 + insufficient only) ---
    energy_provenance_tier: str = "insufficient_data"
    energy_confidence_bps: int = 0
    energy_source_description: str = "No verified benchmark data"


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    """Output of the recommendation policy."""

    recommended_model_id: str
    recommended_tier: str
    recommended_execution_mode: ExecutionMode
    quality_risk: QualityRiskLevel
    confidence_bps: int
    estimated_price_micro_rmb: int
    estimated_energy_micro_wh: int
    estimated_carbon_micro_g: int
    estimated_execution_seconds: int
    estimated_wait_seconds: int
    reason_codes: tuple[str, ...]
    reason_summary: str
    alternatives: tuple[ModelScore, ...]
    policy_version: str
    profile_version: str
    shadow_mode: bool = True


class RecommendationPolicy(Protocol):
    """Multi-objective model recommendation policy."""

    policy_version: str

    def recommend(
        self,
        *,
        request: RecommendationInput,
        available_models: Sequence[ModelScore],  # actually model catalog entries
        now: datetime,
    ) -> RecommendationResult: ...
