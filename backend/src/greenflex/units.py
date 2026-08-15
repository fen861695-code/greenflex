from __future__ import annotations

from decimal import Decimal

MICRO = Decimal(1_000_000)


def micro_to_decimal_string(value: int, places: int = 6) -> str:
    quantizer = Decimal(1).scaleb(-places)
    return str((Decimal(value) / MICRO).quantize(quantizer))


def basis_points_to_percent(value: int) -> str:
    return str((Decimal(value) / Decimal(100)).quantize(Decimal("0.01")))


def micro_wh_to_carbon_micro_g(energy_micro_wh: int, carbon_g_per_kwh: int) -> int:
    return energy_micro_wh * carbon_g_per_kwh // 1_000


def joules_per_output_token(energy_micro_wh: int, output_tokens: int) -> str | None:
    """Return gross energy in joules per output token, or None if no tokens."""
    if output_tokens <= 0:
        return None
    # 1 Wh = 3600 J, so 1 micro-Wh = 3600 micro-J
    micro_joules = energy_micro_wh * 3_600
    return micro_to_decimal_string(micro_joules // output_tokens, places=4)
