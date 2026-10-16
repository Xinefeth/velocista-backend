"""Envoltorio de todo mensaje WebSocket (contrato 2.0), ya en inglés.

Lo que el backend reenvía a /ws/console SIEMPRE usa estas claves en inglés, gracias a la
anti-corruption layer (ver translation.py). El firmware puede seguir en español.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Envelope(BaseModel):
    """Envelope normalizado hacia la consola."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    type: str = Field(pattern=r"^[a-z_]{2,24}$")  # tipo (ya traducido)
    seq: int = Field(ge=0, le=2**32 - 1)
    ts: int = Field(ge=0, description="Milisegundos desde el arranque del emisor")
    sender: str  # origen: robot | timer | api
    data: dict[str, Any] = Field(default_factory=dict)  # datos (ya traducidos)
    received_ms: int = Field(ge=0, description="Reloj del backend al recibir")
