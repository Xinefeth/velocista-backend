# Requirements Document — Architecture (Clean Architecture)

## Introduction

`velocista-backend` is the API and gateway of the track system (robot velocista, cronómetro and
consola). It is organised with Clean Architecture: business rules live in a framework-free
`domain`, use cases in `application`, and every concrete technology (PostgreSQL, WebSocket, JWT,
environment) in `infrastructure` or `interface`. This spec records the architecture as it is
**verified in the code on 2026-10-28** (branch `feat/ingesta-velocista`, commit `a0fed7c`), including
the places where the code departs from `docs/ARCHITECTURE.md`. It does not change any code.

System context (not copied here): the high-level diagram is
`C:\Users\Usuario\Desktop\diagramas_arquitectura\figura1_arquitectura_alto_nivel.svg` and the
component description is `C:\Users\Usuario\Desktop\diagramas_arquitectura\3.1_descripcion_componentes.md`.

## Glossary

- **API**: El servicio `velocista-backend` (FastAPI) con sus routers REST y el gateway WebSocket.
- **Dominio (domain)**: Entidades y reglas de negocio puras (`src/velocista/domain`).
- **Aplicación (application)**: Casos de uso y *ports* (`src/velocista/application`).
- **Infraestructura (infrastructure)**: Adaptadores concretos: SQLAlchemy, Alembic, settings, tiempo real, integraciones.
- **Interfaz (interface)**: Entrega I/O: routers REST y gateway WebSocket.
- **Composition root**: `src/velocista/composition.py`, único sitio donde se eligen los adaptadores.
- **Contexto**: Vertical de negocio: `auth`, `builder` (armador), `catalog` (catálogo), `config`, `events`, `optimization`, `rules` (reglamento), `runs` (corridas).
- **Gateway**: `interface/websocket/gateway.py`; atiende `/ws/robot`, `/ws/timer` y `/ws/console`.
- **ACL**: Anti-corruption layer; traduce el vocabulario ES del firmware al contrato EN en la frontera.
- **Hub**: `Registry` singleton en `infrastructure/realtime/registry.py` con las conexiones vivas.
- **Simulador**: Servicio externo `velocista-sim` al que el backend se conecta como cliente.
- **Render**: Plataforma de despliegue (servicio web Docker + PostgreSQL, plan free).

## Requirements

### Requirement 1: Regla de dependencia

**User Story:** As a maintainer, I want dependencies to point inward, so that business rules can be
tested and changed without touching frameworks.

#### Acceptance Criteria

1. THE `domain` package SHALL NOT import FastAPI, Starlette, Pydantic, SQLAlchemy, Alembic or `websockets`.
2. THE `application` package SHALL NOT import from `infrastructure` or `interface`.
3. THE `domain` package SHALL NOT import from `application`.
4. WHEN a use case needs persistence or a device, THE `application` layer SHALL depend on a *port* declared in its own `ports.py`.
5. THE `infrastructure` package SHOULD NOT import from `interface`.
6. THE `interface` routers SHOULD obtain use cases through the composition root rather than instantiating repositories.

### Requirement 2: Composition root

**User Story:** As a maintainer, I want one place that wires adapters to use cases, so that swapping
an adapter or a test double is a single change.

#### Acceptance Criteria

1. THE composition root SHALL build `CatalogService`, `BuilderService`, the config repository and the device gateway with their concrete adapters.
2. WHEN a router needs a service wired in the composition root, THE router SHALL request it through the FastAPI dependency (`get_*_service`).
3. WHEN tests need a different adapter, THE test SHALL override the dependency (`dependency_overrides`) instead of patching SQLAlchemy.

### Requirement 3: Contextos de negocio

**User Story:** As a developer, I want each business context to have the same four-layer shape, so
that I can find code predictably.

#### Acceptance Criteria

1. THE API SHALL expose the contexts `auth`, `builder`, `catalog`, `config`, `events`, `optimization`, `rules` and `runs` as REST routers registered in `MODULE_ROUTERS` (`main.py`).
2. THE API SHALL expose a public `GET /api/health` that returns HTTP 503 when PostgreSQL is unreachable.
3. WHERE a context has business rules (`runs`, `optimization`, `config`, `events`), THE rules SHALL live in `domain/<context>`.
4. IF a context has no framework-free logic yet (`auth`), THEN THE context SHALL keep its logic out of `domain` and the gap SHALL be documented.

### Requirement 4: Gateway WebSocket como ACL

**User Story:** As a console developer, I want to always receive English message types and enums, so
that firmware vocabulary never leaks into the console.

#### Acceptance Criteria

1. WHEN a device sends a frame with the legacy key `tipo`, THE Gateway SHALL translate `type`, field names and enum values to English before validating, broadcasting and persisting.
2. THE Gateway SHALL leave channel keys (`data.channels`) untouched, because they are an open vocabulary declared by the manifest.
3. WHEN a device is not the robot manifest sender yet, THE Gateway SHALL drop non-manifest robot messages and emit a `no_manifest` event.
4. WHILE the external simulator source is enabled, THE Gateway SHALL reject connections to `/ws/robot` with code 1008.

### Requirement 5: Despliegue

**User Story:** As an operator, I want the service to start the same way locally and on Render, so
that migrations and the health check behave predictably.

#### Acceptance Criteria

1. WHEN the container starts, THE API SHALL run `alembic upgrade head` before accepting traffic (`infrastructure/startup.py`).
2. THE API SHALL run a single worker, because the Hub and the simulator session are in-process state.
3. WHERE `DATABASE_URL` is defined, THE API SHALL use it in preference to the `POSTGRES_*` variables and normalise the scheme to `postgresql+psycopg://`.
4. WHILE `APP_ENV=production`, THE API SHALL refuse to start without `AUTH_REQUIRED=true`, strong secrets and exact CORS origins.
5. THE Render service SHALL use `/api/health` as its health check.
