"""Approximate time-to-closest-approach calculation in image coordinates."""
from math import hypot
from typing import Optional


def calculate_ttc(position_a: tuple[float, float], velocity_a: tuple[float, float],
                  position_b: tuple[float, float], velocity_b: tuple[float, float]) -> dict:
    """Return approximate TTC and closest separation; pixel speed is not calibrated to metres."""
    rx, ry = position_b[0] - position_a[0], position_b[1] - position_a[1]
    vx, vy = velocity_b[0] - velocity_a[0], velocity_b[1] - velocity_a[1]
    distance = hypot(rx, ry)
    speed_sq = vx * vx + vy * vy
    if distance < 1e-6 or speed_sq < 1e-6:
        return {"ttc": None, "valid": False, "distance_px": distance, "closest_distance_px": distance}
    t_closest = -(rx * vx + ry * vy) / speed_sq
    if t_closest <= 0:
        return {"ttc": None, "valid": False, "distance_px": distance, "closest_distance_px": distance}
    closest_x, closest_y = rx + vx * t_closest, ry + vy * t_closest
    closest_distance = hypot(closest_x, closest_y)
    closing_speed = -(rx * vx + ry * vy) / distance
    ttc: Optional[float] = distance / closing_speed if closing_speed > 1e-6 else None
    return {"ttc": ttc, "valid": ttc is not None, "distance_px": distance,
            "closest_distance_px": closest_distance, "time_to_closest_s": t_closest}
