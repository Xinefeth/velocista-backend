from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel
from sqlalchemy.orm import Session

from velocista.application.rules.use_cases import RulesService
from velocista.infrastructure.persistence.db import get_session
from velocista.infrastructure.persistence.repositories.rules_repository import (
    SqlAlchemyRulesRepository,
)


class ProfileOut(BaseModel):
    id: str
    competition: str
    label: str
    category: str
    rules: dict[str, Any]


def get_service(session: Annotated[Session, Depends(get_session)]):
    return RulesService(SqlAlchemyRulesRepository(session))


router = APIRouter(prefix="/api/profiles", tags=["rules"])


@router.get("", response_model=list[ProfileOut], operation_id="listProfiles")
def list_profiles(service: Annotated[RulesService, Depends(get_service)]):
    return service.list_profiles()


@router.get("/{profile_id}", response_model=ProfileOut, operation_id="getProfile")
def get_profile(
    profile_id: Annotated[str, Path(min_length=1, max_length=40)],
    service: Annotated[RulesService, Depends(get_service)],
):
    return service.get_profile(profile_id)
