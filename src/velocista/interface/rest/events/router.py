"""Controlador REST del contexto `events`. Endpoints: /api/events."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from velocista.application.events.use_cases import ListEvents, RecordEvent
from velocista.domain.events.entities import EventLevel
from velocista.infrastructure.persistence.db import get_session
from velocista.infrastructure.persistence.repositories.events_repository import (
    SqlAlchemyEventRepository,
)
from velocista.interface.rest.events.schemas import EventIn, EventOut

router = APIRouter(prefix="/api/events", tags=["events"])
DbSession = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[EventOut], operation_id="listEvents")
def list_events(session: DbSession, limit: Annotated[int, Query(ge=1, le=500)] = 50):
    events = ListEvents(SqlAlchemyEventRepository(session)).execute(limit=limit)
    return [EventOut.from_entity(e) for e in events]


@router.post("", response_model=EventOut, status_code=201, operation_id="createEvent")
def create_event(data: EventIn, session: DbSession):
    event = RecordEvent(SqlAlchemyEventRepository(session)).execute(
        system=data.system, level=EventLevel(data.level), message=data.message
    )
    return EventOut.from_entity(event)
