"""Controlador REST del contexto `catalog`. Solo recibe, valida formato y delega en el servicio."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from velocista.application.catalog.use_cases import CatalogService
from velocista.composition import get_catalog_service
from velocista.interface.rest.catalog.schemas import (
    ComponentCreate,
    ComponentEdit,
    ComponentOut,
    ComponentsPage,
    ComponentTypeOut,
    InventoryOut,
    InventoryPage,
    InventoryUpdate,
    TypeId,
)

router = APIRouter(prefix="/api", tags=["catalog"])
Service = Annotated[CatalogService, Depends(get_catalog_service)]
ComponentId = Annotated[str, Path(min_length=1, max_length=40)]


@router.get("/inventory", response_model=InventoryPage, operation_id="listInventory")
def list_inventory(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=9007199254740991)] = 0,
):
    return service.list_inventory(limit=limit, offset=offset)


@router.put(
    "/inventory/{component_id}", response_model=InventoryOut, operation_id="updateInventory"
)
def update_inventory(component_id: ComponentId, data: InventoryUpdate, service: Service):
    return service.update_inventory(component_id, data)


@router.post(
    "/components", status_code=201, response_model=ComponentOut, operation_id="createComponent"
)
def create_component(data: ComponentCreate, service: Service):
    return service.create_component(data)


@router.get("/components/{component_id}", response_model=ComponentOut, operation_id="getComponent")
def get_component(component_id: ComponentId, service: Service):
    return service.get_component(component_id)


@router.patch(
    "/components/{component_id}", response_model=ComponentOut, operation_id="updateComponent"
)
def update_component(component_id: ComponentId, data: ComponentEdit, service: Service):
    return service.edit_component(component_id, data)


@router.delete(
    "/components/{component_id}",
    status_code=204,
    response_class=Response,
    operation_id="archiveComponent",
)
def archive_component(component_id: ComponentId, service: Service):
    service.archive_component(component_id)
    return Response(status_code=204)


@router.get(
    "/component-types",
    response_model=list[ComponentTypeOut],
    response_model_exclude_none=True,
    operation_id="listComponentTypes",
)
def list_component_types(service: Service):
    return service.list_component_types()


@router.get("/components", response_model=ComponentsPage, operation_id="listComponents")
def list_components(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=9007199254740991)] = 0,
    q: Annotated[str | None, Query(max_length=120)] = None,
    type_id: Annotated[TypeId | None, Query()] = None,
):
    return service.list_components(limit=limit, offset=offset, q=q, type_id=type_id)
