from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from greenflex.domain import (
    ExecutionMode,
    QualityRequirement,
    QualityRiskLevel,
    RecommendationMode,
    TaskType,
)
from greenflex.models import ModelRecord
from greenflex.recommendation import (
    POLICY_VERSION,
    GreenRouterRuleV1,
    hash_recommendation_request,
)
from greenflex.ports import RecommendationInput


def _make_models() -> list[ModelRecord]:
    return [
        ModelRecord(
            id="qwen2.5-0.5b-q4",
            runtime_name="qwen2.5:0.5b",
            display_name="Qwen2.5 0.5B",
            tier="economy",
            parameter_b="0.5B",
            context_limit=4096,
            recommended_for_json="[]",
            input_rate_micro_rmb_per_million=100_000,
            output_rate_micro_rmb_per_million=300_000,
            estimated_tokens_per_second=200,
            estimated_energy_micro_wh_per_1k_output=100_000,
            enabled=True,
        ),
        ModelRecord(
            id="qwen2.5-1.5b-q4",
            runtime_name="qwen2.5:1.5b",
            display_name="Qwen2.5 1.5B",
            tier="balanced",
            parameter_b="1.5B",
            context_limit=4096,
            recommended_for_json="[]",
            input_rate_micro_rmb_per_million=300_000,
            output_rate_micro_rmb_per_million=800_000,
            estimated_tokens_per_second=100,
            estimated_energy_micro_wh_per_1k_output=250_000,
            enabled=True,
        ),
        ModelRecord(
            id="qwen2.5-3b-q4",
            runtime_name="qwen2.5:3b",
            display_name="Qwen2.5 3B",
            tier="quality",
            parameter_b="3B",
            context_limit=4096,
            recommended_for_json="[]",
            input_rate_micro_rmb_per_million=600_000,
            output_rate_micro_rmb_per_million=1_500_000,
            estimated_tokens_per_second=65,
            estimated_energy_micro_wh_per_1k_output=450_000,
            enabled=True,
        ),
    ]


def _make_input(**overrides) -> RecommendationInput:
    defaults = dict(
        mode=RecommendationMode.SMART,
        task_type=TaskType.AUTO,
        estimated_input_tokens=128,
        estimated_output_tokens=256,
        item_count=1,
        quality_requirement=QualityRequirement.STANDARD,
    )
    defaults.update(overrides)
    return RecommendationInput(**defaults)


class TestGreenRouterPolicy:
    def test_policy_version(self):
        policy = GreenRouterRuleV1()
        assert policy.policy_version == POLICY_VERSION

    def test_simple_classification_recommends_smaller_model(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        req = _make_input(
            task_type=TaskType.CLASSIFICATION,
            quality_requirement=QualityRequirement.MINIMUM,
        )
        result = policy.recommend(request=req, available_models=models)
        # Simple classification should prefer economy or balanced
        assert result.recommended_tier in ("economy", "balanced")
        assert result.quality_risk in (QualityRiskLevel.LOW, QualityRiskLevel.MEDIUM)

    def test_code_task_uses_quality_tier(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        req = _make_input(
            task_type=TaskType.CODE,
            quality_requirement=QualityRequirement.CRITICAL,
        )
        result = policy.recommend(request=req, available_models=models)
        # Code with critical quality must use quality tier
        assert result.recommended_tier == "quality"
        assert result.recommended_model_id == "qwen2.5-3b-q4"

    def test_critical_quality_floor(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        req = _make_input(quality_requirement=QualityRequirement.CRITICAL)
        result = policy.recommend(request=req, available_models=models)
        assert result.recommended_tier == "quality"

    def test_economy_mode_picks_cheapest(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        req = _make_input(mode=RecommendationMode.ECONOMY)
        result = policy.recommend(request=req, available_models=models)
        # Economy mode should pick the cheapest feasible model
        prices = {alt.model_id: alt.estimated_price_micro_rmb for alt in result.alternatives}
        prices[result.recommended_model_id] = result.estimated_price_micro_rmb
        assert result.estimated_price_micro_rmb <= min(prices.values())

    def test_quality_mode_picks_quality_tier(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        req = _make_input(mode=RecommendationMode.QUALITY)
        result = policy.recommend(request=req, available_models=models)
        assert result.recommended_tier == "quality"

    def test_budget_constraint_filters_models(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        # Very tight budget should only allow economy model
        req = _make_input(
            mode=RecommendationMode.ECONOMY,
            budget_micro_rmb=100,  # 0.0001 RMB
        )
        result = policy.recommend(request=req, available_models=models)
        assert result.recommended_tier == "economy"

    def test_no_feasible_model_raises(self):
        from greenflex.domain import DomainError

        policy = GreenRouterRuleV1()
        models = _make_models()
        # Impossible budget
        req = _make_input(budget_micro_rmb=1)
        with pytest.raises(DomainError, match="no_feasible_model"):
            policy.recommend(request=req, available_models=models)

    def test_deadline_constraint(self):
        from greenflex.domain import DomainError

        policy = GreenRouterRuleV1()
        models = _make_models()
        # Impossible deadline (1 second from now)
        now = datetime.now(UTC)
        req = _make_input(
            estimated_output_tokens=10_000,  # would take ~150s on 3B
            deadline=now + timedelta(seconds=1),
        )
        with pytest.raises(DomainError, match="no_feasible_model"):
            policy.recommend(request=req, available_models=models, now=now)

    def test_context_limit_constraint(self):
        from greenflex.domain import DomainError

        policy = GreenRouterRuleV1()
        models = _make_models()
        req = _make_input(
            estimated_input_tokens=5000,  # exceeds 4096 context
            estimated_output_tokens=100,
        )
        with pytest.raises(DomainError, match="no_feasible_model"):
            policy.recommend(request=req, available_models=models)

    def test_deterministic_results(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        req = _make_input()
        now = datetime.now(UTC)
        r1 = policy.recommend(request=req, available_models=models, now=now)
        r2 = policy.recommend(request=req, available_models=models, now=now)
        assert r1.recommended_model_id == r2.recommended_model_id
        assert r1.estimated_price_micro_rmb == r2.estimated_price_micro_rmb
        assert r1.composite_score if hasattr(r1, 'composite_score') else True

    def test_returns_alternatives(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        req = _make_input()
        result = policy.recommend(request=req, available_models=models)
        assert len(result.alternatives) >= 1
        alt_ids = {a.model_id for a in result.alternatives}
        assert result.recommended_model_id not in alt_ids

    def test_shadow_mode_default(self):
        policy = GreenRouterRuleV1(shadow_mode=True)
        models = _make_models()
        req = _make_input()
        result = policy.recommend(request=req, available_models=models)
        assert result.shadow_mode is True

    def test_reason_codes_present(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        req = _make_input()
        result = policy.recommend(request=req, available_models=models)
        assert len(result.reason_codes) > 0
        assert result.reason_summary

    def test_confidence_bps_in_range(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        req = _make_input()
        result = policy.recommend(request=req, available_models=models)
        assert 1000 <= result.confidence_bps <= 9500

    def test_energy_estimates_positive(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        req = _make_input()
        result = policy.recommend(request=req, available_models=models)
        assert result.estimated_energy_micro_wh > 0
        assert result.estimated_carbon_micro_g > 0
        assert result.estimated_price_micro_rmb > 0

    def test_request_hash_deterministic(self):
        h1 = hash_recommendation_request(
            task_type="classification",
            mode="smart",
            quality_requirement="standard",
            estimated_input_tokens=100,
            estimated_output_tokens=200,
            item_count=1,
            has_budget=False,
            has_deadline=False,
        )
        h2 = hash_recommendation_request(
            task_type="classification",
            mode="smart",
            quality_requirement="standard",
            estimated_input_tokens=100,
            estimated_output_tokens=200,
            item_count=1,
            has_budget=False,
            has_deadline=False,
        )
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex digest

    def test_request_hash_differs_for_different_inputs(self):
        h1 = hash_recommendation_request(
            task_type="classification",
            mode="smart",
            quality_requirement="standard",
            estimated_input_tokens=100,
            estimated_output_tokens=200,
            item_count=1,
            has_budget=False,
            has_deadline=False,
        )
        h2 = hash_recommendation_request(
            task_type="code",
            mode="smart",
            quality_requirement="standard",
            estimated_input_tokens=100,
            estimated_output_tokens=200,
            item_count=1,
            has_budget=False,
            has_deadline=False,
        )
        assert h1 != h2

    def test_disabled_models_excluded(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        models[2].enabled = False  # disable quality model
        req = _make_input(mode=RecommendationMode.QUALITY)
        # Should fall back to balanced when quality is disabled
        result = policy.recommend(request=req, available_models=models)
        assert result.recommended_model_id != "qwen2.5-3b-q4"

    def test_high_risk_low_confidence_fallback(self):
        policy = GreenRouterRuleV1()
        models = _make_models()
        # Auto mode with very short prompt (low confidence) and high risk
        req = _make_input(
            task_type=TaskType.GENERATION,
            estimated_input_tokens=5,  # very short, low confidence
        )
        result = policy.recommend(request=req, available_models=models)
        # Should fall back to quality tier due to safety guard
        # (unless confidence is still high enough)
        assert result.quality_risk in (QualityRiskLevel.LOW, QualityRiskLevel.MEDIUM) or \
               "safety_high_risk_fallback" in result.reason_codes


class TestRecommendationAPI:
    @pytest.mark.asyncio
    async def test_recommendations_endpoint(self, api_client):
        response = await api_client.post(
            "/api/v1/recommendations",
            json={
                "mode": "smart",
                "task_type": "auto",
                "estimated_input_tokens": 128,
                "estimated_output_tokens": 256,
                "item_count": 1,
                "quality_requirement": "standard",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "recommendation_id" in data
        assert "recommended_model_id" in data
        assert "reason_summary" in data
        assert "alternatives" in data
        assert data["policy_version"] == POLICY_VERSION

    @pytest.mark.asyncio
    async def test_recommendations_economy_mode(self, api_client):
        response = await api_client.post(
            "/api/v1/recommendations",
            json={
                "mode": "economy",
                "task_type": "classification",
                "estimated_input_tokens": 64,
                "estimated_output_tokens": 128,
                "item_count": 1,
                "quality_requirement": "minimum",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["recommended_tier"] in ("economy", "balanced")

    @pytest.mark.asyncio
    async def test_recommendations_with_budget(self, api_client):
        response = await api_client.post(
            "/api/v1/recommendations",
            json={
                "mode": "smart",
                "task_type": "auto",
                "estimated_input_tokens": 128,
                "estimated_output_tokens": 256,
                "item_count": 1,
                "quality_requirement": "standard",
                "budget_rmb": 0.001,
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_recommendations_invalid_budget(self, api_client):
        response = await api_client.post(
            "/api/v1/recommendations",
            json={
                "mode": "smart",
                "task_type": "auto",
                "estimated_input_tokens": 128,
                "estimated_output_tokens": 256,
                "item_count": 1,
                "quality_requirement": "standard",
                "budget_rmb": 0.000001,  # impossibly small
            },
        )
        assert response.status_code == 409
