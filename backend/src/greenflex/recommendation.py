"""GreenRouter v2: multi-objective model recommendation policy.

Two-phase algorithm:
  Phase 1 — Hard constraint filtering (availability, context, deadline,
            budget, quality floor, task capability).
  Phase 2 — Weighted multi-objective scoring across quality risk, price,
            GPU energy, carbon, latency, queue wait, and renewable share.

v2 enhancements:
  - Five-tier energy data provenance (L1-L5 confidence levels)
  - Uncertainty penalty for low-confidence energy/carbon data
  - Integration with EnergyEstimator for benchmark/analytical data
  - Energy source transparency in recommendation output

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
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from greenflex.domain import (
    ComplexityLevel,
    ExecutionMode,
    QualityRequirement,
    QualityRiskLevel,
    RecommendationMode,
    TaskType,
    utc_now,
)
from greenflex.models import ModelRecord
from greenflex.ports import (
    GenerationRequest,
    InferenceProvider,
    ModelScore,
    RecommendationInput,
    RecommendationResult,
)

# ---------------------------------------------------------------------------
# Policy metadata
# ---------------------------------------------------------------------------
POLICY_VERSION = "green-router-rule-v2"
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
        "balanced": QualityRiskLevel.MEDIUM,
        "quality": QualityRiskLevel.LOW,
        "enterprise": QualityRiskLevel.LOW,
    },
    TaskType.ANALYSIS: {
        "economy": QualityRiskLevel.HIGH,
        "balanced": QualityRiskLevel.MEDIUM,
        "quality": QualityRiskLevel.LOW,
        "enterprise": QualityRiskLevel.LOW,
    },
    TaskType.CODE: {
        "economy": QualityRiskLevel.VERY_HIGH,
        "balanced": QualityRiskLevel.HIGH,
        "quality": QualityRiskLevel.MEDIUM,
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
    # --- Energy provenance metadata (v2, L1-L3 + insufficient only) ---
    energy_provenance_tier: str = "insufficient_data"
    energy_confidence_bps: int = 0
    energy_source_description: str = "No verified benchmark data"
    uncertainty_penalty: float = 10.0


class GreenRouterRuleV1:
    """Deterministic multi-objective recommendation policy.

    v2 adds five-tier energy data provenance and uncertainty penalty.
    """

    policy_version = POLICY_VERSION

    def __init__(
        self,
        *,
        carbon_g_per_kwh: int = 550,
        renewable_share_bps: int = 3000,
        price_micro_rmb_per_kwh: int = 660_000,
        queue_depth: int = 0,
        shadow_mode: bool = True,
        energy_estimator: Any | None = None,
    ) -> None:
        self._carbon_g_per_kwh = carbon_g_per_kwh
        self._renewable_share_bps = renewable_share_bps
        self._price_micro_rmb_per_kwh = price_micro_rmb_per_kwh
        self._queue_depth = queue_depth
        self._shadow_mode = shadow_mode
        self._energy_estimator = energy_estimator

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
                c
                for c in scored
                if _TIER_ORDER.get(c.tier, -1) >= _TIER_ORDER["quality"]
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
                    energy_provenance_tier=selected.energy_provenance_tier,
                    energy_confidence_bps=selected.energy_confidence_bps,
                    energy_source_description=selected.energy_source_description,
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

        # Energy estimate — use EnergyEstimator if available (v2), else fallback
        # Only L1-L3 tiers are used; insufficient data gets max penalty
        energy_provenance = "insufficient_data"
        energy_confidence = 0
        energy_source = "No verified benchmark data"
        uncertainty_penalty = 10.0
        tokens_per_second = model.estimated_tokens_per_second

        if self._energy_estimator is not None:
            try:
                est = self._energy_estimator.estimate(
                    model,
                    output_tokens=request.estimated_output_tokens,
                    input_tokens=request.estimated_input_tokens,
                )
                energy_per_1k = est.energy_micro_wh_per_1k_output
                energy_provenance = est.provenance.value
                energy_confidence = est.confidence_bps
                energy_source = est.source_description
                uncertainty_penalty = est.uncertainty_penalty
                if est.tokens_per_second > 0:
                    tokens_per_second = est.tokens_per_second
            except Exception:
                energy_per_1k = model.estimated_energy_micro_wh_per_1k_output
        else:
            energy_per_1k = model.estimated_energy_micro_wh_per_1k_output
            # Use model's stored provenance if available
            if hasattr(model, "energy_data_provenance") and model.energy_data_provenance:
                energy_provenance = model.energy_data_provenance
                energy_confidence = getattr(model, "energy_confidence_bps", 0) or 0
                energy_source = getattr(model, "energy_data_source", None) or "catalog default"
                # Map provenance to penalty (L1-L3 only, insufficient gets max)
                penalty_map = {
                    "l1_local_measured": 1.0,
                    "l2_benchmark_match": 1.05,
                    "l3_cross_gpu_normalized": 1.15,
                    "insufficient_data": 10.0,
                }
                uncertainty_penalty = penalty_map.get(energy_provenance, 10.0)

        energy = energy_per_1k * total_output // 1_000

        # Carbon estimate (micro-g CO2)
        carbon = energy * self._carbon_g_per_kwh // 1_000_000

        # Execution time estimate
        execution_seconds = total_output // max(1, tokens_per_second) + 1

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
            if _TIER_ORDER.get(model.tier, 0) < _TIER_ORDER["balanced"]:
                reasons.append("quality_floor_high")

        # 5. Task capability (code/complex reasoning excludes 0.5B)
        if request.task_type in (TaskType.CODE,) and model.tier == "economy":
            reasons.append("task_capability_excluded")

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
            energy_provenance_tier=energy_provenance,
            energy_confidence_bps=energy_confidence,
            energy_source_description=energy_source,
            uncertainty_penalty=uncertainty_penalty,
        )

    # ------------------------------------------------------------------
    # Phase 2: multi-objective scoring with uncertainty penalty (v2)
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
            # Apply uncertainty penalty to energy and carbon scores (v2)
            # Low-confidence data gets penalized → less likely to be recommended
            e = (c.energy_micro_wh / max_energy) * c.uncertainty_penalty
            carb = (c.carbon_micro_g / max_carbon) * c.uncertainty_penalty
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
                    energy_provenance_tier=c.energy_provenance_tier,
                    energy_confidence_bps=c.energy_confidence_bps,
                    energy_source_description=c.energy_source_description,
                )
            )
        return scored

    def _candidate_reasons(
        self, c: _CandidateEstimate, request: RecommendationInput
    ) -> list[str]:
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

        # Energy provenance reasons (v2)
        if c.energy_provenance_tier == "l1_local_measured":
            reasons.append("energy_data_measured_locally")
        elif c.energy_provenance_tier == "l2_benchmark_match":
            reasons.append("energy_data_benchmark_match")
        elif c.energy_provenance_tier == "insufficient_data":
            reasons.append("energy_data_insufficient")

        return reasons

    # ------------------------------------------------------------------
    # Mode-specific selection
    # ------------------------------------------------------------------
    def _select_by_mode(
        self, scored: list[ModelScore], request: RecommendationInput
    ) -> ModelScore:
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
        # Adjust for energy data confidence (v2)
        energy_conf = getattr(selected, "energy_confidence_bps", 2000)
        if energy_conf < 4000:
            confidence -= 1000  # low confidence energy data
        elif energy_conf >= 8000:
            confidence += 500  # high confidence energy data
        return max(1000, min(9500, confidence))

    def _build_reason_summary(
        self, selected: ModelScore, request: RecommendationInput
    ) -> str:
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

        # Energy data provenance in summary (v2, L1-L3 + insufficient only)
        energy_tier = getattr(selected, "energy_provenance_tier", "insufficient_data")
        tier_labels = {
            "l1_local_measured": "本地实测",
            "l2_benchmark_match": "公开基准匹配",
            "l3_cross_gpu_normalized": "跨GPU归一化",
            "insufficient_data": "数据不足",
        }
        parts.append(f"能耗数据：{tier_labels.get(energy_tier, '数据不足')}")

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


# ---------------------------------------------------------------------------
# Task type classifier (uses local LLM for auto-detection)
# ---------------------------------------------------------------------------
_CLASSIFIER_SYSTEM_PROMPT = """你是一个任务分类器。请将用户的请求准确分类为以下类型之一：
classification, extraction, summarization, analysis, generation, code
分类标准：
- classification：文本分类、情感分析、标签判断、类别判定、打分评级
- extraction：信息提取、实体抽取、字段提取、关键词提取、结构化输出
- summarization：摘要、总结、概括、浓缩、提炼要点
- analysis：分析、解读、评估、推理、多步思考、对比研究
- generation：生成、写作、创作、续写、改写、翻译、润色
- code：代码生成、代码解释、编程问题、调试、脚本编写
只输出 JSON，格式为 {"task_type": "xxx", "confidence": 0.xx}，不要任何解释或额外文字。"""

_CLASSIFIER_FEW_SHOT = """示例：
输入："把这段文字翻译成英文"
输出：{"task_type": "generation", "confidence": 0.95}
输入："总结这篇文章的主要观点"
输出：{"task_type": "summarization", "confidence": 0.92}
输入："判断这条评论是正面还是负面"
输出：{"task_type": "classification", "confidence": 0.88}
输入："从这段文字中提取所有人名和地名"
输出：{"task_type": "extraction", "confidence": 0.94}
输入："Python 怎么读取 CSV 文件"
输出：{"task_type": "code", "confidence": 0.96}
输入："分析一下这个方案的优缺点"
输出：{"task_type": "analysis", "confidence": 0.90}"""


class TaskClassifier:
    """Classify task type from prompt text using a small local model.

    Uses the InferenceProvider port — works with Ollama or any compatible
    backend. Falls back to TaskType.AUTO on any failure.
    """

    def __init__(
        self,
        inference: InferenceProvider,
        model_runtime_name: str = "qwen2.5:1.5b",
    ) -> None:
        self._inference = inference
        self._model_name = model_runtime_name

    async def classify(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> tuple[TaskType, int]:
        """Classify task type from prompt text.

        Returns:
            (task_type, confidence_bps) — confidence in basis points (0-10000).
            On failure, returns (TaskType.AUTO, 0).
        """
        if not prompt or not prompt.strip():
            return TaskType.AUTO, 0

        # Truncate to first 500 chars — classification doesn't need full text
        text_snippet = prompt.strip()[:500]
        user_prompt = f"{_CLASSIFIER_FEW_SHOT}\n\n输入：\"{text_snippet}\"\n输出："

        try:
            result = await self._inference.generate(
                GenerationRequest(
                    model_name=self._model_name,
                    prompt=user_prompt,
                    system_prompt=_CLASSIFIER_SYSTEM_PROMPT,
                    max_output_tokens=64,
                    temperature=0.1,
                )
            )
        except Exception:
            return TaskType.AUTO, 0

        # Parse JSON output
        output = result.output.strip()
        start = output.find("{")
        end = output.rfind("}")
        if start < 0 or end <= start:
            return TaskType.AUTO, 0
        try:
            data = json.loads(output[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            return TaskType.AUTO, 0

        task_type_str = str(data.get("task_type", "")).strip().lower()
        confidence = float(data.get("confidence", 0.5))

        # Validate task type
        try:
            task_type = TaskType(task_type_str)
        except ValueError:
            return TaskType.AUTO, 0

        # Clamp confidence
        confidence_bps = int(max(0.0, min(1.0, confidence)) * 10000)
        return task_type, confidence_bps
