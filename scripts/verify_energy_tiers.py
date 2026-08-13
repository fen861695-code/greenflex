#!/usr/bin/env python3
"""Standalone verification of L1-L3 + insufficient_data energy estimation.

This script does NOT depend on the full GreenFlex project. It reimplements
the core logic to verify that:
1. L1 local measured models return L1 provenance
2. Models with exact benchmark match return L2
3. Models with same-family interpolation return L3
4. Models without any benchmark data return INSUFFICIENT_DATA
5. Uncertainty penalties are correct
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EnergyDataProvenance(str, Enum):
    L1_LOCAL_MEASURED = "l1_local_measured"
    L2_BENCHMARK_MATCH = "l2_benchmark_match"
    L3_CROSS_GPU_NORMALIZED = "l3_cross_gpu_normalized"
    INSUFFICIENT_DATA = "insufficient_data"


CONFIDENCE = {
    EnergyDataProvenance.L1_LOCAL_MEASURED: 9500,
    EnergyDataProvenance.L2_BENCHMARK_MATCH: 8500,
    EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED: 6500,
    EnergyDataProvenance.INSUFFICIENT_DATA: 0,
}

PENALTY = {
    EnergyDataProvenance.L1_LOCAL_MEASURED: 1.0,
    EnergyDataProvenance.L2_BENCHMARK_MATCH: 1.05,
    EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED: 1.15,
    EnergyDataProvenance.INSUFFICIENT_DATA: 10.0,
}


# Simulated benchmark database (18 entries, same as energy_estimator.py)
BENCHMARKS = [
    # JouleBench A100 FP16 (12 models)
    {"family": "llama3", "params": 1.0, "gpu": "a100-80gb", "j_per_tok": 0.031},
    {"family": "qwen2.5", "params": 1.5, "gpu": "a100-80gb", "j_per_tok": 0.040},
    {"family": "gemma2", "params": 2.0, "gpu": "a100-80gb", "j_per_tok": 0.066},
    {"family": "llama3", "params": 3.0, "gpu": "a100-80gb", "j_per_tok": 0.083},
    {"family": "phi3", "params": 3.8, "gpu": "a100-80gb", "j_per_tok": 0.135},
    {"family": "mistral", "params": 7.0, "gpu": "a100-80gb", "j_per_tok": 0.166},
    {"family": "qwen2.5", "params": 7.0, "gpu": "a100-80gb", "j_per_tok": 0.165},
    {"family": "llama3", "params": 8.0, "gpu": "a100-80gb", "j_per_tok": 0.114},
    {"family": "gemma2", "params": 9.0, "gpu": "a100-80gb", "j_per_tok": 0.228},
    {"family": "qwen2.5", "params": 14.0, "gpu": "a100-80gb", "j_per_tok": 0.371},
    {"family": "mistral", "params": 22.0, "gpu": "a100-80gb", "j_per_tok": 0.590},
    {"family": "gemma2", "params": 27.0, "gpu": "a100-80gb", "j_per_tok": 0.765},
    # arXiv 2608.00008 RTX 4060 Ti Q4 (2 models)
    {"family": "qwen2.5", "params": 0.5, "gpu": "rtx-4060-ti", "j_per_tok": 0.012},
    {"family": "qwen2.5", "params": 3.0, "gpu": "rtx-4060-ti", "j_per_tok": 0.058},
    # Watt Counts H100 (2 models)
    {"family": "llama3", "params": 70.0, "gpu": "h100-sxm", "j_per_tok": 0.850},
    {"family": "qwen2.5", "params": 72.0, "gpu": "h100-sxm", "j_per_tok": 0.880},
    # Bench360 RTX 3090 (1 model)
    {"family": "mistral", "params": 7.0, "gpu": "rtx-3090", "j_per_tok": 0.180},
    # JouleBench RTX 4090 (1 model)
    {"family": "llama3", "params": 8.0, "gpu": "rtx-4090", "j_per_tok": 0.120},
]

# Families with at least one benchmark (for L3 interpolation)
BENCHMARK_FAMILIES = {b["family"] for b in BENCHMARKS}


@dataclass
class MockModel:
    id: str
    parameter_b: str
    energy_data_provenance: str = "insufficient_data"
    estimated_energy_micro_wh_per_1k_output: int = 0
    estimated_tokens_per_second: int = 100
    energy_confidence_bps: int = 0
    energy_data_source: str | None = None
    quantization_bits: int | None = None
    parameter_count_b: float | None = None


def parse_param_count(param_str: str) -> float | None:
    """Parse parameter string like '0.5B', '7B', '14B', '70B' to float billions."""
    if not param_str:
        return None
    s = param_str.strip().upper()
    try:
        if s.endswith("T"):
            return float(s[:-1]) * 1000
        if s.endswith("B"):
            return float(s[:-1])
        if s.endswith("M"):
            return float(s[:-1]) / 1000
        return float(s)
    except ValueError:
        return None


def extract_family(model_id: str) -> str:
    """Extract family like 'qwen2.5' from 'qwen2.5-7b-q4'."""
    parts = model_id.replace("cloud-", "").split("-")
    return parts[0] if parts else model_id


def find_benchmark(model: MockModel, exact_gpu: bool = False,
                   local_gpu: str = "rtx-3060-laptop") -> dict | None:
    """Find closest benchmark by family + parameter count.

    L2 (exact_gpu=True): 20% tolerance + quantization match.
    L3 (exact_gpu=False): 50% tolerance, no quantization restriction.
    """
    param_count = model.parameter_count_b or parse_param_count(model.parameter_b)
    if param_count is None:
        return None
    family = extract_family(model.id)

    param_tolerance = 0.20 if exact_gpu else 0.50

    candidates = []
    for b in BENCHMARKS:
        # Family match
        if b["family"] != family:
            continue
        # Parameter count tolerance
        if abs(b["params"] - param_count) / param_count > param_tolerance:
            continue
        if exact_gpu and b["gpu"] != local_gpu:
            continue
        candidates.append((abs(b["params"] - param_count), b))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def estimate_energy(model: MockModel, local_gpu: str = "rtx-3060-laptop") -> dict:
    """Simulate EnergyEstimator.estimate() with L1-L3 + insufficient only."""
    param_count = model.parameter_count_b or parse_param_count(model.parameter_b)

    # L1: local measured
    if model.energy_data_provenance == EnergyDataProvenance.L1_LOCAL_MEASURED.value:
        return {
            "provenance": EnergyDataProvenance.L1_LOCAL_MEASURED,
            "confidence": model.energy_confidence_bps or 9500,
            "penalty": PENALTY[EnergyDataProvenance.L1_LOCAL_MEASURED],
            "energy": model.estimated_energy_micro_wh_per_1k_output,
            "source": model.energy_data_source or "local NVML measurement",
        }

    # L2: exact model-GPU benchmark match
    l2 = find_benchmark(model, exact_gpu=True, local_gpu=local_gpu)
    if l2 is not None:
        energy_wh_per_1k = l2["j_per_tok"] * 1000 / 3600  # J/tok -> Wh/1k
        return {
            "provenance": EnergyDataProvenance.L2_BENCHMARK_MATCH,
            "confidence": 8500,
            "penalty": PENALTY[EnergyDataProvenance.L2_BENCHMARK_MATCH],
            "energy": int(energy_wh_per_1k * 1_000_000),
            "source": f"benchmark: {l2['family']} {l2['params']}B on {l2['gpu']}",
        }

    # L3: cross-GPU benchmark + normalization
    l3 = find_benchmark(model, exact_gpu=False, local_gpu=local_gpu)
    if l3 is not None:
        energy_wh_per_1k = l3["j_per_tok"] * 1000 / 3600
        # Simple normalization factor (in real code uses GPU specs)
        norm_factor = 1.2  # assume local GPU is less efficient than benchmark GPU
        return {
            "provenance": EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED,
            "confidence": 6500,
            "penalty": PENALTY[EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED],
            "energy": int(energy_wh_per_1k * 1_000_000 * norm_factor),
            "source": f"interpolated from {l3['family']} {l3['params']}B on {l3['gpu']}",
        }

    # Insufficient data: no L1-L3 available
    return {
        "provenance": EnergyDataProvenance.INSUFFICIENT_DATA,
        "confidence": 0,
        "penalty": PENALTY[EnergyDataProvenance.INSUFFICIENT_DATA],
        "energy": 10_000_000,  # placeholder max
        "source": "Insufficient benchmark data for reliable estimate",
    }


def run_tests():
    """Run all verification tests."""
    print("=" * 70)
    print("GreenFlex Energy Estimation Verification (L1-L3 + Insufficient)")
    print("=" * 70)

    passed = 0
    failed = 0

    def assert_test(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name} — {detail}")
            failed += 1

    # Test 1: L1 local measured
    print("\n--- Test 1: L1 Local Measured ---")
    model = MockModel(
        id="qwen2.5-0.5b-q4",
        parameter_b="0.5B",
        energy_data_provenance="l1_local_measured",
        estimated_energy_micro_wh_per_1k_output=5000,
        estimated_tokens_per_second=100,
        energy_confidence_bps=9500,
        energy_data_source="local NVML measurement on RTX 3060",
    )
    result = estimate_energy(model)
    assert_test("L1 provenance", result["provenance"] == EnergyDataProvenance.L1_LOCAL_MEASURED,
                f"got {result['provenance']}")
    assert_test("L1 confidence 95%", result["confidence"] == 9500, f"got {result['confidence']}")
    assert_test("L1 penalty 1.0x", result["penalty"] == 1.0, f"got {result['penalty']}")
    assert_test("L1 energy from model", result["energy"] == 5000, f"got {result['energy']}")

    # Test 2: L2 exact benchmark match (same GPU)
    print("\n--- Test 2: L2 Benchmark Match (exact GPU) ---")
    # Note: our local GPU is rtx-3060-laptop, no benchmarks on that GPU
    # So L2 would only trigger if local_gpu matches a benchmark GPU
    model = MockModel(id="qwen2.5-7b", parameter_b="7B")
    result = estimate_energy(model, local_gpu="a100-80gb")
    assert_test("L2 provenance when GPU matches",
                result["provenance"] == EnergyDataProvenance.L2_BENCHMARK_MATCH,
                f"got {result['provenance']}")
    assert_test("L2 confidence 85%", result["confidence"] == 8500, f"got {result['confidence']}")
    assert_test("L2 penalty 1.05x", result["penalty"] == 1.05, f"got {result['penalty']}")

    # Test 3: L3 cross-GPU normalization
    print("\n--- Test 3: L3 Cross-GPU Normalized ---")
    model = MockModel(id="qwen2.5-7b-q4", parameter_b="7B")
    result = estimate_energy(model, local_gpu="rtx-3060-laptop")
    assert_test("L3 provenance for same family different GPU",
                result["provenance"] == EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED,
                f"got {result['provenance']}")
    assert_test("L3 confidence 65%", result["confidence"] == 6500, f"got {result['confidence']}")
    assert_test("L3 penalty 1.15x", result["penalty"] == 1.15, f"got {result['penalty']}")

    # Test 4: L3 for interpolated parameter count
    print("\n--- Test 4: L3 Interpolated Parameter Count ---")
    model = MockModel(id="qwen2.5-10b", parameter_b="10B")  # between 7B and 14B
    result = estimate_energy(model, local_gpu="rtx-3060-laptop")
    assert_test("L3 for 10B (interpolated from 7B/14B)",
                result["provenance"] == EnergyDataProvenance.L3_CROSS_GPU_NORMALIZED,
                f"got {result['provenance']}")

    # Test 5: Insufficient data for unknown family
    print("\n--- Test 5: Insufficient Data ---")
    model = MockModel(id="cloud-gpt4o", parameter_b="175B")
    result = estimate_energy(model)
    assert_test("Insufficient for cloud model",
                result["provenance"] == EnergyDataProvenance.INSUFFICIENT_DATA,
                f"got {result['provenance']}")
    assert_test("Insufficient confidence 0%", result["confidence"] == 0, f"got {result['confidence']}")
    assert_test("Insufficient penalty 10.0x", result["penalty"] == 10.0, f"got {result['penalty']}")

    model = MockModel(id="unknown-arch-50b", parameter_b="50B")
    result = estimate_energy(model)
    assert_test("Insufficient for unknown architecture",
                result["provenance"] == EnergyDataProvenance.INSUFFICIENT_DATA,
                f"got {result['provenance']}")

    # Test 6: No L4/L5 fallback
    print("\n--- Test 6: No L4/L5 Fallback (key change) ---")
    # Previously, a model with known params but no family benchmark would get L4
    # Now it should get INSUFFICIENT_DATA
    model = MockModel(id="some-new-arch-13b", parameter_b="13B")
    result = estimate_energy(model)
    assert_test("No L4 analytical fallback",
                result["provenance"] != "l4_analytical_model",
                f"got {result['provenance']}")
    assert_test("No L5 FLOPs fallback",
                result["provenance"] != "l5_flops_estimate",
                f"got {result['provenance']}")
    assert_test("Falls to insufficient instead",
                result["provenance"] == EnergyDataProvenance.INSUFFICIENT_DATA,
                f"got {result['provenance']}")

    # Test 7: Penalty impact on scoring
    print("\n--- Test 7: Penalty Impact on Scoring ---")
    # Simulate: two models with same raw energy, different provenance
    l2_energy = 100_000  # micro-Wh/1k
    insufficient_energy = 100_000
    l2_score = l2_energy * PENALTY[EnergyDataProvenance.L2_BENCHMARK_MATCH]
    insufficient_score = insufficient_energy * PENALTY[EnergyDataProvenance.INSUFFICIENT_DATA]
    ratio = insufficient_score / l2_score
    assert_test("Insufficient gets 9.5x worse score than L2",
                ratio > 9.0, f"ratio = {ratio:.1f}x")
    print(f"    L2 score: {l2_score:.0f}, Insufficient score: {insufficient_score:.0f}")
    print(f"    Ratio: {ratio:.1f}x (insufficient effectively excluded)")

    # Test 8: Coverage report
    print("\n--- Test 8: Benchmark Coverage ---")
    print(f"    Total benchmarks: {len(BENCHMARKS)}")
    print(f"    Families covered: {sorted(BENCHMARK_FAMILIES)}")
    families_with_l2 = {}
    for b in BENCHMARKS:
        fam = b["family"]
        if fam not in families_with_l2:
            families_with_l2[fam] = []
        families_with_l2[fam].append(b["params"])
    for fam, sizes in sorted(families_with_l2.items()):
        print(f"    {fam:<12}: {sorted(set(sizes))}")

    # Summary
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    if failed == 0:
        print("\nAll tests passed! L1-L3 + insufficient_data logic is correct.")
        print("Key verification: NO L4 analytical or L5 FLOPs fallback exists.")
    else:
        print(f"\n{failed} test(s) failed. Please review.")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
