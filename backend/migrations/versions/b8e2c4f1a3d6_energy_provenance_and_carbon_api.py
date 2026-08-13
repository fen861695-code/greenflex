"""energy data provenance tiers and real-time carbon intensity

Revision ID: b8e2c4f1a3d6
Revises: a7c3f9d2e1b0
Create Date: 2026-08-13 02:40:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e2c4f1a3d6"
down_revision: str | None = "a7c3f9d2e1b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Extend model_catalog with energy provenance metadata ---
    op.add_column(
        "model_catalog",
        sa.Column(
            "energy_data_provenance",
            sa.String(length=24),
            nullable=False,
            server_default="insufficient_data",
        ),
    )
    op.add_column(
        "model_catalog",
        sa.Column("energy_data_source", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "model_catalog",
        sa.Column(
            "energy_confidence_bps",
            sa.Integer(),
            nullable=False,
            server_default="2000",
        ),
    )
    op.add_column(
        "model_catalog",
        sa.Column("reference_gpu_model", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "model_catalog",
        sa.Column("parameter_count_b", sa.Float(), nullable=True),
    )
    op.add_column(
        "model_catalog",
        sa.Column("quantization_bits", sa.Integer(), nullable=True),
    )
    op.add_column(
        "model_catalog",
        sa.Column("architecture_family", sa.String(length=32), nullable=True),
    )

    # --- GPU energy profiles: per-GPU calibration coefficients ---
    op.create_table(
        "gpu_energy_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("gpu_model", sa.String(length=64), nullable=False),
        sa.Column("gpu_uuid", sa.String(length=128), nullable=True),
        sa.Column("tdp_watts", sa.Integer(), nullable=True),
        sa.Column("memory_bandwidth_gbps", sa.Float(), nullable=True),
        sa.Column("compute_tflops_fp16", sa.Float(), nullable=True),
        sa.Column("efficiency_factor", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("calibration_sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_calibrated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calibration_provenance", sa.String(length=24), nullable=False, server_default="factory_spec"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gpu_model", name="uq_gpu_profile_model"),
    )
    op.create_index("ix_gpu_profile_model", "gpu_energy_profiles", ["gpu_model"], unique=False)

    # --- Model energy benchmarks: external dataset entries (Watt Counts, JouleBench, etc.) ---
    op.create_table(
        "model_energy_benchmarks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_family", sa.String(length=64), nullable=False),
        sa.Column("parameter_count_b", sa.Float(), nullable=False),
        sa.Column("quantization_bits", sa.Integer(), nullable=True),
        sa.Column("gpu_model", sa.String(length=64), nullable=False),
        sa.Column("gpu_architecture", sa.String(length=32), nullable=True),
        sa.Column("avg_power_watts", sa.Float(), nullable=False),
        sa.Column("throughput_tokens_per_second", sa.Float(), nullable=False),
        sa.Column("energy_joules_per_token", sa.Float(), nullable=False),
        sa.Column("energy_wh_per_1k_output", sa.Float(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=True),
        sa.Column("serving_mode", sa.String(length=16), nullable=True),
        sa.Column("dataset_source", sa.String(length=64), nullable=False),
        sa.Column("dataset_version", sa.String(length=32), nullable=True),
        sa.Column("provenance_tier", sa.String(length=24), nullable=False, server_default="l2_benchmark"),
        sa.Column("confidence_bps", sa.Integer(), nullable=False, server_default="7000"),
        sa.Column("measurement_method", sa.String(length=32), nullable=True),
        sa.Column("raw_reference_url", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_benchmark_model_family",
        "model_energy_benchmarks",
        ["model_family", "parameter_count_b"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_gpu",
        "model_energy_benchmarks",
        ["gpu_model"],
        unique=False,
    )

    # --- Carbon intensity cache: real-time grid carbon intensity with TTL ---
    op.create_table(
        "carbon_intensity_cache",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("region_code", sa.String(length=16), nullable=False),
        sa.Column("zone", sa.String(length=64), nullable=True),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("carbon_g_per_kwh", sa.Integer(), nullable=False),
        sa.Column("renewable_share_bps", sa.Integer(), nullable=True),
        sa.Column("power_mix_json", sa.Text(), nullable=True),
        sa.Column("data_source", sa.String(length=32), nullable=False),
        sa.Column("data_source_version", sa.String(length=64), nullable=True),
        sa.Column("provenance", sa.String(length=24), nullable=False, server_default="estimated"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "region_code", "interval_start", name="uq_carbon_region_interval"
        ),
    )
    op.create_index(
        "ix_carbon_region_time",
        "carbon_intensity_cache",
        ["region_code", "interval_start"],
        unique=False,
    )
    op.create_index(
        "ix_carbon_expires",
        "carbon_intensity_cache",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_carbon_expires", table_name="carbon_intensity_cache")
    op.drop_index("ix_carbon_region_time", table_name="carbon_intensity_cache")
    op.drop_table("carbon_intensity_cache")

    op.drop_index("ix_benchmark_gpu", table_name="model_energy_benchmarks")
    op.drop_index("ix_benchmark_model_family", table_name="model_energy_benchmarks")
    op.drop_table("model_energy_benchmarks")

    op.drop_index("ix_gpu_profile_model", table_name="gpu_energy_profiles")
    op.drop_table("gpu_energy_profiles")

    op.drop_column("model_catalog", "architecture_family")
    op.drop_column("model_catalog", "quantization_bits")
    op.drop_column("model_catalog", "parameter_count_b")
    op.drop_column("model_catalog", "reference_gpu_model")
    op.drop_column("model_catalog", "energy_confidence_bps")
    op.drop_column("model_catalog", "energy_data_source")
    op.drop_column("model_catalog", "energy_data_provenance")
