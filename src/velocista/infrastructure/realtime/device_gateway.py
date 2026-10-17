"""Validated command delivery through the live WebSocket registry."""

from typing import Any

from velocista.domain.shared.errors import Conflict, DeviceUnavailable, Validation
from velocista.infrastructure.realtime.registry import hub
from velocista.interface.websocket.contract.catalog import InvalidMessage, validate_data
from velocista.interface.websocket.contract.robot import Setup
from velocista.interface.websocket.contract.validation import check_setup


class RealtimeDeviceGateway:
    def __init__(self, session=None):
        self._session = session

    async def send_command(
        self, device: str, type: str, data: dict[str, Any], *, robot_id=None
    ) -> int:
        simulator = hub.simulator
        if device == "robot" and simulator is not None:
            return await simulator.command(type, data, robot_id=robot_id)
        if type == "ack":
            raise Validation("invalid_command", "ack is not a command")
        try:
            model = validate_data(f"api->{device}", type, data)
        except (InvalidMessage, TypeError, ValueError) as exc:
            raise Validation("invalid_command", str(exc)[:300]) from exc
        connection = hub.connections.get(device)
        if device == "robot":
            manifest = connection.manifest if connection else None
            if manifest is None or (robot_id is not None and manifest.id != robot_id):
                raise Conflict("no_manifest", "The selected robot has not sent its manifest")
            if type not in manifest.commands:
                raise Validation("unknown_command", "The robot does not declare this command")
            status = connection.last_status
            if (
                status
                and status.state == "running"
                and status.mode == "competition"
                and type != "stop"
            ):
                raise Conflict("competition_locked", "Only stop is allowed while competing")
            if (
                status
                and status.state in ("running", "calibrating")
                and type not in ("stop", "lap_close")
            ):
                raise Conflict("busy", "The robot is running or calibrating")
            if type == "start" and (not status or not status.calibrated):
                raise Conflict("not_calibrated", "Calibrate the robot before starting")
            if isinstance(model, Setup) and (problem := check_setup(manifest, model)):
                raise Validation(problem[0], problem[1])
        if connection is None:
            raise DeviceUnavailable("device_unavailable", "Device is disconnected")
        try:
            return await hub.send(device, type, model.model_dump(exclude_none=True))
        except (KeyError, RuntimeError, OSError) as exc:
            if hub.connections.get(device) is connection:
                hub.connections.pop(device, None)
            raise DeviceUnavailable(
                "device_unavailable", "Device disconnected during delivery"
            ) from exc

    async def apply_mode(self, robot_id, value):
        return await self.send_command("robot", "mode", {"mode": value}, robot_id=robot_id)

    async def apply_line(self, robot_id, value):
        return await self.send_command("robot", "line", {"color": value}, robot_id=robot_id)


ProvisionalDeviceGateway = RealtimeDeviceGateway
