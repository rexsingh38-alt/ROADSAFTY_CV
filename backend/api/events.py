"""Near-miss event listing, filtering, detail, and deletion."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from config import DEMO_MODE
from models import Location, NearMissEvent, Video
from schemas import EventResponse

router = APIRouter(prefix="/api/events", tags=["events"])


def serialize_event(event: NearMissEvent, location_name: str) -> dict:
    return {"event_id": event.id, "timestamp": event.timestamp, "video_id": event.video_id,
            "object_1_id": event.object_1_id, "object_1_type": event.object_1_type,
            "object_2_id": event.object_2_id, "object_2_type": event.object_2_type,
            "event_type": event.event_type or "NEAR_MISS",
            "ttc": event.ttc, "ttc_valid": bool(event.ttc_valid), "risk_level": event.risk_level,
            "location": location_name, "relative_distance": event.relative_distance,
            "trajectory_conflict": bool(event.trajectory_conflict), "description": event.description}


@router.get("", response_model=list[EventResponse])
def list_events(risk_level: Optional[str] = Query(None), event_date: Optional[date] = Query(None, alias="date"),
                location: Optional[str] = Query(None), skip: int = Query(0, ge=0),
                limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    query = db.query(NearMissEvent, Location.name).join(Location, NearMissEvent.location_id == Location.id)
    if not DEMO_MODE:
        query = query.join(Video, Video.id == NearMissEvent.video_id).filter(Video.frame_count > 0)
    if risk_level:
        risk = risk_level.upper()
        if risk not in {"LOW", "MEDIUM", "HIGH"}:
            raise HTTPException(status_code=422, detail="risk_level must be LOW, MEDIUM, or HIGH")
        query = query.filter(NearMissEvent.risk_level == risk)
    if event_date:
        start = datetime.combine(event_date, time.min, tzinfo=timezone.utc)
        query = query.filter(NearMissEvent.timestamp >= start,
                             NearMissEvent.timestamp < start + timedelta(days=1))
    if location:
        query = query.filter(Location.name.ilike(f"%{location.strip()}%"))
    rows = query.order_by(NearMissEvent.timestamp.desc()).offset(skip).limit(limit).all()
    return [serialize_event(event, name) for event, name in rows]


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: str, db: Session = Depends(get_db)):
    try:
        UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="event_id must be a valid UUID")
    query = (db.query(NearMissEvent, Location.name)
           .join(Location, NearMissEvent.location_id == Location.id)
           .filter(NearMissEvent.id == event_id))
    if not DEMO_MODE:
        query = query.join(Video, Video.id == NearMissEvent.video_id).filter(Video.frame_count > 0)
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Near-miss event not found")
    return serialize_event(*row)


@router.delete("/{event_id}")
def delete_event(event_id: str, db: Session = Depends(get_db)):
    try:
        UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="event_id must be a valid UUID")
    query = db.query(NearMissEvent).filter(NearMissEvent.id == event_id)
    if not DEMO_MODE:
        query = query.join(Video, Video.id == NearMissEvent.video_id).filter(Video.frame_count > 0)
    event = query.first()
    if event is None:
        raise HTTPException(status_code=404, detail="Near-miss event not found")
    db.delete(event)
    db.commit()
    return {"message": "Near-miss event deleted", "event_id": event_id}
