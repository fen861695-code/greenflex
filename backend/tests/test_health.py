from httpx import ASGITransport, AsyncClient

from greenflex.api import create_app


async def test_live_health() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health/live")
        ready = await client.get("/health/ready")
        metrics = await client.get("/metrics")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert ready.json() == {"status": "ready"}
    assert metrics.text == "greenflex_up 1\n"
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_security_middleware_rejects_oversized_preview() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/previews",
            headers={"Content-Length": str(129 * 1024)},
            json={"model_id": "fixture", "prompt": "synthetic-input"},
        )
    assert response.status_code == 413
    assert response.json()["code"] == "request_too_large"
