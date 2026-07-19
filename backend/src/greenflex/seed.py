from __future__ import annotations

import asyncio

from greenflex.catalog import seed_catalog
from greenflex.db import SessionFactory


async def seed() -> None:
    async with SessionFactory() as session:
        await seed_catalog(session)


def main() -> None:  # pragma: no cover - process entry point
    asyncio.run(seed())


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
