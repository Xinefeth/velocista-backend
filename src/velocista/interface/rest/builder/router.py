"""Controlador REST del contexto `builder`. Solo recibe, valida formato y delega en el servicio."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from velocista.application.builder.dto import PartInput, VersionCreateInput
from velocista.application.builder.use_cases import BuilderService
from velocista.composition import get_builder_service
from velocista.interface.rest.builder.schemas import (
    RobotCreate,
    RobotEdit,
    RobotOut,
    RobotsPage,
    SlotOut,
    VersionCreate,
    VersionOut,
    VersionsPage,
)

router = APIRouter(prefix="/api", tags=["builder"])
Service = Annotated[BuilderService, Depends(get_builder_service)]
RobotId = Annotated[str, Path(min_length=1, max_length=40)]
VersionId = Annotated[int, Path(ge=1, le=9007199254740991)]


@router.post("/robots", status_code=201, response_model=RobotOut, operation_id="createRobot")
def create_robot(data: RobotCreate, service: Service):
    robot = service.create_robot(
        name=data.name, short_code=data.short_code, type=data.type, firmware=data.firmware
    )
    return RobotOut.from_entity(robot)


@router.get("/robots", response_model=RobotsPage, operation_id="listRobots")
def list_robots(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=9007199254740991)] = 0,
):
    page = service.list_robots(limit=limit, offset=offset)
    return RobotsPage(
        items=[RobotOut.from_entity(r) for r in page["items"]],
        total=page["total"],
        limit=page["limit"],
        offset=page["offset"],
    )


@router.get("/robots/{robot_id}", response_model=RobotOut, operation_id="getRobot")
def get_robot(robot_id: RobotId, service: Service):
    return RobotOut.from_entity(service.get_robot(robot_id))


@router.get(
    "/robots/{robot_id}/versions", response_model=VersionsPage, operation_id="listRobotVersions"
)
def list_robot_versions(
    robot_id: RobotId,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=9007199254740991)] = 0,
):
    return service.list_versions(robot_id, limit=limit, offset=offset)


@router.get(
    "/robots/{robot_id}/versions/{version_id}",
    response_model=VersionOut,
    operation_id="getRobotVersion",
)
def get_robot_version(robot_id: RobotId, version_id: VersionId, service: Service):
    return service.get_version(robot_id, version_id)


@router.get("/slots", response_model=list[SlotOut], operation_id="listSlots")
def list_slots(service: Service):
    return service.list_slots()


@router.patch("/robots/{robot_id}", response_model=RobotOut, operation_id="updateRobot")
def update_robot(robot_id: RobotId, data: RobotEdit, service: Service):
    changes = data.model_dump(exclude_unset=True)
    return RobotOut.from_entity(service.update_robot(robot_id, changes))


@router.delete(
    "/robots/{robot_id}", status_code=204, response_class=Response, operation_id="archiveRobot"
)
def archive_robot(robot_id: RobotId, service: Service):
    service.archive_robot(robot_id)
    return Response(status_code=204)


@router.post(
    "/robots/{robot_id}/versions",
    status_code=201,
    response_model=VersionOut,
    operation_id="createRobotVersion",
)
def create_robot_version(robot_id: RobotId, data: VersionCreate, service: Service):
    data_in = VersionCreateInput(
        base_version_id=data.base_version_id,
        note=data.note,
        status=data.status,
        parts={
            slot_id: PartInput(component_id=part.component_id, quantity=part.quantity)
            for slot_id, part in data.parts.items()
        },
    )
    return service.create_version(robot_id, data_in)
