"""Objetos de transporte del contexto `tracks` entre `application` e `interface`."""

from __future__ import annotations

from dataclasses import dataclass

from velocista.domain.tracks.entities import Track


@dataclass(frozen=True)
class TracksPage:
    items: list[Track]
    total: int
    limit: int
    offset: int
