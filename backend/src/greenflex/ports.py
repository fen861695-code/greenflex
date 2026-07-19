from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from greenflex.domain import EnergySignal, ExecutionMode, ScheduleSlot


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
