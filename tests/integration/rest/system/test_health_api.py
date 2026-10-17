"""System: health check and OpenAPI/Swagger availability."""


class TestHealth:
    def test_health_when_database_is_up_returns_200(self, client):
        assert client.get("/api/health").status_code == 200

    def test_swagger_ui_and_openapi_are_served(self, client):
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").json()["openapi"].startswith("3.")
