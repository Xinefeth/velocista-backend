"""Ports del contexto `events`."""

from __future__ import annotations

from typing import Protocol

from velocista.domain.events.entities import Event


class EventRepository(Protocol):
    def add(self, event: Event) -> Event: ...

    def list(self, *, limit: int) -> list[Event]: ...
