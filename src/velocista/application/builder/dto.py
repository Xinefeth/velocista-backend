"""DTOs de entrada de los casos de uso de `builder` (independientes de pydantic/HTTP)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PartInput:
    component_id: str
    quantity: int


@dataclass(frozen=True)
class VersionCreateInput:
    base_version_id: int | None
    note: str
    status: str  # current | concept | draft
    parts: dict[str, PartInput]  # indexado por slot_id
