from __future__ import annotations

import asyncio
import socket

from greenflex.config import get_settings
from greenflex.container import build_container
from greenflex.db import SessionFactory
from greenflex.execution import PersistentOrderWorker
from greenflex.logging import configure_logging


async def run(stop_event: asyncio.Event | None = None) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker = PersistentOrderWorker(
        SessionFactory,
        build_container(),
        settings,
        owner=f"{socket.gethostname()}-{id(asyncio.current_task())}",
    )
    await worker.run(stop_event or asyncio.Event())


def main() -> None:  # pragma: no cover - process entry point
    asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
