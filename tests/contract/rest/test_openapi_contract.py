"""Contract: the public REST API (OpenAPI) keeps the agreed shape.

These tests protect the frontend: renaming a path, operationId, JSON field or removing
an endpoint breaks them before it breaks the console.
"""

import re

import pytest

from velocista.main import create_app

EXPECTED_ENDPOINTS = {
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/me"),
    ("GET", "/api/health"),
    ("GET", "/api/component-types"),
    ("GET", "/api/slots"),
    ("GET", "/api/components"),
    ("POST", "/api/components"),
    ("GET", "/api/components/{component_id}"),
    ("PATCH", "/api/components/{component_id}"),
    ("DELETE", "/api/components/{component_id}"),
    ("GET", "/api/inventory"),
    ("PUT", "/api/inventory/{component_id}"),
    ("GET", "/api/robots"),
    ("POST", "/api/robots"),
    ("GET", "/api/robots/{robot_id}"),
    ("PATCH", "/api/robots/{robot_id}"),
    ("DELETE", "/api/robots/{robot_id}"),
    ("GET", "/api/robots/{robot_id}/versions"),
    ("POST", "/api/robots/{robot_id}/versions"),
    ("GET", "/api/robots/{robot_id}/versions/{version_id}"),
    ("GET", "/api/controllers"),
    ("GET", "/api/robots/{robot_id}/setups"),
    ("POST", "/api/robots/{robot_id}/setups"),
    ("GET", "/api/setups/{setup_id}"),
    ("DELETE", "/api/setups/{setup_id}"),
    ("POST", "/api/robots/{robot_id}/setups/{setup_id}/apply"),
    ("POST", "/api/robots/{robot_id}/presets/apply"),
    ("GET", "/api/profiles"),
    ("GET", "/api/profiles/{profile_id}"),
    ("GET", "/api/runs"),
    ("POST", "/api/runs/ingest"),
    ("POST", "/api/runs/simulated"),
    ("GET", "/api/runs/{run_id}"),
    ("PATCH", "/api/runs/{run_id}"),
    ("GET", "/api/runs/{run_id}/laps"),
    ("GET", "/api/events"),
    ("POST", "/api/events"),
    ("GET", "/api/robots/{robot_id}/mode-line"),
    ("POST", "/api/robots/{robot_id}/mode-line/mode"),
    ("POST", "/api/robots/{robot_id}/mode-line/line"),
    ("GET", "/api/tracks"),
    ("POST", "/api/tracks"),
    ("GET", "/api/tracks/{track_id}"),
    ("PUT", "/api/tracks/{track_id}"),
    ("DELETE", "/api/tracks/{track_id}"),
    ("GET", "/api/tracks/{track_id}/export"),
    ("GET", "/api/devices/robot/manifest"),
    ("POST", "/api/devices/{device}/commands"),
}


@pytest.fixture(scope="module")
def spec():
    return create_app().openapi()


@pytest.fixture(scope="module")
def operations(spec):
    return [
        (method.upper(), path, op)
        for path, item in spec["paths"].items()
        for method, op in item.items()
    ]


def test_every_agreed_endpoint_exists(operations):
    published = {(method, path) for method, path, _ in operations}
    assert EXPECTED_ENDPOINTS - published == set()


def test_all_routes_live_under_api_prefix(operations):
    assert all(path.startswith("/api/") for _, path, _ in operations)


def test_operation_ids_are_unique_camel_case_english(operations):
    ids = [op["operationId"] for _, _, op in operations]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z][A-Za-z]+", i) for i in ids), ids


def test_json_property_names_are_snake_case(spec):
    names = {
        name
        for schema in spec["components"]["schemas"].values()
        for name in schema.get("properties", {})
    }
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", n) for n in names), sorted(names)


def test_paginated_lists_share_the_same_envelope(spec):
    pages = {n: s for n, s in spec["components"]["schemas"].items() if n.endswith("Page")}
    assert pages
    for name, schema in pages.items():
        assert set(schema["properties"]) == {"items", "total", "limit", "offset"}, name


def test_robot_schema_exposes_agreed_fields(spec):
    fields = set(spec["components"]["schemas"]["RobotOut"]["properties"])
    assert fields == {
        "id",
        "name",
        "short_code",
        "type",
        "firmware",
        "current_version_id",
        "archived",
    }


def test_run_schema_exposes_traceability_and_score(spec):
    fields = set(spec["components"]["schemas"]["RunOut"]["properties"])
    assert {
        "robot_id",
        "version_id",
        "setup_id",
        "controller_id",
        "parameters",
        "j",
        "source",
    } <= fields


def test_ingestion_requires_idempotency_key_and_laps(spec):
    required = set(spec["components"]["schemas"]["RunIngestion"]["required"])
    assert {"external_run_id", "laps", "robot_id", "version_id", "setup_id"} <= required


def test_track_schema_exposes_agreed_fields(spec):
    schemas = spec["components"]["schemas"]
    assert set(schemas["TrackOut"]["properties"]) == {
        "id",
        "name",
        "board",
        "closed",
        "points",
        "zones",
        "start",
        "profile_id",
        "length_cm",
        "created_at",
        "updated_at",
    }
    assert set(schemas["BoardIO"]["properties"]) == {"width_cm", "height_cm"}
    assert set(schemas["PointIO"]["properties"]) == {"x", "y", "radius", "gap"}
    assert set(schemas["ZoneIO"]["properties"]) == {"x", "y", "width", "height", "name"}
    assert set(schemas["StartIO"]["properties"]) == {"edge", "t"}
    assert {"name", "board", "closed", "points", "length_cm"} <= set(schemas["TrackIn"]["required"])


def test_track_operations_use_the_agreed_ids(operations):
    ids = {op["operationId"] for method, path, op in operations if path.startswith("/api/tracks")}
    assert ids == {
        "listTracks",
        "getTrack",
        "createTrack",
        "updateTrack",
        "deleteTrack",
        "exportTrack",
    }
