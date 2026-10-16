# ARCHITECTURE — velocista-backend

Backend del sistema de pista (robot velocista + cronómetro + consola), reescrito con
**Clean Architecture**. Código y nombres en **inglés**; comentarios en **español**.

## Regla de dependencia

Las dependencias apuntan siempre **hacia adentro**. El dominio no conoce FastAPI,
SQLAlchemy ni WebSocket.

```
domain  ←  application  ←  infrastructure
                        ←  interface (REST + WS)
```

- **domain** — entidades y reglas de negocio puras. Sin imports de frameworks.
- **application** — casos de uso que orquestan el dominio y declaran *ports* (interfaces).
- **infrastructure** — adaptadores concretos que *implementan* los ports (SQLAlchemy, Alembic, settings, tiempo real).
- **interface** — entrega I/O (routers FastAPI + gateway WS) que *invoca* casos de uso.
- **composition.py** — arma el grafo de dependencias (inyección).

## Estructura de carpetas

```
velocista-backend/
├── src/velocista/
│   ├── domain/                 # Núcleo puro, sin frameworks
│   │   ├── builder/            # armador  → robots y versiones
│   │   ├── catalog/            # catalogo → componentes y tipos
│   │   ├── runs/               # corridas → corrida + vuelta
│   │   ├── config/             # configuracion → modo + línea
│   │   ├── events/             # eventos → bitácora
│   │   ├── rules/              # reglamento
│   │   ├── optimization/       # optimizacion
│   │   └── shared/             # value objects + errores de dominio
│   ├── application/            # Un paquete por contexto
│   │   └── <context>/
│   │       ├── ports.py        # interfaces: repositorios, gateways
│   │       ├── dto.py          # objetos de transporte entre capas
│   │       └── use_cases.py    # casos de uso (orquestación)
│   ├── infrastructure/
│   │   ├── persistence/
│   │   │   ├── models/         # modelos ORM SQLAlchemy
│   │   │   ├── repositories/   # implementan los ports de application
│   │   │   └── migrations/     # alembic
│   │   ├── config/             # settings (pydantic-settings), env
│   │   ├── realtime/           # adaptadores de tiempo real si hacen falta
│   │   └── ingestion/          # (FUTURO) servicio de ingesta externo; NO implementar en v1
│   ├── interface/
│   │   ├── rest/
│   │   │   └── <context>/
│   │   │       ├── router.py   # endpoints FastAPI
│   │   │       └── schemas.py  # pydantic de entrada/salida (JSON) — nombres de docs/CONTRACT.md
│   │   └── websocket/          # gateway → /ws/robot, /ws/timer, /ws/console
│   │       ├── contract/       # envelope, catálogo de mensajes, modelos
│   │       ├── gateway.py
│   │       └── commands.py
│   ├── composition.py          # wiring / inyección de dependencias
│   └── main.py                 # arranque FastAPI
├── tests/                      # ver "Estrategia de pruebas"
├── docs/
│   ├── ARCHITECTURE.md
│   └── CONTRACT.md             # glosario ES→EN (fuente de verdad del contrato)
├── pyproject.toml
└── README.md
```

## Mapa de módulos (backend actual → nuevo)

| Actual (ES, Proyecto_Taller/api) | Nuevo (EN) | Contexto |
|---|---|---|
| armador | `builder` | robots + versiones |
| catalogo | `catalog` | componentes + tipos |
| corridas | `runs` | corrida + vuelta |
| configuracion | `config` | modo + línea |
| eventos | `events` | bitácora |
| reglamento | `rules` | reglamento |
| optimizacion | `optimization` | — |
| auth | `auth` | — |
| gateway | `interface/websocket` | /ws/* |
| cronometro | `timer` | dispositivo |

## Estrategia de pruebas (solo formato; sin tests reales en v1)

Estructura espejo del dominio, pirámide de pruebas:

```
tests/
├── unit/                    # dominio + casos de uso, SIN I/O (rápidos)
│   ├── domain/runs/test_lap_rules.py
│   └── application/runs/test_close_lap_use_case.py
├── integration/             # repos reales contra BD de prueba
│   └── persistence/test_runs_repository.py
├── contract/                # valida el contrato WS 2.0 (envelope + catálogo)
│   └── test_message_catalog.py
└── e2e/                     # REST + WS de punta a punta
    └── test_ws_robot_flow.py
```

Convención: un archivo `test_*.py` por unidad; clases `Test<Cosa>`; métodos
`test_<acción>_when_<condición>`. Fixtures compartidas en `tests/conftest.py`.
Los dobles de prueba implementan los *ports* (no se mockea SQLAlchemy).

## Decisiones

- `sender` del dispositivo = `robot`; `velocista`/`minisumo` solo como categoría de competencia (`robot.type`).
- **Gateway WS = anti-corruption layer:** traduce `type` y valores de enum (español→inglés) en `interface/websocket/contract/` antes de reenviar a `/ws/console` y de persistir. El firmware puede seguir en español salvo las **claves de canal** (vocabulario abierto del manifiesto), única dependencia del firmware.
- Servicio de **ingesta** externo previsto (`infrastructure/ingestion/`) pero **no implementado** en v1.
- Nombres de campos/enums/mensajes: ver `docs/CONTRACT.md` (v1 congelada, 2026-10-15).
