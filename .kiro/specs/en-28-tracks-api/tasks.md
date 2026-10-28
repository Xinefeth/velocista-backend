# Implementation Plan — EN-28 · Tracks API (backend)

## Overview

Status (2026-10-28): tasks 1–6 and 7.1/7.3a are **implemented and verified locally** on branch
`feat/EN-28-tracks-api` (uncommitted, as ordered). Verification: full suite against the local
PostgreSQL (`127.0.0.1:15432`) = **540 passed, 15 skipped, 0 failed**; `ruff check` clean; the live
opt-in test passed against a temporary LOCAL server (never against Render). Still `[ ]`: task 0 (the
PO has not answered; the spec's recommendations were used as assumptions, marked "assumption pending
the PO" in code, OpenAPI and docs), task 7.2 (deploy to Render, not done) and the optional tasks.
`*` marks optional tasks.

Every sub-task lists the criteria it covers with explicit numbers (no ranges); the traceability matrix
at the end maps all 49 criteria to tasks.

## Tasks

- [ ] 0. Decisions before coding (PO and frontend)
  - [ ] 0.1 Answer Open questions 1–7 and the contract gaps (id type, `gap`, naming of units); the `start.edge` rule is already agreed with the frontend
  - [ ] 0.2 Confirm the limits (points 2–500, zones 0–100, board 50–2000 cm, radius 0–200 cm, coordinates ±10000 cm, zone width/height ≤ 2000 cm, names ≤ 80, length ≤ 100000 cm) and the "`closed` needs ≥ 3 points" rule
  - _Requirements: 2.1, 2.2, 2.4, 2.10, 2.11, 2.13, 5.5_

- [x] 1. Domain
  - [x] 1.1 Entities `Point`, `Zone`, `Board`, `Start`, `Track` — `src/velocista/domain/tracks/entities.py` _Requirements: 1.7_
  - [x] 1.2 Limits constants and `validate_track` with stable reasons — `src/velocista/domain/tracks/validation.py` _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.8, 2.10, 2.11, 2.12, 2.13, 6.2_
  - [x] 1.3 Unit tests of every limit, finite numbers, coordinates, zone size and name, `closed` with 2 points and the start-edge rule for open and closed polylines — `tests/unit/domain/tracks/test_track_validation.py` _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.10, 2.11, 2.12, 2.13, 8.1_
  - _Requirements: 1.7, 2.1, 2.2, 2.3, 2.4, 2.5, 2.8, 2.10, 2.11, 2.12, 2.13, 6.2, 8.1_

- [x] 2. Application
  - [x] 2.1 `TracksRepository` port — `src/velocista/application/tracks/ports.py` _Requirements: 1.2, 2.6_
  - [x] 2.2 `TracksService` (list, get, create/import, update, delete, export); stores `length_cm` as received, never recomputed; raises `NotFound`/`Validation` — `src/velocista/application/tracks/use_cases.py` _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 2.6, 2.9, 3.2, 4.1, 4.2, 4.3, 6.2_
  - [x] 2.3 Transport objects — `src/velocista/application/tracks/dto.py` _Requirements: 1.7, 3.1_
  - [x] 2.4 Use-case tests with an in-memory repository double (including unknown profile, import of an exported object) — `tests/unit/application/tracks/test_tracks_service.py` _Requirements: 1.6, 2.6, 4.2, 4.3, 8.1_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.6, 2.9, 3.1, 3.2, 4.1, 4.2, 4.3, 6.2, 8.1_

- [x] 3. Persistence
  - [x] 3.1 `TrackModel` with `CHECK` constraints (scalars, array lengths) and FK to `profile` — `src/velocista/infrastructure/persistence/models/tracks.py` (register in `models/__init__.py`) _Requirements: 2.8, 3.1, 7.2_
  - [x] 3.2 Migration `0006` creating `track` (downgrade refuses with rows) — `src/velocista/infrastructure/persistence/migrations/versions/0006_tracks.py` _Requirements: 7.1, 7.2, 7.3_
  - [x] 3.3 `SqlAlchemyTracksRepository` (order `updated_at DESC, id DESC`, limit/offset, `profile_exists`) — `src/velocista/infrastructure/persistence/repositories/tracks_repository.py` _Requirements: 1.2, 1.7, 2.6_
  - [x] 3.4 Repository integration tests on PostgreSQL (CRUD, `CHECK`s, FK, order, pagination) — `tests/integration/persistence/test_tracks_repository.py` _Requirements: 1.2, 1.7, 8.2_
  - [x] 3.5 Migration up/down test — `tests/integration/persistence/test_tracks_migration.py` (how existing tests run Alembic is not verified) _Requirements: 7.3, 8.4_
  - _Requirements: 1.2, 1.7, 2.6, 2.8, 3.1, 7.1, 7.2, 7.3, 8.2, 8.4_

- [x] 4. Track rules in profiles
  - [x] 4.1 Data migration `0007` inserting `lgr2026` and `libre` with `rules.track` (lengths in cm), downgrade removing only them — `src/velocista/infrastructure/persistence/migrations/versions/0007_track_profiles.py` _Requirements: 5.1, 5.3, 5.5, 7.4_
  - [x] 4.2 Test that `GET /api/profiles` returns `rules.track` unchanged, that the four existing profiles have no `track` block and are otherwise unchanged — `tests/integration/rest/rules/test_profiles_api.py` _Requirements: 5.2, 5.4, 8.2_
  - [x] 4.3 Document the `track` block (units, shape) and that profile deletion does not apply (read-only API) in the profile OpenAPI description — `src/velocista/interface/rest/rules/router.py` _Requirements: 5.5, 5.6, 6.5, 6.7_
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.5, 6.7, 7.4, 8.2_

- [x] 5. REST interface
  - [x] 5.1 Pydantic schemas (strict, finite numbers, bounds from the domain, read-only fields ignored on input, raw prototype format rejected) — `src/velocista/interface/rest/tracks/schemas.py` _Requirements: 1.7, 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 2.8, 2.10, 2.11, 2.12, 3.1, 4.4, 6.6_
  - [x] 5.2 Router with the six routes, operation ids `listTracks`, `getTrack`, `createTrack`, `updateTrack`, `deleteTrack`, `exportTrack`, documentation, examples and error responses; export with `Content-Disposition` — `src/velocista/interface/rest/tracks/router.py` _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 4.1, 6.2, 6.3, 6.4_
  - [x] 5.3 `get_tracks_service` in the composition root — `src/velocista/composition.py` _Requirements: 1.1_
  - [x] 5.4 Register the router and the `tracks` OpenAPI tag — `src/velocista/main.py` _Requirements: 6.3, 6.4_
  - [x] 5.5 Route tests (201/200/204/404/422, 401 with `AUTH_REQUIRED`, import of an exported file ignoring `id`/`created_at`/`updated_at`, rejection of the raw prototype format, `length_cm` stored as sent and returned on every read and update, export header) — `tests/integration/rest/tracks/test_tracks_api.py` _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.7, 2.9, 3.1, 3.2, 4.1, 4.2, 4.4, 6.1, 8.2_
  - [x] 5.6 Contract tests: the six operations exist with their operation ids, summary, description, example and error responses; error body format — `tests/contract/rest/` (extend the existing files) _Requirements: 6.2, 6.3, 6.4, 8.3_
  - [x] 5.7 Error-shape tests: a parsing error returns the list `detail` with `loc`/`type`/`msg`; an unknown `profile_id` returns 422 `track_profile_unknown` on `POST` and `PUT`; a domain error returns the object `detail` — `tests/integration/rest/tracks/test_tracks_errors.py` _Requirements: 2.6, 6.2, 6.6, 8.2_
  - [x] 5.8 OpenAPI units: field descriptions state centimetres (`length_cm`, `board`, `points`, `zones`) and the profile description states the `rules.track` units (cm, mm, degrees) — `src/velocista/interface/rest/tracks/schemas.py`, `src/velocista/interface/rest/rules/router.py`, checked in `tests/contract/rest/test_tracks_openapi_units.py` _Requirements: 3.3, 6.5, 8.3_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.6, 2.7, 2.9, 3.1, 3.2, 3.3, 4.1, 4.2, 4.4, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 8.2, 8.3_

- [x] 6. Live opt-in test
  - [x] 6.1 `TRACKS_LIVE_TEST=1` test against the deployed API: login (credentials from environment variables), create, read, export, delete its own track — `tests/integration/test_tracks_live.py` _Requirements: 8.5_
  - _Requirements: 8.5_

- [ ] 7. Closure
  - [x] 7.1 Full suite plus `ruff check` and `ruff format --check` green locally (database up) _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [ ] 7.2 Deploy: the start-up applies `0006` and `0007` on Render; verify with a read-only query that `track` exists and `profile` has 6 rows _Requirements: 7.1, 7.4_
  - [x] 7.3a Update `docs/CONTRACT.md` with the track fields, limits, error shapes and profile track rules — `docs/CONTRACT.md` _Requirements: 6.5_
  - [ ] 7.3b Update the `testing-strategy` and `data-model-persistence` specs with the new counts (540 passed / 15 skipped; `track` table; head `0007`; 20 tables in `public`)
  - _Requirements: 6.5, 7.1, 7.4, 8.1, 8.2, 8.3, 8.4_

- [ ]* 8. Optional
  - [ ]* 8.1 Plausibility check: reject `length_cm` above the polyline length plus a tolerance — `src/velocista/domain/tracks/validation.py`
  - [ ]* 8.2 Port the geometry (arcs, length, crossings) to Python and verify `length_cm` exactly
  - [ ]* 8.3 `If-Match`/`updated_at` check on `PUT` against lost updates
  - [ ]* 8.4 List filters (`profile_id`, `q` by name)
  - [ ]* 8.5 Editable profiles (`POST/PUT/DELETE /api/profiles` with validation of the `track` block; 409 `profile_in_use` on delete) — separate story (Open question 4)
  - [ ]* 8.6 Versioned export envelope (`{"format": "velocista-track", "version": 1, ...}`) (Open question 6)
  - _Requirements: 2.9, 4.1, 5.6, 6.7_

## Traceability matrix (criterion → tasks)

| Req | Criterion | Tasks |
|---|---|---|
| 1 | 1.1 create | 2.2, 2.4, 5.2, 5.3, 5.5 |
| 1 | 1.2 list | 2.1, 3.3, 3.4, 5.2, 5.5 |
| 1 | 1.3 get | 2.2, 5.2, 5.5 |
| 1 | 1.4 update | 2.2, 5.2, 5.5 |
| 1 | 1.5 delete | 2.2, 5.2, 5.5 |
| 1 | 1.6 404 `track_not_found` | 2.2, 2.4, 5.2, 5.5 |
| 1 | 1.7 stored unchanged | 1.1, 2.3, 3.3, 3.4, 5.1, 5.5 |
| 2 | 2.1 name | 1.2, 1.3, 5.1 |
| 2 | 2.2 counts, board, radius | 1.2, 1.3, 5.1 |
| 2 | 2.3 finite numbers | 1.2, 1.3, 5.1 |
| 2 | 2.4 `length_cm` bounds | 1.2, 1.3, 5.1 |
| 2 | 2.5 `start` | 1.2, 1.3, 5.1 |
| 2 | 2.6 unknown `profile_id` | 2.1, 2.2, 2.4, 3.3, 5.7 |
| 2 | 2.7 unknown fields / read-only fields | 5.1, 5.5 |
| 2 | 2.8 limits defined once | 1.2, 3.1, 5.1 |
| 2 | 2.9 no geometry recompute | 2.2, 5.5 (optional 8.1, 8.2) |
| 2 | 2.10 coordinates | 1.2, 1.3, 5.1 |
| 2 | 2.11 zone size and name | 1.2, 1.3, 5.1 |
| 2 | 2.12 `start.edge` range | 1.2, 1.3, 5.1 |
| 2 | 2.13 `closed` needs 3 points | 1.2, 1.3 |
| 3 | 3.1 `length_cm` stored and returned | 2.3, 3.1, 5.1, 5.5 |
| 3 | 3.2 replaced on update | 2.2, 5.5 |
| 3 | 3.3 unit stated | 5.8 |
| 4 | 4.1 export | 2.2, 5.2, 5.5 |
| 4 | 4.2 import | 2.2, 2.4, 5.5 |
| 4 | 4.3 same validation | 2.2, 2.4 |
| 4 | 4.4 raw prototype format rejected | 5.1, 5.5 |
| 5 | 5.1 `track` block | 4.1 |
| 5 | 5.2 returned unchanged | 4.2 |
| 5 | 5.3 seed `lgr2026`, `libre` | 4.1 |
| 5 | 5.4 profiles without block | 4.2 |
| 5 | 5.5 units documented | 4.1, 4.3 |
| 5 | 5.6 profile API read-only | 4.3 (optional 8.5) |
| 6 | 6.1 JWT | 5.5 |
| 6 | 6.2 domain errors and body | 1.2, 2.2, 5.2, 5.6, 5.7 |
| 6 | 6.3 OpenAPI documentation | 5.2, 5.4, 5.6 |
| 6 | 6.4 operation ids | 5.2, 5.4, 5.6 |
| 6 | 6.5 units in OpenAPI | 4.3, 5.8, 7.3 |
| 6 | 6.6 two 422 shapes | 5.1, 5.7 |
| 6 | 6.7 profile delete not applicable | 4.3 (optional 8.5) |
| 7 | 7.1 new revision `0006` | 3.2, 7.2 |
| 7 | 7.2 `CHECK`s and FK | 3.1, 3.2 |
| 7 | 7.3 downgrade refuses with rows | 3.2, 3.5 |
| 7 | 7.4 seed is a separate migration | 4.1, 7.2 |
| 8 | 8.1 unit tests | 1.3, 2.4, 7.1 |
| 8 | 8.2 integration tests | 3.4, 4.2, 5.5, 5.7, 7.1 |
| 8 | 8.3 contract tests | 5.6, 5.8, 7.1 |
| 8 | 8.4 migration test | 3.5, 7.1 |
| 8 | 8.5 live opt-in test | 6.1 |

## Notes

- Sources read: `C:\Users\Usuario\Desktop\ANALISIS_EN-28_trazador_de_pistas.md` and the prototype's pure
  logic (`Proyecto_Taller\trazador-de-pistas.html`, rule catalog, profiles `lgr2026`/`libre`, document
  shape). The LGR numbers were not checked against the official rulebook.
- Not verified: the frontend's tolerance for profiles without robot rules, the exact way the current
  tests exercise Alembic, and whether Render needs a manual step for the data migration.
- Order: 0 → (1, 3.1–3.2) → 2 → 3.3–3.5 → 4 → 5 → 6 → 7.

## Implementation results and spec/reality notes (2026-10-28)

- **Tests added:** 71 unit (`tests/unit/domain/tracks`, `tests/unit/application/tracks`), repository and
  constraints (`tests/integration/persistence/test_tracks_repository.py`), migrations
  (`.../test_tracks_migration.py`), routes and errors (`tests/integration/rest/tracks/`), contract and
  units (`tests/contract/rest/test_tracks_openapi_units.py`, `test_openapi_contract.py`), profiles
  (`tests/integration/rest/rules/test_profiles_api.py`) and the live opt-in test
  (`tests/integration/test_tracks_live.py`, skipped unless `TRACKS_LIVE_TEST=1`).
- **Full suite:** 540 passed, 15 skipped (the 14 previous skips plus the new tracks live test), 0
  failed. `ruff check`: clean. `ruff format --check`: 2 files still unformatted, both pre-existing
  (`velocista_sim/client.py`, `tests/test_sim_integration.py`).
- **Bug found by the tests (spec vs reality):** a body with `NaN`/`Infinity` made FastAPI's default 422
  handler fail to serialise the offending `input` and answered **500** instead of 422 (requirement 2.3).
  Fixed with a `RequestValidationError` handler in `src/velocista/interface/rest/errors.py` that keeps
  the FastAPI list format and only replaces non-finite `input` values by the strings `"NaN"`,
  `"Infinity"`, `"-Infinity"`. It is shared code: it applies to every endpoint, changing only a case
  that used to crash.
- **Existing test changed:** `tests/integration/test_external_persistence.py` asserted head `0005`; it
  now asserts `0007`.
- **Name of 81 characters:** the database rejects it with `DataError` (`varchar(80)`) before the
  `CHECK`; the REST layer already answers 422 earlier.
- **Not verified:** deployment (Render) and its start-up migration; the frontend's tolerance for
  profiles without robot rules; behaviour under concurrent writers (last write wins, by design).
- **Local database:** the dev database `127.0.0.1:15432` was upgraded to revision `0007` (20 tables in
  `public`, profiles `club`, `lgr2026`, `libre`, `mr4a`, `mr4m`, `mr4s`). Render was never touched.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "0.2"] },
    { "id": 1, "tasks": ["1.1", "1.2", "3.1", "3.2"] },
    { "id": 2, "tasks": ["1.3", "2.1", "2.3", "3.3"] },
    { "id": 3, "tasks": ["2.2", "2.4", "3.4", "3.5", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "5.1", "5.3"] },
    { "id": 5, "tasks": ["5.2", "5.4"] },
    { "id": 6, "tasks": ["5.5", "5.6", "5.7", "5.8", "6.1"] },
    { "id": 7, "tasks": ["7.1", "7.2", "7.3"] }
  ]
}
```
