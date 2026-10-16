"""Esquemas HTTP del contexto `builder`. Claves JSON en inglés (docs/CONTRACT.md)."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from velocista.domain.builder.entities import Robot


class RobotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    short_code: str = Field(min_length=1, max_length=12)
    type: Literal["racer", "minisumo"]
    firmware: str | None = Field(default=None, max_length=20)


class RobotOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    short_code: str
    type: Literal["racer", "minisumo"]
    firmware: str | None
    current_version_id: int | None = Field(ge=1, le=9007199254740991)
    archived: bool

    @classmethod
    def from_entity(cls, robot: Robot) -> RobotOut:
        return cls(
            id=robot.id,
            name=robot.name,
            short_code=robot.short_code,
            type=robot.type.value,
            firmware=robot.firmware,
            current_version_id=robot.current_version_id,
            archived=robot.archived,
        )


class RobotEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    short_code: str | None = Field(default=None, min_length=1, max_length=12)
    firmware: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _at_least_one(self):
        if not self.model_fields_set:
            raise ValueError("Envía al menos un campo")
        for field in self.model_fields_set - {"firmware"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} no admite null")
        return self


class PartCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component_id: str = Field(min_length=1, max_length=40)
    quantity: int = Field(strict=True, ge=1, le=2147483647)


class VersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_version_id: int | None = Field(ge=1, le=9007199254740991, strict=True)
    note: str = Field(max_length=1000)
    status: Literal["current", "concept", "draft"]
    parts: dict[str, PartCreate] = Field(max_length=14)


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type_id: str
    name: str
    required: bool
    quantity_editable: bool
    rules_dependent: bool


class RobotsPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[RobotOut]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class ComponentSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str
    type_id: str
    name: str
    price: float = Field(gt=0)
    mass_g: float = Field(ge=0)
    store: str
    current_a: float | None = Field(ge=0)
    specs: dict[str, str | int | float]


class PartOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component_id: str
    quantity: int = Field(ge=1)
    component_snapshot: ComponentSnapshot


class VersionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int = Field(ge=1, le=9007199254740991)
    robot_id: str
    label: str = Field(pattern=r"^v[0-9]+$")
    date: AwareDatetime
    note: str
    status: Literal["current", "previous", "discarded", "concept", "draft"]
    parts: dict[str, PartOut]


class VersionsPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[VersionOut]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
