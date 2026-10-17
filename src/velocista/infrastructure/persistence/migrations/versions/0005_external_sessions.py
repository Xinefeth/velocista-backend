"""External sessions, run identity and nullable unavailable measurements.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "external_session",
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("external_robot_id", sa.String(160), nullable=False),
        sa.Column("robot_id", sa.String(40), sa.ForeignKey("robot.id")),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("hello", postgresql.JSONB(), nullable=False),
        sa.Column("config", postgresql.JSONB()),
        sa.Column("lost_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("diagnostics", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "run",
        sa.Column("external_session_id", sa.String(200), sa.ForeignKey("external_session.id")),
    )
    op.add_column("run", sa.Column("external_run_id", sa.String(160)))
    op.add_column("run", sa.Column("closure_status", sa.String(20)))
    op.create_unique_constraint(
        "uq_run_external", "run", ["source", "external_session_id", "external_run_id"]
    )
    for field in ("mode", "line", "battery_compensation", "turbine_power_pct"):
        op.alter_column("run", field, nullable=True)
    for field in ("accumulated_error", "lost_lines", "battery_v"):
        op.alter_column("lap", field, nullable=True)
    op.create_table(
        "external_telemetry",
        sa.Column(
            "session_id", sa.String(200), sa.ForeignKey("external_session.id"), primary_key=True
        ),
        sa.Column("seq", sa.BigInteger(), primary_key=True),
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey("run.id")),
        sa.Column("t_ms", sa.BigInteger(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("session_id", "seq", name="uq_external_sample"),
    )
    op.create_index("ix_external_telemetry_run_id", "external_telemetry", ["run_id"])


def downgrade():
    # Do not silently destroy externally acquired history or invent legacy measurements.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM external_session")):
        raise RuntimeError("Export/remove external acquisition data explicitly before downgrade")
    op.drop_table("external_telemetry")
    op.drop_constraint("uq_run_external", "run", type_="unique")
    for column in ("closure_status", "external_run_id", "external_session_id"):
        op.drop_column("run", column)
    op.drop_table("external_session")
    for field in ("mode", "line", "battery_compensation", "turbine_power_pct"):
        op.alter_column("run", field, nullable=False)
    for field in ("accumulated_error", "lost_lines", "battery_v"):
        op.alter_column("lap", field, nullable=False)
