from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

from greenflex.adapters import NvidiaSmiTelemetryProvider, OllamaInferenceProvider  # noqa: F401
from greenflex.adapters_nvml import NVMLTelemetryProvider
from greenflex.agent_integration import AgentAdvisor, RuleBasedAgentAdvisor
from greenflex.cloud_provider import CloudAPIProvider
from greenflex.config import get_settings
from greenflex.hybrid_provider import HybridInferenceProvider
from greenflex.policies import LowestImpactSlotPolicy, TieredPricingPolicy
from greenflex.ports import InferenceProvider, TelemetryProvider
from greenflex.recommendation import GreenRouterRuleV1
from greenflex.runtime_settings import RuntimeSettingsStore
from greenflex.signals import SyntheticEnergySignalProvider
from greenflex.simulated_provider import SimulatedInferenceProvider
from greenflex.task_classifier import TaskClassifier


@dataclass(slots=True)
class ServiceContainer:
    inference: InferenceProvider
    telemetry: TelemetryProvider
    signals: SyntheticEnergySignalProvider
    pricing: TieredPricingPolicy
    scheduling: LowestImpactSlotPolicy
    recommendation: GreenRouterRuleV1
    task_classifier: TaskClassifier | None = None
    agent_advisor: AgentAdvisor | None = None
    runtime_settings: RuntimeSettingsStore | None = None
    admin_token: str | None = None


def _load_or_create_admin_token(artifact_dir: Path) -> str:
    """Load admin token from file or generate a new one.

    The token protects settings write endpoints. It is generated on first
    run and stored in the artifact directory with restrictive permissions.
    """
    settings = get_settings()
    if settings.admin_token:
        return settings.admin_token

    token_path = artifact_dir / "admin_token.txt"
    if token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()
        if token:
            return token

    token = secrets.token_urlsafe(32)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token, encoding="utf-8")
    try:
        if hasattr(token_path, "chmod"):
            token_path.chmod(0o600)
    except OSError:
        pass
    return token


def build_container() -> ServiceContainer:
    settings = get_settings()
    signals = SyntheticEnergySignalProvider(region=settings.grid_region)
    telemetry: TelemetryProvider
    if settings.nvml_enabled:
        nvml = NVMLTelemetryProvider(interval_ms=settings.telemetry_interval_ms)
        telemetry = (
            nvml
            if nvml.available
            else NvidiaSmiTelemetryProvider(
                interval_ms=settings.telemetry_interval_ms,
            )
        )
    else:
        telemetry = NvidiaSmiTelemetryProvider(interval_ms=settings.telemetry_interval_ms)

    # Runtime settings store (persists cloud API keys to JSON)
    artifact_dir = Path(settings.artifact_dir)
    persist_path = artifact_dir / "runtime_settings.json"
    runtime_settings = RuntimeSettingsStore(persist_path=persist_path)

    # Admin token for settings write API
    admin_token = _load_or_create_admin_token(artifact_dir)

    # Cloud API provider reads keys dynamically from runtime settings
    cloud = CloudAPIProvider(
        runtime_settings=runtime_settings,
        timeout_seconds=settings.cloud_api_timeout_seconds,
    )

    # Hybrid: cloud APIs when configured, simulated fallback otherwise
    inference: InferenceProvider = HybridInferenceProvider(
        cloud=cloud,
        simulated=SimulatedInferenceProvider(
            latency_factor=1.0,
            enable_random_variation=True,
        ),
        fallback_to_simulated=True,
    )

    # Task classifier (rule-based MVP; Qwen2.5 model reserved for future)
    task_classifier = TaskClassifier(
        use_qwen25_model=False,
        qwen25_model_id="qwen2.5-1.5b-q4",
    )

    # External agent advisor (rule-based MVP; GreenConcierge reserved for future)
    agent_advisor: AgentAdvisor = RuleBasedAgentAdvisor(classifier=task_classifier)

    return ServiceContainer(
        inference=inference,
        telemetry=telemetry,
        signals=signals,
        pricing=TieredPricingPolicy(),
        scheduling=LowestImpactSlotPolicy(signals),
        recommendation=GreenRouterRuleV1(shadow_mode=True),
        task_classifier=task_classifier,
        agent_advisor=agent_advisor,
        runtime_settings=runtime_settings,
        admin_token=admin_token,
    )
