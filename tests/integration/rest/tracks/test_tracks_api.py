"""Tracks API: CRUD, import/export, units and authentication (real PostgreSQL, isolated)."""

import pytest

from support.track_fixtures import track_payload
from velocista.infrastructure.config.settings import settings

TRACKS = "/api/tracks"
PASSWORD = "qa-password-only-for-tests"


def create(client, **overrides):
    response = client.post(TRACKS, json=track_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


class TestCreateAndRead:
    def test_create_returns_201_with_every_field(self, client):
        track = create(client, profile_id="club", length_cm=812.4)
        assert set(track) == {
            "id",
            "name",
            "board",
            "closed",
            "points",
            "zones",
            "start",
            "profile_id",
            "length_cm",
            "created_at",
            "updated_at",
        }
        assert track["id"] >= 1
        assert track["board"] == {"width_cm": 300, "height_cm": 250}
        assert track["profile_id"] == "club"

    def test_create_stores_length_as_sent(self, client):
        track = create(client, length_cm=812.4)
        assert client.get(f"{TRACKS}/{track['id']}").json()["length_cm"] == 812.4

    def test_create_when_start_and_zones_omitted_uses_defaults(self, client):
        body = track_payload()
        del body["start"], body["zones"]
        response = client.post(TRACKS, json=body)
        assert response.status_code == 201
        assert response.json()["start"] == {"edge": 0, "t": 0.5}
        assert response.json()["zones"] == []

    def test_create_when_name_has_spaces_trims_it(self, client):
        assert create(client, name="  Oval  ")["name"] == "Oval"

    def test_get_returns_the_created_track(self, client):
        track = create(client)
        assert client.get(f"{TRACKS}/{track['id']}").json() == track

    def test_list_returns_page_envelope_most_recent_first(self, client):
        a = create(client, name="a")
        b = create(client, name="b")
        body = client.get(TRACKS).json()
        assert set(body) == {"items", "total", "limit", "offset"}
        assert (body["total"], body["limit"], body["offset"]) == (2, 50, 0)
        assert [t["id"] for t in body["items"]] == [b["id"], a["id"]]

    def test_list_paginates(self, client):
        for name in "abc":
            create(client, name=name)
        page = client.get(TRACKS, params={"limit": 1, "offset": 1}).json()
        assert (page["total"], len(page["items"]), page["items"][0]["name"]) == (3, 1, "b")

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
    def test_list_when_paging_out_of_range_returns_422(self, client, params):
        assert client.get(TRACKS, params=params).status_code == 422


class TestUpdateAndDelete:
    def test_update_replaces_fields_keeps_id_and_created_at(self, client):
        track = create(client)
        response = client.put(
            f"{TRACKS}/{track['id']}", json=track_payload(name="Edited", length_cm=900)
        )
        assert response.status_code == 200
        body = response.json()
        assert (body["id"], body["name"], body["length_cm"]) == (track["id"], "Edited", 900)
        assert body["created_at"] == track["created_at"]
        assert body["updated_at"] >= track["updated_at"]

    def test_update_moves_the_track_to_the_top_of_the_list(self, client):
        first = create(client, name="first")
        create(client, name="second")
        client.put(f"{TRACKS}/{first['id']}", json=track_payload(name="first edited"))
        assert client.get(TRACKS).json()["items"][0]["id"] == first["id"]

    def test_delete_returns_204_and_then_404(self, client):
        track = create(client)
        response = client.delete(f"{TRACKS}/{track['id']}")
        assert (response.status_code, response.content) == (204, b"")
        assert client.get(f"{TRACKS}/{track['id']}").status_code == 404

    @pytest.mark.parametrize(
        ("method", "suffix"),
        [("get", ""), ("put", ""), ("delete", ""), ("get", "/export")],
    )
    def test_missing_track_returns_404_track_not_found(self, client, method, suffix):
        kwargs = {"json": track_payload()} if method == "put" else {}
        response = getattr(client, method)(f"{TRACKS}/999999{suffix}", **kwargs)
        assert response.status_code == 404
        assert response.json() == {
            "detail": {"reason": "track_not_found", "detail": "Track does not exist"}
        }

    @pytest.mark.parametrize("track_id", ["0", "-1", "abc"])
    def test_invalid_id_returns_422(self, client, track_id):
        assert client.get(f"{TRACKS}/{track_id}").status_code == 422


class TestImportExport:
    def test_export_returns_the_track_with_download_header(self, client):
        track = create(client, name="Técnica 3 × 2,5")
        response = client.get(f"{TRACKS}/{track['id']}/export")
        assert response.status_code == 200
        assert response.json() == track
        disposition = response.headers["content-disposition"]
        assert disposition == 'attachment; filename="tecnica-3-2-5.json"'

    def test_export_when_name_has_no_ascii_uses_a_fallback_filename(self, client):
        track = create(client, name="???")
        header = client.get(f"{TRACKS}/{track['id']}/export").headers["content-disposition"]
        assert header == f'attachment; filename="track-{track["id"]}.json"'

    def test_post_of_an_exported_file_creates_a_new_track_ignoring_read_only_fields(self, client):
        original = create(client)
        exported = client.get(f"{TRACKS}/{original['id']}/export").json()
        response = client.post(TRACKS, json=exported)
        assert response.status_code == 201
        imported = response.json()
        assert imported["id"] > original["id"]
        read_only = ("id", "created_at", "updated_at")
        assert {k: v for k, v in imported.items() if k not in read_only} == {
            k: v for k, v in original.items() if k not in read_only
        }
        assert client.get(TRACKS).json()["total"] == 2

    def test_post_of_the_raw_prototype_format_is_rejected(self, client):
        prototype = {
            "v": 2,
            "name": "Prototype",
            "board": {"w": 300, "h": 250},
            "closed": True,
            "pts": [{"x": 1, "y": 1, "r": 0}] * 3,
            "zones": [],
            "start": {"e": 0, "t": 0.5},
        }
        response = client.post(TRACKS, json=prototype)
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)
        assert client.get(TRACKS).json()["total"] == 0


class TestAuthentication:
    @pytest.fixture
    def protected(self, monkeypatch, client):
        monkeypatch.setattr(settings, "auth_required", True)
        monkeypatch.setattr(settings, "secret_key", "qa-signing-secret-" * 4)
        monkeypatch.setattr(settings, "admin_username", "qa-admin")
        monkeypatch.setattr(settings, "admin_password", PASSWORD)
        return client

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", TRACKS),
            ("post", TRACKS),
            ("get", f"{TRACKS}/1"),
            ("put", f"{TRACKS}/1"),
            ("delete", f"{TRACKS}/1"),
            ("get", f"{TRACKS}/1/export"),
        ],
    )
    def test_routes_when_no_token_return_401(self, protected, method, path):
        response = getattr(protected, method)(path)
        assert response.status_code == 401
        assert response.json()["detail"]["reason"] == "unauthorized"

    def test_routes_when_token_valid_grant_access(self, protected):
        login = protected.post(
            "/api/auth/login", json={"username": "qa-admin", "password": PASSWORD}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert protected.get(TRACKS, headers=headers).status_code == 200
        assert protected.post(TRACKS, json=track_payload(), headers=headers).status_code == 201
