"""Casos de uso del contexto `events`.

`RecordEvent` es la interfaz pública con la que otros contextos registran eventos.
"""

from __future__ import annotations

from velocista.application.events.ports import EventRepository
from velocista.domain.events.entities import Event, EventLevel


class RecordEvent:
    def __init__(self, events: EventRepository) -> None:
        self._events = events

    def execute(self, *, system: str, level: EventLevel, message: str) -> Event:
        return self._events.add(Event(system=system, level=level, message=message))


class ListEvents:
    def __init__(self, events: EventRepository) -> None:
        self._events = events

    def execute(self, *, limit: int) -> list[Event]:
        return self._events.list(limit=limit)
