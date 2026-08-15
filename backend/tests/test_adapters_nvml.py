"""Unit tests for the NVML telemetry provider.

pynvml is mocked via sys.modules injection so the tests run on any platform
without an NVIDIA driver or GPU.
"""

from __future__ import annotations

import sys
import types
from datetime import UTC, datetime
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from greenflex.adapters_nvml import NVMLTelemetryProvider
from greenflex.ports import PowerSample


def _make_fake_pynvml(
    *,
    power_mw: int = 42_750,
    gpu_percent: int = 63,
    memory_bytes: int = 1024 * 1024 * 1024,
    device_count: int = 1,
    init_side_effect: Exception | None = None,
    read_side_effect: Exception | None = None,
) -> ModuleType:
    """Build a fake pynvml module with configurable return values."""
    fake = MagicMock(spec=ModuleType)
    fake.nvmlInit = MagicMock(side_effect=init_side_effect)
    fake.nvmlDeviceGetCount = MagicMock(return_value=device_count)
    fake.nvmlDeviceGetHandleByIndex = MagicMock(return_value=MagicMock(name="gpu-handle"))

    if read_side_effect is not None:
        fake.nvmlDeviceGetPowerUsage = MagicMock(side_effect=read_side_effect)
    else:
        fake.nvmlDeviceGetPowerUsage = MagicMock(return_value=power_mw)

    fake.nvmlDeviceGetUtilizationRates = MagicMock(
        return_value=types.SimpleNamespace(gpu=gpu_percent, memory=0)
    )
    fake.nvmlDeviceGetMemoryInfo = MagicMock(
        return_value=types.SimpleNamespace(used=memory_bytes, total=0, free=0)
    )
    return fake


# ---------------------------------------------------------------------------
# Availability probe
# ---------------------------------------------------------------------------


def test_nvml_provider_reports_available_when_initialized() -> None:
    fake = _make_fake_pynvml()
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider(interval_ms=100)
        assert provider.available is True
        fake.nvmlInit.assert_called_once()
        fake.nvmlDeviceGetCount.assert_called_once()
        fake.nvmlDeviceGetHandleByIndex.assert_called_once_with(0)


def test_nvml_provider_reports_unavailable_when_init_fails() -> None:
    fake = _make_fake_pynvml(init_side_effect=RuntimeError("no driver"))
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider()
        assert provider.available is False


def test_nvml_provider_reports_unavailable_when_gpu_index_out_of_range() -> None:
    fake = _make_fake_pynvml(device_count=0)
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider(gpu_index=0)
        assert provider.available is False


def test_nvml_provider_availability_is_cached() -> None:
    fake = _make_fake_pynvml()
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider()
        assert provider.available is True
        assert provider.available is True  # second access does not re-init
        fake.nvmlInit.assert_called_once()


def test_nvml_provider_source_attribute() -> None:
    assert NVMLTelemetryProvider.source == "nvml"


# ---------------------------------------------------------------------------
# Sample reading
# ---------------------------------------------------------------------------


def test_nvml_provider_reads_sample_with_correct_units() -> None:
    fake = _make_fake_pynvml(power_mw=42_750, gpu_percent=63, memory_bytes=1024 * 1024 * 1024)
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider()
        assert provider.available
        sample = provider._read_sample_sync()

    assert sample is not None
    assert sample.power_mw == 42_750  # NVML returns mW directly — no conversion
    assert sample.utilization_bps == 6_300  # 63% * 100
    assert sample.memory_used_mb == 1024  # 1 GiB → 1024 MiB
    assert sample.captured_at.tzinfo == UTC
    assert sample.captured_at <= datetime.now(UTC)


def test_nvml_provider_read_returns_none_when_unavailable() -> None:
    fake = _make_fake_pynvml(init_side_effect=RuntimeError("no driver"))
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider()
        assert provider.available is False
        assert provider._read_sample_sync() is None


def test_nvml_provider_read_returns_none_on_nvml_error() -> None:
    fake = _make_fake_pynvml(read_side_effect=OSError("gpu lost"))
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider()
        assert provider.available is True
        assert provider._read_sample_sync() is None


def test_nvml_provider_clamps_negative_power() -> None:
    fake = _make_fake_pynvml(power_mw=-5)
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider()
        sample = provider._read_sample_sync()
    assert sample is not None
    assert sample.power_mw == 0


# ---------------------------------------------------------------------------
# Async: idle_power_mw
# ---------------------------------------------------------------------------


async def test_nvml_idle_power_returns_median() -> None:
    # Alternating power values to verify median selection.
    values = [30_000, 50_000, 40_000]
    call_count = 0

    def fake_power(_handle: object) -> int:
        nonlocal call_count
        value = values[call_count % len(values)]
        call_count += 1
        return value

    fake = _make_fake_pynvml()
    fake.nvmlDeviceGetPowerUsage = MagicMock(side_effect=fake_power)
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider(interval_ms=20)
        result = await provider.idle_power_mw(duration_seconds=0.15)

    assert result is not None
    assert result == 40_000  # median of [30000, 40000, 50000]


async def test_nvml_idle_power_returns_none_when_unavailable() -> None:
    fake = _make_fake_pynvml(init_side_effect=RuntimeError("no driver"))
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider()
        assert await provider.idle_power_mw(0.1) is None


# ---------------------------------------------------------------------------
# Async: samples generator
# ---------------------------------------------------------------------------


async def test_nvml_samples_yields_valid_samples() -> None:
    fake = _make_fake_pynvml(power_mw=55_000, gpu_percent=80, memory_bytes=2 * 1024**3)
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider(interval_ms=10)
        gen = provider.samples()
        try:
            first = await anext(gen)
            second = await anext(gen)
        finally:
            await gen.aclose()

    assert isinstance(first, PowerSample)
    assert first.power_mw == 55_000
    assert first.utilization_bps == 8_000
    assert first.memory_used_mb == 2048
    assert isinstance(second, PowerSample)
    assert second.captured_at >= first.captured_at


async def test_nvml_samples_returns_immediately_when_unavailable() -> None:
    fake = _make_fake_pynvml(init_side_effect=RuntimeError("no driver"))
    with patch.dict(sys.modules, {"pynvml": fake}):
        provider = NVMLTelemetryProvider()
        gen = provider.samples()
        with pytest.raises(StopAsyncIteration):
            await anext(gen)
