"""Polygons API: contour from sides and angles and figures by points (EN-42, HU-41, HU-43)."""

import pytest

SOLVE = "/api/polygons/solve"
POINTS = "/api/polygons/from-points"


def test_l_shape_with_missing_data_is_completed(client):
    response = client.post(
        SOLVE,
        json={"sides_m": [6, 2, 4, None, None, 8], "angles_deg": [90, 90, 90, None, 90, 90]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["area_m2"] == pytest.approx(24)
    assert body["perimeter_m"] == pytest.approx(28)
    assert body["angles_deg"][3] == pytest.approx(270)
    assert body["computed_sides"] == [3, 4]
    assert body["computed_angles"] == [3]
    assert body["concave"] is True and body["closes"] is True
    assert body["points"][0] == {"x": 0, "y": 0}


def test_figure_that_does_not_close_is_warned(client):
    response = client.post(SOLVE, json={"sides_m": [10, 6, 10, 7], "angles_deg": [90] * 4})
    assert response.status_code == 200
    assert response.json()["warnings"] == ["does_not_close"]


def test_underdetermined_figure_is_rejected(client):
    response = client.post(
        SOLVE, json={"sides_m": [10, None, None, None], "angles_deg": [90, 90, 90, 90]}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "polygon_underdetermined"


@pytest.mark.parametrize(
    "body",
    [
        {"sides_m": [1, 2], "angles_deg": [90, 90]},
        {"sides_m": [1, 1, 1], "angles_deg": [60, 60, 60], "extra": 1},
        {"sides_m": [1, "a", 1], "angles_deg": [60, 60, 60]},
        {"sides_m": [1, 1, 1]},
    ],
)
def test_bad_body_is_rejected(client, body):
    assert client.post(SOLVE, json=body).status_code == 422


def test_marked_points_give_area_and_angles(client):
    points = [{"x": x, "y": y} for x, y in [(0, 0), (6, 0), (6, 2), (2, 2), (2, 8), (0, 8)]]
    response = client.post(POINTS, json={"points": points})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["area_m2"] == pytest.approx(24)
    assert body["angles_deg"] == pytest.approx([90, 90, 90, 270, 90, 90])
    assert body["warnings"] == []


def test_crossing_points_are_warned(client):
    points = [{"x": x, "y": y} for x, y in [(0, 0), (4, 4), (4, 0), (0, 4)]]
    response = client.post(POINTS, json={"points": points})
    assert response.status_code == 200
    assert response.json()["warnings"] == ["self_crossing"]


def test_points_on_one_line_are_rejected(client):
    points = [{"x": i, "y": i} for i in range(3)]
    response = client.post(POINTS, json={"points": points})
    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "polygon_degenerate"
