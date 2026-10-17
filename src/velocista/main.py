"""Punto de entrada de la API: crea la app, registra middleware, manejadores y routers."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from velocista.infrastructure.config.settings import settings
from velocista.infrastructure.persistence.db import db_available
from velocista.infrastructure.realtime.registry import device_status
from velocista.interface.rest.auth.middleware import require_authentication
from velocista.interface.rest.auth.router import router as auth_router
from velocista.interface.rest.builder.router import router as builder_router
from velocista.interface.rest.catalog.router import router as catalog_router
from velocista.interface.rest.config.router import router as config_router
from velocista.interface.rest.devices.router import router as devices_router
from velocista.interface.rest.errors import error_responses, register_error_handlers
from velocista.interface.rest.events.router import router as events_router
from velocista.interface.rest.middleware import configure_logging, register_request_logging
from velocista.interface.rest.optimization.router import router as optimization_router
from velocista.interface.rest.rules.router import router as rules_router
from velocista.interface.rest.runs.router import router as runs_router
from velocista.interface.websocket.gateway import router as websocket_router

# Routers de cada contexto. Se van sumando a medida que se portan desde el backend anterior.
MODULE_ROUTERS = [
    catalog_router,
    builder_router,
    config_router,
    events_router,
    auth_router,
    rules_router,
    optimization_router,
    runs_router,
    devices_router,
    websocket_router,
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    from velocista.infrastructure.ingestion.recorder import handle_message
    from velocista.infrastructure.realtime.registry import hub

    previous = hub.message_handler
    hub.message_handler = handle_message
    simulator = None
    if settings.sim_enabled:
        from velocista.infrastructure.integrations.velocista_sim.client import SimulatorClient
        from velocista.infrastructure.integrations.velocista_sim.persistence import Store

        simulator = SimulatorClient(settings, Store(settings), hub)
        hub.simulator = simulator
        app.state.simulator = simulator
        await simulator.start()
    try:
        yield
    finally:
        if simulator:
            await simulator.close()
        hub.simulator = None
        await hub.close_relays()
        hub.message_handler = previous


API_DESCRIPTION = """
REST API of the **APAEC Lab** platform: catalog and inventory, robot builder and versions,
controller setups, run history, competition rules and live robot control.

**Conventions**
- Base path `/api`. JSON field names are English `snake_case`.
- Lists are paginated with `limit` and `offset` and return `{items, total, limit, offset}`.
- Business errors use `{"detail": {"reason": "<stable_code>", "detail": "<readable text>"}}`.
  Validation errors (HTTP 422 from request parsing) use the FastAPI format.
- When the server runs with `AUTH_REQUIRED=true`, send `Authorization: Bearer <token>`
  (get it from `POST /api/auth/login`). `GET /api/health` is always public.
- Commands to the robot are asynchronous: the API answers HTTP 202 with a `seq`, and the
  device confirmation arrives through the console WebSocket `/ws/console` as an `ack`.
"""

OPENAPI_TAGS = [
    {"name": "health", "description": "Service status."},
    {"name": "auth", "description": "Login and token check."},
    {"name": "catalog", "description": "Component types, components and the club inventory."},
    {"name": "builder", "description": "Robots, slots and immutable robot versions."},
    {
        "name": "optimization",
        "description": "Controllers, setups (saved parameter sets) and presets.",
    },
    {"name": "runs", "description": "Run history, laps, notes and ingestion from the simulator."},
    {"name": "rules", "description": "Competition rule profiles."},
    {"name": "events", "description": "System log."},
    {"name": "control", "description": "Operating mode and line color of a robot."},
    {"name": "devices", "description": "Robot/timer manifest and raw device commands."},
]


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    app = FastAPI(
        title="velocista-backend",
        version="0.1.0",
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.middleware("http")(require_authentication)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_request_logging(app)
    register_error_handlers(app)

    @app.get(
        "/api/health",
        tags=["health"],
        operation_id="getHealth",
        summary="Check API, database and device status",
        description=(
            "Public endpoint (no token needed). Reports whether the API is up, "
            "whether PostgreSQL is reachable, the environment name and whether the "
            "robot and the timer are connected over WebSocket."
        ),
        responses=error_responses(
            {503: "Database is unreachable; the body still lists the status of each part"},
            plain=[503],
        ),
    )
    def health(response: Response) -> dict:
        """Salud de la API, la base de datos y los dispositivos conectados."""
        available = db_available()
        if not available:
            response.status_code = 503
        return {
            "api": "ok",
            "database": "ok" if available else "disconnected",
            "environment": settings.app_env,
            "devices": device_status(),  # {robot, timer}
        }

    @app.get(
        "/api/simulator",
        tags=["devices"],
        operation_id="getSimulatorStatus",
        summary="Get the external simulator connection status",
        description=(
            "Returns a snapshot of the connection with the external Velocista simulator. "
            "When the simulator integration is not enabled the body is "
            '`{"state": "disabled"}`.'
        ),
        responses=error_responses({401: "Missing, expired or tampered token (`unauthorized`)"}),
    )
    def simulator_status():
        from velocista.infrastructure.realtime.registry import hub

        return hub.simulator.snapshot() if hub.simulator else {"state": "disabled"}

    for router in MODULE_ROUTERS:
        app.include_router(router)

    return app


app = create_app()
