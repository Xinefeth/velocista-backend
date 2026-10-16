"""PostgreSQL REST smoke, isolated in a rolled-back temporary schema."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from velocista.infrastructure.persistence import models  # noqa: F401
from velocista.infrastructure.persistence.db import Base, engine, get_session
from velocista.infrastructure.persistence.models.catalog import ComponentTypeModel
from velocista.main import create_app


def test_rest_postgres_smoke():
    app = create_app()
    schema = f"smoke_{uuid4().hex}"
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            Base.metadata.create_all(connection)
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                session.add(
                    ComponentTypeModel(
                        id="mcu",
                        name="Microcontroller",
                        color="#123456",
                        fields=[],
                        capabilities=[],
                    )
                )
                session.commit()

            def override_session():
                with Session(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session

            app.dependency_overrides[get_session] = override_session
            with TestClient(app) as client:
                health = client.get("/api/health")
                assert health.status_code == 200, health.text
                assert health.json()["database"] == "ok"
                assert client.get("/docs").status_code == 200
                spec = client.get("/openapi.json").json()
                assert {"/api/robots", "/api/components", "/api/runs", "/api/auth/login"} <= spec[
                    "paths"
                ].keys()
                component = client.post(
                    "/api/components",
                    json={
                        "type_id": "mcu",
                        "name": "Smoke MCU",
                        "price": 20,
                        "mass_g": 10,
                        "specs": {},
                        "stock": 4,
                    },
                )
                assert component.status_code == 201, component.text
                cid = component.json()["id"]
                assert client.get(f"/api/components/{cid}").json()["stock"] == 4
                assert client.get("/api/components", params={"q": "smoke"}).json()["total"] == 1
                updated = client.patch(f"/api/components/{cid}", json={"name": "Updated MCU"})
                assert updated.status_code == 200, updated.text
                inventory = client.put(f"/api/inventory/{cid}", json={"stock": 5, "revision": 1})
                assert inventory.status_code == 200, inventory.text
                assert inventory.json()["available"] == 5
                assert (
                    client.put(
                        f"/api/inventory/{cid}", json={"stock": 6, "revision": 1}
                    ).status_code
                    == 409
                )
                assert client.get("/api/inventory").json()["total"] == 1
                assert len(client.get("/api/component-types").json()) == 1
                robot = client.post(
                    "/api/robots",
                    json={
                        "name": "Smoke Racer",
                        "short_code": "SMOKE",
                        "type": "racer",
                    },
                )
                assert robot.status_code == 201, robot.text
                rid = robot.json()["id"]
                assert client.get(f"/api/robots/{rid}").status_code == 200
                assert client.get("/api/robots").json()["total"] == 1
                assert (
                    client.patch(f"/api/robots/{rid}", json={"name": "Updated Racer"}).status_code
                    == 200
                )
                assert client.get(f"/api/robots/{rid}/versions").status_code == 200
                assert client.get("/api/slots").status_code == 200
                config = client.get(f"/api/robots/{rid}/mode-line")
                assert config.status_code == 404, config.text
                event = client.post(
                    "/api/events",
                    json={
                        "system": "smoke",
                        "level": "info",
                        "message": "REST verified",
                    },
                )
                assert event.status_code == 201, event.text
                assert len(client.get("/api/events").json()) == 1
                assert client.delete(f"/api/components/{cid}").status_code == 204
                assert client.delete(f"/api/robots/{rid}").status_code == 204
        finally:
            app.dependency_overrides.clear()
            transaction.rollback()


if __name__ == "__main__":
    test_rest_postgres_smoke()
    print("REST + PostgreSQL smoke OK (temporary schema rolled back)")
