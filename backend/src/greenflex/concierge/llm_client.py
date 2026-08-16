"""LLM client for the concierge agent.

Uses OpenAI-compatible chat completions API (DeepSeek, OpenAI, Alibaba, etc.).
Reuses GreenFlex cloud API key configuration — reads from the RuntimeSettingsStore
which includes both environment variables and keys set via the settings page.
Keys are never logged or exposed in responses.

Preference order for function-calling quality:
1. DeepSeek (excellent function calling, low cost)
2. OpenAI
3. Alibaba (Qwen)
4. ByteDance (Doubao)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from greenflex.config import get_settings

logger = logging.getLogger(__name__)

# Provider configs: (provider_name, base_url, model)
_PROVIDER_CONFIGS: list[tuple[str, str, str]] = [
    ("deepseek", "https://api.deepseek.com", "deepseek-chat"),
    ("openai", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("alibaba", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ("bytedance", "https://ark.cn-beijing.volces.com/api/v3", "doubao-lite"),
]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]


class ConciergeLLM:
    """OpenAI-compatible chat client with function calling.

    Keys are resolved lazily on each call from the runtime settings store,
    so keys set via the settings page take effect immediately.
    """

    def __init__(self, runtime_settings: Any | None = None) -> None:
        self._runtime_settings = runtime_settings
        self._settings = get_settings()

    def update_runtime_settings(self, runtime_settings: Any | None) -> None:
        """Update the runtime settings reference (called per-request)."""
        self._runtime_settings = runtime_settings

    def _resolve_provider(self) -> tuple[str, str, str, str] | None:
        """Find the first configured provider. Returns (key, base_url, model, name)."""
        for provider_name, base_url, model in _PROVIDER_CONFIGS:
            key = self._get_key(provider_name)
            if key:
                return key, base_url.rstrip("/"), model, provider_name
        return None

    def _get_key(self, provider: str) -> str:
        """Get API key: runtime store (env + UI override) > env var."""
        if self._runtime_settings is not None:
            return self._runtime_settings.get_api_key(provider)
        # Fallback: env vars only
        env_map = {
            "openai": self._settings.openai_api_key,
            "deepseek": self._settings.deepseek_api_key,
            "alibaba": self._settings.alibaba_api_key,
            "bytedance": self._settings.bytedance_api_key,
        }
        return env_map.get(provider) or ""

    @property
    def available(self) -> bool:
        return self._resolve_provider() is not None

    @property
    def provider(self) -> str:
        resolved = self._resolve_provider()
        return resolved[3] if resolved else "none"

    @property
    def model(self) -> str:
        resolved = self._resolve_provider()
        return resolved[2] if resolved else ""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        resolved = self._resolve_provider()
        if resolved is None:
            return LLMResponse(
                content="智能管家需要配置云 API Key（推荐 DeepSeek）才能使用。"
                "请在设置页面填入 API Key。",
                tool_calls=[],
            )

        api_key, base_url, model, provider = resolved
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload: dict[str, Any] = {
            "model": model,
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
