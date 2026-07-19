from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from greenflex.config import get_settings
from greenflex.container import build_container
from greenflex.domain import DomainError
from greenflex.logging import configure_logging
from greenflex.routes import router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    app = FastAPI(
        title="GreenFlex API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.container = build_container()
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    app.include_router(router)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Correlation-ID"],
    )

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
    async def metrics() -> str:
        return "greenflex_up 1\n"

    return app


app = create_app()
