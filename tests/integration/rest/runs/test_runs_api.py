"""Runs: simulated runs, history, laps, annotation and idempotent ingestion."""

import pytest


class TestSimulatedRuns:
    def test_simulate_when_robot_ready_creates_closed_sim_run(self, client, build):
        robot_id, _, _ = build.robot_ready()
        response = client.post(f"/api/runs/simulated?robot_id={robot_id}")
        assert response.status_code == 201, response.text
        run = response.json()
        assert (
            run["source"] == "sim" and run["robot_id"] == robot_id and run["controller_id"] == "pid"
        )

    def test_simulate_when_robot_missing_returns_404(self, client):
        assert client.post("/api/runs/simulated?robot_id=ghost").status_code == 404

    def test_simulate_when_robot_has_no_version_returns_409(self, client, build):
        robot_id = build.robot()
        response = client.post(f"/api/runs/simulated?robot_id={robot_id}")
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "no_current_version"

    def test_simulated_run_j_matches_scoring_formula(self, client, build):
        robot_id, _, _ = build.robot_ready()
        run = client.post(f"/api/runs/simulated?robot_id={robot_id}").json()
        laps = client.get(f"/api/runs/{run['id']}/laps").json()["items"]
        finished = [
            round(lap["time_s"] + 2 * lap["accumulated_error"], 3)
            for lap in laps
            if lap["finished"]
        ]
        assert run["j"] == (min(finished) if finished else 120.0)

    def test_laps_when_listed_have_consistent_sectors_and_segments(self, client, build):
        robot_id, _, _ = build.robot_ready()
        run = client.post(f"/api/runs/simulated?robot_id={robot_id}").json()
        laps = client.get(f"/api/runs/{run['id']}/laps").json()
        assert 3 <= laps["total"] <= 8
        for lap in laps["items"]:
            assert abs(sum(lap["sectors_s"]) - lap["duration_s"]) < 1e-5
            assert len(lap["segments"]) == 4


class TestRunHistory:
    def test_list_runs_when_empty_returns_zero_total(self, client):
        assert client.get("/api/runs").json() == {"items": [], "total": 0, "limit": 50, "offset": 0}

    def test_list_runs_when_filtered_by_robot_controller_and_source(self, client, build):
        robot_id, _, _ = build.robot_ready()
        client.post(f"/api/runs/simulated?robot_id={robot_id}")
        assert client.get(f"/api/runs?robot_id={robot_id}").json()["total"] == 1
        assert client.get("/api/runs?robot_id=other").json()["total"] == 0
        assert client.get("/api/runs?controller_id=pid").json()["total"] == 1
        assert client.get("/api/runs?controller_id=none").json()["total"] == 0
        assert client.get("/api/runs?source=robot").json()["total"] == 0
        assert client.get("/api/runs?source=sim").json()["total"] == 1

    @pytest.mark.parametrize("query", ["source=hybrid", "limit=0", "limit=201", "offset=-1"])
    def test_list_runs_when_query_invalid_returns_422(self, client, query):
        assert client.get(f"/api/runs?{query}").status_code == 422

    def test_get_run_when_missing_returns_404(self, client):
        assert client.get("/api/runs/999999").status_code == 404

    def test_annotate_run_when_note_valid_persists_it(self, client, build):
        robot_id, _, _ = build.robot_ready()
        run = client.post(f"/api/runs/simulated?robot_id={robot_id}").json()
        response = client.patch(f"/api/runs/{run['id']}", json={"note": "Good run"})
        assert response.status_code == 200 and response.json()["note"] == "Good run"
        assert client.get(f"/api/runs/{run['id']}").json()["note"] == "Good run"

    def test_annotate_run_when_note_too_long_returns_422(self, client, build):
        robot_id, _, _ = build.robot_ready()
        run = client.post(f"/api/runs/simulated?robot_id={robot_id}").json()
        assert client.patch(f"/api/runs/{run['id']}", json={"note": "x" * 1001}).status_code == 422

    def test_run_keeps_parameters_snapshot_after_setup_is_archived(self, client, build):
        robot_id, _, setup_id = build.robot_ready()
        run = client.post(f"/api/runs/simulated?robot_id={robot_id}").json()
        client.delete(f"/api/setups/{setup_id}")
        assert client.get(f"/api/runs/{run['id']}").json()["parameters"] == run["parameters"]


class TestSimulationIngestion:
    def test_ingest_when_token_missing_returns_401(self, client, build, service_headers):
        robot_id, version_id, setup_id = build.robot_ready()
        payload = build.ingestion_payload(robot_id, version_id, setup_id)
        assert client.post("/api/runs/ingest", json=payload).status_code == 401

    def test_ingest_when_token_wrong_returns_401(self, client, build, service_headers):
        robot_id, version_id, setup_id = build.robot_ready()
        payload = build.ingestion_payload(robot_id, version_id, setup_id)
        response = client.post(
            "/api/runs/ingest", json=payload, headers={"Authorization": "Bearer wrong"}
        )
        assert response.status_code == 401

    def test_ingest_when_service_not_configured_returns_503(self, client, build, monkeypatch):
        from velocista.infrastructure.config.settings import settings

        monkeypatch.setattr(settings, "simulation_service_token", "")
        robot_id, version_id, setup_id = build.robot_ready()
        payload = build.ingestion_payload(robot_id, version_id, setup_id)
        assert client.post("/api/runs/ingest", json=payload).status_code == 503

    def test_ingest_when_valid_creates_run_with_expected_j(self, client, build, service_headers):
        robot_id, version_id, setup_id = build.robot_ready()
        payload = build.ingestion_payload(robot_id, version_id, setup_id)
        response = client.post("/api/runs/ingest", json=payload, headers=service_headers)
        assert response.status_code == 201, response.text
        assert response.json()["source"] == "sim" and response.json()["j"] == 11.0

    def test_ingest_when_same_payload_is_replayed_returns_200_same_run(
        self, client, build, service_headers
    ):
        robot_id, version_id, setup_id = build.robot_ready()
        payload = build.ingestion_payload(robot_id, version_id, setup_id)
        first = client.post("/api/runs/ingest", json=payload, headers=service_headers)
        replay = client.post("/api/runs/ingest", json=payload, headers=service_headers)
        assert replay.status_code == 200
        assert replay.headers["idempotent-replay"] == "true"
        assert replay.json()["id"] == first.json()["id"]
        assert client.get("/api/runs").json()["total"] == 1

    def test_ingest_when_same_id_with_different_data_returns_409(
        self, client, build, service_headers
    ):
        robot_id, version_id, setup_id = build.robot_ready()
        payload = build.ingestion_payload(robot_id, version_id, setup_id)
        client.post("/api/runs/ingest", json=payload, headers=service_headers)
        payload["laps"][0]["time_s"] = 11.0
        response = client.post("/api/runs/ingest", json=payload, headers=service_headers)
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "external_run_conflict"

    @pytest.mark.parametrize(
        "override,status,reason",
        [
            ({"robot_id": "ghost"}, 404, "robot_not_found"),
            ({"version_id": 999999}, 404, "version_not_found"),
            ({"setup_id": 999999}, 404, "setup_not_found"),
            ({"profile_id": "ghost"}, 404, "profile_not_found"),
        ],
    )
    def test_ingest_when_reference_missing_returns_404(
        self, client, build, service_headers, override, status, reason
    ):
        robot_id, version_id, setup_id = build.robot_ready()
        payload = build.ingestion_payload(robot_id, version_id, setup_id)
        payload.update(override)
        response = client.post("/api/runs/ingest", json=payload, headers=service_headers)
        assert response.status_code == status
        assert response.json()["detail"]["reason"] == reason

    def test_ingest_when_robot_archived_returns_409(self, client, build, service_headers):
        robot_id, version_id, setup_id = build.robot_ready()
        client.delete(f"/api/robots/{robot_id}")
        payload = build.ingestion_payload(robot_id, version_id, setup_id)
        response = client.post("/api/runs/ingest", json=payload, headers=service_headers)
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "robot_archived"

    @pytest.mark.parametrize("missing", ["external_run_id", "laps", "robot_id", "profile_id"])
    def test_ingest_when_required_field_missing_returns_422(
        self, client, build, service_headers, missing
    ):
        robot_id, version_id, setup_id = build.robot_ready()
        payload = build.ingestion_payload(robot_id, version_id, setup_id)
        payload.pop(missing)
        response = client.post("/api/runs/ingest", json=payload, headers=service_headers)
        assert response.status_code == 422
