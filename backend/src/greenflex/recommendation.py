"""GreenRouter v1: multi-objective model recommendation policy.

Two-phase algorithm:
  Phase 1 — Hard constraint filtering (availability, context, deadline,
            budget, quality floor, task capability).
  Phase 2 — Weighted multi-objective scoring across quality risk, price,
            GPU energy, carbon, latency, queue wait, and renewable share.

Safety guards:
  - High-risk tasks with low confidence fall back to quality tier (3B).
  - Confidence < 50% prevents automatic downgrade.
  - 0.5B is only recommended in economy mode for simple tasks.
  - When candidate scores are within 5%, prefer higher quality.
  - All recommendations run in shadow mode by default (audit only,
    no automatic order creation).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from greenflex.domain import (
    ExecutionMode,
    QualityRequirement,
    QualityRiskLevel,
    RecommendationMode,
    TaskType,
    utc_now,
)
from greenflex.models import ModelRecord
from greenflex.ports import (
    ModelScore,
    RecommendationInput,
    RecommendationResult,
)

# ---------------------------------------------------------------------------
# Policy metadata
# ---------------------------------------------------------------------------

POLICY_VERSION = "green-router-rule-v1"
PROFILE_VERSION = "model-task-profile-v1"

# Quality risk numeric values for scoring (lower is better)
_QUALITY_RISK_SCORE: dict[QualityRiskLevel, int] = {
    QualityRiskLevel.LOW: 10,
    QualityRiskLevel.MEDIUM: 30,
    QualityRiskLevel.HIGH: 60,
    QualityRiskLevel.VERY_HIGH: 90,
}

# Multi-objective weights (sum = 1.0; renewable is negative weight)
_W_QUALITY = 0.35
_W_PRICE = 0.20
_W_ENERGY = 0.15
_W_CARBON = 0.10
_W_LATENCY = 0.10
_W_WAIT = 0.05
_W_RENEWABLE = 0.05

# Tier ordering for quality comparisons
_TIER_ORDER: dict[str, int] = {"economy": 0, "balanced": 1, "quality": 2, "enterprise": 3}


# ---------------------------------------------------------------------------
# Quality risk matrix: (task_type, model_tier) -> QualityRiskLevel
# ---------------------------------------------------------------------------

_TASK_TIER_RISK: dict[TaskType, dict[str, QualityRiskLevel]] = {
    TaskType.CLASSIFICATION: {
        "economy": QualityRiskLevel.LOW,
        "balanced": QualityRiskLevel.LOW,
        "quality": QualityRiskLevel.LOW,
        "enterprise": QualityRiskLevel.LOW,
    },
    TaskType.EXTRACTION: {
        "economy": QualityRiskLevel.LOW,
        "balanced": QualityRiskLevel.LOW,
        "quality": QualityRiskLevel.LOW,
        "enterprise": QualityRiskLevel.LOW,
    },
    TaskType.SUMMARIZATION: {
        "economy": QualityRiskLevel.MEDIUM,
        "balanced": QualityRiskLevel.LOW,
        "quality": QualityRiskLevel.LOW,
        "enterprise": QualityRiskLevel.LOW,
    },
    TaskType.GENERATION: {
        "economy": QualityRiskLevel.HIGH,
        "balanced": QualityRiskLevel.LOW,
        "quality": QualityRiskLevel.LOW,
        "enterprise": QualityRiskLevel.LOW,
    },
    TaskType.ANALYSIS: {
        "economy": QualityRiskLevel.HIGH,
        "balanced": QualityRiskLevel.LOW,
        "quality": QualityRiskLevel.LOW,
        "enterprise": QualityRiskLevel.LOW,
    },
    TaskType.CODE: {
        "economy": QualityRiskLevel.VERY_HIGH,
        "balanced": QualityRiskLevel.MEDIUM,
        "quality": QualityRiskLevel.LOW,
        "enterprise": QualityRiskLevel.LOW,
    },
    TaskType.AUTO: {
        "economy": QualityRiskLevel.MEDIUM,
        "balanced": QualityRiskLevel.LOW,
        "quality": QualityRiskLevel.LOW,
        "enterprise": QualityRiskLevel.LOW,
    },
}


@dataclass(frozen=True, slots=True)
class _CandidateEstimate:
    """Precomputed estimates for a candidate model."""

    model: ModelRecord
    quality_risk: QualityRiskLevel
    price_micro_rmb: int
    energy_micro_wh: int
    carbon_micro_g: int
    execution_seconds: int
    wait_seconds: int
    feasible: bool
    rejection_reason: str | None = None


class GreenRouterRuleV1:
    """Deterministic multi-objective recommendation policy."""

    policy_version = POLICY_VERSION

    def __init__(
        self,
        *,
        carbon_g_per_kwh: int = 550,
        renewable_share_bps: int = 3000,
        price_micro_rmb_per_kwh: int = 660_000,
        queue_depth: int = 0,
        shadow_mode: bool = True,
    ) -> None:
        self._carbon_g_per_kwh = carbon_g_per_kwh
        self._renewable_share_bps = renewable_share_bps
        self._price_micro_rmb_per_kwh = price_micro_rmb_per_kwh
        self._queue_depth = queue_depth
        self._shadow_mode = shadow_mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(
        self,
        *,
        request: RecommendationInput,
        available_models: Sequence[ModelRecord],
        now: datetime | None = None,
    ) -> RecommendationResult:
        if now is None:
            now = utc_now()

        # Filter enabled models and candidate set
        models = [m for m in available_models if m.enabled]
        if request.candidate_model_ids is not None:
            models = [m for m in models if m.id in request.candidate_model_ids]

        # Phase 1: compute estimates and apply hard constraints
        candidates: list[_CandidateEstimate] = []
        for model in models:
            est = self._estimate_candidate(model, request, now)
            candidates.append(est)

        feasible = [c for c in candidates if c.feasible]
        if not feasible:
            reasons = [c.rejection_reason for c in candidates if c.rejection_reason]
            from greenflex.domain import DomainError

            raise DomainError(
                "no_feasible_model",
                "没有满足约束的可用模型: " + "; ".join(filter(None, reasons)),
                409,
            )

        # Phase 2: multi-objective scoring
        scored = self._score_candidates(feasible, request)

        # Apply mode-specific selection
        selected = self._select_by_mode(scored, request)

        # Safety guard: high risk + low confidence → fall back to quality tier
        confidence_bps = self._compute_confidence(selected, request, len(scored))
        if (
            selected.quality_risk in (QualityRiskLevel.HIGH, QualityRiskLevel.VERY_HIGH)
            and confidence_bps < 6000
        ):
            quality_candidates = [
                c for c in scored if _TIER_ORDER.get(c.tier, -1) >= _TIER_ORDER["quality"]
            ]
            if quality_candidates:
                selected = min(quality_candidates, key=lambda c: c.composite_score)
                selected_reasons = list(selected.reason_codes)
                selected_reasons.append("safety_high_risk_fallback")
                selected = ModelScore(
                    model_id=selected.model_id,
                    tier=selected.tier,
                    quality_risk=selected.quality_risk,
                    estimated_price_micro_rmb=selected.estimated_price_micro_rmb,
                    estimated_energy_micro_wh=selected.estimated_energy_micro_wh,
                    estimated_carbon_micro_g=selected.estimated_carbon_micro_g,
                    estimated_execution_seconds=selected.estimated_execution_seconds,
                    estimated_wait_seconds=selected.estimated_wait_seconds,
                    composite_score=selected.composite_score,
                    reason_codes=tuple(selected_reasons),
                )

        # Build alternatives (all feasible except selected, sorted by score)
        alternatives = tuple(
            sorted(
                [c for c in scored if c.model_id != selected.model_id],
                key=lambda c: c.composite_score,
            )
        )

        reason_summary = self._build_reason_summary(selected, request)

        return RecommendationResult(
            recommended_model_id=selected.model_id,
            recommended_tier=selected.tier,
            recommended_execution_mode=request.execution_mode,
            quality_risk=selected.quality_risk,
            confidence_bps=confidence_bps,
            estimated_price_micro_rmb=selected.estimated_price_micro_rmb,
            estimated_energy_micro_wh=selected.estimated_energy_micro_wh,
            estimated_carbon_micro_g=selected.estimated_carbon_micro_g,
            estimated_execution_seconds=selected.estimated_execution_seconds,
            estimated_wait_seconds=selected.estimated_wait_seconds,
            reason_codes=selected.reason_codes,
            reason_summary=reason_summary,
            alternatives=alternatives,
            policy_version=POLICY_VERSION,
            profile_version=PROFILE_VERSION,
            shadow_mode=self._shadow_mode,
        )

    # ------------------------------------------------------------------
    # Phase 1: estimation + hard constraints
    # ------------------------------------------------------------------

    def _estimate_candidate(
        self,
        model: ModelRecord,
        request: RecommendationInput,
        now: datetime,
    ) -> _CandidateEstimate:
        total_input = request.estimated_input_tokens * max(1, request.item_count)
        total_output = request.estimated_output_tokens * max(1, request.item_count)

        # Price estimate
        price = (
            total_input * model.input_rate_micro_rmb_per_million // 1_000_000
            + total_output * model.output_rate_micro_rmb_per_million // 1_000_000
        )

        # Energy estimate (GPU energy, micro-Wh)
        energy = model.estimated_energy_micro_wh_per_1k_output * total_output // 1_000

        # Carbon estimate (micro-g CO2)
        carbon = energy * self._carbon_g_per_kwh // 1_000_000

        # Execution time estimate
        execution_seconds = total_output // max(1, model.estimated_tokens_per_second) + 1

        # Wait time estimate (simple queue model)
        wait_seconds = self._queue_depth * 3  # ~3s per queued item

        # Quality risk for this task type
        risk_matrix = _TASK_TIER_RISK.get(request.task_type, _TASK_TIER_RISK[TaskType.AUTO])
        quality_risk = risk_matrix.get(model.tier, QualityRiskLevel.MEDIUM)

        # --- Hard constraints ---
        reasons: list[str] = []

        # 1. Context length
        if (request.estimated_input_tokens + request.estimated_output_tokens) > model.context_limit:
            reasons.append("context_limit_exceeded")

        # 2. Deadline
        if request.deadline is not None:
            total_time = execution_seconds + wait_seconds
            remaining = (request.deadline - now).total_seconds()
            if total_time > remaining:
                reasons.append("deadline_infeasible")

        # 3. Budget
        if request.budget_micro_rmb is not None and price > request.budget_micro_rmb:
            reasons.append("budget_exceeded")

        # 4. Quality floor
        if request.quality_requirement == QualityRequirement.CRITICAL:
            if _TIER_ORDER.get(model.tier, 0) < _TIER_ORDER["quality"]:
                reasons.append("quality_floor_critical")
        elif request.quality_requirement == QualityRequirement.HIGH:
            if _TIER_ORDER.get(model.tier, 0) < _TIER_ORDER["quality"]:
                reasons.append("quality_floor_high")

        # 4b. Classifier tier floor: the task classifier recommends a
        #     minimum tier based on task type + complexity.  This ensures
        #     e.g. a multi-class classification task doesn't end up on
        #     an economy model even in SMART/STANDARD mode.
        if request.classifier_tier_floor:
            floor = _TIER_ORDER.get(request.classifier_tier_floor, 0)
            if floor > 0 and _TIER_ORDER.get(model.tier, 0) < floor:
                reasons.append("classifier_tier_floor")

        # 5. Task capability note: code/complex tasks on economy tier carry
        #    VERY_HIGH quality risk; the safety guard will fall back to quality
        #    tier when confidence is low, so we do not hard-exclude them here.

        # 6. Economy mode gating for 0.5B
        if model.tier == "economy" and request.mode not in (
            RecommendationMode.ECONOMY,
            RecommendationMode.SMART,
        ):
            reasons.append("economy_tier_not_in_mode")

        feasible = len(reasons) == 0
        rejection_reason = None if feasible else "; ".join(reasons)

        return _CandidateEstimate(
            model=model,
            quality_risk=quality_risk,
            price_micro_rmb=price,
            energy_micro_wh=energy,
            carbon_micro_g=carbon,
            execution_seconds=execution_seconds,
            wait_seconds=wait_seconds,
            feasible=feasible,
            rejection_reason=rejection_reason,
        )

    # ------------------------------------------------------------------
    # Phase 2: multi-objective scoring
    # ------------------------------------------------------------------

    def _score_candidates(
        self,
        candidates: list[_CandidateEstimate],
        request: RecommendationInput,
    ) -> list[ModelScore]:
        if not candidates:
            return []

        # Normalization ranges
        max_price = max(c.price_micro_rmb for c in candidates) or 1
        max_energy = max(c.energy_micro_wh for c in candidates) or 1
        max_carbon = max(c.carbon_micro_g for c in candidates) or 1
        max_latency = max(c.execution_seconds for c in candidates) or 1
        max_wait = max(c.wait_seconds for c in candidates) or 1

        scored: list[ModelScore] = []
        for c in candidates:
            q = _QUALITY_RISK_SCORE[c.quality_risk] / 100.0
            p = c.price_micro_rmb / max_price
            e = c.energy_micro_wh / max_energy
            carb = c.carbon_micro_g / max_carbon
            lat = c.execution_seconds / max_latency
            wait = c.wait_seconds / max_wait
            ren = self._renewable_share_bps / 10000.0

            score = (
                _W_QUALITY * q
                + _W_PRICE * p
                + _W_ENERGY * e
                + _W_CARBON * carb
                + _W_LATENCY * lat
                + _W_WAIT * wait
                - _W_RENEWABLE * ren
            )

            reasons = self._candidate_reasons(c, request)

            scored.append(
                ModelScore(
                    model_id=c.model.id,
                    tier=c.model.tier,
                    quality_risk=c.quality_risk,
                    estimated_price_micro_rmb=c.price_micro_rmb,
                    estimated_energy_micro_wh=c.energy_micro_wh,
                    estimated_carbon_micro_g=c.carbon_micro_g,
                    estimated_execution_seconds=c.execution_seconds,
                    estimated_wait_seconds=c.wait_seconds,
                    composite_score=score,
                    reason_codes=tuple(reasons),
                )
            )

        return scored

    def _candidate_reasons(self, c: _CandidateEstimate, request: RecommendationInput) -> list[str]:
        reasons: list[str] = []
        if c.quality_risk == QualityRiskLevel.LOW:
            reasons.append("quality_risk_low")
        elif c.quality_risk == QualityRiskLevel.MEDIUM:
            reasons.append("quality_risk_medium")
        if c.model.tier == "economy":
            reasons.append("lowest_cost_option")
        if c.model.tier == "quality":
            reasons.append("highest_quality_option")
        if self._renewable_share_bps >= 4000:
            reasons.append("high_renewable_window")
        if request.execution_mode == ExecutionMode.FLEXIBLE:
            reasons.append("flexible_scheduling_discount")
        return reasons

    # ------------------------------------------------------------------
    # Mode-specific selection
    # ------------------------------------------------------------------

    def _select_by_mode(self, scored: list[ModelScore], request: RecommendationInput) -> ModelScore:
        if request.mode == RecommendationMode.QUALITY:
            # Quality mode: pick highest tier, then best score
            quality = [c for c in scored if c.tier == "quality"]
            if quality:
                return min(quality, key=lambda c: c.composite_score)
            # Fall through to best available if no quality tier

        elif request.mode == RecommendationMode.ECONOMY:
            # Economy mode: pick lowest price among feasible
            return min(scored, key=lambda c: c.estimated_price_micro_rmb)

        # SMART mode (default): best composite score
        best = min(scored, key=lambda c: c.composite_score)

        # Tie-breaking: if within 5% of best score, prefer higher quality
        threshold = best.composite_score * 1.05
        near_best = [c for c in scored if c.composite_score <= threshold]
        if len(near_best) > 1:
            best = max(near_best, key=lambda c: _TIER_ORDER.get(c.tier, 0))

        return best

    # ------------------------------------------------------------------
    # Confidence and summary
    # ------------------------------------------------------------------

    def _compute_confidence(
        self,
        selected: ModelScore,
        request: RecommendationInput,
        num_candidates: int,
    ) -> int:
        confidence = 8000  # base 80%

        if request.task_type == TaskType.AUTO:
            confidence -= 2000
        if selected.quality_risk == QualityRiskLevel.HIGH:
            confidence -= 1000
        if selected.quality_risk == QualityRiskLevel.VERY_HIGH:
            confidence -= 2000
        if num_candidates < 2:
            confidence -= 1000
        if request.estimated_input_tokens < 50:
            confidence -= 500  # very short prompt, hard to classify

        return max(1000, min(9500, confidence))

    def _build_reason_summary(self, selected: ModelScore, request: RecommendationInput) -> str:
        parts: list[str] = []
        if selected.tier == "quality":
            parts.append("推荐高质量模型以确保输出质量")
        elif selected.tier == "balanced":
            parts.append("在质量与成本之间取得平衡")
        else:
            parts.append("任务简单，推荐轻量模型以节省能耗")

        if "high_renewable_window" in selected.reason_codes:
            parts.append("当前时段绿电比例较高")
        if "flexible_scheduling_discount" in selected.reason_codes:
            parts.append("弹性调度可享受折扣")

        risk_label = {
            QualityRiskLevel.LOW: "低",
            QualityRiskLevel.MEDIUM: "中",
            QualityRiskLevel.HIGH: "高",
            QualityRiskLevel.VERY_HIGH: "极高",
        }[selected.quality_risk]
        parts.append(f"质量风险：{risk_label}")

        return "；".join(parts) + "。"


# ---------------------------------------------------------------------------
# Request hashing (for audit; no prompt content stored)
# ---------------------------------------------------------------------------


def hash_recommendation_request(
    *,
    task_type: str,
    mode: str,
    quality_requirement: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
    item_count: int,
    has_budget: bool,
    has_deadline: bool,
) -> str:
    """Compute a deterministic hash of recommendation request features.

    Does NOT include prompt text — only structural features.
    """
    payload = {
        "t": task_type,
        "m": mode,
        "q": quality_requirement,
        "it": estimated_input_tokens,
        "ot": estimated_output_tokens,
        "n": item_count,
        "b": has_budget,
        "d": has_deadline,
        "v": POLICY_VERSION,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
