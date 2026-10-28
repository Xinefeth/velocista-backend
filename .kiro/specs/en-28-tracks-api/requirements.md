# Requirements Document — EN-28 · Tracks API (backend)

## Introduction

EN-28 integrates the track drawing tool (`trazador-de-pistas.html`, a standalone prototype) into the
console. This spec covers only the **backend** side: persisting tracks in PostgreSQL, a REST API to
create, list, read, update, delete, import and export them, the track length stored per track, and
rule profiles that carry **track rules**. The frontend writes its own spec against the same API
contract. Nothing described here is implemented yet; the status of the repository was verified on
2026-10-28 (branch `feat/ingesta-velocista`, migration head `0005`).

The API contract below was proposed by the orchestrator and is kept as given. Problems found in it are
listed as **Open questions** at the end instead of being changed.

## Glossary

- **Pista (Track)**: Trazado de línea de un velocista sobre un tablero; una poligonal de control con radio por vértice.
- **Tablero (board)**: Rectángulo de la pista, con ancho y alto en cm.
- **Punto (point)**: Vértice de la poligonal: `x`, `y`, `radius` (cm; 0 = esquina viva) y `gap` (corte de línea en el tramo que sale del vértice).
- **Zona (zone)**: Rectángulo prohibido o marcado en el tablero (`x`, `y`, `width`, `height`, `name`).
- **Salida (start)**: Posición de arranque: índice de tramo `edge` y posición relativa `t` en `[0, 1]`.
- **Largo total (length_cm)**: Largo de la línea en una vuelta, en cm, calculado por el **frontend** y guardado por el backend.
- **Perfil (profile)**: Fila de `profile` con `id`, `competition`, `label`, `category` y `rules` JSONB (HU-10).
- **Reglas de pista (track rules)**: Bloque `track` dentro de `profile.rules` con el ancho de línea, el largo de corte y 13 reglas `{enabled, value}`.
- **Importar / exportar**: Crear una pista desde un JSON ya mapeado al contrato / descargar una pista como JSON.
- **Dominio / Aplicación / Infraestructura / Interfaz**: Capas de Clean Architecture (ver `.kiro/specs/architecture`).
- **PO**: Product Owner, dueño de las decisiones abiertas.

## Verified current state (2026-10-28)

- Contexts with REST routers: `auth`, `builder`, `catalog`, `config`, `events`, `optimization`, `rules`, `runs` (+ devices). There is **no** `tracks` context, table, model or router.
- 19 tables (migrations `0001`–`0005`); head `0005`. No `track` table.
- `profile` (`models/rules.py`): `id String(40)` PK, `competition String(120)`, `label String(40)`, `category String(120)`, `rules JSONB` with `CHECK (jsonb_typeof(rules) = 'object')`. The REST API is **read-only**: `GET /api/profiles` and `GET /api/profiles/{profile_id}` (`interface/rest/rules/router.py`); `ProfileOut.rules` is an untyped `dict`.
- Seeded profiles (migration `0003`): `club`, `mr4a`, `mr4m`, `mr4s`; their `rules` hold **robot** rules (`dimensions_mm`, `max_sensors`, `allowed_mcus`, …) and no track geometry.
- `run.profile_id` references `profile.id` with `ON DELETE RESTRICT`.
- Pagination shape already used (`RunsPage`): `{items, total, limit, offset}`, `limit` 1–200 (default 50).
- Business errors: `{"detail": {"reason", "detail"}}`; `Validation`→422, `NotFound`→404, `Conflict`→409; request-parsing errors use the FastAPI 422 format.
- `AUTH_REQUIRED` middleware protects every `/api/*` path except `/api/health`, `/api/auth/login`, `/api/runs/ingest`; `/api/tracks` would be protected automatically.
- There is **no** custom handler for request-validation errors: Pydantic/FastAPI 422s use FastAPI's default list format. Only domain errors, `IntegrityError` (409 `conflict`), `OperationalError` (503) and unhandled errors use `{"detail": {"reason", "detail"}}`. An existing test (`tests/integration/test_extended_rest.py`) already reads `loc` and `type` from that list.
- No code in `src/` reads robot rule keys (`dimensions_mm`, `max_sensors`, `allowed_mcus`: grep found none), so profiles without robot rules do not break backend code (frontend impact not verified).

## Requirements

### Requirement 1: Persist and manage tracks

**User Story:** As a pilot, I want to save, list, open, edit and delete my tracks in the system, so that
they survive the browser and are shared across consoles.

#### Acceptance Criteria

1. WHEN the Consola sends `POST /api/tracks` with a valid body, THE API SHALL create the track, assign an `id`, `created_at` and `updated_at`, and answer 201 with the stored track.
2. WHEN the Consola requests `GET /api/tracks`, THE API SHALL return `{items, total, limit, offset}` ordered by `updated_at` descending, with `limit` 1–200 (default 50) and `offset` ≥ 0.
3. WHEN the Consola requests `GET /api/tracks/{id}` for an existing track, THE API SHALL return all track fields.
4. WHEN the Consola sends `PUT /api/tracks/{id}` with a valid body, THE API SHALL replace the editable fields, keep `id` and `created_at`, and refresh `updated_at`.
5. WHEN the Consola sends `DELETE /api/tracks/{id}` for an existing track, THE API SHALL delete it and answer 204.
6. IF a track id does not exist, THEN THE API SHALL answer 404 with reason `track_not_found` for `GET`, `PUT`, `DELETE` and `export`.
7. THE API SHALL store `points`, `zones`, `board`, `closed`, `start`, `profile_id` and `length_cm` exactly as validated, without changing numeric values.

### Requirement 2: Validation at the boundary and in the domain

**User Story:** As a maintainer, I want invalid or hostile payloads rejected, so that the database holds
only sane tracks.

#### Acceptance Criteria

1. THE API SHALL accept `name` of 1–80 characters (after trimming) and reject empty or longer names with 422.
2. THE API SHALL accept 2–500 `points`, 0–100 `zones`, a `board` of 50–2000 cm per side and `radius` of 0–200 cm; any value outside SHALL be rejected with 422.
3. THE API SHALL reject any non-finite number (`NaN`, `Infinity`) anywhere in the body.
4. THE API SHALL accept `length_cm` only when `0 < length_cm <= 100000`.
5. WHEN `start` is given, THE API SHALL require `0 <= t <= 1` and `edge` to be a valid edge index (see 2.12).
6. WHEN `profile_id` is not null and no such profile exists, THE API SHALL answer HTTP 422 with the business-error body `{"detail": {"reason": "track_profile_unknown", "detail": "Profile does not exist"}}` for both `POST` and `PUT` (a reference inside the body is a validation problem, not a missing URL resource, so it is not 404).
7. THE API SHALL reject unknown fields in the body, except the read-only fields `id`, `created_at` and `updated_at`, which it SHALL ignore (see requirement 4).
8. THE limits SHALL be defined once, in the domain layer, and be reused by the REST schemas; THE database `CHECK` constraints SHALL repeat the scalar limits and the array lengths (per-element limits such as coordinates, radius and zone sizes are enforced only by the domain and the schemas).
9. THE API SHALL NOT recompute the track geometry; it SHALL trust `length_cm` within the stated bounds (decision recorded in `design.md`).
10. THE API SHALL accept `points[].x` and `points[].y` (and `zones[].x`, `zones[].y`) only when finite and `|value| <= 10000` cm. Points MAY lie outside the board, because the `margin` rule is meant to detect that. _Proposed value, pending the PO._
11. THE API SHALL accept `zones[].width` and `zones[].height` only when `0 < value <= 2000` cm, and `zones[].name` of 0–80 characters (default empty). _Proposed values, pending the PO._
12. THE API SHALL accept `start.edge` only as an integer in `0..(points − 1)` when `closed` is true and in `0..(points − 2)` when `closed` is false, and `start.t` in `[0, 1]`.
13. IF `closed` is true and there are fewer than 3 points, THEN THE API SHALL answer 422 with reason `track_closed_needs_three_points`. _Proposed: the prototype's `build()` treats a polyline with fewer than 3 points as open even when `closed` is set, so the combination is ambiguous; confirm with the frontend._

### Requirement 3: Largo total guardado por pista

**User Story:** As a user of later stories (HU-30, HU-35), I want each track to expose its total length,
so that I can use it as a reference.

#### Acceptance Criteria

1. THE API SHALL store `length_cm` on every track and return it in every read response.
2. WHEN a track is updated, THE API SHALL replace `length_cm` with the value sent.
3. THE unit of `length_cm` SHALL be centimetres and SHALL be stated in the OpenAPI description of the field.

### Requirement 4: Import and export JSON

**User Story:** As a pilot, I want to download a track as JSON and load it again, so that I can back it
up and share it.

#### Acceptance Criteria

1. WHEN the Consola requests `GET /api/tracks/{id}/export`, THE API SHALL return the track as JSON with `Content-Disposition: attachment; filename="<slug>.json"`.
2. WHEN the Consola posts an exported JSON to `POST /api/tracks`, THE API SHALL create a **new** track and SHALL ignore the `id`, `created_at` and `updated_at` it carries.
3. THE import path SHALL apply exactly the same validation as a normal create.
4. THE API SHALL NOT accept the prototype's raw format (`pts`, `board.w`, `board.h`, `start.e`); mapping is the frontend's job.

### Requirement 5: Profiles with track rules

**User Story:** As a pilot, I want the track checker to use the rule profiles of the console, so that
there is a single place to read rules.

#### Acceptance Criteria

1. THE profile `rules` JSONB SHALL carry an optional `track` block with `line_width_mm`, `gap_length_cm` and the 13 rules `radius_min`, `angle_min`, `no_sharp`, `separation_min`, `margin`, `zone_distance`, `closed`, `length_min`, `length_max`, `straight_min`, `straight_max`, `cross_max`, `gap_max`, each shaped `{enabled, value}`.
2. WHEN `GET /api/profiles` or `GET /api/profiles/{id}` is called, THE API SHALL return `rules.track` unchanged when present.
3. THE database SHALL seed the profiles `lgr2026` ("Let's Go Robot 2026") and `libre` ("Entrenamiento libre") with the prototype's values.
4. WHILE a profile has no `track` block (`club`, `mr4a`, `mr4s`, `mr4m`), THE API SHALL return it as it is, and the client SHALL treat the absence as "no track rules defined".
5. THE unit of every length rule SHALL be documented (centimetres) and `angle_min` SHALL be in degrees.
6. THE profile API SHALL remain read-only in this story (see Open question 4).

### Requirement 6: Security, errors and documentation

**User Story:** As an operator, I want the new routes to behave like the rest of the API.

#### Acceptance Criteria

1. WHILE `AUTH_REQUIRED` is true, THE API SHALL require a valid JWT on every `/api/tracks` route and answer 401 `unauthorized` otherwise.
2. THE API SHALL use the domain errors `Validation`, `NotFound` and `Conflict` and the standard body `{"detail": {"reason", "detail"}}`.
3. THE API SHALL document every operation in OpenAPI (operation id, summary, description, error responses and an example), as the existing contract tests require.
4. THE API SHALL expose operation ids `listTracks`, `getTrack`, `createTrack`, `updateTrack`, `deleteTrack` and `exportTrack`.
5. THE OpenAPI schemas SHALL state the units in the field descriptions: `length_cm` in centimetres; `board.width_cm` and `board.height_cm` in centimetres; `points[].x`, `y`, `radius` and `zones[].x`, `y`, `width`, `height` in centimetres; `start.t` as a fraction of the edge (0–1). THE profile OpenAPI description SHALL state that, in `rules.track`, every length rule (`radius_min`, `separation_min`, `margin`, `zone_distance`, `length_min`, `length_max`, `straight_min`, `straight_max`) and `gap_length_cm` are in centimetres, `line_width_mm` in millimetres and `angle_min` in degrees.
6. WHEN a request body fails Pydantic/FastAPI validation (wrong type, missing or unknown field, value out of the schema bounds), THE API SHALL answer HTTP 422 with the FastAPI format `{"detail": [ {"type", "loc", "msg", "input", ...} ]}` (a **list**), and SHALL NOT change that format. WHEN a domain rule fails, THE API SHALL answer the business-error format `{"detail": {"reason", "detail"}}` (an **object**). The exact shapes and reasons are listed in `design.md` §3.7.
7. THE profile API is read-only in this story, so deleting a profile that has tracks is **not applicable**; IF a delete is added later, THEN it SHALL answer 409 `profile_in_use` (and a database `RESTRICT` violation reaching the generic handler already yields 409 `conflict`).

### Requirement 7: Schema and migrations

**User Story:** As a maintainer, I want the schema versioned and reversible.

#### Acceptance Criteria

1. THE schema change SHALL be a new Alembic revision after `0005` that creates table `track`; no existing column SHALL change.
2. THE table SHALL enforce the limits with `CHECK` constraints and SHALL reference `profile(id)`.
3. WHEN the migration is downgraded and rows exist, THE downgrade SHALL refuse unless the tracks are exported first (same rule as `0005`).
4. THE profile seed SHALL be a data migration separate from the schema migration.

### Requirement 8: Tests

**User Story:** As a maintainer, I want the feature covered by every test type.

#### Acceptance Criteria

1. THE suite SHALL include unit tests of the domain validation and the use cases with an in-memory repository double.
2. THE suite SHALL include integration tests of the repository and the routes against real PostgreSQL in an isolated schema.
3. THE suite SHALL include REST contract tests (OpenAPI, error format) for the new routes.
4. THE suite SHALL include a test that upgrades and downgrades the migration.
5. WHERE `TRACKS_LIVE_TEST=1`, THE suite SHALL run an opt-in test against the deployed API that creates, reads and deletes its own track.

## Open questions (for the PO; not resolved here)

| # | Question | Recommendation |
|---|---|---|
| 1 | Which competition and track rules govern: Let's Go Robot 2026, Muchik Rumble 4 or another? | Use `lgr2026` as the default profile for new tracks. Leave MR4 profiles without a `track` block until the PO supplies values; no values are invented. The prototype's LGR numbers come from the prototype itself ("Libro de Reglas 2026") and were not checked against the rulebook |
| 2 | Unit of the total length (cm assumed; HU-30 and HU-35 will use it) | Centimetres everywhere. **Discrepancy:** the prototype's `lengthMin`/`lengthMax` rules are in **metres** (catalog unit `m`) while its length is in cm; the seed converts them to cm (×100) and the contract must say so |
| 3 | Is "SVG con cotas" a new export? (frontend work; no backend impact) | Clarify with the PO. The backend stores and serves no SVG |
| 4 | Does the tool's own editable profile disappear (the console's profile view is used instead)? | Yes for EN-28. The profile API is read-only today; if the PO wants editing, open a separate story with `POST/PUT/DELETE /api/profiles`, validation of the `track` block and handling of `ON DELETE RESTRICT` from `run` and `track` |
| 5 | Contract gaps found in the proposal (see below) | Decide with the frontend before implementing |
| 6 | Export shape: plain object or wrapper `{format, version, track}`? | The frontend accepts the plain object, the wrapper and the prototype's `v: 2` format on import. Recommend plain object now (as `GET /{id}`) and the wrapper only if the PO wants versioned files; the backend produces one shape only |
| 7 | `PUT` without concurrency control (last write wins)? | Accept last-write-wins for EN-28 (one admin account, single console in practice); add an `updated_at`/`If-Match` check later if several consoles edit the same track |

Decisions recorded (not questions):

- **Field-level errors are parsed by the frontend.** The frontend reads the FastAPI/Pydantic `detail` list (`loc`, `msg`); the backend keeps its format (requirement 6.6). The frontend must branch on `Array.isArray(detail)`.

Contract gaps found (raised, not changed):

1. **`id` type** is not stated; this spec assumes an integer (identity, like `run.id`) and path parameters `1..9007199254740991`.
2. **`start.edge`** is, in the prototype, a numeric edge index (`start: {e: 0, t: 0.35}`), not an edge name; this spec assumes an integer index, valid range in requirement 2.12 (agreed with the frontend spec).
3. **`points[].gap`** type is not stated; the prototype uses it as a truthy flag; this spec assumes boolean.
4. **Naming**: `board` uses `width_cm`/`height_cm` but `zones` use `width`/`height` (centimetres implied); confirm the unit in OpenAPI.
5. **Export shape**: this spec returns the same object as `GET /api/tracks/{id}` with a download header, no version wrapper. The prototype's format has `v: 2`; a wrapper such as `{"format": "velocista-track", "version": 1, "track": {...}}` would make future migrations safer.
6. **Re-importing an export** carries `id`, `created_at`, `updated_at`; this spec makes `POST` ignore them.
7. **Concurrency**: `PUT` replaces the whole track with no `If-Match`/version; two consoles can overwrite each other (optional task).
8. **Name uniqueness**: not required here (duplicates allowed); say so if the PO wants it unique.
