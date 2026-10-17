"""Device manifests and validated asynchronous commands."""

from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from velocista.domain.shared.errors import DeviceUnavailable, NotFound
from velocista.infrastructure.realtime.device_gateway import (
    RealtimeDeviceGateway,
)
from velocista.infrastructure.realtime.registry import hub
from velocista.interface.rest.errors import error_responses

router = APIRouter(prefix="/api/devices", tags=["devices"])


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    robot_id: str | None = None


@router.get(
    "/robot/manifest",
    operation_id="getRobotManifest",
    summary="Get the manifest of the connected robot",
    description=(
        "Returns the manifest the robot sent when it connected: channels, "
        "controllers, accepted commands and frequencies."
    ),
    responses=error_responses(
        {404: "The robot is not connected or has not sent its manifest (`no_manifest`)"}
    ),
)
def get_manifest():
    connection = hub.connections.get("robot")
    if not connection or not connection.manifest:
        raise NotFound("no_manifest", "The robot has not sent its manifest")
    return connection.manifest.model_dump(exclude_none=True)


@router.post(
    "/{device}/commands",
    status_code=202,
    operation_id="sendCommand",
    summary="Send a command to a device",
    description=(
        "Low-level command to the `robot` or the `timer`. The command is "
        "validated against the message contract, queued (HTTP 202) and "
        "acknowledged through the console WebSocket."
    ),
    responses=error_responses(
        {
            409: (
                "Robot not connected (`no_manifest`), not calibrated (`not_calibrated`), "
                "busy or locked by competition mode"
            ),
            422: (
                "Command is not part of the contract (`invalid_command`) or the robot "
                "does not declare it (`unknown_command`)"
            ),
            503: (
                "Device disconnected (`device_unavailable`); this body is `{reason, "
                "detail}` without the outer `detail`"
            ),
        },
        plain=[503],
    ),
)
async def send_command(device: Literal["robot", "timer"], command: Command):
    try:
        seq = await RealtimeDeviceGateway().send_command(
            device, command.type, command.data, robot_id=command.robot_id
        )
    except DeviceUnavailable as exc:
        return JSONResponse(status_code=503, content={"reason": exc.reason, "detail": exc.detail})
    return {
        "seq": seq,
        "message": "Sent; device acknowledgement arrives through the console WebSocket",
    }
