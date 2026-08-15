"""Runtime settings store for cloud API keys.

Keys can be set via environment variables (static) or updated at runtime
via the settings API. Values are persisted to a JSON file with restrictive
permissions (owner-only read/write) so they survive restarts. Runtime
updates take precedence over environment variables.

Security notes:
    - Keys are stored in plaintext at rest (local development tool).
    - The JSON file is created with 0600 permissions on POSIX systems.
    - The GET API never returns full keys, only masked previews.
    - Callers must ensure keys are never written to logs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any

from greenflex.config import get_settings

_PROVIDER_LABELS: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "deepseek": "DeepSeek",
    "alibaba": "阿里云百炼",
    "bytedance": "火山引擎方舟",
    "google": "Google AI",
}

_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "deepseek": "https://api.deepseek.com",
    "alibaba": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "bytedance": "https://ark.cn-beijing.volces.com/api/v3",
    "google": "https://generativelanguage.googleapis.com/v1beta",
}

# API keys must match this pattern (alphanumeric, hyphens, underscores, dots)
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_\-.]{8,256}$")

# Sensitive key names that must never appear in logs
_SENSITIVE_SUFFIXES = ("_api_key",)


def _mask_key(key: str) -> str:
    """Return a masked preview of an API key, e.g. sk-***abcd."""
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"


def validate_api_key(key: str) -> bool:
    """Validate API key format. Returns True if the key looks plausible."""
    return bool(_KEY_PATTERN.match(key.strip()))


class RuntimeSettingsStore:
    """Thread-safe store for cloud API keys and base URLs.

    Precedence: runtime override > environment variable > default.
    """

    def __init__(self, persist_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._persist_path = persist_path
        self._overrides: dict[str, str] = {}
        if persist_path and persist_path.exists():
            try:
                raw = json.loads(persist_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._overrides = {
                        k: str(v) for k, v in raw.items() if isinstance(v, str)
                    }
            except (json.JSONDecodeError, OSError):
                self._overrides = {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _set_file_permissions(self, path: Path) -> None:
        """Restrict file permissions to owner read/write only."""
        try:
            if os.name == "nt":
                # Windows: use icacls to restrict to current user
                user = os.environ.get("USERNAME", "")
                if user:
                    cmd = ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(R,W)"]
                    subprocess.run(  # noqa: S603
                        cmd, capture_output=True, timeout=5, check=False
                    )
            else:
                # POSIX: 0600 (owner read/write only)
                os.chmod(path, 0o600)
        except (OSError, subprocess.SubprocessError):
            pass  # best-effort

    def _persist(self) -> None:
        if self._persist_path is None:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(
                json.dumps(self._overrides, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._set_file_permissions(self._persist_path)
        except OSError:
            pass  # best-effort persistence

    # ------------------------------------------------------------------
    # Generic getter / setter
    # ------------------------------------------------------------------

    def get(self, key: str, default: str = "") -> str:
        with self._lock:
            if key in self._overrides:
                return self._overrides[key]
        return default

    def set(self, key: str, value: str | None) -> None:
        with self._lock:
            if value is None or value == "":
                self._overrides.pop(key, None)
            else:
                self._overrides[key] = value
            self._persist()

    def update(self, values: dict[str, str | None]) -> None:
        with self._lock:
            for key, value in values.items():
                if value is None or value == "":
                    self._overrides.pop(key, None)
                else:
                    self._overrides[key] = value
            self._persist()

    # ------------------------------------------------------------------
    # Cloud provider convenience
    # ------------------------------------------------------------------

    def get_api_key(self, provider: str) -> str:
        """Get API key: runtime override > env var > empty string."""
        with self._lock:
            override = self._overrides.get(f"{provider}_api_key", "")
            if override:
                return override
        # Fall back to environment-based settings
        s = get_settings()
        env_map = {
            "openai": s.openai_api_key,
            "anthropic": s.anthropic_api_key,
            "deepseek": s.deepseek_api_key,
            "alibaba": s.alibaba_api_key,
            "bytedance": s.bytedance_api_key,
            "google": s.google_api_key,
        }
        return env_map.get(provider) or ""

    def get_base_url(self, provider: str) -> str:
        """Get base URL: runtime override > env var > default."""
        with self._lock:
            override = self._overrides.get(f"{provider}_base_url", "")
            if override:
                return override
        s = get_settings()
        env_map = {
            "openai": s.openai_base_url,
            "anthropic": s.anthropic_base_url,
            "deepseek": s.deepseek_base_url,
            "alibaba": s.alibaba_base_url,
            "bytedance": s.bytedance_base_url,
            "google": s.google_base_url,
        }
        env_val = env_map.get(provider) or ""
        return env_val or _DEFAULT_BASE_URLS.get(provider, "")

    def get_timeout(self) -> int:
        with self._lock:
            val = self._overrides.get("cloud_api_timeout_seconds", "")
            if val:
                try:
                    return int(val)
                except ValueError:
                    pass
        return int(get_settings().cloud_api_timeout_seconds)

    def is_configured(self, provider: str) -> bool:
        return bool(self.get_api_key(provider))

    def provider_status(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for provider, label in _PROVIDER_LABELS.items():
            key = self.get_api_key(provider)
            result.append(
                {
                    "provider": provider,
                    "label": label,
                    "configured": bool(key),
                    "key_preview": _mask_key(key) if key else None,
                    "default_base_url": _DEFAULT_BASE_URLS[provider],
                }
            )
        return result

    @staticmethod
    def provider_labels() -> dict[str, str]:
        return dict(_PROVIDER_LABELS)

    @staticmethod
    def default_base_urls() -> dict[str, str]:
        return dict(_DEFAULT_BASE_URLS)
