# Pruebas funcionales con Swagger — Sprint 2 (EN-38)

Un caso por endpoint nuevo del sprint, con su petición, la respuesta esperada y su evidencia, como
FUN-01 a FUN-16 del Sprint 1 (la numeración sigue desde FUN-17). Incluye los casos de error:
datos inválidos (422), recurso inexistente (404) y estado incorrecto (409).

| Campo | Valor |
|---|---|
| Responsable | Tatiana Priscila Espejo Loyaga |
| Fecha | 4 de noviembre de 2026 |
| Enfoque | Caja negra funcional: solo entradas y salidas HTTP, como en Swagger (`/docs`) |
| Entorno | Backend local con PostgreSQL 16 de pruebas (base vacía), `AUTH_REQUIRED=false` |
| Resultado | **38 de 38 casos aprobados** (automatizado y en Swagger UI) |

## Cómo se ejecutan

1. **Automatizado** (en cada cambio): `pytest tests/functional`. Cada caso corre contra la API con
   PostgreSQL real en un esquema aislado y comprueba el código y los campos clave. Además verifica
   que Swagger documenta ese endpoint con ese código de respuesta.
2. **Evidencia JSON**: con `SWAGGER_EVIDENCE_DIR=docs/evidencias/swagger-sprint2`, cada caso guarda
   su petición y respuesta (las listas largas se recortan a 5 elementos).
3. **Captura de Swagger**: con el backend corriendo sobre una base de pruebas vacía,
   `scripts/swagger_evidence/make_plan.py` prepara los datos de cada caso y
   `scripts/swagger_evidence/capture.cjs` abre `/docs`, pulsa *Try it out*, escribe la petición,
   pulsa *Execute* y guarda la captura del bloque con la respuesta.

## Casos

| ID | Petición | Caso | Esperado | Obtenido | Resultado | Evidencia |
|---|---|---|---|---|---|---|
| FUN-17 | `GET /api/calibrations/new-phone` | Estado de calibración de un celular nuevo | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-17.json) · [captura](evidencias/swagger-sprint2/FUN-17.png) |
| FUN-18 | `POST /api/calibrations/phone-fun/gyro` | Calibrar el giroscopio con el celular quieto 5 s | 201 | 201 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-18.json) · [captura](evidencias/swagger-sprint2/FUN-18.png) |
| FUN-19 | `POST /api/calibrations/phone-fun/gyro` | Calibrar el giroscopio con el celular en movimiento (inválido) | 422 `calibration_phone_moved` | 422 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-19.json) · [captura](evidencias/swagger-sprint2/FUN-19.png) |
| FUN-20 | `POST /api/calibrations/phone-fun/step` | Calibrar el largo del paso caminando 20 m tres veces | 201 | 201 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-20.json) · [captura](evidencias/swagger-sprint2/FUN-20.png) |
| FUN-21 | `POST /api/calibrations/phone-fun/step` | Calibrar el paso con una distancia negativa (inválido) | 422 | 422 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-21.json) · [captura](evidencias/swagger-sprint2/FUN-21.png) |
| FUN-22 | `POST /api/calibrations/phone-fun/car` | Calibrar la velocidad del carro (v = k·PWM + c) | 201 | 201 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-22.json) · [captura](evidencias/swagger-sprint2/FUN-22.png) |
| FUN-23 | `GET /api/calibrations/phone-fun/history` | Historial de calibraciones de un celular | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-23.json) · [captura](evidencias/swagger-sprint2/FUN-23.png) |
| FUN-24 | `POST /api/measurements` | Empezar una medición por pasos con plano de referencia | 201 | 201 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-24.json) · [captura](evidencias/swagger-sprint2/FUN-24.png) |
| FUN-25 | `POST /api/measurements` | Empezar una medición con un método que no existe (inválido) | 422 | 422 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-25.json) · [captura](evidencias/swagger-sprint2/FUN-25.png) |
| FUN-26 | `POST /api/measurements` | Empezar una medición con el carro sin calibrarlo | 422 `measurement_not_calibrated` | 422 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-26.json) · [captura](evidencias/swagger-sprint2/FUN-26.png) |
| FUN-27 | `POST /api/measurements/1/readings` | Enviar un lote de lecturas del celular | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-27.json) · [captura](evidencias/swagger-sprint2/FUN-27.png) |
| FUN-28 | `POST /api/measurements/1/readings` | Reenviar el mismo lote no duplica lecturas e informa las inválidas | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-28.json) · [captura](evidencias/swagger-sprint2/FUN-28.png) |
| FUN-29 | `POST /api/measurements/999999/readings` | Enviar lecturas a una medición que no existe | 404 `measurement_not_found` | 404 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-29.json) · [captura](evidencias/swagger-sprint2/FUN-29.png) |
| FUN-30 | `POST /api/measurements/1/finish` | Terminar la medición: perímetro, área y error de cierre | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-30.json) · [captura](evidencias/swagger-sprint2/FUN-30.png) |
| FUN-31 | `POST /api/measurements/1/readings` | Enviar lecturas a una medición ya terminada | 409 `measurement_finished` | 409 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-31.json) · [captura](evidencias/swagger-sprint2/FUN-31.png) |
| FUN-32 | `GET /api/measurements/1` | Consultar una medición terminada | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-32.json) · [captura](evidencias/swagger-sprint2/FUN-32.png) |
| FUN-33 | `GET /api/measurements/999999` | Consultar una medición que no existe | 404 `measurement_not_found` | 404 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-33.json) · [captura](evidencias/swagger-sprint2/FUN-33.png) |
| FUN-34 | `GET /api/measurements` | Listar las mediciones de un celular | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-34.json) · [captura](evidencias/swagger-sprint2/FUN-34.png) |
| FUN-35 | `GET /api/measurements/1/readings` | Ver las lecturas guardadas de una medición | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-35.json) · [captura](evidencias/swagger-sprint2/FUN-35.png) |
| FUN-36 | `DELETE /api/measurements/1` | Borrar una medición equivocada | 204 | 204 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-36.json) · [captura](evidencias/swagger-sprint2/FUN-36.png) |
| FUN-37 | `DELETE /api/measurements/999999` | Borrar una medición que no existe | 404 `measurement_not_found` | 404 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-37.json) · [captura](evidencias/swagger-sprint2/FUN-37.png) |
| FUN-38 | `POST /api/gps-trials` | Registrar una prueba de error del GPS frente a la cinta | 201 | 201 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-38.json) · [captura](evidencias/swagger-sprint2/FUN-38.png) |
| FUN-39 | `POST /api/gps-trials` | Registrar una prueba del GPS con solo dos lecturas (inválido) | 422 | 422 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-39.json) · [captura](evidencias/swagger-sprint2/FUN-39.png) |
| FUN-40 | `GET /api/gps-trials/summary` | Resumen del error del GPS y lado mínimo del terreno | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-40.json) · [captura](evidencias/swagger-sprint2/FUN-40.png) |
| FUN-41 | `PATCH /api/gps-trials/1` | Cambiar el nombre de una prueba del GPS | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-41.json) · [captura](evidencias/swagger-sprint2/FUN-41.png) |
| FUN-42 | `DELETE /api/gps-trials/1` | Borrar una prueba del GPS equivocada | 204 | 204 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-42.json) · [captura](evidencias/swagger-sprint2/FUN-42.png) |
| FUN-43 | `DELETE /api/gps-trials/999999` | Borrar una prueba del GPS que no existe | 404 `gps_trial_not_found` | 404 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-43.json) · [captura](evidencias/swagger-sprint2/FUN-43.png) |
| FUN-44 | `POST /api/precision-model/runs` | Correr el modelo de precisión con mediciones repetidas | 201 | 201 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-44.json) · [captura](evidencias/swagger-sprint2/FUN-44.png) |
| FUN-45 | `POST /api/precision-model/runs` | Correr el modelo con mediciones que no existen | 404 `measurement_not_found` | 404 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-45.json) · [captura](evidencias/swagger-sprint2/FUN-45.png) |
| FUN-46 | `GET /api/precision-model/runs` | Listar las corridas del modelo | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-46.json) · [captura](evidencias/swagger-sprint2/FUN-46.png) |
| FUN-47 | `POST /api/precision-model/evaluations` | Evaluar el modelo frente al algoritmo solo (línea base) | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-47.json) · [captura](evidencias/swagger-sprint2/FUN-47.png) |
| FUN-48 | `POST /api/precision-model/evaluations` | Evaluar el modelo con una sola medición (inválido) | 422 | 422 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-48.json) · [captura](evidencias/swagger-sprint2/FUN-48.png) |
| FUN-49 | `POST /api/polygons/solve` | Cerrar una figura en L con un ángulo y dos lados que faltan | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-49.json) · [captura](evidencias/swagger-sprint2/FUN-49.png) |
| FUN-50 | `POST /api/polygons/solve` | Cerrar una figura con datos insuficientes | 422 `polygon_underdetermined` | 422 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-50.json) · [captura](evidencias/swagger-sprint2/FUN-50.png) |
| FUN-51 | `POST /api/polygons/from-points` | Área y ángulos de una figura en L marcada por puntos | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-51.json) · [captura](evidencias/swagger-sprint2/FUN-51.png) |
| FUN-52 | `POST /api/polygons/from-points` | Puntos cuyos lados se cruzan: avisa | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-52.json) · [captura](evidencias/swagger-sprint2/FUN-52.png) |
| FUN-53 | `GET /api/profiles` | Listar los perfiles de reglamento | 200 | 200 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-53.json) · [captura](evidencias/swagger-sprint2/FUN-53.png) |
| FUN-54 | `GET /api/profiles/no-such-profile` | Consultar un perfil de reglamento que no existe | 404 `profile_not_found` | 404 | Aprobado | [JSON](evidencias/swagger-sprint2/FUN-54.json) · [captura](evidencias/swagger-sprint2/FUN-54.png) |

Los identificadores de la columna *Petición* son los de la ejecución automatizada (esquema
aislado); en las capturas los ids pueden ser otros porque se usa otra base.

## Cobertura por endpoint

| Etiqueta Swagger | Endpoints | Casos |
|---|---|---|
| `calibration` (EN-35) | 5 | FUN-17 a FUN-23 |
| `measurements` (EN-32, EN-33, EN-34) | 7 | FUN-24 a FUN-37 |
| `gps` (SP-06) | 5 | FUN-38 a FUN-43 |
| `precision-model` (SP-07) | 3 | FUN-44 a FUN-48 |
| `polygons` (EN-42) | 2 | FUN-49 a FUN-52 |
| `rules` (HU-9) | 2 | FUN-53 y FUN-54 |

## Pendiente

- `GET /api/robots/{id}/compliance` (HU-9) todavía no existe en el backend; su caso se agrega
  cuando se implemente.
- Los endpoints de corridas, vueltas y estudio se prueban en el siguiente sprint (criterio de EN-38).
