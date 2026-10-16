"""Esquemas HTTP del contexto `events`. Claves JSON en inglés."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from velocista.domain.events.entities import Event


class EventIn(BaseModel):
    system: str = Field(max_length=40)
    level: Literal["info", "warning", "error"] = "info"
    message: str = Field(max_length=500)


class EventOut(EventIn):
    id: int
    date: datetime

    @classmethod
    def from_entity(cls, event: Event) -> EventOut:
        return cls(
            id=event.id,
            date=event.date,
            system=event.system,
            level=event.level.value,
            message=event.message,
        )
