"""add recommended_batch_size to model_catalog

Revision ID: b8f4d2e9a1c3
Revises: a7c3f9d2e1b0
Create Date: 2026-08-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8f4d2e9a1c3"
down_revision: str | None = "a7c3f9d2e1b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_catalog",
        sa.Column(
            "recommended_batch_size",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("model_catalog", "recommended_batch_size")
