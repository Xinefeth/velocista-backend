# Requirements Document — Testing Strategy

## Introduction

This spec defines how `velocista-backend` is tested and records what exists today. The suite is
organised by test type (unit, integration, contract, e2e) over a real PostgreSQL in an isolated
schema, plus the simulator-contract tests. Numbers below come from `pytest --collect-only` and from
partial runs executed on 2026-10-28; the database-backed part could **not** be run in that session
because the local PostgreSQL (Docker, port 15432) was down.

## Glossary

- **Pirámide de pruebas**: Reparto de pruebas por tipo: muchas unitarias, menos integración, pocas e2e.
- **Unitaria (unit)**: Prueba de dominio o caso de uso con dobles en memoria, sin I/O.
- **Integración (integration)**: Prueba de repositorios SQL o endpoints REST contra PostgreSQL real.
- **Contrato (contract)**: Prueba que protege la forma de REST y WebSocket acordada con la consola.
- **E2E**: Recorrido completo de operador o robot.
- **Esquema temporal**: Esquema `qa_<uuid>` creado dentro de una transacción y revertido al terminar cada prueba.
- **Fixtures del contrato del simulador**: JSON válidos e inválidos en `tests/fixtures/sim_contract/{valid,invalid}`, tomados de `velocista-sim`.
- **Plantilla de formato**: Prueba marcada `@pytest.mark.skip(reason="plantilla de formato")`.

## Requirements

### Requirement 1: Pirámide por tipo

**User Story:** As a developer, I want tests grouped by type, so that I can run the fast ones often and
the database-backed ones before merging.

#### Acceptance Criteria

1. THE suite SHALL keep tests under `tests/unit`, `tests/integration`, `tests/contract` and `tests/e2e`, plus `tests/test_ws_engine.py` and `tests/test_sim_integration.py`.
2. WHEN only `tests/unit`, `tests/contract` and `tests/test_ws_engine.py` are selected, THE suite SHALL run without a database.
3. THE unit tests SHALL use test doubles that implement the application *ports*, not mocks of SQLAlchemy.

### Requirement 2: Base de datos real y aislada

**User Story:** As a developer, I want integration tests on real PostgreSQL that leave no data behind, so
that SQL behaviour is verified without contaminating development data.

#### Acceptance Criteria

1. WHEN an integration or e2e test requests the `db`/`client` fixture, THE suite SHALL create a schema `qa_<uuid>` inside a transaction and roll it back at the end.
2. THE suite SHALL connect through the same `engine` as the application, built from `settings.database_url`.
3. IF `DATABASE_URL` is defined in the environment, THEN THE suite SHALL be considered unsafe to run, because the engine would connect to that database; a guard SHOULD abort the run.
4. WHEN the local database is not reachable, THE database-backed tests SHALL fail or hang rather than pass silently; the developer SHALL start it with `docker compose up -d db`.

### Requirement 3: Contrato del simulador y de la API

**User Story:** As a console developer, I want contract tests to fail first when a message or endpoint
changes shape, so that the frontend is protected.

#### Acceptance Criteria

1. THE contract tests SHALL validate the OpenAPI document, the error format and the WS message catalog.
2. THE simulator integration tests SHALL validate valid and invalid frames against the JSON Schemas in `infrastructure/integrations/velocista_sim/schemas`.
3. WHEN a simulator frame violates the contract, THE client SHALL reject it and the test SHALL assert the rejection.

### Requirement 4: Calidad estática

**User Story:** As a reviewer, I want lint and format checks to be green, so that diffs stay readable.

#### Acceptance Criteria

1. THE repository SHALL pass `ruff check` (line length 100; rules E, F, I, UP, B).
2. THE repository SHOULD pass `ruff format --check`.

### Requirement 5: Transparencia sobre lo omitido y lo no medido

**User Story:** As a lead, I want skipped tests and missing measurements to be explicit, so that green
does not hide gaps.

#### Acceptance Criteria

1. THE test plan SHALL list every skipped test with its reason.
2. WHERE no coverage tool is installed, THE spec SHALL state that coverage is not measured.
3. THE test README SHALL report counts that match the real suite.
