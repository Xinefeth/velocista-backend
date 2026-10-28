"""Casos de uso del contexto `tracks`. Orquestan dominio y ports; no conocen HTTP ni SQL."""

from __future__ import annotations

from dataclasses import replace

from velocista.application.tracks.dto import TracksPage
from velocista.application.tracks.ports import TracksRepository
from velocista.domain.shared.errors import NotFound, Validation
from velocista.domain.tracks.entities import Track
from velocista.domain.tracks.validation import validate_track


class TracksService:
    def __init__(self, repository: TracksRepository):
        self.repository = repository

    def list_tracks(self, *, limit: int, offset: int) -> TracksPage:
        items, total = self.repository.list_tracks(limit=limit, offset=offset)
        return TracksPage(items=items, total=total, limit=limit, offset=offset)

    def get_track(self, track_id: int) -> Track:
        track = self.repository.get_track(track_id)
        if track is None:
            raise NotFound("track_not_found", "Track does not exist")
        return track

    def export_track(self, track_id: int) -> Track:
        return self.get_track(track_id)

    def create_track(self, track: Track) -> Track:
        """Crea una pista nueva; también es la vía de importación de un JSON ya mapeado.

        `length_cm` se guarda tal como llega: el backend no recalcula la geometría.
        """
        track = self._checked(track)
        return self.repository.add_track(track)

    def update_track(self, track_id: int, track: Track) -> Track:
        self.get_track(track_id)  # 404 antes que 422
        track = self._checked(track)
        updated = self.repository.update_track(track_id, track)
        if updated is None:  # borrada entre la lectura y la escritura
            raise NotFound("track_not_found", "Track does not exist")
        return updated

    def delete_track(self, track_id: int) -> None:
        if not self.repository.delete_track(track_id):
            raise NotFound("track_not_found", "Track does not exist")

    def _checked(self, track: Track) -> Track:
        track = replace(track, name=track.name.strip())
        validate_track(track)
        if track.profile_id is not None and not self.repository.profile_exists(track.profile_id):
            raise Validation("track_profile_unknown", "Profile does not exist")
        return track
