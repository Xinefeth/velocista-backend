"""Metrica y seleccion de la mejor vuelta; sin dependencias externas."""

import math


def calculate_j(time_s: float | None, accumulated_error: float, finished: bool) -> float:
    if not math.isfinite(accumulated_error) or accumulated_error < 0:
        raise ValueError("accumulated_error must be finite and non-negative")
    if time_s is not None and (not math.isfinite(time_s) or time_s < 0):
        raise ValueError("time_s must be finite and non-negative")
    return round(time_s + 2 * accumulated_error, 3) if finished and time_s is not None else 120.0


def best_lap(laps: list[dict]) -> dict:
    if not laps:
        raise ValueError("A closed run must contain laps")
    completed = [lap for lap in laps if lap["finished"]]
    return (
        min(
            completed,
            key=lambda lap: (
                calculate_j(lap["time_s"], lap["accumulated_error"], True),
                lap["number"],
            ),
        )
        if completed
        else laps[0]
    )
