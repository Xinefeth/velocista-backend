"""End-to-end: the full operator journey through the public REST API (real PostgreSQL).

Flow: register component -> create robot -> build version -> create setup -> simulate run
-> review history and laps -> annotate -> archive setup -> inventory reflects usage.
"""


def test_operator_journey_from_component_to_run_history(client):
    # given a component in inventory
    component = client.post(
        "/api/components",
        json={"type_id": "mcu", "name": "ESP32", "price": 30, "mass_g": 9, "specs": {}, "stock": 2},
    ).json()

    # and a robot with its first (current) version using that component
    robot = client.post(
        "/api/robots", json={"name": "Flash", "short_code": "FL", "type": "racer"}
    ).json()
    version = client.post(
        f"/api/robots/{robot['id']}/versions",
        json={
            "base_version_id": None,
            "note": "v1",
            "status": "current",
            "parts": {"mcu": {"component_id": component["id"], "quantity": 1}},
        },
    ).json()
    assert client.get(f"/api/robots/{robot['id']}").json()["current_version_id"] == version["id"]

    # when the team creates a PID setup for that version
    setup = client.post(
        f"/api/robots/{robot['id']}/setups",
        json={
            "version_id": version["id"],
            "name": "Track A",
            "controller_id": "pid",
            "parameters": {"kp": 2, "kd": 1},
        },
    ).json()

    # and runs a simulation
    run = client.post(f"/api/runs/simulated?robot_id={robot['id']}").json()

    # then the run is traceable to robot, version and controller
    assert (run["robot_id"], run["version_id"], run["source"]) == (
        robot["id"],
        version["id"],
        "sim",
    )
    assert client.get("/api/runs").json()["total"] == 1
    laps = client.get(f"/api/runs/{run['id']}/laps").json()
    assert laps["total"] >= 3

    # and the engineer can annotate the run
    assert client.patch(f"/api/runs/{run['id']}", json={"note": "Slow in curves"}).json()["note"]

    # and archiving the setup does not rewrite history
    client.delete(f"/api/setups/{setup['id']}")
    assert client.get(f"/api/runs/{run['id']}").json()["parameters"] == run["parameters"]

    # and the inventory reflects the component used by the robot
    item = next(
        i
        for i in client.get("/api/inventory").json()["items"]
        if i["component_id"] == component["id"]
    )
    assert item["in_robots"] == 1 and item["available"] == 1


def test_simulation_service_journey_ingests_run_idempotently(client, build, service_headers):
    robot_id, version_id, setup_id = build.robot_ready()
    payload = build.ingestion_payload(robot_id, version_id, setup_id, external_run_id="sim-e2e")

    created = client.post("/api/runs/ingest", json=payload, headers=service_headers)
    replay = client.post("/api/runs/ingest", json=payload, headers=service_headers)

    assert (created.status_code, replay.status_code) == (201, 200)
    assert created.json()["id"] == replay.json()["id"]
    assert client.get(f"/api/runs?robot_id={robot_id}&source=sim").json()["total"] == 1
