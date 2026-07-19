from __future__ import annotations

from collections.abc import AsyncGenerator

from greenflex.domain import DomainError
from greenflex.ports import GenerationRequest, GenerationResult, PowerSample


class UnavailableInferenceProvider:
    async def available_models(self) -> dict[str, str]:
        return {}

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        del request
        raise DomainError("inference_unavailable", "本地模型运行时尚未连接。", 503)


class UnavailableTelemetryProvider:
    source = "telemetry-unavailable"

    async def idle_power_mw(self, duration_seconds: float = 3.0) -> int | None:
        del duration_seconds
        return None

    async def samples(self) -> AsyncGenerator[PowerSample]:
        if False:
            yield PowerSample  # pragma: no cover
