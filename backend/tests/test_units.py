"""Unit tests for unit conversion helpers."""

from __future__ import annotations

from greenflex.units import (
    basis_points_to_percent,
    joules_per_output_token,
    micro_to_decimal_string,
    micro_wh_to_carbon_micro_g,
)


class TestMicroToDecimalString:
    def test_zero(self) -> None:
        assert micro_to_decimal_string(0) == "0.000000"

    def test_one_million(self) -> None:
        assert micro_to_decimal_string(1_000_000) == "1.000000"

    def test_fractional(self) -> None:
        assert micro_to_decimal_string(500_000) == "0.500000"

    def test_custom_places(self) -> None:
        assert micro_to_decimal_string(1_500_000, places=2) == "1.50"

    def test_large_value(self) -> None:
        assert micro_to_decimal_string(123_456_789) == "123.456789"


class TestBasisPointsToPercent:
    def test_zero(self) -> None:
        assert basis_points_to_percent(0) == "0.00"

    def test_one_percent(self) -> None:
        assert basis_points_to_percent(100) == "1.00"

    def test_fifty_percent(self) -> None:
        assert basis_points_to_percent(5000) == "50.00"

    def test_hundred_percent(self) -> None:
        assert basis_points_to_percent(10000) == "100.00"

    def test_fractional_percent(self) -> None:
        assert basis_points_to_percent(150) == "1.50"


class TestMicroWhToCarbonMicroG:
    def test_zero_energy(self) -> None:
        assert micro_wh_to_carbon_micro_g(0, 550) == 0

    def test_one_kwh_at_550g(self) -> None:
        # 1 kWh = 1,000,000,000 micro-Wh; at 550 g/kWh = 550,000,000 micro-g
        assert micro_wh_to_carbon_micro_g(1_000_000_000, 550) == 550_000_000

    def test_proportional(self) -> None:
        assert micro_wh_to_carbon_micro_g(500_000_000, 550) == 275_000_000

    def test_low_carbon_grid(self) -> None:
        assert micro_wh_to_carbon_micro_g(1_000_000_000, 187) == 187_000_000


class TestJoulesPerOutputToken:
    def test_zero_tokens_returns_none(self) -> None:
        assert joules_per_output_token(100_000, 0) is None

    def test_negative_tokens_returns_none(self) -> None:
        assert joules_per_output_token(100_000, -5) is None

    def test_one_token_one_wh(self) -> None:
        # 1 Wh = 3,600,000,000 micro-Wh; 1 token → 3600 J
        # micro_joules = 3,600,000,000 * 3600 = 12,960,000,000,000
        # / 1 token = 12,960,000,000,000 micro-J = 12,960,000 J
        # Wait, let me recalculate:
        # energy_micro_wh = 3,600,000,000 (1 Wh)
        # micro_joules = 3,600,000,000 * 3600 = 12,960,000,000,000
        # / 1 = 12,960,000,000,000 micro-J = 12,960,000 J
        # places=4 → "12960000.0000"
        result = joules_per_output_token(3_600_000_000, 1)
        assert result == "12960000.0000"

    def test_typical_inference(self) -> None:
        # 64,000 micro-Wh (0.064 Wh) for 128 tokens
        # micro_joules = 64000 * 3600 = 230,400,000
        # / 128 = 1,800,000 micro-J = 1.8 J
        result = joules_per_output_token(64_000, 128)
        assert result == "1.8000"

    def test_high_energy(self) -> None:
        # 250,000 micro-Wh (0.25 Wh) for 100 tokens
        # micro_joules = 250000 * 3600 = 900,000,000
        # / 100 = 9,000,000 micro-J = 9.0 J
        result = joules_per_output_token(250_000, 100)
        assert result == "9.0000"

    def test_zero_energy(self) -> None:
        assert joules_per_output_token(0, 100) == "0.0000"

    def test_integer_division_truncates(self) -> None:
        # 100 micro-Wh * 3600 = 360,000 micro-J / 7 tokens = 51,428 micro-J
        result = joules_per_output_token(100, 7)
        assert result == "0.0514"
