"""Tracks: migrations 0006 (schema) and 0007 (profile seed), up and down, rolled back."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from velocista.infrastructure.persistence.db import engine

ROOT = Path(__file__).parents[3]
RULES = (
    "radius_min angle_min no_sharp separation_min margin zone_distance closed length_min "
    "length_max straight_min straight_max cross_max gap_max"
).split()


@pytest.fixture
def migrated():
    """Connection in a throw-away schema; the whole transaction is rolled back at the end."""
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location", str(ROOT / "src/velocista/infrastructure/persistence/migrations")
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            schema = "migration_tracks_" + uuid4().hex
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config.attributes["connection"] = connection
            yield connection, config
        finally:
            transaction.rollback()


def version(connection):
    return connection.scalar(text("SELECT version_num FROM alembic_version"))


def table_exists(connection, name):
    return connection.scalar(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": name})


def test_upgrade_head_creates_track_table_and_seeds_two_profiles(migrated):
    connection, config = migrated
    command.upgrade(config, "head")
    assert version(connection) == "0007"
    assert table_exists(connection, "track")
    rules = dict(connection.execute(text("SELECT id, rules FROM profile")).all())
    assert {"lgr2026", "libre"} <= set(rules)
    for profile_id in ("lgr2026", "libre"):
        track = rules[profile_id]["track"]
        assert track["line_width_mm"] == 19
        assert track["gap_length_cm"] == 2
        assert all(set(track[name]) == {"enabled", "value"} for name in RULES)
    lgr = rules["lgr2026"]["track"]
    assert lgr["radius_min"] == {"enabled": True, "value": 15}
    assert lgr["length_min"]["value"] == 500  # el prototipo usa 5 m; aquí va en cm
    assert lgr["length_max"]["value"] == 3000
    assert lgr["cross_max"] == {"enabled": True, "value": 0}
    assert rules["libre"]["track"]["cross_max"] == {"enabled": False, "value": 2}


def test_existing_profiles_have_no_track_block_after_upgrade(migrated):
    connection, config = migrated
    command.upgrade(config, "head")
    others = connection.execute(
        text("SELECT id, rules FROM profile WHERE id NOT IN ('lgr2026', 'libre')")
    ).all()
    assert {row.id for row in others} >= {"club", "mr4a", "mr4m", "mr4s"}
    assert all("track" not in row.rules for row in others)


def test_downgrade_to_0005_removes_track_table_and_seeded_profiles(migrated):
    connection, config = migrated
    command.upgrade(config, "head")
    command.downgrade(config, "0005")
    assert version(connection) == "0005"
    assert not table_exists(connection, "track")
    ids = {row.id for row in connection.execute(text("SELECT id FROM profile"))}
    assert ids.isdisjoint({"lgr2026", "libre"})
    assert {"club", "mr4a"} <= ids
    command.upgrade(config, "head")  # y vuelve a subir
    assert version(connection) == "0007"


POINTS = json.dumps([{"x": n, "y": n, "radius": 0, "gap": False} for n in (1, 2)])


def insert_track(connection, profile_id=None):
    connection.execute(
        text(
            "INSERT INTO track (name, board_width_cm, board_height_cm, closed, points, "
            "start_edge, start_t, profile_id, length_cm) VALUES ('keep', 100, 100, false, "
            "CAST(:points AS jsonb), 0, 0.5, :profile_id, 10)"
        ),
        {"points": POINTS, "profile_id": profile_id},
    )


def test_downgrade_refuses_while_tracks_exist(migrated):
    connection, config = migrated
    command.upgrade(config, "head")
    insert_track(connection)
    with pytest.raises(RuntimeError, match="Export/remove saved tracks"):
        command.downgrade(config, "0005")


def test_downgrade_0007_refuses_while_a_track_uses_a_seeded_profile(migrated):
    connection, config = migrated
    command.upgrade(config, "head")
    insert_track(connection, profile_id="lgr2026")
    with pytest.raises(RuntimeError, match="lgr2026/libre"):
        command.downgrade(config, "0006")
