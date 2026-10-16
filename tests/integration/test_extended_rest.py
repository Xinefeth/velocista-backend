"""Additional integration checks; every test rolls back an isolated PostgreSQL schema."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from velocista.infrastructure.persistence import models  # noqa: F401
from velocista.infrastructure.persistence.db import Base, engine, get_session
from velocista.infrastructure.persistence.models.builder import SlotModel
from velocista.infrastructure.persistence.models.catalog import ComponentTypeModel
from velocista.main import create_app


@pytest.fixture
def api():
    app = create_app()
    with engine.connect() as connection:
        outer = connection.begin()
        name = f"qa_{uuid4().hex}"
        try:
            connection.execute(text(f'CREATE SCHEMA "{name}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{name}"'))
            Base.metadata.create_all(connection)

            def session_dependency():
                with Session(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session

            app.dependency_overrides[get_session] = session_dependency
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                session.add(
                    ComponentTypeModel(
                        id="mcu", name="MCU", color="#123456", fields=[], capabilities=[]
                    )
                )
                session.commit()
            with TestClient(app, raise_server_exceptions=False) as client:
                yield client, connection
        finally:
            app.dependency_overrides.clear()
            outer.rollback()


def robot(client, short_code="QA"):
    response = client.post(
        "/api/robots",
        json={
            "name": "QA Racer",
            "short_code": short_code,
            "type": "racer",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_version_lifecycle_snapshots_and_inventory(api):
    client, connection = api
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
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
        session.commit()
    rid = robot(client)
    component = client.post(
        "/api/components",
        json={
            "type_id": "mcu",
            "name": "Original",
            "price": 10,
            "mass_g": 5,
            "specs": {},
            "stock": 2,
        },
    )
    assert component.status_code == 201, component.text
    cid = component.json()["id"]
    data = {
        "base_version_id": None,
        "note": "QA",
        "status": "current",
        "parts": {"mcu": {"component_id": cid, "quantity": 1}},
    }
    first = client.post(f"/api/robots/{rid}/versions", json=data)
    assert first.status_code == 201, first.text
    version = first.json()
    vid = version["id"]
    assert client.get(f"/api/robots/{rid}/versions/{vid}").json() == version
    assert client.get("/api/robots").json()["items"][0]["current_version_id"] == vid
    inventory = client.get("/api/inventory").json()["items"][0]
    assert inventory["in_robots"] == 1
    assert inventory["available"] == 1
    assert client.patch(f"/api/components/{cid}", json={"name": "Changed"}).status_code == 200
    snapshot = client.get(f"/api/robots/{rid}/versions/{vid}").json()["parts"]["mcu"]
    assert snapshot["component_snapshot"]["name"] == "Original"
    stale = client.post(f"/api/robots/{rid}/versions", json=data)
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["reason"] == "version_stale"
    data["base_version_id"] = vid
    second = client.post(f"/api/robots/{rid}/versions", json=data)
    assert second.status_code == 201, second.text
    versions = client.get(f"/api/robots/{rid}/versions").json()["items"]
    assert [v["status"] for v in versions] == ["previous", "current"]
    other = robot(client, "OTHER")
    assert client.get(f"/api/robots/{other}/versions/{vid}").status_code == 404


def test_missing_slots_rejects_version_creation(api):
    client, _ = api
    rid = robot(client)
    result = client.post(
        f"/api/robots/{rid}/versions",
        json={
            "base_version_id": None,
            "note": "QA",
            "status": "draft",
            "parts": {},
        },
    )
    assert result.status_code == 422, result.text
    assert result.json()["detail"]["reason"] == "no_slots"


def test_frontend_version_payload_is_rejected(api):
    client, _ = api
    rid = robot(client)
    result = client.post(
        f"/api/robots/{rid}/versions",
        json={
            "version_base_id": None,
            "note": "QA",
            "status": "draft",
            "parts": {},
        },
    )
    assert result.status_code == 422, result.text
    errors = result.json()["detail"]
    assert any(e["loc"][-1] == "base_version_id" and e["type"] == "missing" for e in errors)
    assert any(e["loc"][-1] == "version_base_id" and e["type"] == "extra_forbidden" for e in errors)


def test_duplicate_short_code_and_archive(api):
    client, _ = api
    rid = robot(client)
    duplicate = client.post(
        "/api/robots",
        json={
            "name": "Duplicate",
            "short_code": "QA",
            "type": "racer",
        },
    )
    assert duplicate.status_code == 409, duplicate.text
    assert client.delete(f"/api/robots/{rid}").status_code == 204
    assert client.get("/api/robots").json()["total"] == 0
    assert client.patch(f"/api/robots/{rid}", json={"name": "Invalid"}).status_code == 409


@pytest.mark.parametrize("path,field", [("mode", "mode"), ("line", "color")])
@pytest.mark.parametrize("value", ["invalid", None, 42, {}, []])
def test_invalid_commands_return_validation_instead_of_server_error(api, path, field, value):
    client, _ = api
    rid = robot(client)
    response = client.post(f"/api/robots/{rid}/mode-line/{path}", json={field: value})
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["reason"] == "invalid_command"


@pytest.mark.parametrize("path,body", [("mode", {"mode": "test"}), ("line", {"color": "black"})])
def test_valid_commands_require_manifest(api, path, body):
    client, _ = api
    rid = robot(client)
    response = client.post(f"/api/robots/{rid}/mode-line/{path}", json=body)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["reason"] == "no_manifest"
