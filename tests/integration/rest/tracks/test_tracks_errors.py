"""Tracks API: the two 422 shapes (parsing list vs domain object) and field validation."""

import pytest

from support.track_fixtures import track_payload

TRACKS = "/api/tracks"


def locs(response):
    return [tuple(error["loc"]) for error in response.json()["detail"]]


class TestParsingErrorsUseTheFastApiList:
    def test_error_when_field_out_of_bounds_lists_loc_type_and_msg(self, client):
        body = track_payload()
        body["points"][3]["radius"] = 250
        response = client.post(TRACKS, json=body)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, list)
        error = detail[0]
        assert {"type", "loc", "msg", "input"} <= set(error)
        assert error["loc"] == ["body", "points", 3, "radius"]
        assert error["type"] == "less_than_equal"
        assert error["input"] == 250

    def test_error_lists_every_failing_field_not_only_the_first(self, client):
        body = track_payload(length_cm=0, name="")
        del body["board"]
        found = locs(client.post(TRACKS, json=body))
        assert {("body", "length_cm"), ("body", "name"), ("body", "board")} <= set(found)

    def test_error_when_unknown_field_is_extra_forbidden(self, client):
        response = client.post(TRACKS, json=track_payload(extra="x"))
        assert response.json()["detail"][0]["type"] == "extra_forbidden"
        assert response.json()["detail"][0]["loc"] == ["body", "extra"]

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("name", ""),
            ("name", "x" * 81),
            ("length_cm", 0),
            ("length_cm", 100000.5),
            ("closed", "maybe"),
        ],
    )
    def test_error_when_top_level_field_invalid(self, client, field, value):
        response = client.post(TRACKS, json=track_payload(**{field: value}))
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)

    @pytest.mark.parametrize(
        "board", [{"width_cm": 49, "height_cm": 250}, {"width_cm": 300, "height_cm": 2001}]
    )
    def test_error_when_board_out_of_range(self, client, board):
        response = client.post(TRACKS, json=track_payload(board=board))
        assert response.status_code == 422
        assert locs(response)[0][:2] == ("body", "board")

    @pytest.mark.parametrize(
        "point",
        [
            {"x": 10001, "y": 0, "radius": 0, "gap": False},
            {"x": 0, "y": -10001, "radius": 0, "gap": False},
            {"x": 0, "y": 0, "radius": -1, "gap": False},
        ],
    )
    def test_error_when_point_out_of_range(self, client, point):
        body = track_payload()
        body["points"][0] = point
        assert client.post(TRACKS, json=body).status_code == 422

    def test_error_when_points_count_out_of_range(self, client):
        too_few = track_payload(points=[{"x": 1, "y": 1}], closed=False)
        too_many = track_payload(points=[{"x": 1, "y": 1}] * 501)
        assert client.post(TRACKS, json=too_few).status_code == 422
        assert client.post(TRACKS, json=too_many).status_code == 422

    @pytest.mark.parametrize(
        "zone",
        [
            {"x": 0, "y": 0, "width": 0, "height": 5},
            {"x": 0, "y": 0, "width": 5, "height": 2001},
            {"x": 0, "y": 0, "width": 5, "height": 5, "name": "z" * 81},
        ],
    )
    def test_error_when_zone_invalid(self, client, zone):
        assert client.post(TRACKS, json=track_payload(zones=[zone])).status_code == 422

    def test_error_when_zones_over_the_limit(self, client):
        zones = [{"x": 0, "y": 0, "width": 1, "height": 1}] * 101
        assert client.post(TRACKS, json=track_payload(zones=zones)).status_code == 422

    @pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
    def test_error_when_number_is_not_finite(self, client, literal):
        raw = (
            '{"name":"n","board":{"width_cm":300,"height_cm":250},"closed":false,'
            '"points":[{"x":1,"y":1},{"x":2,"y":2}],"length_cm":' + literal + "}"
        )
        response = client.post(TRACKS, content=raw, headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)

    def test_error_when_start_edge_is_not_an_integer(self, client):
        response = client.post(TRACKS, json=track_payload(start={"edge": 1.5, "t": 0.5}))
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)

    def test_error_when_start_t_out_of_range(self, client):
        assert (
            client.post(TRACKS, json=track_payload(start={"edge": 0, "t": 1.5})).status_code == 422
        )


class TestDomainErrorsUseTheBusinessObject:
    @pytest.mark.parametrize(
        ("overrides", "reason"),
        [
            (
                {"closed": True, "points": [{"x": 1, "y": 1}, {"x": 2, "y": 2}]},
                "track_closed_needs_three_points",
            ),
            ({"start": {"edge": 4, "t": 0.5}}, "track_start_invalid"),
            (
                {"closed": False, "start": {"edge": 3, "t": 0.5}},
                "track_start_invalid",
            ),
        ],
    )
    def test_error_when_domain_rule_fails_returns_reason_object(self, client, overrides, reason):
        response = client.post(TRACKS, json=track_payload(**overrides))
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, dict)
        assert set(detail) == {"reason", "detail"}
        assert detail["reason"] == reason

    def test_start_edge_is_valid_up_to_points_minus_one_when_closed(self, client):
        assert client.post(TRACKS, json=track_payload(start={"edge": 3, "t": 1})).status_code == 201

    def test_start_edge_is_valid_up_to_points_minus_two_when_open(self, client):
        body = track_payload(closed=False, start={"edge": 2, "t": 0})
        assert client.post(TRACKS, json=body).status_code == 201

    def test_unknown_profile_on_post_returns_422_track_profile_unknown(self, client):
        response = client.post(TRACKS, json=track_payload(profile_id="nope"))
        assert response.status_code == 422
        assert response.json() == {
            "detail": {"reason": "track_profile_unknown", "detail": "Profile does not exist"}
        }

    def test_unknown_profile_on_put_returns_422_track_profile_unknown(self, client):
        created = client.post(TRACKS, json=track_payload()).json()
        response = client.put(f"{TRACKS}/{created['id']}", json=track_payload(profile_id="nope"))
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "track_profile_unknown"

    def test_existing_profile_is_accepted(self, client):
        response = client.post(TRACKS, json=track_payload(profile_id="club"))
        assert response.status_code == 201
        assert response.json()["profile_id"] == "club"

    def test_put_when_missing_and_invalid_answers_404_first(self, client):
        response = client.put(f"{TRACKS}/999999", json=track_payload(profile_id="nope"))
        assert response.status_code == 404


class TestPerimeterAndAreaErrors:
    @pytest.mark.parametrize("field", ["perimeter_cm", "area_cm2"])
    def test_open_track_with_a_metric_returns_the_domain_object(self, client, field):
        body = track_payload(closed=False, start={"edge": 0, "t": 0.5}, **{field: 10.0})
        response = client.post(TRACKS, json=body)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, dict)
        assert detail["reason"] == "track_metrics_invalid"

    def test_area_over_four_times_the_board_returns_the_domain_object(self, client):
        response = client.post(TRACKS, json=track_payload(area_cm2=300000.5))
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "track_metrics_invalid"

    def test_area_at_four_times_the_board_is_accepted(self, client):
        assert client.post(TRACKS, json=track_payload(area_cm2=300000)).status_code == 201

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("perimeter_cm", -1),
            ("perimeter_cm", 400000.5),
            ("area_cm2", -1),
            ("perimeter_cm", "wide"),
        ],
    )
    def test_out_of_bounds_metric_returns_the_parsing_list(self, client, field, value):
        response = client.post(TRACKS, json=track_payload(**{field: value}))
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)
        assert locs(response)[0] == ("body", field)

    @pytest.mark.parametrize("literal", ["NaN", "Infinity"])
    def test_not_finite_metric_returns_422_list_not_500(self, client, literal):
        raw = (
            '{"name":"n","board":{"width_cm":300,"height_cm":250},"closed":true,'
            '"points":[{"x":1,"y":1},{"x":2,"y":2},{"x":3,"y":1}],"length_cm":10,"area_cm2":'
            + literal
            + "}"
        )
        response = client.post(TRACKS, content=raw, headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)

    def test_update_with_invalid_metrics_is_rejected_and_keeps_the_old_values(self, client):
        track = client.post(TRACKS, json=track_payload(perimeter_cm=700.5)).json()
        response = client.put(
            f"{TRACKS}/{track['id']}",
            json=track_payload(closed=False, start={"edge": 0, "t": 0.5}, perimeter_cm=5.0),
        )
        assert response.status_code == 422
        assert client.get(f"{TRACKS}/{track['id']}").json()["perimeter_cm"] == 700.5
