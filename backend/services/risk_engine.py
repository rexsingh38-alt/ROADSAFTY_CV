"""Small configurable rule-based near-miss risk classifier."""
from config import HIGH_RISK_TTC_SECONDS, MEDIUM_RISK_TTC_SECONDS, MAX_CONFLICT_DISTANCE_PX


def classify_risk(ttc: float | None, ttc_valid: bool, distance_px: float,
                  trajectory_conflict: bool) -> str:
    if ttc_valid and ttc is not None and ttc <= HIGH_RISK_TTC_SECONDS:
        return "HIGH"
    if trajectory_conflict and (not ttc_valid or ttc is None or ttc <= MEDIUM_RISK_TTC_SECONDS):
        return "HIGH" if distance_px <= MAX_CONFLICT_DISTANCE_PX * 0.45 else "MEDIUM"
    if ttc_valid and ttc is not None and ttc <= MEDIUM_RISK_TTC_SECONDS:
        return "MEDIUM"
    if trajectory_conflict or distance_px <= MAX_CONFLICT_DISTANCE_PX:
        return "MEDIUM"
    return "LOW"
