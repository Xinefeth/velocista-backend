"""Contract: every business error follows {"detail": {"reason", "detail"}}."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from velocista.domain.shared.errors import Conflict, Forbidden, NotFound, Validation
from velocista.interface.rest.errors import register_error_handlers


@pytest.fixture
def client():
    app = FastAPI()
    register_error_handlers(app)

    for (
        name,
        error,
    ) in {
        "not-found": NotFound("x_not_found", "missing"),
        "conflict": Conflict("x_conflict", "clash"),
        "validation": Validation("x_invalid", "bad"),
        "forbidden": Forbidden("x_forbidden", "no"),
    }.items():

        def make(e):
            def endpoint():
                raise e

            return endpoint

        app.add_api_route(f"/{name}", make(error))

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internals")

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "path,status,reason",
    [
        ("not-found", 404, "x_not_found"),
        ("conflict", 409, "x_conflict"),
        ("validation", 422, "x_invalid"),
        ("forbidden", 403, "x_forbidden"),
    ],
)
def test_business_errors_use_standard_body(client, path, status, reason):
    response = client.get(f"/{path}")
    assert response.status_code == status
    assert response.json() == {
        "detail": {"reason": reason, "detail": response.json()["detail"]["detail"]}
    }


def test_unhandled_error_returns_500_without_internal_details(client):
    response = client.get("/boom")
    assert response.status_code == 500
    assert response.json()["detail"]["reason"] == "internal_error"
    assert "secret" not in response.text
