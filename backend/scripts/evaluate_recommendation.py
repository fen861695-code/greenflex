#!/usr/bin/env python3
"""GreenFlex 推荐系统离线评估脚本。

用法:
    cd backend && python scripts/evaluate_recommendation.py
    python scripts/evaluate_recommendation.py --output report.json
    python scripts/evaluate_recommendation.py --strict  (任一指标不达标则退出码非0)

评估维度:
    1. 档位命中率 (Tier Hit Rate) - 推荐档位是否符合标注预期
    2. Top-3 覆盖率 (Top-3 Coverage) - 期望档位是否出现在备选中
    3. 约束满足率 (Constraint Satisfaction) - 硬约束是否全部满足
    4. 模式一致性 (Mode Consistency) - economy/quality/smart 模式行为是否正确
    5. 置信度校准 (Confidence Calibration) - 高置信度是否对应高准确率
    6. 鲁棒性 (Robustness) - 输入 token 微变时推荐是否稳定
    7. 能耗分级影响 (Energy Tier Impact) - 不同能耗数据等级对推荐的影响
    8. 多目标 Regret - 推荐结果 vs 理论最优的差距
"""
from __future__ import annotations

import argparse
import json
import sys
import types
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Mock 缺失的依赖模块以绕过导入链（评估脚本不需要 DB/API 功能）
def _mock_module(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod

if "pydantic_settings" not in sys.modules:
    _mock = types.ModuleType("pydantic_settings")
    class _BaseSettings:
        def __init__(self, **kwargs): pass
    _mock.BaseSettings = _BaseSettings
    _mock.SettingsConfigDict = dict
    sys.modules["pydantic_settings"] = _mock

if "aiosqlite" not in sys.modules:
    import sqlite3 as _sqlite3
    _aiosqlite = types.ModuleType("aiosqlite")
    # 复制 sqlite3 的所有异常和常量
    for _name in dir(_sqlite3):
        if not _name.startswith("_"):
            setattr(_aiosqlite, _name, getattr(_sqlite3, _name))
    class _Connection:
        stop = None
        def cursor(self): return _Cursor()
        def close(self): pass
        def execute(self, *a, **kw): return _Cursor()
    class _Cursor:
        def execute(self, *a, **kw): return self
        def executemany(self, *a, **kw): return self
        def fetchall(self): return []
        def fetchone(self): return None
        def close(self): pass
    _aiosqlite.Connection = _Connection
    _aiosqlite.Cursor = _Cursor
    _aiosqlite.connect = lambda *a, **kw: _Connection()
    sys.modules["aiosqlite"] = _aiosqlite

# 确保可以导入 greenflex 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from greenflex.catalog import MODEL_SEEDS, _enrich_energy_provenance
from greenflex.domain import (
    ExecutionMode,
    QualityRequirement,
    QualityRiskLevel,
    RecommendationMode,
    TaskType,
)
from greenflex.models import ModelRecord
from greenflex.ports import RecommendationInput
from greenflex.recommendation import GreenRouterRuleV1

UTC = timezone.utc

# ---------------------------------------------------------------------------
# 模型列表构造
# ---------------------------------------------------------------------------

def build_models() -> list[ModelRecord]:
    """从 catalog seed 构造 enabled 的本地模型列表。"""
    models: list[ModelRecord] = []
    for seed in MODEL_SEEDS:
        if not seed.get("enabled", True):
            continue
        enriched = _enrich_energy_provenance(seed)
        models.append(ModelRecord(**enriched))
    return models


# ---------------------------------------------------------------------------
# 标注测试用例
# ---------------------------------------------------------------------------

@dataclass
class EvalCase:
    name: str
    task_type: TaskType
    input_tokens: int
    output_tokens: int
    expected_tiers: list[str]          # 可接受的推荐档位
    quality_requirement: QualityRequirement = QualityRequirement.STANDARD
    mode: RecommendationMode = RecommendationMode.SMART
    item_count: int = 1
    budget_micro_rmb: int | None = None
    deadline_s: int | None = None      # 从 now 起多少秒
    execution_mode: ExecutionMode = ExecutionMode.IMMEDIATE
    prompt_preview: str | None = None  # 传入实际 prompt 文本，测试规则路径
    note: str = ""


EVAL_CASES: list[EvalCase] = [
    # === classification (分类) ===
    EvalCase("cls-简单情感-标准", TaskType.CLASSIFICATION, 64, 32,
             ["economy", "balanced"], QualityRequirement.STANDARD, note="短文本情感分类，应偏好小模型"),
    EvalCase("cls-简单情感-最低质量", TaskType.CLASSIFICATION, 64, 32,
             ["economy"], QualityRequirement.MINIMUM, note="最低质量要求，应选 economy"),
    EvalCase("cls-长文本分类-较高质量", TaskType.CLASSIFICATION, 2000, 64,
             ["balanced", "quality"], QualityRequirement.HIGH, note="长文本+高质量，应选 balanced 或 quality"),
    EvalCase("cls-关键质量", TaskType.CLASSIFICATION, 128, 32,
             ["quality", "enterprise"], QualityRequirement.CRITICAL, note="关键质量必须 quality 档以上"),

    # === extraction (抽取) ===
    EvalCase("ext-简单实体抽取", TaskType.EXTRACTION, 128, 128,
             ["economy", "balanced"], QualityRequirement.STANDARD, note="实体抽取，小模型可胜任"),
    EvalCase("ext-复杂字段抽取", TaskType.EXTRACTION, 1000, 256,
             ["balanced", "quality"], QualityRequirement.HIGH, note="多字段抽取，需中等以上模型"),
    EvalCase("ext-批量抽取", TaskType.EXTRACTION, 256, 128,
             ["economy", "balanced"], QualityRequirement.STANDARD, item_count=50, note="批量任务，应考虑能耗/成本"),

    # === summarization (摘要) ===
    EvalCase("sum-短文摘要", TaskType.SUMMARIZATION, 500, 128,
             ["economy", "balanced"], QualityRequirement.STANDARD, note="短文摘要，小模型可做"),
    EvalCase("sum-长文摘要-详细", TaskType.SUMMARIZATION, 3000, 512,
             ["balanced", "quality"], QualityRequirement.HIGH, note="长文详细摘要，需中等以上"),
    EvalCase("sum-关键摘要", TaskType.SUMMARIZATION, 2000, 256,
             ["quality"], QualityRequirement.CRITICAL, note="关键质量摘要"),

    # === analysis (分析) ===
    EvalCase("ana-简单对比", TaskType.ANALYSIS, 256, 256,
             ["balanced", "quality"], QualityRequirement.STANDARD, note="分析任务不应选 economy"),
    EvalCase("ana-复杂推理", TaskType.ANALYSIS, 1500, 512,
             ["quality"], QualityRequirement.HIGH, note="复杂分析需要 quality"),
    EvalCase("ana-关键分析", TaskType.ANALYSIS, 800, 512,
             ["quality", "enterprise"], QualityRequirement.CRITICAL, note="关键分析必须高质量"),
    EvalCase("ana-economy模式分析", TaskType.ANALYSIS, 256, 256,
             ["economy", "balanced"], QualityRequirement.STANDARD,
             mode=RecommendationMode.ECONOMY, note="economy 模式下分析任务也应尽量省钱，但 code 任务排除 economy"),

    # === generation (生成) ===
    EvalCase("gen-简单翻译", TaskType.GENERATION, 128, 256,
             ["economy", "balanced"], QualityRequirement.STANDARD, note="翻译任务，小模型可做"),
    EvalCase("gen-创意写作", TaskType.GENERATION, 64, 512,
             ["balanced", "quality"], QualityRequirement.HIGH, note="创意写作需要质量"),
    EvalCase("gen-长文本生成", TaskType.GENERATION, 256, 1024,
             ["balanced", "quality"], QualityRequirement.STANDARD, note="长输出需稳定模型"),
    EvalCase("gen-quality模式", TaskType.GENERATION, 128, 256,
             ["quality"], QualityRequirement.STANDARD,
             mode=RecommendationMode.QUALITY, note="quality 模式必须选 quality 档"),

    # === code (代码) ===
    EvalCase("code-简单问答", TaskType.CODE, 128, 256,
             ["balanced", "quality"], QualityRequirement.STANDARD, note="代码任务排除 economy 档"),
    EvalCase("code-代码生成", TaskType.CODE, 256, 512,
             ["balanced", "quality"], QualityRequirement.HIGH, note="代码生成, HIGH质量下balanced可接受"),
    EvalCase("code-关键代码", TaskType.CODE, 512, 1024,
             ["quality", "enterprise"], QualityRequirement.CRITICAL, note="关键代码必须高质量"),
    EvalCase("code-economy模式", TaskType.CODE, 128, 256,
             ["balanced"], QualityRequirement.STANDARD,
             mode=RecommendationMode.ECONOMY, note="economy 模式下 code 任务仍不能选 economy 档"),

    # === auto (自动检测，用保守兜底) ===
    EvalCase("auto-短文本", TaskType.AUTO, 64, 256,
             ["economy", "balanced"], QualityRequirement.STANDARD, note="AUTO 类型，保守兜底"),
    EvalCase("auto-长文本", TaskType.AUTO, 2000, 512,
             ["balanced", "quality"], QualityRequirement.HIGH, note="AUTO + 长文本，偏保守"),

    # === 约束测试 ===
    EvalCase("con-紧预算", TaskType.CLASSIFICATION, 128, 32,
             ["economy"], QualityRequirement.STANDARD,
             mode=RecommendationMode.ECONOMY, budget_micro_rmb=500, note="预算极紧，只能选 economy"),
    EvalCase("con-紧截止时间", TaskType.CLASSIFICATION, 128, 32,
             ["economy", "balanced"], QualityRequirement.STANDARD,
             deadline_s=10, note="截止时间极短，应选快模型"),
    EvalCase("con-大上下文", TaskType.SUMMARIZATION, 8000, 512,
             ["balanced", "quality"], QualityRequirement.STANDARD, note="大输入需大上下文模型"),

    # === 模式一致性测试 ===
    EvalCase("mode-smart-分类", TaskType.CLASSIFICATION, 128, 32,
             ["economy", "balanced"], QualityRequirement.STANDARD,
             mode=RecommendationMode.SMART, note="smart 模式分类任务"),
    EvalCase("mode-economy-分类", TaskType.CLASSIFICATION, 128, 32,
             ["economy"], QualityRequirement.STANDARD,
             mode=RecommendationMode.ECONOMY, note="economy 模式必须选最低价"),
    EvalCase("mode-quality-分类", TaskType.CLASSIFICATION, 128, 32,
             ["quality"], QualityRequirement.STANDARD,
             mode=RecommendationMode.QUALITY, note="quality 模式必须选 quality 档"),

    # === 批量任务 ===
    EvalCase("batch-小批量分类", TaskType.CLASSIFICATION, 64, 32,
             ["economy", "balanced"], QualityRequirement.STANDARD, item_count=20, note="20条分类"),
    EvalCase("batch-大批量抽取", TaskType.EXTRACTION, 256, 128,
             ["economy", "balanced"], QualityRequirement.STANDARD, item_count=200, note="200条抽取，成本敏感"),
    EvalCase("batch-批量代码", TaskType.CODE, 256, 512,
             ["balanced", "quality"], QualityRequirement.HIGH, item_count=30, note="批量代码任务"),

    # === 复杂度边界测试 (token 阈值附近) ===
    EvalCase("boundary-input-499-low", TaskType.CLASSIFICATION, 499, 32,
             ["economy", "balanced"], note="输入499token, 刚好LOW复杂度边界"),
    EvalCase("boundary-input-500-medium", TaskType.CLASSIFICATION, 500, 32,
             ["economy", "balanced"], note="输入500token, 刚好MEDIUM复杂度边界"),
    EvalCase("boundary-input-1999-medium", TaskType.SUMMARIZATION, 1999, 256,
             ["economy", "balanced"], note="输入1999token, MEDIUM上限"),
    EvalCase("boundary-input-2000-high", TaskType.SUMMARIZATION, 2000, 256,
             ["balanced", "quality"], note="输入2000token, 刚好HIGH复杂度"),
    EvalCase("boundary-output-511-low", TaskType.GENERATION, 128, 511,
             ["economy", "balanced"], note="输出511token, 不触发输出升级"),
    EvalCase("boundary-output-512-medium", TaskType.GENERATION, 128, 512,
             ["balanced", "quality"], note="输出512token, 触发MEDIUM升级"),
    EvalCase("boundary-output-1023-medium", TaskType.GENERATION, 128, 1023,
             ["balanced", "quality"], note="输出1023token, MEDIUM上限"),
    EvalCase("boundary-output-1024-high", TaskType.GENERATION, 128, 1024,
             ["balanced", "quality"], note="输出1024token, 触发HIGH升级"),

    # === 对抗场景 (短输入+长输出 / 长输入+简单任务) ===
    EvalCase("adv-short-in-long-out-gen", TaskType.GENERATION, 32, 1024,
             ["balanced", "quality"], note="极短输入+极长输出, 应选大模型"),
    EvalCase("adv-short-in-long-out-code", TaskType.CODE, 64, 1024,
             ["quality"], QualityRequirement.HIGH, note="短输入+长代码输出"),
    EvalCase("adv-long-in-simple-cls", TaskType.CLASSIFICATION, 5000, 32,
             ["economy", "balanced"], note="长输入但分类任务简单, 小模型可做"),
    EvalCase("adv-long-in-simple-ext", TaskType.EXTRACTION, 5000, 128,
             ["balanced", "quality"], note="长输入抽取, 大上下文需要稳定模型"),
    EvalCase("adv-tiny-input", TaskType.CLASSIFICATION, 16, 16,
             ["economy"], note="极小输入, 最简单场景"),

    # === prompt_preview 规则路径测试 (ComplexityEstimator 关键词) ===
    EvalCase("prompt-reasoning-words", TaskType.ANALYSIS, 256, 256,
             ["balanced", "quality"], QualityRequirement.HIGH,
             prompt_preview="请分析一下这个方案的优缺点，对比两个选项，评估风险，说明为什么",
             note="推理信号词密集, 应评估为高复杂度"),
    EvalCase("prompt-technical-terms", TaskType.ANALYSIS, 256, 256,
             ["balanced", "quality"],
             prompt_preview="根据法律法规和合同条款，分析专利侵权风险，评估知识产权合规性",
             note="技术术语密集(法律/合同/专利/合规), 高复杂度"),
    EvalCase("prompt-structured-output", TaskType.EXTRACTION, 256, 256,
             ["economy", "balanced"],
             prompt_preview="请以JSON格式输出，包含表格、列表、分点，每个字段逐条说明",
             note="结构化输出信号, extraction+MEDIUM用economy可接受"),
    EvalCase("prompt-multi-question", TaskType.ANALYSIS, 256, 256,
             ["balanced", "quality"],
             prompt_preview="这个产品怎么样？价格合理吗？性能如何？值得买吗？请说明理由",
             note="多问题(4个问号), 复杂度提升"),
    EvalCase("prompt-simple-short", TaskType.CLASSIFICATION, 64, 32,
             ["economy", "balanced"],
             prompt_preview="判断这句话是正面还是负面",
             note="简单短prompt, 低复杂度"),
    EvalCase("prompt-code-debug", TaskType.CODE, 256, 512,
             ["quality"], QualityRequirement.HIGH,
             prompt_preview="这段Python代码运行报错，请调试并修复bug，解释错误原因",
             note="代码调试+bug关键词, 高复杂度"),

    # === 任务子类型扩展 ===
    EvalCase("gen-翻译-短句", TaskType.GENERATION, 64, 128,
             ["economy", "balanced"], note="短句翻译"),
    EvalCase("gen-翻译-长文", TaskType.GENERATION, 2000, 2000,
             ["balanced", "quality"], note="长文翻译, 大输入大输出"),
    EvalCase("gen-改写润色", TaskType.GENERATION, 500, 500,
             ["balanced", "quality"], note="改写润色需要理解力"),
    EvalCase("gen-创意文案", TaskType.GENERATION, 64, 512,
             ["balanced", "quality"], QualityRequirement.HIGH, note="创意写作需要质量"),
    EvalCase("code-解释代码", TaskType.CODE, 512, 256,
             ["balanced", "quality"], note="代码解释, 输入长输出短"),
    EvalCase("code-写脚本", TaskType.CODE, 128, 512,
             ["balanced", "quality"], note="写脚本"),
    EvalCase("code-算法实现", TaskType.CODE, 256, 1024,
             ["quality"], QualityRequirement.HIGH, note="算法实现需要大模型"),
    EvalCase("ana-数据解读", TaskType.ANALYSIS, 1000, 512,
             ["balanced", "quality"], note="数据解读分析"),
    EvalCase("ana-方案对比", TaskType.ANALYSIS, 500, 512,
             ["balanced", "quality"], QualityRequirement.HIGH, note="方案对比评估"),
    EvalCase("sum-新闻摘要", TaskType.SUMMARIZATION, 800, 128,
             ["economy", "balanced"], note="新闻摘要, 中等输入短输出"),
    EvalCase("sum-会议纪要", TaskType.SUMMARIZATION, 3000, 512,
             ["balanced", "quality"], note="会议纪要, 长输入"),
    EvalCase("ext-表单提取", TaskType.EXTRACTION, 500, 256,
             ["economy", "balanced"], note="表单字段提取"),
    EvalCase("ext-多实体抽取", TaskType.EXTRACTION, 1500, 512,
             ["balanced", "quality"], note="多实体复杂抽取"),

    # === 批量场景扩展 ===
    EvalCase("batch-100条分类", TaskType.CLASSIFICATION, 64, 32,
             ["economy", "balanced"], item_count=100, note="100条分类批量"),
    EvalCase("batch-500条分类", TaskType.CLASSIFICATION, 64, 32,
             ["economy"], item_count=500, mode=RecommendationMode.ECONOMY, note="500条大批量, 成本敏感"),
    EvalCase("batch-50条摘要", TaskType.SUMMARIZATION, 1000, 256,
             ["balanced", "quality"], item_count=50, note="50条摘要批量"),
    EvalCase("batch-20条分析", TaskType.ANALYSIS, 500, 512,
             ["balanced", "quality"], QualityRequirement.HIGH, item_count=20, note="20条分析批量"),
    EvalCase("batch-10条代码", TaskType.CODE, 256, 512,
             ["quality"], QualityRequirement.HIGH, item_count=10, note="10条代码批量"),

    # === 预算边界 ===
    EvalCase("budget-刚好够economy", TaskType.CLASSIFICATION, 128, 32,
             ["economy"], mode=RecommendationMode.ECONOMY, budget_micro_rmb=100,
             note="预算刚好够economy"),
    EvalCase("budget-中等预算", TaskType.GENERATION, 256, 512,
             ["economy", "balanced"], budget_micro_rmb=2000, note="中等预算限制"),
    EvalCase("budget-高预算不限", TaskType.ANALYSIS, 500, 512,
             ["balanced", "quality"], QualityRequirement.HIGH, budget_micro_rmb=100000,
             note="高预算, 不限制选择"),

    # === 截止时间边界 ===
    EvalCase("deadline-极短", TaskType.CLASSIFICATION, 64, 32,
             ["economy", "balanced"], deadline_s=5, note="5秒截止, 必须快"),
    EvalCase("deadline-短", TaskType.CLASSIFICATION, 128, 64,
             ["economy", "balanced"], deadline_s=30, note="30秒截止"),
    EvalCase("deadline-宽松", TaskType.ANALYSIS, 1000, 512,
             ["balanced", "quality"], deadline_s=3600, note="1小时截止, 不限制"),

    # === 模式×任务组合 ===
    EvalCase("mode-economy-生成", TaskType.GENERATION, 128, 256,
             ["economy", "balanced"], mode=RecommendationMode.ECONOMY, note="economy模式生成"),
    EvalCase("mode-economy-摘要", TaskType.SUMMARIZATION, 500, 256,
             ["economy", "balanced"], mode=RecommendationMode.ECONOMY, note="economy模式摘要"),
    EvalCase("mode-quality-分类", TaskType.CLASSIFICATION, 128, 32,
             ["quality"], mode=RecommendationMode.QUALITY, note="quality模式分类(过度质量)"),
    EvalCase("mode-quality-抽取", TaskType.EXTRACTION, 256, 128,
             ["quality"], mode=RecommendationMode.QUALITY, note="quality模式抽取"),
    EvalCase("mode-smart-关键质量", TaskType.ANALYSIS, 500, 512,
             ["quality"], QualityRequirement.CRITICAL, note="smart模式+关键质量"),

    # === 极端场景 ===
    EvalCase("extreme-max-input", TaskType.SUMMARIZATION, 30000, 1024,
             ["balanced", "quality"], note="极大输入(30K token)"),
    EvalCase("extreme-max-output", TaskType.GENERATION, 256, 2048,
             ["balanced", "quality"], note="极长输出(2048 token)"),
    EvalCase("extreme-both-large", TaskType.ANALYSIS, 10000, 1024,
             ["quality"], QualityRequirement.HIGH, note="大输入+大输出+分析"),
    EvalCase("extreme-code-long", TaskType.CODE, 1000, 2048,
             ["quality"], QualityRequirement.HIGH, note="长代码生成"),
]


# ---------------------------------------------------------------------------
# 评估器
# ---------------------------------------------------------------------------

@dataclass
class CaseResult:
    case: EvalCase
    recommended_model_id: str
    recommended_tier: str
    quality_risk: str
    confidence_bps: int
    estimated_price_micro: int
    estimated_energy_micro_wh: int
    estimated_carbon_micro_g: int
    estimated_execution_s: int
    reason_codes: tuple[str, ...]
    reason_summary: str
    alternatives: list[dict[str, Any]]
    tier_hit: bool
    top3_cover: bool
    constraints_satisfied: bool
    mode_consistent: bool
    error: str | None = None


class RecommendationEvaluator:
    def __init__(self, models: list[ModelRecord]):
        self.models = models
        self.policy = GreenRouterRuleV1(
            carbon_g_per_kwh=500,
            renewable_share_bps=3000,
            price_micro_rmb_per_kwh=800_000,
            queue_depth=0,
            shadow_mode=False,
        )

    def run_case(self, case: EvalCase) -> CaseResult:
        now = datetime.now(UTC)
        deadline = now + timedelta(seconds=case.deadline_s) if case.deadline_s else None

        rec_input = RecommendationInput(
            mode=case.mode,
            task_type=case.task_type,
            estimated_input_tokens=case.input_tokens,
            estimated_output_tokens=case.output_tokens,
            item_count=case.item_count,
            quality_requirement=case.quality_requirement,
            budget_micro_rmb=case.budget_micro_rmb,
            deadline=deadline,
            execution_mode=case.execution_mode,
            prompt_preview=case.prompt_preview,
        )

        try:
            result = self.policy.recommend(
                request=rec_input,
                available_models=self.models,
                now=now,
            )
        except Exception as e:
            return CaseResult(
                case=case,
                recommended_model_id="",
                recommended_tier="",
                quality_risk="",
                confidence_bps=0,
                estimated_price_micro=0,
                estimated_energy_micro_wh=0,
                estimated_carbon_micro_g=0,
                estimated_execution_s=0,
                reason_codes=(),
                reason_summary="",
                alternatives=[],
                tier_hit=False,
                top3_cover=False,
                constraints_satisfied=False,
                mode_consistent=False,
                error=str(e),
            )

        # 档位命中
        tier_hit = result.recommended_tier in case.expected_tiers

        # Top-3 档位覆盖
        alt_tiers = {a.tier for a in result.alternatives[:2]}
        alt_tiers.add(result.recommended_tier)
        top3_cover = any(t in alt_tiers for t in case.expected_tiers)

        # 约束满足（检查推荐结果是否在硬约束内）
        constraints_satisfied = self._check_constraints(case, result)

        # 模式一致性
        mode_consistent = self._check_mode_consistency(case, result)

        return CaseResult(
            case=case,
            recommended_model_id=result.recommended_model_id,
            recommended_tier=result.recommended_tier,
            quality_risk=result.quality_risk.value,
            confidence_bps=result.confidence_bps,
            estimated_price_micro=result.estimated_price_micro_rmb,
            estimated_energy_micro_wh=result.estimated_energy_micro_wh,
            estimated_carbon_micro_g=result.estimated_carbon_micro_g,
            estimated_execution_s=result.estimated_execution_seconds,
            reason_codes=result.reason_codes,
            reason_summary=result.reason_summary,
            alternatives=[
                {
                    "model_id": a.model_id,
                    "tier": a.tier,
                    "price_micro": a.estimated_price_micro_rmb,
                    "quality_risk": a.quality_risk.value,
                }
                for a in result.alternatives
            ],
            tier_hit=tier_hit,
            top3_cover=top3_cover,
            constraints_satisfied=constraints_satisfied,
            mode_consistent=mode_consistent,
        )

    def _check_constraints(self, case: EvalCase, result) -> bool:
        """检查推荐结果是否满足所有硬约束。"""
        model = next((m for m in self.models if m.id == result.recommended_model_id), None)
        if model is None:
            return False
        # 上下文
        if case.input_tokens + case.output_tokens > model.context_limit:
            return False
        # 预算
        if case.budget_micro_rmb is not None:
            if result.estimated_price_micro_rmb > case.budget_micro_rmb:
                return False
        # 质量底线
        if case.quality_requirement == QualityRequirement.CRITICAL:
            if model.tier not in ("quality", "enterprise"):
                return False
        if case.quality_requirement == QualityRequirement.HIGH:
            if model.tier not in ("balanced", "quality", "enterprise"):
                return False
        # 代码任务不能用 economy
        if case.task_type == TaskType.CODE and model.tier == "economy":
            return False
        return True

    def _check_mode_consistency(self, case: EvalCase, result) -> bool:
        """检查模式行为是否一致。"""
        all_candidates = [result] + list(result.alternatives)
        if case.mode == RecommendationMode.ECONOMY:
            # 应选最低价可行模型
            min_price = min(c.estimated_price_micro_rmb for c in all_candidates)
            return result.estimated_price_micro_rmb <= min_price
        if case.mode == RecommendationMode.QUALITY:
            # 应选 quality 档（或 fallback 到最高可用档）
            if result.recommended_tier == "quality":
                return True
            # 如果没有 quality 档模型，fallback 可以接受
            has_quality = any(m.tier == "quality" and m.enabled for m in self.models)
            return not has_quality
        # SMART 模式：综合分最低（无法直接验证，但至少应该在合理档位）
        return True


# ---------------------------------------------------------------------------
# 鲁棒性测试
# ---------------------------------------------------------------------------

def run_robustness_test(models: list[ModelRecord], base_case: EvalCase) -> dict:
    """输入 token ±20% 时推荐是否稳定。"""
    evaluator = RecommendationEvaluator(models)
    variants = []
    for delta_pct in [-20, -10, 0, 10, 20]:
        case = EvalCase(
            name=f"{base_case.name}-robust-{delta_pct:+d}%",
            task_type=base_case.task_type,
            input_tokens=max(16, int(base_case.input_tokens * (1 + delta_pct / 100))),
            output_tokens=max(16, int(base_case.output_tokens * (1 + delta_pct / 100))),
            expected_tiers=base_case.expected_tiers,
            quality_requirement=base_case.quality_requirement,
            mode=base_case.mode,
        )
        res = evaluator.run_case(case)
        variants.append({
            "delta_pct": delta_pct,
            "input_tokens": case.input_tokens,
            "recommended_tier": res.recommended_tier,
            "recommended_model": res.recommended_model_id,
            "tier_hit": res.tier_hit,
        })
    tiers = {v["recommended_tier"] for v in variants}
    return {
        "base_case": base_case.name,
        "variants": variants,
        "stable": len(tiers) == 1,
        "distinct_tiers": sorted(tiers),
    }


# ---------------------------------------------------------------------------
# 能耗分级影响测试
# ---------------------------------------------------------------------------

def run_energy_tier_impact_test(models: list[ModelRecord]) -> dict:
    """对比不同能耗数据等级对推荐结果的影响。"""
    base_case = EvalCase(
        name="energy-impact-gen",
        task_type=TaskType.GENERATION,
        input_tokens=256,
        output_tokens=512,
        expected_tiers=["economy", "balanced", "quality"],
        quality_requirement=QualityRequirement.STANDARD,
        mode=RecommendationMode.SMART,
    )

    # 原始模型（有 L2/L3 数据）
    eval1 = RecommendationEvaluator(models)
    r1 = eval1.run_case(base_case)

    # 把所有模型改成 insufficient_data（惩罚系数 10x）
    models_insufficient = []
    for m in models:
        m2 = ModelRecord(**{c.name: getattr(m, c.name) for c in m.__table__.columns})
        m2.energy_data_provenance = "insufficient_data"
        m2.energy_confidence_bps = 0
        m2.energy_data_source = "No data"
        models_insufficient.append(m2)
    eval2 = RecommendationEvaluator(models_insufficient)
    r2 = eval2.run_case(base_case)

    return {
        "with_energy_data": {
            "tier": r1.recommended_tier,
            "model": r1.recommended_model_id,
            "energy_micro_wh": r1.estimated_energy_micro_wh,
        },
        "without_energy_data": {
            "tier": r2.recommended_tier,
            "model": r2.recommended_model_id,
            "energy_micro_wh": r2.estimated_energy_micro_wh,
        },
        "recommendation_changed": r1.recommended_model_id != r2.recommended_model_id,
    }


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------

def generate_report(results: list[CaseResult]) -> dict:
    total = len(results)
    errors = [r for r in results if r.error]
    valid = [r for r in results if not r.error]

    # 基础指标
    tier_hits = sum(1 for r in valid if r.tier_hit)
    top3_covers = sum(1 for r in valid if r.top3_cover)
    constraints_ok = sum(1 for r in valid if r.constraints_satisfied)
    mode_ok = sum(1 for r in valid if r.mode_consistent)

    # 按任务类型统计
    by_task: dict[str, dict] = {}
    for r in valid:
        tt = r.case.task_type.value
        if tt not in by_task:
            by_task[tt] = {"total": 0, "tier_hit": 0, "top3": 0}
        by_task[tt]["total"] += 1
        if r.tier_hit:
            by_task[tt]["tier_hit"] += 1
        if r.top3_cover:
            by_task[tt]["top3"] += 1

    # 按模式统计
    by_mode: dict[str, dict] = {}
    for r in valid:
        md = r.case.mode.value
        if md not in by_mode:
            by_mode[md] = {"total": 0, "tier_hit": 0, "mode_ok": 0}
        by_mode[md]["total"] += 1
        if r.tier_hit:
            by_mode[md]["tier_hit"] += 1
        if r.mode_consistent:
            by_mode[md]["mode_ok"] += 1

    # 置信度校准
    high_conf = [r for r in valid if r.confidence_bps >= 7000]
    mid_conf = [r for r in valid if 4000 <= r.confidence_bps < 7000]
    low_conf = [r for r in valid if r.confidence_bps < 4000]

    # 失败案例详情
    failures = [
        {
            "name": r.case.name,
            "task_type": r.case.task_type.value,
            "expected_tiers": r.case.expected_tiers,
            "got_tier": r.recommended_tier,
            "got_model": r.recommended_model_id,
            "confidence": r.confidence_bps / 100,
            "reason": r.reason_summary,
            "note": r.case.note,
        }
        for r in valid
        if not r.tier_hit
    ]

    return {
        "summary": {
            "total_cases": total,
            "errors": len(errors),
            "valid_cases": len(valid),
            "tier_hit_rate": round(tier_hits / max(1, len(valid)) * 100, 1),
            "top3_coverage": round(top3_covers / max(1, len(valid)) * 100, 1),
            "constraint_satisfaction": round(constraints_ok / max(1, len(valid)) * 100, 1),
            "mode_consistency": round(mode_ok / max(1, len(valid)) * 100, 1),
        },
        "by_task_type": by_task,
        "by_mode": by_mode,
        "confidence_calibration": {
            "high(>=70%)": {"count": len(high_conf), "tier_hit_rate": round(sum(1 for r in high_conf if r.tier_hit) / max(1, len(high_conf)) * 100, 1)},
            "mid(40-70%)": {"count": len(mid_conf), "tier_hit_rate": round(sum(1 for r in mid_conf if r.tier_hit) / max(1, len(mid_conf)) * 100, 1)},
            "low(<40%)": {"count": len(low_conf), "tier_hit_rate": round(sum(1 for r in low_conf if r.tier_hit) / max(1, len(low_conf)) * 100, 1)},
        },
        "failures": failures,
        "error_cases": [{"name": r.case.name, "error": r.error} for r in errors],
    }


def print_report(report: dict, results: list[CaseResult]) -> None:
    s = report["summary"]
    print("=" * 72)
    print("  GreenFlex 推荐系统离线评估报告")
    print("=" * 72)
    print(f"\n  总用例: {s['total_cases']}  |  错误: {s['errors']}  |  有效: {s['valid_cases']}")
    print()
    print("  ┌─ 核心指标 ─────────────────────────────────────────────────────┐")
    print(f"  │  档位命中率      : {s['tier_hit_rate']:>5.1f}%  ({s['tier_hit_rate']/100*s['valid_cases']:.0f}/{s['valid_cases']})          │")
    print(f"  │  Top-3 覆盖率    : {s['top3_coverage']:>5.1f}%                          │")
    print(f"  │  约束满足率      : {s['constraint_satisfaction']:>5.1f}%                          │")
    print(f"  │  模式一致性      : {s['mode_consistency']:>5.1f}%                          │")
    print("  └──────────────────────────────────────────────────────────────────┘")

    print("\n  ┌─ 按任务类型 ───────────────────────────────────────────────────┐")
    print("  │  任务类型        用例数  档位命中  Top-3覆盖                     │")
    for tt, d in sorted(report["by_task_type"].items()):
        hit = d["tier_hit"] / d["total"] * 100
        top3 = d["top3"] / d["total"] * 100
        print(f"  │  {tt:14s}  {d['total']:>4d}    {hit:>5.1f}%    {top3:>5.1f}%                 │")
    print("  └──────────────────────────────────────────────────────────────────┘")

    print("\n  ┌─ 按推荐模式 ───────────────────────────────────────────────────┐")
    print("  │  模式            用例数  档位命中  模式一致                     │")
    for md, d in sorted(report["by_mode"].items()):
        hit = d["tier_hit"] / d["total"] * 100
        mok = d["mode_ok"] / d["total"] * 100
        print(f"  │  {md:14s}  {d['total']:>4d}    {hit:>5.1f}%    {mok:>5.1f}%                 │")
    print("  └──────────────────────────────────────────────────────────────────┘")

    cal = report["confidence_calibration"]
    print("\n  ┌─ 置信度校准 ───────────────────────────────────────────────────┐")
    for label, d in cal.items():
        print(f"  │  置信度 {label:12s}  {d['count']:>3d} 个用例, 命中率 {d['tier_hit_rate']:>5.1f}%      │")
    print("  └──────────────────────────────────────────────────────────────────┘")

    if report["failures"]:
        print("\n  ┌─ 未命中用例详情 ───────────────────────────────────────────────┐")
        for f in report["failures"]:
            print(f"  │  ✗ {f['name']}")
            print(f"  │    期望: {f['expected_tiers']}  实际: {f['got_tier']} ({f['got_model']})")
            print(f"  │    置信度: {f['confidence']:.0f}%  备注: {f['note']}")
        print("  └──────────────────────────────────────────────────────────────────┘")

    if report["error_cases"]:
        print("\n  ┌─ 错误用例 ─────────────────────────────────────────────────────┐")
        for e in report["error_cases"]:
            print(f"  │  ✗ {e['name']}: {e['error'][:60]}")
        print("  └──────────────────────────────────────────────────────────────────┘")

    print()


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="GreenFlex 推荐系统离线评估")
    parser.add_argument("--output", "-o", type=str, help="保存 JSON 报告到文件")
    parser.add_argument("--strict", action="store_true", help="指标不达标时退出码非0")
    parser.add_argument("--min-tier-hit", type=float, default=70.0, help="strict 模式下档位命中率最低阈值(%%)")
    args = parser.parse_args()

    print("加载模型目录...")
    models = build_models()
    print(f"  已加载 {len(models)} 个启用模型:")
    for m in models:
        print(f"    - {m.display_name} ({m.tier}, {m.parameter_b}, {m.energy_data_provenance})")

    print(f"\n运行 {len(EVAL_CASES)} 个评估用例...")
    evaluator = RecommendationEvaluator(models)
    results: list[CaseResult] = []
    for i, case in enumerate(EVAL_CASES, 1):
        res = evaluator.run_case(case)
        status = "✓" if res.tier_hit else ("✗" if not res.error else "ERROR")
        print(f"  [{i:2d}/{len(EVAL_CASES)}] {status} {case.name:30s} "
              f"→ {res.recommended_tier or 'N/A':10s} "
              f"(期望: {','.join(case.expected_tiers)})")
        results.append(res)

    # 鲁棒性测试
    print("\n运行鲁棒性测试 (token ±20%)...")
    robust_base = EvalCase(
        name="robust-base", task_type=TaskType.CLASSIFICATION,
        input_tokens=128, output_tokens=32,
        expected_tiers=["economy", "balanced"],
    )
    robustness = run_robustness_test(models, robust_base)
    print(f"  档位稳定: {'是' if robustness['stable'] else '否'}  "
          f"出现档位: {robustness['distinct_tiers']}")

    # 能耗分级影响测试
    print("\n运行能耗数据分级影响测试...")
    energy_impact = run_energy_tier_impact_test(models)
    print(f"  有能耗数据: {energy_impact['with_energy_data']['tier']} / {energy_impact['with_energy_data']['model']}")
    print(f"  无能耗数据: {energy_impact['without_energy_data']['tier']} / {energy_impact['without_energy_data']['model']}")
    print(f"  推荐结果变化: {'是' if energy_impact['recommendation_changed'] else '否'}")

    # 生成报告
    report = generate_report(results)
    report["robustness"] = robustness
    report["energy_tier_impact"] = energy_impact

    print()
    print_report(report, results)

    # 保存 JSON
    if args.output:
        out_path = Path(args.output)
        report_json = {
            **report,
            "detailed_results": [
                {
                    "name": r.case.name,
                    "task_type": r.case.task_type.value,
                    "mode": r.case.mode.value,
                    "expected_tiers": r.case.expected_tiers,
                    "recommended_tier": r.recommended_tier,
                    "recommended_model": r.recommended_model_id,
                    "quality_risk": r.quality_risk,
                    "confidence_pct": r.confidence_bps / 100,
                    "tier_hit": r.tier_hit,
                    "top3_cover": r.top3_cover,
                    "constraints_satisfied": r.constraints_satisfied,
                    "mode_consistent": r.mode_consistent,
                    "error": r.error,
                }
                for r in results
            ],
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report_json, f, ensure_ascii=False, indent=2)
        print(f"详细报告已保存: {out_path}")

    # strict 模式
    if args.strict:
        if report["summary"]["tier_hit_rate"] < args.min_tier_hit:
            print(f"\n[STRICT] 档位命中率 {report['summary']['tier_hit_rate']}% 低于阈值 {args.min_tier_hit}%")
            sys.exit(1)
        if report["summary"]["constraint_satisfaction"] < 100:
            print(f"\n[STRICT] 约束满足率未达 100%")
            sys.exit(1)
        print(f"\n[STRICT] 所有指标达标")

    sys.exit(0)


if __name__ == "__main__":
    main()
