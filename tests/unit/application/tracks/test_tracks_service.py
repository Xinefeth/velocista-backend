"""Tracks: use cases with an in-memory double of the repository port."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from support.track_fixtures import make_track
from velocista.application.tracks.ports import TracksRepository
from velocista.application.tracks.use_cases import TracksService
from velocista.domain.shared.errors import NotFound, Validation


class InMemoryTracksRepository(TracksRepository):
    """Implements the port without a database."""

    def __init__(self, profiles=("lgr2026",)):
        self.rows = {}
        self.profiles = set(profiles)
        self.next_id = 1
        self.ticks = 0

    def _now(self):
        # Reloj incremental: evita empates de microsegundos en el orden por edición.
        self.ticks += 1
        return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=self.ticks)

    def list_tracks(self, *, limit, offset):
        ordered = sorted(self.rows.values(), key=lambda t: (t.updated_at, t.id), reverse=True)
        return ordered[offset : offset + limit], len(ordered)

    def get_track(self, track_id):
        return self.rows.get(track_id)

    def add_track(self, track):
        now = self._now()
        saved = replace(track, id=self.next_id, created_at=now, updated_at=now)
        self.rows[saved.id] = saved
        self.next_id += 1
        return saved

    def update_track(self, track_id, track):
        old = self.rows.get(track_id)
        if old is None:
            return None
        saved = replace(track, id=track_id, created_at=old.created_at, updated_at=self._now())
        self.rows[track_id] = saved
        return saved

    def delete_track(self, track_id):
        return self.rows.pop(track_id, None) is not None

    def profile_exists(self, profile_id):
        return profile_id in self.profiles


@pytest.fixture
def service():
    return TracksService(InMemoryTracksRepository())


class TestCreate:
    def test_create_when_valid_assigns_id_and_dates(self, service):
        saved = service.create_track(make_track())
        assert saved.id == 1
        assert saved.created_at is not None
        assert saved.updated_at is not None

    def test_create_stores_length_as_sent_without_recomputing(self, service):
        assert service.create_track(make_track(length_cm=812.4)).length_cm == 812.4

    def test_create_when_name_has_spaces_trims_it(self, service):
        assert service.create_track(make_track(name="  Oval  ")).name == "Oval"

    def test_create_when_profile_exists_keeps_it(self, service):
        assert service.create_track(make_track(profile_id="lgr2026")).profile_id == "lgr2026"

    def test_create_when_profile_unknown_raises_validation(self, service):
        with pytest.raises(Validation) as error:
            service.create_track(make_track(profile_id="nope"))
        assert error.value.reason == "track_profile_unknown"

    def test_create_when_track_invalid_raises_validation(self, service):
        with pytest.raises(Validation) as error:
            service.create_track(make_track(length_cm=0))
        assert error.value.reason == "track_length_invalid"
        assert service.repository.rows == {}

    def test_create_when_exported_track_is_imported_makes_a_new_one(self, service):
        first = service.create_track(make_track())
        imported = service.create_track(first)  # an export carries id and dates
        assert imported.id != first.id


class TestReadUpdateDelete:
    def test_get_when_missing_raises_not_found(self, service):
        with pytest.raises(NotFound) as error:
            service.get_track(99)
        assert error.value.reason == "track_not_found"

    def test_export_when_missing_raises_not_found(self, service):
        with pytest.raises(NotFound):
            service.export_track(99)

    def test_list_when_paginated_returns_page_and_total(self, service):
        for _ in range(3):
            service.create_track(make_track())
        page = service.list_tracks(limit=2, offset=1)
        assert (page.total, page.limit, page.offset, len(page.items)) == (3, 2, 1, 2)

    def test_list_orders_by_most_recently_edited(self, service):
        first = service.create_track(make_track())
        service.create_track(make_track())
        service.update_track(first.id, make_track(name="Edited"))
        assert service.list_tracks(limit=10, offset=0).items[0].id == first.id

    def test_update_replaces_fields_and_keeps_id_and_created_at(self, service):
        first = service.create_track(make_track())
        saved = service.update_track(first.id, make_track(name="Edited", length_cm=900))
        assert (saved.id, saved.name, saved.length_cm) == (first.id, "Edited", 900)
        assert saved.created_at == first.created_at
        assert saved.updated_at >= first.updated_at

    def test_update_when_missing_raises_not_found_before_validating(self, service):
        with pytest.raises(NotFound):
            service.update_track(99, make_track(length_cm=0))

    def test_update_when_invalid_raises_validation(self, service):
        first = service.create_track(make_track())
        with pytest.raises(Validation):
            service.update_track(first.id, make_track(length_cm=0))

    def test_update_when_profile_unknown_raises_validation(self, service):
        first = service.create_track(make_track())
        with pytest.raises(Validation) as error:
            service.update_track(first.id, make_track(profile_id="nope"))
        assert error.value.reason == "track_profile_unknown"

    def test_delete_removes_the_track(self, service):
        first = service.create_track(make_track())
        service.delete_track(first.id)
        with pytest.raises(NotFound):
            service.get_track(first.id)

    def test_delete_when_missing_raises_not_found(self, service):
        with pytest.raises(NotFound):
            service.delete_track(99)
