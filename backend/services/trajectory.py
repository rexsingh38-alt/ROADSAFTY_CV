"""Trajectory helpers used to estimate whether object paths are converging."""
from math import hypot


def center(box: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def direction(previous: tuple[float, float] | None, current: tuple[float, float], dt: float) -> tuple[float, float]:
    if previous is None or dt <= 0:
        return (0.0, 0.0)
    return ((current[0] - previous[0]) / dt, (current[1] - previous[1]) / dt)


def paths_conflict(prediction: dict, threshold_px: float) -> bool:
    return prediction["valid"] and prediction["time_to_closest_s"] > 0 and prediction["closest_distance_px"] <= threshold_px


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot(b[0] - a[0], b[1] - a[1])
