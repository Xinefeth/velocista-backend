# Evaluación del modelo que reajusta la precisión (SP-07)

Responde la pregunta del profesor: **¿baja el error de la medición si un modelo reajusta los
parámetros con mediciones repetidas?** Compara el algoritmo solo (línea base) con el algoritmo
más el modelo de refuerzo simple de `tuning.py` (sección 4.5 de [MEDICIONES.md](MEDICIONES.md)).

## Cómo se evalúa

| Paso | Qué se calcula |
|---|---|
| Línea base (sin modelo) | Error de cierre en m y en % de cada medición con **su propia** calibración del paso y del giroscopio (el algoritmo tal como midió) |
| Con modelo | El mismo error con los parámetros que ajustó el modelo |
| Curva | Error de cierre medio por intento, con y sin modelo (para el gráfico) |
| Validación | La última medición no se usa para ajustar: comprueba si el modelo generaliza |
| Veredicto | `improves_green` (baja y queda bajo 3 %), `improves_not_green` (baja pero no llega a verde) o `no_improvement` (no baja: queda como trabajo futuro) |

La evaluación **no guarda nada** ni cambia la calibración del celular.

- API: `POST /api/precision-model/evaluations` con `{"measurement_ids": [...], "max_attempts": 40}`
  (en Swagger, etiqueta `precision-model`).
- Línea de comandos, sobre una base con mediciones guardadas:

  ```powershell
  .\.venv\Scripts\python.exe scripts\evaluate_precision_model.py 10 11 12 13 --attempts 60
  ```

## Resultados con datos reales (3 de noviembre, celular `cel-621b8d99`)

Mediciones por pasos de Tatiana en su casa (`mediciones_tatiana.sql`), 60 intentos. Cada grupo es
el mismo ambiente medido varias veces; el plano viene de las medidas tomadas con cinta.

| Ambiente (plano) | Mediciones (validación) | Cierre sin modelo | Cierre con modelo | Mejora | Error vs plano sin → con | ¿Generaliza? | Veredicto |
|---|---|---|---|---|---|---|---|
| 6 × 4 m | 10, 11, 12 (13) | 7,53 % | 5,39 % | 2,14 pts | 40,7 % → 9,4 % | Sí | Baja, no llega a verde |
| 4 × 4 m | 24, 25 (26) | 10,20 % | 7,10 % | 3,10 pts | 7,1 % → 4,5 % | No | Baja, no llega a verde |
| 6 × 6 m | 20, 23 | 14,09 % | 14,22 % | −0,13 pts | 19,3 % → 0,6 % | — | No baja el cierre |
| 4 × 6 m | 8, 9 | 8,19 % | 8,10 % | 0,08 pts | 65,9 % → 34,0 % | — | Baja, no llega a verde |
| Todas juntas | 10 mediciones (26) | 9,08 % | 8,63 % | 0,45 pts | 34,3 % → 31,0 % | No | Baja, no llega a verde |

### Conclusión

1. **El modelo sí baja el error, pero no llega al límite verde (3 %).** En el mejor ambiente baja
   el cierre de 7,5 % a 5,4 % y lo pasa de rojo a amarillo. Según el criterio de SP-07, esto se
   declara: **con estos datos el modelo no alcanza verde y queda como trabajo futuro**.
2. **Lo que más mejora es el error frente al plano** (de 40,7 % a 9,4 % en el ambiente 6 × 4):
   el modelo corrige el largo del paso, que la calibración de 20 m no estimó bien en interiores.
3. **El error de cierre casi no baja** porque depende sobre todo del giroscopio y del recorrido de
   cada vuelta (ruido), no de un sesgo fijo que el modelo pueda aprender.
4. **Generaliza poco:** solo uno de los dos grupos con validación mejora en la medición apartada.
   Con 2 a 4 mediciones por ambiente hay muy pocos datos. Para concluir con más seguridad hacen
   falta al menos 5 mediciones del mismo lugar (HU-39) y repetir la evaluación.

### Datos sintéticos (simulador de pruebas)

Con el simulador de `tests/support` (paso mal calibrado 0,77 m en vez de 0,70 m y giroscopio sin
calibrar), el modelo sí llega a verde y generaliza. Las pruebas `test_measurement_evaluation.py`
lo comprueban. Sirve para validar el código, no como resultado final.
