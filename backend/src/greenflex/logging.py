from __future__ import annotations

import logging
import re
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "key",
    "password",
    "prompt",
    "response",
    "secret",
    "token",
    "x-api-key",
    "x_admin_token",
}

# Patterns that look like API keys in free-text log messages
_API_KEY_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_-]{8,})"),
    re.compile(r"(sk-ant-[A-Za-z0-9_-]{8,})"),
    re.compile(r"(AIza[A-Za-z0-9_-]{8,})"),
    re.compile(r'("(?:openai|anthropic|deepseek|alibaba|bytedance|google)_api_key"\s*:\s*")[^"]+(")'),
]


def _redact_text(text: str) -> str:
    """Redact API key patterns from a string."""
    result = text
    for pattern in _API_KEY_PATTERNS:
        if pattern.groups == 2:  # JSON key-value pattern
            result = pattern.sub(r"\1[REDACTED]\2", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


def redact_sensitive(
    _: Any,
    __: str,
    event_dict: MutableMapping[str, Any],
) -> Mapping[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in event_dict.items():
        if key.lower() in SENSITIVE_KEYS:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, str):
            redacted[key] = _redact_text(value)
        else:
            redacted[key] = value
    return redacted


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            redact_sensitive,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
    )
