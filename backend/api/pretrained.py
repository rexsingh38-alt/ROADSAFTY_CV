"""Persist completed pretrained video analyses and their safety events."""
from datetime import datetime, timedelta, timezone
import json
from typing import Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import Location, NearMissEvent, Video, VideoSafetySolution
from services.solution_engine import build_video_solution

router = APIRouter(prefix="/api/pretrained", tags=["pretrained analysis"])


class IncidentImport(BaseModel):
    incident_id: str | int
    type: Literal["COLLISION", "NEAR_MISS"]
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    peak_severity: float = Field(ge=0, le=100)
    track_a: int | None = None
    track_b: int | None = None
    class_a: str = "vehicle"
    class_b: str | None = None
    ttc_seconds: float | None = Field(default=None, ge=0)
    relative_distance: float | None = Field(default=None, ge=0)
    subtype: str = ""


class AnalysisImport(BaseModel):
    job_id: str = Field(min_length=1, max_length=40)
    video_name: str = Field(min_length=1, max_length=255)
    location: str = Field(default="Junction A", min_length=1, max_length=120)
    total_frames: int = Field(default=0, ge=0)
    fps: float = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0, ge=0)
    incidents: list[IncidentImport] = Field(default_factory=list, max_length=5000)


def _risk_level(severity: float) -> str:
    return "HIGH" if severity >= 75 else "MEDIUM" if severity >= 50 else "LOW"


@router.post("/import")
def import_analysis(payload: AnalysisImport, db: Session = Depends(get_db)):
    """Idempotently store one completed video and its collision/near-miss incidents."""
    job_id = payload.job_id.strip()
    video_id = str(uuid5(NAMESPACE_URL, f"saferoad-pretrained:{job_id}"))
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        video = Video(id=video_id, filename=payload.video_name[:255],
                      stored_path=f"pretrained://{job_id}/{payload.video_name[:200]}",
                      processing_status="completed", frame_count=payload.total_frames,
                      processed_at=datetime.now(timezone.utc))
        db.add(video)
        db.flush()
    else:
        video.filename = payload.video_name[:255]
        video.processing_status = "completed"
        video.frame_count = payload.total_frames
        video.processed_at = datetime.now(timezone.utc)

    location_name = payload.location.strip() or "Junction A"
    location = db.query(Location).filter(Location.name == location_name).first()
    if location is None:
        location = Location(name=location_name)
        db.add(location)
        db.flush()

    imported = 0
    updated = 0
    base_time = video.created_at or datetime.now(timezone.utc)
    for incident in payload.incidents:
        source_id = str(incident.incident_id)[:50]
        event = (db.query(NearMissEvent)
                 .filter(NearMissEvent.source_job_id == job_id,
                         NearMissEvent.source_incident_id == source_id).first())
        created = event is None
        if created:
            event = NearMissEvent(id=str(uuid4()), timestamp=base_time + timedelta(seconds=incident.start_time),
                                  video_id=video_id, object_1_id="", object_1_type="",
                                  object_2_id="", object_2_type="", risk_level="LOW",
                                  location_id=location.id, description="")
            db.add(event)
        type_a = incident.class_a.strip().lower()[:30] or "vehicle"
        type_b = (incident.class_b or "unknown").strip().lower()[:30] or "unknown"
        event.video_id = video_id
        event.location_id = location.id
        event.event_type = incident.type
        event.source_job_id = job_id
        event.source_incident_id = source_id
        event.timestamp = base_time + timedelta(seconds=incident.start_time)
        event.object_1_id = f"TRACK-{incident.track_a}" if incident.track_a is not None else "MODEL-DETECTED"
        event.object_1_type = type_a
        event.object_2_id = f"TRACK-{incident.track_b}" if incident.track_b is not None else "UNKNOWN"
        event.object_2_type = type_b
        event.ttc = incident.ttc_seconds
        event.ttc_valid = int(incident.ttc_seconds is not None)
        event.risk_level = _risk_level(incident.peak_severity)
        event.relative_distance = incident.relative_distance
        event.trajectory_conflict = 1
        event.description = (
            f"Potential {incident.type.replace('_', ' ').lower()} ({incident.subtype or 'motion analysis'}) "
            f"at {location_name}; severity {incident.peak_severity:.1f}%, "
            f"video time {incident.start_time:.2f}s–{incident.end_time:.2f}s."
        )[:2000]
        if created:
            imported += 1
        else:
            updated += 1

    db.flush()
    other_video_events = (db.query(NearMissEvent.id)
                          .filter(NearMissEvent.location_id == location.id,
                                  NearMissEvent.video_id != video_id).count())
    solution = build_video_solution(payload.incidents, repeated_at_location=other_video_events >= 3)
    record = db.query(VideoSafetySolution).filter(VideoSafetySolution.video_id == video_id).first()
    if record is None:
        record = VideoSafetySolution(id=str(uuid4()), video_id=video_id, job_id=job_id,
                                     video_name=payload.video_name[:255], location=location_name,
                                     total_events=0, near_misses=0, collisions=0,
                                     risk_level="LOW", priority="LOW", possible_factors="[]",
                                     recommended_actions="[]", event_solutions="[]")
        db.add(record)
    record.job_id = job_id
    record.video_name = payload.video_name[:255]
    record.location = location_name
    record.total_events = solution["total_events"]
    record.near_misses = solution["near_misses"]
    record.collisions = solution["collisions"]
    record.risk_level = solution["risk_level"]
    record.priority = solution["priority"]
    record.possible_factors = json.dumps(solution["possible_contributing_factors"], ensure_ascii=False)
    record.recommended_actions = json.dumps(solution["recommended_actions"], ensure_ascii=False)
    record.event_solutions = json.dumps(solution["event_solutions"], ensure_ascii=False)
    db.commit()
    return {"video_id": video_id, "job_id": job_id, "location": location_name,
            "incidents_imported": imported, "incidents_updated": updated,
            "collisions": sum(item.type == "COLLISION" for item in payload.incidents),
            "near_misses": sum(item.type == "NEAR_MISS" for item in payload.incidents),
            "solution": {**solution, "video_name": payload.video_name, "location": location_name}}


def _serialize_solution(record: VideoSafetySolution) -> dict:
    return {
        "video_id": record.video_id,
        "job_id": record.job_id,
        "video_name": record.video_name,
        "location": record.location,
        "generated_at": record.generated_at,
        "total_events": record.total_events,
        "near_misses": record.near_misses,
        "collisions": record.collisions,
        "risk_level": record.risk_level,
        "priority": record.priority,
        "possible_contributing_factors": json.loads(record.possible_factors),
        "recommended_actions": json.loads(record.recommended_actions),
        "event_solutions": json.loads(record.event_solutions),
        "note": "Recommendations are rule-based review guidance. CCTV alone cannot confirm the actual cause.",
    }


@router.get("/solutions/latest")
def get_latest_video_solutions(limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    records = (db.query(VideoSafetySolution)
               .order_by(VideoSafetySolution.generated_at.desc())
               .limit(limit).all())
    return [_serialize_solution(record) for record in records]


@router.get("/{job_id}/solution")
def get_video_solution(job_id: str, db: Session = Depends(get_db)):
    record = db.query(VideoSafetySolution).filter(VideoSafetySolution.job_id == job_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="No safety solution is stored for this video yet.")
    return _serialize_solution(record)
