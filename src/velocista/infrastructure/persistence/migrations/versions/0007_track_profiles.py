"""Track rules profiles lgr2026 and libre (EN-28).

Datos de referencia de las reglas de pista. SUPUESTO PENDIENTE DEL PO: los valores salen del
prototipo del trazador (`trazador-de-pistas.html`) y no se han contrastado con el libro de reglas.
Todas las distancias van en cm (el prototipo guarda el largo mínimo y máximo en metros; aquí se
convierten a cm); `angle_min` en grados; `line_width_mm` en milímetros.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

PROFILE = sa.table(
    "profile",
    sa.column("id", sa.String),
    sa.column("competition", sa.String),
    sa.column("label", sa.String),
    sa.column("category", sa.String),
    sa.column("rules", JSONB),
)


def _rule(enabled, value):
    return {"enabled": enabled, "value": value}


PROFILES = [
    {
        "id": "lgr2026",
        "competition": "Let's Go Robot 2026",
        "label": "LGR 2026",
        "category": "Velocista",
        "rules": {
            "track": {
                "line_width_mm": 19,
                "gap_length_cm": 2,
                "radius_min": _rule(True, 15),
                "angle_min": _rule(True, 90),
                "no_sharp": _rule(False, True),
                "separation_min": _rule(True, 30),
                "margin": _rule(True, 30),
                "zone_distance": _rule(True, 30),
                "closed": _rule(True, True),
                "length_min": _rule(False, 500),
                "length_max": _rule(False, 3000),
                "straight_min": _rule(False, 10),
                "straight_max": _rule(False, 200),
                "cross_max": _rule(True, 0),
                "gap_max": _rule(True, 0),
            }
        },
    },
    {
        "id": "libre",
        "competition": "Entrenamiento libre",
        "label": "Libre",
        "category": "Entrenamiento",
        "rules": {
            "track": {
                "line_width_mm": 19,
                "gap_length_cm": 2,
                "radius_min": _rule(True, 5),
                "angle_min": _rule(True, 30),
                "no_sharp": _rule(False, True),
                "separation_min": _rule(True, 12),
                "margin": _rule(True, 12),
                "zone_distance": _rule(True, 10),
                "closed": _rule(True, True),
                "length_min": _rule(False, 500),
                "length_max": _rule(False, 3000),
                "straight_min": _rule(False, 10),
                "straight_max": _rule(False, 200),
                "cross_max": _rule(False, 2),
                "gap_max": _rule(False, 4),
            }
        },
    },
]


def upgrade():
    op.bulk_insert(PROFILE, PROFILES)


def downgrade():
    connection = op.get_bind()
    ids = [p["id"] for p in PROFILES]
    if connection.scalar(
        sa.text("SELECT count(*) FROM track WHERE profile_id = ANY(:ids)"), {"ids": ids}
    ):
        raise RuntimeError("Reassign or delete tracks that use lgr2026/libre before downgrade")
    connection.execute(sa.text("DELETE FROM profile WHERE id = ANY(:ids)"), {"ids": ids})
