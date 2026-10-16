"""Ports del contexto `builder`.

Rompen el ciclo con `catalog` (snapshot de componente) y con la actividad del robot
(realtime + corridas en curso): la capa `application` los declara, `infrastructure` los implementa.
"""

from __future__ import annotations

from typing import Any, Protocol

from velocista.domain.builder.entities import Robot, Slot


class ComponentProvider(Protocol):
    """Catálogo visto desde builder: ficha de un componente para congelar en una versión."""

    def snapshot_for_version(self, component_id: str) -> dict[str, Any]:
        """Devuelve la ficha (sin stock/archived) o lanza NotFound/Conflict si no sirve."""
        ...


class RobotActivity(Protocol):
    """¿El robot está corriendo (realtime) o tiene una corrida abierta en la BD?"""

    def is_running(self, robot_id: str) -> bool: ...


class BuilderRepository(Protocol):
    def create_robot(
        self, *, name: str, short_code: str, type: str, firmware: str | None
    ) -> Robot: ...

    def list_robots(self, *, limit: int, offset: int) -> dict[str, Any]: ...

    def get_robot(self, robot_id: str) -> Robot: ...

    def update_robot(self, robot_id: str, changes: dict[str, Any]) -> Robot: ...

    def archive_robot(self, robot_id: str) -> None: ...

    def list_slots(self) -> list[Slot]: ...

    def list_versions(self, robot_id: str, *, limit: int, offset: int) -> dict[str, Any]: ...

    def get_version(self, robot_id: str, version_id: int) -> dict[str, Any]: ...

    def create_version(self, robot_id: str, data: Any) -> dict[str, Any]: ...
