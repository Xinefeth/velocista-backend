# Design Document — EN-28 · Tracks API (backend)

## Introduction

A new `tracks` context is added following the existing four-layer pattern: framework-free rules in
`domain/tracks`, use cases and ports in `application/tracks`, a SQLAlchemy model and repository in
`infrastructure/persistence`, and REST routes in `interface/rest/tracks`. The REST layer is wired
through `composition.py` (like `builder` and `catalog`), not by instantiating the repository in the
router (which the `rules` router does today and which `.kiro/specs/architecture` records as a
deviation). The track geometry stays in the frontend: the backend validates limits and stores the
`length_cm` the client computed. Profiles gain a `track` block in their JSONB `rules`; no profile
column changes.

Nothing here is implemented; every task in `tasks.md` is open.

## Goals & Non-Goals

**Goals**

- Persist tracks with a single, validated, documented REST API (CRUD, import, export).
- Store `length_cm` per track.
- Serve track rules through the existing profile API with a data-only change.
- Reuse the current stack (Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3, pytest, JWT); no new dependency.

**Non-Goals**

- Computing track geometry (arcs, crossings, length) in Python — optional future task.
- Editing profiles (`POST/PUT/DELETE /api/profiles`) — Open question 4.
- SVG/PNG generation or "SVG con cotas" — frontend.
- Per-user ownership or sharing: the system has one admin account.
- Versioned/optimistic-locking updates — optional.

## Architecture Overview

```
Consola (frontend)                       velocista-backend
   │ JWT                                  ┌────────────────────────────────────────────────────┐
   │ GET/POST/PUT/DELETE /api/tracks      │ interface/rest/tracks   router.py · schemas.py      │
   │ GET /api/tracks/{id}/export          │    │ Depends(get_tracks_service)  (composition.py)  │
   │ GET /api/profiles (rules.track)      │    ▼                                                │
   ▼                                      │ application/tracks   ports.py · use_cases.py · dto  │
 require_authentication (middleware)      │    │ TracksRepository (Protocol)                    │
   ──────────────────────────────────────▶│    ▼                                                │
                                          │ domain/tracks  entities.py · validation.py          │
                                          │    (limits, finite numbers, start-edge rule)        │
                                          │ infrastructure/persistence                          │
                                          │    models/tracks.py · repositories/tracks_repository│
                                          │    migrations 0006_tracks · 0007_track_profiles     │
                                          └──────────────────────────┬─────────────────────────┘
                                                                     ▼
                                       PostgreSQL: track (new) · profile (rules.track added by seed)
```

Dependency direction: `domain ← application ← infrastructure / interface` (limits live in the domain
and are imported by the schemas; the database `CHECK`s repeat them as defence in depth).

## Component Design

### 3.1 API contract (as proposed; gaps in `requirements.md`)

| Method | Path | operation id | Result |
|---|---|---|---|
| GET | `/api/tracks` | `listTracks` | 200 `{items, total, limit, offset}` |
| GET | `/api/tracks/{id}` | `getTrack` | 200 track · 404 `track_not_found` |
| POST | `/api/tracks` | `createTrack` | 201 track · 422 |
| PUT | `/api/tracks/{id}` | `updateTrack` | 200 track · 404 · 422 |
| DELETE | `/api/tracks/{id}` | `deleteTrack` | 204 · 404 |
| GET | `/api/tracks/{id}/export` | `exportTrack` | 200 JSON + `Content-Disposition` |
| GET | `/api/profiles`, `/api/profiles/{id}` | `listProfiles`, `getProfile` | existing; now also `rules.track` |

Track JSON (snake_case, English):

```json
{
  "id": 1, "name": "Técnica 3 × 2,5",
  "board": {"width_cm": 300, "height_cm": 250},
  "closed": true,
  "points": [{"x": 10, "y": 20, "radius": 15, "gap": false}],
  "zones": [{"x": 104, "y": 0, "width": 12, "height": 12, "name": "poste del cronómetro"}],
  "start": {"edge": 0, "t": 0.35},
  "profile_id": "lgr2026",
  "length_cm": 812.4,
  "created_at": "2026-10-28T15:00:00Z", "updated_at": "2026-10-28T15:00:00Z"
}
```

Mapping from the prototype (done by the frontend, listed so both specs agree): `pts→points`,
`pts[].r→radius`, `pts[].g→gap`, `board.w/h→board.width_cm/height_cm`, `zones[].w/h→width/height`,
`start.e→start.edge`, `build(doc).L→length_cm`.

### 3.2 Domain (`domain/tracks`)

- `entities.py`: frozen dataclasses `Point`, `Zone`, `Board`, `Start`, `Track` (no framework).
- `validation.py`: constants `MAX_POINTS=500`, `MIN_POINTS=2`, `MAX_ZONES=100`, `BOARD_MIN_CM=50`,
  `BOARD_MAX_CM=2000`, `RADIUS_MAX_CM=200`, `COORD_MAX_CM=10000`, `ZONE_SIZE_MAX_CM=2000`,
  `ZONE_NAME_MAX=80`, `NAME_MAX=80`, `LENGTH_MAX_CM=100000`; and `validate_track(...)`, raising
  `Validation(reason, detail)` for: `track_name_invalid`, `track_points_count`, `track_zones_count`,
  `track_board_size`, `track_radius_range`, `track_coordinate_range`, `track_zone_size`,
  `track_zone_name`, `track_not_finite`, `track_length_invalid`, `track_start_invalid`,
  `track_closed_needs_three_points`.
- Start edge rule (agreed with the frontend spec): valid `edge` is an integer in `0..(n − 1)` when
  `closed` and `0..(n − 2)` when open, `t` in `[0, 1]`; `closed` with fewer than 3 points is rejected
  (the prototype's `build()` ignores `closed` below 3 points, so the combination is ambiguous).
- Points may lie outside the board (the `margin` rule detects it); only `|x|, |y| <= 10000` cm and
  finiteness are enforced.
- All limits are **assumptions pending the PO**.

### 3.3 Application (`application/tracks`)

`ports.py`: `TracksRepository` Protocol — `list(limit, offset)`, `get(id)`, `add(track)`,
`update(id, track)`, `delete(id)`, `profile_exists(profile_id)`. `use_cases.py`: `TracksService` with
`list_tracks`, `get_track`, `create_track` (also the import path), `update_track`, `delete_track`,
`export_track`; raises `NotFound("track_not_found", ...)` and `Validation("track_profile_unknown", ...)`.
`dto.py`: transport objects between layers.

### 3.4 Infrastructure

- `models/tracks.py` — `TrackModel` (`__tablename__ = "track"`):

| Column | Type | Notes |
|---|---|---|
| `id` | BigInteger identity PK | like `run.id` |
| `name` | String(80) NOT NULL | `CHECK char_length(trim(name)) BETWEEN 1 AND 80` |
| `board_width_cm`, `board_height_cm` | Float NOT NULL | `CHECK BETWEEN 50 AND 2000` |
| `closed` | Boolean NOT NULL | |
| `points` | JSONB NOT NULL | `CHECK jsonb_typeof = 'array' AND jsonb_array_length BETWEEN 2 AND 500` |
| `zones` | JSONB NOT NULL DEFAULT '[]' | `CHECK array, length 0..100` |
| `start_edge` | Integer NOT NULL | `CHECK >= 0` |
| `start_t` | Float NOT NULL | `CHECK BETWEEN 0 AND 1` |
| `profile_id` | String(40) NULL | FK `profile.id` `ON DELETE RESTRICT` (as `run.profile_id`), indexed |
| `length_cm` | Float NOT NULL | `CHECK > 0 AND <= 100000` |
| `created_at`, `updated_at` | timestamptz NOT NULL | server default `now()`; `updated_at` set on update |

  Points and zones are JSONB because they are always read and written whole; no per-point query exists.
  The `CHECK`s cover scalar columns and array lengths only; per-element limits (coordinates, radius,
  zone width/height/name, `start.edge` against the point count) are enforced by the domain and the
  Pydantic schemas, not by the database. A `CHECK` that fires despite those validations would surface
  as `IntegrityError` → 409 `conflict` and would be a bug.
- `repositories/tracks_repository.py`: `SqlAlchemyTracksRepository` implements the port.
- `migrations/versions/0006_tracks.py`: creates `track` and indexes; `downgrade` refuses when rows
  exist (same pattern as `0005`).
- `migrations/versions/0007_track_profiles.py` (data): inserts `lgr2026` and `libre`; downgrade deletes
  only those two rows.

### 3.5 Track rules in profiles

`profile.rules.track` is flat:

```json
"track": {
  "line_width_mm": 19, "gap_length_cm": 2,
  "radius_min": {"enabled": true, "value": 15},  "angle_min": {"enabled": true, "value": 90},
  "no_sharp": {"enabled": false, "value": true}, "separation_min": {"enabled": true, "value": 30},
  "margin": {"enabled": true, "value": 30},      "zone_distance": {"enabled": true, "value": 30},
  "closed": {"enabled": true, "value": true},    "length_min": {"enabled": false, "value": 500},
  "length_max": {"enabled": false, "value": 3000}, "straight_min": {"enabled": false, "value": 10},
  "straight_max": {"enabled": false, "value": 200}, "cross_max": {"enabled": true, "value": 0},
  "gap_max": {"enabled": true, "value": 0}
}
```

Seed values are the prototype's (`lgr2026`; lengths converted from its metres to cm). `libre`:
`radius_min 5`, `angle_min 30`, `separation_min 12`, `margin 12`, `zone_distance 10`, `cross_max`
disabled with value 2, `gap_max` disabled with value 4, the rest as in `lgr2026`. Units: lengths in cm,
`angle_min` in degrees, counts unitless, `line_width_mm` in mm (the prototype divides it by 10 to draw
in cm).

New profile rows (proposal): `lgr2026` — competition "Let's Go Robot 2026", label "LGR 2026", category
"Velocista"; `libre` — competition "Entrenamiento libre", label "Libre", category "Entrenamiento". They
carry only the `track` block (no robot rules).

### 3.6 Units in OpenAPI

Every numeric field description states its unit: `length_cm`, `board.width_cm/height_cm`, `points[].x/y/
radius` and `zones[].x/y/width/height` in **centimetres**; `start.t` fraction 0–1. The profile route
description documents `rules.track`: lengths and `gap_length_cm` in **centimetres** (including
`length_min` and `length_max`, converted from the prototype's metres), `line_width_mm` in
**millimetres**, `angle_min` in **degrees**, counts unitless.

### 3.7 Error formats (exact, for the frontend)

The API has two 422 shapes; the frontend tells them apart with `Array.isArray(body.detail)`.
The backend does **not** change either format (decision: the frontend parses field errors).

**A. Request parsing (Pydantic/FastAPI default, `detail` is a list)**

```json
{"detail": [
  {"type": "less_than_equal", "loc": ["body", "points", 3, "radius"],
   "msg": "Input should be less than or equal to 200", "input": 250, "ctx": {"le": 200}},
  {"type": "missing", "loc": ["body", "board", "width_cm"],
   "msg": "Field required", "input": {"height_cm": 250}},
  {"type": "extra_forbidden", "loc": ["body", "pts"],
   "msg": "Extra inputs are not permitted", "input": []}
]}
```

`loc` is an array of strings and integers; `loc[0]` is `"body"` (`"path"` or `"query"` for path/query
parameters); `type` is a Pydantic code; `msg` is an English sentence (not localised); `input` is the
offending value; `ctx` appears only for some errors. The list contains every failing field, not only
the first. (Keys confirmed in part by an existing test that reads `loc` and `type`; the exact `msg`
texts depend on the installed Pydantic version.)

**B. Domain rule or reference (business error, `detail` is an object)**

```json
{"detail": {"reason": "track_profile_unknown", "detail": "Profile does not exist"}}
```

| HTTP | `reason` | Cause |
|---|---|---|
| 404 | `track_not_found` | `GET`, `PUT`, `DELETE`, `export` of a missing id |
| 422 | `track_profile_unknown` | `profile_id` of `POST`/`PUT` does not exist |
| 422 | `track_name_invalid`, `track_points_count`, `track_zones_count`, `track_board_size`, `track_radius_range`, `track_coordinate_range`, `track_zone_size`, `track_zone_name`, `track_not_finite`, `track_length_invalid`, `track_start_invalid`, `track_closed_needs_three_points` | Domain rule (raised only when a body passes the schemas but not the domain, or for non-REST callers) |
| 401 | `unauthorized` | Missing/expired JWT (`WWW-Authenticate: Bearer`) |
| 409 | `conflict` | Unexpected `IntegrityError` (generic handler) |
| 503 | `database_unavailable` | Database down |

Profile deletion with tracks: not applicable (the profile API is read-only). If a delete is added, it
returns 409 `profile_in_use`; today a raw `RESTRICT` violation would reach the generic handler as 409
`conflict`.

### 3.8 Wiring

`composition.py`: `get_tracks_service(session) -> TracksService`. `main.py`: add `tracks_router` to
`MODULE_ROUTERS` and an OpenAPI tag `tracks`.

## Data Flow

```
Create/import: JSON ▶ Pydantic schema (shape, finite, bounds) ▶ TracksService.create_track
   ▶ domain validate_track ▶ repo.profile_exists ▶ repo.add ▶ INSERT (CHECKs) ▶ 201
Export:        GET /{id}/export ▶ get_track ▶ JSON + Content-Disposition: attachment
Profiles:      GET /api/profiles ▶ rules JSONB returned as stored (rules.track present for lgr2026/libre)
```

## Design Decisions & Trade-offs

1. **The backend does not recompute geometry; it trusts `length_cm`.** Porting arcs and crossings to
   Python would double the work and the bug surface. Trade-off: a client can store a wrong length
   within `(0, 100000]`. Optional mitigation: a plausibility check — with fillets the real length is
   at most the polyline length through the control points (an arc is shorter than its two tangent
   legs), so `length_cm` can be rejected above that sum plus a tolerance. Reasoned, not tested.
2. **Two new profiles instead of extending the existing four.** The existing profiles are MR4/club
   robot rules with no source for their track rules, so inventing values is not acceptable, and `club`
   is the default profile of simulated runs (`SIM_PROFILE_ID`). Trade-off: the profile list grows by
   two entries that have no robot rules; the console's profile view must tolerate that (not verified).
3. **Two migrations (`0006` schema, `0007` data).** The seed can be reverted without dropping the
   table. A single revision is acceptable if the team prefers fewer files.
4. **JSONB for `points`/`zones`, columns for scalars.** Limits are enforceable by `CHECK`; points are
   never queried individually.
5. **`ON DELETE RESTRICT` on `profile_id`.** Same as `run`; profiles are not deletable by API anyway.
6. **Domain constants as the single source of limits**, reused by Pydantic and echoed in `CHECK`s.
7. **Router wired through `composition.py`.** Keeps the dependency rule intact for the new context.
8. **`POST` doubles as import and ignores read-only fields**, so an exported file can be re-imported
   without editing.
9. **List order `updated_at DESC, id DESC`.** Most recently edited first; no filters in this story.
10. **Field-level errors are parsed by the frontend.** The backend keeps FastAPI's list-shaped 422 for
    parsing errors and its `{reason, detail}` object for domain errors; no new error format.
    Trade-off: two shapes to handle; benefit: no change to the existing error contract.
11. **Unknown `profile_id` is 422, not 404.** The missing thing is a value inside the body, not the
    resource in the URL.
12. **Coordinates may lie outside the board.** The `margin` rule exists to report it, so the backend
    only bounds them (`|x|, |y| <= 10000` cm) and requires finiteness.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Limits are PO assumptions | Rework of validation and `CHECK`s | Constants in one place; `CHECK` changes need a migration |
| Wrong `length_cm` from the client | Bad reference for HU-30/HU-35 | Bounds now; optional plausibility check or Python port later |
| Unit mismatch (prototype lengths in m) | Wrong enabled thresholds | Convert to cm in the seed; document in OpenAPI; Open question 2 |
| Contract gaps (id type, `edge`, `gap`, export shape) | Frontend/backend mismatch | Resolve the Open questions before coding |
| Profile list gains robot-rule-less profiles | Console view could assume robot keys | Check the frontend; no backend code reads those keys |
| Last-write-wins on `PUT` | Lost edits across consoles | Optional `If-Match` / `updated_at` check |
| Two 422 shapes (list vs object) | Frontend shows a generic message if it only handles one | Documented in §3.7; contract test asserts both |
| Points far outside the board (up to ±10000 cm) | Odd but valid tracks | Intended: `margin` rule reports it; bound is a PO assumption |
| Large payloads (500 points) | Slow requests | Bounded by limits; request size is small (a few tens of kB) |
| Migration order/data | Bad seed on Render | Test up/down locally; run on Render only through the normal start-up migration |
| The prototype is unversioned (`trazador-de-pistas.html`) | Source of seed values could be lost | Keep a copy in an active repository (see the analysis, §7) |

## Test Strategy

- **Unit (no DB)**: `domain/tracks` — every boundary (1/80 chars, 2/500 points, 0/100 zones, 50/2000 cm,
  radius 0/200, coordinates ±10000, zone width/height >0 and ≤2000, zone name 80, length >0 and
  ≤100000, `t` 0/1, `start.edge` for open and closed polylines, `closed` with 2 points), `NaN`/`Infinity`;
  `TracksService` with an in-memory double of `TracksRepository`.
- **Integration (real PostgreSQL, isolated schema `qa_<uuid>`)**: repository CRUD, `CHECK` violations,
  FK to `profile`, ordering and pagination; routes through `client` (`201/200/204/404/422`), 401 when
  `AUTH_REQUIRED`, import of an exported file, profiles returning `rules.track`.
- **Contract (`tests/contract/rest`)**: OpenAPI contains the six operations with documentation and
  error responses; error body format; the schema descriptions mention centimetres for `length_cm`,
  `board`, `points` and `zones`, and the profile description states the units of `rules.track`; a
  parsing error returns the list shape and a domain error the object shape.
- **Migration**: `0006` upgrade/downgrade on an empty database (downgrade with rows refuses);
  `0007` inserts and removes only its two profiles. How the existing suite exercises Alembic is **not
  verified**; the design assumes a test that runs the revisions on a temporary schema.
- **Live opt-in** (`TRACKS_LIVE_TEST=1`, like `SIM_LIVE_TEST`): logs in against the deployed API with
  credentials from environment variables, creates a track, reads, exports and deletes it; never
  touches other rows; no credentials in the repository.

## Relative size

EN-28 is estimated at 1 SP, but the backend alone is clearly larger: 2 migrations, 1 model, a new
context in four layers, 6 routes, a profile seed and 5 test types — roughly three times the size of the
read-only `rules` context (2 routes, no migration) plus validation and tests. The analysis rates the
backend "medium" and the frontend interface "large". Judgement (not a measurement): the whole of EN-28
is several times 1 SP, and splitting it into backend and frontend stories, as the analysis suggests,
is advisable.
