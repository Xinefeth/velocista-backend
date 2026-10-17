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

router = APIRouter(prefix="/api/devices", tags=["devices"])


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    robot_id: str | None = None


@router.get("/robot/manifest", operation_id="getRobotManifest")
def get_manifest():
    connection = hub.connections.get("robot")
    if not connection or not connection.manifest:
        raise NotFound("no_manifest", "The robot has not sent its manifest")
    return connection.manifest.model_dump(exclude_none=True)


@router.post("/{device}/commands", status_code=202, operation_id="sendCommand")
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
