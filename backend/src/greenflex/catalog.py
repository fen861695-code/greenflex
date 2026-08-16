from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from greenflex.models import ModelRecord

MODEL_SEED_VERSION = "model-catalog-v3"

# Data file paths
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_BENCHMARK_FILE = _DATA_DIR / "benchmarks" / "model-energy-bench-v1.json"


def _load_benchmark_data() -> dict[str, object]:
    """Load benchmark data from local JSON file."""
    if _BENCHMARK_FILE.exists():
        with open(_BENCHMARK_FILE, encoding="utf-8") as f:
            data: dict[str, object] = json.load(f)
            return data
    return {}


def _wh_to_micro_wh(wh_per_1k: float) -> int:
    """Convert Wh/1k tokens to micro-Wh/1k tokens."""
    return int(wh_per_1k * 1_000_000)


# Energy values from data/benchmarks/model-energy-bench-v1.json
# Source: arXiv 2608.00008 (RTX 4060 Ti, Q4), arXiv 2607.26571 (H100 FP16)
# Values are conservative for consumer laptop GPUs (RTX 4050/4060 class)
# Pricing is simulated local pricing (no cloud API costs for local models)
MODEL_SEEDS = (
    # === Economy tier: sub-2B models, fast and efficient ===
    {
        "id": "qwen2.5-0.5b-q4",
        "runtime_name": "qwen2.5:0.5b",
        "display_name": "Qwen2.5 0.5B (任务分类器)",
        "tier": "economy",
        "parameter_b": "0.5B",
        "context_limit": 32_768,
        "recommended_for_json": json.dumps(
            ["任务分类", "意图识别", "复杂度判断"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 50_000,
        "output_rate_micro_rmb_per_million": 150_000,
        "estimated_tokens_per_second": 200,
        "estimated_energy_micro_wh_per_1k_output": 100_000,  # 0.10 Wh/1k conservative
        "recommended_batch_size": 8,
        "enabled": False,
        "is_task_classifier": True,
        "official_data_source": (
            "Qwen2.5 官方技术报告 https://qwenlm.github.io/blog/qwen2.5/ ; "
            "实测基准 JouleBench (arXiv 2608.00008)"
        ),
    },
    {
        "id": "gemma3-1b-q4",
        "runtime_name": "gemma3:1b",
        "display_name": "Gemma 3 1B",
        "tier": "economy",
        "parameter_b": "1B",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(
            ["短文本分类", "实体抽取", "简单问答"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 80_000,
        "output_rate_micro_rmb_per_million": 240_000,
        "estimated_tokens_per_second": 180,
        "estimated_energy_micro_wh_per_1k_output": 180_000,  # 0.18 Wh/1k (measured 0.154)
        "recommended_batch_size": 6,
        "enabled": True,
        # data_provenance: measured
        # source_note: RTX 4060 Ti: 0.556 J/token = 0.154 Wh/1k, 207.7 tok/s
    },
    {
        "id": "llama3.2-1b-q4",
        "runtime_name": "llama3.2:1b",
        "display_name": "Llama 3.2 1B",
        "tier": "economy",
        "parameter_b": "1B",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(
            ["简单摘要", "格式转换", "关键词提取"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 80_000,
        "output_rate_micro_rmb_per_million": 240_000,
        "estimated_tokens_per_second": 150,
        "estimated_energy_micro_wh_per_1k_output": 200_000,  # 0.20 Wh/1k (measured 0.180)
        "recommended_batch_size": 6,
        "enabled": True,
        # data_provenance: measured
        # source_note: RTX 4060 Ti: 0.647 J/token = 0.180 Wh/1k, 173 tok/s
    },
    # === Balanced tier: 2-4B models, good quality/efficiency tradeoff ===
    {
        "id": "qwen2.5-1.5b-q4",
        "runtime_name": "qwen2.5:1.5b",
        "display_name": "Qwen2.5 1.5B (任务分类器)",
        "tier": "balanced",
        "parameter_b": "1.5B",
        "context_limit": 32_768,
        "recommended_for_json": json.dumps(
            ["任务分类", "意图识别", "复杂度判断", "路由决策"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 200_000,
        "output_rate_micro_rmb_per_million": 600_000,
        "estimated_tokens_per_second": 110,
        "estimated_energy_micro_wh_per_1k_output": 280_000,  # 0.28 Wh/1k (interpolated)
        "recommended_batch_size": 4,
        "enabled": False,
        "is_task_classifier": True,
        "official_data_source": (
            "Qwen2.5 官方技术报告 https://qwenlm.github.io/blog/qwen2.5/ ; "
            "实测基准 JouleBench (arXiv 2608.00008)"
        ),
    },
    {
        "id": "gemma4-e2b-q4",
        "runtime_name": "gemma4:e2b",
        "display_name": "Gemma 4 E2B",
        "tier": "balanced",
        "parameter_b": "2B",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(
            ["推理任务", "多步分析", "边缘部署"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 250_000,
        "output_rate_micro_rmb_per_million": 750_000,
        "estimated_tokens_per_second": 100,
        "estimated_energy_micro_wh_per_1k_output": 350_000,  # 0.35 Wh/1k (measured 0.304)
        "recommended_batch_size": 4,
        "enabled": True,
        # data_provenance: measured
        # source_note: RTX 4060 Ti: 1.093 J/token = 0.304 Wh/1k, 114 tok/s
    },
    {
        "id": "llama3.2-3b-q4",
        "runtime_name": "llama3.2:3b",
        "display_name": "Llama 3.2 3B",
        "tier": "balanced",
        "parameter_b": "3B",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(
            ["内容创作", "逻辑推理", "代码解释"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 350_000,
        "output_rate_micro_rmb_per_million": 1_000_000,
        "estimated_tokens_per_second": 95,
        "estimated_energy_micro_wh_per_1k_output": 380_000,  # 0.38 Wh/1k (measured 0.340)
        "recommended_batch_size": 2,
        "enabled": True,
        # data_provenance: measured
        # source_note: RTX 4060 Ti: 1.225 J/token = 0.340 Wh/1k, 112.4 tok/s
    },
    {
        "id": "qwen2.5-3b-q4",
        "runtime_name": "qwen2.5:3b",
        "display_name": "Qwen2.5 3B",
        "tier": "balanced",
        "parameter_b": "3B",
        "context_limit": 32_768,
        "recommended_for_json": json.dumps(
            ["复杂摘要", "多步分析", "高质量生成", "中文任务"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 400_000,
        "output_rate_micro_rmb_per_million": 1_100_000,
        "estimated_tokens_per_second": 90,
        "estimated_energy_micro_wh_per_1k_output": 400_000,  # 0.40 Wh/1k (measured 0.348)
        "recommended_batch_size": 2,
        "enabled": True,
        # data_provenance: measured
        # source_note: RTX 4060 Ti: 1.252 J/token = 0.348 Wh/1k, 107.8 tok/s
    },
    {
        "id": "phi4-mini-3.8b-q4",
        "runtime_name": "phi4-mini:3.8b",
        "display_name": "Phi-4 Mini 3.8B",
        "tier": "balanced",
        "parameter_b": "3.8B",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(
            ["推理任务", "数学问题", "逻辑分析"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 450_000,
        "output_rate_micro_rmb_per_million": 1_300_000,
        "estimated_tokens_per_second": 75,
        "estimated_energy_micro_wh_per_1k_output": 480_000,  # 0.48 Wh/1k (measured 0.443)
        "recommended_batch_size": 2,
        "enabled": True,
        # data_provenance: measured
        # source_note: RTX 4060 Ti: 1.595 J/token = 0.443 Wh/1k, 86.5 tok/s
    },
    # === Quality tier: 7-14B models, requires 8-10GB VRAM ===
    {
        "id": "gemma3-4b-q4",
        "runtime_name": "gemma3:4b",
        "display_name": "Gemma 3 4B",
        "tier": "quality",
        "parameter_b": "4B",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(
            ["长文理解", "复杂推理", "多模态任务"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 500_000,
        "output_rate_micro_rmb_per_million": 1_500_000,
        "estimated_tokens_per_second": 70,
        "estimated_energy_micro_wh_per_1k_output": 500_000,  # 0.50 Wh/1k (measured 0.464)
        "recommended_batch_size": 2,
        "enabled": True,
        # data_provenance: measured
        # source_note: RTX 4060 Ti: 1.671 J/token = 0.464 Wh/1k, 78.5 tok/s
    },
    {
        "id": "mistral-7b-q4",
        "runtime_name": "mistral:7b",
        "display_name": "Mistral 7B",
        "tier": "quality",
        "parameter_b": "7B",
        "context_limit": 32_768,
        "recommended_for_json": json.dumps(
            ["通用对话", "文本生成", "知识密集型任务"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 700_000,
        "output_rate_micro_rmb_per_million": 2_000_000,
        "estimated_tokens_per_second": 50,
        "estimated_energy_micro_wh_per_1k_output": 750_000,  # 0.75 Wh/1k (measured 0.690)
        "recommended_batch_size": 1,
        "enabled": True,
        # data_provenance: measured
        # source_note: RTX 4060 Ti: 2.485 J/token = 0.690 Wh/1k, 55.1 tok/s
    },
    {
        "id": "qwen2.5-7b-q4",
        "runtime_name": "qwen2.5:7b",
        "display_name": "Qwen2.5 7B",
        "tier": "quality",
        "parameter_b": "7B",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(
            ["高质量写作", "代码生成", "深度分析", "中文优化"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 800_000,
        "output_rate_micro_rmb_per_million": 2_200_000,
        "estimated_tokens_per_second": 45,
        "estimated_energy_micro_wh_per_1k_output": 800_000,  # 0.80 Wh/1k (interpolated)
        "recommended_batch_size": 1,
        "enabled": True,
        # data_provenance: interpolated
        # source_note: Interpolated from mistral:7b same hardware class; Qwen family more efficient
    },
    {
        "id": "llama3.1-8b-q4",
        "runtime_name": "llama3.1:8b",
        "display_name": "Llama 3.1 8B",
        "tier": "quality",
        "parameter_b": "8B",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(
            ["复杂推理", "长文生成", "通用任务"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 900_000,
        "output_rate_micro_rmb_per_million": 2_500_000,
        "estimated_tokens_per_second": 40,
        "estimated_energy_micro_wh_per_1k_output": 850_000,  # 0.85 Wh/1k (interpolated)
        "recommended_batch_size": 1,
        "enabled": True,
        # data_provenance: interpolated
        # source_note: Requires ~6GB VRAM for Q4; may offload on 8GB cards
    },
    {
        "id": "qwen2.5-14b-q4",
        "runtime_name": "qwen2.5:14b",
        "display_name": "Qwen2.5 14B",
        "tier": "quality",
        "parameter_b": "14B",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(
            ["专业写作", "复杂代码", "深度推理", "企业级任务"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 1_500_000,
        "output_rate_micro_rmb_per_million": 4_000_000,
        "estimated_tokens_per_second": 22,
        "estimated_energy_micro_wh_per_1k_output": 1_500_000,  # 1.5 Wh/1k (interpolated)
        "recommended_batch_size": 1,
        "enabled": False,  # Disabled by default; requires 10GB+ VRAM
        # data_provenance: interpolated
        # source_note: Requires ~10GB VRAM for Q4; enable if you have sufficient GPU memory
    },
    # === Enterprise tier: 32B+ models, requires datacenter or multi-GPU ===
    {
        "id": "qwen3-32b-q4",
        "runtime_name": "qwen3:32b",
        "display_name": "Qwen3 32B",
        "tier": "enterprise",
        "parameter_b": "32B",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(
            ["企业级部署", "高难度推理", "专业领域"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 4_000_000,
        "output_rate_micro_rmb_per_million": 10_000_000,
        "estimated_tokens_per_second": 10,
        "estimated_energy_micro_wh_per_1k_output": 3_000_000,  # 3.0 Wh/1k consumer
        "recommended_batch_size": 1,
        "enabled": False,
        # data_provenance: analytical
        # source_note: H100 FP16: 99.8 mJ/token = 27.7 Wh/1k; Q4 consumer ~3 Wh/1k
    },
    {
        "id": "llama3.3-70b-q4",
        "runtime_name": "llama3.3:70b",
        "display_name": "Llama 3.3 70B",
        "tier": "enterprise",
        "parameter_b": "70B",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(
            ["最复杂任务", "研究级推理", "旗舰质量"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 8_000_000,
        "output_rate_micro_rmb_per_million": 20_000_000,
        "estimated_tokens_per_second": 4,
        "estimated_energy_micro_wh_per_1k_output": 6_500_000,  # 6.5 Wh/1k consumer Q4
        "recommended_batch_size": 1,
        "enabled": False,
        # data_provenance: analytical
        # source_note: H100 FP16: 218.4 mJ/token = 60.7 Wh/1k; requires multi-GPU for consumer
    },
)

# ============================================================================
# Cloud API production models (reference/benchmark)
# Source: data/benchmarks/cloud-production-models-v1.json
# These represent what AI vendors ACTUALLY deploy in production (H100/H200/B200)
# They are disabled by default for local inference but can be used for:
#   - Cost/energy comparison with local models
#   - Cloud routing (if API keys configured)
#   - Reference benchmarks
# Energy values include PUE 1.2 datacenter overhead
# Pricing: USD -> micro-RMB at ~7.2 CNY/USD (simulated)
# ============================================================================

# USD to micro-RMB conversion: 1 USD = 7.2 CNY = 7,200,000 micro-RMB
_USD_TO_MICRO_RMB = 7_200_000

CLOUD_MODEL_SEEDS = (
    # === Frontier reasoning models (most capable, highest energy) ===
    {
        "id": "cloud-openai-gpt-o3-ultra",
        "runtime_name": "cloud:openai/gpt-o3-ultra",
        "display_name": "[云API] GPT-o3 Ultra (推理)",
        "tier": "enterprise",
        "parameter_b": "~1.8T MoE",
        "context_limit": 200_000,
        "recommended_for_json": json.dumps(
            ["最复杂推理", "数学证明", "科学研究"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 15 * _USD_TO_MICRO_RMB,
        "output_rate_micro_rmb_per_million": 60 * _USD_TO_MICRO_RMB,
        "estimated_tokens_per_second": 30,
        "estimated_energy_micro_wh_per_1k_output": 23_800_000,  # 23.8 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-anthropic-opus-thinking",
        "runtime_name": "cloud:anthropic/claude-opus-thinking",
        "display_name": "[云API] Claude Opus Thinking",
        "tier": "enterprise",
        "parameter_b": "~400B Dense",
        "context_limit": 1_000_000,
        "recommended_for_json": json.dumps(
            ["深度推理", "法律分析", "医疗诊断"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 15 * _USD_TO_MICRO_RMB,
        "output_rate_micro_rmb_per_million": 75 * _USD_TO_MICRO_RMB,
        "estimated_tokens_per_second": 25,
        "estimated_energy_micro_wh_per_1k_output": 19_600_000,  # 19.6 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-deepseek-r1",
        "runtime_name": "cloud:deepseek/deepseek-r1",
        "display_name": "[云API] DeepSeek-R1 (推理)",
        "tier": "enterprise",
        "parameter_b": "671B MoE/37B active",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(["推理任务", "代码", "数学"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(0.55 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": int(2.19 * _USD_TO_MICRO_RMB),
        "estimated_tokens_per_second": 40,
        "estimated_energy_micro_wh_per_1k_output": 5_000_000,  # 5.0 Wh/1k
        "enabled": True,
    },
    # === Frontier general models ===
    {
        "id": "cloud-openai-gpt-5-pro",
        "runtime_name": "cloud:openai/gpt-5-pro",
        "display_name": "[云API] GPT-5 Pro",
        "tier": "enterprise",
        "parameter_b": "~800B MoE",
        "context_limit": 400_000,
        "recommended_for_json": json.dumps(["旗舰质量", "企业级", "多模态"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": 2 * _USD_TO_MICRO_RMB,
        "output_rate_micro_rmb_per_million": 8 * _USD_TO_MICRO_RMB,
        "estimated_tokens_per_second": 60,
        "estimated_energy_micro_wh_per_1k_output": 2_600_000,  # 2.6 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-anthropic-opus",
        "runtime_name": "cloud:anthropic/claude-opus",
        "display_name": "[云API] Claude Opus 4.6",
        "tier": "enterprise",
        "parameter_b": "~400B Dense",
        "context_limit": 1_000_000,
        "recommended_for_json": json.dumps(
            ["长文写作", "深度分析", "安全合规"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 5 * _USD_TO_MICRO_RMB,
        "output_rate_micro_rmb_per_million": 25 * _USD_TO_MICRO_RMB,
        "estimated_tokens_per_second": 50,
        "estimated_energy_micro_wh_per_1k_output": 7_000_000,  # 7.0 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-google-gemini-ultra",
        "runtime_name": "cloud:google/gemini-ultra",
        "display_name": "[云API] Gemini 3.1 Ultra",
        "tier": "enterprise",
        "parameter_b": "~1.5T MoE",
        "context_limit": 2_000_000,
        "recommended_for_json": json.dumps(
            ["超长上下文", "多模态", "百万token"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 4 * _USD_TO_MICRO_RMB,
        "output_rate_micro_rmb_per_million": 16 * _USD_TO_MICRO_RMB,
        "estimated_tokens_per_second": 55,
        "estimated_energy_micro_wh_per_1k_output": 7_400_000,  # 7.4 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-qwen-max",
        "runtime_name": "cloud:alibaba/qwen-max",
        "display_name": "[云API] 通义千问 Max",
        "tier": "enterprise",
        "parameter_b": "~1T MoE",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(["中文旗舰", "企业应用", "多模态"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(1.6 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": int(6.4 * _USD_TO_MICRO_RMB),
        "estimated_tokens_per_second": 55,
        "estimated_energy_micro_wh_per_1k_output": 1_050_000,  # 1.05 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-doubao-pro",
        "runtime_name": "cloud:bytedance/doubao-pro",
        "display_name": "[云API] 豆包 Pro 1.5",
        "tier": "enterprise",
        "parameter_b": "~800B MoE",
        "context_limit": 256_000,
        "recommended_for_json": json.dumps(["中文优化", "高并发", "多模态"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(0.7 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": int(2.0 * _USD_TO_MICRO_RMB),
        "estimated_tokens_per_second": 60,
        "estimated_energy_micro_wh_per_1k_output": 910_000,  # 0.91 Wh/1k
        "enabled": True,
    },
    # === High-end production models (daily workhorses) ===
    {
        "id": "cloud-openai-gpt-5",
        "runtime_name": "cloud:openai/gpt-5",
        "display_name": "[云API] GPT-5",
        "tier": "quality",
        "parameter_b": "~500B MoE",
        "context_limit": 270_000,
        "recommended_for_json": json.dumps(["通用任务", "代码", "写作"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": 1 * _USD_TO_MICRO_RMB,
        "output_rate_micro_rmb_per_million": 4 * _USD_TO_MICRO_RMB,
        "estimated_tokens_per_second": 80,
        "estimated_energy_micro_wh_per_1k_output": 1_180_000,  # 1.18 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-anthropic-sonnet",
        "runtime_name": "cloud:anthropic/claude-sonnet",
        "display_name": "[云API] Claude Sonnet 4.6",
        "tier": "quality",
        "parameter_b": "~80B Dense",
        "context_limit": 200_000,
        "recommended_for_json": json.dumps(["日常开发", "代码", "写作", "RAG"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": 3 * _USD_TO_MICRO_RMB,
        "output_rate_micro_rmb_per_million": 15 * _USD_TO_MICRO_RMB,
        "estimated_tokens_per_second": 70,
        "estimated_energy_micro_wh_per_1k_output": 2_180_000,  # 2.18 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-google-gemini-pro",
        "runtime_name": "cloud:google/gemini-pro",
        "display_name": "[云API] Gemini 3.1 Pro",
        "tier": "quality",
        "parameter_b": "~500B MoE",
        "context_limit": 1_000_000,
        "recommended_for_json": json.dumps(["长上下文", "多模态", "通用"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(1.25 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": 5 * _USD_TO_MICRO_RMB,
        "estimated_tokens_per_second": 75,
        "estimated_energy_micro_wh_per_1k_output": 2_430_000,  # 2.43 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-deepseek-v3",
        "runtime_name": "cloud:deepseek/deepseek-v3",
        "display_name": "[云API] DeepSeek-V3",
        "tier": "quality",
        "parameter_b": "671B MoE/37B active",
        "context_limit": 64_000,
        "recommended_for_json": json.dumps(["高性价比", "代码", "通用"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(0.27 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": int(1.10 * _USD_TO_MICRO_RMB),
        "estimated_tokens_per_second": 80,
        "estimated_energy_micro_wh_per_1k_output": 250_000,  # 0.25 Wh/1k (very efficient!)
        "enabled": True,
    },
    {
        "id": "cloud-qwen-plus",
        "runtime_name": "cloud:alibaba/qwen-plus",
        "display_name": "[云API] 通义千问 Plus",
        "tier": "quality",
        "parameter_b": "~300B MoE",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(["中文通用", "客服", "电商"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(0.8 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": 2 * _USD_TO_MICRO_RMB,
        "estimated_tokens_per_second": 85,
        "estimated_energy_micro_wh_per_1k_output": 420_000,  # 0.42 Wh/1k
        "enabled": True,
    },
    # === Mid-range high-concurrency models ===
    {
        "id": "cloud-openai-4o",
        "runtime_name": "cloud:openai/gpt-4o",
        "display_name": "[云API] GPT-4o",
        "tier": "balanced",
        "parameter_b": "~300B MoE",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(["多模态", "实时对话", "通用"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(2.5 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": 10 * _USD_TO_MICRO_RMB,
        "estimated_tokens_per_second": 100,
        "estimated_energy_micro_wh_per_1k_output": 1_130_000,  # 1.13 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-anthropic-haiku",
        "runtime_name": "cloud:anthropic/claude-haiku",
        "display_name": "[云API] Claude Haiku 4.5",
        "tier": "balanced",
        "parameter_b": "~20B Dense",
        "context_limit": 200_000,
        "recommended_for_json": json.dumps(["高并发", "分类", "抽取"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(0.8 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": 4 * _USD_TO_MICRO_RMB,
        "estimated_tokens_per_second": 150,
        "estimated_energy_micro_wh_per_1k_output": 830_000,  # 0.83 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-google-flash",
        "runtime_name": "cloud:google/gemini-flash",
        "display_name": "[云API] Gemini 3.1 Flash",
        "tier": "balanced",
        "parameter_b": "~100B MoE",
        "context_limit": 1_000_000,
        "recommended_for_json": json.dumps(["高速", "长上下文", "多模态"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(0.15 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": int(0.6 * _USD_TO_MICRO_RMB),
        "estimated_tokens_per_second": 200,
        "estimated_energy_micro_wh_per_1k_output": 870_000,  # 0.87 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-qwen-turbo",
        "runtime_name": "cloud:alibaba/qwen-turbo",
        "display_name": "[云API] 通义千问 Turbo",
        "tier": "balanced",
        "parameter_b": "~100B MoE",
        "context_limit": 1_000_000,
        "recommended_for_json": json.dumps(["高并发", "实时", "中文"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(0.3 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": int(0.9 * _USD_TO_MICRO_RMB),
        "estimated_tokens_per_second": 200,
        "estimated_energy_micro_wh_per_1k_output": 220_000,  # 0.22 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-doubao-lite",
        "runtime_name": "cloud:bytedance/doubao-lite",
        "display_name": "[云API] 豆包 Lite",
        "tier": "balanced",
        "parameter_b": "~150B MoE",
        "context_limit": 256_000,
        "recommended_for_json": json.dumps(["高并发", "分类", "客服"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(0.1 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": int(0.3 * _USD_TO_MICRO_RMB),
        "estimated_tokens_per_second": 250,
        "estimated_energy_micro_wh_per_1k_output": 290_000,  # 0.29 Wh/1k
        "enabled": True,
    },
    # === Lightweight models ===
    {
        "id": "cloud-openai-4o-mini",
        "runtime_name": "cloud:openai/gpt-4o-mini",
        "display_name": "[云API] GPT-4o Mini",
        "tier": "economy",
        "parameter_b": "~60B MoE",
        "context_limit": 128_000,
        "recommended_for_json": json.dumps(["简单任务", "分类", "抽取"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(0.15 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": int(0.6 * _USD_TO_MICRO_RMB),
        "estimated_tokens_per_second": 300,
        "estimated_energy_micro_wh_per_1k_output": 350_000,  # 0.35 Wh/1k
        "enabled": True,
    },
    {
        "id": "cloud-google-flash-lite",
        "runtime_name": "cloud:google/gemini-flash-lite",
        "display_name": "[云API] Gemini Flash Lite",
        "tier": "economy",
        "parameter_b": "~10B Dense",
        "context_limit": 1_000_000,
        "recommended_for_json": json.dumps(["超高速", "简单分类", "批量处理"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": int(0.075 * _USD_TO_MICRO_RMB),
        "output_rate_micro_rmb_per_million": int(0.3 * _USD_TO_MICRO_RMB),
        "estimated_tokens_per_second": 400,
        "estimated_energy_micro_wh_per_1k_output": 420_000,  # 0.42 Wh/1k
        "enabled": True,
    },
)


async def seed_catalog(session: AsyncSession) -> None:
    """Seed model catalog from MODEL_SEEDS (local) and CLOUD_MODEL_SEEDS (reference).

    Idempotent: only inserts models not already present.
    Does NOT update existing models (to preserve user overrides).
    """
    existing = set((await session.scalars(select(ModelRecord.id))).all())
    for values in MODEL_SEEDS + CLOUD_MODEL_SEEDS:
        if values["id"] not in existing:
            enriched = dict(values)
            enriched.setdefault("is_task_classifier", False)
            if not enriched.get("official_data_source"):
                enriched["official_data_source"] = _get_official_data_source(
                    str(enriched["id"]),
                    str(enriched.get("runtime_name", "")),
                    str(enriched.get("tier", "")),
                )
            session.add(ModelRecord(**enriched))
    await session.commit()


def _enrich_energy_provenance(values: dict) -> dict:
    """Enrich model seed data with energy provenance metadata (v2).

    Only L1-L3 tiers are used. Models without sufficient benchmark data
    are marked INSUFFICIENT_DATA and excluded from energy-aware scoring.
    """
    enriched = dict(values)
    model_id = values.get("id", "")
    parameter_b = values.get("parameter_b", "")
    display_name = values.get("display_name", "")

    param_count = _parse_param_count(parameter_b)
    arch_family = _extract_arch_family(model_id, display_name)
    quant_bits = 4 if "-q4" in model_id else (16 if "cloud" in model_id else None)

    l2_coverage = {
        "qwen2.5": [0.5, 1.5, 3.0, 7.0, 14.0, 72.0],
        "llama3": [1.0, 3.0, 8.0, 70.0],
        "gemma2": [2.0, 9.0, 27.0],
        "gemma3": [1.0, 4.0],
        "gemma4": [2.0],
        "phi3": [3.8],
        "phi4": [3.8],
        "mistral": [7.0, 22.0],
    }
    l3_families = set(l2_coverage.keys())

    if "cloud" in model_id:
        provenance = "insufficient_data"
        confidence = 0
        source = "Cloud API model: no verified inference energy benchmark data"
        reference_gpu = None
    elif param_count is not None and arch_family in l2_coverage:
        exact_match = any(
            abs(p - param_count) < 0.1 for p in l2_coverage[arch_family]
        )
        if exact_match:
            provenance = "l2_benchmark_match"
            confidence = 8500
            gpu = "a100-80gb" if param_count >= 1.0 else "rtx-4060-ti"
            source = f"Public benchmark (JouleBench): {display_name} on {gpu}"
            reference_gpu = gpu
        else:
            provenance = "l3_cross_gpu_normalized"
            confidence = 6500
            nearest = min(l2_coverage[arch_family], key=lambda p: abs(p - param_count))
            source = f"Interpolated from {arch_family} {nearest}B benchmark (cross-GPU normalized)"
            reference_gpu = "a100-80gb"
    elif arch_family in l3_families:
        provenance = "l3_cross_gpu_normalized"
        confidence = 6000
        source = f"Interpolated from {arch_family} family benchmarks"
        reference_gpu = "a100-80gb"
    else:
        provenance = "insufficient_data"
        confidence = 0
        source = f"No verified energy benchmark available for {arch_family} architecture"
        reference_gpu = None

    enriched.setdefault("energy_data_provenance", provenance)
    enriched.setdefault("energy_data_source", source)
    enriched.setdefault("energy_confidence_bps", confidence)
    enriched.setdefault("reference_gpu_model", reference_gpu)
    enriched.setdefault("parameter_count_b", param_count)
    enriched.setdefault("quantization_bits", quant_bits)
    enriched.setdefault("architecture_family", arch_family)
    return enriched


def _parse_param_count(param_str: str) -> float | None:
    """Parse parameter count string to float billions."""
    if not param_str:
        return None
    s = param_str.strip().upper().replace(" ", "").replace("~", "")
    try:
        if "T" in s:
            return float(s.replace("T", "")) * 1000
        if "B" in s:
            return float(s.replace("B", ""))
        if "M" in s:
            return float(s.replace("M", "")) / 1000
        if "MOE" in s:
            import re
            match = re.search(r"([\d.]+)", s)
            if match:
                return float(match.group(1))
        return float(s) / 1e9
    except (ValueError, IndexError):
        return None


def _extract_arch_family(model_id: str, display_name: str) -> str:
    """Extract architecture family from model ID."""
    mid = model_id.lower().replace("cloud-", "")
    if "qwen" in mid:
        if "qwen3" in mid:
            return "qwen3"
        if "qwen2.5" in mid:
            return "qwen2.5"
        return "qwen"
    if "llama" in mid:
        if "llama3.3" in mid:
            return "llama3.3"
        if "llama3.2" in mid:
            return "llama3.2"
        if "llama3.1" in mid:
            return "llama3.1"
        return "llama"
    if "gemma" in mid:
        if "gemma4" in mid:
            return "gemma4"
        if "gemma3" in mid:
            return "gemma3"
        return "gemma"
    if "mistral" in mid:
        return "mistral"
    if "phi" in mid:
        return "phi"
    if "gpt" in mid:
        return "gpt"
    if "claude" in mid:
        return "claude"
    if "deepseek" in mid:
        return "deepseek"
    if "doubao" in mid:
        return "doubao"
    return "unknown"


def _get_official_data_source(model_id: str, runtime_name: str, tier: str) -> str:
    """Return official data source citation for a model based on its family/vendor.

    Args:
        model_id: The model catalog ID.
        runtime_name: The runtime name (e.g. "cloud:openai/gpt-4o", "qwen2.5:7b").
        tier: The model tier.

    Returns:
        A string with official pricing, technical report, and energy benchmark sources.
    """
    name = runtime_name.lower()
    mid = model_id.lower()

    # Cloud providers
    if "openai" in name:
        return (
            "OpenAI 官方定价 https://openai.com/api/pricing ; "
            "GPT-4 技术报告 arXiv:2303.08774 ; "
            "能耗估算基准 Watt Counts (arXiv 2607.26571, H100)"
        )
    if "anthropic" in name or "claude" in name:
        return (
            "Anthropic 官方定价 https://www.anthropic.com/pricing ; "
            "Claude 3 模型卡 https://www.anthropic.com/news/claude-3-family ; "
            "能耗估算基准 Watt Counts (H100)"
        )
    if "google" in name or "gemini" in name:
        return (
            "Google AI 官方定价 https://ai.google.dev/pricing ; "
            "Gemini 技术报告 https://deepmind.google/technologies/gemini/ ; "
            "能耗估算基准 Watt Counts (H100)"
        )
    if "deepseek" in name:
        return (
            "DeepSeek 官方定价 https://platform.deepseek.com/pricing ; "
            "DeepSeek-V3 技术报告 arXiv:2412.19437 ; "
            "DeepSeek-R1 技术报告 arXiv:2501.12948 ; "
            "能耗估算基于 MoE 架构分析 (H100)"
        )
    if "alibaba" in name or ("qwen" in mid and "cloud" in mid):
        return (
            "阿里云百炼官方定价 https://help.aliyun.com/zh/model-studio/billing-for-model-studio ; "
            "Qwen 技术报告 https://qwenlm.github.io/ ; "
            "能耗估算基准 JouleBench (A100)"
        )
    if "bytedance" in name or "doubao" in name:
        return (
            "火山引擎方舟官方定价 https://www.volcengine.com/docs/82379/1099320 ; "
            "豆包模型技术文档 https://www.volcengine.com/product/doubao ; "
            "能耗估算基于 MoE 架构分析 (H100)"
        )

    # Local open-source models by family
    if "qwen" in mid:
        return (
            "Qwen2.5 官方技术报告 https://qwenlm.github.io/blog/qwen2.5/ ; "
            "实测基准 JouleBench (arXiv 2608.00008, RTX 4060 Ti Q4)"
        )
    if "gemma" in mid:
        return (
            "Gemma 官方模型卡 https://ai.google.dev/gemma ; "
            "Gemma 技术报告 arXiv:2403.08295 ; "
            "实测基准 JouleBench (arXiv 2608.00008, RTX 4060 Ti Q4)"
        )
    if "llama" in mid:
        return (
            "Llama 官方模型卡 https://www.llama.com/ ; "
            "Llama 3 技术报告 arXiv:2407.21783 ; "
            "实测基准 JouleBench (arXiv 2608.00008, RTX 4060 Ti Q4)"
        )
    if "mistral" in mid:
        return (
            "Mistral 官方文档 https://docs.mistral.ai/ ; "
            "Mistral 7B 技术报告 arXiv:2310.06825 ; "
            "实测基准 JouleBench (arXiv 2608.00008, RTX 4060 Ti Q4)"
        )
    if "phi" in mid:
        return (
            "Phi-4 官方模型卡 https://huggingface.co/microsoft/phi-4 ; "
            "Phi-4 技术报告 arXiv:2412.08905 ; "
            "实测基准 JouleBench (arXiv 2608.00008, RTX 4060 Ti Q4)"
        )

    # Default for unknown local models
    return "开源模型官方文档 ; 能耗估算基准 JouleBench (arXiv 2608.00008, RTX 4060 Ti Q4)"


def get_model_energy_estimate(model_id: str) -> dict[str, object] | None:
    """Get energy benchmark data for a model from local data files.

    Returns dict with j_per_token, wh_per_1k, tokens_per_second, confidence, source
    or None if not found.
    """
    data = _load_benchmark_data()
    if not data:
        return None

    # Search consumer GPU models
    consumer = cast(dict[str, object], data.get("consumer_gpu", {}))
    models_list = cast(list[dict[str, object]], consumer.get("models", []))
    for model in models_list:
        model_id_str = cast(str, model["id"])
        if model_id_str.replace(":", "-").replace(".", "-") == model_id.replace(":", "-"):
            return {
                "j_per_output_token": model["j_per_output_token"],
                "wh_per_1k_output": model["wh_per_1k_output"],
                "tokens_per_second": model["tokens_per_second"],
                "confidence": model["confidence"],
                "source": "arXiv:2608.00008 (RTX 4060 Ti)",
                "hardware": "consumer_q4",
            }

    return None
