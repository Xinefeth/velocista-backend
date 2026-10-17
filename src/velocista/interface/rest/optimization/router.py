from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt
from sqlalchemy.orm import Session

from velocista.application.optimization.use_cases import OptimizationService
from velocista.infrastructure.persistence.db import get_session
from velocista.infrastructure.persistence.repositories.optimization_repository import (
    SqlAlchemyOptimizationRepository,
)
from velocista.interface.rest.errors import error_responses


class SetupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    version_id: int = Field(strict=True, ge=1, le=9007199254740991)
    name: str = Field(min_length=1, max_length=120)
    controller_id: str = Field(min_length=1, max_length=40)
    parameters: dict[str, StrictFloat | StrictInt] = Field(max_length=32)


class SetupOut(BaseModel):
    id: int
    robot_id: str
    version_id: int
    name: str
    controller_id: str
    parameters: dict[str, float]
    created_at: datetime
    archived: bool


class SetupsPage(BaseModel):
    items: list[SetupOut]
    total: int
    limit: int
    offset: int


def get_service(session: Annotated[Session, Depends(get_session)]):
    return OptimizationService(SqlAlchemyOptimizationRepository(session))


Service = Annotated[OptimizationService, Depends(get_service)]
RobotId = Annotated[str, Path(min_length=1, max_length=40)]
SetupId = Annotated[int, Path(ge=1, le=9007199254740991)]
router = APIRouter(prefix="/api", tags=["optimization"])


@router.get(
    "/controllers",
    operation_id="listControllers",
    summary="List controllers",
    description=(
        "Returns the controller catalog (for example PID) with each parameter's "
        "key, range and the named presets."
    ),
)
def list_controllers(service: Service):
    return service.list_controllers()


@router.get(
    "/robots/{robot_id}/setups",
    response_model=SetupsPage,
    operation_id="listSetups",
    summary="List the setups of a robot",
    description=(
        "A setup is a saved set of controller parameters for one robot version. "
        "Archived setups are hidden. Paginated with `limit` (1-200, default 50) "
        "and `offset` (default 0). Optional filter `version_id`."
    ),
    responses=error_responses({404: "Robot does not exist (`robot_not_found`)"}),
)
def list_setups(
    robot_id: RobotId,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    version_id: Annotated[int | None, Query(ge=1)] = None,
):
    return service.list_setups(robot_id, limit, offset, version_id)


@router.post(
    "/robots/{robot_id}/setups",
    status_code=201,
    response_model=SetupOut,
    operation_id="createSetup",
    summary="Save a setup",
    description=(
        "Stores a controller and its parameters for a version of the robot. "
        "Parameters must match the controller definition exactly and stay inside "
        "each allowed range."
    ),
    responses=error_responses(
        {
            404: (
                "Version does not belong to the robot (`version_not_found`) or controller "
                "does not exist (`controller_not_found`)"
            ),
            422: (
                "Parameters missing, extra or out of range (`invalid_parameters`, `out_of_range`)"
            ),
        }
    ),
)
def create_setup(robot_id: RobotId, data: SetupCreate, service: Service):
    return service.create_setup(robot_id, data.model_dump())


@router.get(
    "/setups/{setup_id}",
    response_model=SetupOut,
    operation_id="getSetup",
    summary="Get a setup",
    description="Returns one setup, including archived ones.",
    responses=error_responses({404: "Setup does not exist (`setup_not_found`)"}),
)
def get_setup(setup_id: SetupId, service: Service):
    return service.get_setup(setup_id)


@router.delete(
    "/setups/{setup_id}",
    status_code=204,
    operation_id="archiveSetup",
    summary="Archive a setup",
    description=(
        "Soft delete. Runs already recorded keep the parameters they used. Returns no body."
    ),
    responses=error_responses({404: "Setup does not exist (`setup_not_found`)"}),
)
def archive_setup(setup_id: SetupId, service: Service):
    service.archive_setup(setup_id)
    return Response(status_code=204)


class PresetApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    controller_id: str = Field(min_length=1, max_length=40)
    preset_id: str = Field(min_length=1, max_length=40)


def selected_manifest(robot_id):
    from velocista.infrastructure.realtime.registry import hub

    connection = hub.connections.get("robot")
    manifest = connection.manifest if connection else None
    return manifest if manifest and manifest.id == robot_id else None


@router.get(
    "/robots/{robot_id}/controllers",
    operation_id="listReconciledControllers",
    summary="List controllers with live values",
    description=(
        "Like `GET /api/controllers`, but each parameter also carries the `value` "
        "currently loaded in the connected robot and the active controller is "
        "flagged. When the robot is not connected, values are null and no "
        "controller is active."
    ),
)
def reconciled_controllers(robot_id: RobotId, service: Service):
    manifest = selected_manifest(robot_id)
    controllers = []
    for controller in service.list_controllers():
        live = manifest.controller(controller["id"]) if manifest else None
        parameters = []
        for parameter in controller["parameters"]:
            current = live.parameter(parameter["key"]) if live else None
            parameters.append({**parameter, "value": current.value if current else None})
        controllers.append(
            {
                **controller,
                "parameters": parameters,
                "active": bool(manifest and manifest.active_controller == controller["id"]),
            }
        )
    return {
        "active_controller": manifest.active_controller if manifest else None,
        "controllers": controllers,
    }


@router.get(
    "/robots/{robot_id}/configuration",
    operation_id="getRobotControllerConfig",
    summary="Get the configuration loaded in the robot",
    description=(
        "Returns the active controller and its parameter values exactly as the "
        "robot reported them in its manifest."
    ),
    responses=error_responses(
        {404: "The selected robot has not sent its manifest (`no_manifest`)"}
    ),
)
def live_configuration(robot_id: RobotId):
    from velocista.domain.shared.errors import NotFound

    manifest = selected_manifest(robot_id)
    if manifest is None:
        raise NotFound("no_manifest", "The selected robot has not sent its manifest")
    controller = manifest.controller(manifest.active_controller)
    return {
        "active_controller": controller.name,
        "parameters": [
            {"name": parameter.name, "value": parameter.value}
            for parameter in controller.parameters
        ],
    }


@router.post(
    "/robots/{robot_id}/setups/{setup_id}/apply",
    status_code=202,
    operation_id="applySetup",
    summary="Send a saved setup to the robot",
    description=(
        "Asynchronous: the command is queued (HTTP 202) and the robot confirms "
        "through the console WebSocket with an `ack` message carrying the "
        "returned `seq`. Competition mode locks the setup while the robot is "
        "running."
    ),
    responses=error_responses(
        {
            404: "Setup does not exist or belongs to another robot",
            409: (
                "Setup is archived (`setup_archived`), robot not connected "
                "(`no_manifest`), busy, not calibrated or locked by competition mode"
            ),
            503: "Robot disconnected while sending (`device_unavailable`)",
        }
    ),
)
async def apply_setup(robot_id: RobotId, setup_id: SetupId, service: Service):
    from velocista.domain.shared.errors import Conflict, NotFound
    from velocista.infrastructure.realtime.device_gateway import RealtimeDeviceGateway

    setup = service.get_setup(setup_id)
    if setup["robot_id"] != robot_id:
        raise NotFound("setup_not_found", "Setup does not belong to this robot")
    if setup["archived"]:
        raise Conflict("setup_archived", "An archived setup cannot be applied")
    seq = await RealtimeDeviceGateway().send_command(
        "robot",
        "setup",
        {
            "controller": setup["controller_id"],
            "parameters": setup["parameters"],
            "setup_id": setup_id,
        },
        robot_id=robot_id,
    )
    return {"seq": seq, "message": "Sent; acknowledgement arrives through the console WebSocket"}


@router.post(
    "/robots/{robot_id}/presets/apply",
    status_code=202,
    operation_id="applyPreset",
    summary="Send a controller preset to the robot",
    description=(
        "Same as applying a setup, but uses one of the named presets declared by "
        "the controller (for example `Base`)."
    ),
    responses=error_responses(
        {
            404: "Controller does not exist (`controller_not_found`)",
            409: "Robot not connected (`no_manifest`), busy or locked",
            422: "Controller does not declare that preset (`preset_not_found`)",
        }
    ),
)
async def apply_preset(robot_id: RobotId, data: PresetApply, service: Service):
    from velocista.domain.optimization.validation import validate_parameters
    from velocista.domain.shared.errors import NotFound, Validation
    from velocista.infrastructure.realtime.device_gateway import RealtimeDeviceGateway

    controller = next(
        (item for item in service.list_controllers() if item["id"] == data.controller_id), None
    )
    if controller is None:
        raise NotFound("controller_not_found", "Controller does not exist")
    parameters = controller["presets"].get(data.preset_id)
    if parameters is None:
        raise Validation("preset_not_found", "Controller does not declare this preset")
    parameters = validate_parameters(controller["parameters"], parameters)
    seq = await RealtimeDeviceGateway().send_command(
        "robot",
        "setup",
        {"controller": data.controller_id, "parameters": parameters, "setup_id": None},
        robot_id=robot_id,
    )
    return {"seq": seq, "message": "Sent; acknowledgement arrives through the console WebSocket"}
