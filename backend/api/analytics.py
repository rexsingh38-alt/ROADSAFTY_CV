"""Summary statistics for dashboard cards and analytics charts."""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import DEMO_MODE
from database import get_db
from models import NearMissEvent, TrackedObject, Video
from schemas import AnalyticsResponse, DashboardResponse
from services.hotspot import aggregate_hotspots

router = APIRouter(prefix="/api", tags=["analytics"])
DEMO_VEHICLES = 1248
DEMO_PEDESTRIANS = 436


def _counts(db: Session):
    query = db.query(NearMissEvent)
    if not DEMO_MODE:
        query = query.join(Video, Video.id == NearMissEvent.video_id).filter(Video.frame_count > 0)
    return {risk: int(query.filter(NearMissEvent.risk_level == risk).count())
            for risk in ("HIGH", "MEDIUM", "LOW")}


def _event_type_count(db: Session, event_type: str) -> int:
    query = db.query(NearMissEvent).filter(NearMissEvent.event_type == event_type)
    if not DEMO_MODE:
        query = query.join(Video, Video.id == NearMissEvent.video_id).filter(Video.frame_count > 0)
    return int(query.count())


def _tracked_count(db: Session, object_types: list[str]) -> int:
    query = db.query(func.count(TrackedObject.id)).filter(TrackedObject.object_type.in_(object_types))
    if not DEMO_MODE:
        query = query.join(Video, Video.id == TrackedObject.video_id).filter(Video.frame_count > 0)
    return int(query.scalar() or 0)


def _average_ttc(db: Session):
    query = db.query(NearMissEvent)
    if not DEMO_MODE:
        query = query.join(Video, Video.id == NearMissEvent.video_id).filter(Video.frame_count > 0)
    return query.with_entities(func.avg(NearMissEvent.ttc)).filter(NearMissEvent.ttc.is_not(None)).scalar()


@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(db: Session = Depends(get_db)):
    counts = _counts(db)
    event_count = sum(counts.values())
    near_misses = _event_type_count(db, "NEAR_MISS")
    collisions = _event_type_count(db, "COLLISION")
    average = _average_ttc(db)
    vehicles = DEMO_VEHICLES if DEMO_MODE else _tracked_count(db, ["car", "motorcycle", "bus", "truck"])
    pedestrians = DEMO_PEDESTRIANS if DEMO_MODE else _tracked_count(db, ["person"])
    return {"total_vehicles_tracked": vehicles, "total_pedestrians_tracked": pedestrians,
            "total_near_miss_events": event_count, "near_miss_events": near_misses,
            "collision_events": collisions,
            "high_risk_events": counts["HIGH"],
            "medium_risk_events": counts["MEDIUM"], "low_risk_events": counts["LOW"],
            "high_risk_rate": round(counts["HIGH"] * 100 / event_count, 1) if event_count else 0,
            "average_ttc": round(float(average), 2) if average is not None else None,
            "top_risky_locations": aggregate_hotspots(db)[:5]}


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(db: Session = Depends(get_db)):
    counts = _counts(db)
    near_misses = _event_type_count(db, "NEAR_MISS")
    collisions = _event_type_count(db, "COLLISION")
    hotspots = aggregate_hotspots(db)
    vehicles = DEMO_VEHICLES if DEMO_MODE else _tracked_count(db, ["car", "motorcycle", "bus", "truck"])
    pedestrians = DEMO_PEDESTRIANS if DEMO_MODE else _tracked_count(db, ["person"])
    average = _average_ttc(db)
    high_risk_hotspots = sum(1 for spot in hotspots if spot["risk_level"] in {"HIGH", "MEDIUM"})
    return {"vehicles_tracked": vehicles, "pedestrians_tracked": pedestrians,
            "near_miss_events": near_misses, "collision_events": collisions,
            "high_risk_events": counts["HIGH"],
            "risk_hotspots": high_risk_hotspots,
            "average_ttc": round(float(average), 2) if average is not None else None,
            "monitoring_status": "DEMO" if DEMO_MODE else "READY"}
