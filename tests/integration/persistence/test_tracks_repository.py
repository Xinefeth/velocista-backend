"""Tracks: repository and CHECK/FK constraints on real PostgreSQL (isolated schema)."""

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from support.track_fixtures import make_track
from velocista.domain.tracks.entities import Start
from velocista.infrastructure.persistence.models.rules import ProfileModel
from velocista.infrastructure.persistence.models.tracks import TrackModel
from velocista.infrastructure.persistence.repositories.tracks_repository import (
    SqlAlchemyTracksRepository,
)


@pytest.fixture
def session(db):
    with Session(bind=db, expire_on_commit=False, join_transaction_mode="create_savepoint") as s:
        yield s


@pytest.fixture
def repo(session):
    return SqlAlchemyTracksRepository(session)


def raw_row(**overrides) -> TrackModel:
    """A valid ORM row; overrides let each test break one constraint."""
    fields = {
        "name": "Oval",
        "board_width_cm": 300.0,
        "board_height_cm": 250.0,
        "closed": True,
        "points": [{"x": 1, "y": 1, "radius": 0, "gap": False}] * 3,
        "zones": [],
        "start_edge": 0,
        "start_t": 0.5,
        "profile_id": None,
        "length_cm": 100.0,
    }
    fields.update(overrides)
    return TrackModel(**fields)


class TestRepository:
    def test_add_and_get_round_trip_keeps_every_field(self, repo):
        saved = repo.add_track(make_track(profile_id="club", length_cm=812.4))
        loaded = repo.get_track(saved.id)
        assert loaded == saved
        assert loaded.length_cm == 812.4
        assert loaded.points[0].radius == 15
        assert loaded.zones[0].name == "timer post"
        assert loaded.start == Start(0, 0.35)
        assert loaded.created_at is not None

    def test_get_when_missing_returns_none(self, repo):
        assert repo.get_track(999999) is None

    def test_update_replaces_fields_keeps_created_at_and_moves_updated_at(self, repo):
        saved = repo.add_track(make_track())
        updated = repo.update_track(saved.id, make_track(name="Edited", length_cm=900))
        assert (updated.id, updated.name, updated.length_cm) == (saved.id, "Edited", 900)
        assert updated.created_at == saved.created_at
        assert updated.updated_at > saved.updated_at

    def test_update_when_missing_returns_none(self, repo):
        assert repo.update_track(999999, make_track()) is None

    def test_delete_removes_and_reports(self, repo):
        saved = repo.add_track(make_track())
        assert repo.delete_track(saved.id) is True
        assert repo.get_track(saved.id) is None
        assert repo.delete_track(saved.id) is False

    def test_list_orders_by_updated_at_descending_and_paginates(self, repo):
        first = repo.add_track(make_track(name="first"))
        second = repo.add_track(make_track(name="second"))
        third = repo.add_track(make_track(name="third"))
        repo.update_track(first.id, make_track(name="first edited"))
        items, total = repo.list_tracks(limit=10, offset=0)
        assert total == 3
        assert [t.id for t in items] == [first.id, third.id, second.id]
        page, total = repo.list_tracks(limit=1, offset=1)
        assert (total, [t.id for t in page]) == (3, [third.id])

    def test_profile_exists_for_seeded_and_unknown(self, repo):
        assert repo.profile_exists("club") is True
        assert repo.profile_exists("nope") is False


class TestConstraints:
    @pytest.mark.parametrize(
        "overrides",
        [
            {"name": "   "},
            {"name": "x" * 81},
            {"board_width_cm": 49.0},
            {"board_height_cm": 2001.0},
            {"points": [{"x": 1, "y": 1, "radius": 0, "gap": False}]},
            {"points": [{"x": 1, "y": 1, "radius": 0, "gap": False}] * 501},
            {"points": {}},
            {"zones": [{"x": 0, "y": 0, "width": 1, "height": 1, "name": ""}] * 101},
            {"zones": "not an array"},
            {"start_edge": -1},
            {"start_t": 1.5},
            {"start_t": -0.1},
            {"length_cm": 0.0},
            {"length_cm": 100000.5},
        ],
        ids=lambda o: next(iter(o)) + "=" + str(list(o.values())[0])[:20],
    )
    def test_check_rejects_values_outside_the_limits(self, session, overrides):
        session.add(raw_row(**overrides))
        # varchar(80) corta antes que el CHECK con un nombre de 81 caracteres (DataError)
        with pytest.raises((IntegrityError, DataError)):
            session.flush()
        session.rollback()

    def test_check_accepts_the_limits(self, session):
        session.add(raw_row(board_width_cm=50.0, board_height_cm=2000.0, length_cm=100000.0))
        session.add(raw_row(points=[{"x": 1, "y": 1, "radius": 0, "gap": False}] * 2, start_t=0))
        session.flush()

    def test_foreign_key_rejects_unknown_profile(self, session):
        session.add(raw_row(profile_id="nope"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    def test_foreign_key_restricts_deleting_a_profile_used_by_a_track(self, session):
        session.add(raw_row(profile_id="club"))
        session.flush()
        session.delete(session.get(ProfileModel, "club"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    def test_zones_default_to_empty_array(self, session):
        points = json.dumps([{"x": n, "y": n, "radius": 0, "gap": False} for n in (1, 2, 3)])
        session.execute(
            text(
                "INSERT INTO track (name, board_width_cm, board_height_cm, closed, points, "
                "start_edge, start_t, length_cm) VALUES ('d', 100, 100, true, "
                "CAST(:points AS jsonb), 0, 0.5, 10)"
            ),
            {"points": points},
        )
        assert session.execute(text("SELECT zones FROM track")).scalar_one() == []
