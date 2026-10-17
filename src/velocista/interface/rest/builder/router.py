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
from velocista.interface.rest.errors import error_responses

router = APIRouter(prefix="/api", tags=["builder"])
Service = Annotated[BuilderService, Depends(get_builder_service)]
RobotId = Annotated[str, Path(min_length=1, max_length=40)]
VersionId = Annotated[int, Path(ge=1, le=9007199254740991)]


@router.post(
    "/robots",
    status_code=201,
    response_model=RobotOut,
    operation_id="createRobot",
    summary="Register a robot",
    description=(
        "Creates a robot without versions. `short_code` (max 12 characters) must "
        "be unique among robots. Add its parts afterwards with `POST "
        "/api/robots/{robot_id}/versions`."
    ),
    responses=error_responses(
        {409: "`short_code` already used", 422: "Invalid name, short code or type"}
    ),
)
def create_robot(data: RobotCreate, service: Service):
    robot = service.create_robot(
        name=data.name, short_code=data.short_code, type=data.type, firmware=data.firmware
    )
    return RobotOut.from_entity(robot)


@router.get(
    "/robots",
    response_model=RobotsPage,
    operation_id="listRobots",
    summary="List robots",
    description=(
        "Lists the robots of the club ordered by short code, with the id of their "
        "current version. Archived robots are hidden. Paginated with `limit` "
        "(1-200, default 50) and `offset` (default 0)."
    ),
)
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


@router.get(
    "/robots/{robot_id}",
    response_model=RobotOut,
    operation_id="getRobot",
    summary="Get a robot",
    description=(
        "Returns one robot by id, including its firmware and `current_version_id` "
        "(null while it has no version)."
    ),
    responses=error_responses({404: "Robot does not exist (`robot_not_found`)"}),
)
def get_robot(robot_id: RobotId, service: Service):
    return RobotOut.from_entity(service.get_robot(robot_id))


@router.get(
    "/robots/{robot_id}/versions",
    response_model=VersionsPage,
    operation_id="listRobotVersions",
    summary="List the versions of a robot",
    description=(
        "Returns the history of versions, oldest first, each with its status "
        "(`current`, `previous`, `draft`...). Paginated with `limit` (1-200, "
        "default 50) and `offset` (default 0)."
    ),
    responses=error_responses({404: "Robot does not exist (`robot_not_found`)"}),
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
    summary="Get one version of a robot",
    description=(
        "Returns a version with the list of parts. Each part carries a "
        "`component_snapshot`: the component data as it was when the version was "
        "saved."
    ),
    responses=error_responses(
        {
            404: (
                "Robot or version does not exist, or the version belongs to another robot "
                "(`version_not_found`)"
            )
        }
    ),
)
def get_robot_version(robot_id: RobotId, version_id: VersionId, service: Service):
    return service.get_version(robot_id, version_id)


@router.get(
    "/slots",
    response_model=list[SlotOut],
    operation_id="listSlots",
    summary="List the slots of a robot",
    description=(
        "Returns the fixed slots a robot is built from (MCU, motors, battery...) "
        "with the component type each slot accepts, and whether it is required or "
        "editable."
    ),
)
def list_slots(service: Service):
    return service.list_slots()


@router.patch(
    "/robots/{robot_id}",
    response_model=RobotOut,
    operation_id="updateRobot",
    summary="Edit a robot",
    description="Partial update of name, short code or firmware.",
    responses=error_responses(
        {
            404: "Robot does not exist (`robot_not_found`)",
            409: "Robot is archived (`robot_archived`) or the short code is already used",
            422: "Invalid values",
        }
    ),
)
def update_robot(robot_id: RobotId, data: RobotEdit, service: Service):
    changes = data.model_dump(exclude_unset=True)
    return RobotOut.from_entity(service.update_robot(robot_id, changes))


@router.delete(
    "/robots/{robot_id}",
    status_code=204,
    response_class=Response,
    operation_id="archiveRobot",
    summary="Archive a robot",
    description=(
        "Soft delete. An archived robot disappears from the list, cannot be "
        "edited and cannot receive runs. Returns no body."
    ),
    responses=error_responses(
        {
            404: "Robot does not exist (`robot_not_found`)",
            409: "Robot has an active run (`run_in_progress`)",
        }
    ),
)
def archive_robot(robot_id: RobotId, service: Service):
    service.archive_robot(robot_id)
    return Response(status_code=204)


@router.post(
    "/robots/{robot_id}/versions",
    status_code=201,
    response_model=VersionOut,
    operation_id="createRobotVersion",
    summary="Save a new version of a robot",
    description=(
        "Creates an immutable version with the chosen parts (HU-06). "
        "`base_version_id` must be the robot's current version id (or null for "
        "the first one); otherwise the save is rejected so two people cannot "
        "overwrite each other. A `current` version needs every required slot. "
        "Saving a new `current` version turns the previous one into `previous`."
    ),
    responses=error_responses(
        {
            404: "Robot does not exist (`robot_not_found`)",
            409: (
                "Stale base version (`version_stale`), archived robot (`robot_archived`) "
                "or active run (`run_in_progress`)"
            ),
            422: (
                "Missing required slots (`required_slots_missing`), unknown slot, "
                "incompatible component type or invalid quantity"
            ),
        }
    ),
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
