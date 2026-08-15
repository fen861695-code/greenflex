"""Cloud API inference provider with real HTTP implementations.

Routes requests to one of six supported cloud LLM providers based on the
runtime_name prefix (e.g. ``cloud:openai/gpt-4o``).  OpenAI-compatible
providers (DeepSeek, Alibaba DashScope, ByteDance Volcengine) share the
same chat-completions format; Anthropic and Google use their native APIs.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx

from greenflex.domain import DomainError
from greenflex.ports import GenerationRequest, GenerationResult, InferenceProvider

if TYPE_CHECKING:
    from greenflex.runtime_settings import RuntimeSettingsStore

_PROVIDERS = ("openai", "anthropic", "deepseek", "alibaba", "bytedance", "google")

# Default base URLs for each provider
_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "deepseek": "https://api.deepseek.com",
    "alibaba": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "bytedance": "https://ark.cn-beijing.volces.com/api/v3",
    "google": "https://generativelanguage.googleapis.com/v1beta",
}

# Map catalog model IDs to actual API model names
_MODEL_NAME_MAP: dict[str, dict[str, str]] = {
    "openai": {
        "gpt-o3-ultra": "gpt-4o",
        "gpt-5-pro": "gpt-4o",
        "gpt-4o-mini": "gpt-4o-mini",
    },
    "anthropic": {
        "claude-opus-thinking": "claude-opus-4-20250514",
        "claude-opus": "claude-opus-4-20250514",
    },
    "google": {
        "gemini-ultra": "gemini-2.5-pro",
        "gemini-flash-lite": "gemini-2.0-flash-lite",
    },
    "deepseek": {
        "deepseek-r1": "deepseek-reasoner",
    },
    "alibaba": {},
    "bytedance": {
        "doubao-pro": "doubao-pro-32k",
        "doubao-lite": "doubao-lite-32k",
    },
}

# Anthropic API version
_ANTHROPIC_VERSION = "2023-06-01"


class CloudAPIProvider:
    """Routes inference requests to configured cloud LLM APIs.

    Keys and base URLs are read dynamically from a RuntimeSettingsStore,
    allowing runtime updates via the settings API without restart.
    """

    source = "cloud-api"

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingsStore | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._settings = runtime_settings
        self._timeout = httpx.Timeout(timeout_seconds, connect=10.0)

    def _get_api_key(self, provider: str) -> str:
        if self._settings is not None:
            return self._settings.get_api_key(provider)
        return ""

    def _get_base_url(self, provider: str) -> str:
        if self._settings is not None:
            return self._settings.get_base_url(provider)
        return _DEFAULT_BASE_URLS.get(provider, "")

    async def available_models(self) -> dict[str, str]:
        """Return providers that have API keys configured."""
        if self._settings is not None:
            return {p: "configured" for p in _PROVIDERS if self._settings.is_configured(p)}
        return {}

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Route the generation request to the appropriate cloud provider."""
        provider = self._extract_provider(request.model_name)
        if provider is None:
            raise DomainError(
                "unknown_cloud_provider",
                f"无法识别云服务商: {request.model_name}",
                400,
            )

        api_key = self._get_api_key(provider)
        if not api_key:
            raise DomainError(
                "cloud_api_not_configured",
                f"云服务商 {provider} 的 API Key 未配置，请在设置页面或 .env 中配置。",
                503,
            )

        if provider in ("openai", "deepseek", "alibaba", "bytedance"):
            return await self._generate_openai_compatible(request, api_key, provider)
        if provider == "anthropic":
            return await self._generate_anthropic(request, api_key)
        if provider == "google":
            return await self._generate_google(request, api_key)
        raise DomainError(
            "unknown_cloud_provider",
            f"不支持的云服务商: {provider}",
            400,
        )

    # ------------------------------------------------------------------
    # Provider routing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_provider(model_name: str) -> str | None:
        """Extract provider name from runtime_name like 'cloud:openai/gpt-4o'."""
        if not model_name.startswith("cloud:"):
            return None
        remainder = model_name[len("cloud:") :]
        provider = remainder.split("/", 1)[0]
        if provider in _PROVIDERS:
            return provider
        return None

    @staticmethod
    def _extract_model_id(model_name: str) -> str:
        """Extract model ID from runtime_name like 'cloud:openai/gpt-4o'."""
        if "/" in model_name:
            return model_name.split("/", 1)[1]
        return model_name

    def _resolve_api_model(self, provider: str, model_name: str) -> str:
        """Map catalog model ID to actual API model name."""
        raw = self._extract_model_id(model_name)
        return _MODEL_NAME_MAP.get(provider, {}).get(raw, raw)

    def _build_messages(self, request: GenerationRequest) -> list[dict[str, str]]:
        """Build messages array from request, supporting multi-turn chat."""
        if request.messages:
            return [dict(m) for m in request.messages]
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        return messages

    # ------------------------------------------------------------------
    # OpenAI-compatible providers (OpenAI, DeepSeek, Alibaba, ByteDance)
    # ------------------------------------------------------------------

    async def _generate_openai_compatible(
        self,
        request: GenerationRequest,
        api_key: str,
        provider: str,
    ) -> GenerationResult:
        """Call an OpenAI-compatible Chat Completions API."""
        base_url = self._get_base_url(provider)
        api_model = self._resolve_api_model(provider, request.model_name)
        messages = self._build_messages(request)

        payload: dict[str, Any] = {
            "model": api_model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            raise DomainError(
                "cloud_api_unavailable",
                f"无法连接 {provider} API，请检查网络。",
                503,
            ) from exc
        except httpx.TimeoutException as exc:
            raise DomainError(
                "cloud_api_timeout",
                f"{provider} API 请求超时。",
                504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_detail(exc)
            status = exc.response.status_code
            if status == 401:
                raise DomainError(
                    "cloud_api_auth_failed",
                    f"{provider} API Key 无效或已过期。",
                    401,
                ) from exc
            if status == 429:
                raise DomainError(
                    "cloud_api_rate_limited",
                    f"{provider} API 请求频率超限，请稍后重试。",
                    429,
                ) from exc
            raise DomainError(
                "cloud_api_error",
                f"{provider} API 返回错误 ({status}): {detail}",
                502 if status >= 500 else 422,
            ) from exc
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DomainError(
                "cloud_api_error",
                f"{provider} API 调用失败: {exc}",
                502,
            ) from exc

        duration_us = int((time.perf_counter() - start) * 1_000_000)

        # Parse OpenAI-format response
        try:
            choice = data["choices"][0]
            output = choice["message"]["content"] or ""
            usage = data.get("usage", {})
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
        except (KeyError, IndexError, TypeError) as exc:
            raise DomainError(
                "cloud_api_invalid_response",
                f"{provider} API 返回了无效的响应格式。",
                502,
            ) from exc

        return GenerationResult(
            output=output,
            prompt_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            duration_us=duration_us,
            source="cloud-api",
        )

    # ------------------------------------------------------------------
    # Anthropic Messages API
    # ------------------------------------------------------------------

    async def _generate_anthropic(
        self,
        request: GenerationRequest,
        api_key: str,
        provider: str = "anthropic",
    ) -> GenerationResult:
        """Call Anthropic Messages API."""
        base_url = self._get_base_url("anthropic")
        api_model = self._resolve_api_model("anthropic", request.model_name)

        # Anthropic separates system prompt from messages
        messages = self._build_messages(request)
        system_prompt = request.system_prompt
        if messages and messages[0]["role"] == "system":
            system_prompt = messages[0]["content"]
            messages = messages[1:]

        payload: dict[str, Any] = {
            "model": api_model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{base_url}/messages",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            raise DomainError(
                "cloud_api_unavailable",
                "无法连接 Anthropic API，请检查网络。",
                503,
            ) from exc
        except httpx.TimeoutException as exc:
            raise DomainError(
                "cloud_api_timeout",
                "Anthropic API 请求超时。",
                504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_detail(exc)
            status = exc.response.status_code
            if status == 401:
                raise DomainError(
                    "cloud_api_auth_failed",
                    "Anthropic API Key 无效或已过期。",
                    401,
                ) from exc
            if status == 429:
                raise DomainError(
                    "cloud_api_rate_limited",
                    "Anthropic API 请求频率超限。",
                    429,
                ) from exc
            raise DomainError(
                "cloud_api_error",
                f"Anthropic API 返回错误 ({status}): {detail}",
                502 if status >= 500 else 422,
            ) from exc
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DomainError(
                "cloud_api_error",
                f"Anthropic API 调用失败: {exc}",
                502,
            ) from exc

        duration_us = int((time.perf_counter() - start) * 1_000_000)

        try:
            content_parts = data.get("content", [])
            output = "".join(
                part.get("text", "") for part in content_parts if part.get("type") == "text"
            )
            usage = data.get("usage", {})
            prompt_tokens = int(usage.get("input_tokens", 0))
            completion_tokens = int(usage.get("output_tokens", 0))
        except (KeyError, TypeError) as exc:
            raise DomainError(
                "cloud_api_invalid_response",
                "Anthropic API 返回了无效的响应格式。",
                502,
            ) from exc

        return GenerationResult(
            output=output,
            prompt_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            duration_us=duration_us,
            source="cloud-api",
        )

    # ------------------------------------------------------------------
    # Google Gemini API
    # ------------------------------------------------------------------

    async def _generate_google(
        self,
        request: GenerationRequest,
        api_key: str,
        provider: str = "google",
    ) -> GenerationResult:
        """Call Google Gemini generateContent API."""
        base_url = self._get_base_url("google")
        api_model = self._resolve_api_model("google", request.model_name)

        # Build Gemini-format contents
        messages = self._build_messages(request)
        contents: list[dict[str, Any]] = []
        system_instruction: dict[str, Any] | None = None

        for msg in messages:
            if msg["role"] == "system":
                system_instruction = {"parts": [{"text": msg["content"]}]}
            elif msg["role"] == "user":
                contents.append(
                    {
                        "role": "user",
                        "parts": [{"text": msg["content"]}],
                    }
                )
            elif msg["role"] == "assistant":
                contents.append(
                    {
                        "role": "model",
                        "parts": [{"text": msg["content"]}],
                    }
                )

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_output_tokens,
                "temperature": request.temperature,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{base_url}/models/{api_model}:generateContent",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    params={"key": api_key},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            raise DomainError(
                "cloud_api_unavailable",
                "无法连接 Google Gemini API，请检查网络。",
                503,
            ) from exc
        except httpx.TimeoutException as exc:
            raise DomainError(
                "cloud_api_timeout",
                "Google Gemini API 请求超时。",
                504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_detail(exc)
            status = exc.response.status_code
            if status == 400:
                raise DomainError(
                    "cloud_api_error",
                    f"Google API 请求错误: {detail}",
                    422,
                ) from exc
            if status == 403:
                raise DomainError(
                    "cloud_api_auth_failed",
                    "Google API Key 无效或未授权。",
                    401,
                ) from exc
            if status == 429:
                raise DomainError(
                    "cloud_api_rate_limited",
                    "Google API 请求频率超限。",
                    429,
                ) from exc
            raise DomainError(
                "cloud_api_error",
                f"Google API 返回错误 ({status}): {detail}",
                502 if status >= 500 else 422,
            ) from exc
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DomainError(
                "cloud_api_error",
                f"Google API 调用失败: {exc}",
                502,
            ) from exc

        duration_us = int((time.perf_counter() - start) * 1_000_000)

        try:
            candidate = data["candidates"][0]
            parts = candidate["content"]["parts"]
            output = "".join(part.get("text", "") for part in parts)
            usage = data.get("usageMetadata", {})
            prompt_tokens = int(usage.get("promptTokenCount", 0))
            completion_tokens = int(usage.get("candidatesTokenCount", 0))
        except (KeyError, IndexError, TypeError) as exc:
            raise DomainError(
                "cloud_api_invalid_response",
                "Google API 返回了无效的响应格式。",
                502,
            ) from exc

        return GenerationResult(
            output=output,
            prompt_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            duration_us=duration_us,
            source="cloud-api",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_error_detail(exc: httpx.HTTPStatusError) -> str:
        """Extract error message from an HTTP error response."""
        try:
            body = exc.response.json()
            if isinstance(body, dict):
                error = body.get("error", {})
                if isinstance(error, dict):
                    return str(error.get("message", exc.response.text[:200]))
                return str(error)
            return exc.response.text[:200]
        except Exception:
            return exc.response.text[:200]


# Static structural check: CloudAPIProvider satisfies InferenceProvider
_provider: type[InferenceProvider] = CloudAPIProvider
