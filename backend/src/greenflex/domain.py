from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

# Python 3.11+ has StrEnum; for 3.10 compatibility, define our own
if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    class StrEnum(str, Enum):
        """Backport of Python 3.11's StrEnum for 3.10 compatibility."""
        def __str__(self) -> str:
            return self.value


class Provenance(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    SIMULATED = "simulated"


class EnergyDataProvenance(StrEnum):
    """Energy data provenance classification (three-tier + insufficient).

    Only tiers with defensible, extensible data are used for recommendation.
    L4 analytical models and L5 FLOPs estimates are intentionally excluded
    because they lack sufficient validation for reliable scoring.

    L1 LOCAL_MEASURED   — measured on this machine via NVML/nvidia-smi (highest confidence)
    L2 BENCHMARK_MATCH  — exact model-GPU match in public benchmark dataset (JouleBench, etc.)
    L3 CROSS_GPU_NORM   — benchmark data on a different GPU, normalized via efficiency factor
    INSUFFICIENT_DATA   — no L1-L3 data available; model excluded from energy-aware scoring
    """

    L1_LOCAL_MEASURED = "l1_local_measured"
    L2_BENCHMARK_MATCH = "l2_benchmark_match"
    L3_CROSS_GPU_NORMALIZED = "l3_cross_gpu_normalized"
    INSUFFICIENT_DATA = "insufficient_data"


# Confidence baseline per provenance tier (basis points, 0-10000)
ENERGY_PROVENANCE_CONFIDENCE: dict[EnergyDataProvenance, int] = {
    EnergyDataProvenance.L1_LOCAL_MEASURED: 9500,
    EnergyDataProvenance.L2_BENCHMARK_MATCH: 8500,
    EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED: 6500,
    EnergyDataProvenance.INSUFFICIENT_DATA: 0,
}

# Uncertainty penalty multiplier per tier (applied to energy/carbon score in routing)
# Higher tier = more penalty = less likely to be recommended when alternatives exist
# INSUFFICIENT_DATA gets max penalty; these models are typically filtered out before scoring
ENERGY_UNCERTAINTY_PENALTY: dict[EnergyDataProvenance, float] = {
    EnergyDataProvenance.L1_LOCAL_MEASURED: 1.0,
    EnergyDataProvenance.L2_BENCHMARK_MATCH: 1.05,
    EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED: 1.15,
    EnergyDataProvenance.INSUFFICIENT_DATA: 10.0,
}


class ModelTier(StrEnum):
    ECONOMY = "economy"
    BALANCED = "balanced"
    QUALITY = "quality"
    ENTERPRISE = "enterprise"


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


class RecommendationMode(StrEnum):
    """User-facing recommendation mode selector."""

    SMART = "smart"
    ECONOMY = "economy"
    QUALITY = "quality"
    MANUAL = "manual"


class QualityRequirement(StrEnum):
    """User-stated quality requirement for the task."""

    MINIMUM = "minimum"
    STANDARD = "standard"
    HIGH = "high"
    CRITICAL = "critical"


class QualityRiskLevel(StrEnum):
    """Assessed quality risk for a model-task pair."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class TaskType(StrEnum):
    """Detected or user-specified task type."""

    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    SUMMARIZATION = "summarization"
    ANALYSIS = "analysis"
    GENERATION = "generation"
    CODE = "code"
    AUTO = "auto"


class ComplexityLevel(StrEnum):
    ESTIMATED = "estimated"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


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
    source_version: str = "synthetic-cn-east-v2"
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
    return datetime.now(timezone.utc)
