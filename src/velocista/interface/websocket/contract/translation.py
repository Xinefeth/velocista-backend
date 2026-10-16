"""Translate legacy device frames at the public English contract boundary."""

from typing import Any

FIELDS = {
    "tipo": "type",
    "datos": "data",
    "nombre": "name",
    "descripcion": "description",
    "longitud": "length",
    "unidad": "unit",
    "grupo": "group",
    "etiqueta": "label",
    "paso": "step",
    "valor": "value",
    "parametros": "parameters",
    "modelo": "model",
    "canales": "channels",
    "detalles": "details",
    "lazo_hz": "loop_hz",
    "estado_hz": "status_hz",
    "senales_hz": "signals_hz",
    "contrato": "contract",
    "tipo_robot": "robot_type",
    "sensores": "sensors",
    "actuadores": "actuators",
    "controladores": "controllers",
    "controlador_activo": "active_controller",
    "comandos": "commands",
    "frecuencias": "frequencies",
    "arranque": "start_mode",
    "compensa_bateria": "battery_compensation",
    "estado": "state",
    "calibrado": "calibrated",
    "modo": "mode",
    "linea": "line",
    "controlador": "controller",
    "id_vuelta": "lap_id",
    "tiempo_interno_ms": "internal_time_ms",
    "error_acumulado": "accumulated_error",
    "lineas_perdidas": "lost_lines",
    "vueltas": "laps",
    "codigo": "code",
    "nivel": "level",
    "mensaje": "message",
    "id_setup": "setup_id",
    "motivo": "reason",
    "detalle": "detail",
    "antirrebote_ms": "debounce_ms",
    "n_corte": "crossing_number",
    "tiempo_vuelta_ms": "lap_time_ms",
    "marca_us": "timestamp_us",
    "barrera": "gate",
    "pendientes": "pending",
}
VALUES = {
    "velocista": "robot",
    "cronometro": "timer",
    "manifiesto": "manifest",
    "senales": "signals",
    "vuelta": "lap",
    "cierre_vuelta": "lap_close",
    "evento": "event",
    "hola": "hello",
    "corte": "crossing",
    "rearmar": "rearm",
    "prueba": "test",
    "competencia": "competition",
    "negra": "black",
    "blanca": "white",
    "aviso": "warning",
    "comando": "command",
    "modulo_arranque": "start_module",
    "turbina": "turbine",
    "otro": "other",
    "bloqueada": "blocked",
    "sin_senal": "no_signal",
    "bloqueado_competencia": "competition_locked",
    "no_calibrado": "not_calibrated",
    "fuera_de_rango": "out_of_range",
    "parametro_desconocido": "unknown_parameter",
    "controlador_no_disponible": "controller_unavailable",
    "comando_desconocido": "unknown_command",
    "ocupado": "busy",
    "estado": "status",
    "modo": "mode",
    "linea": "line",
}
FIELDS["estado"] = "state"
FIELDS["bateria_v"] = "battery_v"
VALUES["estado"] = "status"
FIELDS["bateria_v"] = "battery_v"
VALUES["estado"] = "status"
REVERSE_FIELDS = {v: k for k, v in FIELDS.items()}
REVERSE_VALUES = {v: k for k, v in VALUES.items()}


def translate_type(value: str) -> str:
    return VALUES.get(value, value)


def translate_sender(value: str) -> str:
    return VALUES.get(value, value)


def translate_payload(data: dict[str, Any], *, reverse: bool = False) -> dict[str, Any]:
    fields = REVERSE_FIELDS if reverse else FIELDS
    values = REVERSE_VALUES if reverse else VALUES

    def visit(value, parent=""):
        if isinstance(value, dict):
            # Channel names and parameter names belong to the firmware, not the API.
            if parent in ("channels", "parameters", "details"):
                return value
            result = {}
            for key, item in value.items():
                normalized = FIELDS.get(key, key)
                result[fields.get(key, key)] = visit(item, normalized)
            return result
        if isinstance(value, list):
            return [visit(item, parent if not isinstance(item, dict) else "") for item in value]
        if isinstance(value, str):
            # IDs, prose and channel references are open vocabulary.
            if parent in (
                "type",
                "group",
                "mode",
                "line",
                "color",
                "level",
                "gate",
                "reason",
                "start_mode",
                "commands",
            ):
                return values.get(value, value)
        return value

    return visit(data)
