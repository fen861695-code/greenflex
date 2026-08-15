"""Task classifier for automatic task type detection and model tier recommendation.

MVP stage uses rule-based matching.  A Qwen2.5-based classifier method is
reserved for future implementation.

Enhanced with natural-language intent understanding:
  - Output length hints ("一句话" -> short, "报告/详细" -> long)
  - Batch size hints ("一批/多条/100条" -> item_count)
  - Multi-intent detection (picks the most demanding task type)
  - Human-readable Chinese labels for UI display
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from greenflex.domain import QualityRequirement, TaskType


class ClassifierComplexity(StrEnum):
    """Complexity level assessed by the task classifier."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


# Chinese display labels for task types
TASK_TYPE_LABELS_ZH: dict[TaskType, str] = {
    TaskType.CLASSIFICATION: "分类判断",
    TaskType.EXTRACTION: "信息抽取",
    TaskType.SUMMARIZATION: "摘要总结",
    TaskType.ANALYSIS: "分析推理",
    TaskType.GENERATION: "内容生成",
    TaskType.CODE: "代码编程",
    TaskType.TRANSLATION: "翻译",
    TaskType.GENERAL: "通用任务",
    TaskType.AUTO: "自动识别",
}

COMPLEXITY_LABELS_ZH: dict[ClassifierComplexity, str] = {
    ClassifierComplexity.SIMPLE: "简单",
    ClassifierComplexity.MEDIUM: "中等",
    ClassifierComplexity.COMPLEX: "复杂",
}


@dataclass(frozen=True, slots=True)
class TaskClassification:
    """Result of task classification."""

    task_type: TaskType
    complexity: ClassifierComplexity
    estimated_input_tokens: int
    estimated_output_tokens: int
    requires_json: bool
    recommended_tier: str
    confidence_bps: int
    classifier_version: str
    provenance: str


@dataclass(frozen=True, slots=True)
class TaskUnderstanding:
    """Rich natural-language understanding result for UI display."""

    task_type: TaskType
    task_type_label: str
    complexity: ClassifierComplexity
    complexity_label: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_item_count: int
    output_length_hint: str  # "short" / "medium" / "long"
    requires_json: bool
    recommended_tier: str
    confidence_bps: int
    confidence_label: str
    detected_intents: list[str] = field(default_factory=list)
    reasoning: str = ""
    classifier_version: str = ""
    provenance: str = "rule-based"
    inferred_quality: str = "standard"  # "standard" or "high" from natural language hints


# ---------------------------------------------------------------------------
# Regex patterns for task type detection
#
# Design principle: patterns should match INTENT (action verbs), not just
# nouns.  Standalone nouns like "文章/代码/脚本" are excluded because they
# frequently appear in other task contexts (e.g. "总结这篇文章" is
# summarization, not generation; "解释代码为什么慢" is analysis, not coding).
# ---------------------------------------------------------------------------

# Strong classification signals: these phrases almost always mean classification
_CLASSIFICATION_STRONG = [
    re.compile(r"(情感分析|情感倾向|情绪分析|情感判别|正负面分析|褒贬分析)"),
    re.compile(r"(是不是|是否|有没有)[^，。？?！!]{0,10}(垃圾|违规|色情|暴力|谣言|诈骗|风险|正面|负面|真实|假)"),
    re.compile(r"(判断|判别|判定|识别|检测|区分|辨别).{0,15}(是否|是不是|有没有|真伪|真假|违规|垃圾|风险)"),
]

_CLASSIFICATION_PATTERNS = [
    re.compile(r"\b(classify|categorize|sentiment analysis|label|spam detection|detect)\b", re.I),
    re.compile(
        r"(分类|判断|情感|类别|标签|是否|识别|正负面|褒贬|分一下|分出|分清|区分|归类|好评|差评|正面|负面|"
        r"满意|不满意|投诉|筛选|判别|打分|评级|标注|排序|分级|分成|分为|划分|分组|辨别|归类|"
        r"是不是|真伪|真假|违规|垃圾邮件|风险判断|流失风险)"
    ),
]

_EXTRACTION_PATTERNS = [
    re.compile(r"\b(extract|entities|keywords|named entity|NER|fields?|parse)\b", re.I),
    re.compile(r"(提取|抽取|摘出|抠出|关键词|实体|字段|解析出|找出|列出|识别出|提取出)"),
]

_SUMMARIZATION_STRONG = [
    re.compile(r"(总结|摘要|概括|提炼|归纳|汇总|梳理|浓缩)[一下]?"),
]

_SUMMARIZATION_PATTERNS = [
    re.compile(r"\b(summarize|summary|tldr|key points|abstract|digest)\b", re.I),
    re.compile(r"(总结|摘要|概括|提炼|要点|归纳|整理|汇总|梳理|浓缩|梗概|概要|周报|月报)"),
]

_GENERATION_PATTERNS = [
    re.compile(r"\b(write|generate|create|compose|draft|story|essay|article|blog)\b", re.I),
    # Action-oriented: must have a writing/creating verb
    re.compile(r"(写一[份篇个首封]|写个|写篇|写首|写封|撰写|起草|创作|编写|生成一|来一[篇首封])"),
    re.compile(r"(写)([^，。？!！]*)(文案|文章|故事|诗|邮件|报告|方案|脚本|稿件|推文|标题|标语|宣传语|简介)"),
    # "生成" + content type (excluding AI-generated references)
    re.compile(r"(生成)(\d+|[^，。？!！]{0,6})(条|篇|个|份|段|句|组|套)?[^，。？!！]{0,10}(文案|内容|文本|描述|标题|文章|报告|方案|代码|回复|评论|摘要)"),
]

# Strong generation signals: "写一篇/写一份/写一个" at the start of the request
_GENERATION_STRONG = [
    re.compile(r"(写一[篇份个首封]|帮我写|请写|来一[篇首封]|撰写|起草|创作)"),
]

# Exclusion: if these appear, do NOT count as generation even if "生成" matches
_GENERATION_EXCLUDE = [
    re.compile(r"(AI生成|机器生成|自动生成|是不是生成|是否生成|生成的内容|生成式)"),
]

_ANALYSIS_PATTERNS = [
    re.compile(r"\b(analyze|analysis|evaluate|compare|review|assess|explain why|diagnose)\b", re.I),
    re.compile(
        r"(分析|评估|对比|比较|评价|审查|解释|研究|诊断|排查|原因|为什么|怎么回事|"
        r"趋势|瓶颈|根本原因|优劣|优缺点|可行性|风险评估|性能分析)"
    ),
]

# Exclusion: "诊断结论/诊断结果/诊断报告" are nouns, not analysis intent
_ANALYSIS_EXCLUDE = [
    re.compile(r"(诊断结论|诊断结果|诊断报告|分析报告|评估报告)"),
]

_CODE_PATTERNS = [
    re.compile(r"\b(code|function|class|def |bug|debug|refactor|algorithm|api)\b", re.I),
    re.compile(r"```(python|javascript|typescript|java|c\+\+|go|rust|sql|bash|shell)", re.I),
    # Action-oriented code patterns: verb + tech term
    re.compile(
        r"(写代码|编写程序|写一个?函数|实现一个?|写个?脚本|调试|报错|bug修复|修bug|"
        r"编程|工具类|连接池|写正则|正则表达式|写组件|写模块|部署脚本|运维脚本|爬虫|爬取|"
        r"单例模式|分布式锁|中间件配置|写接口|写API|HTTP中间件)"
    ),
    # "写/实现/用" + programming language/tech
    re.compile(
        r"(写|用|实现|编写|开发|调试|部署)[^，。？!！]{0,10}"
        r"(python|java|javascript|typescript|golang|rust|mysql|postgres|mongodb|redis|"
        r"docker|kubernetes|react|vue|angular|spring|django|flask|fastapi|node\.?js|"
        r"express|tensorflow|pytorch|c\+\+|sql|shell|bash|ruby|php|kotlin|swift)",
        re.I,
    ),
    # "Go" as a standalone language name (not the English word "go")
    re.compile(r"(用|写|实现|编写|开发)[^，。？!！]{0,3}\bGo\b[^，。？!！]{0,10}(写|实现|编写|开发|中间件|服务|接口|程序|代码)"),
    # SQL-specific
    re.compile(r"(写|写一个|编写|实现)[^，。？!！]{0,10}(sql|查询|数据库查询|建表|索引)"),
    re.compile(r"\b(select|insert|update|delete|create table|alter table)\b", re.I),
]

_TRANSLATION_PATTERNS = [
    re.compile(r"\b(translate|translation|in english|in chinese|localize)\b", re.I),
    re.compile(
        r"(翻译成?|翻译一下|帮我翻译|中译英|英译中|中译日|日译中|中译韩|韩译中|"
        r"译成英文|译成中文|译成日文|译为|笔译|口译|译文)"
    ),
]

_TASK_TYPE_RULES: list[tuple[TaskType, list[re.Pattern[str]]]] = [
    (TaskType.CODE, _CODE_PATTERNS),
    (TaskType.TRANSLATION, _TRANSLATION_PATTERNS),
    (TaskType.SUMMARIZATION, _SUMMARIZATION_PATTERNS),
    (TaskType.EXTRACTION, _EXTRACTION_PATTERNS),
    (TaskType.CLASSIFICATION, _CLASSIFICATION_PATTERNS),
    (TaskType.ANALYSIS, _ANALYSIS_PATTERNS),
    (TaskType.GENERATION, _GENERATION_PATTERNS),
]

# Task type priority when multiple intents detected (higher = more demanding)
_TASK_TYPE_PRIORITY: dict[TaskType, int] = {
    TaskType.CODE: 7,
    TaskType.ANALYSIS: 6,
    TaskType.GENERATION: 5,
    TaskType.SUMMARIZATION: 4,
    TaskType.EXTRACTION: 3,
    TaskType.TRANSLATION: 2,
    TaskType.CLASSIFICATION: 1,
    TaskType.GENERAL: 0,
    TaskType.AUTO: 0,
}

# ---------------------------------------------------------------------------
# Natural-language hint patterns
# ---------------------------------------------------------------------------

# Output length hints
_SHORT_OUTPUT_PATTERNS = [
    re.compile(r"(一句话|简短|简要|简单说|几个字|一两句话|简明|简洁)", re.I),
    re.compile(r"\b(one sentence|brief|short|concise|in a few words)\b", re.I),
]

_LONG_OUTPUT_PATTERNS = [
    re.compile(
        r"(详细|详尽|全面|完整|报告|方案|文档|文章|论文|深度|长篇|展开|具体|充分|细致)",
        re.I,
    ),
    re.compile(r"\b(detailed|comprehensive|full report|in depth|thorough|elaborate)\b", re.I),
]

# Batch / item count hints
_BATCH_HINT_PATTERNS = [
    re.compile(r"(\d+)\s*[条个篇份封段道]"),
    re.compile(r"(\d+)\s*(items?|records?|entries|rows|reviews|comments|tickets)", re.I),
    re.compile(r"(一批|一堆|大量|批量|众多|很多|数百|数千|几十|上百|若干|多条|多个)"),
]

_BATCH_LARGE_WORDS = {"一批", "一堆", "大量", "批量", "众多", "很多", "数百", "数千", "上百"}
_BATCH_MEDIUM_WORDS = {"几十", "若干", "多条", "多个"}

# Quality hints from natural language — these indicate the user needs
# high accuracy/correctness, NOT just long output.  "详细/详尽" are
# output-length hints (already in _LONG_OUTPUT_PATTERNS), not quality hints.
_HIGH_QUALITY_PATTERNS = [
    re.compile(
        r"(专业|正式|汇报|老板|客户要求|高要求|严谨|精确|准确|高质量|高标准|务必|必须|"
        r"不能出错|关键任务|核心业务|发布|上线|生产环境|董事会|正式文件|"
        r"法律|合同审查|医疗|用药|安全漏洞|深度)",
        re.I,
    ),
    re.compile(r"\b(professional|formal|critical|important|high.quality|production|must.be.accurate)\b", re.I),
]

# Patterns indicating inherently complex/difficult tasks (bump complexity to MEDIUM)
_COMPLEX_TASK_PATTERNS = [
    re.compile(r"(架构|瓶颈|根本原因|宕机|性能优化|产业链|竞争格局|分布式|高并发)"),
    re.compile(r"(详细|详尽|全面|完整|深度|数据支撑|论证)"),
    re.compile(r"(诊断|排查|评估|评审|审查)[^，。？!！]{0,10}(系统|架构|性能|安全|风险|方案)"),
]

# Patterns indicating multi-class classification (more nuanced than binary)
_MULTICLASS_PATTERNS = [
    re.compile(r"[：:][^，。？!！]*(、|，|,)[^，。？!！]*(、|，|,)"),  # Lists categories with ：
    re.compile(r"(分成|分为|划分|分组|分级)[^，。？!！]*(、|，|,|和)"),  # "分成A、B、C"
]

# ---------------------------------------------------------------------------
# Tier recommendation matrix: (task_type, complexity) -> tier
# ---------------------------------------------------------------------------

_TIER_MATRIX: dict[tuple[TaskType, ClassifierComplexity], str] = {
    (TaskType.CLASSIFICATION, ClassifierComplexity.SIMPLE): "economy",
    (TaskType.CLASSIFICATION, ClassifierComplexity.MEDIUM): "balanced",
    (TaskType.CLASSIFICATION, ClassifierComplexity.COMPLEX): "balanced",
    (TaskType.EXTRACTION, ClassifierComplexity.SIMPLE): "economy",
    (TaskType.EXTRACTION, ClassifierComplexity.MEDIUM): "balanced",
    (TaskType.EXTRACTION, ClassifierComplexity.COMPLEX): "quality",
    (TaskType.SUMMARIZATION, ClassifierComplexity.SIMPLE): "balanced",
    (TaskType.SUMMARIZATION, ClassifierComplexity.MEDIUM): "balanced",
    (TaskType.SUMMARIZATION, ClassifierComplexity.COMPLEX): "quality",
    (TaskType.GENERATION, ClassifierComplexity.SIMPLE): "balanced",
    (TaskType.GENERATION, ClassifierComplexity.MEDIUM): "quality",
    (TaskType.GENERATION, ClassifierComplexity.COMPLEX): "quality",
    (TaskType.ANALYSIS, ClassifierComplexity.SIMPLE): "balanced",
    (TaskType.ANALYSIS, ClassifierComplexity.MEDIUM): "quality",
    (TaskType.ANALYSIS, ClassifierComplexity.COMPLEX): "quality",
    (TaskType.CODE, ClassifierComplexity.SIMPLE): "quality",
    (TaskType.CODE, ClassifierComplexity.MEDIUM): "quality",
    (TaskType.CODE, ClassifierComplexity.COMPLEX): "enterprise",
    (TaskType.TRANSLATION, ClassifierComplexity.SIMPLE): "economy",
    (TaskType.TRANSLATION, ClassifierComplexity.MEDIUM): "balanced",
    (TaskType.TRANSLATION, ClassifierComplexity.COMPLEX): "quality",
    (TaskType.GENERAL, ClassifierComplexity.SIMPLE): "balanced",
    (TaskType.GENERAL, ClassifierComplexity.MEDIUM): "balanced",
    (TaskType.GENERAL, ClassifierComplexity.COMPLEX): "quality",
    (TaskType.AUTO, ClassifierComplexity.SIMPLE): "balanced",
    (TaskType.AUTO, ClassifierComplexity.MEDIUM): "balanced",
    (TaskType.AUTO, ClassifierComplexity.COMPLEX): "quality",
}

_TIER_ORDER = ["economy", "balanced", "quality", "enterprise"]

# Patterns suggesting JSON output requirement
_JSON_PATTERNS = [
    re.compile(r"\b(json|format|schema|structured)\b", re.I),
    re.compile(r"(JSON|格式|结构化|输出为)", re.I),
]

CLASSIFIER_VERSION = "task-classifier-rule-v2"


def _estimate_tokens(text: str) -> int:
    """Estimate token count: Chinese ~1.5 chars/token, English ~4 chars/token."""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - chinese_chars
    return max(1, int(chinese_chars / 1.5) + (other_chars // 4))


class TaskClassifier:
    """Rule-based task classifier (MVP).

    Future: classify_with_qwen25() will use a real Qwen2.5 model for
    more accurate classification.
    """

    def __init__(
        self,
        *,
        use_qwen25_model: bool = False,
        qwen25_model_id: str = "qwen2.5-1.5b-q4",
    ) -> None:
        self._use_qwen25_model = use_qwen25_model
        self._qwen25_model_id = qwen25_model_id

    def classify(
        self,
        prompt: str,
        *,
        item_count: int = 1,
        output_length: str = "medium",
        quality_requirement: QualityRequirement = QualityRequirement.STANDARD,
    ) -> TaskClassification:
        """Classify a task from its prompt text.

        Args:
            prompt: The user's prompt text.
            item_count: Number of items in batch.
            output_length: Expected output length ("short"/"medium"/"long").
            quality_requirement: User-stated quality requirement.

        Returns:
            TaskClassification with task type, complexity, token estimates, etc.
        """
        understanding = self.understand(prompt, item_count=item_count)
        return TaskClassification(
            task_type=understanding.task_type,
            complexity=understanding.complexity,
            estimated_input_tokens=understanding.estimated_input_tokens,
            estimated_output_tokens=understanding.estimated_output_tokens,
            requires_json=understanding.requires_json,
            recommended_tier=understanding.recommended_tier,
            confidence_bps=understanding.confidence_bps,
            classifier_version=CLASSIFIER_VERSION,
            provenance="rule-based",
        )

    def understand(
        self,
        prompt: str,
        *,
        item_count: int = 1,
        quality_requirement: QualityRequirement = QualityRequirement.STANDARD,
    ) -> TaskUnderstanding:
        """Deep natural-language understanding of a user prompt.

        Infers task type, complexity, output length, batch size, and
        returns a human-readable reasoning string for UI display.
        """
        # 1. Detect all matching intents
        detected = self._detect_all_intents(prompt)
        task_type = self._select_primary_intent(detected)

        # 1b. Infer quality requirement from natural language hints
        effective_quality = quality_requirement
        quality_hint = self._infer_quality_hint(prompt)
        if quality_hint == "high" and quality_requirement == QualityRequirement.STANDARD:
            effective_quality = QualityRequirement.HIGH

        # 2. Infer output length from natural language
        output_length = self._infer_output_length(prompt)

        # 3. Infer batch size from natural language
        inferred_items = self._infer_item_count(prompt)
        effective_items = max(item_count, inferred_items)

        # 4. Assess complexity
        complexity = self._assess_complexity(prompt, effective_items, output_length, len(detected))

        # 5. Token estimates
        input_tokens = _estimate_tokens(prompt)
        output_tokens = self._estimate_output_tokens(input_tokens, output_length, task_type)

        # 6. JSON requirement
        requires_json = self._detect_json_requirement(prompt)

        # 7. Recommend tier
        recommended_tier = self._recommend_tier(task_type, complexity, effective_quality)

        # 8. Confidence
        confidence = self._compute_confidence(task_type, complexity, prompt, len(detected))

        # 9. Build reasoning string
        reasoning = self._build_reasoning(
            task_type,
            complexity,
            output_length,
            effective_items,
            output_tokens,
            requires_json,
            detected,
        )

        confidence_label = "高" if confidence >= 7000 else ("中" if confidence >= 4000 else "低")

        return TaskUnderstanding(
            task_type=task_type,
            task_type_label=TASK_TYPE_LABELS_ZH[task_type],
            complexity=complexity,
            complexity_label=COMPLEXITY_LABELS_ZH[complexity],
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_item_count=effective_items,
            output_length_hint=output_length,
            requires_json=requires_json,
            recommended_tier=recommended_tier,
            confidence_bps=confidence,
            confidence_label=confidence_label,
            detected_intents=[TASK_TYPE_LABELS_ZH[t] for t in detected],
            reasoning=reasoning,
            classifier_version=CLASSIFIER_VERSION,
            inferred_quality=quality_hint,
        )

    def classify_with_qwen25(
        self,
        prompt: str,
        *,
        item_count: int = 1,
        output_length: str = "medium",
        quality_requirement: QualityRequirement = QualityRequirement.STANDARD,
    ) -> TaskClassification:
        """Classify using a real Qwen2.5 model (future implementation).

        Currently raises NotImplementedError.  When implemented, this will
        send the prompt to the Qwen2.5 classifier model and parse its
        structured JSON response.
        """
        raise NotImplementedError(
            "Qwen2.5 model classification is not yet implemented. "
            "Use classify() for rule-based classification."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_all_intents(prompt: str) -> list[TaskType]:
        """Detect all matching task types, ordered by priority.

        Uses strong-signal patterns first (high confidence matches),
        then regular patterns with exclusion filters to avoid false
        positives from nouns appearing in other task contexts.
        """
        matches: list[TaskType] = []

        # 1. Check strong classification signals first (highest confidence)
        for pattern in _CLASSIFICATION_STRONG:
            if pattern.search(prompt):
                matches.append(TaskType.CLASSIFICATION)
                break

        # 1b. Strong generation signals: "写一篇/帮我写/撰写" override analysis
        for pattern in _GENERATION_STRONG:
            if pattern.search(prompt):
                matches.append(TaskType.GENERATION)
                break

        # 1c. Strong summarization signals: "总结/概括/梳理" override analysis
        for pattern in _SUMMARIZATION_STRONG:
            if pattern.search(prompt):
                matches.append(TaskType.SUMMARIZATION)
                break

        # 2. Check regular patterns with exclusions
        type_checks = [
            (TaskType.CODE, _CODE_PATTERNS, None),
            (TaskType.TRANSLATION, _TRANSLATION_PATTERNS, None),
            (TaskType.SUMMARIZATION, _SUMMARIZATION_PATTERNS, None),
            (TaskType.EXTRACTION, _EXTRACTION_PATTERNS, None),
            (TaskType.ANALYSIS, _ANALYSIS_PATTERNS, _ANALYSIS_EXCLUDE),
            (TaskType.GENERATION, _GENERATION_PATTERNS, _GENERATION_EXCLUDE),
        ]

        for task_type, patterns, exclusions in type_checks:
            if task_type in matches:
                continue
            matched = False
            for pattern in patterns:
                if pattern.search(prompt):
                    # Check exclusions
                    if exclusions:
                        excluded = any(ex.search(prompt) for ex in exclusions)
                        if excluded:
                            continue
                    matched = True
                    break
            if matched:
                matches.append(task_type)

        # 3. Classification regular patterns (if not already matched by strong)
        if TaskType.CLASSIFICATION not in matches:
            for pattern in _CLASSIFICATION_PATTERNS:
                if pattern.search(prompt):
                    matches.append(TaskType.CLASSIFICATION)
                    break

        if not matches:
            matches.append(TaskType.GENERAL)

        # Strong signals override priority — but CODE always wins because
        # it is the most specific intent (e.g. "用Python写一个排序" is code,
        # not generic generation).
        if TaskType.CODE in matches:
            return [TaskType.CODE] + [t for t in matches if t != TaskType.CODE]

        if TaskType.CLASSIFICATION in matches and any(
            p.search(prompt) for p in _CLASSIFICATION_STRONG
        ):
            return [TaskType.CLASSIFICATION] + [
                t for t in matches if t != TaskType.CLASSIFICATION
            ]
        if TaskType.GENERATION in matches and any(
            p.search(prompt) for p in _GENERATION_STRONG
        ):
            return [TaskType.GENERATION] + [
                t for t in matches if t != TaskType.GENERATION
            ]
        if TaskType.SUMMARIZATION in matches and any(
            p.search(prompt) for p in _SUMMARIZATION_STRONG
        ):
            return [TaskType.SUMMARIZATION] + [
                t for t in matches if t != TaskType.SUMMARIZATION
            ]

        # Sort by priority (highest first)
        matches.sort(key=lambda t: _TASK_TYPE_PRIORITY.get(t, 0), reverse=True)
        return matches

    @staticmethod
    def _select_primary_intent(detected: list[TaskType]) -> TaskType:
        """Pick the most demanding task type from detected intents."""
        return detected[0] if detected else TaskType.GENERAL

    @staticmethod
    def _infer_output_length(prompt: str) -> str:
        """Infer expected output length from natural language hints."""
        for pattern in _SHORT_OUTPUT_PATTERNS:
            if pattern.search(prompt):
                return "short"
        for pattern in _LONG_OUTPUT_PATTERNS:
            if pattern.search(prompt):
                return "long"
        return "medium"

    @staticmethod
    def _infer_item_count(prompt: str) -> int:
        """Infer batch item count from natural language hints."""
        # Check for explicit numbers
        for pattern in _BATCH_HINT_PATTERNS[:2]:
            m = pattern.search(prompt)
            if m:
                try:
                    return max(1, int(m.group(1)))
                except (ValueError, IndexError):
                    pass
        # Check for qualitative batch words
        for pattern in [re.compile(w) for w in _BATCH_LARGE_WORDS]:
            if pattern.search(prompt):
                return 50  # estimated large batch
        for pattern in [re.compile(w) for w in _BATCH_MEDIUM_WORDS]:
            if pattern.search(prompt):
                return 10  # estimated medium batch
        return 1

    @staticmethod
    def _infer_quality_hint(prompt: str) -> str:
        """Infer quality requirement from natural language hints.

        Returns 'high' if words like '深度/汇报/老板/正式/专业' are found,
        otherwise 'standard'.
        """
        for pattern in _HIGH_QUALITY_PATTERNS:
            if pattern.search(prompt):
                return "high"
        return "standard"

    @staticmethod
    def _assess_complexity(
        prompt: str,
        item_count: int,
        output_length: str,
        num_intents: int = 1,
    ) -> ClassifierComplexity:
        # Batch size thresholds
        if item_count > 100:
            return ClassifierComplexity.COMPLEX
        if item_count > 20:
            return ClassifierComplexity.MEDIUM

        # Text length thresholds
        text_len = len(prompt)
        if text_len > 2000:
            return ClassifierComplexity.COMPLEX
        if text_len > 500:
            return ClassifierComplexity.MEDIUM

        # Inherently complex task patterns
        for pattern in _COMPLEX_TASK_PATTERNS:
            if pattern.search(prompt):
                return ClassifierComplexity.MEDIUM

        # Multi-class classification is more demanding than binary
        for pattern in _MULTICLASS_PATTERNS:
            if pattern.search(prompt):
                return ClassifierComplexity.MEDIUM

        # Multi-intent tasks (e.g. "extract then translate") are more complex
        if num_intents >= 2:
            return ClassifierComplexity.MEDIUM

        # Long output requirement bumps complexity
        if output_length == "long":
            return ClassifierComplexity.MEDIUM

        return ClassifierComplexity.SIMPLE

    @staticmethod
    def _estimate_output_tokens(
        input_tokens: int,
        output_length: str,
        task_type: TaskType,
    ) -> int:
        length_multipliers = {
            "short": 0.15,
            "medium": 0.5,
            "long": 1.5,
        }
        multiplier = length_multipliers.get(output_length, 0.5)

        # Code and analysis tasks tend to produce longer outputs
        if task_type == TaskType.CODE:
            multiplier = max(multiplier, 1.0)
        elif task_type == TaskType.ANALYSIS:
            multiplier = max(multiplier, 0.8)
        elif task_type == TaskType.GENERATION:
            multiplier = max(multiplier, 0.8)
        elif task_type == TaskType.SUMMARIZATION:
            multiplier = max(multiplier, 0.4)
        elif task_type == TaskType.CLASSIFICATION:
            multiplier = min(multiplier, 0.15)

        # Ensure reasonable minimums based on output length
        base_min = {"short": 32, "medium": 128, "long": 512}
        estimated = max(base_min[output_length], int(input_tokens * multiplier))
        # Cap at 4096 for safety
        return min(4096, estimated)

    @staticmethod
    def _detect_json_requirement(prompt: str) -> bool:
        return any(p.search(prompt) for p in _JSON_PATTERNS)

    @staticmethod
    def _recommend_tier(
        task_type: TaskType,
        complexity: ClassifierComplexity,
        quality_requirement: QualityRequirement,
    ) -> str:
        tier = _TIER_MATRIX.get((task_type, complexity), "balanced")

        # High/critical quality requirement bumps up one tier
        if quality_requirement in (QualityRequirement.HIGH, QualityRequirement.CRITICAL):
            idx = _TIER_ORDER.index(tier)
            if idx < len(_TIER_ORDER) - 1:
                tier = _TIER_ORDER[idx + 1]

        return tier

    @staticmethod
    def _compute_confidence(
        task_type: TaskType,
        complexity: ClassifierComplexity,
        prompt: str,
        num_intents: int,
    ) -> int:
        # Base confidence
        confidence = 7000

        # Short prompts reduce confidence
        if len(prompt) < 10:
            confidence -= 2000
        elif len(prompt) < 20:
            confidence -= 1000
        elif len(prompt) < 50:
            confidence -= 500

        # General/auto type has lower confidence
        if task_type in (TaskType.GENERAL, TaskType.AUTO):
            confidence -= 2000
            # Very short + general = very low confidence
            if len(prompt) < 15:
                confidence -= 1000

        # Complex tasks are harder to classify confidently
        if complexity == ClassifierComplexity.COMPLEX:
            confidence -= 500

        # Multiple intents detected — slightly lower confidence on primary
        if num_intents > 1:
            confidence -= 300

        return max(1000, min(9500, confidence))

    @staticmethod
    def _build_reasoning(
        task_type: TaskType,
        complexity: ClassifierComplexity,
        output_length: str,
        item_count: int,
        output_tokens: int,
        requires_json: bool,
        detected: list[TaskType],
    ) -> str:
        parts: list[str] = []

        # Task type description
        type_desc = TASK_TYPE_LABELS_ZH[task_type]
        if len(detected) > 1:
            other = "、".join(TASK_TYPE_LABELS_ZH[t] for t in detected[1:])
            parts.append(f"识别到复合任务（{type_desc}为主，含{other}）")
        else:
            parts.append(f"任务类型：{type_desc}")

        # Complexity
        parts.append(f"复杂度：{COMPLEXITY_LABELS_ZH[complexity]}")

        # Output length
        length_desc = {"short": "简短输出", "medium": "中等输出", "long": "详细输出"}
        parts.append(length_desc.get(output_length, "中等输出"))

        # Batch
        if item_count > 1:
            parts.append(f"批量约 {item_count} 条")

        # JSON
        if requires_json:
            parts.append("需要结构化输出")

        return "；".join(parts)
