"""Safe local video upload and processing-status endpoints."""
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config import MAX_UPLOAD_MB, UPLOAD_DIR
from database import get_db
from models import Location, Video
from schemas import VideoStatusResponse, VideoUploadResponse
from services.video_processor import process_video_task

router = APIRouter(prefix="/api/video", tags=["video"])
ALLOWED_EXTENSIONS = {".mp4", ".avi"}


def _video_status(video: Video) -> dict:
    return {"video_id": video.id, "filename": video.filename,
            "processing_status": video.processing_status, "frame_count": video.frame_count,
            "error_message": video.error_message, "created_at": video.created_at,
            "processed_at": video.processed_at}


@router.post("/upload", response_model=VideoUploadResponse, status_code=202)
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...),
                       location: str = Form("Junction A"), db: Session = Depends(get_db)):
    original_name = Path((file.filename or "video").replace("\\", "/")).name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported video format. Upload an MP4 or AVI file.")
    if not original_name or original_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="A valid filename is required")
    video_id = str(uuid4())
    destination = (UPLOAD_DIR / f"{video_id}{suffix}").resolve()
    if destination.parent != UPLOAD_DIR:
        raise HTTPException(status_code=400, detail="Invalid upload path")
    temporary = destination.with_suffix(destination.suffix + ".part")
    maximum = MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    try:
        with temporary.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > maximum:
                    raise HTTPException(status_code=413, detail=f"Video exceeds the {MAX_UPLOAD_MB} MB upload limit")
                output.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty")
        temporary.replace(destination)
        location_name = location.strip()[:120] or "Junction A"
        db_location = db.query(Location).filter(Location.name == location_name).first()
        if db_location is None:
            db_location = Location(name=location_name)
            db.add(db_location)
            db.flush()
        video = Video(id=video_id, filename=original_name[:255], stored_path=str(destination), processing_status="queued")
        db.add(video)
        db.commit()
        background_tasks.add_task(process_video_task, video_id)
        return {"video_id": video_id, "filename": video.filename, "processing_status": "queued"}
    except HTTPException:
        if temporary.exists():
            temporary.unlink()
        if destination.exists():
            destination.unlink()
        raise
    except OSError as exc:
        db.rollback()
        if temporary.exists():
            temporary.unlink()
        if destination.exists():
            destination.unlink()
        raise HTTPException(status_code=500, detail="Could not save the uploaded video") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        if temporary.exists():
            temporary.unlink()
        if destination.exists():
            destination.unlink()
        raise HTTPException(status_code=503, detail="Could not register the uploaded video in the database") from exc
    finally:
        await file.close()


@router.get("", response_model=list[VideoStatusResponse])
def list_videos(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    if skip < 0 or limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="skip must be >= 0 and limit must be between 1 and 500")
    rows = db.query(Video).order_by(Video.created_at.desc()).offset(skip).limit(limit).all()
    return [_video_status(row) for row in rows]


@router.get("/{video_id}", response_model=VideoStatusResponse)
def get_video_status(video_id: str, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return _video_status(video)
