from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from greenflex.models import ModelRecord

MODEL_SEED_VERSION = "model-catalog-v1"

MODEL_SEEDS = (
    {
        "id": "qwen2.5-0.5b-q4",
        "runtime_name": "qwen2.5:0.5b",
        "display_name": "Qwen2.5 0.5B",
        "tier": "economy",
        "parameter_b": "0.5B",
        "context_limit": 4_096,
        "recommended_for_json": json.dumps(["分类", "字段提取", "简单改写"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": 100_000,
        "output_rate_micro_rmb_per_million": 300_000,
        "estimated_tokens_per_second": 55,
        "estimated_energy_micro_wh_per_1k_output": 800_000,
        "enabled": True,
    },
    {
        "id": "qwen2.5-1.5b-q4",
        "runtime_name": "qwen2.5:1.5b",
        "display_name": "Qwen2.5 1.5B",
        "tier": "balanced",
        "parameter_b": "1.5B",
        "context_limit": 4_096,
        "recommended_for_json": json.dumps(["摘要", "知识问答", "通用写作"], ensure_ascii=False),
        "input_rate_micro_rmb_per_million": 300_000,
        "output_rate_micro_rmb_per_million": 800_000,
        "estimated_tokens_per_second": 38,
        "estimated_energy_micro_wh_per_1k_output": 1_400_000,
        "enabled": True,
    },
    {
        "id": "qwen2.5-3b-q4",
        "runtime_name": "qwen2.5:3b",
        "display_name": "Qwen2.5 3B",
        "tier": "quality",
        "parameter_b": "3B",
        "context_limit": 4_096,
        "recommended_for_json": json.dumps(
            ["复杂摘要", "多步分析", "高质量生成"], ensure_ascii=False
        ),
        "input_rate_micro_rmb_per_million": 600_000,
        "output_rate_micro_rmb_per_million": 1_500_000,
        "estimated_tokens_per_second": 24,
        "estimated_energy_micro_wh_per_1k_output": 2_200_000,
        "enabled": True,
    },
)


async def seed_catalog(session: AsyncSession) -> None:
    existing = set((await session.scalars(select(ModelRecord.id))).all())
    for values in MODEL_SEEDS:
        if values["id"] not in existing:
            session.add(ModelRecord(**values))
    await session.commit()
