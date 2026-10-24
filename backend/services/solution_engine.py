"""Explainable, rule-based safety recommendations for analyzed CCTV clips."""


def _is_vehicle(value: str | None) -> bool:
    return (value or "").lower() in {"car", "truck", "bus", "motorcycle", "vehicle"}


def solution_for_event(event, repeated_at_location: bool = False) -> dict:
    first = (event.class_a or "object").lower()
    second = (event.class_b or "unknown").lower()
    objects = [name for name in (first, second) if name != "unknown"]
    is_collision = event.type == "COLLISION"
    factors = []
    actions = []

    if is_collision:
        factors.append(f"The video analysis classified a possible impact involving {' and '.join(objects) or 'a road user'}.")
        actions.extend([
            "Flag this location for an authority review and verify the original footage.",
            "Inspect junction geometry, sight lines, and traffic-control measures.",
            "Review the event with incident records and any available witness or camera footage.",
        ])
    elif "person" in objects or "pedestrian" in objects:
        factors.append("A vehicle-pedestrian conflict was detected; crossing exposure may be a contributing factor.")
        actions.extend([
            "Review pedestrian-crossing visibility, markings, and approach sight lines.",
            "Review pedestrian signal timing and crossing placement.",
            "Assess speed-management measures and monitor the crossing during peak periods.",
        ])
    elif any(name in objects for name in ("motorcycle", "bicycle", "bike")):
        factors.append("A motor vehicle and two-wheeler interaction was detected; lane separation or merging may contribute.")
        actions.extend([
            "Review lane markings, merge points, and two-wheeler separation.",
            "Check warning-sign visibility and peak-hour traffic flow at this location.",
        ])
    elif _is_vehicle(first) and _is_vehicle(second):
        factors.append("A vehicle-to-vehicle conflict was detected; lane interaction or following distance may contribute.")
        actions.extend([
            "Review lane markings, turning paths, and merge arrangements.",
            "Check whether approach warnings and traffic-control measures are clear.",
            "Review peak-hour flow and vehicle separation at the conflict point.",
        ])
    elif "ROADSIDE" in event.subtype.upper() or "BARRIER" in event.subtype.upper():
        factors.append("The tracked vehicle showed a possible roadside-stop or barrier-impact pattern.")
        actions.extend([
            "Inspect the road edge, shoulder, roadside objects, and safety barriers.",
            "Review visibility and road geometry around the detected stop location.",
        ])
    else:
        factors.append("A close interaction was detected; review the video context to identify the contributing road layout or movement.")
        actions.append("Review the event frame, road layout, and traffic-control measures.")

    if "ROADSIDE" in event.subtype.upper() or "BARRIER" in event.subtype.upper():
        factors.append("The detector also reported a possible roadside or barrier-impact pattern.")
        actions.append("Inspect the road edge, shoulder, roadside objects, and safety barriers.")

    if event.ttc_seconds is not None and event.ttc_seconds <= 1.5:
        factors.append(f"Estimated TTC was short ({event.ttc_seconds:.2f} s), indicating limited reaction time.")
        actions.append("Assess approach speeds and sight distance; the video does not establish a measured road speed.")
    if event.subtype:
        factors.append(f"Detector pattern: {event.subtype.replace('_', ' ').lower()}.")
    if repeated_at_location:
        factors.append("Other incidents are already recorded at this location, suggesting a recurring point to review.")
        actions.append("Prioritize a location-level safety assessment using previous incident records.")

    severity = event.peak_severity
    priority = "CRITICAL" if is_collision else "HIGH" if severity >= 75 or (event.ttc_seconds is not None and event.ttc_seconds <= 1.5) or repeated_at_location else "MEDIUM" if severity >= 50 else "LOW"
    risk = "HIGH" if priority in {"CRITICAL", "HIGH"} else "MEDIUM" if priority == "MEDIUM" else "LOW"
    return {
        "incident_id": str(event.incident_id),
        "event_type": event.type,
        "start_time_seconds": round(event.start_time, 2),
        "end_time_seconds": round(event.end_time, 2),
        "detector_pattern": event.subtype or "motion analysis",
        "objects": objects,
        "severity": round(severity, 1),
        "ttc_seconds": event.ttc_seconds,
        "priority": priority,
        "risk_level": risk,
        "possible_contributing_factors": list(dict.fromkeys(factors)),
        "recommended_actions": list(dict.fromkeys(actions)),
        "note": "These are review suggestions based on video patterns, not a confirmed cause or legal finding.",
    }


def build_video_solution(incidents, repeated_at_location: bool = False) -> dict:
    per_event = [solution_for_event(event, repeated_at_location) for event in incidents]
    collisions = sum(event.type == "COLLISION" for event in incidents)
    near_misses = sum(event.type == "NEAR_MISS" for event in incidents)
    priority_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    priority = max((item["priority"] for item in per_event), key=priority_order.get, default="LOW")
    risk_level = "HIGH" if priority in {"HIGH", "CRITICAL"} else "MEDIUM" if priority == "MEDIUM" else "LOW"
    factors = list(dict.fromkeys(factor for item in per_event for factor in item["possible_contributing_factors"]))
    actions = list(dict.fromkeys(action for item in per_event for action in item["recommended_actions"]))
    if not incidents:
        factors = ["No qualifying near-miss or collision event was reported for this video."]
        actions = ["Review the analyzed footage if an incident is visible, then continue monitoring this location."]
    return {
        "total_events": len(incidents),
        "near_misses": near_misses,
        "collisions": collisions,
        "risk_level": risk_level,
        "priority": priority,
        "possible_contributing_factors": factors,
        "recommended_actions": actions,
        "event_solutions": per_event,
        "note": "Recommendations are rule-based review guidance. CCTV alone cannot confirm the actual cause.",
    }
