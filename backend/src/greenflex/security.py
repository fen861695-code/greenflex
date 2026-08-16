from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

RequestHandler = Callable[[Request], Awaitable[Response]]

RATE_LIMITS = {
    "/api/v1/previews": 20,
    "/api/v1/quotes": 30,
    "/api/v1/quotes/upload": 10,
    "/api/v1/chat": 30,
    "/api/v1/concierge/chat": 20,
    "/api/v1/settings/cloud-api": 10,
}
BODY_LIMITS = {
    "/api/v1/previews": 128 * 1024,
    "/api/v1/quotes": 6 * 1024 * 1024,
    "/api/v1/quotes/upload": 6 * 1024 * 1024,
    "/api/v1/chat": 256 * 1024,
    "/api/v1/concierge/chat": 32 * 1024,
    "/api/v1/settings/cloud-api": 16 * 1024,
}


class LocalSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._requests: defaultdict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        path = request.url.path
        limit = BODY_LIMITS.get(path)
        content_length = request.headers.get("content-length")
        if limit is not None and content_length is not None:
            try:
                too_large = int(content_length) > limit
            except ValueError:
                too_large = True
            if too_large:
                return _error(413, "request_too_large", "请求体超过允许大小。")

        rate = RATE_LIMITS.get(path)
        if rate is not None:
            client = request.client.host if request.client is not None else "local"
            key = (client, path)
            now = time.monotonic()
            window = self._requests[key]
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= rate:
                return _error(429, "rate_limit_exceeded", "请求过于频繁, 请稍后重试。")
            window.append(now)

        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response


def _error(status: int, code: str, message: str) -> JSONResponse:
    response = JSONResponse(status_code=status, content={"code": code, "message": message})
    response.headers["Cache-Control"] = "no-store"
    return response
