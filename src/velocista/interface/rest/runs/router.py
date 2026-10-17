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


@router.get("", response_model=RunsPage, operation_id="listRuns")
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


@router.post("/ingest", response_model=RunOut, operation_id="ingestSimulationRun")
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
    "/simulated", response_model=RunOut, status_code=201, operation_id="createSimulatedRun"
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


@router.get("/{run_id}", response_model=RunOut, operation_id="getRun")
def get_run(run_id: RunId, service: Service):
    return service.get_run(run_id)


@router.patch("/{run_id}", response_model=RunOut, operation_id="annotateRun")
def annotate_run(run_id: RunId, data: RunNote, service: Service):
    return service.annotate(run_id, data.note)


@router.get("/{run_id}/laps", response_model=LapsPage, operation_id="listRunLaps")
def list_run_laps(
    run_id: RunId,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list_laps(run_id, limit, offset)
