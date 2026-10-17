# Pruebas extremo a extremo (backend)

Recorren **un proceso completo** como lo haría el operador, el simulador o el robot, atravesando
todas las capas con PostgreSQL real.

## Flujo 1 — Recorrido del operador (`flows/test_operator_journey.py`)

```mermaid
sequenceDiagram
    actor Op as Operador
    participant API as Backend
    participant DB as PostgreSQL
    Op->>API: POST /components (ESP32, stock 2)
    Op->>API: POST /robots
    Op->>API: POST /robots/{id}/versions (current)
    API->>DB: guarda snapshot de piezas
    Op->>API: POST /robots/{id}/setups (PID kp=2, kd=1)
    Op->>API: POST /runs/simulated
    API->>DB: corrida + vueltas + sectores + segmentos
    Op->>API: GET /runs · GET /runs/{id}/laps
    Op->>API: PATCH /runs/{id} (nota)
    Op->>API: DELETE /setups/{id}
    Op->>API: GET /runs/{id}
    API-->>Op: parámetros intactos (historial inmutable)
    Op->>API: GET /inventory
    API-->>Op: in_robots = 1, available = 1
```

## Flujo 2 — Servicio de simulación (`flows/test_operator_journey.py`)

```mermaid
sequenceDiagram
    participant S as Simulador
    participant API as Backend
    S->>API: POST /runs/ingest (Bearer token, external_run_id)
    API-->>S: 201 Created
    S->>API: POST /runs/ingest (mismo payload — reintento)
    API-->>S: 200 + Idempotent-Replay: true
    Note over S,API: mismo id → misma corrida, sin duplicar
```

## Flujo 3 — Sesión del robot por WebSocket (`flows/test_robot_websocket_flow.py`)

```mermaid
sequenceDiagram
    participant C as Consola (/ws/console)
    participant API as Backend
    participant R as Robot (/ws/robot)
    C->>API: conecta
    API-->>C: hello {robot:false, timer:false}
    R->>API: conecta con token
    API-->>C: link {robot, connected:true}
    R->>API: manifest
    API-->>R: ack ok
    API-->>C: manifest (traducido a inglés)
    R->>API: status (ready, calibrated)
    API-->>C: status
    C->>API: POST /devices/robot/commands {mode: competition}
    API->>R: mode
    R->>API: ack
    API-->>C: ack
    R--xAPI: desconecta
    API-->>C: link {connected:false}
```

Casos extra: token inválido → cierre `1008`; `start` sin calibrar → `409 not_calibrated`.

## Ejecutar

```powershell
pytest tests/e2e -q
```

> `tests/e2e/test_ws_robot_flow.py` es una plantilla previa del equipo (omitida); los flujos reales están en `flows/`.
