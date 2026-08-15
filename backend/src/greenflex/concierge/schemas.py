"""Concierge API request/response models."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ConciergeChatRequest(BaseModel):
    """User chat request to the concierge agent."""

    session_id: str = Field(
        default="default",
        description="Session ID for conversation history isolation",
        min_length=1,
        max_length=64,
    )
    message: str = Field(
        ...,
        description="User message",
        min_length=1,
        max_length=8192,
    )


class ConciergeChatResponse(BaseModel):
    """Concierge agent reply."""

    session_id: str
    reply: str
    agent_mode: str = Field(
        default="llm",
        description="Agent mode used: 'llm' (function-calling) or 'rule' (fallback)",
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="Tools called during this turn",
    )


class ConciergeResetRequest(BaseModel):
    """Reset a conversation session."""

    session_id: str = Field(default="default", min_length=1, max_length=64)


class ConciergeHealthResponse(BaseModel):
    """Concierge health status."""

    status: str
    llm_available: bool
    llm_provider: str
    llm_model: str
