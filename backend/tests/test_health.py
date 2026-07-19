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
