"""LLM client for the concierge agent.

Uses OpenAI-compatible chat completions API (DeepSeek, OpenAI, Alibaba, etc.).
Reuses GreenFlex cloud API key configuration. No new env vars required —
if any cloud key is configured, the concierge can use it.

Preference order for function-calling quality:
1. DeepSeek (excellent function calling, low cost)
2. OpenAI
3. Alibaba (Qwen)
4. Any other configured provider
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from greenflex.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]


# Provider configs: (key setting, base URL, model name, display name)
_PROVIDER_CHOICES: list[tuple[str | None, str, str, str]] = [
    (
        getattr(settings, "deepseek_api_key", None) or None,
        "https://api.deepseek.com",
        "deepseek-chat",
        "deepseek",
    ),
    (
        getattr(settings, "openai_api_key", None) or None,
        "https://api.openai.com/v1",
        "gpt-4o-mini",
        "openai",
    ),
    (
        getattr(settings, "alibaba_api_key", None) or None,
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus",
        "alibaba",
    ),
    (
        getattr(settings, "bytedance_api_key", None) or None,
        "https://ark.cn-beijing.volces.com/api/v3",
        "doubao-lite",
        "bytedance",
    ),
]


class ConciergeLLM:
    """OpenAI-compatible chat client with function calling."""

    def __init__(self) -> None:
        self._available = False
        self._base_url = ""
        self._api_key = ""
        self._model = ""
        self._provider = "none"

        for key, base_url, model, provider in _PROVIDER_CHOICES:
            if key:
                self._available = True
                self._base_url = base_url.rstrip("/")
                self._api_key = key
                self._model = model
                self._provider = provider
                logger.info("Concierge LLM using %s (%s)", provider, model)
                break

    @property
    def available(self) -> bool:
        return self._available

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        if not self._available:
            return LLMResponse(
                content="智能管家需要配置云 API Key（推荐 DeepSeek）才能使用。"
                "请在设置页面填入 API Key。",
                tool_calls=[],
            )

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        msg = choice["message"]

        tool_calls: list[ToolCall] = []
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                func = tc["function"]
                try:
                    args = json.loads(func["arguments"])
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(
                    ToolCall(id=tc["id"], name=func["name"], arguments=args)
                )

        return LLMResponse(content=msg.get("content"), tool_calls=tool_calls)
