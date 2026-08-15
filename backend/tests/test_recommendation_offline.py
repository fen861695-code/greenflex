"""推荐系统离线评估测试 — 作为 CI 回归门禁。

运行评估脚本中的全部标注用例，断言核心指标达标。
用法: pytest tests/test_recommendation_offline.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

# 导入 scripts 目录下的评估模块
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from evaluate_recommendation import (  # noqa: E402
    EVAL_CASES,
    RecommendationEvaluator,
    build_models,
    generate_report,
)

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def models():
    return build_models()


@pytest.fixture(scope="module")
def results(models):
    evaluator = RecommendationEvaluator(models)
    return [evaluator.run_case(case) for case in EVAL_CASES]


@pytest.fixture(scope="module")
def report(results):
    return generate_report(results)


class TestOfflineEvaluationMetrics:
    """核心指标断言 — 用于 CI 门禁。"""

    def test_no_errors(self, results):
        errors = [r for r in results if r.error]
        assert len(errors) == 0, f"存在错误用例: {[e.case.name for e in errors]}"

    def test_tier_hit_rate_above_threshold(self, report):
        """档位命中率 >= 90%。"""
        assert report["summary"]["tier_hit_rate"] >= 90.0, (
            f"档位命中率 {report['summary']['tier_hit_rate']}% 低于 90%"
        )

    def test_top3_coverage_above_threshold(self, report):
        """Top-3 覆盖率 >= 95%。"""
        assert report["summary"]["top3_coverage"] >= 95.0, (
            f"Top-3 覆盖率 {report['summary']['top3_coverage']}% 低于 95%"
        )

    def test_constraint_satisfaction_perfect(self, report):
        """约束满足率必须 100%。"""
        assert report["summary"]["constraint_satisfaction"] == 100.0, (
            f"约束满足率 {report['summary']['constraint_satisfaction']}% 未达 100%"
        )

    def test_mode_consistency_perfect(self, report):
        """模式一致性必须 100%。"""
        assert report["summary"]["mode_consistency"] == 100.0, (
            f"模式一致性 {report['summary']['mode_consistency']}% 未达 100%"
        )

    def test_all_cases_have_recommendation(self, results):
        """每个有效用例都必须有推荐结果。"""
        for r in results:
            if r.error:
                continue
            assert r.recommended_model_id, f"{r.case.name}: 无推荐模型"
            assert r.recommended_tier, f"{r.case.name}: 无推荐档位"

    def test_confidence_in_range(self, results):
        """置信度必须在合理范围内。"""
        for r in results:
            if r.error:
                continue
            assert 1000 <= r.confidence_bps <= 9500, (
                f"{r.case.name}: 置信度 {r.confidence_bps} 超出 [1000, 9500]"
            )

    def test_estimates_positive(self, results):
        """价格/能耗/碳排估算必须为正。"""
        for r in results:
            if r.error:
                continue
            assert r.estimated_price_micro > 0, f"{r.case.name}: 价格非正"
            assert r.estimated_energy_micro_wh > 0, f"{r.case.name}: 能耗非正"
            assert r.estimated_carbon_micro_g > 0, f"{r.case.name}: 碳排非正"


class TestTaskTypeCoverage:
    """各任务类型都有足够覆盖且表现合理。"""

    @pytest.mark.parametrize("task_type", [
        "classification", "extraction", "summarization",
        "analysis", "generation", "code", "auto",
    ])
    def test_task_type_has_cases(self, report, task_type):
        assert task_type in report["by_task_type"], f"缺少 {task_type} 类型用例"
        assert report["by_task_type"][task_type]["total"] >= 2, (
            f"{task_type} 用例数不足"
        )

    @pytest.mark.parametrize("task_type", [
        "classification", "extraction", "summarization",
        "analysis", "generation", "code", "auto",
    ])
    def test_task_type_hit_rate(self, report, task_type):
        d = report["by_task_type"][task_type]
        rate = d["tier_hit"] / d["total"] * 100
        assert rate >= 80.0, f"{task_type} 命中率 {rate:.1f}% 低于 80%"


class TestModeBehavior:
    """各推荐模式行为正确。"""

    def test_economy_mode_picks_cheapest(self, models):
        from greenflex.domain import RecommendationMode, TaskType, QualityRequirement
        from greenflex.ports import RecommendationInput
        from datetime import datetime, timezone

        evaluator = RecommendationEvaluator(models)
        req = RecommendationInput(
            mode=RecommendationMode.ECONOMY,
            task_type=TaskType.CLASSIFICATION,
            estimated_input_tokens=128,
            estimated_output_tokens=32,
            item_count=1,
            quality_requirement=QualityRequirement.STANDARD,
        )
        result = evaluator.policy.recommend(
            request=req, available_models=models, now=datetime.now(timezone.utc)
        )
        all_prices = [result.estimated_price_micro_rmb] + [
            a.estimated_price_micro_rmb for a in result.alternatives
        ]
        assert result.estimated_price_micro_rmb <= min(all_prices)

    def test_quality_mode_picks_quality_tier(self, models):
        from greenflex.domain import RecommendationMode, TaskType, QualityRequirement
        from greenflex.ports import RecommendationInput
        from datetime import datetime, timezone

        evaluator = RecommendationEvaluator(models)
        req = RecommendationInput(
            mode=RecommendationMode.QUALITY,
            task_type=TaskType.CLASSIFICATION,
            estimated_input_tokens=128,
            estimated_output_tokens=32,
            item_count=1,
            quality_requirement=QualityRequirement.STANDARD,
        )
        result = evaluator.policy.recommend(
            request=req, available_models=models, now=datetime.now(timezone.utc)
        )
        assert result.recommended_tier == "quality"


class TestComplexityIntegration:
    """复杂度接入验证 — 确保 3D 矩阵生效。"""

    def test_high_complexity_analysis_not_economy(self, models):
        from greenflex.domain import TaskType, QualityRequirement
        from greenflex.ports import RecommendationInput
        from datetime import datetime, timezone

        evaluator = RecommendationEvaluator(models)
        req = RecommendationInput(
            task_type=TaskType.ANALYSIS,
            estimated_input_tokens=3000,
            estimated_output_tokens=512,
            item_count=1,
            quality_requirement=QualityRequirement.HIGH,
        )
        result = evaluator.policy.recommend(
            request=req, available_models=models, now=datetime.now(timezone.utc)
        )
        assert result.recommended_tier != "economy", (
            f"高复杂度分析任务不应选 economy, 实际 {result.recommended_tier}"
        )

    def test_large_input_summarization_high_risk(self, models):
        from greenflex.domain import TaskType, QualityRiskLevel
        from greenflex.ports import RecommendationInput
        from datetime import datetime, timezone

        evaluator = RecommendationEvaluator(models)
        req = RecommendationInput(
            task_type=TaskType.SUMMARIZATION,
            estimated_input_tokens=10000,
            estimated_output_tokens=512,
            item_count=1,
        )
        result = evaluator.policy.recommend(
            request=req, available_models=models, now=datetime.now(timezone.utc)
        )
        # 大输入摘要任务，economy 档风险应为 HIGH/VERY_HIGH
        econ_alt = next(
            (a for a in result.alternatives if a.tier == "economy"), None
        )
        if econ_alt:
            assert econ_alt.quality_risk in (
                QualityRiskLevel.HIGH, QualityRiskLevel.VERY_HIGH
            ), f"大输入摘要 economy 风险应为 HIGH, 实际 {econ_alt.quality_risk}"

    def test_long_output_generation_not_low_risk(self, models):
        from greenflex.domain import TaskType, QualityRiskLevel
        from greenflex.ports import RecommendationInput
        from datetime import datetime, timezone

        evaluator = RecommendationEvaluator(models)
        req = RecommendationInput(
            task_type=TaskType.GENERATION,
            estimated_input_tokens=64,
            estimated_output_tokens=1500,
            item_count=1,
        )
        result = evaluator.policy.recommend(
            request=req, available_models=models, now=datetime.now(timezone.utc)
        )
        assert result.quality_risk != QualityRiskLevel.LOW, (
            f"长输出生成任务风险不应为 LOW, 实际 {result.quality_risk}"
        )
