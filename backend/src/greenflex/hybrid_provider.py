"""Hybrid inference provider that routes to cloud or simulated backends.

- Cloud models (runtime_name starting with ``cloud:``) are routed to
  CloudAPIProvider when the corresponding API key is configured.
- All other models fall back to SimulatedInferenceProvider.
- If a cloud API call fails, it optionally falls back to simulation.
"""

from __future__ import annotations

from greenflex.cloud_provider import CloudAPIProvider
from greenflex.domain import DomainError
from greenflex.ports import GenerationRequest, GenerationResult, InferenceProvider
from greenflex.simulated_provider import SimulatedInferenceProvider


class HybridInferenceProvider:
    """Routes inference to cloud APIs when configured, otherwise simulates.

    Args:
        cloud: CloudAPIProvider instance with configured keys.
        simulated: SimulatedInferenceProvider fallback.
        fallback_to_simulated: If True, cloud errors fall back to simulation.
    """

    source = "hybrid"

    def __init__(
        self,
        *,
        cloud: CloudAPIProvider,
        simulated: SimulatedInferenceProvider | None = None,
        fallback_to_simulated: bool = True,
    ) -> None:
        self._cloud = cloud
        self._simulated = simulated or SimulatedInferenceProvider(
            latency_factor=1.0,
            enable_random_variation=True,
        )
        self._fallback = fallback_to_simulated

    async def available_models(self) -> dict[str, str]:
        """Return configured cloud providers; simulated handles all local models."""
        cloud_available = await self._cloud.available_models()
        # Return cloud:provider keys so services can match runtime_name prefixes
        return {f"cloud:{provider}": "configured" for provider in cloud_available}

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Route to cloud for cloud models, simulate for everything else."""
        if request.model_name.startswith("cloud:"):
            try:
                return await self._cloud.generate(request)
            except DomainError as exc:
                # If cloud is not configured, fall back to simulation
                if exc.code == "cloud_api_not_configured" and self._fallback:
                    return await self._simulated.generate(request)
                raise
        return await self._simulated.generate(request)


# Static structural check
_provider: type[InferenceProvider] = HybridInferenceProvider
