"""Phone measurements, readings, calibrations, GPS error trials and precision model (EN-33).

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _created_at():
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade():
    op.create_table(
        "measurement",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("mount", sa.String(8), nullable=False),
        sa.Column("place_name", sa.String(80), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("reference", postgresql.JSONB()),
        sa.Column("tape_side_m", sa.Float()),
        sa.Column("calibration", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("reading_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("perimeter_m", sa.Float()),
        sa.Column("area_m2", sa.Float()),
        sa.Column("closure_error_pct", sa.Float()),
        sa.Column("quality", sa.String(8)),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("method IN ('steps', 'gps', 'car')", name="ck_measurement_method"),
        sa.CheckConstraint(
            "source IN ('phone', 'simulator', 'robot')", name="ck_measurement_source"
        ),
        sa.CheckConstraint("mount IN ('hand', 'robot')", name="ck_measurement_mount"),
        sa.CheckConstraint("status IN ('recording', 'finished')", name="ck_measurement_status"),
        sa.CheckConstraint(
            "char_length(btrim(place_name)) BETWEEN 1 AND 80",
            name="ck_measurement_place",
        ),
        sa.CheckConstraint("reading_count >= 0", name="ck_measurement_reading_count"),
    )
    op.create_index("ix_measurement_device_id", "measurement", ["device_id"])

    op.create_table(
        "measurement_reading",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "measurement_id",
            sa.BigInteger(),
            sa.ForeignKey("measurement.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("t_ms", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("gyro_z_dps", sa.Float()),
        sa.Column("accel_x", sa.Float()),
        sa.Column("accel_y", sa.Float()),
        sa.Column("accel_z", sa.Float()),
        sa.Column("step", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pwm", sa.Float()),
        sa.Column("lat", sa.Float()),
        sa.Column("lon", sa.Float()),
        sa.Column("accuracy_m", sa.Float()),
        sa.UniqueConstraint("measurement_id", "seq", name="uq_measurement_reading_seq"),
        sa.CheckConstraint(
            "kind IN ('motion', 'gps', 'corner')", name="ck_measurement_reading_kind"
        ),
        sa.CheckConstraint("seq >= 0 AND t_ms >= 0", name="ck_measurement_reading_seq"),
    )
    op.create_index(
        "ix_measurement_reading_measurement_id",
        "measurement_reading",
        ["measurement_id"],
    )

    op.create_table(
        "sensor_calibration",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("origin", sa.String(8), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "kind IN ('gyro_bias', 'step_length', 'car_speed')",
            name="ck_sensor_calibration_kind",
        ),
        sa.CheckConstraint("origin IN ('manual', 'model')", name="ck_sensor_calibration_origin"),
    )
    op.create_index("ix_sensor_calibration_device_id", "sensor_calibration", ["device_id"])

    op.create_table(
        "gps_trial",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("place_name", sa.String(80), nullable=False),
        sa.Column("environment", sa.String(12), nullable=False),
        sa.Column("real_distance_m", sa.Float(), nullable=False),
        sa.Column("start_fixes", postgresql.JSONB(), nullable=False),
        sa.Column("end_fixes", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "environment IN ('open', 'buildings', 'trees', 'indoor')",
            name="ck_gps_trial_env",
        ),
        sa.CheckConstraint("real_distance_m >= 0", name="ck_gps_trial_distance"),
    )
    op.create_index("ix_gps_trial_device_id", "gps_trial", ["device_id"])

    op.create_table(
        "precision_model_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("measurement_ids", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        _created_at(),
    )
    op.create_index("ix_precision_model_run_device_id", "precision_model_run", ["device_id"])


def downgrade():
    op.drop_table("precision_model_run")
    op.drop_table("gps_trial")
    op.drop_table("sensor_calibration")
    op.drop_table("measurement_reading")
    op.drop_table("measurement")
