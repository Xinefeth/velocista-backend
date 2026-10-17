"""Translate supported internal commands, without inventing device acknowledgements."""

from velocista.domain.shared.errors import Validation

from .contract import validate


def translate(kind, data):
    if kind == "setup":
        allowed = {"controller", "parameters", "setup_id"}
        if set(data) - allowed or not isinstance(data.get("parameters"), dict):
            raise Validation("invalid_command", "Expected PID setup parameters")
        parameters = data["parameters"]
        if set(parameters) - {"kp", "ki", "kd", "base_speed"}:
            raise Validation(
                "unsupported_parameter", "Only kp, ki, kd and base_speed are supported"
            )
        frame = {"cmd": "set_config", "controller": data.get("controller", "pid")}
        pid = {key: value for key, value in parameters.items() if key != "base_speed"}
        if pid:
            frame["params"] = pid
        if "base_speed" in parameters:
            frame["base_speed"] = parameters["base_speed"]
    elif kind in {"start", "stop", "set_config", "set_rate", "list"}:
        fields = {
            "start": set(),
            "stop": set(),
            "list": set(),
            "set_rate": {"hz"},
            "set_config": {"controller", "params", "base_speed"},
        }
        if set(data) - fields[kind]:
            raise Validation("invalid_command", "Unknown command fields")
        frame = {"cmd": kind, **data}
    else:
        raise Validation("unsupported_command", f"External source does not support {kind}")
    try:
        validate(frame, command=True)
    except ValueError as exc:
        raise Validation("invalid_command", str(exc)) from exc
    return frame


def confirms(command, message, run_id):
    kind = command["cmd"]
    if kind in {"start", "stop"}:
        event = "run_started" if kind == "start" else "run_finished"
        return (
            message["type"] == "event"
            and message["event"] == event
            and (kind == "start" or message["run_id"] == run_id)
        )
    if kind == "list":
        return message["type"] == "catalog"
    if message["type"] != "config":
        return False
    if kind == "set_rate":
        return message["rate_hz"] == command["hz"]
    return all(
        all(message["params"].get(k) == v for k, v in value.items())
        if key == "params"
        else message.get(key) == value
        for key, value in command.items()
        if key != "cmd"
    )
