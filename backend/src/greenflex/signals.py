from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from greenflex.domain import EnergySignal


@dataclass(frozen=True, slots=True)
class GridRegion:
    code: str
    name_zh: str
    carbon_g_per_kwh: int
    renewable_share_bps: int


# 2023 official MEE regional grid baseline factors
# (生态环境部 2026-01 announcement)
GRID_REGIONS: dict[str, GridRegion] = {
    "CN-North": GridRegion("CN-North", "华北电网", 623, 2500),
    "CN-Northeast": GridRegion("CN-Northeast", "东北电网", 526, 3000),
    "CN-East": GridRegion("CN-East", "华东电网", 550, 3000),
    "CN-Central": GridRegion("CN-Central", "华中电网", 493, 3500),
    "CN-South": GridRegion("CN-South", "南方电网", 523, 3200),
    "CN-Northwest": GridRegion("CN-Northwest", "西北电网", 432, 4800),
    "CN-Southwest": GridRegion("CN-Southwest", "西南电网", 187, 7500),
}

DEFAULT_REGION_CODE = "CN-East"


class SyntheticEnergySignalProvider:
    """Deterministic 15-minute digital-twin signal for China regional grids.

    Price tiers reference 2026 Shanghai/Jiangsu industrial TOU tariffs
    (沪发改价管﹝2022﹞50号, 2026-07 agency purchase prices):
      - Deep valley (midday PV peak): ~0.29 yuan/kWh
      - Valley (night): ~0.41 yuan/kWh
      - Flat: ~0.66 yuan/kWh
      - Peak: ~0.90 yuan/kWh
      - Sharp peak (summer evening): ~1.12 yuan/kWh

    Carbon baselines use 2023 official MEE regional grid factors.
    Renewable share varies by region (hydro-rich Southwest lowest carbon).
    Time-of-day variation models solar midday boost and wind overnight.

    All values are simulated for local development; never presented as
    real-time grid data.
    """

    def __init__(self, region: str = DEFAULT_REGION_CODE) -> None:
        self._region = GRID_REGIONS.get(region, GRID_REGIONS[DEFAULT_REGION_CODE])
        self.version = f"synthetic-{self._region.code.lower()}-v2"

    @property
    def region(self) -> GridRegion:
        return self._region

    @staticmethod
    def available_regions() -> list[GridRegion]:
        return list(GRID_REGIONS.values())

    def signal_at(self, instant: datetime) -> EnergySignal:
        aware = instant if instant.tzinfo is not None else instant.replace(tzinfo=UTC)
        local_hour = aware.astimezone().hour

        # TOU price tiers (micro-RMB per kWh)
        if 19 <= local_hour < 21:
            price = 1_120_000
        elif 11 <= local_hour < 14:
            price = 290_000
        elif (8 <= local_hour < 11) or (14 <= local_hour < 19) or (21 <= local_hour < 22):
            price = 900_000
        elif 23 <= local_hour or local_hour < 7:
            price = 410_000
        else:
            price = 660_000

        # Renewable share: regional baseline + solar midday + wind overnight
        solar_boost = max(0, 5 - abs(local_hour - 13)) * 500
        wind_boost = 400 if local_hour < 6 or local_hour >= 22 else 0
        renewable_bps = min(
            9_500,
            self._region.renewable_share_bps + solar_boost + wind_boost,
        )

        # Carbon: regional baseline reduced by above-baseline renewable penetration
        # Each 10% above baseline -> ~5% carbon reduction
        baseline = self._region.renewable_share_bps
        extra_renewable = max(0, renewable_bps - baseline)
        carbon_reduction = self._region.carbon_g_per_kwh * extra_renewable // 20_000
        carbon = max(120, self._region.carbon_g_per_kwh - carbon_reduction)

        slot_minute = (aware.minute // 15) * 15
        start = aware.replace(minute=slot_minute, second=0, microsecond=0)
        return EnergySignal(
            interval_start=start,
            price_micro_rmb_per_kwh=price,
            carbon_g_per_kwh=carbon,
            renewable_share_bps=renewable_bps,
        )

    def signals_between(self, start: datetime, end: datetime) -> Sequence[EnergySignal]:
        cursor = start.replace(minute=(start.minute // 15) * 15, second=0, microsecond=0)
        result: list[EnergySignal] = []
        while cursor <= end:
            result.append(self.signal_at(cursor))
            cursor += timedelta(minutes=15)
        return result
