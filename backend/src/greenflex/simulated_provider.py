"""Simulated inference provider for demo and development without GPU/Ollama.

Generates deterministic placeholder outputs based on prompt hash and model tier.
Does NOT connect to any real model or GPU.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import re
from dataclasses import dataclass

from greenflex.domain import TaskType
from greenflex.ports import GenerationRequest, GenerationResult, InferenceProvider

# ---------------------------------------------------------------------------
# Task type detection patterns (regex-based, MVP)
# ---------------------------------------------------------------------------

_TASK_PATTERNS: tuple[tuple[TaskType, list[re.Pattern[str]]], ...] = (
    (
        TaskType.CODE,
        [
            re.compile(r"\b(code|function|class|def |bug|debug|refactor|algorithm)\b", re.I),
            re.compile(r"```(python|javascript|typescript|java|c\+\+|go|rust|sql)", re.I),
            re.compile(r"(写代码|编写程序|代码|函数|调试|报错|bug|算法)", re.I),
        ],
    ),
    (
        TaskType.TRANSLATION,
        [
            re.compile(r"\b(translate|translation|in english|in chinese|译成|翻译)\b", re.I),
            re.compile(r"(翻译成|英文|中文|日语|韩语)", re.I),
        ],
    ),
    (
        TaskType.SUMMARIZATION,
        [
            re.compile(r"\b(summarize|summary|tldr|key points|abstract)\b", re.I),
            re.compile(r"(总结|摘要|概括|提炼|要点)", re.I),
        ],
    ),
    (
        TaskType.EXTRACTION,
        [
            re.compile(r"\b(extract|entities|keywords|named entity|NER|fields?)\b", re.I),
            re.compile(r"(提取|抽取|关键词|实体|字段)", re.I),
        ],
    ),
    (
        TaskType.CLASSIFICATION,
        [
            re.compile(r"\b(classify|categorize|sentiment|label|category|spam)\b", re.I),
            re.compile(r"(分类|判断|情感|类别|标签|是否)", re.I),
        ],
    ),
    (
        TaskType.ANALYSIS,
        [
            re.compile(r"\b(analyze|analysis|evaluate|compare|review|assess)\b", re.I),
            re.compile(r"(分析|评估|对比|比较|评价|审查)", re.I),
        ],
    ),
    (
        TaskType.GENERATION,
        [
            re.compile(r"\b(write|generate|create|compose|draft|story|essay|article)\b", re.I),
            re.compile(r"(写|生成|创作|撰写|起草|文章|故事)", re.I),
        ],
    ),
)


def detect_task_type(prompt: str) -> TaskType:
    """Detect task type from prompt text using regex patterns."""
    for task_type, patterns in _TASK_PATTERNS:
        for pattern in patterns:
            if pattern.search(prompt):
                return task_type
    return TaskType.GENERAL


# ---------------------------------------------------------------------------
# Tier-based simulation parameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _TierProfile:
    base_latency_ms: int
    ms_per_output_token: float
    output_token_ratio: float  # output / input token ratio
    placeholder: str


_TIER_PROFILES: dict[str, _TierProfile] = {
    "economy": _TierProfile(
        base_latency_ms=80,
        ms_per_output_token=5.0,
        output_token_ratio=0.3,
        placeholder="[模拟输出] 经济档模型已处理请求。",
    ),
    "balanced": _TierProfile(
        base_latency_ms=150,
        ms_per_output_token=9.0,
        output_token_ratio=0.5,
        placeholder="[模拟输出] 均衡档模型已处理请求。",
    ),
    "quality": _TierProfile(
        base_latency_ms=300,
        ms_per_output_token=18.0,
        output_token_ratio=0.8,
        placeholder="[模拟输出] 质量档模型已处理请求。",
    ),
    "enterprise": _TierProfile(
        base_latency_ms=600,
        ms_per_output_token=35.0,
        output_token_ratio=1.2,
        placeholder="[模拟输出] 企业档模型已处理请求。",
    ),
}

# Fallback profile for unknown tiers
_DEFAULT_PROFILE = _TIER_PROFILES["balanced"]


def _estimate_prompt_tokens(prompt: str) -> int:
    """Rough token estimate: Chinese ~1.5 chars/token, English ~4 chars/token."""
    if not prompt:
        return 0
    chinese_chars = sum(1 for c in prompt if "\u4e00" <= c <= "\u9fff")
    other_chars = len(prompt) - chinese_chars
    tokens = int(chinese_chars / 1.5) + (other_chars // 4)
    return max(1, tokens)


class SimulatedInferenceProvider:
    """Inference provider that returns deterministic simulated results.

    No GPU, Ollama, or network required.  Output is a placeholder string
    seeded by the MD5 hash of the prompt so identical inputs produce
    identical outputs.
    """

    source = "simulated"

    def __init__(
        self,
        *,
        latency_factor: float = 1.0,
        enable_random_variation: bool = True,
    ) -> None:
        self._latency_factor = latency_factor
        self._enable_random_variation = enable_random_variation

    async def available_models(self) -> dict[str, str]:
        """Return empty dict — simulated provider has no real installed models."""
        return {}

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Return a simulated generation result with realistic latency."""
        # Determine tier from model name (e.g. "qwen2.5:0.5b" -> economy by default)
        tier = self._infer_tier(request.model_name)
        profile = _TIER_PROFILES.get(tier, _DEFAULT_PROFILE)

        # Detect task type for richer output
        task_type = detect_task_type(request.prompt)

        # Deterministic seed from prompt hash (MD5 is fine for non-security seeding)
        prompt_hash = hashlib.md5(request.prompt.encode("utf-8")).hexdigest()  # noqa: S324
        seed = int(prompt_hash[:8], 16)
        rng = random.Random(seed)  # noqa: S311

        # Estimate tokens
        prompt_tokens = _estimate_prompt_tokens(request.prompt)
        output_tokens = min(
            request.max_output_tokens,
            max(8, int(prompt_tokens * profile.output_token_ratio)),
        )

        # Build placeholder output with task-specific prefix
        output = self._build_output(
            profile.placeholder,
            task_type,
            prompt_hash[:12],
            output_tokens,
            rng,
        )

        # Simulate latency with ±15% random variation
        latency_ms = profile.base_latency_ms + profile.ms_per_output_token * output_tokens
        latency_ms = int(latency_ms * self._latency_factor)
        if self._enable_random_variation:
            variation = rng.uniform(0.85, 1.15)
            latency_ms = int(latency_ms * variation)
        latency_ms = max(10, latency_ms)

        await asyncio.sleep(latency_ms / 1000.0)

        return GenerationResult(
            output=output,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            duration_us=latency_ms * 1000,
            source="simulated",
        )

    @staticmethod
    def _infer_tier(model_name: str) -> str:
        """Infer model tier from model name heuristics."""
        name = model_name.lower()
        # Cloud models: infer from runtime prefix or known IDs
        if "gpt-o3" in name or "opus-thinking" in name or "deepseek-r1" in name:
            return "enterprise"
        if "gpt-5-pro" in name or "opus" in name or "gemini-ultra" in name or "qwen-max" in name:
            return "enterprise"
        if "gpt-5" in name or "sonnet" in name or "gemini-pro" in name or "deepseek-v3" in name:
            return "quality"
        if "gpt-4o" in name or "haiku" in name or "gemini-flash" in name or "qwen-plus" in name:
            return "balanced"
        if "mini" in name or "lite" in name or "turbo" in name or "flash-lite" in name:
            return "economy"
        # Local models: infer from parameter size
        size_match = re.search(r"(\d+(?:\.\d+)?)\s*b", name)
        if size_match:
            params = float(size_match.group(1))
            if params <= 1.5:
                return "economy"
            if params <= 4:
                return "balanced"
            if params <= 14:
                return "quality"
            return "enterprise"
        return "balanced"

    @staticmethod
    def _build_output(
        placeholder: str,
        task_type: TaskType,
        hash_prefix: str,
        output_tokens: int,
        rng: random.Random,
    ) -> str:
        """Build a deterministic placeholder output string."""
        task_labels = {
            TaskType.CLASSIFICATION: "任务类型: 分类",
            TaskType.EXTRACTION: "任务类型: 抽取",
            TaskType.SUMMARIZATION: "任务类型: 摘要",
            TaskType.ANALYSIS: "任务类型: 分析",
            TaskType.GENERATION: "任务类型: 生成",
            TaskType.CODE: "任务类型: 代码",
            TaskType.TRANSLATION: "任务类型: 翻译",
            TaskType.GENERAL: "任务类型: 通用",
            TaskType.AUTO: "任务类型: 自动",
        }
        label = task_labels.get(task_type, "任务类型: 未知")
        # Pad output to roughly match output_tokens (Chinese ~1.5 chars/token)
        target_chars = int(output_tokens * 1.5)
        suffix = f" (hash:{hash_prefix})"
        content = placeholder
        while len(content) < target_chars:
            content += " 这是模拟推理生成的占位内容，用于演示和测试。"
        content = content[:target_chars]
        return f"{label}\n{content}{suffix}"


# Static structural check: SimulatedInferenceProvider satisfies InferenceProvider
_provider: type[InferenceProvider] = SimulatedInferenceProvider
