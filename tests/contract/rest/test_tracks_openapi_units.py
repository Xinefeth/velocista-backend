"""Contract: the tracks OpenAPI states its units (centimetres) and the profile track rules units."""

import pytest

from velocista.main import create_app


@pytest.fixture(scope="module")
def spec():
    return create_app().openapi()


@pytest.fixture(scope="module")
def schemas(spec):
    return spec["components"]["schemas"]


def described(schema, field):
    return schema["properties"][field].get("description", "")


def test_length_and_board_fields_state_centimetres(schemas):
    assert "centimetres" in described(schemas["TrackOut"], "length_cm")
    assert "centimetres" in described(schemas["TrackIn"], "length_cm")
    assert "centimetres" in described(schemas["BoardIO"], "width_cm")
    assert "centimetres" in described(schemas["BoardIO"], "height_cm")


@pytest.mark.parametrize("field", ["x", "y", "radius"])
def test_point_fields_state_centimetres(schemas, field):
    assert "centimetres" in described(schemas["PointIO"], field)


@pytest.mark.parametrize("field", ["x", "y", "width", "height"])
def test_zone_fields_state_centimetres(schemas, field):
    assert "centimetres" in described(schemas["ZoneIO"], field)


def test_start_t_is_documented_as_a_fraction(schemas):
    assert "Fraction" in described(schemas["StartIO"], "t")


@pytest.mark.parametrize("operation", ["/api/tracks", "/api/tracks/{track_id}"])
def test_track_operations_mention_centimetres(spec, operation):
    for method, op in spec["paths"][operation].items():
        if method != "delete":  # borrar no maneja distancias
            assert "centimetres" in op["description"]


@pytest.mark.parametrize("path", ["/api/profiles", "/api/profiles/{profile_id}"])
def test_profile_description_states_track_rule_units(spec, path):
    description = spec["paths"][path]["get"]["description"]
    assert "centimetres" in description
    assert "degrees" in description
    assert "millimetres" in description
    assert "rules.track" in description


def test_list_profiles_names_every_length_rule(spec):
    description = spec["paths"]["/api/profiles"]["get"]["description"]
    for rule in (
        "radius_min",
        "separation_min",
        "margin",
        "zone_distance",
        "length_min",
        "length_max",
        "straight_min",
        "straight_max",
    ):
        assert rule in description


def test_track_operations_document_their_errors(spec):
    for path, method, codes in [
        ("/api/tracks", "get", {"401"}),
        ("/api/tracks", "post", {"401", "422"}),
        ("/api/tracks/{track_id}", "get", {"401", "404"}),
        ("/api/tracks/{track_id}", "put", {"401", "404", "422"}),
        ("/api/tracks/{track_id}", "delete", {"401", "404"}),
        ("/api/tracks/{track_id}/export", "get", {"401", "404"}),
    ]:
        documented = set(spec["paths"][path][method]["responses"])
        assert codes <= documented, (path, method)
