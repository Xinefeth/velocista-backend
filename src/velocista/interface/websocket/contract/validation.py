"""Validaciones que dependen del manifest del robot conectado."""

from typing import Literal

from velocista.interface.websocket.contract.manifest import Channel, Manifest
from velocista.interface.websocket.contract.robot import ChannelValue, Setup


def _valid_value(channel: Channel, value: ChannelValue) -> str | None:
    base = channel.type.removesuffix("[]")
    valores = value if isinstance(value, list) else [value]
    if channel.type.endswith("[]"):
        if not isinstance(value, list):
            return f"{channel.name}: se esperaba un arreglo"
        if len(value) != channel.length:
            return f"{channel.name}: se esperaban {channel.length} valores y llegaron {len(value)}"
    elif isinstance(value, list):
        return f"{channel.name}: no se esperaba un arreglo"
    for v in valores:
        if base == "bool":
            if not isinstance(v, bool):
                return f"{channel.name}: se esperaba bool"
            continue
        if isinstance(v, bool) or not isinstance(v, int | float):
            return f"{channel.name}: se esperaba un número"
        if base == "int" and not float(v).is_integer():
            return f"{channel.name}: se esperaba un entero"
        if (
            channel.min is not None
            and v < channel.min
            or channel.max is not None
            and v > channel.max
        ):
            return f"{channel.name}: {v} fuera de [{channel.min}, {channel.max}]"
    return None


def check_channels(
    manifest: Manifest, group: Literal["status", "signals"], channels: dict[str, ChannelValue]
) -> list[str]:
    """Devuelve avisos; nunca descarta la muestra completa por un channel raro."""
    avisos = []
    for name, value in channels.items():
        channel = manifest.channel(name)
        if channel is None:
            avisos.append(f"{name}: channel no declarado en el manifest")
        elif channel.group != group:
            avisos.append(f"{name}: pertenece al group {channel.group}, no a {group}")
        elif problema := _valid_value(channel, value):
            avisos.append(problema)
    return avisos


def check_setup(manifest: Manifest, setup: Setup) -> tuple[str, str] | None:
    """Devuelve (reason, detail) si el setup no cabe en lo que el robot declaró."""
    controller = manifest.controller(setup.controller)
    if controller is None:
        return "controller_unavailable", f"el robot no tiene el controller {setup.controller}"
    for name, value in setup.parameters.items():
        p = controller.parameter(name)
        if p is None:
            return "unknown_parameter", f"{setup.controller} no tiene el parámetro {name}"
        if not p.min <= value <= p.max:
            return "out_of_range", f"{name}={value} fuera de [{p.min}, {p.max}]"
        if p.type == "int" and not float(value).is_integer():
            return "out_of_range", f"{name} debe ser entero"
    return None


def check_complete_setup(manifest: Manifest, setup: Setup) -> tuple[str, str] | None:
    """Como check_setup, pero además exige que estén todos los parámetros del controller.

    Lo usa el flujo de aplicar (HU-17, Req 4.5): al cargar un setup o preset en el robot, un
    parámetro que el controller declara pero el setup omite se rechaza con unknown_parameter.
    No modifica check_setup para no alterar el envío de commands crudos (POST .../commands).
    """
    controller = manifest.controller(setup.controller)
    if controller is None:
        return "controller_unavailable", f"el robot no tiene el controller {setup.controller}"
    for p in controller.parameters:  # completitud (Req 4.5)
        if p.name not in setup.parameters:
            return "unknown_parameter", f"falta el parámetro {p.name} del controller"
    return check_setup(manifest, setup)  # existencia/rango/type por value (Req 4.3/4.4)
