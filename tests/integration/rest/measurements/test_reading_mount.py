"""EN-32 criterion 2: every reading the API returns says if the phone was in hand or on the robot.

`mount` belongs to the measurement; the phone does not send it per reading and the API adds it on
output. Real PostgreSQL in an isolated schema.
"""

MEASUREMENTS = "/api/measurements"
CALIBRATIONS = "/api/calibrations"
PHONE = "phone-mount-1"


def start(client, **overrides):
    body = {"method": "gps", "place_name": "Mount", "device_id": PHONE, **overrides}
    response = client.post(MEASUREMENTS, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def send(client, measurement_id, extra=None):
    readings = [
        {
            "seq": 0,
            "t_ms": 1_730_592_000_000,
            "kind": "motion",
            "gyro_z_dps": 0.4,
            "accel": [0.1, 0.2, 9.8],
            **(extra or {}),
        },
        {
            "seq": 1,
            "t_ms": 1_730_592_000_020,
            "kind": "gps",
            "lat": -8.1116,
            "lon": -79.0287,
            "accuracy_m": 4.8,
        },
        {"seq": 2, "t_ms": 1_730_592_003_000, "kind": "corner"},
    ]
    response = client.post(f"{MEASUREMENTS}/{measurement_id}/readings", json={"readings": readings})
    assert response.status_code == 200, response.text


def read(client, measurement_id):
    response = client.get(f"{MEASUREMENTS}/{measurement_id}/readings")
    assert response.status_code == 200, response.text
    return response.json()


def test_readings_of_a_hand_measurement_say_hand(client):
    m = start(client, mount="hand")
    send(client, m["id"])
    readings = read(client, m["id"])
    assert len(readings) == 3
    assert {r["mount"] for r in readings} == {"hand"}


def test_mount_defaults_to_hand_when_the_measurement_does_not_say(client):
    m = start(client)
    send(client, m["id"])
    assert {r["mount"] for r in read(client, m["id"])} == {"hand"}


def test_readings_of_a_robot_measurement_say_robot(client):
    m = start(client, mount="robot")
    send(client, m["id"])
    readings = read(client, m["id"])
    assert {r["mount"] for r in readings} == {"robot"}
    assert [r["kind"] for r in readings] == ["motion", "gps", "corner"]


def test_a_car_measurement_always_returns_robot(client):
    trials = [{"pwm": p, "distance_m": (0.01 * p + 0.05) * 4, "seconds": 4} for p in (30, 60)]
    assert client.post(f"{CALIBRATIONS}/{PHONE}/car", json={"trials": trials}).status_code == 201
    m = start(client, method="car", mount="robot")
    send(client, m["id"])
    assert {r["mount"] for r in read(client, m["id"])} == {"robot"}


def test_each_measurement_returns_its_own_mount(client):
    hand = start(client, mount="hand")
    robot = start(client, mount="robot")
    send(client, hand["id"])
    send(client, robot["id"])
    assert {r["mount"] for r in read(client, hand["id"])} == {"hand"}
    assert {r["mount"] for r in read(client, robot["id"])} == {"robot"}


def test_a_mount_sent_inside_a_reading_is_ignored(client):
    m = start(client, mount="hand")
    send(client, m["id"], extra={"mount": "robot"})
    assert {r["mount"] for r in read(client, m["id"])} == {"hand"}


def test_the_rest_of_the_reading_is_unchanged(client):
    m = start(client, mount="robot")
    send(client, m["id"])
    first = read(client, m["id"])[0]
    assert first["seq"] == 0 and first["gyro_z_dps"] == 0.4 and first["accel"] == [0.1, 0.2, 9.8]
    assert set(first) == {
        "seq",
        "t_ms",
        "kind",
        "gyro_z_dps",
        "accel",
        "step",
        "pwm",
        "lat",
        "lon",
        "accuracy_m",
        "mount",
    }


def test_unknown_measurement_is_still_404(client):
    assert client.get(f"{MEASUREMENTS}/999999/readings").status_code == 404
