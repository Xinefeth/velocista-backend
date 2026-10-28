# Design Document — WebSocket Gateway and Contract 2.0

## Introduction

`gateway.py` is a thin adapter: it authenticates the connection, parses and translates each frame,
validates it against the catalog, applies per-device rules (manifest first, ordering, dedup, channel
checks), hands it to the message handler (the recorder, in a thread pool) and broadcasts the result to
consoles through the Hub. The simulator client is a separate outbound connection that feeds the same
console channel.

## Goals & Non-Goals

**Goals**

- One strict, versioned message contract (`CONTRACT_VERSION = "2.0"`).
- Firmware can stay in Spanish except channel keys (ACL).
- Slow consoles never block ingestion.

**Non-Goals**

- Changing the firmware or the simulator.
- Binary framing or compression.
- Authentication redesign beyond moving the JWT out of the URL (task 7).

## Architecture Overview

```
Robot ──/ws/robot──┐                                   ┌── /ws/console ──▶ Consola
Cronómetro ─/ws/timer─┤  serve(): token ▶ accept         │   hello · link · manifest · status · ack · event · sim messages
                      ▼                                  │
              process(): json ▶ Envelope ▶ [translate if "tipo"] ▶ validate_data(CATALOG)
                      ▶ robot rules (manifest first · t_ms order · channel check · dedup by seq)
                      ▶ hub.message_handler (recorder, threadpool) ▶ ack ▶ hub.broadcast ──┘
velocista-sim ◀─WS (client)── SimulatorClient ── contract v1 schemas ──▶ hub (sender "sim")
```

## Component Design

### 3.1 Envelope (`contract/base.py`)

`Envelope(type, seq, ts, data)`; `Strict` models use `extra="forbid"`, `strict=True`, no NaN/Inf.
`type` also accepts the legacy alias `tipo` and `data` accepts `datos`. Names of channels, parameters
and sensors match `^[a-z][a-z0-9_]{0,31}$`.

### 3.2 Catalog (`contract/catalog.py`)

| Sender → | `type` (ack) |
|---|---|
| robot → api | `manifest`(ack), `status`, `signals`, `lap`(ack), `sync`(ack), `event`(ack), `ack` |
| api → robot | `calibrate`(ack), `start`(ack), `stop`(ack), `setup`(ack), `mode`(ack), `line`(ack), `lap_close`(ack), `ack` |
| timer → api | `hello`(ack), `crossing`(ack), `status`, `ack` |
| api → timer | `rearm`(ack), `ack` |

Frequencies in the catalog: status 1 Hz, signals 20 Hz while running, timer status every 5 s.

### 3.3 ACL (`contract/translation.py`)

`FIELDS` (e.g. `tipo→type`, `datos→data`, `canales→channels`, `lazo_hz→loop_hz`) and `VALUES` (e.g.
`manifiesto→manifest`, `senales→signals`, `vuelta→lap`, `evento→event`, `cierre_vuelta→lap_close`,
`prueba→test`, `competencia→competition`) are applied by `translate_type`/`translate_payload`.
`REVERSE_VALUES` is used by `Registry.send` for legacy devices. Channel keys are never translated.

### 3.4 Hub (`infrastructure/realtime/registry.py`)

Holds `connections` (device → `Connection` with manifest, last status, last `t_ms`, warnings, received
seq window) and a bounded relay queue per console. A console whose queue or send times out is closed
with 1013. `device_status()` feeds `GET /api/health` and the console `hello`.

### 3.5 Simulator client (`integrations/velocista_sim/`)

`SimulatorClient` (one connection per process), `SessionState`, `contract.validate` (JSON Schemas under
`schemas/`), `commands.translate/confirms`, `adapter.telemetry`. Source of the contract:
`AlessoEngnr/velocista-sim`, commit `ea74075` (`docs/SIMULATOR.md`). `GET /api/simulator` returns its
snapshot.

### 3.6 Console authentication today and target

Today: `ws.query_params.get("token")` or `Authorization: Bearer` (`gateway.py:136`) when
`AUTH_REQUIRED`; device tokens by header or `?token=` (`gateway.py:86`). Target (pending): first
message `{"type":"auth","data":{"token":"<jwt>"}}`, then the connection is accepted into
`hub.consoles`.

## Data Flow

```
Robot frame ─▶ process ─▶ (accepted) recorder (DB) ─▶ ack ─▶ broadcast
                      └▶ (rejected) event invalid_message / no_manifest / invalid_channel
Console ─POST /api/devices/robot/commands─▶ 202 {seq} ─▶ hub.send ─▶ robot ─ack─▶ console
```

## Design Decisions & Trade-offs

- **ACL instead of changing firmware.** The firmware keeps working; cost: translation tables to
  maintain. Channel keys remain the only firmware dependency.
- **Ack only after persistence.** A message that cannot be saved is not acknowledged, so the device
  can retry; duplicates are re-acked and ignored.
- **Single in-process Hub.** No cross-instance fan-out; fits one worker.
- **JWT in the query string is a known weakness** kept for browser compatibility; see requirement 7.
