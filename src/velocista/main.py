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
from velocista.interface.rest.errors import register_error_handlers
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


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    app = FastAPI(title="velocista-backend", version="0.1.0", lifespan=lifespan)
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

    @app.get("/api/health", tags=["health"], operation_id="getHealth")
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

    @app.get("/api/simulator", tags=["devices"], operation_id="getSimulatorStatus")
    def simulator_status():
        from velocista.infrastructure.realtime.registry import hub

        return hub.simulator.snapshot() if hub.simulator else {"state": "disabled"}

    for router in MODULE_ROUTERS:
        app.include_router(router)

    return app


app = create_app()
