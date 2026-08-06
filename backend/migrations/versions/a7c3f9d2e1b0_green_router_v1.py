"""green router v1: recommendation tables

Revision ID: a7c3f9d2e1b0
Revises: f59417dcb05c
Create Date: 2026-08-06 18:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3f9d2e1b0"
down_revision: str | None = "f59417dcb05c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Model task profiles: statistical quality/energy profiles per model-task pair
    op.create_table(
        "model_task_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("complexity_level", sa.String(length=16), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_quality_score_bps", sa.Integer(), nullable=True),
        sa.Column("quality_std_bps", sa.Integer(), nullable=True),
        sa.Column("avg_output_tokens_per_1k_input", sa.Integer(), nullable=True),
        sa.Column("avg_latency_ms_per_1k_output", sa.Integer(), nullable=True),
        sa.Column("avg_energy_micro_wh_per_1k_output", sa.Integer(), nullable=True),
        sa.Column("failure_rate_bps", sa.Integer(), nullable=True),
        sa.Column("profile_version", sa.String(length=64), nullable=False),
        sa.Column("provenance", sa.String(length=24), nullable=False, server_default="simulated"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["model_catalog.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "model_id",
            "task_type",
            "complexity_level",
            "profile_version",
            name="uq_profile_model_task_version",
        ),
    )
    op.create_index("ix_profile_model", "model_task_profiles", ["model_id"], unique=False)
    op.create_index(
        "ix_profile_task", "model_task_profiles", ["task_type", "complexity_level"], unique=False
    )

    # Recommendation decisions: audit log of every recommendation (no prompts stored)
    op.create_table(
        "recommendation_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("recommended_model_id", sa.String(length=64), nullable=False),
        sa.Column("recommended_tier", sa.String(length=24), nullable=False),
        sa.Column("recommended_mode", sa.String(length=24), nullable=False),
        sa.Column("confidence_bps", sa.Integer(), nullable=False),
        sa.Column("quality_risk_level", sa.String(length=16), nullable=False),
        sa.Column("estimated_energy_micro_wh", sa.Integer(), nullable=False),
        sa.Column("estimated_price_micro_rmb", sa.Integer(), nullable=False),
        sa.Column("estimated_carbon_micro_g", sa.Integer(), nullable=False),
        sa.Column("estimated_wait_seconds", sa.Integer(), nullable=False),
        sa.Column("estimated_execution_seconds", sa.Integer(), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("alternatives_json", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("profile_version", sa.String(length=64), nullable=False),
        sa.Column("provenance", sa.String(length=24), nullable=False, server_default="simulated"),
        sa.Column("shadow_mode", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("user_override_model_id", sa.String(length=64), nullable=True),
        sa.Column("override_reason", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recommended_model_id"], ["model_catalog.id"]),
        sa.ForeignKeyConstraint(["user_override_model_id"], ["model_catalog.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recommendation_tenant", "recommendation_decisions", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_recommendation_created", "recommendation_decisions", ["created_at"], unique=False
    )
    op.create_index(
        "ix_recommendation_request_hash",
        "recommendation_decisions",
        ["request_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_recommendation_request_hash", table_name="recommendation_decisions")
    op.drop_index("ix_recommendation_created", table_name="recommendation_decisions")
    op.drop_index("ix_recommendation_tenant", table_name="recommendation_decisions")
    op.drop_table("recommendation_decisions")

    op.drop_index("ix_profile_task", table_name="model_task_profiles")
    op.drop_index("ix_profile_model", table_name="model_task_profiles")
    op.drop_table("model_task_profiles")
