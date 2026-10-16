"""Manifiesto: lo que el robot declara de sí mismo al conectarse.

Los channels tienen name. Agregar un sensor = declarar sus channels aquí;
la API, la base de data y la consola los usan sin cambiar el contract.
"""

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from velocista.interface.websocket.contract.base import NAME_PATTERN, Strict, same_major_version

ChannelType = Literal["float", "int", "bool", "float[]", "int[]"]

# Canales que la API necesita para calcular J y vigilar la batería.
REQUIRED_CHANNELS: dict[str, str] = {"error": "signals"}

ROBOT_COMMANDS = {"calibrate", "start", "stop", "setup", "mode", "line", "lap_close"}


class Channel(Strict):
    name: str = Field(pattern=NAME_PATTERN)
    description: str = Field(default="", max_length=120)
    type: ChannelType
    length: int | None = Field(default=None, ge=1, le=64, description="Solo para arreglos")
    unit: str = Field(default="", max_length=12)
    min: float | None = None
    max: float | None = None
    group: Literal["status", "signals"] = Field(
        description="status viaja a la frecuencia de status; signals, a la de señales"
    )

    @model_validator(mode="after")
    def _coherente(self) -> "Channel":
        es_arreglo = self.type.endswith("[]")
        if es_arreglo and self.length is None:
            raise ValueError(f"el channel {self.name} es un arreglo y necesita length")
        if not es_arreglo and self.length is not None:
            raise ValueError(f"el channel {self.name} no es arreglo y no lleva length")
        if self.type == "bool" and (self.min is not None or self.max is not None):
            raise ValueError(f"el channel {self.name} es bool y no lleva rango")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"el channel {self.name} tiene min mayor que max")
        return self


class Parameter(Strict):
    name: str = Field(pattern=NAME_PATTERN)
    label: str = Field(max_length=40)
    type: Literal["float", "int"]
    min: float
    max: float
    step: float | None = Field(default=None, gt=0)
    value: float = Field(description="Valor cargado ahora en el robot")
    unit: str = Field(default="", max_length=12)
    optimizable: bool = Field(default=True, description="Si Twiddle y la bayesiana pueden moverlo")

    @model_validator(mode="after")
    def _en_rango(self) -> "Parameter":
        if self.min >= self.max:
            raise ValueError(f"el parámetro {self.name} necesita min menor que max")
        if not self.min <= self.value <= self.max:
            raise ValueError(f"el value de {self.name} está fuera de su rango")
        if self.type == "int" and not all(
            float(v).is_integer() for v in (self.min, self.max, self.value)
        ):
            raise ValueError(f"el parámetro {self.name} es int y tiene valores decimales")
        return self


class Controller(Strict):
    name: str = Field(pattern=NAME_PATTERN)
    description: str = Field(default="", max_length=120)
    parameters: list[Parameter] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def _sin_repetidos(self) -> "Controller":
        nombres = [p.name for p in self.parameters]
        if len(nombres) != len(set(nombres)):
            raise ValueError(f"el controller {self.name} repite parámetros")
        return self

    def parameter(self, name: str) -> Parameter | None:
        return next((p for p in self.parameters if p.name == name), None)


class Sensor(Strict):
    name: str = Field(pattern=NAME_PATTERN)
    model: str = Field(max_length=40)
    channels: list[str] = Field(min_length=1, description="Canales que produce este sensor")
    details: dict[str, Any] = Field(default_factory=dict)


class Actuator(Strict):
    name: str = Field(pattern=NAME_PATTERN)
    type: Literal["motor_dc", "servo", "turbine", "led", "other"]
    model: str = Field(default="", max_length=40)
    channels: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class Frequencies(Strict):
    loop_hz: int = Field(ge=1, le=10000)
    status_hz: float = Field(gt=0, le=10)
    signals_hz: float = Field(gt=0, le=50)


class Manifest(Strict):
    contract: str = Field(pattern=r"^\d+\.\d+$")
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    robot_type: str = Field(pattern=NAME_PATTERN, description="robot, minisumo…")
    firmware: str = Field(max_length=20)
    sensors: list[Sensor]
    actuators: list[Actuator]
    channels: list[Channel] = Field(min_length=1, max_length=64)
    controllers: list[Controller] = Field(min_length=1)
    active_controller: str
    commands: list[str]
    frequencies: Frequencies
    start_mode: Literal["command", "start_module"]
    battery_compensation: bool

    _version = field_validator("contract")(same_major_version)

    @model_validator(mode="after")
    def _consistente(self) -> "Manifest":
        nombres = [c.name for c in self.channels]
        if len(nombres) != len(set(nombres)):
            raise ValueError("hay channels con el mismo name")
        grupos = {c.name: c.group for c in self.channels}
        for name, group in REQUIRED_CHANNELS.items():
            if grupos.get(name) != group:
                raise ValueError(f"falta el channel requerido {name} en el group {group}")
        if not any(grupos.get(name) == "status" for name in ("battery_v", "bateria_v")):
            raise ValueError("falta el channel requerido battery_v en el group status")
        for dispositivo in [*self.sensors, *self.actuators]:
            faltan = set(dispositivo.channels) - set(nombres)
            if faltan:
                raise ValueError(f"{dispositivo.name} usa channels no declarados: {sorted(faltan)}")
        if self.active_controller not in {c.name for c in self.controllers}:
            raise ValueError("active_controller no está entre los controllers declarados")
        desconocidos = set(self.commands) - ROBOT_COMMANDS
        if desconocidos:
            raise ValueError(f"commands desconocidos: {sorted(desconocidos)}")
        return self

    def channel(self, name: str) -> Channel | None:
        return next((c for c in self.channels if c.name == name), None)

    def controller(self, name: str) -> Controller | None:
        return next((c for c in self.controllers if c.name == name), None)
