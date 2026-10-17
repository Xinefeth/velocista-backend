"""Auth: login, token validation and route protection."""

import pytest

from velocista.infrastructure.config.settings import settings

PASSWORD = "qa-password-only-for-tests"


@pytest.fixture
def protected(monkeypatch, client):
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "secret_key", "qa-signing-secret-" * 4)
    monkeypatch.setattr(settings, "admin_username", "qa-admin")
    monkeypatch.setattr(settings, "admin_password", PASSWORD)
    return client


def login(client, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": "qa-admin", "password": password})


class TestAuth:
    def test_protected_route_when_no_token_returns_401(self, protected):
        assert protected.get("/api/robots").status_code == 401

    def test_health_is_public_even_when_auth_required(self, protected):
        assert protected.get("/api/health").status_code == 200

    def test_login_when_credentials_wrong_returns_401(self, protected):
        assert login(protected, "wrong").status_code == 401

    @pytest.mark.parametrize("payload", [{}, {"username": "qa-admin"}, {"password": "x"}])
    def test_login_when_fields_missing_returns_422(self, protected, payload):
        assert protected.post("/api/auth/login", json=payload).status_code == 422

    def test_login_when_ok_token_grants_access_and_me_returns_username(self, protected):
        token = login(protected).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert protected.get("/api/auth/me", headers=headers).json() == {"username": "qa-admin"}
        assert protected.get("/api/robots", headers=headers).status_code == 200

    def test_protected_route_when_token_tampered_returns_401(self, protected):
        token = login(protected).json()["access_token"]
        response = protected.get("/api/robots", headers={"Authorization": f"Bearer {token}x"})
        assert response.status_code == 401

    def test_auth_me_when_no_token_returns_401(self, protected):
        assert protected.get("/api/auth/me").status_code == 401
