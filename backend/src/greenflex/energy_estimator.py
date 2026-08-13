"""Five-tier energy estimation system for GreenRouter.

Resolves model energy data through five confidence tiers:
  L1 LOCAL_MEASURED   — measured on this machine (highest confidence)
  L2 BENCHMARK_MATCH  — exact model-GPU match in public benchmark dataset
  L3 CROSS_GPU_NORM   — benchmark on different GPU, normalized via efficiency factor
  L4 ANALYTICAL_MODEL — WattGPU-style prediction from model metadata + GPU specs
  L5 FLOPS_ESTIMATE   — coarse FLOPs-based estimate (fallback only)

Each resolution returns an EnergyEstimate with provenance tier, confidence,
and the raw data source description. GreenRouter uses the uncertainty
penalty to weight lower-confidence data less heavily.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from greenflex.domain import (
    ENERGY_PROVENANCE_CONFIDENCE,
    ENERGY_UNCERTAINTY_PENALTY,
    EnergyDataProvenance,
)
from greenflex.models import GpuEnergyProfileRecord, ModelEnergyBenchmarkRecord, ModelRecord


@dataclass(frozen=True, slots=True)
class EnergyEstimate:
    """Resolved energy estimate with full provenance metadata."""

    energy_micro_wh_per_1k_output: int
    tokens_per_second: int
    provenance: EnergyDataProvenance
    confidence_bps: int
    uncertainty_penalty: float
    source_description: str
    reference_gpu: str | None = None
    parameter_count_b: float | None = None


# ---------------------------------------------------------------------------
# GPU specification database (factory specs for common consumer/datacenter GPUs)
# Used by L4 analytical model when no calibration data exists.
# ---------------------------------------------------------------------------
_GPU_SPECS: dict[str, dict] = {
    # Consumer GPUs
    "rtx-3060": {"tdp_w": 170, "bw_gbps": 360, "tflops_fp16": 24.0, "arch": "ampere"},
    "rtx-3060-laptop": {"tdp_w": 115, "bw_gbps": 336, "tflops_fp16": 19.2, "arch": "ampere"},
    "rtx-3070": {"tdp_w": 220, "bw_gbps": 448, "tflops_fp16": 39.7, "arch": "ampere"},
    "rtx-3080": {"tdp_w": 320, "bw_gbps": 760, "tflops_fp16": 59.5, "arch": "ampere"},
    "rtx-3090": {"tdp_w": 350, "bw_gbps": 936, "tflops_fp16": 71.0, "arch": "ampere"},
    "rtx-4050": {"tdp_w": 115, "bw_gbps": 256, "tflops_fp16": 19.2, "arch": "ada"},
    "rtx-4060": {"tdp_w": 115, "bw_gbps": 272, "tflops_fp16": 22.9, "arch": "ada"},
    "rtx-4060-ti": {"tdp_w": 160, "bw_gbps": 288, "tflops_fp16": 31.8, "arch": "ada"},
    "rtx-4070": {"tdp_w": 200, "bw_gbps": 504, "tflops_fp16": 40.6, "arch": "ada"},
    "rtx-4070-ti": {"tdp_w": 285, "bw_gbps": 504, "tflops_fp16": 51.0, "arch": "ada"},
    "rtx-4080": {"tdp_w": 320, "bw_gbps": 717, "tflops_fp16": 65.4, "arch": "ada"},
    "rtx-4090": {"tdp_w": 450, "bw_gbps": 1008, "tflops_fp16": 82.6, "arch": "ada"},
    # Datacenter GPUs
    "a100-40gb": {"tdp_w": 400, "bw_gbps": 1555, "tflops_fp16": 312, "arch": "ampere"},
    "a100-80gb": {"tdp_w": 400, "bw_gbps": 2039, "tflops_fp16": 312, "arch": "ampere"},
    "h100-sxm": {"tdp_w": 700, "bw_gbps": 3350, "tflops_fp16": 1979, "arch": "hopper"},
    "h100-pcie": {"tdp_w": 350, "bw_gbps": 2000, "tflops_fp16": 989, "arch": "hopper"},
    "h200": {"tdp_w": 700, "bw_gbps": 4800, "tflops_fp16": 1979, "arch": "hopper"},
    "b200": {"tdp_w": 1000, "bw_gbps": 8000, "tflops_fp16": 4500, "arch": "blackwell"},
}

# Reference GPU for benchmark normalization (RTX 4060 Ti — common in consumer benchmarks)
_REFERENCE_GPU = "rtx-4060-ti"


def _parse_parameter_count(param_str: str) -> float | None:
    """Parse parameter count string like '0.5B', '7B', '14B' to float billions."""
    if not param_str:
        return None
    s = param_str.strip().upper().replace(" ", "")
    try:
        if s.endswith("T"):
            return float(s[:-1]) * 1000
        if s.endswith("B"):
            return float(s[:-1])
        if s.endswith("M"):
            return float(s[:-1]) / 1000
        return float(s) / 1e9
    except (ValueError, IndexError):
        return None


def _normalize_gpu_name(raw: str) -> str:
    """Normalize GPU name string to lookup key."""
    if not raw:
        return ""
    s = raw.lower().strip()
    s = s.replace("nvidia ", "").replace("geforce ", "").replace("rtx ", "rtx-")
    s = s.replace(" ", "-").replace("_", "-")
    # Handle common variants
    s = s.replace("rtx-3060-mobile", "rtx-3060-laptop")
    s = s.replace("rtx-4060ti", "rtx-4060-ti")
    s = s.replace("rtx-4070ti", "rtx-4070-ti")
    return s


class EnergyEstimator:
    """Five-tier energy estimation engine.

    Usage:
        estimator = EnergyEstimator(benchmarks, gpu_profiles, local_gpu_model)
        estimate = estimator.estimate(model_record, output_tokens=256)
    """

    def __init__(
        self,
        *,
        benchmarks: Sequence[ModelEnergyBenchmarkRecord] = (),
        gpu_profiles: Sequence[GpuEnergyProfileRecord] = (),
        local_gpu_model: str = "rtx-3060-laptop",
    ) -> None:
        self._benchmarks = list(benchmarks)
        self._gpu_profiles = {p.gpu_model.lower(): p for p in gpu_profiles}
        self._local_gpu = _normalize_gpu_name(local_gpu_model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def estimate(
        self,
        model: ModelRecord,
        *,
        output_tokens: int = 256,
        input_tokens: int = 512,
    ) -> EnergyEstimate:
        """Resolve energy estimate through L1-L3 tiers only.

        L4 analytical models and L5 FLOPs estimates are intentionally excluded
        because they lack sufficient validation for reliable scoring.
        Models without L1-L3 data receive INSUFFICIENT_DATA and are typically
        filtered out of energy-aware recommendation.
        """
        param_count = model.parameter_count_b or _parse_parameter_count(model.parameter_b)

        # Tier L1: local measured (stored directly on model record)
        if model.energy_data_provenance == EnergyDataProvenance.L1_LOCAL_MEASURED:
            return EnergyEstimate(
                energy_micro_wh_per_1k_output=model.estimated_energy_micro_wh_per_1k_output,
                tokens_per_second=model.estimated_tokens_per_second,
                provenance=EnergyDataProvenance.L1_LOCAL_MEASURED,
                confidence_bps=model.energy_confidence_bps
                or ENERGY_PROVENANCE_CONFIDENCE[EnergyDataProvenance.L1_LOCAL_MEASURED],
                uncertainty_penalty=ENERGY_UNCERTAINTY_PENALTY[
                    EnergyDataProvenance.L1_LOCAL_MEASURED
                ],
                source_description=model.energy_data_source or "local NVML measurement",
                reference_gpu=self._local_gpu,
                parameter_count_b=param_count,
            )

        # Tier L2: exact model-GPU benchmark match
        l2 = self._find_benchmark_match(model, exact_gpu=True)
        if l2 is not None:
            energy = self._benchmark_to_micro_wh(l2)
            return EnergyEstimate(
                energy_micro_wh_per_1k_output=energy,
                tokens_per_second=int(l2.throughput_tokens_per_second),
                provenance=EnergyDataProvenance.L2_BENCHMARK_MATCH,
                confidence_bps=l2.confidence_bps,
                uncertainty_penalty=ENERGY_UNCERTAINTY_PENALTY[
                    EnergyDataProvenance.L2_BENCHMARK_MATCH
                ],
                source_description=f"{l2.dataset_source} benchmark: {l2.gpu_model}",
                reference_gpu=l2.gpu_model,
                parameter_count_b=param_count,
            )

        # Tier L3: cross-GPU benchmark + normalization
        l3 = self._find_benchmark_match(model, exact_gpu=False)
        if l3 is not None:
            raw_energy = self._benchmark_to_micro_wh(l3)
            norm_factor = self._gpu_efficiency_normalization(l3.gpu_model)
            energy = int(raw_energy * norm_factor)
            tps = int(l3.throughput_tokens_per_second / norm_factor)
            return EnergyEstimate(
                energy_micro_wh_per_1k_output=energy,
                tokens_per_second=max(1, tps),
                provenance=EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED,
                confidence_bps=min(
                    l3.confidence_bps,
                    ENERGY_PROVENANCE_CONFIDENCE[EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED],
                ),
                uncertainty_penalty=ENERGY_UNCERTAINTY_PENALTY[
                    EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED
                ],
                source_description=(
                    f"{l3.dataset_source} on {l3.gpu_model}, "
                    f"normalized to {self._local_gpu} (factor={norm_factor:.2f})"
                ),
                reference_gpu=l3.gpu_model,
                parameter_count_b=param_count,
            )

        # No L1-L3 data available: return insufficient data marker
        # These models should be filtered out before energy-aware scoring
        return EnergyEstimate(
            energy_micro_wh_per_1k_output=10_000_000,  # 10 Wh/1k placeholder (max penalty)
            tokens_per_second=1,
            provenance=EnergyDataProvenance.INSUFFICIENT_DATA,
            confidence_bps=0,
            uncertainty_penalty=ENERGY_UNCERTAINTY_PENALTY[
                EnergyDataProvenance.INSUFFICIENT_DATA
            ],
            source_description="Insufficient benchmark data for reliable estimate",
            reference_gpu=None,
            parameter_count_b=param_count,
        )

    # ------------------------------------------------------------------
    # Tier L2/L3: benchmark lookup
    # ------------------------------------------------------------------
    def _find_benchmark_match(
        self, model: ModelRecord, *, exact_gpu: bool
    ) -> ModelEnergyBenchmarkRecord | None:
        """Find closest benchmark entry by model family + parameter count.

        For L2 exact match (exact_gpu=True): 20% param tolerance + quantization match.
        For L3 cross-GPU match (exact_gpu=False): 50% param tolerance, no quantization
        restriction (quantization difference is handled by normalization).
        """
        param_count = model.parameter_count_b or _parse_parameter_count(model.parameter_b)
        if param_count is None:
            return None

        model_family = self._extract_model_family(model.id)
        candidates: list[tuple[float, ModelEnergyBenchmarkRecord]] = []

        # L2 uses strict 20% tolerance; L3 uses relaxed 50% for family interpolation
        param_tolerance = 0.20 if exact_gpu else 0.50

        for bench in self._benchmarks:
            # Match model family (e.g., 'qwen2.5' matches 'qwen2.5-7b')
            if model_family and bench.model_family.lower() not in model_family.lower():
                if model_family.lower() not in bench.model_family.lower():
                    continue
            # Parameter count tolerance
            if abs(bench.parameter_count_b - param_count) / param_count > param_tolerance:
                continue
            # Quantization match only for L2 exact match
            if exact_gpu and model.quantization_bits and bench.quantization_bits:
                if abs(model.quantization_bits - bench.quantization_bits) > 2:
                    continue
            if exact_gpu:
                if _normalize_gpu_name(bench.gpu_model) != self._local_gpu:
                    continue
            # Score: closer param count = better
            param_diff = abs(bench.parameter_count_b - param_count)
            candidates.append((param_diff, bench))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    @staticmethod
    def _extract_model_family(model_id: str) -> str:
        """Extract family name like 'qwen2.5' from 'qwen2.5-7b-q4'."""
        parts = model_id.replace("cloud-", "").split("-")
        if len(parts) >= 2:
            return parts[0]
        return model_id

    @staticmethod
    def _benchmark_to_micro_wh(bench: ModelEnergyBenchmarkRecord) -> int:
        """Convert benchmark Wh/1k to micro-Wh/1k."""
        return int(bench.energy_wh_per_1k_output * 1_000_000)

    # ------------------------------------------------------------------
    # Tier L3: GPU efficiency normalization
    # ------------------------------------------------------------------
    def _gpu_efficiency_normalization(self, source_gpu: str) -> float:
        """Compute energy normalization factor from source GPU to local GPU.

        Factor < 1.0 means local GPU is more efficient (less energy).
        Based on memory bandwidth ratio (inference is memory-bound for decode).
        """
        source = _normalize_gpu_name(source_gpu)
        source_specs = _GPU_SPECS.get(source)
        local_specs = _GPU_SPECS.get(self._local_gpu)

        if source_specs is None or local_specs is None:
            # Fallback: use calibrated profile if available
            source_profile = self._gpu_profiles.get(source)
            local_profile = self._gpu_profiles.get(self._local_gpu)
            if source_profile and local_profile:
                return local_profile.efficiency_factor / source_profile.efficiency_factor
            return 1.0

        # Inference decode is memory-bandwidth-bound: energy ∝ 1/bandwidth
        # But also affected by TDP (power ceiling). Use geometric mean.
        bw_ratio = source_specs["bw_gbps"] / local_specs["bw_gbps"]
        tdp_ratio = source_specs["tdp_w"] / local_specs["tdp_w"]
        factor = math.sqrt(bw_ratio * tdp_ratio)

        # Apply calibration offset if local GPU has been calibrated
        local_profile = self._gpu_profiles.get(self._local_gpu)
        if local_profile and local_profile.calibration_sample_count > 0:
            factor *= local_profile.efficiency_factor

        return max(0.3, min(3.0, factor))

    # ------------------------------------------------------------------
    # Tier L4: WattGPU-style analytical model
    # ------------------------------------------------------------------
    def _analytical_estimate(self, param_count_b: float, quant_bits: int) -> dict:
        """Predict energy using model metadata + GPU specs (WattGPU approach).

        Key insight from WattGPU (arXiv 2607.02391): inference power and
        latency can be predicted from:
          - Model: parameter count, quantization, architecture
          - GPU: memory bandwidth, TDP, compute throughput

        Decode phase is memory-bound: each token requires loading all parameters.
        Energy ∝ (params × bytes_per_param) / memory_bandwidth × power
        """
        local_specs = _GPU_SPECS.get(self._local_gpu, _GPU_SPECS["rtx-3060-laptop"])
        bw_gbps = local_specs["bw_gbps"]
        tdp_w = local_specs["tdp_w"]

        # Bytes loaded per token = params × bytes_per_param (quantized)
        bytes_per_param = quant_bits / 8.0
        bytes_per_token = param_count_b * 1e9 * bytes_per_param

        # Time per token (decode) = bytes / bandwidth (seconds)
        # Add overhead factor for KV cache and attention
        time_per_token_s = (bytes_per_token / (bw_gbps * 1e9)) * 1.8

        # Average power during inference = 60-80% of TDP (memory-bound workload)
        # Small models use less of TDP; larger models approach saturation
        power_utilization = min(0.85, 0.4 + 0.05 * math.log10(max(1, param_count_b)))
        avg_power_w = tdp_w * power_utilization

        # Energy per token (Joules) = power × time
        energy_j_per_token = avg_power_w * time_per_token_s

        # Convert to Wh per 1k tokens
        energy_wh_per_1k = energy_j_per_token * 1000 / 3600
        energy_micro_wh_per_1k = int(energy_wh_per_1k * 1_000_000)

        # Throughput
        tokens_per_second = max(1, int(1.0 / time_per_token_s))

        # Apply calibration factor
        local_profile = self._gpu_profiles.get(self._local_gpu)
        if local_profile and local_profile.calibration_sample_count > 0:
            energy_micro_wh_per_1k = int(
                energy_micro_wh_per_1k * local_profile.efficiency_factor
            )

        return {
            "energy_micro_wh_per_1k": max(10_000, energy_micro_wh_per_1k),
            "tokens_per_second": tokens_per_second,
        }

    # ------------------------------------------------------------------
    # Tier L5: FLOPs-based coarse estimate
    # ------------------------------------------------------------------
    @staticmethod
    def _flops_estimate(param_count_b: float) -> dict:
        """Coarse estimate from FLOPs count (lowest confidence).

        FLOPs/token ≈ 2 × N_params (each param does ~1 multiply + ~1 add).
        Energy = FLOPs / GPU_efficiency (FLOPs/Joule).
        Consumer GPU efficiency ~ 5-20 GFLOPs/J (varies by utilization).
        """
        flops_per_token = 2 * param_count_b * 1e9
        # Conservative efficiency for consumer GPU at moderate utilization
        gflops_per_joule = 8.0
        energy_j_per_token = flops_per_token / (gflops_per_joule * 1e9)
        energy_wh_per_1k = energy_j_per_token * 1000 / 3600
        energy_micro_wh_per_1k = int(energy_wh_per_1k * 1_000_000)

        # Rough throughput estimate (very coarse)
        tokens_per_second = max(1, int(50 / math.sqrt(max(1, param_count_b))))

        return {
            "energy_micro_wh_per_1k": max(50_000, energy_micro_wh_per_1k),
            "tokens_per_second": tokens_per_second,
        }


# ---------------------------------------------------------------------------
# Benchmark seed data (curated from public datasets)
# ---------------------------------------------------------------------------
def get_default_benchmarks() -> list[dict]:
    """Return curated benchmark seed data from Watt Counts / JouleBench / papers.

    These are representative values; users can import full Watt Counts dataset
    (50 models × 10 GPUs) via the import API.
    """
    now = datetime.now(timezone.utc).isoformat()
    return [
        # Qwen2.5 family (from arXiv 2608.00008, RTX 4060 Ti Q4)
        {
            "id": "bench-qwen2.5-0.5b-4060ti",
            "model_family": "qwen2.5",
            "parameter_count_b": 0.5,
            "quantization_bits": 4,
            "gpu_model": "rtx-4060-ti",
            "gpu_architecture": "ada",
            "avg_power_watts": 45.0,
            "throughput_tokens_per_second": 207.7,
            "energy_joules_per_token": 0.217,
            "energy_wh_per_1k_output": 0.060,
            "batch_size": 1,
            "serving_mode": "server",
            "dataset_source": "arXiv-2608.00008",
            "dataset_version": "v1",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8200,
            "measurement_method": "nvml",
            "raw_reference_url": "https://arxiv.org/abs/2608.00008",
            "created_at": now,
        },
        {
            "id": "bench-qwen2.5-3b-4060ti",
            "model_family": "qwen2.5",
            "parameter_count_b": 3.0,
            "quantization_bits": 4,
            "gpu_model": "rtx-4060-ti",
            "gpu_architecture": "ada",
            "avg_power_watts": 78.0,
            "throughput_tokens_per_second": 107.8,
            "energy_joules_per_token": 0.724,
            "energy_wh_per_1k_output": 0.201,
            "batch_size": 1,
            "serving_mode": "server",
            "dataset_source": "arXiv-2608.00008",
            "dataset_version": "v1",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8200,
            "measurement_method": "nvml",
            "raw_reference_url": "https://arxiv.org/abs/2608.00008",
            "created_at": now,
        },
        # Llama 3 family (from JouleBench, RTX 4090)
        {
            "id": "bench-llama3-8b-4090",
            "model_family": "llama3",
            "parameter_count_b": 8.0,
            "quantization_bits": 4,
            "gpu_model": "rtx-4090",
            "gpu_architecture": "ada",
            "avg_power_watts": 180.0,
            "throughput_tokens_per_second": 95.0,
            "energy_joules_per_token": 1.895,
            "energy_wh_per_1k_output": 0.526,
            "batch_size": 1,
            "serving_mode": "server",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 7800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        # Mistral 7B (from Bench360, RTX 3090)
        {
            "id": "bench-mistral-7b-3090",
            "model_family": "mistral",
            "parameter_count_b": 7.0,
            "quantization_bits": 4,
            "gpu_model": "rtx-3090",
            "gpu_architecture": "ampere",
            "avg_power_watts": 145.0,
            "throughput_tokens_per_second": 55.1,
            "energy_joules_per_token": 2.632,
            "energy_wh_per_1k_output": 0.731,
            "batch_size": 1,
            "serving_mode": "server",
            "dataset_source": "bench360",
            "dataset_version": "v1",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 7500,
            "measurement_method": "nvml",
            "raw_reference_url": "https://arxiv.org/abs/2511.16682",
            "created_at": now,
        },
        # H100 datacenter benchmarks (from Watt Counts)
        {
            "id": "bench-llama3-70b-h100",
            "model_family": "llama3",
            "parameter_count_b": 70.0,
            "quantization_bits": 16,
            "gpu_model": "h100-sxm",
            "gpu_architecture": "hopper",
            "avg_power_watts": 580.0,
            "throughput_tokens_per_second": 18.0,
            "energy_joules_per_token": 32.2,
            "energy_wh_per_1k_output": 8.94,
            "batch_size": 32,
            "serving_mode": "batch",
            "dataset_source": "watt-counts",
            "dataset_version": "v1",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8500,
            "measurement_method": "dcgm",
            "raw_reference_url": "https://arxiv.org/abs/2604.09048",
            "created_at": now,
        },
        {
            "id": "bench-qwen2.5-72b-h100",
            "model_family": "qwen2.5",
            "parameter_count_b": 72.0,
            "quantization_bits": 16,
            "gpu_model": "h100-sxm",
            "gpu_architecture": "hopper",
            "avg_power_watts": 620.0,
            "throughput_tokens_per_second": 16.5,
            "energy_joules_per_token": 37.6,
            "energy_wh_per_1k_output": 10.44,
            "batch_size": 32,
            "serving_mode": "batch",
            "dataset_source": "watt-counts",
            "dataset_version": "v1",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8500,
            "measurement_method": "dcgm",
            "raw_reference_url": "https://arxiv.org/abs/2604.09048",
            "created_at": now,
        },
        # ==================================================================
        # JouleBench: 12 models on NVIDIA A100 80GB PCIe, FP16, NVML measured
        # Source: https://github.com/danielcregg/joulebench (MIT License)
        # All values are best J/tok at optimal batch size, 306 measurements
        # ==================================================================
        {
            "id": "jb-llama3.2-1b-a100",
            "model_family": "llama3",
            "parameter_count_b": 1.0,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 100.7,
            "throughput_tokens_per_second": 1284.2,
            "energy_joules_per_token": 0.031,
            "energy_wh_per_1k_output": 0.0086,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        {
            "id": "jb-qwen2.5-1.5b-a100",
            "model_family": "qwen2.5",
            "parameter_count_b": 1.5,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 93.7,
            "throughput_tokens_per_second": 736.3,
            "energy_joules_per_token": 0.040,
            "energy_wh_per_1k_output": 0.0111,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        {
            "id": "jb-gemma2-2b-a100",
            "model_family": "gemma2",
            "parameter_count_b": 2.0,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 98.6,
            "throughput_tokens_per_second": 591.9,
            "energy_joules_per_token": 0.066,
            "energy_wh_per_1k_output": 0.0183,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        {
            "id": "jb-llama3.2-3b-a100",
            "model_family": "llama3",
            "parameter_count_b": 3.0,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 120.9,
            "throughput_tokens_per_second": 744.4,
            "energy_joules_per_token": 0.083,
            "energy_wh_per_1k_output": 0.0231,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        {
            "id": "jb-phi3-3.8b-a100",
            "model_family": "phi3",
            "parameter_count_b": 3.8,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 155.3,
            "throughput_tokens_per_second": 665.1,
            "energy_joules_per_token": 0.135,
            "energy_wh_per_1k_output": 0.0375,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        {
            "id": "jb-mistral-7b-a100",
            "model_family": "mistral",
            "parameter_count_b": 7.0,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 170.3,
            "throughput_tokens_per_second": 672.4,
            "energy_joules_per_token": 0.166,
            "energy_wh_per_1k_output": 0.0461,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        {
            "id": "jb-qwen2.5-7b-a100",
            "model_family": "qwen2.5",
            "parameter_count_b": 7.0,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 179.4,
            "throughput_tokens_per_second": 725.5,
            "energy_joules_per_token": 0.165,
            "energy_wh_per_1k_output": 0.0458,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        {
            "id": "jb-llama3.1-8b-a100",
            "model_family": "llama3",
            "parameter_count_b": 8.0,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 208.0,
            "throughput_tokens_per_second": 1284.7,
            "energy_joules_per_token": 0.114,
            "energy_wh_per_1k_output": 0.0317,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        {
            "id": "jb-gemma2-9b-a100",
            "model_family": "gemma2",
            "parameter_count_b": 9.0,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 144.3,
            "throughput_tokens_per_second": 371.4,
            "energy_joules_per_token": 0.228,
            "energy_wh_per_1k_output": 0.0633,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        {
            "id": "jb-qwen2.5-14b-a100",
            "model_family": "qwen2.5",
            "parameter_count_b": 14.0,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 222.7,
            "throughput_tokens_per_second": 434.1,
            "energy_joules_per_token": 0.371,
            "energy_wh_per_1k_output": 0.1031,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        {
            "id": "jb-mistral-small-22b-a100",
            "model_family": "mistral",
            "parameter_count_b": 22.0,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 274.8,
            "throughput_tokens_per_second": 360.2,
            "energy_joules_per_token": 0.590,
            "energy_wh_per_1k_output": 0.1639,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
        {
            "id": "jb-gemma2-27b-a100",
            "model_family": "gemma2",
            "parameter_count_b": 27.0,
            "quantization_bits": 16,
            "gpu_model": "a100-80gb",
            "gpu_architecture": "ampere",
            "avg_power_watts": 249.6,
            "throughput_tokens_per_second": 244.7,
            "energy_joules_per_token": 0.765,
            "energy_wh_per_1k_output": 0.2125,
            "batch_size": 16,
            "serving_mode": "batch",
            "dataset_source": "joulebench",
            "dataset_version": "v0.3",
            "provenance_tier": "l2_benchmark_match",
            "confidence_bps": 8800,
            "measurement_method": "nvml",
            "raw_reference_url": "https://github.com/danielcregg/joulebench",
            "created_at": now,
        },
    ]
