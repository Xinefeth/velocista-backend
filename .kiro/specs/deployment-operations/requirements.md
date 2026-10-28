# Requirements Document — Deployment and Operations

## Introduction

`velocista-backend` runs on Render as one Docker web service plus one PostgreSQL database, both on the
free plan, described by `render.yaml`. Locally it runs with `docker compose` (PostgreSQL on port
15432). On 2026-10-27 the free database filled its disk because the simulator telemetry was stored at
50 Hz without limits; this spec captures the deployment contract, the operating procedures and the
lessons from that incident.

## Glossary

- **Servicio web**: `velocista-backend` en Render (Docker, 1 instancia, plan free).
- **Base de datos**: `velocista-db`, PostgreSQL de Render (plan free, base `velocista`).
- **URL interna**: Cadena `DATABASE_URL` con host `dpg-…-a` sin sufijo; solo funciona dentro de la red de Render.
- **URL externa**: Cadena con host `dpg-…-a.<región>-postgres.render.com`; sirve desde fuera (pgAdmin, scripts).
- **Health check**: `GET /api/health`.
- **Runbook**: Procedimiento manual de operación (`docs/OPERATIONS.md`, hoy ausente del árbol de trabajo).
- **Disco lleno**: Error `No space left on device` de PostgreSQL.
- **Redeploy**: Nuevo despliegue tras cambiar código o variables de entorno.

## Requirements

### Requirement 1: Despliegue reproducible

**User Story:** As an operator, I want the same image and start-up everywhere, so that Render and local
behave alike.

#### Acceptance Criteria

1. THE service SHALL build from `Dockerfile` (`python:3.12-slim`, pinned by `requirements.lock`, non-root user).
2. WHEN the container starts, THE service SHALL run `alembic upgrade head` and then start one `uvicorn` worker on `$PORT`.
3. THE Render blueprint SHALL declare the web service, the database and their variables (`render.yaml`).
4. THE service SHALL read `DATABASE_URL` in preference to `POSTGRES_*` and normalise the driver scheme.

### Requirement 2: Salud y arranque

**User Story:** As an operator, I want Render to know whether the service is healthy.

#### Acceptance Criteria

1. THE Render health check SHALL be `GET /api/health`.
2. WHEN PostgreSQL is unreachable, THE health endpoint SHALL answer HTTP 503 and still report each part.
3. THE service SHALL run exactly one instance and one worker.

### Requirement 3: Configuración del simulador en Render

**User Story:** As an operator, I want the simulator and telemetry limits to be explicit in deployment.

#### Acceptance Criteria

1. WHERE the simulator integration is used, THE deployment SHALL define `SIM_ENABLED`, `SIM_INTERNAL_ROBOT_ID`, `SIM_SETUP_ID`, `SIM_PROFILE_ID` and the telemetry limits.
2. THE deployment SHOULD declare those variables in `render.yaml` or document the values set in the panel.
3. WHEN `APP_ENV=production`, THE service SHALL refuse to start with weak secrets (see `auth-security`).

### Requirement 4: Control del tamaño de la base

**User Story:** As an operator, I want to detect and prevent disk exhaustion before it blocks writes.

#### Acceptance Criteria

1. THE operations runbook SHALL provide read-only queries for database size, table sizes and row counts, and SHALL be versioned in the repository.
2. WHEN a cleanup deletes data, THE operator SHALL first confirm the target database and SHALL export rows worth keeping.
3. WHILE the disk is full, THE runbook SHALL use `DROP`/recreate for the offending table instead of `TRUNCATE` or `DELETE`, because `TRUNCATE` creates new relation files and `DELETE` writes WAL.
4. WHEN a table is dropped and recreated, THE operator SHALL recreate its exact constraints and indexes and SHALL verify them afterwards.
5. THE operations SHOULD include an alert or periodic check of database size.

### Requirement 5: Acceso administrativo seguro

**User Story:** As an owner, I want database access from my machine without leaking credentials.

#### Acceptance Criteria

1. WHEN connecting from outside Render, THE operator SHALL use the External Database URL, stored in a session environment variable (e.g. `RENDER_DB_URL`) and never pasted into chats or committed.
2. THE operator SHALL use read-only sessions for inspection and a separate, explicit confirmation for each write.
3. IF a credential is exposed, THEN THE operator SHALL reset the database password and update `DATABASE_URL` of the web service if needed.
4. THE operator SHALL NOT run the test suite with `DATABASE_URL` pointing to Render.
