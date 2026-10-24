"""Background video processing for mock/demo and YOLO-powered deployments."""
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import json
import logging

from config import (DEMO_MODE, MAX_VIDEO_FRAMES, MAX_CONFLICT_DISTANCE_PX,
                    PROCESS_EVERY_N_FRAMES, VEHICLE_CLASSES)
from database import SessionLocal
from models import Location, NearMissEvent, TrackedObject, Video
from services.detector import create_detector
from services.risk_engine import classify_risk
from services.trajectory import direction
from services.ttc import calculate_ttc

logger = logging.getLogger(__name__)


def _save_tracks(db, video_id: str, tracker, fps: float) -> None:
    for object_id, track in tracker.tracks.items():
        points = track["points"]
        if len(points) < 1:
            continue
        elapsed = max((points[-1]["frame"] - points[0]["frame"]) / max(fps, 1), 0.001)
        first, last = points[0]["position"], points[-1]["position"]
        speed = (((last[0] - first[0]) ** 2 + (last[1] - first[1]) ** 2) ** .5) / elapsed
        payload = [{"frame": p["frame"], "x": round(p["position"][0], 1), "y": round(p["position"][1], 1)} for p in points]
        db.add(TrackedObject(video_id=video_id, object_id=object_id, object_type=track["class_name"],
                             trajectory_json=json.dumps(payload), average_speed_px_s=round(speed, 2)))


def _process_real_video(db, video: Video, location: Location) -> int:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is not installed. Install backend requirements to process video.") from exc
    # Keep image decoding from consuming every available CPU core during analysis.
    cv2.setNumThreads(1)
    detector = create_detector()
    from services.tracker import CentroidTracker
    capture = cv2.VideoCapture(video.stored_path)
    if not capture.isOpened():
        capture.release()
        raise ValueError("OpenCV could not open the uploaded video. Check that the file is a valid MP4 or AVI.")
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    tracker = CentroidTracker()
    frame_index, processed_frames, seen_pairs = 0, 0, set()
    try:
        while frame_index < MAX_VIDEO_FRAMES:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % PROCESS_EVERY_N_FRAMES == 0:
                detections = detector.detect(frame, frame_index)
                current = tracker.update(detections, frame_index)
                processed_frames += 1
                for one, two in combinations(current, 2):
                    if not ((one["class_name"] == "person" and two["class_name"] in VEHICLE_CLASSES)
                            or (two["class_name"] == "person" and one["class_name"] in VEHICLE_CLASSES)):
                        continue
                    pair_key = tuple(sorted((one["object_id"], two["object_id"])))
                    if pair_key in seen_pairs:
                        continue
                    def velocity(item):
                        history = item["history"]
                        if len(history) < 2:
                            return (0.0, 0.0)
                        a, b = history[-2], history[-1]
                        dt = (b["frame"] - a["frame"]) / max(fps, 1)
                        return direction(a["position"], b["position"], dt)
                    one_velocity, two_velocity = velocity(one), velocity(two)
                    prediction = calculate_ttc(one["position"], one_velocity, two["position"], two_velocity)
                    conflict = prediction.get("valid", False) and prediction.get("closest_distance_px", 999999) <= MAX_CONFLICT_DISTANCE_PX
                    risk = classify_risk(prediction.get("ttc"), prediction.get("valid", False),
                                         prediction.get("distance_px", 999999), conflict)
                    # Only retain actionable candidates. TTC is an image-space estimate, not a calibrated prediction.
                    if risk == "LOW" or prediction.get("distance_px", 999999) > MAX_CONFLICT_DISTANCE_PX * 1.5:
                        continue
                    ttc = prediction.get("ttc")
                    db.add(NearMissEvent(
                        id=__import__("uuid").uuid4().hex, timestamp=datetime.now(timezone.utc), video_id=video.id,
                        object_1_id=one["object_id"], object_1_type=one["class_name"],
                        object_2_id=two["object_id"], object_2_type=two["class_name"],
                        ttc=round(ttc, 2) if ttc is not None else None,
                        ttc_valid=1 if prediction.get("valid") else 0, risk_level=risk, location_id=location.id,
                        relative_distance=round(prediction.get("distance_px", 0), 1),
                        trajectory_conflict=1 if conflict else 0,
                        description=(f"Potential {risk.lower()}-risk interaction between {one['class_name']} "
                                     f"{one['object_id']} and {two['class_name']} {two['object_id']}. "
                                     "Image-space TTC is approximate and should be reviewed.")))
                    seen_pairs.add(pair_key)
            frame_index += 1
        _save_tracks(db, video.id, tracker, fps)
        return frame_index
    finally:
        capture.release()


def _create_demo_events(db, video: Video, location: Location) -> None:
    """Add explicitly simulated detections so an uploaded demo clip shows API activity."""
    examples = [("OBJ-024", "car", "OBJ-031", "motorcycle", .8, "HIGH", 62.0),
                ("OBJ-008", "person", "OBJ-016", "car", 1.6, "MEDIUM", 94.0),
                ("OBJ-019", "person", "OBJ-022", "bus", 2.4, "MEDIUM", 128.0)]
    from uuid import uuid4
    for one_id, one_type, two_id, two_type, ttc, risk, distance_px in examples:
        db.add(NearMissEvent(id=str(uuid4()), timestamp=datetime.now(timezone.utc), video_id=video.id,
                             object_1_id=one_id, object_1_type=one_type, object_2_id=two_id,
                             object_2_type=two_type, ttc=ttc, ttc_valid=1, risk_level=risk,
                             location_id=location.id, relative_distance=distance_px,
                             trajectory_conflict=1,
                             description=f"Demo simulation: potential {risk.lower()}-risk interaction at {location.name}."))
    db.add_all([
        TrackedObject(video_id=video.id, object_id="OBJ-024", object_type="car", trajectory_json="[]", average_speed_px_s=38.4),
        TrackedObject(video_id=video.id, object_id="OBJ-031", object_type="motorcycle", trajectory_json="[]", average_speed_px_s=44.1),
        TrackedObject(video_id=video.id, object_id="OBJ-008", object_type="person", trajectory_json="[]", average_speed_px_s=12.5),
    ])


def process_video_task(video_id: str) -> None:
    """Run outside the request and persist either completion or a clean failure."""
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video is None:
            return
        location = db.query(Location).filter(Location.name == "Junction A").first()
        if location is None:
            location = Location(name="Junction A", latitude=28.6139, longitude=77.2090)
            db.add(location)
            db.flush()
        video.processing_status = "processing"
        db.commit()
        try:
            if DEMO_MODE:
                _create_demo_events(db, video, location)
                video.frame_count = 0
            else:
                video.frame_count = _process_real_video(db, video, location)
            video.processing_status = "completed"
            video.processed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            video = db.query(Video).filter(Video.id == video_id).first()
            if video:
                video.processing_status = "failed"
                video.error_message = str(exc)[:1000]
                video.processed_at = datetime.now(timezone.utc)
                db.commit()
            logger.exception("Video processing failed for %s", video_id)
    finally:
        db.close()
