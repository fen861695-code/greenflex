"""Tests for EnergyEstimator (L1-L3 + insufficient_data only).

Verifies that:
- L1 local measured models return L1 provenance
- Models with exact benchmark match return L2
- Models with same-family interpolation return L3
- Models without benchmark data return INSUFFICIENT_DATA
- No L4 analytical or L5 FLOPs fallback exists
- Uncertainty penalties are correct
- Benchmark matching tolerances are correct (20% for L2, 50% for L3)
"""
from __future__ import annotations

import pytest

from greenflex.domain import EnergyDataProvenance, ENERGY_UNCERTAINTY_PENALTY
from greenflex.energy_estimator import EnergyEstimator, get_default_benchmarks
from greenflex.models import ModelEnergyBenchmarkRecord, ModelRecord


def _benchmark_records() -> list[ModelEnergyBenchmarkRecord]:
    """Convert default benchmark dicts to record objects."""
    return [ModelEnergyBenchmarkRecord(**b) for b in get_default_benchmarks()]


@pytest.fixture
def estimator() -> EnergyEstimator:
    """Create EnergyEstimator with default benchmarks and local GPU."""
    return EnergyEstimator(
        benchmarks=_benchmark_records(),
        gpu_profiles=[],
        local_gpu_model="rtx-3060-laptop",
    )


@pytest.fixture
def estimator_a100() -> EnergyEstimator:
    """Create EnergyEstimator with A100 as local GPU (for L2 exact match tests)."""
    return EnergyEstimator(
        benchmarks=_benchmark_records(),
        gpu_profiles=[],
        local_gpu_model="a100-80gb",
    )


def _make_model(
    model_id: str,
    parameter_b: str = "7B",
    *,
    provenance: str = "insufficient_data",
    energy: int = 0,
    tokens_per_second: int = 100,
    confidence: int = 0,
    source: str | None = None,
    quant_bits: int | None = 4,
    param_count: float | None = None,
) -> ModelRecord:
    """Helper to create a minimal ModelRecord for testing."""
    return ModelRecord(
        id=model_id,
        runtime_name=model_id,
        display_name=model_id,
        tier="balanced",
        parameter_b=parameter_b,
        context_limit=8192,
        recommended_for_json="{}",
        input_rate_micro_rmb_per_million=100,
        output_rate_micro_rmb_per_million=200,
        estimated_tokens_per_second=tokens_per_second,
        estimated_energy_micro_wh_per_1k_output=energy,
        digest=None,
        enabled=True,
        energy_data_provenance=provenance,
        energy_data_source=source,
        energy_confidence_bps=confidence,
        reference_gpu_model=None,
        parameter_count_b=param_count,
        quantization_bits=quant_bits,
        architecture_family=None,
    )


# ---------------------------------------------------------------------------
# L1 Local Measured
# ---------------------------------------------------------------------------
class TestL1LocalMeasured:
    def test_l1_returns_local_provenance(self, estimator: EnergyEstimator):
        model = _make_model(
            "qwen2.5-0.5b-q4",
            "0.5B",
            provenance="l1_local_measured",
            energy=5000,
            confidence=9500,
            source="local NVML measurement",
        )
        result = estimator.estimate(model)
        assert result.provenance == EnergyDataProvenance.L1_LOCAL_MEASURED

    def test_l1_uses_stored_energy(self, estimator: EnergyEstimator):
        model = _make_model(
            "qwen2.5-0.5b-q4",
            "0.5B",
            provenance="l1_local_measured",
            energy=12345,
        )
        result = estimator.estimate(model)
        assert result.energy_micro_wh_per_1k_output == 12345

    def test_l1_confidence_95_percent(self, estimator: EnergyEstimator):
        model = _make_model(
            "qwen2.5-0.5b-q4",
            "0.5B",
            provenance="l1_local_measured",
            confidence=9500,
        )
        result = estimator.estimate(model)
        assert result.confidence_bps == 9500

    def test_l1_penalty_is_1_0(self, estimator: EnergyEstimator):
        model = _make_model(
            "qwen2.5-0.5b-q4",
            "0.5B",
            provenance="l1_local_measured",
        )
        result = estimator.estimate(model)
        assert result.uncertainty_penalty == 1.0


# ---------------------------------------------------------------------------
# L2 Benchmark Match (exact GPU)
# ---------------------------------------------------------------------------
class TestL2BenchmarkMatch:
    def test_l2_exact_gpu_match(self, estimator_a100: EnergyEstimator):
        """Qwen2.5 7B on A100 should match JouleBench benchmark exactly."""
        model = _make_model("qwen2.5-7b", "7B", quant_bits=16)
        result = estimator_a100.estimate(model)
        assert result.provenance == EnergyDataProvenance.L2_BENCHMARK_MATCH

    def test_l2_confidence_85_percent(self, estimator_a100: EnergyEstimator):
        model = _make_model("qwen2.5-7b", "7B", quant_bits=16)
        result = estimator_a100.estimate(model)
        assert result.confidence_bps >= 8000

    def test_l2_penalty_is_1_05(self, estimator_a100: EnergyEstimator):
        model = _make_model("qwen2.5-7b", "7B", quant_bits=16)
        result = estimator_a100.estimate(model)
        assert result.uncertainty_penalty == 1.05

    def test_l2_no_match_on_different_gpu(self, estimator: EnergyEstimator):
        """With local GPU = rtx-3060-laptop, no exact L2 match should exist."""
        model = _make_model("qwen2.5-7b", "7B", quant_bits=16)
        result = estimator.estimate(model)
        # Should fall through to L3 or insufficient, not L2
        assert result.provenance != EnergyDataProvenance.L2_BENCHMARK_MATCH


# ---------------------------------------------------------------------------
# L3 Cross-GPU Normalized
# ---------------------------------------------------------------------------
class TestL3CrossGpuNormalized:
    def test_l3_same_family_different_gpu(self, estimator: EnergyEstimator):
        """Qwen2.5 7B on rtx-3060-laptop should get L3 via A100 benchmark."""
        model = _make_model("qwen2.5-7b-q4", "7B", quant_bits=4)
        result = estimator.estimate(model)
        assert result.provenance == EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED

    def test_l3_confidence_65_percent(self, estimator: EnergyEstimator):
        model = _make_model("qwen2.5-7b-q4", "7B", quant_bits=4)
        result = estimator.estimate(model)
        assert result.confidence_bps == 6500

    def test_l3_penalty_is_1_15(self, estimator: EnergyEstimator):
        model = _make_model("qwen2.5-7b-q4", "7B", quant_bits=4)
        result = estimator.estimate(model)
        assert result.uncertainty_penalty == 1.15

    def test_l3_interpolated_param_count(self, estimator: EnergyEstimator):
        """Qwen2.5 10B (between 7B and 14B) should get L3 via 50% tolerance."""
        model = _make_model("qwen2.5-10b", "10B", quant_bits=4)
        result = estimator.estimate(model)
        assert result.provenance == EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED

    def test_l3_llama3_family(self, estimator: EnergyEstimator):
        model = _make_model("llama3.1-8b-q4", "8B", quant_bits=4)
        result = estimator.estimate(model)
        assert result.provenance == EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED

    def test_l3_mistral_family(self, estimator: EnergyEstimator):
        model = _make_model("mistral-7b-q4", "7B", quant_bits=4)
        result = estimator.estimate(model)
        assert result.provenance == EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED


# ---------------------------------------------------------------------------
# Insufficient Data (no L1-L3 available)
# ---------------------------------------------------------------------------
class TestInsufficientData:
    def test_insufficient_for_cloud_model(self, estimator: EnergyEstimator):
        model = _make_model("cloud-gpt4o", "175B", quant_bits=16)
        result = estimator.estimate(model)
        assert result.provenance == EnergyDataProvenance.INSUFFICIENT_DATA

    def test_insufficient_for_unknown_architecture(self, estimator: EnergyEstimator):
        model = _make_model("some-new-arch-13b", "13B", quant_bits=4)
        result = estimator.estimate(model)
        assert result.provenance == EnergyDataProvenance.INSUFFICIENT_DATA

    def test_insufficient_confidence_is_0(self, estimator: EnergyEstimator):
        model = _make_model("cloud-gpt4o", "175B")
        result = estimator.estimate(model)
        assert result.confidence_bps == 0

    def test_insufficient_penalty_is_10_0(self, estimator: EnergyEstimator):
        model = _make_model("cloud-gpt4o", "175B")
        result = estimator.estimate(model)
        assert result.uncertainty_penalty == 10.0

    def test_no_l4_analytical_fallback(self, estimator: EnergyEstimator):
        """Key test: models without L1-L3 should NOT get L4 analytical estimate."""
        model = _make_model("unknown-arch-50b", "50B")
        result = estimator.estimate(model)
        assert result.provenance != "l4_analytical_model"

    def test_no_l5_flops_fallback(self, estimator: EnergyEstimator):
        """Key test: models without L1-L3 should NOT get L5 FLOPs estimate."""
        model = _make_model("unknown-arch-50b", "50B")
        result = estimator.estimate(model)
        assert result.provenance != "l5_flops_estimate"


# ---------------------------------------------------------------------------
# Benchmark Matching Tolerances
# ---------------------------------------------------------------------------
class TestBenchmarkMatching:
    def test_l2_strict_20_percent_tolerance(self, estimator_a100: EnergyEstimator):
        """L2 exact match should use 20% tolerance: 10B should NOT match 7B."""
        model = _make_model("qwen2.5-10b", "10B", quant_bits=16)
        result = estimator_a100.estimate(model)
        # 10B is 43% away from 7B, so no L2 match
        assert result.provenance != EnergyDataProvenance.L2_BENCHMARK_MATCH

    def test_l3_relaxed_50_percent_tolerance(self, estimator: EnergyEstimator):
        """L3 cross-GPU should use 50% tolerance: 10B should match 7B or 14B."""
        model = _make_model("qwen2.5-10b", "10B", quant_bits=4)
        result = estimator.estimate(model)
        # 10B is within 50% of both 7B (43%) and 14B (29%)
        assert result.provenance == EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED

    def test_l3_quantization_not_restricted(self, estimator: EnergyEstimator):
        """L3 should match even if quantization differs (Q4 vs FP16)."""
        model = _make_model("qwen2.5-7b-q4", "7B", quant_bits=4)
        result = estimator.estimate(model)
        # Benchmarks are FP16 (16-bit), model is Q4 (4-bit) — should still match L3
        assert result.provenance == EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED


# ---------------------------------------------------------------------------
# Penalty Impact
# ---------------------------------------------------------------------------
class TestPenaltyImpact:
    def test_insufficient_penalty_much_higher_than_l2(self, estimator: EnergyEstimator,
                                                       estimator_a100: EnergyEstimator):
        """Insufficient data should score much worse than L2 in energy dimension."""
        l2_model = _make_model("qwen2.5-7b", "7B", quant_bits=16)
        insufficient_model = _make_model("cloud-gpt4o", "175B")

        l2_result = estimator_a100.estimate(l2_model)
        insufficient_result = estimator.estimate(insufficient_model)

        # Even if raw energy is similar, penalty makes insufficient much worse
        l2_effective = l2_result.energy_micro_wh_per_1k_output * l2_result.uncertainty_penalty
        insufficient_effective = (
            insufficient_result.energy_micro_wh_per_1k_output
            * insufficient_result.uncertainty_penalty
        )
        # Insufficient should be at least 5x worse in effective score
        assert insufficient_effective > l2_effective * 5


# ---------------------------------------------------------------------------
# Default Benchmarks
# ---------------------------------------------------------------------------
class TestDefaultBenchmarks:
    def test_default_benchmarks_has_18_entries(self):
        benchmarks = get_default_benchmarks()
        assert len(benchmarks) == 18

    def test_default_benchmarks_covers_5_families(self):
        benchmarks = get_default_benchmarks()
        families = {b["model_family"] for b in benchmarks}
        assert "qwen2.5" in families
        assert "llama3" in families
        assert "gemma2" in families
        assert "phi3" in families
        assert "mistral" in families

    def test_default_benchmarks_has_joulebench_data(self):
        benchmarks = get_default_benchmarks()
        joulebench = [b for b in benchmarks if b["dataset_source"] == "joulebench"]
        assert len(joulebench) >= 12  # 12 A100 + possibly more from other sources
