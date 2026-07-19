from __future__ import annotations

import asyncio

import structlog

from greenflex.config import get_settings
from greenflex.logging import configure_logging


async def run(stop_event: asyncio.Event | None = None) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger("greenflex.worker")
    logger.info("worker_started")
    await (stop_event or asyncio.Event()).wait()


def main() -> None:  # pragma: no cover - process entry point
    asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
