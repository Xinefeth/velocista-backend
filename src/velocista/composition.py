"""Composition root: construye los servicios de aplicación con sus implementaciones concretas.

Único sitio donde se eligen los adaptadores (repositorios SQLAlchemy, providers, actividad) y
se inyectan en los servicios. Los routers piden su servicio con estas dependencias de FastAPI.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from velocista.application.builder.use_cases import BuilderService
from velocista.application.catalog.use_cases import CatalogService
from velocista.application.config.ports import ConfigRepository, DeviceGateway
from velocista.infrastructure.persistence.db import get_session
from velocista.infrastructure.persistence.repositories.builder_repository import (
    SqlAlchemyBuilderRepository,
)
from velocista.infrastructure.persistence.repositories.catalog_repository import (
    CatalogComponentProvider,
    SqlAlchemyCatalogRepository,
)
from velocista.infrastructure.persistence.repositories.config_repository import (
    SqlAlchemyConfigRepository,
)
from velocista.infrastructure.realtime.device_gateway import RealtimeDeviceGateway
from velocista.infrastructure.realtime.robot_activity import RealtimeRobotActivity

DbSession = Annotated[Session, Depends(get_session)]


def get_catalog_service(session: DbSession) -> CatalogService:
    return CatalogService(SqlAlchemyCatalogRepository(session))


def get_builder_service(session: DbSession) -> BuilderService:
    repo = SqlAlchemyBuilderRepository(
        session,
        components=CatalogComponentProvider(session),
        activity=RealtimeRobotActivity(session),
    )
    return BuilderService(repo)


def get_config_repository(session: DbSession) -> ConfigRepository:
    return SqlAlchemyConfigRepository(session)


def get_device_gateway(session: DbSession) -> DeviceGateway:
    return RealtimeDeviceGateway(session)
