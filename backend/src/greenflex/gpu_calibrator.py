"""GPU energy efficiency calibration.

Implements the "calibrate one model, benefit all models" mechanism:
  1. User runs a model locally → measured energy data captured
  2. Compare measured vs. benchmark/analytical estimate for same model
  3. Compute efficiency_factor correction for this GPU
  4. Apply factor to ALL other model estimates (L3/L4 tiers)

This solves the core problem: user can only run a few models locally, but
those measurements calibrate the entire model catalog's energy estimates.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from greenflex.domain import EnergyDataProvenance
from greenflex.energy_estimator import EnergyEstimator, _normalize_gpu_name
from greenflex.models import GpuEnergyProfileRecord, ModelRecord


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    """Result of a GPU calibration update."""

    gpu_model: str
    old_efficiency_factor: float
    new_efficiency_factor: float
    sample_count: int
    measured_energy_micro_wh_per_1k: int
    expected_energy_micro_wh_per_1k: int
    correction_ratio: float
    confidence_bps: int


class GpuCalibrator:
    """Calibrates GPU energy efficiency factor from local measurements.

    The efficiency_factor represents how this GPU's actual efficiency
    compares to the reference GPU used in benchmark data.
      factor = 1.0 → same as reference
      factor < 1.0 → more efficient (uses less energy than predicted)
      factor > 1.0 → less efficient (uses more energy than predicted)

    Calibration uses exponential moving average to be robust to outliers:
      new_factor = old_factor * (1 - alpha) + measured_ratio * alpha
    where alpha decreases as sample count grows.
    """

    def __init__(
        self,
        *,
        estimator: EnergyEstimator,
        gpu_profiles: Sequence[GpuEnergyProfileRecord] = (),
        local_gpu_model: str = "rtx-3060-laptop",
    ) -> None:
        self._estimator = estimator
        self._profiles = {p.gpu_model.lower(): p for p in gpu_profiles}
        self._local_gpu = _normalize_gpu_name(local_gpu_model)

    def calibrate_from_measurement(
        self,
        *,
        model: ModelRecord,
        measured_energy_micro_wh_per_1k: int,
        measured_tokens_per_second: int,
        gpu_model: str | None = None,
    ) -> CalibrationResult:
        """Update GPU efficiency factor from a local measurement.

        Compare measured energy to what the estimator would have predicted
        for this model (without calibration), then adjust the factor.
        """
        gpu = _normalize_gpu_name(gpu_model) if gpu_model else self._local_gpu
        profile = self._profiles.get(gpu)

        # Get the uncalibrated estimate (temporarily reset factor)
        expected = self._estimator.estimate(model)
        expected_energy = expected.energy_micro_wh_per_1k_output

        # Compute correction ratio
        if expected_energy <= 0:
            correction_ratio = 1.0
        else:
            correction_ratio = measured_energy_micro_wh_per_1k / expected_energy

        # Clamp ratio to reasonable range (avoid wild corrections from bad data)
        correction_ratio = max(0.3, min(3.0, correction_ratio))

        # Exponential moving average with sample-count-dependent alpha
        old_factor = profile.efficiency_factor if profile else 1.0
        sample_count = profile.calibration_sample_count if profile else 0
        alpha = min(0.5, 10.0 / (sample_count + 10))  # starts at 0.5, decays
        new_factor = old_factor * (1 - alpha) + correction_ratio * alpha
        new_factor = max(0.3, min(3.0, new_factor))

        # Confidence increases with sample count
        confidence_bps = min(9000, 3000 + sample_count * 500)

        return CalibrationResult(
            gpu_model=gpu,
            old_efficiency_factor=old_factor,
            new_efficiency_factor=new_factor,
            sample_count=sample_count + 1,
            measured_energy_micro_wh_per_1k=measured_energy_micro_wh_per_1k,
            expected_energy_micro_wh_per_1k=expected_energy,
            correction_ratio=correction_ratio,
            confidence_bps=confidence_bps,
        )

    def build_profile_record(
        self,
        *,
        gpu_model: str,
        efficiency_factor: float,
        sample_count: int,
        tdp_watts: int | None = None,
        memory_bandwidth_gbps: float | None = None,
        compute_tflops_fp16: float | None = None,
    ) -> GpuEnergyProfileRecord:
        """Create or update a GpuEnergyProfileRecord."""
        now = datetime.now(timezone.utc)
        gpu = _normalize_gpu_name(gpu_model)
        existing = self._profiles.get(gpu)

        if existing:
            existing.efficiency_factor = efficiency_factor
            existing.calibration_sample_count = sample_count
            existing.last_calibrated_at = now
            existing.calibration_provenance = "local_measured"
            existing.updated_at = now
            return existing

        return GpuEnergyProfileRecord(
            id=str(uuid.uuid4()),
            gpu_model=gpu,
            tdp_watts=tdp_watts,
            memory_bandwidth_gbps=memory_bandwidth_gbps,
            compute_tflops_fp16=compute_tflops_fp16,
            efficiency_factor=efficiency_factor,
            calibration_sample_count=sample_count,
            last_calibrated_at=now,
            calibration_provenance="local_measured",
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def promote_model_to_l1(
        model: ModelRecord,
        *,
        measured_energy_micro_wh_per_1k: int,
        measured_tokens_per_second: int,
        source_note: str = "local NVML measurement",
    ) -> None:
        """Promote a model's energy data to L1 (local measured) after calibration.

        Updates the model record in-place with measured values and L1 provenance.
        """
        model.estimated_energy_micro_wh_per_1k_output = measured_energy_micro_wh_per_1k
        model.estimated_tokens_per_second = measured_tokens_per_second
        model.energy_data_provenance = EnergyDataProvenance.L1_LOCAL_MEASURED
        model.energy_confidence_bps = 9500
        model.energy_data_source = source_note
        model.reference_gpu_model = "local"
