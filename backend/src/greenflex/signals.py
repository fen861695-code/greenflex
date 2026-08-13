from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
UTC = timezone.utc

from greenflex.domain import EnergySignal


class SyntheticEnergySignalProvider:
    """Deterministic 15-minute digital-twin signal calibrated for East China grid.

    Price tiers reference 2026 Shanghai/Jiangsu industrial TOU tariffs
    (沪发改价管﹝2022﹞50号, 2026-07 agency purchase prices):
      - Deep valley (midday PV peak): ~0.29 元/kWh
      - Valley (night): ~0.41 元/kWh
      - Flat: ~0.66 元/kWh
      - Peak: ~0.90 元/kWh
      - Sharp peak (summer evening): ~1.12 元/kWh

    Carbon baseline: East China grid 2023 official factor = 550 gCO₂/kWh
    (生态环境部 2026-01 announcement), trending toward ~500 g by 2026 Q3.
    Renewable share ranges 20-50% (midday solar peak higher).

    All values are simulated for local development; never presented as
    real-time grid data.
    """

    version = "synthetic-cn-east-v2"

    def signal_at(self, instant: datetime) -> EnergySignal:
        aware = instant if instant.tzinfo is not None else instant.replace(tzinfo=UTC)
        local_hour = aware.astimezone().hour

        # TOU price tiers (micro-RMB per kWh), calibrated to East China 2026
        if 19 <= local_hour < 21:
            # Sharp peak (summer evening demand)
            price = 1_120_000
        elif 11 <= local_hour < 14:
            # Midday deep valley (solar PV oversupply)
            price = 290_000
        elif (8 <= local_hour < 11) or (14 <= local_hour < 19) or (21 <= local_hour < 22):
            # Peak
            price = 900_000
        elif 23 <= local_hour or local_hour < 7:
            # Night valley
            price = 410_000
        else:
            # Flat (7-8, 22-23)
            price = 660_000

        # Renewable share: higher midday (solar) and overnight (wind)
        # Range 20% (2000 bps) to 50% (5000 bps)
        solar_boost = max(0, 5 - abs(local_hour - 13)) * 500  # peak at 13:00
        wind_boost = 400 if local_hour < 6 or local_hour >= 22 else 0
        renewable_bps = min(5_000, 2_000 + solar_boost + wind_boost)

        # Carbon: baseline 550 g/kWh, reduced by renewable penetration
        # Each 10% renewable → ~55 g reduction (grid average displacement)
        carbon_reduction = renewable_bps * 55 // 1000
        carbon = max(180, 550 - carbon_reduction)

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
