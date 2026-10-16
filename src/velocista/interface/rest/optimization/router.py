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


@router.get("/controllers", operation_id="listControllers")
def list_controllers(service: Service):
    return service.list_controllers()


@router.get("/robots/{robot_id}/setups", response_model=SetupsPage, operation_id="listSetups")
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
)
def create_setup(robot_id: RobotId, data: SetupCreate, service: Service):
    return service.create_setup(robot_id, data.model_dump())


@router.get("/setups/{setup_id}", response_model=SetupOut, operation_id="getSetup")
def get_setup(setup_id: SetupId, service: Service):
    return service.get_setup(setup_id)


@router.delete("/setups/{setup_id}", status_code=204, operation_id="archiveSetup")
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


@router.get("/robots/{robot_id}/controllers", operation_id="listReconciledControllers")
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


@router.get("/robots/{robot_id}/configuration", operation_id="getRobotControllerConfig")
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
    "/robots/{robot_id}/setups/{setup_id}/apply", status_code=202, operation_id="applySetup"
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


@router.post("/robots/{robot_id}/presets/apply", status_code=202, operation_id="applyPreset")
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
