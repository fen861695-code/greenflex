"""Tests for the carbon calendar and grid region API endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signals_regions_returns_all_seven_regions(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/signals/regions")
    assert response.status_code == 200
    payload = response.json()

    assert "current" in payload
    assert "regions" in payload
    assert len(payload["regions"]) == 7

    codes = {r["code"] for r in payload["regions"]}
    expected = {
        "CN-North",
        "CN-Northeast",
        "CN-East",
        "CN-Central",
        "CN-South",
        "CN-Northwest",
        "CN-Southwest",
    }
    assert codes == expected

    # Default region is CN-East
    assert payload["current"] == "CN-East"

    # Southwest has the lowest carbon (hydro-heavy)
    southwest = next(r for r in payload["regions"] if r["code"] == "CN-Southwest")
    assert southwest["carbon_g_per_kwh"] < 250
    assert southwest["renewable_share_bps"] >= 7000


@pytest.mark.asyncio
async def test_signals_calendar_default_seven_days(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/signals/calendar")
    assert response.status_code == 200
    payload = response.json()

    assert payload["region"] == "CN-East"
    assert "signal_version" in payload
    assert len(payload["days"]) == 7

    for day in payload["days"]:
        assert "date" in day
        assert len(day["hours"]) == 24
        for hour in day["hours"]:
            assert 0 <= hour["hour"] <= 23
            assert hour["carbon_g_per_kwh"] > 0
            assert hour["price_micro_rmb_per_kwh"] > 0
            assert 0 <= hour["renewable_share_bps"] <= 10000


@pytest.mark.asyncio
async def test_signals_calendar_custom_days(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/signals/calendar", params={"days": 3})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["days"]) == 3


@pytest.mark.asyncio
async def test_signals_calendar_max_fourteen_days(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/signals/calendar", params={"days": 14})
    assert response.status_code == 200
    assert len(response.json()["days"]) == 14


@pytest.mark.asyncio
async def test_signals_calendar_rejects_days_above_max(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/signals/calendar", params={"days": 15})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_signals_calendar_rejects_days_below_min(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/signals/calendar", params={"days": 0})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_signals_calendar_custom_region(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get(
        "/api/v1/signals/calendar",
        params={"region": "CN-Southwest"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["region"] == "CN-Southwest"

    # Southwest carbon should be lower than East baseline
    first_hour = payload["days"][0]["hours"][12]  # noon
    assert first_hour["carbon_g_per_kwh"] < 300


@pytest.mark.asyncio
async def test_signals_calendar_invalid_region_falls_back_to_default(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get(
        "/api/v1/signals/calendar",
        params={"region": "INVALID-REGION"},
    )
    assert response.status_code == 200
    # Invalid region is ignored; falls back to container default (CN-East)
    assert response.json()["region"] == "CN-East"


@pytest.mark.asyncio
async def test_signals_calendar_midday_lower_carbon_than_evening(
    api_client: AsyncClient,
) -> None:
    """Solar generation should make midday carbon lower than evening peak."""
    response = await api_client.get("/api/v1/signals/calendar")
    payload = response.json()
    first_day = payload["days"][0]

    noon = next(h for h in first_day["hours"] if h["hour"] == 12)
    evening = next(h for h in first_day["hours"] if h["hour"] == 20)

    # Midday should have more renewable (solar) → lower carbon
    assert noon["renewable_share_bps"] > evening["renewable_share_bps"]
    assert noon["carbon_g_per_kwh"] < evening["carbon_g_per_kwh"]


@pytest.mark.asyncio
async def test_signals_calendar_deep_valley_lowest_price(
    api_client: AsyncClient,
) -> None:
    """11-14 deep valley should have the lowest electricity price."""
    response = await api_client.get("/api/v1/signals/calendar")
    payload = response.json()
    first_day = payload["days"][0]

    prices = {h["hour"]: h["price_micro_rmb_per_kwh"] for h in first_day["hours"]}

    # Deep valley 11-14 should be cheaper than peak 19-21
    assert prices[12] < prices[20]
    assert prices[13] < prices[19]
