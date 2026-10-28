# Requirements Document — WebSocket Gateway and Contract 2.0

## Introduction

The gateway connects the robot, the cronómetro and the consola over WebSocket and relays validated
messages in English. It is an anti-corruption layer: firmware frames written with Spanish keys and
enum values are translated at the boundary. A separate outbound client talks to the external
simulator (contract v1) and publishes its messages to the console with `sender: "sim"`. Source of
truth for names: `docs/CONTRACT.md` (v1 frozen 2026-10-15, WS contract 2.0).

## Glossary

- **Gateway**: Router WebSocket `interface/websocket/gateway.py`.
- **Envelope**: Sobre común `{type, seq, ts, data}` de todo mensaje.
- **Catálogo (CATALOG)**: Tabla `(emisor, type) → modelo, requiere ack, frecuencia` en `contract/catalog.py`.
- **Manifiesto (manifest)**: Primer mensaje del robot; declara canales, controladores y comandos.
- **Canal (channel)**: Clave de señal dentro de `data.channels`; vocabulario abierto declarado por el manifiesto.
- **ACL**: Anti-corruption layer; `contract/translation.py` (`translate_type`, `translate_payload`).
- **Ack**: Confirmación `{ok: true}` con el mismo `seq` del mensaje confirmado.
- **Consola**: Cliente web conectado a `/ws/console` (alias `/ws/consola`).
- **Simulador**: `velocista-sim`; el backend es su cliente (contrato v1 rev. 1.2).

## Requirements

### Requirement 1: Envelope y validación estricta

**User Story:** As a firmware developer, I want malformed frames rejected with a visible event, so that
typing errors are found quickly.

#### Acceptance Criteria

1. THE Gateway SHALL accept frames shaped `{type, seq, ts, data}` with `type` matching `^[a-z_]{2,24}$`, `seq` in `0..2^32-1` and `ts >= 0`.
2. THE Envelope and every message model SHALL reject undeclared fields.
3. IF a frame is not valid JSON, fails the envelope or fails the model for its `(sender, type)`, THEN THE Gateway SHALL discard it and broadcast an `invalid_message` event.
4. WHEN a device declares a contract with a different major version than `2`, THE Gateway SHALL reject its manifest.

### Requirement 2: Canales y autenticación de dispositivo

**User Story:** As an operator, I want only authorised devices to connect, so that nobody else can
feed or control the robot.

#### Acceptance Criteria

1. THE Gateway SHALL expose `/ws/robot`, `/ws/timer`, `/ws/console` and the alias `/ws/consola`.
2. WHEN a device connects, THE Gateway SHALL require `x-device-token` (header) or `?token=` and compare it in constant time with the configured token; otherwise it SHALL close with code 1008.
3. WHEN a second connection of the same device arrives, THE Gateway SHALL replace the first and close it with code 1012.
4. WHILE the external simulator source is enabled, THE Gateway SHALL close `/ws/robot` with code 1008.
5. WHEN a device connects or disconnects, THE Gateway SHALL broadcast a `link` message from `api`.

### Requirement 3: Flujo del robot

**User Story:** As a console user, I want a coherent live state of the robot, so that I only see data
consistent with its manifest.

#### Acceptance Criteria

1. WHEN the robot sends any message before its manifest, THE Gateway SHALL discard it and emit a `no_manifest` event.
2. WHEN a new manifest arrives, THE Gateway SHALL reset the last status, the last `t_ms` and the channel warnings.
3. WHEN a `signals` message has `t_ms` not greater than the last accepted one, THE Gateway SHALL discard it.
4. IF a `status` or `signals` message carries a channel not declared in the manifest, THEN THE Gateway SHALL emit `invalid_channel` once per warning.
5. WHEN a message that requires ack is a duplicate (same `seq` already received), THE Gateway SHALL re-send the ack and SHALL NOT process it again.
6. WHEN a message that requires ack is processed and saved, THE Gateway SHALL send `ack` with its `seq` and broadcast it to consoles.
7. IF saving a device message fails, THEN THE Gateway SHALL emit `ingestion_failed` and SHALL NOT ack it.

### Requirement 4: Anti-corruption layer ES→EN

**User Story:** As a console developer, I want English `type`, field names and enum values always, so
that the console never depends on firmware vocabulary.

#### Acceptance Criteria

1. WHEN a frame contains the key `tipo`, THE Gateway SHALL treat it as legacy and translate `type`, field names and enum values to English before validation, broadcast and persistence.
2. THE Gateway SHALL NOT translate channel keys inside `data.channels`.
3. WHEN the API sends a command to a legacy device, THE Gateway SHALL translate English `type` and enum values back to the device vocabulary.

### Requirement 5: Consola

**User Story:** As a console user, I want an initial snapshot on connect and a stable stream.

#### Acceptance Criteria

1. WHEN a console connects, THE Gateway SHALL send `hello` (`data.devices`), then a simulator `connection` snapshot if the simulator is active, then the current `manifest` and `status` of connected devices.
2. WHEN a console connects with an `Origin` header not listed in CORS origins, THE Gateway SHALL close with code 1008.
3. WHILE `AUTH_REQUIRED` is true, THE Gateway SHALL require a valid console JWT (query `token` or `Authorization: Bearer`).
4. WHEN a console cannot keep up, THE Hub SHALL disconnect it with code 1013 using a bounded queue per console, without blocking other consoles or the database.
5. THE API SHALL accept commands over `POST /api/devices/{device}/commands`, answer HTTP 202 and deliver the confirmation as an `ack` on the console WebSocket.

### Requirement 6: Cliente del simulador (contrato v1)

**User Story:** As an operator, I want the backend to consume the simulator safely, so that runs are
stored without inventing data.

#### Acceptance Criteria

1. WHEN `SIM_ENABLED` is true, THE API SHALL connect to `SIM_WS_URL` and validate every incoming frame against the JSON Schemas of contract v1.
2. THE API SHALL expose the connection state at `GET /api/simulator` (`{"state": "disabled"}` when off).
3. THE API SHALL relay simulator messages to consoles with `sender: "sim"` and types `connection`, `hello`, `config`, `telemetry`, `event`, `catalog`, `error`, `diagnostic`, `command_result`.
4. WHEN a command gets no confirmation before `SIM_COMMAND_TIMEOUT`, THE API SHALL report `command_uncertain` and SHALL block new commands until reconnection, never re-sending `start` automatically.
5. WHEN the connection drops, THE API SHALL reconnect with a bounded backoff (`SIM_RECONNECT_MAX_SECONDS`).

### Requirement 7: Autenticación de la consola por mensaje (pendiente)

**User Story:** As a security-minded operator, I want the console JWT not to travel in the URL, so
that it does not end up in logs or browser history.

#### Acceptance Criteria

1. WHEN a console connects with `AUTH_REQUIRED=true`, THE Gateway SHALL accept the JWT in a first message `{"type":"auth","data":{"token":"..."}}` and SHALL NOT require it in the query string.
2. IF the first message is not a valid `auth`, or arrives late, THEN THE Gateway SHALL close with code 1008.
3. WHILE the migration is in progress, THE Gateway MAY keep accepting `?token=` and SHALL log a deprecation warning.
