"""Mensajes entre el Velocista y la API."""

from typing import Any, Literal

from pydantic import AliasChoices, Field

from velocista.interface.websocket.contract.base import NAME_PATTERN, Strict

ChannelValue = float | int | bool | list[float] | list[int]

# ---------- Robot -> API ----------


class Status(Strict):
    """Cada 1/status_hz segundos (1 Hz por defecto)."""

    state: Literal["ready", "calibrating", "running", "stopped", "error"]
    calibrated: bool
    mode: Literal["test", "competition"]
    line: Literal["black", "white"]
    controller: str = Field(pattern=NAME_PATTERN)
    loop_hz: int = Field(ge=0, description="Frecuencia real medida del lazo de control")
    rssi_dbm: int = Field(ge=-120, le=0)
    channels: dict[str, ChannelValue] = Field(description="Canales del group status")


class Signals(Strict):
    """Cada 1/signals_hz segundos (20 Hz por defecto), solo mientras corre."""

    t_ms: int = Field(ge=0, description="Instante de la muestra en el reloj del robot")
    channels: dict[str, ChannelValue] = Field(description="Canales del group signals")


class Lap(Strict):
    """Resumen de una lap; respuesta a lap_close."""

    lap_id: int = Field(ge=1)
    internal_time_ms: int = Field(
        ge=0, description="Medido por el robot; el oficial es el del cronómetro"
    )
    accumulated_error: float = Field(ge=0, description="Integral del |error| en la lap (IAE)")
    lost_lines: int = Field(ge=0, validation_alias=AliasChoices("lost_lines", "lines_lost"))
    battery_v: float = Field(ge=0)


class Sync(Strict):
    """Vueltas guardadas mientras no había enlace; se envían al reconectar."""

    laps: list[Lap] = Field(min_length=1, max_length=50)


class Event(Strict):
    code: str = Field(
        pattern=NAME_PATTERN, description="Ver catálogo de eventos en la especificación"
    )
    level: Literal["info", "warning", "error"]
    message: str = Field(max_length=120)
    data: dict[str, Any] = Field(default_factory=dict)


# ---------- API -> Robot (commands) ----------


class NoData(Strict):
    """calibrate, start, stop."""


class Setup(Strict):
    controller: str = Field(pattern=NAME_PATTERN)
    parameters: dict[str, float] = Field(min_length=1)
    setup_id: int | None = Field(default=None, description="Id del setup guardado en la API")


class Mode(Strict):
    mode: Literal["test", "competition"]


class Line(Strict):
    color: Literal["black", "white"]


class LapClose(Strict):
    lap_id: int = Field(ge=1)


# ---------- Ambos sentidos ----------

RejectReason = Literal[
    "competition_locked",
    "not_calibrated",
    "out_of_range",
    "unknown_parameter",
    "controller_unavailable",
    "unknown_command",
    "busy",
]


class Ack(Strict):
    """Confirma el message cuyo seq viaja en el sobre. ok=false rechaza un command."""

    ok: bool = True
    reason: RejectReason | None = None
    detail: str | None = Field(default=None, max_length=120)
