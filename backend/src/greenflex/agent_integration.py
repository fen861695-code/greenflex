"""External agent integration for task analysis and model recommendation.

Provides an AgentAdvisor protocol with a rule-based MVP implementation and
a GreenConcierge placeholder for future LLM-driven agent assistance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from greenflex.domain import QualityRequirement, TaskType
from greenflex.task_classifier import (
    CLASSIFIER_VERSION,
    ClassifierComplexity,
    TaskClassification,
    TaskClassifier,
)


class AgentProviderType(StrEnum):
    """Supported external agent providers."""

    RULE_BASED = "rule-based"
    GREEN_CONCIERGE = "green-concierge"
    CUSTOM_LLM = "custom-llm"


@dataclass(frozen=True, slots=True)
class AgentTaskAnalysis:
    """Result of agent task analysis."""

    task_type: TaskType
    complexity: ClassifierComplexity
    estimated_input_tokens: int
    estimated_output_tokens: int
    recommended_tier: str
    confidence_bps: int
    reasoning: str
    suggested_models: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    agent_provider: str = "rule-based"
    agent_version: str = CLASSIFIER_VERSION


@dataclass(frozen=True, slots=True)
class AgentModelRecommendation:
    """Result of agent model recommendation."""

    primary_model_id: str
    primary_reason: str
    alternative_model_ids: list[str] = field(default_factory=list)
    estimated_price_micro_rmb: int = 0
    estimated_energy_micro_wh: int = 0
    estimated_carbon_micro_g: int = 0
    confidence_bps: int = 5000
    agent_provider: str = "rule-based"


class AgentAdvisor(Protocol):
    """Protocol for external agent advisors."""

    def analyze_task(
        self,
        prompt: str,
        *,
        item_count: int,
        output_length: str,
        quality_requirement: QualityRequirement,
        context: dict[str, Any] | None = None,
    ) -> AgentTaskAnalysis: ...

    def recommend_model(
        self,
        analysis: AgentTaskAnalysis,
        available_models: Sequence[Any],
        *,
        budget_micro_rmb: int | None = None,
        deadline: datetime | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentModelRecommendation: ...


class RuleBasedAgentAdvisor:
    """MVP agent advisor that uses the rule-based TaskClassifier.

    For model recommendation, it filters models by recommended tier and
    selects the one with the highest throughput (tokens/second).  If no
    model exists in the recommended tier, it falls back to adjacent tiers.
    """

    def __init__(self, *, classifier: TaskClassifier | None = None) -> None:
        self._classifier = classifier or TaskClassifier()

    def analyze_task(
        self,
        prompt: str,
        *,
        item_count: int = 1,
        output_length: str = "medium",
        quality_requirement: QualityRequirement = QualityRequirement.STANDARD,
        context: dict[str, Any] | None = None,
    ) -> AgentTaskAnalysis:
        del context  # MVP: context not used
        classification: TaskClassification = self._classifier.classify(
            prompt,
            item_count=item_count,
            output_length=output_length,
            quality_requirement=quality_requirement,
        )

        reasoning = self._build_reasoning(classification)
        risk_notes = self._build_risk_notes(classification)

        return AgentTaskAnalysis(
            task_type=classification.task_type,
            complexity=classification.complexity,
            estimated_input_tokens=classification.estimated_input_tokens,
            estimated_output_tokens=classification.estimated_output_tokens,
            recommended_tier=classification.recommended_tier,
            confidence_bps=classification.confidence_bps,
            reasoning=reasoning,
            suggested_models=[],
            risk_notes=risk_notes,
            agent_provider="rule-based",
            agent_version=CLASSIFIER_VERSION,
        )

    def recommend_model(
        self,
        analysis: AgentTaskAnalysis,
        available_models: Sequence[Any],
        *,
        budget_micro_rmb: int | None = None,
        deadline: datetime | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentModelRecommendation:
        del deadline, context  # MVP: not used

        # Filter enabled models only
        enabled = [m for m in available_models if getattr(m, "enabled", True)]
        if not enabled:
            enabled = list(available_models)

        # Try recommended tier first, then fall back
        tier_order = [
            analysis.recommended_tier,
            self._tier_up(analysis.recommended_tier),
            self._tier_down(analysis.recommended_tier),
        ]

        selected = None
        for tier in tier_order:
            candidates = [m for m in enabled if getattr(m, "tier", "") == tier]
            if budget_micro_rmb is not None:
                candidates = [
                    m
                    for m in candidates
                    if getattr(m, "output_rate_micro_rmb_per_million", 0) <= budget_micro_rmb
                ]
            if candidates:
                # Select highest throughput
                selected = max(
                    candidates,
                    key=lambda m: getattr(m, "estimated_tokens_per_second", 0),
                )
                break

        if selected is None:
            # Last resort: pick any model with highest throughput
            selected = max(
                enabled,
                key=lambda m: getattr(m, "estimated_tokens_per_second", 0),
            )

        alternatives = [
            m.id for m in enabled if m.id != selected.id and getattr(m, "tier", "") == selected.tier
        ][:3]

        # Estimate cost/energy
        output_tokens = analysis.estimated_output_tokens
        price = (
            getattr(selected, "output_rate_micro_rmb_per_million", 0) * output_tokens // 1_000_000
        )
        energy = (
            getattr(selected, "estimated_energy_micro_wh_per_1k_output", 0) * output_tokens // 1000
        )

        return AgentModelRecommendation(
            primary_model_id=selected.id,
            primary_reason=(
                f"按{analysis.recommended_tier}档位筛选，选择吞吐量最高的模型 "
                f"({getattr(selected, 'estimated_tokens_per_second', 0)} tok/s)"
            ),
            alternative_model_ids=alternatives,
            estimated_price_micro_rmb=price,
            estimated_energy_micro_wh=energy,
            estimated_carbon_micro_g=0,
            confidence_bps=analysis.confidence_bps,
            agent_provider="rule-based",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tier_up(tier: str) -> str:
        order = ["economy", "balanced", "quality", "enterprise"]
        idx = order.index(tier) if tier in order else 1
        return order[min(idx + 1, len(order) - 1)]

    @staticmethod
    def _tier_down(tier: str) -> str:
        order = ["economy", "balanced", "quality", "enterprise"]
        idx = order.index(tier) if tier in order else 1
        return order[max(idx - 1, 0)]

    @staticmethod
    def _build_reasoning(classification: TaskClassification) -> str:
        parts = [
            f"任务类型: {classification.task_type.value}",
            f"复杂度: {classification.complexity.value}",
            f"推荐档位: {classification.recommended_tier}",
        ]
        if classification.requires_json:
            parts.append("需要结构化JSON输出")
        return "；".join(parts)

    @staticmethod
    def _build_risk_notes(classification: TaskClassification) -> list[str]:
        notes: list[str] = []
        if classification.task_type == TaskType.CODE:
            notes.append("代码任务建议使用quality及以上档位以降低出错风险")
        if classification.complexity == ClassifierComplexity.COMPLEX:
            notes.append("复杂任务可能需要更长推理时间和更高能耗")
        if classification.confidence_bps < 5000:
            notes.append("分类置信度较低，建议人工确认任务类型")
        return notes


class GreenConciergeAgentAdvisor:
    """GreenConcierge agent advisor — integrated in-process.

    The concierge is now embedded in GreenFlex (see ``greenflex.concierge``).
    For the recommendation pipeline, this advisor delegates to the
    :class:`TaskClassifier` for deterministic task analysis. When a cloud
    LLM is configured, the concierge chat interface provides richer
    LLM-driven analysis via function calling.
    """

    def __init__(
        self,
        *,
        concierge_api_url: str = "",
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        classifier: TaskClassifier | None = None,
    ) -> None:
        self._api_url = concierge_api_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._classifier = classifier or TaskClassifier()

    def analyze_task(
        self,
        prompt: str,
        *,
        item_count: int = 1,
        output_length: str = "medium",
        quality_requirement: QualityRequirement = QualityRequirement.STANDARD,
        context: dict[str, Any] | None = None,
    ) -> AgentTaskAnalysis:
        """Analyze task using the integrated classifier."""
        cls = self._classifier.classify(
            prompt,
            item_count=item_count,
            output_length=output_length,  # type: ignore[arg-type]
            quality_requirement=quality_requirement,
        )
        return AgentTaskAnalysis(
            task_type=cls.task_type.value,
            complexity=cls.complexity.value,
            estimated_input_tokens=cls.estimated_input_tokens,
            estimated_output_tokens=cls.estimated_output_tokens,
            recommended_tier=cls.recommended_tier.value,
            confidence_bps=cls.confidence_bps,
            reasoning=f"GreenConcierge integrated classifier v{cls.classifier_version}",
            suggested_models=[],
            risk_notes=[],
            agent_provider="green-concierge",
            agent_version="1.0.0",
        )

    def recommend_model(
        self,
        analysis: AgentTaskAnalysis,
        available_models: Sequence[Any],
        *,
        budget_micro_rmb: int | None = None,
        deadline: datetime | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentModelRecommendation:
        """Recommend model using rule-based selection (same as RuleBasedAgentAdvisor)."""
        rule_advisor = RuleBasedAgentAdvisor(classifier=self._classifier)
        return rule_advisor.recommend_model(
            analysis,
            available_models,
            budget_micro_rmb=budget_micro_rmb,
            deadline=deadline,
            context=context,
        )


def create_agent_advisor(
    provider_type: AgentProviderType,
    **kwargs: Any,
) -> AgentAdvisor:
    """Factory function to create an AgentAdvisor by provider type.

    Args:
        provider_type: Which agent provider to use.
        **kwargs: Provider-specific arguments (e.g. concierge_api_url, api_key).

    Returns:
        An AgentAdvisor instance.
    """
    if provider_type == AgentProviderType.RULE_BASED:
        classifier = kwargs.get("classifier")
        return RuleBasedAgentAdvisor(classifier=classifier)
    if provider_type == AgentProviderType.GREEN_CONCIERGE:
        return GreenConciergeAgentAdvisor(
            concierge_api_url=kwargs.get("concierge_api_url", "http://localhost:8001"),
            api_key=kwargs.get("api_key"),
            timeout_seconds=kwargs.get("timeout_seconds", 30.0),
        )
    # CUSTOM_LLM and unknown types default to rule-based
    return RuleBasedAgentAdvisor()
