# Design Document — Architecture (Clean Architecture)

## Introduction

The backend is a single FastAPI process (≈7,500 lines of Python in `src/`) organised in four layers
plus a composition root. REST routers and the WebSocket gateway call application services; adapters
for PostgreSQL, the in-memory device Hub and the external simulator implement the ports. Everything
below was checked by reading the code and running import-rule greps on 2026-10-28; where the code
differs from `docs/ARCHITECTURE.md` it is listed under *Known deviations*.

## Goals & Non-Goals

**Goals**

- Keep `domain` and `application` free of frameworks so unit tests need no I/O.
- Wire concrete adapters in one place (`composition.py`).
- Translate firmware vocabulary at the WebSocket boundary (ACL).
- Deploy as one Docker web service plus one PostgreSQL on Render.

**Non-Goals**

- Splitting into microservices or running multiple workers (the Hub is in-process state).
- A durable message journal for telemetry (documented in `docs/SIMULATOR.md` as not provided).
- Changing the public REST or WS contract (see `ws-gateway-contract`).

## Architecture Overview

```
 Robot (ESP32)   Cronómetro        Consola (web)              velocista-sim (Railway)
     │ WS            │ WS              │ REST + WS                    ▲ WS (cliente saliente)
     ▼               ▼                 ▼                              │
┌──────────────────────────── interface ──────────────────────────────┼───────────┐
│  websocket/gateway.py  (/ws/robot /ws/timer /ws/console)            │           │
│  websocket/contract/   (envelope, catálogo, traducción ES→EN = ACL) │           │
│  rest/<context>/router.py + schemas.py  (+ auth/middleware.py)      │           │
└───────────────┬───────────────────────────────────────────────────────┼───────────┘
                │ calls                                                  │
┌───────────────▼────────────  application  ───────────────┐             │
│  <context>/use_cases.py   <context>/ports.py   dto.py      │             │
└───────────────▲───────────────────────────────────────────┘             │
                │ ports implemented by                                      │
┌───────────────┴────────────  infrastructure  ─────────────────────────────┴───┐
│ persistence/ (models, repositories, migrations)   realtime/ (Hub, gateways)     │
│ integrations/velocista_sim/ (client, persistence)  ingestion/recorder.py        │
│ config/settings.py   security.py (JWT)   startup.py (alembic + uvicorn)         │
└───────────────┬────────────────────────────────────────────────────────────────┘
                ▼
┌──────────────  domain (pure)  ──────────────┐        PostgreSQL 16 (Render)
│ builder catalog runs config events           │
│ optimization rules(shared) shared/errors     │        composition.py = wiring
└──────────────────────────────────────────────┘
```

Dependency direction: `domain ← application ← infrastructure / interface`. The diagram of the whole
system (devices, console, simulator, Render) is in `figura1_arquitectura_alto_nivel.svg`; its
component text is in `3.1_descripcion_componentes.md` (both under
`C:\Users\Usuario\Desktop\diagramas_arquitectura\`).

## Component Design

### 3.1 Layers (verified)

| Layer | Path | Verified fact |
|---|---|---|
| domain | `src/velocista/domain/<context>` | No imports of fastapi/sqlalchemy/starlette/pydantic/alembic/websockets (grep: none) |
| application | `src/velocista/application/<context>` | No imports of `infrastructure` or `interface` (grep: none); declares `ports.py` |
| infrastructure | `src/velocista/infrastructure` | persistence, realtime Hub, simulator client, JWT, settings, startup |
| interface | `src/velocista/interface` | REST routers per context, WS gateway and contract |
| wiring | `src/velocista/composition.py` | `get_catalog_service`, `get_builder_service`, `get_config_repository`, `get_device_gateway` |
| entry | `src/velocista/main.py` | `create_app()`, `lifespan` (starts `SimulatorClient` when `SIM_ENABLED`), `/api/health` |

### 3.2 Contexts

`auth`, `builder`, `catalog`, `config`, `events`, `optimization`, `rules`, `runs`. Each has a REST
router under `interface/rest/<context>/`. `domain/auth` and `application/auth` contain only
`__init__.py`: authentication lives in `infrastructure/security.py` (JWT) and
`interface/rest/auth/` (login, middleware).

### 3.3 Known deviations from `docs/ARCHITECTURE.md`

| # | Rule or statement | Reality in the code |
|---|---|---|
| 1 | `interface` invokes use cases | The `events`, `optimization`, `rules` and `runs` routers import `infrastructure.persistence` repositories and `get_session` directly |
| 2 | `infrastructure` does not know `interface` | `realtime/device_gateway.py` imports `interface.websocket.contract.*`; `realtime/registry.py` lazy-imports `translation` |
| 3 | Ingestion is "FUTURO; NO implementar en v1" | `infrastructure/ingestion/recorder.py` and `infrastructure/integrations/velocista_sim/` are implemented and wired in `main.lifespan` |
| 4 | `interface/websocket/commands.py` exists | It does not; device commands are in `interface/rest/devices/router.py` |
| 5 | Context `timer` | There is no `timer` context; the timer is a device over `/ws/timer` |
| 6 | "sin tests reales en v1" | The suite has 371 collected tests (see `testing-strategy`) |

### 3.4 Runtime and deployment

- `Dockerfile`: `python:3.12-slim`, installs with `requirements.lock`, runs as non-root `appuser`, `CMD python -m velocista.infrastructure.startup`.
- `startup.py`: `alembic upgrade head`, then `uvicorn` with `workers=1`, `proxy_headers=True`, port from `PORT`.
- `render.yaml`: web service `velocista-backend` (docker, plan free, 1 instance, health check `/api/health`) and database `velocista-db` (plan free, db `velocista`). It declares `APP_ENV`, `AUTH_REQUIRED`, `DATABASE_URL`, `CORS_ORIGINS`, `SECRET_KEY`, `ADMIN_*`, `DEVICE_TOKEN_*`, `SIMULATION_SERVICE_TOKEN`; it declares no `SIM_*` variable.

## Data Flow

### Device message

```
Robot ─WS─▶ gateway.serve (token) ─▶ process: parse ▶ translate (if "tipo") ▶ validate_data
          ▶ manifest/status/signals bookkeeping ▶ hub.message_handler (recorder, threadpool)
          ▶ ack ▶ hub.broadcast ─WS─▶ Consola
```

### REST call

```
Consola ─HTTP─▶ require_authentication (JWT if AUTH_REQUIRED) ▶ router ▶ service/repository ▶ PostgreSQL
```

## Design Decisions & Trade-offs

- **Single worker, in-process Hub.** Simplest way to keep device connections and the simulator
  session coherent. Trade-off: no horizontal scaling.
- **ACL at the WS boundary.** The firmware can keep Spanish `type`/enums; the console always sees
  English. Trade-off: the translation tables must be kept in sync with the contract.
- **`create_all` only for tests and bootstrap; Alembic in production.** `startup.py` always runs
  migrations.
- **Pragmatic deviations (known).** Some routers talk to repositories directly. This is recorded as
  debt in `tasks.md` rather than hidden.
