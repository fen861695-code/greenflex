from __future__ import annotations

import asyncio
import csv
import gzip
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from greenflex.ports import PowerSample, TelemetryProvider


@dataclass(frozen=True, slots=True)
class TelemetryMeasurement:
    source: str
    idle_power_mw: int | None
    average_power_mw: int | None
    peak_power_mw: int | None
    gross_energy_micro_wh: int | None
    incremental_energy_micro_wh: int | None
    duration_seconds: float
    samples: tuple[PowerSample, ...]


class TelemetryCapture:
    def __init__(self, provider: TelemetryProvider, *, idle_seconds: float = 3.0) -> None:
        self._provider = provider
        self._idle_seconds = idle_seconds
        self._samples: list[PowerSample] = []
        self._stop = asyncio.Event()
        self._collector: asyncio.Task[None] | None = None
        self._started_at = 0.0
        self._duration_seconds = 0.0
        self._idle_power_mw: int | None = None

    async def __aenter__(self) -> TelemetryCapture:
        try:
            self._idle_power_mw = await self._provider.idle_power_mw(self._idle_seconds)
        except Exception:
            self._idle_power_mw = None
        self._started_at = time.perf_counter()
        self._collector = asyncio.create_task(self._collect())
        await asyncio.sleep(0)
        return self

    async def __aexit__(self, *_: object) -> None:
        self._duration_seconds = max(0.0, time.perf_counter() - self._started_at)
        self._stop.set()
        if self._collector is not None:
            try:
                await asyncio.wait_for(self._collector, timeout=2.0)
            except TimeoutError:
                self._collector.cancel()
                await asyncio.gather(self._collector, return_exceptions=True)

    async def _collect(self) -> None:
        try:
            async for sample in self._provider.samples():
                self._samples.append(sample)
                if self._stop.is_set():
                    break
        except Exception:
            return

    def measurement(self) -> TelemetryMeasurement:
        powers = [sample.power_mw for sample in self._samples]
        average = round(sum(powers) / len(powers)) if powers else None
        peak = max(powers) if powers else None
        gross = _power_duration_to_micro_wh(average, self._duration_seconds)
        incremental_power = (
            max(0, average - self._idle_power_mw)
            if average is not None and self._idle_power_mw is not None
            else None
        )
        incremental = _power_duration_to_micro_wh(incremental_power, self._duration_seconds)
        return TelemetryMeasurement(
            source=self._provider.source,
            idle_power_mw=self._idle_power_mw,
            average_power_mw=average,
            peak_power_mw=peak,
            gross_energy_micro_wh=gross,
            incremental_energy_micro_wh=incremental,
            duration_seconds=self._duration_seconds,
            samples=tuple(self._samples),
        )


def write_telemetry_artifact(
    samples: tuple[PowerSample, ...],
    artifact_dir: Path,
    artifact_id: str,
) -> tuple[str, str] | None:
    if not samples:
        return None
    directory = artifact_dir / "telemetry"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{artifact_id}.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["captured_at", "power_mw", "utilization_bps", "memory_used_mb"])
        for sample in samples:
            writer.writerow(
                [
                    sample.captured_at.isoformat(),
                    sample.power_mw,
                    sample.utilization_bps,
                    sample.memory_used_mb,
                ]
            )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return str(path), digest


def _power_duration_to_micro_wh(power_mw: int | None, duration_seconds: float) -> int | None:
    if power_mw is None:
        return None
    return max(0, round(power_mw * duration_seconds * 1_000 / 3_600))
