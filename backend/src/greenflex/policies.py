from __future__ import annotations

from datetime import UTC, datetime, timedelta

from greenflex.domain import DomainError, EnergySignal, ExecutionMode, ScheduleSlot
from greenflex.ports import EnergySignalProvider


class TieredPricingPolicy:
    version = "pricing-sim-v1"

    def discount_bps(self, mode: ExecutionMode, flexibility_seconds: int) -> int:
        if mode is ExecutionMode.IMMEDIATE:
            return 0
        hours = flexibility_seconds / 3600
        if hours >= 8:
            return 1_500
        if hours >= 4:
            return 1_000
        if hours >= 1:
            return 500
        return 0

    def settle_micro_rmb(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        input_rate: int,
        output_rate: int,
        discount_bps: int,
    ) -> int:
        base = (input_tokens * input_rate + output_tokens * output_rate) // 1_000_000
        return base - (base * discount_bps // 10_000)


class LowestImpactSlotPolicy:
    def __init__(self, signals: EnergySignalProvider) -> None:
        self.signals = signals

    def choose_slot(
        self,
        *,
        mode: ExecutionMode,
        now: datetime,
        runtime_seconds: int,
        deadline: datetime | None,
    ) -> ScheduleSlot:
        aware_now = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        runtime = timedelta(seconds=max(runtime_seconds, 1))

        if mode is ExecutionMode.IMMEDIATE:
            signal = self.signals.signal_at(aware_now)
            return ScheduleSlot(start=aware_now, end=aware_now + runtime, signal=signal)

        if deadline is None:
            raise DomainError("deadline_required", "弹性订单必须设置截止时间。")
        aware_deadline = deadline if deadline.tzinfo is not None else deadline.replace(tzinfo=UTC)
        latest_start = aware_deadline - runtime
        if latest_start < aware_now:
            raise DomainError("no_feasible_schedule", "当前时间无法在截止时间前完成任务。", 409)

        candidates = self.signals.signals_between(aware_now, latest_start)
        if not candidates:
            raise DomainError("no_feasible_schedule", "没有可用的调度时间槽。", 409)

        def score(typed: EnergySignal) -> tuple[int, int, datetime]:
            return (
                typed.price_micro_rmb_per_kwh + typed.carbon_g_per_kwh * 1_000,
                -typed.renewable_share_bps,
                typed.interval_start,
            )

        selected = min(candidates, key=score)
        return ScheduleSlot(
            start=selected.interval_start,
            end=selected.interval_start + runtime,
            signal=selected,
        )
