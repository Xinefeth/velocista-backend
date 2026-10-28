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


class TestProfileTrackRules:
    """EN-28: `rules.track` travels inside the existing JSONB `rules` (read-only API)."""

    TRACK = {
        "line_width_mm": 19,
        "gap_length_cm": 2,
        "radius_min": {"enabled": True, "value": 15},
        "length_min": {"enabled": False, "value": 500},
    }

    def test_profile_with_track_rules_returns_them_unchanged(self, client, db):
        from sqlalchemy.orm import Session

        from velocista.infrastructure.persistence.models.rules import ProfileModel

        with Session(bind=db, join_transaction_mode="create_savepoint") as session:
            session.add(
                ProfileModel(
                    id="lgr-test",
                    competition="LGR",
                    label="LGR",
                    category="Racer",
                    rules={"track": self.TRACK},
                )
            )
            session.commit()
        assert client.get("/api/profiles/lgr-test").json()["rules"] == {"track": self.TRACK}
        listed = {p["id"]: p for p in client.get("/api/profiles").json()}
        assert listed["lgr-test"]["rules"]["track"] == self.TRACK

    def test_profile_without_track_block_is_returned_as_it_is(self, client):
        assert "track" not in client.get("/api/profiles/club").json()["rules"]
