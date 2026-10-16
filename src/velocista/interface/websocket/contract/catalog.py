"""Catálogo de mensajes: quién envía cada type, qué model valida sus data y si requiere ack."""

from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from velocista.interface.websocket.contract import robot as r
from velocista.interface.websocket.contract import timer as c
from velocista.interface.websocket.contract.manifest import Manifest


@dataclass(frozen=True)
class Definition:
    model: type[BaseModel]
    requires_ack: bool
    frequency: str


# (emisor, type) -> definición. Emisor "api" = mensajes que la API envía al dispositivo.
CATALOG: dict[tuple[str, str], Definition] = {
    # Robot -> API
    ("robot", "manifest"): Definition(Manifest, True, "al conectar, primer message"),
    ("robot", "status"): Definition(r.Status, False, "status_hz (1 Hz)"),
    ("robot", "signals"): Definition(r.Signals, False, "signals_hz (20 Hz) mientras corre"),
    ("robot", "lap"): Definition(r.Lap, True, "tras lap_close"),
    ("robot", "sync"): Definition(r.Sync, True, "al reconectar, si hay laps guardadas"),
    ("robot", "event"): Definition(r.Event, True, "cuando ocurre"),
    ("robot", "ack"): Definition(r.Ack, False, "por cada command"),
    # API -> Robot
    ("api->robot", "calibrate"): Definition(r.NoData, True, "a pedido"),
    ("api->robot", "start"): Definition(r.NoData, True, "a pedido"),
    ("api->robot", "stop"): Definition(r.NoData, True, "a pedido"),
    ("api->robot", "setup"): Definition(r.Setup, True, "a pedido"),
    ("api->robot", "mode"): Definition(r.Mode, True, "a pedido"),
    ("api->robot", "line"): Definition(r.Line, True, "a pedido"),
    ("api->robot", "lap_close"): Definition(r.LapClose, True, "al recibir un crossing"),
    ("api->robot", "ack"): Definition(r.Ack, False, "por cada message que lo requiere"),
    # Cronómetro -> API
    ("timer", "hello"): Definition(c.Hello, True, "al conectar"),
    ("timer", "crossing"): Definition(c.Crossing, True, "cada step por la meta"),
    ("timer", "status"): Definition(c.TimerStatus, False, "cada 5 s"),
    ("timer", "ack"): Definition(r.Ack, False, "por cada command"),
    # API -> Cronómetro
    ("api->timer", "rearm"): Definition(c.Rearm, True, "a pedido"),
    ("api->timer", "ack"): Definition(r.Ack, False, "por cada message que lo requiere"),
}


class InvalidMessage(ValueError):
    pass


def validate_data(emisor: str, type: str, data: dict) -> BaseModel:
    definicion = CATALOG.get((emisor, type))
    if definicion is None:
        raise InvalidMessage(f"type desconocido para {emisor}: {type}")
    try:
        return definicion.model.model_validate(data)
    except ValidationError as e:
        raise InvalidMessage(str(e)) from e


def requires_ack(emisor: str, type: str) -> bool:
    definicion = CATALOG.get((emisor, type))
    return bool(definicion and definicion.requires_ack)
