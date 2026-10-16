"""Servicio de aplicación del contexto `catalog`. Delega en el repositorio (lógica portada)."""

from __future__ import annotations

from typing import Any

from velocista.application.catalog.ports import CatalogRepository


class CatalogService:
    def __init__(self, repo: CatalogRepository) -> None:
        self._repo = repo

    def create_component(self, data: Any) -> dict[str, Any]:
        return self._repo.create_component(data)

    def get_component(self, component_id: str) -> dict[str, Any]:
        return self._repo.get_component(component_id)

    def edit_component(self, component_id: str, data: Any) -> dict[str, Any]:
        return self._repo.edit_component(component_id, data)

    def archive_component(self, component_id: str) -> None:
        self._repo.archive_component(component_id)

    def list_component_types(self) -> list[Any]:
        return self._repo.list_component_types()

    def list_inventory(self, *, limit: int, offset: int) -> dict[str, Any]:
        return self._repo.list_inventory(limit=limit, offset=offset)

    def update_inventory(self, component_id: str, data: Any) -> dict[str, Any]:
        return self._repo.update_inventory(component_id, data)

    def list_components(
        self, *, limit: int, offset: int, q: str | None, type_id: str | None
    ) -> dict[str, Any]:
        return self._repo.list_components(limit=limit, offset=offset, q=q, type_id=type_id)
