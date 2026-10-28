"""Controlador REST del contexto `tracks`. Solo recibe, valida formato y delega en el servicio."""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import JSONResponse

from velocista.application.tracks.use_cases import TracksService
from velocista.composition import get_tracks_service
from velocista.interface.rest.errors import error_responses
from velocista.interface.rest.tracks.schemas import TrackIn, TrackOut, TracksPage

router = APIRouter(prefix="/api/tracks", tags=["tracks"])
Service = Annotated[TracksService, Depends(get_tracks_service)]
TrackId = Annotated[int, Path(ge=1, le=9007199254740991)]

UNAUTHORIZED = "Missing, expired or tampered token (`unauthorized`)"
NOT_FOUND = "Track does not exist (`track_not_found`)"
INVALID = (
    "Invalid body. Parsing errors use the FastAPI list format; domain rules and an unknown "
    "`profile_id` (`track_profile_unknown`) use `{detail: {reason, detail}}`"
)
UNITS = (
    "All distances are in centimetres (`length_cm`, `board`, `points`, `zones`). Limits are "
    "assumptions pending the PO."
)


def _slug(name: str, track_id: int) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:60]
    return slug or f"track-{track_id}"


@router.get(
    "",
    response_model=TracksPage,
    operation_id="listTracks",
    summary="List tracks",
    description=(
        "Lists the saved tracks, most recently edited first. Paginated with `limit` "
        "(1-200, default 50) and `offset` (default 0). " + UNITS
    ),
    responses=error_responses({401: UNAUTHORIZED}),
)
def list_tracks(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=9007199254740991)] = 0,
):
    page = service.list_tracks(limit=limit, offset=offset)
    return TracksPage(
        items=[TrackOut.from_entity(t) for t in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "",
    status_code=201,
    response_model=TrackOut,
    operation_id="createTrack",
    summary="Create or import a track",
    description=(
        "Creates a track. It is also the import path: an exported track can be posted again and "
        "creates a new track (`id`, `created_at` and `updated_at` are ignored). The backend does "
        "not recompute the geometry: `length_cm` is stored as sent. `start` defaults to "
        "`{edge: 0, t: 0.5}`; `profile_id` is optional. " + UNITS
    ),
    responses=error_responses({401: UNAUTHORIZED, 422: INVALID}),
)
def create_track(data: TrackIn, service: Service):
    return TrackOut.from_entity(service.create_track(data.to_entity()))


@router.get(
    "/{track_id}",
    response_model=TrackOut,
    operation_id="getTrack",
    summary="Get a track",
    description="Returns one track with all its fields. " + UNITS,
    responses=error_responses({401: UNAUTHORIZED, 404: NOT_FOUND}),
)
def get_track(track_id: TrackId, service: Service):
    return TrackOut.from_entity(service.get_track(track_id))


@router.put(
    "/{track_id}",
    response_model=TrackOut,
    operation_id="updateTrack",
    summary="Replace a track",
    description=(
        "Replaces every editable field of the track; `id` and `created_at` are kept and "
        "`updated_at` is refreshed. The last write wins (no concurrency control; assumption "
        "pending the PO). " + UNITS
    ),
    responses=error_responses({401: UNAUTHORIZED, 404: NOT_FOUND, 422: INVALID}),
)
def update_track(track_id: TrackId, data: TrackIn, service: Service):
    return TrackOut.from_entity(service.update_track(track_id, data.to_entity()))


@router.delete(
    "/{track_id}",
    status_code=204,
    operation_id="deleteTrack",
    summary="Delete a track",
    description="Deletes the track permanently and answers 204 with no body.",
    responses=error_responses({401: UNAUTHORIZED, 404: NOT_FOUND}),
)
def delete_track(track_id: TrackId, service: Service):
    service.delete_track(track_id)
    return Response(status_code=204)


@router.get(
    "/{track_id}/export",
    response_model=TrackOut,
    operation_id="exportTrack",
    summary="Export a track as JSON",
    description=(
        "Downloads the track as a JSON file (`Content-Disposition: attachment`). The body is the "
        "same object as `GET /api/tracks/{track_id}` with no version wrapper (assumption pending "
        "the PO). " + UNITS
    ),
    responses=error_responses({401: UNAUTHORIZED, 404: NOT_FOUND}),
)
def export_track(track_id: TrackId, service: Service):
    track = service.export_track(track_id)
    return JSONResponse(
        content=TrackOut.from_entity(track).model_dump(mode="json"),
        headers={
            "Content-Disposition": f'attachment; filename="{_slug(track.name, track_id)}.json"'
        },
    )
