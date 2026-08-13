from datetime import datetime, timedelta, timezone
UTC = timezone.utc

from httpx import AsyncClient
from pytest import MonkeyPatch


async def test_catalog_lists_three_local_models(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/models")
    assert response.status_code == 200
    payload = response.json()
    # v2 expanded catalog: at least one model per tier
    tiers = {item["tier"] for item in payload}
    assert "economy" in tiers
    assert "balanced" in tiers
    assert "quality" in tiers
    assert all(item["available"] is False for item in payload)


async def test_quote_order_and_cancel_flow(
    api_client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    monkeypatch.setattr("greenflex.services.utc_now", lambda: now)
    deadline = now + timedelta(hours=9)
    quote_response = await api_client.post(
        "/api/v1/quotes",
        json={
            "items": [
                {
                    "client_item_id": "item-001",
                    "prompt": "总结绿色算力的主要价值。",
                    "max_output_tokens": 128,
                }
            ],
            "deadline": deadline.isoformat(),
        },
    )
    assert quote_response.status_code == 200
    options = quote_response.json()["options"]
    # v2 expanded catalog: more models, more options
    assert len(options) >= 6
    flexible = next(
        option
        for option in options
        if option["model_id"] == "qwen2.5-0.5b-q4" and option["execution_mode"] == "flexible"
    )
    assert flexible["discount_percent"] == "15.00"
    assert flexible["commercial_provenance"] == "simulated"

    created = await api_client.post("/api/v1/orders", json={"quote_id": flexible["quote_id"]})
    assert created.status_code == 200
    order = created.json()
    assert order["status"] == "scheduled"
    assert order["created_at"].endswith("Z")
    assert order["items"][0]["output"] is None

    repeated = await api_client.post("/api/v1/orders", json={"quote_id": flexible["quote_id"]})
    assert repeated.json()["id"] == order["id"]

    cancelled = await api_client.post(f"/api/v1/orders/{order['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    purged = await api_client.delete(f"/api/v1/orders/{order['id']}/content")
    assert purged.status_code == 200
    assert purged.json()["content_purged"] is True


async def test_preview_reports_unavailable_runtime(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/previews",
        json={"model_id": "qwen2.5-0.5b-q4", "prompt": "hello"},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "inference_unavailable"


async def test_quote_rejects_duplicate_client_ids(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/quotes",
        json={
            "items": [
                {"client_item_id": "same", "prompt": "one"},
                {"client_item_id": "same", "prompt": "two"},
            ]
        },
    )
    assert response.status_code == 422
