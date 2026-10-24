"""Database-backed reports for near misses and collision incidents."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from config import DEMO_MODE
from database import get_db
from models import Location, NearMissEvent, Video
from api.events import serialize_event

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/traffic-safety")
def traffic_safety_report(days: int = Query(7, ge=1, le=365),
                          location: str | None = Query(None, max_length=120),
                          risk_level: str | None = Query(None, pattern="^(LOW|MEDIUM|HIGH)$"),
                          db: Session = Depends(get_db)):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = (db.query(NearMissEvent, Location.name)
             .join(Location, NearMissEvent.location_id == Location.id)
             .filter(NearMissEvent.timestamp >= cutoff))
    if not DEMO_MODE:
        query = query.join(Video, Video.id == NearMissEvent.video_id).filter(Video.frame_count > 0)
    if location:
        query = query.filter(Location.name == location)
    if risk_level:
        query = query.filter(NearMissEvent.risk_level == risk_level.upper())
    rows = query.order_by(NearMissEvent.timestamp.desc()).limit(5000).all()
    events = [serialize_event(event, name) for event, name in rows]
    collisions = sum(event["event_type"] == "COLLISION" for event in events)
    near_misses = sum(event["event_type"] == "NEAR_MISS" for event in events)
    risks = {level: sum(event["risk_level"] == level for event in events)
             for level in ("HIGH", "MEDIUM", "LOW")}
    average_ttc_values = [event["ttc"] for event in events if event["ttc"] is not None]
    locations = {}
    for event in events:
        locations[event["location"]] = locations.get(event["location"], 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period_days": days,
        "location_filter": location or "All locations",
        "risk_filter": risk_level or "All risk levels",
        "summary": {
            "total_incidents": len(events), "near_misses": near_misses,
            "collisions": collisions, "high_risk": risks["HIGH"],
            "medium_risk": risks["MEDIUM"], "low_risk": risks["LOW"],
            "high_risk_rate": round(risks["HIGH"] * 100 / len(events), 1) if events else 0,
            "average_ttc_seconds": round(sum(average_ttc_values) / len(average_ttc_values), 2) if average_ttc_values else None,
        },
        "events_by_location": locations,
        "events": events,
    }
