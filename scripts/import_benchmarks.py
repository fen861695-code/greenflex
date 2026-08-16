#!/usr/bin/env python3
"""Import public LLM energy benchmark datasets into GreenFlex.

Supported sources:
- JouleBench (GitHub: danielcregg/joulebench) - 12 models on A100
- Watt Counts (arXiv 2604.09048) - 50 models x 10 GPUs
- TokenPowerBench (arXiv 2512.03024)
- EcoLogits (genai-impact/ecologits) - cloud API models

Usage:
    python scripts/import_benchmarks.py --source joulebench --db-path ./data/greenflex.db
    python scripts/import_benchmarks.py --source all --dry-run

This script can also output a coverage report showing which models in the
catalog have L2/L3/L4/L5 data.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# JouleBench data (curated from https://github.com/danielcregg/joulebench)
# 12 models on NVIDIA A100 80GB PCIe, FP16, NVML direct measurement
# ---------------------------------------------------------------------------
JOULEBENCH_DATA = [
    {"model_family": "llama3", "parameter_count_b": 1.0, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 100.7, "throughput_tokens_per_second": 1284.2,
     "energy_joules_per_token": 0.031, "energy_wh_per_1k_output": 0.0086,
     "batch_size": 16, "serving_mode": "batch"},
    {"model_family": "qwen2.5", "parameter_count_b": 1.5, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 93.7, "throughput_tokens_per_second": 736.3,
     "energy_joules_per_token": 0.040, "energy_wh_per_1k_output": 0.0111,
     "batch_size": 16, "serving_mode": "batch"},
    {"model_family": "gemma2", "parameter_count_b": 2.0, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 98.6, "throughput_tokens_per_second": 591.9,
     "energy_joules_per_token": 0.066, "energy_wh_per_1k_output": 0.0183,
     "batch_size": 16, "serving_mode": "batch"},
    {"model_family": "llama3", "parameter_count_b": 3.0, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 120.9, "throughput_tokens_per_second": 744.4,
     "energy_joules_per_token": 0.083, "energy_wh_per_1k_output": 0.0231,
     "batch_size": 16, "serving_mode": "batch"},
    {"model_family": "phi3", "parameter_count_b": 3.8, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 155.3, "throughput_tokens_per_second": 665.1,
     "energy_joules_per_token": 0.135, "energy_wh_per_1k_output": 0.0375,
     "batch_size": 16, "serving_mode": "batch"},
    {"model_family": "mistral", "parameter_count_b": 7.0, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 170.3, "throughput_tokens_per_second": 672.4,
     "energy_joules_per_token": 0.166, "energy_wh_per_1k_output": 0.0461,
     "batch_size": 16, "serving_mode": "batch"},
    {"model_family": "qwen2.5", "parameter_count_b": 7.0, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 179.4, "throughput_tokens_per_second": 725.5,
     "energy_joules_per_token": 0.165, "energy_wh_per_1k_output": 0.0458,
     "batch_size": 16, "serving_mode": "batch"},
    {"model_family": "llama3", "parameter_count_b": 8.0, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 208.0, "throughput_tokens_per_second": 1284.7,
     "energy_joules_per_token": 0.114, "energy_wh_per_1k_output": 0.0317,
     "batch_size": 16, "serving_mode": "batch"},
    {"model_family": "gemma2", "parameter_count_b": 9.0, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 144.3, "throughput_tokens_per_second": 371.4,
     "energy_joules_per_token": 0.228, "energy_wh_per_1k_output": 0.0633,
     "batch_size": 16, "serving_mode": "batch"},
    {"model_family": "qwen2.5", "parameter_count_b": 14.0, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 222.7, "throughput_tokens_per_second": 434.1,
     "energy_joules_per_token": 0.371, "energy_wh_per_1k_output": 0.1031,
     "batch_size": 16, "serving_mode": "batch"},
    {"model_family": "mistral", "parameter_count_b": 22.0, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 274.8, "throughput_tokens_per_second": 360.2,
     "energy_joules_per_token": 0.590, "energy_wh_per_1k_output": 0.1639,
     "batch_size": 16, "serving_mode": "batch"},
    {"model_family": "gemma2", "parameter_count_b": 27.0, "quantization_bits": 16,
     "gpu_model": "a100-80gb", "gpu_architecture": "ampere",
     "avg_power_watts": 249.6, "throughput_tokens_per_second": 244.7,
     "energy_joules_per_token": 0.765, "energy_wh_per_1k_output": 0.2125,
     "batch_size": 16, "serving_mode": "batch"},
]


def build_benchmark_record(data: dict, source: str, source_version: str,
                           confidence_bps: int = 8500) -> dict:
    """Convert raw benchmark data to database record format."""
    now = datetime.now(timezone.utc).isoformat()
    bench_id = f"import-{source}-{data['model_family']}-{data['parameter_count_b']}b-{data['gpu_model']}"
    return {
        "id": bench_id,
        **data,
        "dataset_source": source,
        "dataset_version": source_version,
        "provenance_tier": "l2_benchmark_match",
        "confidence_bps": confidence_bps,
        "measurement_method": "nvml",
        "raw_reference_url": _source_url(source),
        "created_at": now,
    }


def _source_url(source: str) -> str:
    urls = {
        "joulebench": "https://github.com/danielcregg/joulebench",
        "watt-counts": "https://arxiv.org/abs/2604.09048",
        "tokenpowerbench": "https://arxiv.org/abs/2512.03024",
        "ecologits": "https://github.com/genai-impact/ecologits",
    }
    return urls.get(source, "")


def import_to_sqlite(db_path: str, records: list[dict], dry_run: bool = False) -> None:
    """Import benchmark records into SQLite database."""
    if dry_run:
        print(f"[DRY RUN] Would import {len(records)} records into {db_path}")
        for r in records[:3]:
            print(f"  - {r['id']}: {r['model_family']} {r['parameter_count_b']}B "
                  f"on {r['gpu_model']} = {r['energy_joules_per_token']} J/tok")
        if len(records) > 3:
            print(f"  ... and {len(records) - 3} more")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model_energy_benchmarks'")
    if cursor.fetchone() is None:
        print("Error: model_energy_benchmarks table not found. Run alembic upgrade first.")
        conn.close()
        return

    imported = 0
    skipped = 0
    for r in records:
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO model_energy_benchmarks
                (id, model_family, parameter_count_b, quantization_bits, gpu_model,
                 gpu_architecture, avg_power_watts, throughput_tokens_per_second,
                 energy_joules_per_token, energy_wh_per_1k_output, batch_size,
                 serving_mode, dataset_source, dataset_version, provenance_tier,
                 confidence_bps, measurement_method, raw_reference_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["id"], r["model_family"], r["parameter_count_b"], r["quantization_bits"],
                r["gpu_model"], r["gpu_architecture"], r["avg_power_watts"],
                r["throughput_tokens_per_second"], r["energy_joules_per_token"],
                r["energy_wh_per_1k_output"], r["batch_size"], r["serving_mode"],
                r["dataset_source"], r["dataset_version"], r["provenance_tier"],
                r["confidence_bps"], r["measurement_method"], r["raw_reference_url"],
                r["created_at"],
            ))
            imported += 1
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()
    conn.close()
    print(f"Imported {imported} records, skipped {skipped} duplicates")


def coverage_report(db_path: str | None = None) -> None:
    """Print benchmark data coverage report."""
    print("=" * 70)
    print("GreenFlex Energy Benchmark Data Coverage Report")
    print("=" * 70)

    # Built-in benchmarks
    all_builtin = []
    for d in JOULEBENCH_DATA:
        all_builtin.append(("joulebench", d))

    print(f"\nBuilt-in benchmark datasets:")
    print(f"  JouleBench: {len(JOULEBENCH_DATA)} models on A100 80GB (FP16)")

    # Family coverage
    families = {}
    for _, d in all_builtin:
        fam = d["model_family"]
        if fam not in families:
            families[fam] = []
        families[fam].append(d["parameter_count_b"])

    print(f"\nFamily coverage (L2 exact match):")
    for fam, sizes in sorted(families.items()):
        sizes_str = ", ".join(f"{s}B" for s in sorted(sizes))
        print(f"  {fam:<12}: {sizes_str}")

    # If DB path provided, query actual catalog
    if db_path and Path(db_path).exists():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT energy_data_provenance, COUNT(*) as cnt
                FROM model_catalog
                GROUP BY energy_data_provenance
                ORDER BY cnt DESC
            """)
            print(f"\nCatalog provenance distribution:")
            tier_names = {
                "l1_local_measured": "L1 Local Measured",
                "l2_benchmark_match": "L2 Benchmark Match",
                "l3_cross_gpu_normalized": "L3 Cross-GPU Normalized",
                "insufficient_data": "Insufficient Data",
            }
            total = 0
            for tier, cnt in cursor.fetchall():
                name = tier_names.get(tier, tier)
                print(f"  {name:<25}: {cnt} models")
                total += cnt
            print(f"  {'TOTAL':<25}: {total} models")
        except sqlite3.OperationalError:
            print("\n  (model_catalog table not found or empty)")
        conn.close()

    print(f"\nNote: Only L1-L3 tiers are used for recommendation scoring.")
    print(f"Models without L1-L3 data are marked 'insufficient_data' and excluded.")
    print(f"Import more data with: python scripts/import_benchmarks.py --source all")


def main():
    parser = argparse.ArgumentParser(description="Import LLM energy benchmark datasets")
    parser.add_argument("--source", choices=["joulebench", "watt-counts", "tokenpowerbench",
                                              "ecologits", "all"],
                        default="joulebench", help="Benchmark source to import")
    parser.add_argument("--db-path", default="./data/greenflex.db",
                        help="Path to SQLite database")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be imported without modifying DB")
    parser.add_argument("--report", action="store_true",
                        help="Show coverage report only")

    args = parser.parse_args()

    if args.report:
        coverage_report(args.db_path)
        return

    records = []
    if args.source in ("joulebench", "all"):
        for d in JOULEBENCH_DATA:
            records.append(build_benchmark_record(d, "joulebench", "v0.3"))
        print(f"Prepared {len(JOULEBENCH_DATA)} JouleBench records")

    if args.source in ("watt-counts", "all"):
        print("Watt Counts import: download full dataset from arXiv 2604.09048")
        print("  and place CSV at data/benchmarks/watt_counts.csv")
        print("  Then run with --source watt-counts after implementing parser")

    if args.source in ("tokenpowerbench", "all"):
        print("TokenPowerBench import: download from arXiv 2512.03024")

    if args.source in ("ecologits", "all"):
        print("EcoLogits import: cloud API model estimates from genai-impact/ecologits")

    if records:
        import_to_sqlite(args.db_path, records, dry_run=args.dry_run)
    else:
        print("No records to import. Use --report to see current coverage.")


if __name__ == "__main__":
    main()
