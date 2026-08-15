"""Short-term conversation memory per session.

In-memory storage with automatic truncation. Can be swapped for Redis/SQLite
in the future without changing the agent interface.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

_MAX_MESSAGE_CHARS = 4000
_MAX_TURNS = 10


@dataclass
class Message:
    role: str  # system / user / assistant / tool
    content: str | None = None
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls is not None:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


class ConversationMemory:
    """Manages conversation history per session_id."""

    def __init__(self, system_prompt: str) -> None:
        self._system_prompt = system_prompt
        self._sessions: dict[str, list[Message]] = defaultdict(list)

    def add(
        self, session_id: str, role: str, content: str | None = None, **kwargs: Any
    ) -> None:
        if content and len(content) > _MAX_MESSAGE_CHARS:
            content = content[:_MAX_MESSAGE_CHARS] + "\n...(truncated)"
        self._sessions[session_id].append(
            Message(role=role, content=content, **kwargs)
        )
        self._truncate(session_id)

    def add_raw(self, session_id: str, message: Message) -> None:
        if message.content and len(message.content) > _MAX_MESSAGE_CHARS:
            message.content = message.content[:_MAX_MESSAGE_CHARS] + "\n...(truncated)"
        self._sessions[session_id].append(message)
        self._truncate(session_id)

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        history = self._sessions.get(session_id, [])
        return [{"role": "system", "content": self._system_prompt}] + [
            m.to_dict() for m in history
        ]

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _truncate(self, session_id: str) -> None:
        history = self._sessions[session_id]
        max_messages = _MAX_TURNS * 2 + 4
        while len(history) > max_messages:
            first_user_idx = next(
                (i for i, m in enumerate(history) if m.role == "user"), 0
            )
            del history[: first_user_idx + 1]
