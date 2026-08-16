"""NVML-based telemetry provider for high-frequency GPU power sampling.

Uses the NVIDIA Management Library (pynvml / nvidia-ml-py) to read GPU power,
utilization, and memory directly at 10 Hz (100 ms intervals) -- 5x faster than
the nvidia-smi subprocess fallback. Falls back gracefully when NVML is
unavailable (no driver, no GPU, or unsupported platform).
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from greenflex.ports import PowerSample, TelemetryProvider

_LOGGER = logging.getLogger(__name__)


class NVMLTelemetryProvider:
    """Telemetry provider backed by NVML direct register reads.

    Implements the :class:`TelemetryProvider` protocol. NVML returns power in
    milliwatts directly, so no unit conversion is needed. Sampling is dispatched
    to a worker thread via :func:`asyncio.to_thread` so the event loop is never
    blocked by the synchronous NVML calls.
    """

    source = "nvml"

    def __init__(self, *, interval_ms: int = 100, gpu_index: int = 0) -> None:
        self._interval_ms = interval_ms
        self._gpu_index = gpu_index
        self._handle: object | None = None
        self._checked = False
        self._available = False

    @property
    def available(self) -> bool:
        """Return True if NVML initialised and a GPU handle was obtained."""
        self._ensure_checked()
        return self._available

    def _ensure_checked(self) -> None:
        if self._checked:
            return
        self._checked = True
        try:
            import pynvml  # type: ignore[import-untyped]

            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            if self._gpu_index >= count:
                return
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(self._gpu_index)
            self._available = True
        except Exception:
            self._available = False
            self._handle = None
            _LOGGER.debug("NVML not available, falling back to nvidia-smi", exc_info=True)

    def _read_sample_sync(self) -> PowerSample | None:
        self._ensure_checked()
        if self._handle is None:
            return None
        try:
            import pynvml

            power_mw = int(pynvml.nvmlDeviceGetPowerUsage(self._handle))
            util = pynvml.nvmlDeviceGetUtilizationRates(self._handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
            return PowerSample(
                captured_at=datetime.now(UTC),
                power_mw=max(0, power_mw),
                utilization_bps=max(0, min(10_000, int(util.gpu) * 100)),
                memory_used_mb=max(0, int(mem.used // 1024 // 1024)),
            )
        except Exception:
            _LOGGER.debug("NVML sample read failed", exc_info=True)
            return None

    async def idle_power_mw(self, duration_seconds: float = 3.0) -> int | None:
        self._ensure_checked()
        if not self._available:
            return None
        values: list[int] = []
        deadline = asyncio.get_running_loop().time() + duration_seconds
        while True:
            sample = await asyncio.to_thread(self._read_sample_sync)
            if sample is not None:
                values.append(sample.power_mw)
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(self._interval_ms / 1000, remaining))
        return int(statistics.median(values)) if values else None

    async def samples(self) -> AsyncGenerator[PowerSample]:
        self._ensure_checked()
        if not self._available:
            return
        interval = self._interval_ms / 1000
        while True:
            sample = await asyncio.to_thread(self._read_sample_sync)
            if sample is not None:
                yield sample
            await asyncio.sleep(interval)


# Structural subtyping check: NVMLTelemetryProvider satisfies TelemetryProvider.
_: type[TelemetryProvider] = NVMLTelemetryProvider
