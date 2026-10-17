"""Catalog: component types, components CRUD and inventory (REST + PostgreSQL)."""

import pytest


class TestComponentTypes:
    def test_list_component_types_when_seeded_returns_type_with_fields(self, client):
        response = client.get("/api/component-types")
        assert response.status_code == 200
        assert [t["id"] for t in response.json()] == ["mcu"]
        assert {"id", "name", "color", "fields", "capabilities"} <= set(response.json()[0])

    def test_list_slots_returns_required_slots(self, client):
        slots = client.get("/api/slots").json()
        assert slots[0]["id"] == "mcu" and slots[0]["required"] is True


class TestComponentsCrud:
    def test_create_component_when_valid_returns_201_with_defaults(self, client):
        response = client.post(
            "/api/components",
            json={
                "type_id": "mcu",
                "name": "ESP32",
                "price": 25.5,
                "mass_g": 8,
                "specs": {},
                "stock": 3,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["name"] == "ESP32" and body["stock"] == 3 and body["archived"] is False

    @pytest.mark.parametrize("field,value", [("price", 0), ("price", -1), ("mass_g", -1)])
    def test_create_component_when_number_out_of_range_returns_422(self, client, field, value):
        payload = {"type_id": "mcu", "name": "X", "price": 1, "mass_g": 1, "specs": {}, "stock": 1}
        payload[field] = value
        assert client.post("/api/components", json=payload).status_code == 422

    def test_create_component_when_type_is_unknown_returns_422(self, client):
        response = client.post(
            "/api/components",
            json={
                "type_id": "ghost",
                "name": "X",
                "price": 1,
                "mass_g": 1,
                "specs": {},
                "stock": 1,
            },
        )
        assert response.status_code == 422, response.text

    def test_get_component_when_exists_returns_it(self, client, build):
        component_id = build.component("Sensor board")
        response = client.get(f"/api/components/{component_id}")
        assert response.status_code == 200 and response.json()["name"] == "Sensor board"

    def test_get_component_when_missing_returns_404_with_reason(self, client):
        response = client.get("/api/components/missing")
        assert response.status_code == 404
        assert set(response.json()["detail"]) == {"reason", "detail"}

    def test_update_component_when_partial_changes_only_given_fields(self, client, build):
        component_id = build.component("Old")
        response = client.patch(f"/api/components/{component_id}", json={"name": "New"})
        assert response.status_code == 200
        assert response.json()["name"] == "New" and response.json()["stock"] == 2

    def test_archive_component_when_not_used_hides_it_from_default_list(self, client, build):
        component_id = build.component()
        assert client.delete(f"/api/components/{component_id}").status_code == 204
        ids = [c["id"] for c in client.get("/api/components").json()["items"]]
        assert component_id not in ids

    def test_list_components_when_paginated_respects_limit_and_offset(self, client, build):
        for index in range(3):
            build.component(f"C{index}")
        page = client.get("/api/components?limit=2&offset=1").json()
        assert page["total"] == 3 and page["limit"] == 2 and page["offset"] == 1
        assert len(page["items"]) == 2

    @pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1"])
    def test_list_components_when_pagination_invalid_returns_422(self, client, query):
        assert client.get(f"/api/components?{query}").status_code == 422


class TestInventory:
    def test_list_inventory_when_component_unused_available_equals_stock(self, client, build):
        component_id = build.component(stock=4)
        item = next(
            i
            for i in client.get("/api/inventory").json()["items"]
            if i["component_id"] == component_id
        )
        assert (item["stock"], item["in_robots"], item["available"], item["shortage"]) == (
            4,
            0,
            4,
            0,
        )

    def test_inventory_when_component_used_in_version_counts_it_as_in_robots(self, client, build):
        robot_id = build.robot()
        component_id = build.component(stock=2)
        build.version(robot_id, component_id)
        item = client.get("/api/inventory").json()["items"][0]
        assert item["in_robots"] == 1 and item["available"] == 1

    def test_update_inventory_when_revision_matches_updates_stock(self, client, build):
        component_id = build.component(stock=1)
        current = client.get("/api/inventory").json()["items"][0]
        response = client.put(
            f"/api/inventory/{component_id}",
            json={"stock": 9, "revision": current["revision"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["stock"] == 9

    def test_update_inventory_when_revision_is_stale_returns_409(self, client, build):
        component_id = build.component(stock=1)
        current = client.get("/api/inventory").json()["items"][0]
        client.put(
            f"/api/inventory/{component_id}", json={"stock": 5, "revision": current["revision"]}
        )
        stale = client.put(
            f"/api/inventory/{component_id}", json={"stock": 7, "revision": current["revision"]}
        )
        assert stale.status_code == 409, stale.text

    def test_update_inventory_when_stock_negative_returns_422(self, client, build):
        component_id = build.component()
        response = client.put(f"/api/inventory/{component_id}", json={"stock": -1, "revision": 0})
        assert response.status_code == 422
