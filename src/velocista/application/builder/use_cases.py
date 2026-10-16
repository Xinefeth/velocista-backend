"""Servicio de aplicación del contexto `builder`.

Orquestación fina: delega en el repositorio, que implementa la lógica de negocio portada
(reglas de versión, snapshots, guardas de actividad). Mantener aquí la superficie pública.
"""

from __future__ import annotations

from typing import Any

from velocista.application.builder.ports import BuilderRepository
from velocista.domain.builder.entities import Robot, Slot


class BuilderService:
    def __init__(self, repo: BuilderRepository) -> None:
        self._repo = repo

    def create_robot(self, *, name: str, short_code: str, type: str, firmware: str | None) -> Robot:
        return self._repo.create_robot(
            name=name, short_code=short_code, type=type, firmware=firmware
        )

    def list_robots(self, *, limit: int, offset: int) -> dict[str, Any]:
        return self._repo.list_robots(limit=limit, offset=offset)

    def get_robot(self, robot_id: str) -> Robot:
        return self._repo.get_robot(robot_id)

    def update_robot(self, robot_id: str, changes: dict[str, Any]) -> Robot:
        return self._repo.update_robot(robot_id, changes)

    def archive_robot(self, robot_id: str) -> None:
        self._repo.archive_robot(robot_id)

    def list_slots(self) -> list[Slot]:
        return self._repo.list_slots()

    def list_versions(self, robot_id: str, *, limit: int, offset: int) -> dict[str, Any]:
        return self._repo.list_versions(robot_id, limit=limit, offset=offset)

    def get_version(self, robot_id: str, version_id: int) -> dict[str, Any]:
        return self._repo.get_version(robot_id, version_id)

    def create_version(self, robot_id: str, data: Any) -> dict[str, Any]:
        return self._repo.create_version(robot_id, data)
