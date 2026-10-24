"""Location-level event aggregation helpers."""
from sqlalchemy import case, func

from config import DEMO_MODE
from models import Location, NearMissEvent, Video


def aggregate_hotspots(db) -> list[dict]:
    query = (db.query(Location, func.count(NearMissEvent.id),
                     func.sum(case((NearMissEvent.risk_level == "HIGH", 1), else_=0)),
                     func.sum(case((NearMissEvent.risk_level == "MEDIUM", 1), else_=0)),
                     func.avg(NearMissEvent.ttc))
            .join(NearMissEvent, NearMissEvent.location_id == Location.id)
            )
    if not DEMO_MODE:
        query = query.join(Video, Video.id == NearMissEvent.video_id).filter(Video.frame_count > 0)
    rows = query.group_by(Location.id).all()
    results = []
    for location, total, high, medium, average_ttc in rows:
        risk = "HIGH" if (high or 0) > 0 else "MEDIUM" if (medium or 0) > 0 else "LOW"
        results.append({"location": location.name, "latitude": location.latitude,
                        "longitude": location.longitude, "total_events": int(total),
                        "high_risk_events": int(high or 0),
                        "average_ttc": round(float(average_ttc), 2) if average_ttc is not None else None,
                        "risk_level": risk})
    return sorted(results, key=lambda item: (item["high_risk_events"], item["total_events"]), reverse=True)
