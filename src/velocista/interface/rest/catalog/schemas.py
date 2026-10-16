"""Esquemas HTTP del contexto `catalog`. Claves JSON en inglés (docs/CONTRACT.md)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

TypeId = Literal[
    "mcu",
    "exp",
    "linea",
    "mux",
    "motor",
    "driver",
    "bat",
    "reg",
    "rueda",
    "chasis",
    "sw",
    "enc",
    "imu",
    "turb",
]


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=40)
    label: str = Field(max_length=120)
    type: Literal["number", "text"]  # antes n/t
    unit: str = Field(max_length=20)
    required: bool


class CapabilitySpec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    key: str = Field(min_length=1, max_length=40)
    unit: str = Field(max_length=20)
    aggregation: Literal["sum_by_quantity", "per_component"]
    field: str | None = Field(default=None, min_length=1, max_length=40)
    fields: list[str] | None = Field(default=None, min_length=2)
    operation: Literal["product"] | None = None
    min: float | None = None
    max: float | None = None


class ComponentTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: str = Field(min_length=1, max_length=40)
    name: str = Field(max_length=120)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    fields: list[FieldSpec]
    capabilities: list[CapabilitySpec]


class ComponentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    type_id: TypeId
    name: str = Field(min_length=1, max_length=120)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    mass_g: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    store: str = Field(default="", max_length=200)
    current_a: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)
    specs: dict[str, StrictStr | StrictInt | StrictFloat]
    stock: int = Field(strict=True, ge=0, le=2147483647)


class ComponentEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    mass_g: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    store: str | None = Field(default=None, max_length=200)
    current_a: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)
    specs: dict[str, StrictStr | StrictInt | StrictFloat] | None = None

    @model_validator(mode="after")
    def _at_least_one(self):
        if not self.model_fields_set:
            raise ValueError("Envía al menos un campo para editar")
        for field in self.model_fields_set - {"current_a"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} no puede ser null")
        return self


class ComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", allow_inf_nan=False)
    id: str
    type_id: TypeId
    name: str
    price: float = Field(gt=0)
    mass_g: float = Field(ge=0)
    store: str
    current_a: float | None = Field(ge=0)
    specs: dict[str, str | int | float]
    stock: int = Field(ge=0)
    archived: bool


class ComponentsPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ComponentOut]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class InventoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stock: int = Field(strict=True, ge=0, le=2147483647)
    revision: int = Field(strict=True, ge=1, le=2147483647)


class InventoryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component_id: str
    stock: int = Field(ge=0)
    in_robots: int = Field(ge=0)  # antes en_robots
    available: int  # antes disponible
    shortage: int = Field(ge=0)  # antes faltante
    revision: int = Field(ge=1)


class InventoryPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[InventoryOut]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
