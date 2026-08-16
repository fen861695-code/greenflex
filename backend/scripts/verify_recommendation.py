#!/usr/bin/env python3
"""验证 recommendation.py 修改后核心逻辑仍然正确。
复现 test_recommendation.py 中的关键测试用例。
"""
import sys
import types
from datetime import datetime, timedelta, timezone

# Mock 缺失依赖
if "pydantic_settings" not in sys.modules:
    m = types.ModuleType("pydantic_settings")
    class _BS: 
        def __init__(self, **kw): pass
    m.BaseSettings = _BS
    m.SettingsConfigDict = dict
    sys.modules["pydantic_settings"] = m

if "aiosqlite" not in sys.modules:
    import sqlite3 as _sq
    m = types.ModuleType("aiosqlite")
    for n in dir(_sq):
        if not n.startswith("_"):
            setattr(m, n, getattr(_sq, n))
    class _C:
        stop = None
        def cursor(self): return _Cur()
        def close(self): pass
        def execute(self, *a, **kw): return _Cur()
    class _Cur:
        def execute(self, *a, **kw): return self
        def fetchall(self): return []
        def fetchone(self): return None
        def close(self): pass
    m.Connection = _C
    m.Cursor = _Cur
    m.connect = lambda *a, **kw: _C()
    sys.modules["aiosqlite"] = m

sys.path.insert(0, "src")

from greenflex.domain import (
    ExecutionMode, QualityRequirement, QualityRiskLevel,
    RecommendationMode, TaskType,
)
from greenflex.models import ModelRecord
from greenflex.recommendation import GreenRouterRuleV1, POLICY_VERSION
from greenflex.ports import RecommendationInput

UTC = timezone.utc

def make_models():
    return [
        ModelRecord(id="qwen2.5-0.5b-q4", runtime_name="qwen2.5:0.5b",
            display_name="Qwen2.5 0.5B", tier="economy", parameter_b="0.5B",
            context_limit=32768, recommended_for_json="[]",
            input_rate_micro_rmb_per_million=100_000, output_rate_micro_rmb_per_million=300_000,
            estimated_tokens_per_second=200, estimated_energy_micro_wh_per_1k_output=100_000,
            enabled=True, energy_data_provenance="l2_benchmark_match",
            energy_confidence_bps=8500, energy_data_source="JouleBench"),
        ModelRecord(id="qwen2.5-1.5b-q4", runtime_name="qwen2.5:1.5b",
            display_name="Qwen2.5 1.5B", tier="balanced", parameter_b="1.5B",
            context_limit=32768, recommended_for_json="[]",
            input_rate_micro_rmb_per_million=300_000, output_rate_micro_rmb_per_million=800_000,
            estimated_tokens_per_second=100, estimated_energy_micro_wh_per_1k_output=250_000,
            enabled=True, energy_data_provenance="l2_benchmark_match",
            energy_confidence_bps=8500, energy_data_source="JouleBench"),
        ModelRecord(id="qwen2.5-3b-q4", runtime_name="qwen2.5:3b",
            display_name="Qwen2.5 3B", tier="quality", parameter_b="3B",
            context_limit=32768, recommended_for_json="[]",
            input_rate_micro_rmb_per_million=600_000, output_rate_micro_rmb_per_million=1_500_000,
            estimated_tokens_per_second=65, estimated_energy_micro_wh_per_1k_output=450_000,
            enabled=True, energy_data_provenance="l2_benchmark_match",
            energy_confidence_bps=8500, energy_data_source="JouleBench"),
    ]

def make_input(**over):
    d = dict(mode=RecommendationMode.SMART, task_type=TaskType.AUTO,
             estimated_input_tokens=128, estimated_output_tokens=256,
             item_count=1, quality_requirement=QualityRequirement.STANDARD)
    d.update(over)
    return RecommendationInput(**d)

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}  {detail}")

policy = GreenRouterRuleV1()
models = make_models()

print("=== 核心逻辑验证 ===")

# 1. 政策版本
check("policy_version", policy.policy_version == POLICY_VERSION)

# 2. 简单分类推荐小模型
r = policy.recommend(request=make_input(task_type=TaskType.CLASSIFICATION,
    quality_requirement=QualityRequirement.MINIMUM), available_models=models)
check("simple_classification_prefers_small", r.recommended_tier in ("economy", "balanced"),
      f"got {r.recommended_tier}")

# 3. 代码任务+关键质量用 quality
r = policy.recommend(request=make_input(task_type=TaskType.CODE,
    quality_requirement=QualityRequirement.CRITICAL), available_models=models)
check("code_critical_uses_quality", r.recommended_tier == "quality",
      f"got {r.recommended_tier}")
check("code_critical_model", r.recommended_model_id == "qwen2.5-3b-q4",
      f"got {r.recommended_model_id}")

# 4. 关键质量底线
r = policy.recommend(request=make_input(quality_requirement=QualityRequirement.CRITICAL), available_models=models)
check("critical_quality_floor", r.recommended_tier == "quality",
      f"got {r.recommended_tier}")

# 5. economy 模式选最低价
r = policy.recommend(request=make_input(mode=RecommendationMode.ECONOMY), available_models=models)
prices = {a.model_id: a.estimated_price_micro_rmb for a in r.alternatives}
prices[r.recommended_model_id] = r.estimated_price_micro_rmb
check("economy_mode_cheapest", r.estimated_price_micro_rmb <= min(prices.values()))

# 6. quality 模式选 quality 档
r = policy.recommend(request=make_input(mode=RecommendationMode.QUALITY), available_models=models)
check("quality_mode_picks_quality", r.recommended_tier == "quality",
      f"got {r.recommended_tier}")

# 7. 预算约束
r = policy.recommend(request=make_input(mode=RecommendationMode.ECONOMY, budget_micro_rmb=100), available_models=models)
check("budget_constraint", r.recommended_tier == "economy", f"got {r.recommended_tier}")

# 8. 无可行模型抛异常
try:
    policy.recommend(request=make_input(budget_micro_rmb=1), available_models=models)
    check("no_feasible_raises", False, "should have raised")
except Exception as e:
    check("no_feasible_raises", "没有满足约束" in str(e))

# 9. 截止时间约束
try:
    now = datetime.now(UTC)
    policy.recommend(request=make_input(estimated_output_tokens=10_000,
        deadline=now + timedelta(seconds=1)), available_models=models, now=now)
    check("deadline_constraint", False, "should have raised")
except Exception as e:
    check("deadline_constraint", "没有满足约束" in str(e))

# 10. 上下文限制
try:
    policy.recommend(request=make_input(estimated_input_tokens=40000, estimated_output_tokens=100), available_models=models)
    check("context_limit", False, "should have raised")
except Exception as e:
    check("context_limit", "没有满足约束" in str(e))

# 11. 确定性
now = datetime.now(UTC)
r1 = policy.recommend(request=make_input(), available_models=models, now=now)
r2 = policy.recommend(request=make_input(), available_models=models, now=now)
check("deterministic", r1.recommended_model_id == r2.recommended_model_id)

# 12. 返回备选
r = policy.recommend(request=make_input(), available_models=models)
check("returns_alternatives", len(r.alternatives) >= 1)
check("alternatives_exclude_selected",
      r.recommended_model_id not in {a.model_id for a in r.alternatives})

# 13. 影子模式
p2 = GreenRouterRuleV1(shadow_mode=True)
r = p2.recommend(request=make_input(), available_models=models)
check("shadow_mode", r.shadow_mode is True)

# 14. reason codes
r = policy.recommend(request=make_input(), available_models=models)
check("reason_codes", len(r.reason_codes) > 0)
check("reason_summary", bool(r.reason_summary))

# 15. 置信度范围
r = policy.recommend(request=make_input(), available_models=models)
check("confidence_range", 1000 <= r.confidence_bps <= 9500,
      f"got {r.confidence_bps}")

# 16. 能耗估算为正
r = policy.recommend(request=make_input(), available_models=models)
check("energy_positive", r.estimated_energy_micro_wh > 0)
check("carbon_positive", r.estimated_carbon_micro_g > 0)
check("price_positive", r.estimated_price_micro_rmb > 0)

# 17. 禁用模型排除
models2 = make_models()
models2[2].enabled = False
r = policy.recommend(request=make_input(mode=RecommendationMode.QUALITY), available_models=models2)
check("disabled_excluded", r.recommended_model_id != "qwen2.5-3b-q4",
      f"got {r.recommended_model_id}")

# 18. 复杂度接入验证：analysis 高复杂度不应选 economy
r = policy.recommend(request=make_input(task_type=TaskType.ANALYSIS,
    estimated_input_tokens=1500, estimated_output_tokens=512,
    quality_requirement=QualityRequirement.HIGH), available_models=models)
check("analysis_high_complexity_not_economy", r.recommended_tier != "economy",
      f"got {r.recommended_tier}")

# 19. 大上下文应提高质量风险（复杂度接入验证）
r = policy.recommend(request=make_input(task_type=TaskType.SUMMARIZATION,
    estimated_input_tokens=8000, estimated_output_tokens=512), available_models=models)
# 8000+512=8512 tokens → HIGH complexity → summarization×HIGH×economy = HIGH risk
check("large_context_high_risk",
      r.quality_risk in (QualityRiskLevel.HIGH, QualityRiskLevel.VERY_HIGH),
      f"risk: {r.quality_risk}, tier: {r.recommended_tier}")

# 20. 长输出生成应提高质量风险
r = policy.recommend(request=make_input(task_type=TaskType.GENERATION,
    estimated_input_tokens=256, estimated_output_tokens=1024), available_models=models)
check("long_output_high_risk",
      r.quality_risk in (QualityRiskLevel.HIGH, QualityRiskLevel.VERY_HIGH),
      f"risk: {r.quality_risk}, tier: {r.recommended_tier}")

print(f"\n=== 结果: {passed} 通过, {failed} 失败 ===")
sys.exit(1 if failed > 0 else 0)
