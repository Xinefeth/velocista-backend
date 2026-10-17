# Soporte de pruebas (backend)

Código compartido por las pruebas. **No contiene pruebas.**

## `db_fixtures.py`

```mermaid
flowchart TB
    db["<b>db</b><br/>conexión con esquema temporal<br/>+ datos de referencia"] --> client["<b>client</b><br/>TestClient de la app real<br/>con get_session sobreescrito"]
    client --> build["<b>build</b><br/>Builders: crea datos por la API"]
    monk["monkeypatch"] --> sh["<b>service_headers</b><br/>token del servicio de simulación"]
```

| Fixture | Devuelve | Úsalo para |
|---------|----------|------------|
| `db` | conexión SQLAlchemy aislada | pruebas de repositorio |
| `client` | `TestClient` (no relanza excepciones del servidor) | llamar endpoints |
| `build` | `Builders` | preparar datos: `robot()`, `component()`, `version()`, `setup()`, `robot_ready()`, `ingestion_payload()` |
| `service_headers` | `{"Authorization": "Bearer …"}` | probar `/runs/ingest` |

### Datos de referencia sembrados por `db`

| Tabla | Registro |
|-------|----------|
| `component_type` | `mcu` |
| `slot` | `mcu` (obligatorio) |
| `controller` | `pid` con `kp∈[0,10]`, `kd∈[0,5]`, preset `Base` |
| `profile` | `club` |

### Cómo usarlo en una carpeta nueva

```python
# tests/integration/rest/<contexto>/conftest.py  (o en la carpeta padre)
from support.db_fixtures import Builders, build, client, db, service_headers  # noqa: F401
```
