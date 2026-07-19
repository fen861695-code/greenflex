from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class Provenance(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    SIMULATED = "simulated"


class ModelTier(StrEnum):
    ECONOMY = "economy"
    BALANCED = "balanced"
    QUALITY = "quality"


class ExecutionMode(StrEnum):
    IMMEDIATE = "immediate"
    FLEXIBLE = "flexible"


class OrderStatus(StrEnum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ItemStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


TERMINAL_ORDER_STATUSES = {
    OrderStatus.SUCCEEDED,
    OrderStatus.PARTIAL_SUCCESS,
    OrderStatus.FAILED,
    OrderStatus.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class EnergySignal:
    interval_start: datetime
    price_micro_rmb_per_kwh: int
    carbon_g_per_kwh: int
    renewable_share_bps: int
    source_version: str = "synthetic-cn-east-v1"
    provenance: Provenance = Provenance.SIMULATED


@dataclass(frozen=True, slots=True)
class ScheduleSlot:
    start: datetime
    end: datetime
    signal: EnergySignal


class DomainError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def utc_now() -> datetime:
    return datetime.now(UTC)
