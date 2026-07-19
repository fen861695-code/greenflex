from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from greenflex.domain import EnergySignal


class SyntheticEnergySignalProvider:
    """Deterministic 15-minute digital-twin signal; never presented as real grid data."""

    version = "synthetic-cn-east-v1"

    def signal_at(self, instant: datetime) -> EnergySignal:
        aware = instant if instant.tzinfo is not None else instant.replace(tzinfo=UTC)
        local_hour = aware.astimezone().hour

        if 0 <= local_hour < 8 or local_hour >= 22:
            price = 350_000
        elif 11 <= local_hour < 13 or 17 <= local_hour < 22:
            price = 1_200_000
        else:
            price = 800_000

        solar_effect = max(0, 6 - abs(local_hour - 13))
        wind_effect = 3 if local_hour < 6 or local_hour >= 22 else 0
        renewable_bps = min(8_500, 2_200 + solar_effect * 800 + wind_effect * 550)
        carbon = max(180, 650 - renewable_bps // 14)

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
