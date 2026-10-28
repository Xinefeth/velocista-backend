from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel
from sqlalchemy.orm import Session

from velocista.application.rules.use_cases import RulesService
from velocista.infrastructure.persistence.db import get_session
from velocista.infrastructure.persistence.repositories.rules_repository import (
    SqlAlchemyRulesRepository,
)
from velocista.interface.rest.errors import error_responses


class ProfileOut(BaseModel):
    id: str
    competition: str
    label: str
    category: str
    rules: dict[str, Any]


def get_service(session: Annotated[Session, Depends(get_session)]):
    return RulesService(SqlAlchemyRulesRepository(session))


router = APIRouter(prefix="/api/profiles", tags=["rules"])


@router.get(
    "",
    response_model=list[ProfileOut],
    operation_id="listProfiles",
    summary="List rule profiles",
    description=(
        "Returns the competition profiles (for example Muchik Rumble 4 Senior) "
        "with their rules stored as data (HU-10). A profile may carry track rules in "
        "`rules.track` (EN-28): `line_width_mm` in millimetres, `gap_length_cm` in centimetres "
        "and 13 rules shaped `{enabled, value}`; every length rule (`radius_min`, "
        "`separation_min`, `margin`, `zone_distance`, `length_min`, `length_max`, "
        "`straight_min`, `straight_max`) is in centimetres, `angle_min` in degrees, `cross_max` "
        "and `gap_max` are counts, `no_sharp` and `closed` are booleans. Profiles without a "
        "`track` block define no track rules. The profile API is read-only."
    ),
)
def list_profiles(service: Annotated[RulesService, Depends(get_service)]):
    return service.list_profiles()


@router.get(
    "/{profile_id}",
    response_model=ProfileOut,
    operation_id="getProfile",
    summary="Get a rule profile",
    description=(
        "Returns one profile with its rules, including `rules.track` when present "
        "(lengths in centimetres, `angle_min` in degrees, `line_width_mm` in millimetres)."
    ),
    responses=error_responses({404: "Profile does not exist"}),
)
def get_profile(
    profile_id: Annotated[str, Path(min_length=1, max_length=40)],
    service: Annotated[RulesService, Depends(get_service)],
):
    return service.get_profile(profile_id)
