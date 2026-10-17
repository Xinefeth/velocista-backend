"""Pinned wire schemas plus capability-dependent validation. No network schema resolution."""

import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


@cache
def validators():
    schemas = {}
    resources = []
    root = Path(__file__).with_name("schemas")
    for path in root.rglob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schemas[path.relative_to(root).as_posix().removesuffix(".schema.json")] = schema
        resources.append((schema["$id"], Resource.from_contents(schema)))
    registry = Registry().with_resources(resources)
    return {key: Draft202012Validator(value, registry=registry) for key, value in schemas.items()}


def validate(message, hello=None, *, command=False):
    if not isinstance(message, dict):
        raise ValueError("Message must be an object")
    key = f"commands/{message.get('cmd')}" if command else f"messages/{message.get('type')}"
    validator = validators().get(key)
    if validator is None:
        raise ValueError("Unknown message or command")
    errors = list(validator.iter_errors(message))
    if errors:
        raise ValueError(errors[0].message[:200])
    # JSON does not admit NaN/Infinity, even inside extension fields.
    json.dumps(message, allow_nan=False)
    if command or hello is None:
        return message
    caps = hello["capabilities"]
    kind = message["type"]

    def require(condition, detail):
        if not condition:
            raise ValueError(detail)

    if kind == "telemetry":
        count = caps["line_sensors"]
        require(len(message["sensors"]) == count, "sensors_length")
        require(all(v < 2 ** caps["adc_bits"] for v in message["sensors"]), "sensor_range")
        require(message["line_position"] <= (count - 1) * 1000, "line_position_range")
        require(
            message["error"] == message["line_position"] - (count - 1) * 500, "error_consistency"
        )
        for field, expected in {
            "battery_v": caps["battery"]["voltage_sense"],
            "sim_truth": hello["source"] == "sim",
            "odometry": caps["encoders"] or caps["imu"],
            "lap": caps["lap_timing"] and message["running"],
            "run_id": message["running"],
        }.items():
            require((field in message) == expected, f"invalid_presence:{field}")
        if "odometry" in message:
            for field, expected in {
                "distance_m": caps["encoders"],
                "speed_mps": caps["encoders"],
                "heading_rad": caps["imu"],
            }.items():
                require((field in message["odometry"]) == expected, f"odometry:{field}")
    elif kind == "event":
        if message["event"] == "lap":
            require(caps["lap_timing"], "lap_without_timing")
        if message["event"] == "run_finished":
            summary = message["summary"]
            require((summary["laps"] is not None) == caps["lap_timing"], "summary_laps")
            if hello["source"] == "robot":
                require(summary["track_id"] is None, "track_id_robot_real")
    elif kind == "config" and hello["source"] == "robot":
        require(message["track_id"] is None, "track_id_robot_real")
    elif kind == "catalog" and hello["source"] == "robot":
        require(
            message["robots"] == [hello["robot"]["id"]] and not message["tracks"],
            "catalog_robot_real",
        )
    return message
