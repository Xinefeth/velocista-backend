"""Ports del contexto `tracks`: `infrastructure` los implementa con SQLAlchemy."""

from __future__ import annotations

from typing import Protocol

from velocista.domain.tracks.entities import Track


class TracksRepository(Protocol):
    def list_tracks(self, *, limit: int, offset: int) -> tuple[list[Track], int]:
        """Pistas de la más recientemente editada a la más antigua, y el total."""
        ...

    def get_track(self, track_id: int) -> Track | None: ...

    def add_track(self, track: Track) -> Track: ...

    def update_track(self, track_id: int, track: Track) -> Track | None:
        """Reemplaza los campos editables; devuelve None si la pista no existe."""
        ...

    def delete_track(self, track_id: int) -> bool:
        """True si la pista existía y se borró."""
        ...

    def profile_exists(self, profile_id: str) -> bool: ...
