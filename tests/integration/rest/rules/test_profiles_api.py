"""Rules: competition profiles."""


class TestProfiles:
    def test_list_profiles_returns_seeded_profiles(self, client):
        profiles = client.get("/api/profiles").json()
        assert [p["id"] for p in profiles] == ["club"]
        assert {"id", "competition", "label", "category", "rules"} <= set(profiles[0])

    def test_get_profile_when_exists_returns_it(self, client):
        assert client.get("/api/profiles/club").json()["label"] == "Club"

    def test_get_profile_when_missing_returns_404(self, client):
        response = client.get("/api/profiles/missing")
        assert response.status_code == 404
        assert set(response.json()["detail"]) == {"reason", "detail"}
