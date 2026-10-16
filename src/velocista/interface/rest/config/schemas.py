"""Esquemas HTTP del contexto `config` (HU-18). Claves JSON en inglés."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from velocista.domain.config.entities import RobotConfig


class ConfigSaved(BaseModel):
    """Modo y color de línea guardados; null cuando aún no se ha fijado alguno."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    mode: Literal["test", "competition"] | None
    line: Literal["black", "white"] | None
    updated_at: AwareDatetime | None

    @classmethod
    def from_entity(cls, config: RobotConfig) -> ConfigSaved:
        return cls(mode=config.mode, line=config.line, updated_at=config.updated_at)


class ModeChange(BaseModel):
    """`mode` es Any a propósito: un valor inválido se rechaza con invalid_command."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"mode": "test"}})
    mode: Any = Field(default=None, examples=["test", "competition"])


class LineChange(BaseModel):
    """`color` es Any a propósito (ver ModeChange)."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"color": "black"}})
    color: Any = Field(default=None, examples=["black", "white"])


class CommandAccepted(BaseModel):
    """La API aceptó y envió el comando; el ack del robot llega por /ws/console."""

    model_config = ConfigDict(extra="forbid")
    seq: int
    message: str = "Enviado. La confirmación del robot llega a la consola como ack."
