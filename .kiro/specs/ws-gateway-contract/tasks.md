# Implementation Plan — WebSocket Gateway and Contract 2.0

## Overview

`[x]` marks work done and verified in the code (file evidence); `[ ]` marks pending work; `*` is
optional. The no-database WS tests were run on 2026-10-28 (`tests/contract` + `tests/test_ws_engine.py`
included in 104 passed / 9 skipped; `tests/test_sim_integration.py` 87 passed). End-to-end WS flows are
database-backed and were not run in that session.

## Tasks

- [x] 1. Envelope and catalog
  - [x] 1.1 Strict `Envelope` with legacy aliases — `src/velocista/interface/websocket/contract/base.py`
  - [x] 1.2 Catalog of senders, models, ack and frequency — `.../contract/catalog.py`
  - [x] 1.3 Version check (major must be 2) — `.../contract/base.py` (`same_major_version`)
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Channels and device auth
  - [x] 2.1 `/ws/robot`, `/ws/timer`, `/ws/console` + alias `/ws/consola` — `.../websocket/gateway.py`
  - [x] 2.2 Constant-time device token check, close 1008 — `gateway.py:86-89`
  - [x] 2.3 Replace previous connection with close 1012; `link` broadcast — `gateway.py:92-110`
  - [x] 2.4 `/ws/robot` closed while the simulator is enabled — `gateway.py:113-118`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 3. Robot flow rules
  - [x] 3.1 Manifest first (`no_manifest`), reset on new manifest — `gateway.py:45-66`
  - [x] 3.2 Out-of-order `signals` dropped by `t_ms` — `gateway.py:55-58`
  - [x] 3.3 Undeclared channel warning once (`invalid_channel`) — `gateway.py:61-66`
  - [x] 3.4 Duplicate dedup + ack only after saving; `ingestion_failed` on error — `gateway.py:41-79`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 4. ACL
  - [x] 4.1 ES→EN field and value tables — `.../contract/translation.py`
  - [x] 4.2 Reverse translation for commands — `src/velocista/infrastructure/realtime/registry.py` (`send`, `REVERSE_VALUES`)
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 5. Console behaviour
  - [x] 5.1 Initial `hello`, simulator `connection`, `manifest`/`status` snapshots — `gateway.py:146-179`
  - [x] 5.2 Origin check and JWT when `AUTH_REQUIRED` — `gateway.py:128-143`
  - [x] 5.3 Slow consoles disconnected with 1013 — `registry.py` (`_relay`, `_close_slow`)
  - [x] 5.4 Commands answer 202 and confirm by `ack` — `src/velocista/interface/rest/devices/router.py`
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 6. Simulator client
  - [x] 6.1 Schemas, validation, commands, status endpoint — `src/velocista/infrastructure/integrations/velocista_sim/`, `src/velocista/main.py` (`/api/simulator`)
  - [x] 6.2 Tests with official fixtures (87 pass) — `tests/test_sim_integration.py`
  - _Requirements: 6.1, 6.2, 6.3_
  - Not individually verified: timeout/`command_uncertain` and reconnection backoff behaviour (described in `docs/SIMULATOR.md`; tests not reviewed one by one)

- [ ] 7. Move the console JWT out of the URL
  - [ ] 7.1 Accept `{"type":"auth","data":{"token":...}}` as first message on `/ws/console` — `src/velocista/interface/websocket/gateway.py` (today `query_params.get("token")`, line 136)
  - [ ] 7.2 Close with 1008 if the first message is not a valid `auth` or arrives late
  - [ ] 7.3 Keep `?token=` temporarily with a deprecation log; then remove it
  - [ ] 7.4 Contract and e2e tests for the new handshake; update `docs/CONTRACT.md`
  - _Requirements: 7.1, 7.2, 7.3_

- [ ] 8. Contract documentation and tests
  - [ ] 8.1 Replace the 2 skipped template tests in `tests/contract/test_message_catalog.py` with real catalog tests
  - [ ] 8.2 Document in `docs/CONTRACT.md` that `/api/devices/robot/manifest` is the manifest endpoint and list `sim` message types
  - _Requirements: 1.3, 6.3_

- [ ]* 9. Device tokens in headers only
  - [ ]* 9.1 Stop accepting `?token=` for `/ws/robot` and `/ws/timer` once firmware sends `x-device-token`
  - _Requirements: 2.2_

## Notes

- Not verified: real firmware or timer behaviour (no device available), the live simulator, and the
  database-backed WS e2e flow `tests/e2e/flows/test_robot_websocket_flow.py`.
- Line numbers refer to the commit `a0fed7c` working tree on 2026-10-28.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "2.1", "2.2", "2.3", "2.4", "3.1", "3.2", "3.3", "3.4", "4.1", "4.2", "5.1", "5.2", "5.3", "5.4", "6.1", "6.2"] },
    { "id": 1, "tasks": ["7.1", "7.2", "8.1", "8.2"] },
    { "id": 2, "tasks": ["7.3", "7.4", "9.1"] }
  ]
}
```
