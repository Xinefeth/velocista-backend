"""Entidades del contexto `measurements`. Sin frameworks. Distancias en metros, tiempos en ms."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

METHODS = ("steps", "gps", "car")  # cómo se estima la distancia
SOURCES = ("phone", "simulator", "robot")  # de dónde vienen las lecturas
MOUNTS = ("hand", "robot")  # celular en la mano o encima del carro
READING_KINDS = ("motion", "gps", "corner")
STATUSES = ("recording", "finished")
CALIBRATION_KINDS = ("gyro_bias", "step_length", "car_speed")
CALIBRATION_ORIGINS = ("manual", "model")
ENVIRONMENTS = ("open", "buildings", "trees", "indoor")


@dataclass(frozen=True)
class XY:
    x: float
    y: float


@dataclass(frozen=True)
class Reading:
    """Una lectura del celular.

    - `motion`: giroscopio (`gyro_z_dps`, giro alrededor del eje perpendicular a la pantalla, °/s,
      positivo = antihorario visto desde arriba), acelerómetro con gravedad (`accel`, m/s²),
      `step` si el celular ya detectó un paso, `pwm` del motor si va sobre el carro.
    - `gps`: `lat`, `lon` en grados y `accuracy_m` (la precisión que informa el celular).
    - `corner`: la persona tocó "Marcar esquina".
    """

    seq: int
    t_ms: int
    kind: str
    gyro_z_dps: float | None = None
    accel: tuple[float, float, float] | None = None
    step: bool = False
    pwm: float | None = None
    lat: float | None = None
    lon: float | None = None
    accuracy_m: float | None = None


@dataclass(frozen=True)
class Calibration:
    """Parámetros con los que se calcula una medición (copia fija al crearla)."""

    gyro_bias_dps: float = 0.0
    step_length_m: float | None = None
    speed_k: float | None = None  # v = k·PWM + c (carro sin encoders)
    speed_c: float = 0.0
    step_threshold_ms2: float = 1.2  # pico sobre la gravedad para contar un paso
    step_min_interval_ms: int = 300
    gyro_calibrated: bool = False


@dataclass(frozen=True)
class Reference:
    """Plano de referencia: `points` en metros como se dibujaron; real = points × scale_n."""

    points: tuple[XY, ...]
    scale_n: float = 1.0
    name: str = ""

    def real_points(self) -> tuple[XY, ...]:
        return tuple(XY(p.x * self.scale_n, p.y * self.scale_n) for p in self.points)


@dataclass(frozen=True)
class Result:
    """Resultado de una medición. Las métricas `raw_*` son antes de corregir."""

    method: str
    reading_count: int
    step_count: int
    distance_m: float  # largo del recorrido caminado
    closure_error_m: float  # distancia entre el punto final y el inicial (sin corregir)
    closure_error_pct: float  # closure_error_m / distance_m · 100
    heading_drift_deg: float | None  # giro sobrante frente a ±360° (solo odometría)
    raw_perimeter_m: float
    raw_area_m2: float
    perimeter_m: float  # tras corregir giro y cierre (y escala si hay lado con cinta)
    area_m2: float
    scale_factor: float | None
    corners: int
    concave: bool
    self_crossing: bool
    quality: str  # green | yellow | red, según closure_error_pct
    reference_perimeter_m: float | None = None
    reference_area_m2: float | None = None
    perimeter_error_pct: float | None = None
    area_error_pct: float | None = None
    min_gps_size_m: float | None = None
    # Giro acumulado de toda la caminata (°, positivo a la izquierda). None por GPS y en filas
    # guardadas antes de HU-30 (el resultado es JSON: no hay migración).
    turn_total_deg: float | None = None
    warnings: tuple[str, ...] = ()
    raw_path: tuple[XY, ...] = ()
    corrected_path: tuple[XY, ...] = ()
    polygon: tuple[XY, ...] = ()  # vértices usados para perímetro y área


@dataclass(frozen=True)
class Measurement:
    method: str
    source: str
    mount: str
    place_name: str
    device_id: str
    closed: bool = True
    reference: Reference | None = None
    tape_side_m: float | None = None
    calibration: Calibration = field(default_factory=Calibration)
    status: str = "recording"
    reading_count: int = 0
    result: Result | None = None
    id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True)
class CalibrationRecord:
    """Una calibración guardada de un celular. La más reciente de cada tipo es la que se usa."""

    device_id: str
    kind: str  # gyro_bias | step_length | car_speed
    params: dict
    origin: str = "manual"  # manual | model (SP-07)
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class GpsTrial:
    """Prueba de error del GPS (SP-06): dos puntos con distancia real medida con cinta."""

    device_id: str
    place_name: str
    environment: str
    real_distance_m: float
    start_fixes: tuple  # tuple[Fix, ...]
    end_fixes: tuple
    result: dict | None = None
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ModelRun:
    """Una corrida del modelo de precisión (SP-07) sobre mediciones repetidas."""

    device_id: str
    measurement_ids: tuple[int, ...]
    result: dict
    applied: bool = False
    id: int | None = None
    created_at: datetime | None = None
