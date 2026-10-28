"""Tracks of the track drawing tool (EN-28).

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _array_between(column, low, high):
    # CASE evita que jsonb_array_length falle con un valor que no es arreglo.
    return (
        f"CASE WHEN jsonb_typeof({column}) = 'array' "
        f"THEN jsonb_array_length({column}) BETWEEN {low} AND {high} ELSE false END"
    )


def upgrade():
    op.create_table(
        "track",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("board_width_cm", sa.Float(), nullable=False),
        sa.Column("board_height_cm", sa.Float(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("points", postgresql.JSONB(), nullable=False),
        sa.Column(
            "zones", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("start_edge", sa.Integer(), nullable=False),
        sa.Column("start_t", sa.Float(), nullable=False),
        sa.Column("profile_id", sa.String(40), sa.ForeignKey("profile.id", ondelete="RESTRICT")),
        sa.Column("length_cm", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("char_length(btrim(name)) BETWEEN 1 AND 80", name="ck_track_name"),
        sa.CheckConstraint(
            "board_width_cm BETWEEN 50 AND 2000 AND board_height_cm BETWEEN 50 AND 2000",
            name="ck_track_board",
        ),
        sa.CheckConstraint(_array_between("points", 2, 500), name="ck_track_points"),
        sa.CheckConstraint(_array_between("zones", 0, 100), name="ck_track_zones"),
        sa.CheckConstraint("start_edge >= 0", name="ck_track_start_edge"),
        sa.CheckConstraint("start_t BETWEEN 0 AND 1", name="ck_track_start_t"),
        sa.CheckConstraint("length_cm > 0 AND length_cm <= 100000", name="ck_track_length"),
    )
    op.create_index("ix_track_profile_id", "track", ["profile_id"])


def downgrade():
    # Mismo criterio que 0005: no se destruyen datos de usuario sin exportarlos antes.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM track")):
        raise RuntimeError("Export/remove saved tracks explicitly before downgrade")
    op.drop_index("ix_track_profile_id", table_name="track")
    op.drop_table("track")
