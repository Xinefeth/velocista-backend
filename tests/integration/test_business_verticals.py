"""Prueba vertical real de PostgreSQL aislada en una transaccion."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from velocista.infrastructure.config.settings import settings
from velocista.infrastructure.persistence.db import Base, engine, get_session
from velocista.infrastructure.persistence.models.builder import RobotModel, VersionModel
from velocista.infrastructure.persistence.models.optimization import ControllerModel
from velocista.infrastructure.persistence.models.rules import ProfileModel
from velocista.interface.rest.errors import register_error_handlers
from velocista.interface.rest.optimization.router import router as optimization_router
from velocista.interface.rest.rules.router import router as rules_router
from velocista.interface.rest.runs.router import router as runs_router


def test_profiles_setups_runs_postgres(monkeypatch):
    app = FastAPI()
    register_error_handlers(app)
    for router in (rules_router, optimization_router, runs_router):
        app.include_router(router)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            schema = "business_" + uuid4().hex
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            Base.metadata.create_all(connection)
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                session.add(
                    RobotModel(
                        id="integration",
                        name="Integration Racer",
                        short_code="INT",
                        type="racer",
                        firmware="1",
                    )
                )
                session.flush()
                version = VersionModel(
                    robot_id="integration",
                    ordinal=1,
                    date=datetime.now(UTC),
                    note="Initial",
                    status="current",
                )
                session.add(version)
                session.flush()
                session.get(RobotModel, "integration").current_version_id = version.id
                session.add(
                    ControllerModel(
                        id="pid",
                        name="PID",
                        short_name="PID",
                        description="PID",
                        parameters=[{"key": "kp", "min": 0, "max": 10}],
                        presets={"Base": {"kp": 1.0}},
                    )
                )
                session.add(
                    ProfileModel(
                        id="club", competition="Club", label="Club", category="Racer", rules={}
                    )
                )
                version_id = version.id
                session.commit()

            def override():
                with Session(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session

            app.dependency_overrides[get_session] = override
            with TestClient(app) as client:
                assert client.get("/api/profiles").json()[0]["id"] == "club"
                assert client.get("/api/profiles/missing").status_code == 404
                assert client.get("/api/controllers").json()[0]["id"] == "pid"
                create = {
                    "version_id": version_id,
                    "name": "Track",
                    "controller_id": "pid",
                    "parameters": {"kp": 2},
                }
                invalid = client.post(
                    "/api/robots/integration/setups", json={**create, "parameters": {"kp": 11}}
                )
                assert invalid.status_code == 422, invalid.text
                invalid = client.post("/api/robots/other/setups", json=create)
                assert invalid.status_code == 404, invalid.text
                setup = client.post("/api/robots/integration/setups", json=create)
                assert setup.status_code == 201, setup.text
                assert setup.json()["parameters"] == {"kp": 2.0}
                assert client.get("/api/robots/integration/setups").json()["total"] == 1
                simulated = client.post("/api/runs/simulated?robot_id=integration")
                assert simulated.status_code == 201, simulated.text
                run = simulated.json()
                assert run["source"] == "sim"
                laps = client.get(f"/api/runs/{run['id']}/laps").json()["items"]
                assert 3 <= len(laps) <= 8
                for lap in laps:
                    assert abs(sum(lap["sectors_s"]) - lap["duration_s"]) < 0.00001
                    assert len(lap["segments"]) == 4
                completed = [lap for lap in laps if lap["finished"]]
                expected = min(
                    (round(lap["time_s"] + 2 * lap["accumulated_error"], 3) for lap in completed),
                    default=120,
                )
                assert run["j"] == expected
                assert client.get("/api/runs?robot_id=other").json()["total"] == 0
                assert client.get("/api/runs?controller_id=pid").json()["total"] == 1
                note = client.patch(f"/api/runs/{run['id']}", json={"note": "Track note"})
                assert note.json()["note"] == "Track note"
                assert client.delete(f"/api/setups/{setup.json()['id']}").status_code == 204
                assert client.get(f"/api/runs/{run['id']}").json()["parameters"] == {"kp": 1.0}
                assert client.post("/api/runs/simulated?robot_id=missing").status_code == 404
                monkeypatch.setattr(
                    settings, "simulation_service_token", "test-simulation-service-token"
                )
                ingested = {
                    "external_run_id": "simulator-run-001",
                    "robot_id": "integration",
                    "version_id": version_id,
                    "setup_id": setup.json()["id"],
                    "profile_id": "club",
                    "started_at": datetime.now(UTC).isoformat(),
                    "finished_at": datetime.now(UTC).isoformat(),
                    "mode": "test",
                    "line": "black",
                    "battery_compensation": True,
                    "turbine_power_pct": 0,
                    "laps": [
                        {
                            "number": 1,
                            "time_s": 10.0,
                            "duration_s": 10.0,
                            "internal_time_ms": 10000,
                            "accumulated_error": 0.5,
                            "lines_lost": 1,
                            "battery_v": 7.4,
                            "finished": True,
                            "time_source": "telemetry",
                            "sectors_s": [4.0, 6.0],
                            "segments": [
                                {
                                    "type": "straight",
                                    "duration_s": 10.0,
                                    "angle_degrees": 0,
                                    "accumulated_error": 0.5,
                                }
                            ],
                        }
                    ],
                }
                assert client.post("/api/runs/ingest", json=ingested).status_code == 401
                service_headers = {"Authorization": "Bearer test-simulation-service-token"}
                received = client.post("/api/runs/ingest", json=ingested, headers=service_headers)
                assert received.status_code == 201, received.text
                ingested_run = received.json()
                assert ingested_run["source"] == "sim" and ingested_run["j"] == 11.0
                replay = client.post("/api/runs/ingest", json=ingested, headers=service_headers)
                assert replay.status_code == 200 and replay.headers["idempotent-replay"] == "true"
                assert replay.json()["id"] == ingested_run["id"]
                changed = {**ingested, "laps": [{**ingested["laps"][0], "time_s": 11.0}]}
                assert (
                    client.post(
                        "/api/runs/ingest", json=changed, headers=service_headers
                    ).status_code
                    == 409
                )
                # Corrida real: manifiesto, dos vueltas y cronometro antes/despues del resumen.
                from types import SimpleNamespace

                from sqlalchemy import select

                from velocista.infrastructure.ingestion.recorder import RunRecorder
                from velocista.infrastructure.persistence.models.runs import LapModel, RunModel

                controller = SimpleNamespace(parameters=[SimpleNamespace(name="kp", value=3.0)])
                manifest = SimpleNamespace(
                    controller=lambda name: controller,
                    firmware="2.0",
                    battery_compensation=True,
                    model_dump=lambda **kwargs: {"firmware": "2.0", "active_controller": "pid"},
                )
                status = {
                    "state": "running",
                    "controller": "pid",
                    "mode": "test",
                    "line": "black",
                    "channels": {"battery_v": 7.8},
                }
                payload = {
                    "lap_id": 1,
                    "internal_time_ms": 10000,
                    "accumulated_error": 0.4,
                    "lost_lines": 0,
                    "battery_v": 7.8,
                }
                with Session(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    recorder = RunRecorder(session)
                    assert recorder.status("integration", status, manifest)
                    assert recorder.status("integration", status, manifest)
                    assert recorder.crossing(
                        "integration", {"crossing_number": 2, "lap_time_ms": 9500}
                    )
                    assert recorder.lap("integration", payload)
                    assert recorder.lap("integration", payload)
                    assert recorder.lap(
                        "integration", {**payload, "lap_id": 2, "internal_time_ms": 11000}
                    )
                    assert recorder.crossing(
                        "integration", {"crossing_number": 3, "lap_time_ms": 10500}
                    )
                    assert recorder.status("integration", {**status, "state": "stopped"}, manifest)
                    session.commit()
                    real_run = session.scalar(select(RunModel).where(RunModel.source == "robot"))
                    assert real_run.closed_at is not None
                    assert real_run.context_snapshot["parameters"] == {"kp": 3.0}
                    assert real_run.context_snapshot["firmware"] == "2.0"
                    real_id = real_run.id
                    measured = session.scalars(
                        select(LapModel).where(LapModel.run_id == real_id).order_by(LapModel.number)
                    ).all()
                    assert len(measured) == 2
                    assert [lap.time_s for lap in measured] == [9.5, 10.5]
                    assert all(lap.time_source == "finish" for lap in measured)
                real = client.get(f"/api/runs/{real_id}").json()
                assert real["time_source"] == "finish"
                assert real["j"] == 10.3
                assert client.get("/api/runs?source=robot").json()["total"] == 1
        finally:
            app.dependency_overrides.clear()
            transaction.rollback()
