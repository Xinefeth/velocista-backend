# Contorno desde lados y ángulos (EN-42)

Sin sensores: se escriben los lados y ángulos que se conocen y el backend completa lo que falta,
cierra la figura y devuelve sus puntos, perímetro y área, también para figuras cóncavas (en L).
Lo usan HU-43 (armar el plano en el trazador, CU-5) y HU-41 (áreas marcando puntos, CU-3).

Código: `domain/measurements/polygon.py` (cálculo) e `interface/rest/polygons/` (endpoints).
No guarda nada en la base de datos.

## Convención

- Se recorre la figura en sentido **antihorario**, como se dibuja un plano.
- El **lado `i`** va del vértice `i` al vértice `i + 1`; el último vuelve al vértice 0.
- El **ángulo `i`** es el ángulo **interior** del vértice `i` (entre el lado `i − 1` y el lado `i`).
  La esquina entrante de una L mide **270°**.
- El lado 0 sale de (0, 0) hacia +x. En cada vértice se gira `180° − ángulo`.

## Qué puede faltar

| Dato | Regla |
|---|---|
| Ángulos | Suma de interiores = (n − 2) × 180°. Puede faltar **uno**, o los **dos** de los extremos de un mismo lado (la figura se cierra con ese lado, que también puede faltar) |
| Lados | Con todos los ángulos, la figura tiene que cerrar: pueden faltar hasta **dos lados que no sean paralelos** |

Ejemplos:

| Figura | Datos | Resultado |
|---|---|---|
| Cuadrado | `[4, 4, 4, 4]`, `[90, 90, 90, 90]` | 16 m, 16 m² |
| Rectángulo con dos lados que faltan | `[10, 6, null, null]`, `[90, 90, 90, 90]` | completa 10 y 6; 60 m² |
| L | `[6, 2, 4, null, null, 8]`, `[90, 90, 90, null, 90, 90]` | ángulo 270°, lados 6 y 2; 28 m, 24 m² |
| Triángulo (dos lados y el ángulo entre ellos) | `[3, 4, null]`, `[null, 90, null]` | lado 5; ángulos 53,13° y 36,87°; 6 m² |

## Endpoints (Swagger, etiqueta `polygons`)

| Método | Ruta | Para qué |
|---|---|---|
| POST | `/api/polygons/solve` | `{"sides_m": [...], "angles_deg": [...]}` con `null` en lo que falta |
| POST | `/api/polygons/from-points` | `{"points": [{"x": 0, "y": 0}, ...]}` en orden (horario o antihorario) |

Respuesta: `points`, `sides_m`, `angles_deg`, `perimeter_m`, `area_m2`, `concave`, `self_crossing`,
`closure_error_m`, `angle_sum_error_deg`, `closes`, `computed_sides`, `computed_angles` y
`warnings`.

| Aviso (`warnings`) | Significa |
|---|---|
| `does_not_close` | Con los lados escritos la figura no vuelve al inicio (más de 1 cm) |
| `angle_sum_mismatch` | Los ángulos no suman (n − 2) × 180° (más de 0,5°) |
| `self_crossing` | Dos lados se cruzan: el área no es válida |

| Error 422 (`reason`) | Cuándo |
|---|---|
| `polygon_side_count` | Menos de 3 o más de 100 lados |
| `polygon_lengths_mismatch` | Distinta cantidad de lados y de ángulos |
| `polygon_invalid_side` / `polygon_invalid_angle` | Lado ≤ 0 o ángulo fuera de (0°, 360°) |
| `polygon_underdetermined` | Faltan demasiados datos o los lados que faltan son paralelos |
| `polygon_does_not_close` | Con esos datos la figura no puede cerrar (lado o ángulo negativo) |
| `polygon_degenerate` / `polygon_repeated_point` | Puntos en una línea o dos puntos seguidos iguales |

## Pruebas

- Unitarias: `tests/unit/domain/measurements/test_measurement_polygon.py` (cuadrado, rectángulo,
  figura en L, datos que faltan, avisos y datos inválidos).
- Integración: `tests/integration/rest/polygons/test_polygons_api.py`.
