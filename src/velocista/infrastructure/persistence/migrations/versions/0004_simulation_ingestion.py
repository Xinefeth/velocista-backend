"""Persist simulation service run IDs for idempotent ingestion.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("run", sa.Column("ingestion_id", sa.String(length=120), nullable=True))
    op.create_unique_constraint("uq_run_ingestion_id", "run", ["ingestion_id"])


def downgrade() -> None:
    op.drop_constraint("uq_run_ingestion_id", "run", type_="unique")
    op.drop_column("run", "ingestion_id")
