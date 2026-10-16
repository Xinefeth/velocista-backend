"""Reference component types, slots, controllers and competition profiles.

Revision ID: 0003
Revises: 0002
"""

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

DATA = json.loads(Path(__file__).with_name("0003_reference_data.json").read_text(encoding="utf-8"))
TABLES = {
    "component_type": sa.table(
        "component_type",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("color", sa.String),
        sa.column("fields", JSONB),
        sa.column("capabilities", JSONB),
    ),
    "slot": sa.table(
        "slot",
        sa.column("id", sa.String),
        sa.column("type_id", sa.String),
        sa.column("name", sa.String),
        sa.column("required", sa.Boolean),
        sa.column("quantity_editable", sa.Boolean),
        sa.column("rules_dependent", sa.Boolean),
    ),
    "controller": sa.table(
        "controller",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("short_name", sa.String),
        sa.column("description", sa.Text),
        sa.column("parameters", JSONB),
        sa.column("presets", JSONB),
    ),
    "profile": sa.table(
        "profile",
        sa.column("id", sa.String),
        sa.column("competition", sa.String),
        sa.column("label", sa.String),
        sa.column("category", sa.String),
        sa.column("rules", JSONB),
    ),
}


def upgrade():
    for name, table in TABLES.items():
        op.bulk_insert(table, DATA[name])


def downgrade():
    for name, table in reversed(list(TABLES.items())):
        op.execute(table.delete().where(table.c.id.in_([row["id"] for row in DATA[name]])))
