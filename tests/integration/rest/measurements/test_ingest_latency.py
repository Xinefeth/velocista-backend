"""EN-32 criterion 4: a batch of phone readings is answered in under 1 s.

Real PostgreSQL in an isolated schema (local only). The time covers the whole request:
validation, discard checks and the INSERT of the batch. The network of the phone is not included.

How the limit is applied (agreed with the EN-32 reviewer):
- Batch of 25 (the real size: the phone page sends about 30 readings every 0.5 s): the WORST of
  5 runs must be under 1 s. It takes about 30-60 ms, so the margin is large.
- Batch of 1000 (the API limit, a stress case): the MEDIAN of 5 runs must be under 1 s and the
  worst run under 2 s. On the development machine it takes 450-700 ms, a margin of only ~30 % over
  1 s, so judging the worst run alone would make the test fail on a slower or busy machine.
"""

from statistics import median
from time import perf_counter

import pytest

MEASUREMENTS = "/api/measurements"
LIMIT_S = 1.0
SAFETY_S = 2.0  # safety net for the worst run of a 1000-reading batch
REAL_BATCH = 100  # batches up to this size are what the phone really sends
REPEATS = 5  # the worst of several runs is compared, so one slow run does not decide alone


def batch(n: int, first_seq: int = 0) -> list[dict]:
    """n readings like the phone sends them: motion at 50 Hz, a GPS fix every 50 readings."""
    t0 = 1_730_592_000_000
    readings = []
    for i in range(n):
        seq = first_seq + i
        if i % 50 == 49:
            readings.append(
                {
                    "seq": seq,
                    "t_ms": t0 + seq * 20,
                    "kind": "gps",
                    "lat": -8.1116 + seq * 1e-6,
                    "lon": -79.0287,
                    "accuracy_m": 4.8,
                }
            )
        else:
            readings.append(
                {
                    "seq": seq,
                    "t_ms": t0 + seq * 20,
                    "kind": "motion",
                    "gyro_z_dps": 0.42,
                    "accel": [0.12, 0.31, 9.79],
                }
            )
    return readings


def new_measurement(client) -> int:
    response = client.post(
        MEASUREMENTS,
        json={
            "method": "gps",
            "place_name": "Latency",
            "device_id": "phone-latency",
            "closed": False,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def timed_post(client, measurement_id: int, readings: list[dict]) -> tuple[float, dict]:
    start = perf_counter()
    response = client.post(f"{MEASUREMENTS}/{measurement_id}/readings", json={"readings": readings})
    elapsed = perf_counter() - start
    assert response.status_code == 200, response.text
    return elapsed, response.json()


@pytest.mark.parametrize("size", [25, 1000])
def test_batch_is_answered_in_under_one_second(client, size, capsys):
    new_measurement_id = new_measurement(client)
    timed_post(client, new_measurement_id, batch(5))  # warm-up: connection and first query

    times = []
    for _ in range(REPEATS):
        measurement_id = new_measurement(client)
        elapsed, report = timed_post(client, measurement_id, batch(size))
        assert report["accepted"] == size
        assert report["duplicates"] == 0
        assert report["discarded"] == {}
        assert report["total_readings"] == size
        times.append(elapsed)

    with capsys.disabled():
        print(
            f"\n[latency] batch of {size}: min {min(times) * 1000:.0f} ms, "
            f"median {median(times) * 1000:.0f} ms, max {max(times) * 1000:.0f} ms "
            f"over {REPEATS} runs (limit {LIMIT_S * 1000:.0f} ms)"
        )
    if size <= REAL_BATCH:
        # The real size (the page sends ~30 readings every 0.5 s): the worst run must fit.
        assert max(times) < LIMIT_S, f"slowest batch of {size} took {max(times):.3f} s"
    else:
        # The 1000 limit is a stress case: the median decides, the worst run only needs a margin.
        assert median(times) < LIMIT_S, f"median batch of {size} took {median(times):.3f} s"
        assert max(times) < SAFETY_S, f"slowest batch of {size} took {max(times):.3f} s"


def test_resent_batch_of_1000_is_also_fast_and_not_duplicated(client):
    measurement_id = new_measurement(client)
    readings = batch(1000)
    timed_post(client, measurement_id, readings)
    elapsed, report = timed_post(client, measurement_id, readings)
    assert report["accepted"] == 0
    assert report["duplicates"] == 1000
    assert report["total_readings"] == 1000
    assert elapsed < SAFETY_S
