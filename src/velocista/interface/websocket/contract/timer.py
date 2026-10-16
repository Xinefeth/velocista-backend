"""Mensajes entre el cronómetro de meta y la API."""

from typing import Literal

from pydantic import Field, field_validator

from velocista.interface.websocket.contract.base import NAME_PATTERN, Strict, same_major_version


class Hello(Strict):
    id: str = Field(pattern=NAME_PATTERN)
    firmware: str = Field(max_length=20)
    contract: str = Field(pattern=r"^\d+\.\d+$")
    debounce_ms: int = Field(ge=0)

    _version = field_validator("contract")(same_major_version)


class Crossing(Strict):
    crossing_number: int = Field(ge=1, description="Correlativo de cortes desde el último rearm")
    lap_time_ms: int | None = Field(
        ge=0,
        description="Elapsed timer clock since the previous crossing; null for the start",
    )
    timestamp_us: int = Field(ge=0, description="Instante del crossing en microsegundos")


class TimerStatus(Strict):
    gate: Literal["ok", "blocked", "no_signal"]
    rssi_dbm: int = Field(ge=-120, le=0)
    pending: int = Field(ge=0, description="Cortes guardados sin ack")


class Rearm(Strict):
    """API -> cronómetro: el próximo crossing es una salida nueva."""
