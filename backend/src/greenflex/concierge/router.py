"""FastAPI router for the concierge agent.

Mount this in the main app at /api/v1/concierge.
"""
from __future__ import annotations

import logging
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from greenflex.container import ServiceContainer
from greenflex.db import get_session

from .agent import ConciergeAgent
from .schemas import (
    ConciergeChatRequest,
    ConciergeChatResponse,
    ConciergeHealthResponse,
    ConciergeResetRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/concierge", tags=["concierge"])

# Shared agent instance (memory is in-memory per session_id)
_agent: ConciergeAgent | None = None


def get_agent() -> ConciergeAgent:
    global _agent
    if _agent is None:
        _agent = ConciergeAgent()
    return _agent


def _sync_runtime_settings(agent: ConciergeAgent, container: ServiceContainer) -> None:
    """Ensure the agent's LLM reads keys from the current runtime settings."""
    if container.runtime_settings is not None:
        agent.llm.update_runtime_settings(container.runtime_settings)


def _get_container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContainerDep = Annotated[ServiceContainer, Depends(_get_container)]
AgentDep = Annotated[ConciergeAgent, Depends(get_agent)]


@router.post("/chat", response_model=ConciergeChatResponse)
async def concierge_chat(
    payload: ConciergeChatRequest,
    session: SessionDep,
    container: ContainerDep,
    agent: AgentDep,
) -> ConciergeChatResponse:
    """Send a message to the GreenConcierge agent."""
    _sync_runtime_settings(agent, container)
    reply, mode, tools_used = await agent.chat(
        payload.session_id,
        payload.message,
        db_session=session,
        container=container,
    )
    return ConciergeChatResponse(
        session_id=payload.session_id,
        reply=reply,
        agent_mode=mode,
        tools_used=tools_used,
    )


@router.post("/reset")
async def concierge_reset(
    payload: ConciergeResetRequest, agent: AgentDep
) -> dict:
    """Reset conversation history for a session."""
    agent.reset(payload.session_id)
    return {"status": "ok", "session_id": payload.session_id}


@router.get("/health", response_model=ConciergeHealthResponse)
async def concierge_health(
    agent: AgentDep, container: ContainerDep
) -> ConciergeHealthResponse:
    """Check concierge agent status."""
    _sync_runtime_settings(agent, container)
    return ConciergeHealthResponse(
        status="ok" if agent.llm.available else "degraded",
        llm_available=agent.llm.available,
        llm_provider=agent.llm.provider,
        llm_model=agent.llm.model,
    )
