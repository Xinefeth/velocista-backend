"""Opt-in acceptance test against a DEPLOYED API: creates, reads, exports and deletes ITS OWN track.

Run only on purpose: TRACKS_LIVE_TEST=1 plus TRACKS_LIVE_URL (for example https://host), and
TRACKS_LIVE_USER / TRACKS_LIVE_PASSWORD when the API requires a login. Credentials come from the
environment and are never stored in the repository. It touches no other row.
"""

import os

import httpx
import pytest

from support.track_fixtures import track_payload

pytestmark = pytest.mark.skipif(
    os.getenv("TRACKS_LIVE_TEST") != "1", reason="Opt-in deployed API test (TRACKS_LIVE_TEST=1)"
)


def test_deployed_api_creates_reads_exports_and_deletes_its_own_track():
    base = os.environ["TRACKS_LIVE_URL"].rstrip("/")
    with httpx.Client(base_url=base, timeout=30) as http:
        user, password = os.getenv("TRACKS_LIVE_USER"), os.getenv("TRACKS_LIVE_PASSWORD")
        if user and password:
            login = http.post("/api/auth/login", json={"username": user, "password": password})
            assert login.status_code == 200
            http.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        created = http.post("/api/tracks", json=track_payload(name="live-test-track"))
        assert created.status_code == 201, created.text
        track_id = created.json()["id"]
        try:
            assert http.get(f"/api/tracks/{track_id}").json()["name"] == "live-test-track"
            exported = http.get(f"/api/tracks/{track_id}/export")
            assert exported.status_code == 200
            assert "attachment" in exported.headers["content-disposition"]
            assert exported.json()["id"] == track_id
        finally:
            assert http.delete(f"/api/tracks/{track_id}").status_code == 204
        assert http.get(f"/api/tracks/{track_id}").status_code == 404
