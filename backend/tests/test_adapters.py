"""Tests for adapter helpers and providers."""

from __future__ import annotations

import httpx
import pytest
import respx

from greenflex.adapters import (
    NvidiaSmiTelemetryProvider,
    OllamaInferenceProvider,
    _nanoseconds_to_microseconds,
    _non_negative_int,
    _parse_nvidia_smi_line,
)
from greenflex.ports import GenerationRequest


class TestParseNvidiaSmiLine:
    def test_valid_line(self) -> None:
        sample = _parse_nvidia_smi_line("45.32, 67, 2048\n")
        assert sample is not None
        assert sample.power_mw == 45_320
        assert sample.utilization_bps == 6_700
        assert sample.memory_used_mb == 2048

    def test_zero_values(self) -> None:
        sample = _parse_nvidia_smi_line("0.0, 0, 0\n")
        assert sample is not None
        assert sample.power_mw == 0
        assert sample.utilization_bps == 0
        assert sample.memory_used_mb == 0

    def test_negative_power_clamped_to_zero(self) -> None:
        sample = _parse_nvidia_smi_line("-5.0, 50, 1024\n")
        assert sample is not None
        assert sample.power_mw == 0

    def test_utilization_above_100_clamped(self) -> None:
        sample = _parse_nvidia_smi_line("30.0, 150, 1024\n")
        assert sample is not None
        assert sample.utilization_bps == 10_000

    def test_negative_utilization_clamped(self) -> None:
        sample = _parse_nvidia_smi_line("30.0, -10, 1024\n")
        assert sample is not None
        assert sample.utilization_bps == 0

    def test_invalid_format_returns_none(self) -> None:
        assert _parse_nvidia_smi_line("not,a,valid,line\n") is None

    def test_non_numeric_values_returns_none(self) -> None:
        assert _parse_nvidia_smi_line("N/A, N/A, N/A\n") is None

    def test_empty_line_returns_none(self) -> None:
        assert _parse_nvidia_smi_line("\n") is None

    def test_fractional_utilization(self) -> None:
        sample = _parse_nvidia_smi_line("40.5, 33.5, 512.7\n")
        assert sample is not None
        assert sample.power_mw == 40_500
        assert sample.utilization_bps == 3_350
        assert sample.memory_used_mb == 513


class TestNonNegativeInt:
    def test_positive(self) -> None:
        assert _non_negative_int(42) == 42

    def test_zero(self) -> None:
        assert _non_negative_int(0) == 0

    def test_negative(self) -> None:
        assert _non_negative_int(-5) == 0

    def test_non_int_returns_zero(self) -> None:
        assert _non_negative_int("not an int") == 0
        assert _non_negative_int(None) == 0
        assert _non_negative_int(3.14) == 0


class TestNanosecondsToMicroseconds:
    def test_positive(self) -> None:
        assert _nanoseconds_to_microseconds(1_000_000) == 1_000

    def test_zero_returns_one(self) -> None:
        assert _nanoseconds_to_microseconds(0) == 1

    def test_negative_returns_one(self) -> None:
        assert _nanoseconds_to_microseconds(-5000) == 1

    def test_non_int_returns_one(self) -> None:
        assert _nanoseconds_to_microseconds("not an int") == 1
        assert _nanoseconds_to_microseconds(None) == 1

    def test_small_value_returns_one(self) -> None:
        assert _nanoseconds_to_microseconds(500) == 1  # 500ns // 1000 = 0 → max(1, 0) = 1


class TestNvidiaSmiTelemetryProvider:
    def test_source_attribute(self) -> None:
        provider = NvidiaSmiTelemetryProvider()
        assert provider.source == "nvidia-smi"

    @pytest.mark.asyncio
    async def test_idle_power_returns_none_without_executable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("greenflex.adapters.shutil.which", lambda _: None)
        provider = NvidiaSmiTelemetryProvider()
        result = await provider.idle_power_mw(duration_seconds=0.1)
        assert result is None

    @pytest.mark.asyncio
    async def test_samples_empty_without_executable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("greenflex.adapters.shutil.which", lambda _: None)
        provider = NvidiaSmiTelemetryProvider()
        samples = [s async for s in provider.samples()]
        assert samples == []


class TestOllamaInferenceProvider:
    def test_base_url_trailing_slash_stripped(self) -> None:
        provider = OllamaInferenceProvider("http://localhost:11434/")
        assert provider._base_url == "http://localhost:11434"

    @pytest.mark.asyncio
    @respx.mock
    async def test_available_models_parses_response(self) -> None:
        route = respx.get("http://localhost:11434/api/tags").mock(
            return_value=httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "qwen2.5:0.5b", "digest": "abc123"},
                        {"name": "qwen2.5:1.5b", "digest": "def456"},
                    ]
                },
            )
        )
        provider = OllamaInferenceProvider("http://localhost:11434")
        models = await provider.available_models()
        assert route.called
        assert models == {"qwen2.5:0.5b": "abc123", "qwen2.5:1.5b": "def456"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_available_models_returns_empty_on_error(self) -> None:
        respx.get("http://localhost:11434/api/tags").mock(return_value=httpx.Response(500))
        provider = OllamaInferenceProvider("http://localhost:11434")
        models = await provider.available_models()
        assert models == {}

    @pytest.mark.asyncio
    @respx.mock
    async def test_generate_returns_result(self) -> None:
        respx.post("http://localhost:11434/api/generate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "response": "Hello, world!",
                    "prompt_eval_count": 10,
                    "eval_count": 5,
                    "total_duration": 1_000_000_000,  # 1 second in ns
                },
            )
        )
        provider = OllamaInferenceProvider("http://localhost:11434")
        request = GenerationRequest(
            model_name="qwen2.5:0.5b",
            prompt="Hi",
            system_prompt=None,
            max_output_tokens=32,
            temperature=0.7,
        )
        result = await provider.generate(request)
        assert result.output == "Hello, world!"
        assert result.prompt_tokens == 10
        assert result.output_tokens == 5
        assert result.duration_us == 1_000_000

    @pytest.mark.asyncio
    @respx.mock
    async def test_generate_with_system_prompt(self) -> None:
        route = respx.post("http://localhost:11434/api/generate").mock(
            return_value=httpx.Response(200, json={"response": "ok"})
        )
        provider = OllamaInferenceProvider("http://localhost:11434")
        request = GenerationRequest(
            model_name="qwen2.5:0.5b",
            prompt="Hi",
            system_prompt="You are helpful.",
            max_output_tokens=32,
            temperature=0.7,
        )
        await provider.generate(request)
        sent = route.calls.last.request.content
        assert b"system" in sent
        assert b"You are helpful." in sent
