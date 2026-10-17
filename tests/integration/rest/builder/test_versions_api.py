"""Builder: immutable versions with component snapshots and optimistic concurrency."""


class TestVersions:
    def test_create_first_version_when_current_sets_robot_current_version(self, client, build):
        robot_id = build.robot()
        version_id = build.version(robot_id, build.component())
        assert client.get(f"/api/robots/{robot_id}").json()["current_version_id"] == version_id

    def test_create_current_version_when_required_slot_missing_returns_422(self, client, build):
        robot_id = build.robot()
        response = client.post(
            f"/api/robots/{robot_id}/versions",
            json={"base_version_id": None, "note": "x", "status": "current", "parts": {}},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "required_slots_missing"

    def test_create_draft_version_when_parts_empty_is_allowed(self, client, build):
        robot_id = build.robot()
        response = client.post(
            f"/api/robots/{robot_id}/versions",
            json={"base_version_id": None, "note": "x", "status": "draft", "parts": {}},
        )
        assert response.status_code == 201, response.text

    def test_create_version_when_base_is_stale_returns_409_version_stale(self, client, build):
        robot_id = build.robot()
        component_id = build.component()
        build.version(robot_id, component_id)
        response = client.post(
            f"/api/robots/{robot_id}/versions",
            json={
                "base_version_id": None,
                "note": "x",
                "status": "current",
                "parts": {"mcu": {"component_id": component_id, "quantity": 1}},
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "version_stale"

    def test_new_current_version_when_created_demotes_previous_to_previous(self, client, build):
        robot_id = build.robot()
        component_id = build.component()
        first = build.version(robot_id, component_id)
        build.version(robot_id, component_id, base_version_id=first)
        statuses = [
            v["status"] for v in client.get(f"/api/robots/{robot_id}/versions").json()["items"]
        ]
        assert statuses == ["previous", "current"]

    def test_version_snapshot_when_component_edited_keeps_original_data(self, client, build):
        robot_id = build.robot()
        component_id = build.component("Original")
        version_id = build.version(robot_id, component_id)
        client.patch(f"/api/components/{component_id}", json={"name": "Changed"})
        parts = client.get(f"/api/robots/{robot_id}/versions/{version_id}").json()["parts"]
        assert parts["mcu"]["component_snapshot"]["name"] == "Original"

    def test_get_version_when_it_belongs_to_another_robot_returns_404(self, client, build):
        robot_id = build.robot("A")
        version_id = build.version(robot_id, build.component())
        other = build.robot("B", name="Other")
        assert client.get(f"/api/robots/{other}/versions/{version_id}").status_code == 404

    def test_create_version_when_robot_missing_returns_404(self, client, build):
        component_id = build.component()
        response = client.post(
            "/api/robots/ghost/versions",
            json={
                "base_version_id": None,
                "note": "x",
                "status": "draft",
                "parts": {"mcu": {"component_id": component_id, "quantity": 1}},
            },
        )
        assert response.status_code == 404

    def test_create_version_when_legacy_field_name_returns_422(self, client, build):
        robot_id = build.robot()
        response = client.post(
            f"/api/robots/{robot_id}/versions",
            json={"version_base_id": None, "note": "x", "status": "draft", "parts": {}},
        )
        assert response.status_code == 422
