"""Controladores REST del contexto `measurements`. Solo reciben, validan formato y delegan.

Flujo del celular (EN-32 a EN-35):
1. GET  /api/calibrations/{device_id}          ¿está calibrado?
2. POST /api/calibrations/{device_id}/gyro     celular quieto 5 s
   POST /api/calibrations/{device_id}/step     caminar 20 m tres veces
3. POST /api/measurements                      empezar (copia la calibración vigente)
4. POST /api/measurements/{id}/readings        cada ~0,5 s un lote de lecturas
5. POST /api/measurements/{id}/finish          calcular perímetro, área y error de cierre
6. DELETE /api/measurements/{id}               borrar una equivocada o cancelada
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from velocista.application.measurements.use_cases import (
    CalibrationService,
    GpsErrorService,
    MeasurementsService,
    PrecisionModelService,
)
from velocista.composition import (
    get_calibration_service,
    get_gps_error_service,
    get_measurements_service,
    get_precision_model_service,
)
from velocista.domain.measurements.validation import DEVICE_MAX
from velocista.interface.rest.errors import error_responses
from velocista.interface.rest.measurements.schemas import (
    CalibrationOut,
    CalibrationRecordOut,
    CalibrationStateOut,
    CarCalibrationIn,
    GpsSummaryOut,
    GpsTrialIn,
    GpsTrialOut,
    GpsTrialRenameIn,
    GyroCalibrationIn,
    IngestReportOut,
    MeasurementIn,
    MeasurementOut,
    MeasurementsPage,
    ModelEvaluationIn,
    ModelEvaluationOut,
    ModelRunIn,
    ModelRunOut,
    ReadingOut,
    ReadingsBatchIn,
    StepCalibrationIn,
)

Measurements = Annotated[MeasurementsService, Depends(get_measurements_service)]
Calibrations = Annotated[CalibrationService, Depends(get_calibration_service)]
GpsErrors = Annotated[GpsErrorService, Depends(get_gps_error_service)]
Model = Annotated[PrecisionModelService, Depends(get_precision_model_service)]
MeasurementId = Annotated[int, Path(ge=1, le=9007199254740991)]
DevicePath = Annotated[str, Path(min_length=1, max_length=DEVICE_MAX)]
DeviceQuery = Annotated[str | None, Query(min_length=1, max_length=DEVICE_MAX)]

UNAUTHORIZED = "Missing, expired or tampered token (`unauthorized`)"
NOT_FOUND = "Measurement does not exist (`measurement_not_found`)"
INVALID = "Invalid body or a domain rule failed (`{detail: {reason, detail}}`)"
UNITS = "Distances in metres, times in epoch milliseconds."

measurements = APIRouter(prefix="/api/measurements", tags=["measurements"])
calibrations = APIRouter(prefix="/api/calibrations", tags=["calibration"])
gps_trials = APIRouter(prefix="/api/gps-trials", tags=["gps"])
precision = APIRouter(prefix="/api/precision-model", tags=["precision-model"])


# ------------------------------------------------------------- mediciones (EN-32, EN-33, EN-34)


@measurements.post(
    "",
    status_code=201,
    response_model=MeasurementOut,
    operation_id="startMeasurement",
    summary="Start a measurement",
    description=(
        "Creates a measurement in `recording` status and freezes the current calibration of the "
        "phone. `steps` needs a step calibration and `car` a speed calibration "
        "(`measurement_not_calibrated`). `reference` is the plan to compare with (scale 1:N). "
        + UNITS
    ),
    responses=error_responses({401: UNAUTHORIZED, 422: INVALID}),
)
def start_measurement(data: MeasurementIn, service: Measurements):
    return MeasurementOut.from_entity(service.start(data.to_entity()))


@measurements.get(
    "",
    response_model=MeasurementsPage,
    operation_id="listMeasurements",
    summary="List measurements",
    description="Most recent first. Paths are left out; get one measurement to see them.",
    responses=error_responses({401: UNAUTHORIZED}),
)
def list_measurements(
    service: Measurements,
    device_id: DeviceQuery = None,
    place_name: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=9007199254740991)] = 0,
):
    page = service.list(limit=limit, offset=offset, device_id=device_id, place_name=place_name)
    return MeasurementsPage(
        items=[MeasurementOut.from_entity(m, paths=False) for m in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@measurements.get(
    "/{measurement_id}",
    response_model=MeasurementOut,
    operation_id="getMeasurement",
    summary="Get a measurement with its result and paths",
    description=(
        "Returns the measurement, the calibration it used and, once finished, the result with "
        "the raw path, the corrected path and the polygon used for perimeter and area. " + UNITS
    ),
    responses=error_responses({401: UNAUTHORIZED, 404: NOT_FOUND}),
)
def get_measurement(measurement_id: MeasurementId, service: Measurements):
    return MeasurementOut.from_entity(service.get(measurement_id))


@measurements.post(
    "/{measurement_id}/readings",
    response_model=IngestReportOut,
    operation_id="ingestReadings",
    summary="Send a batch of phone readings",
    description=(
        "Ingestion (EN-32). Send up to 1000 readings per call, about every 0.5 s. Each reading "
        "is `motion` (gyroscope, accelerometer with gravity, optional step or PWM), `gps` "
        "(lat, lon, accuracy_m) or `corner`. Invalid readings are discarded and counted by "
        "reason; a repeated `seq` is ignored, so a batch can be retried safely. 409 "
        "`measurement_finished` after finishing. " + UNITS
    ),
    responses=error_responses(
        {
            401: UNAUTHORIZED,
            404: NOT_FOUND,
            409: "Measurement finished or too many readings",
        }
    ),
)
def ingest_readings(measurement_id: MeasurementId, data: ReadingsBatchIn, service: Measurements):
    report = service.ingest(measurement_id, [r.to_entity() for r in data.readings])
    return IngestReportOut(**report.__dict__)


@measurements.get(
    "/{measurement_id}/readings",
    response_model=list[ReadingOut],
    operation_id="listMeasurementReadings",
    summary="Raw readings of a measurement",
    description=(
        "Every stored reading ordered by time, to audit or re-process a walk. Each reading "
        "carries the `mount` (`hand` or `robot`) of its measurement; `method: car` implies "
        "`robot`. " + UNITS
    ),
    responses=error_responses({401: UNAUTHORIZED, 404: NOT_FOUND}),
)
def list_readings(measurement_id: MeasurementId, service: Measurements):
    mount, readings = service.readings_with_mount(measurement_id)
    return [ReadingOut.from_entity(r, mount) for r in readings]


@measurements.post(
    "/{measurement_id}/finish",
    response_model=MeasurementOut,
    operation_id="finishMeasurement",
    summary="Finish and compute perimeter, area and closure error",
    description=(
        "Computes the result (EN-34) and marks the measurement `finished`. Calling it again "
        "recomputes. `quality`: green < 3 % closure error, yellow up to 6 %, red above. "
        "422 `measurement_too_short` if there are too few steps or GPS readings."
    ),
    responses=error_responses({401: UNAUTHORIZED, 404: NOT_FOUND, 422: INVALID}),
)
def finish_measurement(measurement_id: MeasurementId, service: Measurements):
    return MeasurementOut.from_entity(service.finish(measurement_id))


@measurements.delete(
    "/{measurement_id}",
    status_code=204,
    operation_id="deleteMeasurement",
    summary="Delete a measurement",
    description=(
        "Deletes the measurement and all its readings permanently (a mistaken or cancelled "
        "walk) and answers 204 with no body. Calibrations and GPS trials are kept."
    ),
    responses=error_responses({401: UNAUTHORIZED, 404: NOT_FOUND}),
)
def delete_measurement(measurement_id: MeasurementId, service: Measurements):
    service.delete(measurement_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ calibración (EN-35)


def _state(device_id: str, service: CalibrationService) -> CalibrationStateOut:
    cal, records = service.current(device_id)
    return CalibrationStateOut(
        device_id=device_id,
        calibration=CalibrationOut(**cal.__dict__),
        ready={
            "steps": bool(cal.step_length_m),
            "car": cal.speed_k is not None,
            "gps": True,
        },
        records={k: CalibrationRecordOut.from_entity(r) for k, r in records.items()},
    )


@calibrations.get(
    "/{device_id}",
    response_model=CalibrationStateOut,
    operation_id="getCalibration",
    summary="Current calibration of a phone",
    description=(
        "The newest calibration of each kind and which methods are ready to measure "
        "(`ready.steps` needs a step length, `ready.car` a speed model; GPS needs none)."
    ),
    responses=error_responses({401: UNAUTHORIZED}),
)
def get_calibration(device_id: DevicePath, service: Calibrations):
    return _state(device_id, service)


@calibrations.get(
    "/{device_id}/history",
    response_model=list[CalibrationRecordOut],
    operation_id="listCalibrations",
    summary="All calibrations of a phone, newest first",
    description="Manual calibrations and the ones saved by the precision model (`origin`).",
    responses=error_responses({401: UNAUTHORIZED}),
)
def list_calibrations(device_id: DevicePath, service: Calibrations):
    return [CalibrationRecordOut.from_entity(r) for r in service.history(device_id)]


@calibrations.post(
    "/{device_id}/gyro",
    status_code=201,
    response_model=CalibrationRecordOut,
    operation_id="calibrateGyro",
    summary="Calibrate the gyroscope (phone still ~5 s)",
    description=(
        "The mean rotation rate while still is the gyroscope bias; it is subtracted from every "
        "reading. Needs 30+ samples over 3+ s; 422 `calibration_phone_moved` if it moved."
    ),
    responses=error_responses({401: UNAUTHORIZED, 422: INVALID}),
)
def calibrate_gyro(device_id: DevicePath, data: GyroCalibrationIn, service: Calibrations):
    record = service.gyro(device_id, [(s.t_ms, s.gyro_z_dps) for s in data.samples])
    return CalibrationRecordOut.from_entity(record)


@calibrations.post(
    "/{device_id}/step",
    status_code=201,
    response_model=CalibrationRecordOut,
    operation_id="calibrateStep",
    summary="Calibrate the step length (walk a taped distance 3 times)",
    description=(
        "Each trial sends the tape distance and either `step_count` or the accelerometer "
        "`readings` of the walk (then the backend counts the steps with the same detector it "
        "uses to measure). Warns `uneven_pace` if the trials differ by more than 2 cm."
    ),
    responses=error_responses({401: UNAUTHORIZED, 422: INVALID}),
)
def calibrate_step(device_id: DevicePath, data: StepCalibrationIn, service: Calibrations):
    trials = [
        (
            t.distance_m,
            t.step_count,
            [r.to_entity() for r in t.readings] if t.readings is not None else None,
        )
        for t in data.trials
    ]
    return CalibrationRecordOut.from_entity(service.step(device_id, trials))


@calibrations.post(
    "/{device_id}/car",
    status_code=201,
    response_model=CalibrationRecordOut,
    operation_id="calibrateCarSpeed",
    summary="Calibrate the car speed model v = k·PWM + c",
    description="Run the car over taped distances with different PWM; least squares fit.",
    responses=error_responses({401: UNAUTHORIZED, 422: INVALID}),
)
def calibrate_car(device_id: DevicePath, data: CarCalibrationIn, service: Calibrations):
    record = service.car(device_id, [(t.pwm, t.distance_m, t.seconds) for t in data.trials])
    return CalibrationRecordOut.from_entity(record)


# ------------------------------------------------------------------ error del GPS (SP-06)


@gps_trials.post(
    "",
    status_code=201,
    response_model=GpsTrialOut,
    operation_id="createGpsTrial",
    summary="Save a GPS error trial against a taped distance",
    description=(
        "Stand still ~20 s on the start point and on the end point. The error of the GPS "
        "distance against the tape is computed with a single reading, the mean and the "
        "filtered mean (drops readings worse than the median, weights by 1/accuracy²). "
        "`real_distance_m` 0 means returning to the same point."
    ),
    responses=error_responses({401: UNAUTHORIZED, 422: INVALID}),
)
def create_gps_trial(data: GpsTrialIn, service: GpsErrors):
    return GpsTrialOut.from_entity(service.add_trial(data.to_entity()))


@gps_trials.get(
    "",
    response_model=list[GpsTrialOut],
    operation_id="listGpsTrials",
    summary="List GPS error trials",
    description="Newest first; filter by phone with `device_id`.",
    responses=error_responses({401: UNAUTHORIZED}),
)
def list_gps_trials(service: GpsErrors, device_id: DeviceQuery = None):
    return [GpsTrialOut.from_entity(t) for t in service.list(device_id)]


@gps_trials.patch(
    "/{trial_id}",
    response_model=GpsTrialOut,
    operation_id="renameGpsTrial",
    summary="Rename a GPS error trial",
    description="Fixes the place name only; readings and errors stay the same.",
    responses=error_responses(
        {401: UNAUTHORIZED, 404: "GPS trial does not exist (`gps_trial_not_found`)", 422: INVALID}
    ),
)
def rename_gps_trial(trial_id: MeasurementId, data: GpsTrialRenameIn, service: GpsErrors):
    return GpsTrialOut.from_entity(service.rename(trial_id, data.place_name))


@gps_trials.delete(
    "/{trial_id}",
    status_code=204,
    operation_id="deleteGpsTrial",
    summary="Delete a GPS error trial",
    description=(
        "Deletes a mistaken trial permanently and answers 204 with no body; the summary stops "
        "counting it."
    ),
    responses=error_responses(
        {401: UNAUTHORIZED, 404: "GPS trial does not exist (`gps_trial_not_found`)"}
    ),
)
def delete_gps_trial(trial_id: MeasurementId, service: GpsErrors):
    service.delete(trial_id)
    return Response(status_code=204)


@gps_trials.get(
    "/summary",
    response_model=GpsSummaryOut,
    operation_id="getGpsErrorSummary",
    summary="GPS error summary and minimum field size",
    description=(
        "Mean and max error per method, the best method, how much it improves over a single "
        "reading, and `min_side_m`: the smallest side for which the GPS error stays below "
        "`target_pct` % (uses the max error of the best method). Also, per environment "
        "(`environments`), error against the taped distance (`by_distance`, `error_trend`), "
        "the accuracy threshold to wait for before measuring (`by_accuracy`, "
        "`recommended_accuracy_m`), how long to stand still (`by_wait`), the accuracy the phone "
        "reports against the real error (`reported_vs_real`), warnings when there are fewer "
        "than `min_trials` trials, and a `conclusion`. `target_pct` and `min_trials` default to "
        "the server settings (GPS_TARGET_PCT, GPS_MIN_TRIALS)."
    ),
    responses=error_responses({401: UNAUTHORIZED, 422: INVALID}),
)
def gps_summary(
    service: GpsErrors,
    device_id: DeviceQuery = None,
    target_pct: Annotated[float | None, Query(gt=0, le=100)] = None,
    min_trials: Annotated[int | None, Query(ge=1, le=1000)] = None,
) -> dict:
    return service.summary(device_id, target_pct, min_trials)


# ------------------------------------------------------------------ modelo de precisión (SP-07)


@precision.post(
    "/runs",
    status_code=201,
    response_model=ModelRunOut,
    operation_id="runPrecisionModel",
    summary="Tune gyro bias and step length with repeated measurements",
    description=(
        "Simple reinforcement tuning (trial and error with a penalty = closure error % + "
        "|perimeter error vs plan| %). Uses repeated measurements of the same place; the last "
        "one is kept out to check the model generalizes. `attempts` gives the error by "
        "attempt for the chart. With `apply`, saves the tuned values as the phone calibration "
        "only when they improve."
    ),
    responses=error_responses({401: UNAUTHORIZED, 404: NOT_FOUND, 422: INVALID}),
)
def run_model(data: ModelRunIn, service: Model):
    run = service.run(data.measurement_ids, data.max_attempts, data.apply)
    return ModelRunOut.from_entity(run)


@precision.get(
    "/runs",
    response_model=list[ModelRunOut],
    operation_id="listPrecisionModelRuns",
    summary="List precision model runs",
    description="Newest first, with the error by attempt of each run; filter with `device_id`.",
    responses=error_responses({401: UNAUTHORIZED}),
)
def list_runs(service: Model, device_id: DeviceQuery = None):
    return [ModelRunOut.from_entity(r) for r in service.list(device_id)]


@precision.post(
    "/evaluations",
    response_model=ModelEvaluationOut,
    operation_id="evaluatePrecisionModel",
    summary="Compare the algorithm alone with the algorithm plus the precision model",
    description=(
        "SP-07 evaluation. Baseline = closure error (m and %) of each measurement with the "
        "calibration it was measured with; model = the same after tuning. `curve` gives the mean "
        "closure error by attempt with and without the model; `verdict` compares it with the "
        "green limit (< 3 %). Nothing is saved and the phone calibration does not change."
    ),
    responses=error_responses({401: UNAUTHORIZED, 404: NOT_FOUND, 422: INVALID}),
)
def evaluate_model(data: ModelEvaluationIn, service: Model):
    return service.evaluate(data.measurement_ids, data.max_attempts)


router = APIRouter()
for _sub in (measurements, calibrations, gps_trials, precision):
    router.include_router(_sub)
