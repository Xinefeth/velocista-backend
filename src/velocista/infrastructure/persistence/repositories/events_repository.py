"""Implementación SQLAlchemy del port `EventRepository`."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from velocista.application.events.ports import EventRepository
from velocista.domain.events.entities import Event, EventLevel
from velocista.infrastructure.persistence.models.event import EventModel


def _to_entity(row: EventModel) -> Event:
    return Event(
        id=row.id,
        date=row.date,
        system=row.system,
        level=EventLevel(row.level),
        message=row.message,
    )


class SqlAlchemyEventRepository(EventRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: Event) -> Event:
        row = EventModel(system=event.system, level=event.level.value, message=event.message)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return _to_entity(row)

    def list(self, *, limit: int) -> list[Event]:
        stmt = (
            select(EventModel).order_by(EventModel.date.desc(), EventModel.id.desc()).limit(limit)
        )
        return [_to_entity(row) for row in self._session.scalars(stmt)]
