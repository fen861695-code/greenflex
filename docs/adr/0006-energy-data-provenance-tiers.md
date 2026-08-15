# ADR 0006: Three-Tier Energy Data Provenance System (L1-L3 + Insufficient)

## Status

Accepted (revised from five-tier to three-tier)

## Context

GreenFlex recommends models based on estimated energy consumption and carbon
emissions. However, the energy data for different models comes from vastly
different sources with wildly different accuracy:

1. **Locally measured models** — measured via NVIDIA NVML during actual
   inference. High accuracy (±5%).
2. **Models with published benchmarks** — data from papers like JouleBench,
   Watt Counts. Good accuracy (±15%) but on different GPUs.
3. **Interpolated models** — no direct benchmark, but same architecture family
   as a benchmarked model. Medium accuracy (±30%).
4. **Analytical estimates** — WattGPU-style memory-bandwidth model. Low
   accuracy (±50%) but works for any model/GPU combination.
5. **FLOPs-based coarse estimates** — order-of-magnitude only. Very low
   accuracy (±100%+).

The original design proposed five tiers (L1-L5), but after implementation
review, we decided to **exclude L4 and L5 from recommendation scoring**. The
reasoning:

- L4 analytical models and L5 FLOPs estimates lack sufficient validation for
  reliable scoring. Using them could mislead users into thinking a model is
  energy-efficient when it's actually not.
- GreenFlex's core principle is "measured over estimated" — if we don't have
  defensible data, we should say so rather than fabricate a number.
- Users prefer "we don't have reliable data for this model" over a precise
  but wrong estimate.

## Decision

Implement a **three-tier + insufficient** energy data provenance system:

### Tier Definitions

| Tier | Name | Source | Confidence | Penalty |
|------|------|--------|------------|---------|
| L1 | `l1_local_measured` | Local NVML measurement | 95% | 1.00x |
| L2 | `l2_benchmark_match` | Exact model+GPU benchmark match | 85% | 1.05x |
| L3 | `l3_cross_gpu_normalized` | Benchmark on different GPU, normalized | 65% | 1.15x |
| — | `insufficient_data` | No L1-L3 data available | 0% | 10.0x (effectively excluded) |

### Key Design Principles

1. **Only defensible, extensible data is used for scoring.** L1-L3 all have
   either direct measurement or a clear, auditable interpolation path.
2. **L4 and L5 are intentionally excluded.** The code for analytical models
   may be retained as a reference tool, but it is not used in recommendation.
3. **Models with insufficient data are not hidden.** They appear in the catalog
   with a "数据不足" label, but receive maximum penalty in scoring, making
   them unlikely to be recommended when alternatives exist.
4. **L1 is never hidden.** Even if the user has few locally measurable models,
   the L1 path remains available for any model that gets measured locally.

### Uncertainty Penalty in Scoring

In GreenRouter v2's multi-objective scoring, the energy and carbon components
are multiplied by the uncertainty penalty:

```
energy_score = (energy / max_energy) * uncertainty_penalty
carbon_score = (carbon / max_carbon) * uncertainty_penalty
```

This means a model with L5 data is effectively 50% "worse" on energy/carbon
than the same numbers with L1 data. This prevents low-confidence estimates
from dominating recommendations.

### GPU Calibration ("Calibrate One, Benefit All")

A `GpuCalibrator` module computes an `efficiency_factor` for the local GPU
by comparing measured energy to benchmark/analytical estimates. This factor
is then applied to ALL model estimates (L2-L4), so measuring one model
improves the accuracy of the entire catalog.

Calibration uses exponential moving average with sample-count-dependent alpha:
- Initial alpha = 0.5 (fast adaptation)
- Decays to ~0.1 after 90 samples
- Factor clamped to [0.3, 3.0]

### Database Schema

New tables:
- `gpu_energy_profiles` — per-GPU efficiency factors and calibration history
- `model_energy_benchmarks` — importable benchmark dataset (Watt Counts format)

Extended `model_catalog` with 7 new fields:
- `energy_data_provenance` — tier label
- `energy_data_source` — human-readable source description
- `energy_confidence_bps` — confidence in basis points
- `reference_gpu_model` — GPU the energy data was measured/estimated on
- `parameter_count_b` — float parameter count (for analytical model)
- `quantization_bits` — quantization level
- `architecture_family` — model family (qwen2.5, llama3, etc.)

## Consequences

### Positive
- Recommendations transparently show data confidence (L1-L5 badge in UI)
- Low-confidence models are naturally penalized without hard exclusions
- Users can see which models would benefit most from local calibration
- Single GPU measurement improves entire catalog accuracy
- Benchmark datasets (Watt Counts, JouleBench) can be imported as L2 data

### Negative
- More complex scoring logic (but fully backward compatible)
- Requires database migration
- Users may be confused by "why did the L5 model lose if it uses less energy?"
  — addressed by UI explanation

### Risks
- Uncertainty penalty too aggressive → only L1 models ever recommended
  - Mitigation: max penalty 1.5x, quality/price still dominate (55% weight)
- Calibration factor drifts with bad data
  - Mitigation: EMA with clamping, manual reset available

## References

- Watt Counts: arXiv 2604.09048 (50 models × 10 GPUs)
- WattGPU: arXiv 2607.02391 (analytical model for unseen GPUs/models)
- JouleBench: https://github.com/danielcregg/joulebench/
- TokenPowerBench: arXiv 2512.03024
