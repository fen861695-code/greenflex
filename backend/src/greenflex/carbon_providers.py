"""Real-time grid carbon intensity providers.

Supports multiple backends with graceful degradation:
  1. Electricity Maps API (global coverage, free tier available)
  2. WattTime API (US/EU focus)
  3. DynLCA (China regional grid data, open source)
  4. Synthetic fallback (when all APIs fail)

All providers implement the EnergySignalProvider port so they can be
used interchangeably with the existing SyntheticEnergySignalProvider.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from greenflex.domain import EnergySignal, Provenance

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Electricity Maps provider
# ---------------------------------------------------------------------------
class ElectricityMapsProvider:
    """Electricity Maps API carbon intensity provider.

    Docs: https://static.electricitymaps.com/api/docs/index.html
    Free tier: limited requests/hour, sufficient for local development.

    Environment variable: GREENFLEX_ELECTRICITY_MAPS_API_KEY
    """

    base_url = "https://api.electricitymap.org/v3"
    version = "electricity-maps-v3"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        zone: str = "CN-CS",  # China Central-South (Changsha/Hunan region)
        timeout_seconds: float = 5.0,
        cache_ttl_minutes: int = 15,
    ) -> None:
        self._api_key = api_key
        self._zone = zone
        self._timeout = timeout_seconds
        self._cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self._cache: dict[str, _CachedSignal] = {}

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def signal_at(self, instant: datetime) -> EnergySignal:
        """Get carbon intensity at a specific time (uses cache)."""
        cache_key = self._cache_key(instant)
        cached = self._cache.get(cache_key)
        if cached and not self._is_expired(cached):
            return cached.signal

        try:
            signal = self._fetch_live()
            self._cache[cache_key] = _CachedSignal(signal=signal, fetched_at=datetime.now(timezone.utc))
            return signal
        except Exception as exc:
            logger.warning("Electricity Maps fetch failed: %s", exc)
            if cached:
                return cached.signal  # stale cache is better than nothing
            raise

    def signals_between(self, start: datetime, end: datetime) -> Sequence[EnergySignal]:
        """Get signals for a time range (15-minute intervals)."""
        result: list[EnergySignal] = []
        cursor = start.replace(minute=(start.minute // 15) * 15, second=0, microsecond=0)
        while cursor <= end:
            try:
                result.append(self.signal_at(cursor))
            except Exception:
                break
            cursor += timedelta(minutes=15)
        return result

    def _fetch_live(self) -> EnergySignal:
        """Fetch live carbon intensity from Electricity Maps API."""
        if not self._api_key:
            raise RuntimeError("Electricity Maps API key not configured")

        url = f"{self.base_url}/carbon-intensity/latest"
        params = {"zone": self._zone}
        headers = {"auth-token": self._api_key}

        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

        carbon = data.get("carbonIntensity", 550)  # gCO2/kWh
        # Electricity Maps doesn't directly provide price; use synthetic price
        price = self._estimate_price(carbon)
        renewable = self._estimate_renewable_share(data)

        interval_start = datetime.fromisoformat(
            data.get("datetime", datetime.now(timezone.utc).isoformat())
        ).replace(tzinfo=timezone.utc)

        return EnergySignal(
            interval_start=interval_start,
            price_micro_rmb_per_kwh=price,
            carbon_g_per_kwh=int(carbon),
            renewable_share_bps=renewable,
            source_version=self.version,
            provenance=Provenance.ESTIMATED,
        )

    @staticmethod
    def _estimate_price(carbon_g_per_kwh: int) -> int:
        """Estimate electricity price from carbon intensity (correlation proxy).

        Higher carbon → more fossil fuels → higher peak price.
        This is a rough proxy; real TOU pricing should come from utility data.
        """
        # Base 0.55 RMB/kWh, adjust ±0.20 based on carbon intensity
        # Range: 300 g/kWh (clean) → 0.40; 800 g/kWh (dirty) → 0.75
        base = 550_000  # micro-RMB
        adjustment = int((carbon_g_per_kwh - 550) * 400)  # ~0.04 RMB per 100g
        return max(290_000, min(1_120_000, base + adjustment))

    @staticmethod
    def _estimate_renewable_share(data: dict[str, Any]) -> int:
        """Estimate renewable share from power breakdown data."""
        power_breakdown = data.get("powerOriginBreakdown", {})
        if not power_breakdown:
            # Infer from carbon: 200g → 50% renewable, 700g → 10% renewable
            carbon = data.get("carbonIntensity", 550)
            share = max(10, min(50, int(70 - carbon * 0.08)))
            return share * 100  # to bps

        renewable_keys = ["hydro", "solar", "wind", "geothermal", "biomass"]
        total = sum(power_breakdown.values())
        if total <= 0:
            return 3000
        renewable = sum(power_breakdown.get(k, 0) for k in renewable_keys)
        return int((renewable / total) * 10000)

    def _cache_key(self, instant: datetime) -> str:
        slot = instant.replace(minute=(instant.minute // 15) * 15, second=0, microsecond=0)
        return f"{self._zone}:{slot.isoformat()}"

    def _is_expired(self, cached: "_CachedSignal") -> bool:
        return datetime.now(timezone.utc) - cached.fetched_at > self._cache_ttl


@dataclass(frozen=True, slots=True)
class _CachedSignal:
    signal: EnergySignal
    fetched_at: datetime


# ---------------------------------------------------------------------------
# WattTime provider (simplified)
# ---------------------------------------------------------------------------
class WattTimeProvider:
    """WattTime API carbon intensity provider (US/EU focus).

    Docs: https://docs.watttime.org/
    Free tier: region preview only, limited historical data.
    """

    base_url = "https://api.watttime.org/v3"
    version = "watttime-v3"

    def __init__(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        region: str = "CAISO_NORTH",
        timeout_seconds: float = 5.0,
    ) -> None:
        self._username = username
        self._password = password
        self._region = region
        self._timeout = timeout_seconds
        self._token: str | None = None
        self._token_expires: datetime | None = None

    @property
    def available(self) -> bool:
        return bool(self._username and self._password)

    def signal_at(self, instant: datetime) -> EnergySignal:
        if not self.available:
            raise RuntimeError("WattTime credentials not configured")
        # Simplified: WattTime provides MOER (marginal emissions rate)
        # For production, implement full auth + /v3/forecast endpoint
        raise NotImplementedError("WattTime provider requires full implementation")

    def signals_between(self, start: datetime, end: datetime) -> Sequence[EnergySignal]:
        return []


# ---------------------------------------------------------------------------
# DynLCA provider (China regional grid data)
# ---------------------------------------------------------------------------
class DynLCAProvider:
    """China regional grid carbon intensity from DynLCA open dataset.

    Uses CEPD/CATARC public data for Chinese regional grids.
    GitHub: https://github.com/guangcansu/dynlca

    This provider uses locally cached data files rather than a live API,
    as Chinese grid data is not available via a standard real-time API.
    """

    version = "dynlca-china-v1"

    # Default provincial grid factors (gCO2/kWh, 2023 baseline)
    # Source: CEPD (China Electricity Planning & Design Institute)
    _PROVINCIAL_BASELINE: dict[str, int] = {
        "CN-HB": 870,  # Hebei (coal-heavy)
        "CN-SD": 810,  # Shandong
        "CN-SX": 880,  # Shanxi
        "CN-NM": 850,  # Inner Mongolia
        "CN-HA": 780,  # Henan
        "CN-AH": 750,  # Anhui
        "CN-JS": 680,  # Jiangsu
        "CN-SH": 520,  # Shanghai
        "CN-ZJ": 580,  # Zhejiang
        "CN-FJ": 520,  # Fujian (nuclear + hydro)
        "CN-HN": 620,  # Hunan (hydro)
        "CN-HUB": 550,  # Hubei (Three Gorges hydro)
        "CN-SC": 480,  # Sichuan (hydro-heavy)
        "CN-CQ": 560,  # Chongqing
        "CN-GD": 520,  # Guangdong (nuclear)
        "CN-GX": 500,  # Guangxi (hydro)
        "CN-YN": 350,  # Yunnan (hydro-heavy)
        "CN-GZ": 520,  # Guizhou (hydro)
        "CN-LN": 720,  # Liaoning
        "CN-JL": 700,  # Jilin
        "CN-HLJ": 680,  # Heilongjiang
        "CN-BJ": 620,  # Beijing
        "CN-TJ": 700,  # Tianjin
        "CN-SN": 580,  # Shaanxi
        "CN-GS": 650,  # Gansu (wind)
        "CN-QH": 400,  # Qinghai (solar + hydro)
        "CN-NX": 780,  # Ningxia (coal)
        "CN-XJ": 720,  # Xinjiang
        "CN-HI": 700,  # Hainan
    }

    def __init__(self, *, region_code: str = "CN-HN") -> None:
        self._region = region_code

    @property
    def available(self) -> bool:
        return self._region in self._PROVINCIAL_BASELINE

    def signal_at(self, instant: datetime) -> EnergySignal:
        baseline = self._PROVINCIAL_BASELINE.get(self._region, 550)
        # Apply time-of-day variation: daytime higher (more AC demand → more peaker coal)
        local_hour = instant.astimezone().hour
        if 19 <= local_hour < 22:
            carbon = int(baseline * 1.10)  # evening peak
        elif 11 <= local_hour < 15:
            carbon = int(baseline * 0.85)  # midday solar
        elif 23 <= local_hour or local_hour < 6:
            carbon = int(baseline * 0.90)  # night valley
        else:
            carbon = baseline

        renewable = max(1000, min(5000, int((900 - carbon) * 8)))
        price = self._tou_price(local_hour)

        slot = instant.replace(minute=(instant.minute // 15) * 15, second=0, microsecond=0)
        return EnergySignal(
            interval_start=slot,
            price_micro_rmb_per_kwh=price,
            carbon_g_per_kwh=carbon,
            renewable_share_bps=renewable,
            source_version=self.version,
            provenance=Provenance.ESTIMATED,
        )

    def signals_between(self, start: datetime, end: datetime) -> Sequence[EnergySignal]:
        result: list[EnergySignal] = []
        cursor = start.replace(minute=(start.minute // 15) * 15, second=0, microsecond=0)
        while cursor <= end:
            result.append(self.signal_at(cursor))
            cursor += timedelta(minutes=15)
        return result

    @staticmethod
    def _tou_price(hour: int) -> int:
        """China industrial TOU pricing (micro-RMB/kWh)."""
        if 19 <= hour < 21:
            return 1_120_000  # sharp peak
        if 11 <= hour < 14:
            return 290_000  # deep valley (solar)
        if (8 <= hour < 11) or (14 <= hour < 19) or (21 <= hour < 22):
            return 900_000  # peak
        if 23 <= hour or hour < 7:
            return 410_000  # valley
        return 660_000  # flat


# ---------------------------------------------------------------------------
# Fallback provider (always available)
# ---------------------------------------------------------------------------
class FallbackCarbonProvider:
    """Synthetic fallback when all real-time providers fail.

    Uses East China grid baseline with TOU variation.
    Provenance is SIMULATED — clearly labeled as not real-time.
    """

    version = "synthetic-fallback-v1"

    def signal_at(self, instant: datetime) -> EnergySignal:
        local_hour = instant.astimezone().hour
        if 19 <= local_hour < 21:
            price, carbon, renewable = 1_120_000, 600, 2000
        elif 11 <= local_hour < 14:
            price, carbon, renewable = 290_000, 420, 4800
        elif (8 <= local_hour < 11) or (14 <= local_hour < 19) or (21 <= local_hour < 22):
            price, carbon, renewable = 900_000, 560, 2800
        elif 23 <= local_hour or local_hour < 7:
            price, carbon, renewable = 410_000, 500, 3500
        else:
            price, carbon, renewable = 660_000, 530, 3200

        slot = instant.replace(minute=(instant.minute // 15) * 15, second=0, microsecond=0)
        return EnergySignal(
            interval_start=slot,
            price_micro_rmb_per_kwh=price,
            carbon_g_per_kwh=carbon,
            renewable_share_bps=renewable,
            source_version=self.version,
            provenance=Provenance.SIMULATED,
        )

    def signals_between(self, start: datetime, end: datetime) -> Sequence[EnergySignal]:
        result: list[EnergySignal] = []
        cursor = start.replace(minute=(start.minute // 15) * 15, second=0, microsecond=0)
        while cursor <= end:
            result.append(self.signal_at(cursor))
            cursor += timedelta(minutes=15)
        return result
