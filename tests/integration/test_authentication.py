"""Verify deploy authentication without touching user data."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from velocista.infrastructure.config.settings import Settings, settings
from velocista.infrastructure.security import decode_access_token
from velocista.main import create_app


@pytest.fixture
def protected_client(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "secret_key", "qa-signing-secret-" * 4)
    monkeypatch.setattr(settings, "admin_username", "qa-admin")
    monkeypatch.setattr(settings, "admin_password", "qa-password-only-for-tests")
    with TestClient(create_app()) as client:
        yield client


def test_auth_login_expiry_and_protected_requests(protected_client):
    client = protected_client
    assert client.get("/api/robots").status_code == 401
    assert client.get("/api/health").status_code == 200
    bad = client.post("/api/auth/login", json={"username": "qa-admin", "password": "wrong"})
    assert bad.status_code == 401
    response = client.post(
        "/api/auth/login",
        json={
            "username": "qa-admin",
            "password": "qa-password-only-for-tests",
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert decode_access_token(token)["sub"] == "qa-admin"
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).json() == {"username": "qa-admin"}
    assert client.get("/api/robots", headers=headers).status_code == 200
    assert (
        client.get("/api/robots", headers={"Authorization": f"Bearer {token}x"}).status_code == 401
    )
    expired = jwt.encode(
        {
            "sub": "qa-admin",
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "iss": "velocista-backend",
            "aud": "velocista-console",
        },
        settings.secret_key,
        algorithm="HS256",
    )
    assert (
        client.get("/api/robots", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    )


def test_cors_headers_survive_unauthorized_response(protected_client):
    response = protected_client.get("/api/robots", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    preflight = protected_client.options(
        "/api/robots",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert preflight.status_code == 200


def test_production_requires_secrets():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production")
    Settings(
        _env_file=None,
        app_env="production",
        auth_required=True,
        secret_key="qa-only-signing-secret-" * 3,
        admin_password="qa-only-password",
        device_token_robot="qa-only-robot-token-" * 3,
        device_token_timer="qa-only-timer-token-" * 3,
        simulation_service_token="qa-only-simulation-service-token-" * 2,
        cors_origins="https://console.example.com",
    )
