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
from velocista.interface.rest.errors import error_responses

router = APIRouter(prefix="/api", tags=["catalog"])
Service = Annotated[CatalogService, Depends(get_catalog_service)]
ComponentId = Annotated[str, Path(min_length=1, max_length=40)]


@router.get(
    "/inventory",
    response_model=InventoryPage,
    operation_id="listInventory",
    summary="List the club inventory",
    description=(
        "For every component returns the stock owned by the club, how many units "
        "are used by current robot versions (`in_robots`), the units still "
        "`available`, the `shortage` and the row `revision` used for concurrency "
        "control. Paginated with `limit` (1-200, default 50) and `offset` "
        "(default 0)."
    ),
)
def list_inventory(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=9007199254740991)] = 0,
):
    return service.list_inventory(limit=limit, offset=offset)


@router.put(
    "/inventory/{component_id}",
    response_model=InventoryOut,
    operation_id="updateInventory",
    summary="Set the stock of a component",
    description=(
        "Sets the number of units owned by the club. Uses optimistic concurrency: "
        "send the `revision` you last read; if someone else changed the stock "
        "meanwhile the request is rejected and you must reload."
    ),
    responses=error_responses(
        {
            404: "Inventory row does not exist (`inventory_not_found`)",
            409: "Stale `revision` or revision limit reached (`revision_exhausted`)",
            422: "Negative stock",
        }
    ),
)
def update_inventory(component_id: ComponentId, data: InventoryUpdate, service: Service):
    return service.update_inventory(component_id, data)


@router.post(
    "/components",
    status_code=201,
    response_model=ComponentOut,
    operation_id="createComponent",
    summary="Register a component",
    description=(
        "Adds a component to the club catalog (HU-02). `specs` must contain "
        "exactly the fields declared by the component type. `price` must be "
        "greater than 0 and `mass_g` zero or more. `stock` is the number of units "
        "the club owns."
    ),
    responses=error_responses(
        {
            422: (
                "Invalid or missing spec (`invalid_spec`), type not loaded "
                "(`type_unavailable`) or `current_a` different from `specs.i` "
                "(`inconsistent_current`)"
            )
        }
    ),
)
def create_component(data: ComponentCreate, service: Service):
    return service.create_component(data)


@router.get(
    "/components/{component_id}",
    response_model=ComponentOut,
    operation_id="getComponent",
    summary="Get a component",
    description=("Returns one component by id, including its specs, stock and archived flag."),
    responses=error_responses({404: "Component does not exist (`component_not_found`)"}),
)
def get_component(component_id: ComponentId, service: Service):
    return service.get_component(component_id)


@router.patch(
    "/components/{component_id}",
    response_model=ComponentOut,
    operation_id="updateComponent",
    summary="Edit a component",
    description=(
        "Partial update: only the fields sent are changed. Robot versions that "
        "already used this component keep their own snapshot and are not "
        "affected."
    ),
    responses=error_responses(
        {
            404: "Component does not exist (`component_not_found`)",
            409: "Component is archived (`component_archived`)",
            422: "Invalid spec values",
        }
    ),
)
def update_component(component_id: ComponentId, data: ComponentEdit, service: Service):
    return service.edit_component(component_id, data)


@router.delete(
    "/components/{component_id}",
    status_code=204,
    response_class=Response,
    operation_id="archiveComponent",
    summary="Archive a component",
    description=(
        "Soft delete: the component disappears from the catalog list but stays in "
        "the version snapshots that used it. Returns no body."
    ),
    responses=error_responses({404: "Component does not exist (`component_not_found`)"}),
)
def archive_component(component_id: ComponentId, service: Service):
    service.archive_component(component_id)
    return Response(status_code=204)


@router.get(
    "/component-types",
    response_model=list[ComponentTypeOut],
    response_model_exclude_none=True,
    operation_id="listComponentTypes",
    summary="List component types",
    description=(
        "Returns the catalog of component types (microcontroller, sensor strip, "
        "motor...) with their color, the spec fields each type requires and the "
        "console capabilities it adds."
    ),
)
def list_component_types(service: Service):
    return service.list_component_types()


@router.get(
    "/components",
    response_model=ComponentsPage,
    operation_id="listComponents",
    summary="List components",
    description=(
        "Lists catalog components ordered by name. Paginated with `limit` (1-200, "
        "default 50) and `offset` (default 0). Optional filters: `q` (text "
        "search) and `type_id` (component type). Archived components are hidden."
    ),
)
def list_components(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=9007199254740991)] = 0,
    q: Annotated[str | None, Query(max_length=120)] = None,
    type_id: Annotated[TypeId | None, Query()] = None,
):
    return service.list_components(limit=limit, offset=offset, q=q, type_id=type_id)
