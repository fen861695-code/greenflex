"""add is_task_classifier and official_data_source to model_catalog

Revision ID: c9a5e3f7b2d1
Revises: b8f4d2e9a1c3
Create Date: 2026-08-15 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9a5e3f7b2d1"
down_revision: str | None = "b8f4d2e9a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_catalog",
        sa.Column(
            "is_task_classifier",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "model_catalog",
        sa.Column(
            "official_data_source",
            sa.String(length=512),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("model_catalog", "official_data_source")
    op.drop_column("model_catalog", "is_task_classifier")
