import hmac
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response
from sqlalchemy.orm import Session

from velocista.application.runs.history import RunHistoryService
from velocista.infrastructure.config.settings import settings
from velocista.infrastructure.persistence.db import get_session
from velocista.infrastructure.persistence.repositories.run_history_repository import (
    SqlAlchemyRunHistoryRepository,
)
from velocista.infrastructure.persistence.repositories.simulation_ingestion_repository import (
    SimulationIngestionRepository,
)
from velocista.interface.rest.errors import error_responses
from velocista.interface.rest.runs.schemas import (
    LapsPage,
    RunIngestion,
    RunNote,
    RunOut,
    RunsPage,
)


def get_service(session: Annotated[Session, Depends(get_session)]):
    return RunHistoryService(SqlAlchemyRunHistoryRepository(session))


Service = Annotated[RunHistoryService, Depends(get_service)]
Database = Annotated[Session, Depends(get_session)]
RunId = Annotated[int, Path(ge=1, le=9007199254740991)]
router = APIRouter(prefix="/api/runs", tags=["runs"])


def require_simulation_service(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.simulation_service_token
    if not expected:
        raise HTTPException(status_code=503, detail="Simulation ingestion is not configured")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Simulation service token is invalid")


SimulationService = Annotated[None, Depends(require_simulation_service)]


@router.get(
    "",
    response_model=RunsPage,
    operation_id="listRuns",
    summary="List run history",
    description=(
        "Lists closed runs, newest first, each with its score `j` (best finished "
        "lap: time + 2 x accumulated error; 120 when no lap finished). Paginated "
        "with `limit` (1-200, default 50) and `offset` (default 0). Filters: "
        "`robot_id`, `version_id`, `controller_id` and `source` (`sim` or "
        "`robot`)."
    ),
)
def list_runs(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    robot_id: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    version_id: Annotated[int | None, Query(ge=1)] = None,
    controller_id: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    source: Literal["sim", "robot"] | None = None,
):
    return service.list_runs(
        limit=limit,
        offset=offset,
        robot_id=robot_id,
        version_id=version_id,
        controller_id=controller_id,
        source=source,
    )


@router.post(
    "/ingest",
    response_model=RunOut,
    operation_id="ingestSimulationRun",
    summary="Ingest a run from the simulation service",
    description=(
        "Used only by the separate simulation service. Authenticate with "
        "`Authorization: Bearer <SIMULATION_SERVICE_TOKEN>`. Idempotent by "
        "`external_run_id`: the first call returns 201; repeating the identical "
        "payload returns 200 with header `Idempotent-Replay: true` and the same "
        "run; reusing the id with different data is rejected."
    ),
    responses=error_responses(
        {
            401: "Missing or wrong service token",
            404: "Robot, version, setup or profile does not exist or does not match",
            409: (
                "Same `external_run_id` with different data (`external_run_conflict`) or "
                "archived robot (`robot_archived`)"
            ),
            503: "Ingestion is not configured on this server",
        },
        plain=[401, 503],
    ),
)
def ingest_simulation_run(
    data: RunIngestion,
    response: Response,
    session: Database,
    _: SimulationService,
):
    run, created = SimulationIngestionRepository(session).ingest(data)
    response.status_code = 201 if created else 200
    if not created:
        response.headers["Idempotent-Replay"] = "true"
    return run


@router.post(
    "/simulated",
    response_model=RunOut,
    status_code=201,
    operation_id="createSimulatedRun",
    summary="Generate a simulated run",
    description=(
        "Creates a closed run with random laps for a robot, using its current "
        "version and a `Simulation` setup. It is marked `source=sim` and is meant "
        "for demos and for filling the history."
    ),
    responses=error_responses(
        {
            404: "Robot does not exist (`robot_not_found`)",
            409: (
                "Robot has no current version (`no_current_version`) or already has an "
                "active run (`robot_running`)"
            ),
        }
    ),
)
def create_simulated_run(
    service: Service, robot_id: Annotated[str, Query(min_length=1, max_length=40)]
):
    if settings.sim_enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "Use robot commands to run the external simulator; synthetic generation is disabled"
            ),
        )
    return service.simulate(robot_id)


@router.get(
    "/{run_id}",
    response_model=RunOut,
    operation_id="getRun",
    summary="Get a run",
    description=(
        "Returns the summary of a closed run: the controller and parameters it "
        "used, the best lap and its score `j`."
    ),
    responses=error_responses(
        {404: "Run does not exist", 409: "Run is still active or has no laps"}
    ),
)
def get_run(run_id: RunId, service: Service):
    return service.get_run(run_id)


@router.patch(
    "/{run_id}",
    response_model=RunOut,
    operation_id="annotateRun",
    summary="Add a note to a run",
    description="Replaces the free-text note of the run (max 1000 characters).",
    responses=error_responses({404: "Run does not exist"}),
)
def annotate_run(run_id: RunId, data: RunNote, service: Service):
    return service.annotate(run_id, data.note)


@router.get(
    "/{run_id}/laps",
    response_model=LapsPage,
    operation_id="listRunLaps",
    summary="List the laps of a run",
    description=(
        "Returns every lap with its sector times and segments (straights, "
        "curves). Paginated with `limit` (1-200, default 50) and `offset` "
        "(default 0)."
    ),
    responses=error_responses({404: "Run does not exist"}),
)
def list_run_laps(
    run_id: RunId,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list_laps(run_id, limit, offset)
