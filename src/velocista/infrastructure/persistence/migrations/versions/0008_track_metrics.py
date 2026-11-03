"""Perimeter and area of each track (EN-28, additive).

Revision ID: 0008
Revises: 0007

SUPUESTO PENDIENTE DEL PO: unidades cm y cm2. Los calcula el frontend y el backend los guarda.
Es una revisión aparte de `0006` porque esa ya se fusionó en `main` (PR #7) y no puede editarse.
Las filas existentes quedan con NULL, que es un valor válido.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("track", sa.Column("perimeter_cm", sa.Float(), nullable=True))
    op.add_column("track", sa.Column("area_cm2", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_track_perimeter",
        "track",
        "perimeter_cm IS NULL OR (perimeter_cm >= 0 AND perimeter_cm <= 400000)",
    )
    op.create_check_constraint(
        "ck_track_area",
        "track",
        "area_cm2 IS NULL OR (area_cm2 >= 0 AND area_cm2 <= board_width_cm * board_height_cm * 4)",
    )
    op.create_check_constraint(
        "ck_track_metrics_closed",
        "track",
        "closed OR (perimeter_cm IS NULL AND area_cm2 IS NULL)",
    )


def downgrade():
    # Son valores derivados que el frontend puede recalcular: se pueden descartar sin exportar.
    op.drop_constraint("ck_track_metrics_closed", "track", type_="check")
    op.drop_constraint("ck_track_area", "track", type_="check")
    op.drop_constraint("ck_track_perimeter", "track", type_="check")
    op.drop_column("track", "area_cm2")
    op.drop_column("track", "perimeter_cm")
