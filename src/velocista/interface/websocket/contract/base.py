"""Sobre común y tipos básicos del contract."""

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

CONTRACT_VERSION = "2.0"


def same_major_version(version: str) -> str:
    """Valida que el dispositivo hable la misma versión mayor del contract."""
    if version.split(".")[0] != CONTRACT_VERSION.split(".")[0]:
        raise ValueError(f"contract {version} incompatible con {CONTRACT_VERSION}")
    return version


# Nombres de channels, parámetros y sensors: minúsculas, dígitos y guion bajo.
NAME_PATTERN = r"^[a-z][a-z0-9_]{0,31}$"

Sender = Literal["robot", "timer", "api"]


class Strict(BaseModel):
    """Rechaza campos no declarados: un error de tipeo en el firmware se detecta enseguida."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Envelope(Strict):
    """Envoltorio de todo message WebSocket."""

    type: str = Field(validation_alias=AliasChoices("type", "tipo"), pattern=r"^[a-z_]{2,24}$")
    seq: int = Field(
        ge=0, le=2**32 - 1, description="Correlativo del emisor; en ack repite el confirmado"
    )
    ts: int = Field(ge=0, description="Milisegundos desde el start_mode del emisor")
    data: dict[str, Any] = Field(
        default_factory=dict, validation_alias=AliasChoices("data", "datos")
    )
