# tests/ — formato (sin tests reales todavía)

Estas son **plantillas de formato**, no tests implementados (van marcados `@pytest.mark.skip`
para que `pytest` pase en verde). Muestran la estructura y convenciones acordadas.

## Pirámide

```
tests/
├── unit/            # dominio + casos de uso, SIN I/O (rápidos)
│   ├── domain/
│   └── application/
├── integration/     # repos reales contra BD de prueba
│   └── persistence/
├── contract/        # valida el contrato WS 2.0 (envelope + traducción ACL)
└── e2e/             # REST + WS de punta a punta
```

## Convenciones

- Un archivo `test_*.py` por unidad. Clases `Test<Cosa>`. Métodos `test_<acción>_when_<condición>`.
- Patrón **given / when / then** en el cuerpo (comentarios en español).
- Fixtures compartidas en `tests/conftest.py`.
- Los dobles de prueba implementan los **ports** de `application` (no se mockea SQLAlchemy).
