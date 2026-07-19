import asyncio

from sqlalchemy import text

from greenflex.config import Settings
from greenflex.db import get_session
from greenflex.logging import redact_sensitive
from greenflex.worker import run


def test_settings_exposes_sync_database_url() -> None:
    settings = Settings(database_url="sqlite+aiosqlite:///./data/test.db")
    assert settings.sync_database_url == "sqlite:///./data/test.db"


def test_sensitive_log_values_are_redacted() -> None:
    result = redact_sensitive(None, "event", {"authorization": "private", "status": "ok"})
    assert result == {"authorization": "[REDACTED]", "status": "ok"}


async def test_session_factory_executes_sql() -> None:
    async for session in get_session():
        value = await session.scalar(text("SELECT 1"))
        assert value == 1


async def test_worker_accepts_a_stop_event() -> None:
    event = asyncio.Event()
    event.set()
    await run(event)
