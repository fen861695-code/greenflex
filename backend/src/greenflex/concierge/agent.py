"""GreenConcierge agent core — function-calling loop with rule-based fallback.

When an LLM with function-calling support is configured (e.g. DeepSeek), the
agent uses the LLM to decide which tools to call. When no LLM is available,
it falls back to a rule-based mode that can still analyze tasks and answer
common questions.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from greenflex.container import ServiceContainer

from .llm_client import ConciergeLLM
from .memory import ConversationMemory, Message
from .tools import ConciergeTools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 GreenFlex 绿色推理管家，帮助用户选择合适的 AI 模型、获取报价、提交任务并查询状态。

## 你的职责
1. 理解用户的任务需求（分类、抽取、摘要、分析、生成、代码、翻译等）
2. 调用 analyze_task 获取推荐方案（含价格、能耗、碳排、耗时）
3. 用简洁的中文向用户展示方案，说明推荐理由
4. 如果用户只是想聊天或提问，调用 chat_with_model 直接回答
5. 帮助查询模型列表、碳信号、订单状态

## 重要规则
- 主动解释推荐理由：告诉用户为什么推荐这个模型
- 关注绿色指标：展示方案时包含能耗和碳排信息
- 价格单位是元，能耗是 Wh，碳排是 g CO2
- 信息不足时追问
- 简洁回复，用列表或表格展示关键信息
- 用户想直接聊天/写作/翻译时，用 chat_with_model，不要每次都推荐模型
"""

# Keywords that suggest the user wants a direct chat rather than model recommendation
_CHAT_KEYWORDS = re.compile(
    r"你好|谢谢|再见|你是谁|什么是|怎么|为什么|帮我写|写一首|写一篇|翻译|解释一下|聊聊天",
    re.IGNORECASE,
)

_TASK_KEYWORDS = re.compile(
    r"分类|抽取|提取|摘要|总结|分析|生成|代码|写一个函数|批量|处理|识别|判断",
    re.IGNORECASE,
)


class ConciergeAgent:
    """GreenFlex conversational agent."""

    def __init__(self) -> None:
        self.llm = ConciergeLLM()
        self.memory = ConversationMemory(SYSTEM_PROMPT)

    async def chat(
        self,
        session_id: str,
        message: str,
        *,
        db_session: AsyncSession,
        container: ServiceContainer,
    ) -> tuple[str, str, list[str]]:
        """Process a user message.

        Returns:
            (reply_text, agent_mode, tools_used)
        """
        tools = ConciergeTools(db_session, container)
        self.memory.add(session_id, "user", message)

        if self.llm.available:
            return await self._llm_loop(session_id, message, tools)
        return await self._rule_based(session_id, message, tools)

    async def _llm_loop(
        self,
        session_id: str,
        message: str,
        tools: ConciergeTools,
    ) -> tuple[str, str, list[str]]:
        """Function-calling loop with LLM."""
        tool_defs = tools.get_tool_definitions()
        tools_used: list[str] = []

        for _ in range(5):
            messages = self.memory.get_messages(session_id)
            response = await self.llm.chat(messages, tools=tool_defs)

            if not response.tool_calls:
                reply = response.content or "（无回复）"
                self.memory.add(session_id, "assistant", reply)
                return reply, "llm", tools_used

            # Record assistant message with tool_calls
            raw_calls = []
            for tc in response.tool_calls:
                raw_calls.append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                )
            self.memory.add_raw(
                session_id,
                Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=raw_calls,
                ),
            )

            for tc in response.tool_calls:
                tools_used.append(tc.name)
                result = await tools.execute(tc.name, tc.arguments)
                self.memory.add(
                    session_id,
                    "tool",
                    result,
                    tool_call_id=tc.id,
                    name=tc.name,
                )

        # Max tool calls reached — ask LLM to summarize
        messages = self.memory.get_messages(session_id)
        response = await self.llm.chat(messages)
        reply = response.content or "处理完成。"
        self.memory.add(session_id, "assistant", reply)
        return reply, "llm", tools_used

    async def _rule_based(
        self,
        session_id: str,
        message: str,
        tools: ConciergeTools,
    ) -> tuple[str, str, list[str]]:
        """Rule-based fallback when no LLM is configured.

        Still provides task analysis and recommendations using the
        GreenFlex recommendation engine directly.
        """
        tools_used: list[str] = []
        msg = message.strip()

        # Carbon status query
        if re.search(r"碳|绿电|能源|环保|排放|电网", msg):
            result = await tools.get_carbon_status()
            tools_used.append("get_carbon_status")
            reply = (
                f"当前电网碳信号（{result['region_name']}）：\n"
                f"- 碳强度：{result['carbon_g_per_kwh']} g CO₂/kWh\n"
                f"- 绿电占比：{result['renewable_pct']}%\n"
                f"- 电价：¥{result['price_rmb_per_kwh']}/kWh\n\n"
                f"共覆盖 {result['regions_count']} 个电网区域。"
                f"配置云 API Key（推荐 DeepSeek）后，我可以用自然语言帮你完成更多任务。"
            )
            self.memory.add(session_id, "assistant", reply)
            return reply, "rule", tools_used

        # Model list query
        if re.search(r"有哪些模型|模型列表|列出模型|什么模型", msg):
            result = await tools.list_models()
            tools_used.append("list_models")
            all_models = result["models"]
            enabled = [m for m in all_models if m.get("available") or m.get("is_cloud")]
            lines = [f"共 {len(enabled)} 个可用模型："]
            for m in enabled[:10]:
                lines.append(
                    f"- [{m['tier']}] {m['name']} ({m['params']}, {m['speed_tps']} tok/s)"
                )
            if len(enabled) > 10:
                lines.append(f"... 等共 {len(enabled)} 个")
            lines.append("\n配置云 API Key 后可以直接和我对话。")
            reply = "\n".join(lines)
            self.memory.add(session_id, "assistant", reply)
            return reply, "rule", tools_used

        # Task analysis (default for task-like messages)
        if _TASK_KEYWORDS.search(msg) or len(msg) > 10:
            result = await tools.analyze_task(prompt=msg)
            tools_used.append("analyze_task")
            alts = result.get("alternatives", [])
            lines = [
                f"任务分析完成：",
                f"- 推荐模型：{result['recommended_model']}（{result['recommended_tier']} 档）",
                f"- 预估价格：¥{result['price_rmb']}",
                f"- 预估能耗：{result['energy_wh']} Wh",
                f"- 预估碳排：{result['carbon_g']} g CO₂",
                f"- 预计耗时：{result['execution_seconds']} 秒",
                f"- 推荐理由：{result['reason']}",
            ]
            if alts:
                lines.append("\n备选方案：")
                for a in alts[1:3]:
                    lines.append(
                        f"- [{a['tier']}] {a['model_name']}：¥{a['price_rmb']}, "
                        f"{a['energy_wh']}Wh, {a['carbon_g']}g"
                    )
            lines.append(
                "\n提示：配置云 API Key（推荐 DeepSeek）后，我可以直接帮你执行任务和对话。"
            )
            reply = "\n".join(lines)
            self.memory.add(session_id, "assistant", reply)
            return reply, "rule", tools_used

        # Default greeting / help
        reply = (
            "你好！我是 GreenFlex 绿色推理管家。我可以帮你：\n"
            "- 分析任务并推荐最合适的 AI 模型\n"
            "- 对比不同模型的价格、能耗和碳排\n"
            "- 查询电网碳信号\n"
            "- 列出可用模型\n\n"
            "直接描述你的任务即可，比如「帮我总结一篇文章」或「分类100条评论」。\n\n"
            "提示：在设置页面配置云 API Key（推荐 DeepSeek）后，我可以直接和你对话。"
        )
        self.memory.add(session_id, "assistant", reply)
        return reply, "rule", tools_used

    def reset(self, session_id: str) -> None:
        """Clear conversation history for a session."""
        self.memory.clear(session_id)
