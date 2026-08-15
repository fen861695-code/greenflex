"""GreenFlex API tools for the concierge agent.

These tools call GreenFlex internal services directly (no HTTP overhead),
exposing them as LLM function-calling tools.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from greenflex.container import ServiceContainer
from greenflex.schemas import (
    ChatRequest,
    ChatMessage,
    PreviewRequest,
    RecommendationRequest,
)
from greenflex.services import (
    create_recommendation,
    get_order,
    list_models,
    order_view,
    preview,
)
from greenflex.signals import GRID_REGIONS

logger = logging.getLogger(__name__)


class ConciergeTools:
    """Tools callable by the concierge LLM via function calling."""

    def __init__(self, session: AsyncSession, container: ServiceContainer) -> None:
        self._session = session
        self._container = container

    # ---- Tool implementations ----

    async def analyze_task(
        self,
        prompt: str,
        task_type: str = "auto",
        quality_requirement: str = "standard",
        budget_rmb: float | None = None,
        item_count: int = 1,
    ) -> dict[str, Any]:
        """Analyze a task and return model recommendations with price/energy/carbon."""
        request = RecommendationRequest(
            mode="smart",
            task_type=task_type,  # type: ignore[arg-type]
            prompt_preview=prompt,
            item_count=item_count,
            quality_requirement=quality_requirement,  # type: ignore[arg-type]
            budget_rmb=budget_rmb,
        )
        result = await create_recommendation(self._session, self._container, request)

        alternatives = []
        for alt in result.alternatives[:3]:
            alternatives.append(
                {
                    "model_id": alt.model_id,
                    "model_name": alt.model_name,
                    "tier": alt.tier,
                    "price_rmb": alt.estimated_price_rmb,
                    "energy_wh": alt.estimated_energy_wh,
                    "carbon_g": alt.estimated_carbon_g,
                    "quality_risk": alt.quality_risk,
                    "reason_codes": alt.reason_codes,
                }
            )

        return {
            "recommended_model": result.recommended_model_name,
            "recommended_tier": result.recommended_tier,
            "quality_risk": result.quality_risk,
            "price_rmb": result.estimated_price_rmb,
            "energy_wh": result.estimated_energy_wh,
            "carbon_g": result.estimated_carbon_g,
            "execution_seconds": result.estimated_execution_seconds,
            "reason": result.reason_summary,
            "confidence": result.confidence_label,
            "alternatives": alternatives,
        }

    async def list_models(self) -> dict[str, Any]:
        """List all available models with their tier and specs."""
        models = await list_models(self._session, self._container)
        return {
            "models": [
                {
                    "id": m.id,
                    "name": m.display_name,
                    "tier": m.tier,
                    "params": m.parameter_b,
                    "context": m.context_limit,
                    "speed_tps": m.estimated_tokens_per_second,
                    "available": m.available,
                    "is_cloud": m.is_cloud_model,
                }
                for m in models
            ]
        }

    async def preview_model(
        self, model_id: str, prompt: str, max_output_tokens: int = 256
    ) -> dict[str, Any]:
        """Run a single prompt on a specific model and return the output."""
        request = PreviewRequest(
            model_id=model_id,
            prompt=prompt,
            max_output_tokens=max_output_tokens,
        )
        result = await preview(self._session, self._container, request)
        return {
            "model_id": result.model_id,
            "output": result.output[:1000],
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.output_tokens,
            "duration_ms": result.latency_ms,
        }

    async def get_carbon_status(self) -> dict[str, Any]:
        """Get current grid carbon intensity and renewable share."""
        signal = self._container.signals.signal_at(
            __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
        )
        region = self._container.signals.region
        return {
            "region": region.code,
            "region_name": region.name_zh,
            "carbon_g_per_kwh": round(signal.carbon_g_per_kwh, 1),
            "renewable_pct": round(signal.renewable_share_bps / 100, 1),
            "price_rmb_per_kwh": round(signal.price_micro_rmb_per_kwh / 1_000_000, 4),
            "regions_count": len(GRID_REGIONS),
        }

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        """Check order status and results."""
        order = await get_order(self._session, order_id)
        view = order_view(order, include_items=True)
        items = []
        for item in (view.items or [])[:5]:
            items.append(
                {
                    "id": item.client_item_id,
                    "status": item.status,
                    "output": (item.output or "")[:200],
                    "tokens": item.output_tokens,
                    "error": item.error_code,
                }
            )
        return {
            "order_id": view.id,
            "status": view.status,
            "model": view.model_name,
            "total_items": view.item_count,
            "succeeded": view.succeeded_count,
            "failed": view.failed_count,
            "quoted_price_rmb": view.quoted_price_rmb,
            "energy_wh": view.gross_gpu_energy_wh,
            "carbon_g": view.location_carbon_g,
            "items": items,
        }

    async def chat_with_model(
        self, message: str, model_id: str | None = None
    ) -> dict[str, Any]:
        """Send a message to an AI model for a direct response.

        Use this when the user wants to chat, ask questions, or get content
        generated — not when they need model recommendations.
        """
        # Default to a balanced cloud model if available, else first enabled
        if not model_id:
            from sqlalchemy import select
            from greenflex.models import ModelRecord

            models = (
                await self._session.scalars(
                    select(ModelRecord).where(ModelRecord.enabled.is_(True))
                )
            ).all()
            # Prefer cloud balanced models for chat
            model_id = next(
                (
                    m.id
                    for m in models
                    if "cloud" in m.id and m.tier == "balanced"
                ),
                models[0].id if models else "gemma3-1b-q4",
            )

        request = ChatRequest(
            model_id=model_id,
            messages=[ChatMessage(role="user", content=message)],
            max_output_tokens=1024,
        )
        from greenflex.services import chat as chat_service

        result = await chat_service(self._session, self._container, request)
        return {
            "model_id": result.model_id,
            "model_name": result.model_name,
            "reply": result.reply,
            "tokens": result.prompt_tokens + result.completion_tokens,
            "price_rmb": round(result.estimated_price_micro_rmb / 1_000_000, 6),
        }

    # ---- Tool definitions (OpenAI function calling format) ----

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "analyze_task",
                    "description": (
                        "分析用户的文本处理任务，自动识别任务类型和复杂度，"
                        "返回推荐模型方案（含价格、能耗、碳排、耗时）。"
                        "用户描述任务、询问推荐、需要报价时调用。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "用户的任务描述文本",
                            },
                            "task_type": {
                                "type": "string",
                                "enum": [
                                    "auto",
                                    "classification",
                                    "extraction",
                                    "summarization",
                                    "generation",
                                    "analysis",
                                    "code",
                                    "translation",
                                ],
                                "description": "任务类型，默认 auto 自动检测",
                            },
                            "quality_requirement": {
                                "type": "string",
                                "enum": ["minimum", "standard", "high", "critical"],
                                "description": "质量要求",
                                "default": "standard",
                            },
                            "budget_rmb": {
                                "type": "number",
                                "description": "预算上限（元）",
                            },
                            "item_count": {
                                "type": "integer",
                                "description": "批量条数，默认 1",
                                "default": 1,
                            },
                        },
                        "required": ["prompt"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "chat_with_model",
                    "description": (
                        "直接与 AI 模型对话，获取回答或生成内容。"
                        "当用户想聊天、提问、写东西、翻译（而非需要模型推荐）时调用。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "用户的消息内容",
                            },
                            "model_id": {
                                "type": "string",
                                "description": "指定模型 ID（可选，默认自动选择）",
                            },
                        },
                        "required": ["message"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_models",
                    "description": "列出所有可用模型及规格（参数量、档位、速度）。用户问有哪些模型时调用。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_carbon_status",
                    "description": "查询当前电网碳强度和绿电占比。用户问碳排、绿色能源、环保时调用。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "preview_model",
                    "description": "用指定模型试跑一条任务，查看实际输出。用户想对比模型效果时调用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model_id": {"type": "string", "description": "模型 ID"},
                            "prompt": {
                                "type": "string",
                                "description": "试跑的任务文本",
                            },
                            "max_output_tokens": {
                                "type": "integer",
                                "description": "最大输出 token 数",
                                "default": 256,
                            },
                        },
                        "required": ["model_id", "prompt"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_order_status",
                    "description": "查询订单执行状态和结果。用户问任务进度时调用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {
                                "type": "string",
                                "description": "订单 ID",
                            }
                        },
                        "required": ["order_id"],
                    },
                },
            },
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool and return JSON string result."""
        tool_map = {
            "analyze_task": self.analyze_task,
            "chat_with_model": self.chat_with_model,
            "list_models": self.list_models,
            "get_carbon_status": self.get_carbon_status,
            "preview_model": self.preview_model,
            "get_order_status": self.get_order_status,
        }
        func = tool_map.get(name)
        if not func:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
        try:
            result = await func(**arguments)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            logger.exception("Tool execution failed: %s", name)
            return json.dumps(
                {"error": f"工具执行失败: {e}"}, ensure_ascii=False
            )
