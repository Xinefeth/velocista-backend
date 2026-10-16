"""Casos de uso del contexto `config` (HU-18).

Fijar modo/línea: se envía al robot por el gateway (que valida contra el manifiesto y el estado
vivos); si el envío tiene éxito, se persiste el valor por robot.
"""

from __future__ import annotations

from typing import Any

from velocista.application.config.ports import ConfigRepository, DeviceGateway
from velocista.domain.config.entities import RobotConfig
from velocista.domain.shared.errors import NotFound


class GetConfig:
    def __init__(self, repo: ConfigRepository) -> None:
        self._repo = repo

    def execute(self, robot_id: str) -> RobotConfig:
        config = self._repo.get(robot_id)
        if config is None:
            raise NotFound("no_config", "El robot no tiene modo ni línea guardados")
        return config


class SetMode:
    def __init__(self, device: DeviceGateway, repo: ConfigRepository) -> None:
        self._device = device
        self._repo = repo

    async def execute(self, robot_id: str, value: Any) -> int:
        seq = await self._device.apply_mode(robot_id, value)
        self._repo.upsert(robot_id, column="mode", value=value)
        return seq


class SetLine:
    def __init__(self, device: DeviceGateway, repo: ConfigRepository) -> None:
        self._device = device
        self._repo = repo

    async def execute(self, robot_id: str, value: Any) -> int:
        seq = await self._device.apply_line(robot_id, value)
        self._repo.upsert(robot_id, column="line", value=value)
        return seq
