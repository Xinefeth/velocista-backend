"""Shared database + HTTP fixtures (imported by the conftest of integration/rest and e2e/flows).

Every test runs against a REAL PostgreSQL inside an isolated schema that is rolled back at
the end, so tests never leave data behind and can run in any order.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from velocista.infrastructure.config.settings import settings
from velocista.infrastructure.persistence import models  # noqa: F401
from velocista.infrastructure.persistence.db import Base, engine, get_session
from velocista.infrastructure.persistence.models.builder import SlotModel
from velocista.infrastructure.persistence.models.catalog import ComponentTypeModel
from velocista.infrastructure.persistence.models.optimization import ControllerModel
from velocista.infrastructure.persistence.models.rules import ProfileModel
from velocista.main import create_app

SERVICE_TOKEN = "test-simulation-service-token"


@pytest.fixture
def db():
    """Connection bound to an isolated schema (rolled back after the test)."""
    with engine.connect() as connection:
        outer = connection.begin()
        schema = f"qa_{uuid4().hex}"
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            Base.metadata.create_all(connection)
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                session.add(
                    ComponentTypeModel(
                        id="mcu", name="MCU", color="#123456", fields=[], capabilities=[]
                    )
                )
                session.flush()
                session.add(
                    SlotModel(
                        id="mcu",
                        type_id="mcu",
                        name="MCU",
                        required=True,
                        quantity_editable=False,
                        rules_dependent=False,
                    )
                )
                session.add(
                    ControllerModel(
                        id="pid",
                        name="PID",
                        short_name="PID",
                        description="PID controller",
                        parameters=[
                            {"key": "kp", "min": 0, "max": 10},
                            {"key": "kd", "min": 0, "max": 5},
                        ],
                        presets={"Base": {"kp": 1.0, "kd": 0.5}},
                    )
                )
                session.add(
                    ProfileModel(
                        id="club", competition="Club", label="Club", category="Racer", rules={}
                    )
                )
                session.commit()
            yield connection
        finally:
            outer.rollback()


@pytest.fixture
def client(db):
    """HTTP client of the full app wired to the isolated schema."""
    app = create_app()

    def session_dependency():
        with Session(
            bind=db, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session

    app.dependency_overrides[get_session] = session_dependency
    with TestClient(app, raise_server_exceptions=False) as http:
        yield http
    app.dependency_overrides.clear()


@pytest.fixture
def service_headers(monkeypatch):
    """Authorization header of the simulation service (token configured for the test)."""
    monkeypatch.setattr(settings, "simulation_service_token", SERVICE_TOKEN)
    return {"Authorization": f"Bearer {SERVICE_TOKEN}"}


# ---- builders (small helpers so each test reads as given / when / then) ----------------


class Builders:
    """Creates API data through the public endpoints (never through the database)."""

    def __init__(self, client):
        self.client = client

    def robot(self, short_code="QA", name="QA Racer"):
        response = self.client.post(
            "/api/robots", json={"name": name, "short_code": short_code, "type": "racer"}
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def component(self, name="Main MCU", stock=2, type_id="mcu"):
        response = self.client.post(
            "/api/components",
            json={
                "type_id": type_id,
                "name": name,
                "price": 10,
                "mass_g": 5,
                "specs": {},
                "stock": stock,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def version(self, robot_id, component_id, base_version_id=None, status="current"):
        response = self.client.post(
            f"/api/robots/{robot_id}/versions",
            json={
                "base_version_id": base_version_id,
                "note": "QA",
                "status": status,
                "parts": {"mcu": {"component_id": component_id, "quantity": 1}},
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def setup(self, robot_id, version_id, name="Track", parameters=None):
        response = self.client.post(
            f"/api/robots/{robot_id}/setups",
            json={
                "version_id": version_id,
                "name": name,
                "controller_id": "pid",
                "parameters": parameters or {"kp": 2, "kd": 1},
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def robot_ready(self):
        """Robot with a current version and one setup: (robot_id, version_id, setup_id)."""
        robot_id = self.robot()
        version_id = self.version(robot_id, self.component())
        return robot_id, version_id, self.setup(robot_id, version_id)

    @staticmethod
    def ingestion_payload(robot_id, version_id, setup_id, external_run_id="sim-001", **overrides):
        now = datetime.now(UTC).isoformat()
        payload = {
            "external_run_id": external_run_id,
            "robot_id": robot_id,
            "version_id": version_id,
            "setup_id": setup_id,
            "profile_id": "club",
            "started_at": now,
            "finished_at": now,
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
                    "lost_lines": 1,
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
        payload.update(overrides)
        return payload


@pytest.fixture
def build(client):
    return Builders(client)
