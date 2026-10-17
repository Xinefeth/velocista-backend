"""REST del modo de funcionamiento y color de línea del robot (HU-18)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from velocista.application.config.ports import ConfigRepository, DeviceGateway
from velocista.application.config.use_cases import GetConfig, SetLine, SetMode
from velocista.composition import get_config_repository, get_device_gateway
from velocista.interface.rest.config.schemas import (
    CommandAccepted,
    ConfigSaved,
    LineChange,
    ModeChange,
)
from velocista.interface.rest.errors import error_responses

router = APIRouter(prefix="/api", tags=["control"])
RobotId = Annotated[str, Path(min_length=1, max_length=40)]
Repo = Annotated[ConfigRepository, Depends(get_config_repository)]
Device = Annotated[DeviceGateway, Depends(get_device_gateway)]


@router.get(
    "/robots/{robot_id}/mode-line",
    response_model=ConfigSaved,
    operation_id="getRobotModeLine",
    summary="Get the saved mode and line color",
    description=(
        "Returns the last operating mode (`test` or `competition`) and line color "
        "(`black` or `white`) saved for the robot."
    ),
    responses=error_responses({404: "Nothing saved yet for this robot (`no_config`)"}),
)
def get_robot_mode_line(robot_id: RobotId, repo: Repo):
    return ConfigSaved.from_entity(GetConfig(repo).execute(robot_id))


@router.post(
    "/robots/{robot_id}/mode-line/mode",
    status_code=202,
    response_model=CommandAccepted,
    operation_id="setMode",
    summary="Change the operating mode",
    description=(
        "Sends the mode to the robot (HTTP 202, confirmation arrives by "
        "WebSocket) and saves it. Allowed values: `test`, `competition`."
    ),
    responses=error_responses(
        {
            409: "Robot has not sent its manifest (`no_manifest`) or is busy",
            422: "Invalid value (`invalid_command`)",
            503: "Robot disconnected (`device_unavailable`)",
        }
    ),
)
async def set_mode(robot_id: RobotId, body: ModeChange, repo: Repo, device: Device):
    seq = await SetMode(device, repo).execute(robot_id, body.mode)
    return CommandAccepted(seq=seq)


@router.post(
    "/robots/{robot_id}/mode-line/line",
    status_code=202,
    response_model=CommandAccepted,
    operation_id="setLine",
    summary="Change the line color",
    description=(
        "Sends the line color to the robot (HTTP 202, confirmation arrives by "
        "WebSocket) and saves it. Allowed values: `black`, `white`."
    ),
    responses=error_responses(
        {
            409: "Robot has not sent its manifest (`no_manifest`) or is busy",
            422: "Invalid value (`invalid_command`)",
            503: "Robot disconnected (`device_unavailable`)",
        }
    ),
)
async def set_line(robot_id: RobotId, body: LineChange, repo: Repo, device: Device):
    seq = await SetLine(device, repo).execute(robot_id, body.color)
    return CommandAccepted(seq=seq)
