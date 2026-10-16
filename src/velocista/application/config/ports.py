"""Ports del contexto `config`."""

from __future__ import annotations

from typing import Any, Protocol

from velocista.domain.config.entities import RobotConfig


class ConfigRepository(Protocol):
    def get(self, robot_id: str) -> RobotConfig | None: ...

    def upsert(self, robot_id: str, *, column: str, value: str) -> None:
        """Guarda modo o línea (column = 'mode' | 'line') del robot."""
        ...


class DeviceGateway(Protocol):
    """Envío validado de comandos al robot (contra su manifiesto y estado vivos)."""

    async def apply_mode(self, robot_id: str, value: Any) -> int: ...

    async def apply_line(self, robot_id: str, value: Any) -> int: ...
