import os
import uuid
import json
import time
import shutil
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from accident_detector import AccidentDetector

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
SNAPSHOTS_DIR = os.path.join(OUTPUTS_DIR, "snapshots")
DEFAULT_SAMPLE_VIDEO = os.environ.get("SAFEROAD_SAMPLE_VIDEO", r"C:\Users\UJJWAL CHAND KAUSHIK\Downloads\videoplayback.mp4")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

app = FastAPI(title="SafeGuard AI - Accident Detection Studio", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job state tracking
JOBS: Dict[str, Dict[str, Any]] = {}


class ModelCheckRequest(BaseModel):
    model_id: str = "local-yolov8n"


class AnalysisRequest(BaseModel):
    video_source: str  # "sample" or filename in uploads
    location: str = "Junction A"
    model_id: str = "local-yolov8n"
    conf_thresh: float = 0.35
    collision_iou_thresh: float = 0.15
    frame_stride: int = 2


@app.get("/")
async def serve_index():
    return RedirectResponse("http://127.0.0.1:5500/", status_code=307)


@app.post("/api/check-model")
async def check_local_model(req: ModelCheckRequest):
    """Check that local pretrained YOLO weights and their runtime are available."""
    start = time.time()
    try:
        from ultralytics import YOLO
        model_path = os.path.abspath(os.path.join(BASE_DIR, "..", "backend", "models", "yolov8n.pt"))
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"Local pretrained weights are missing: {model_path}")
        YOLO(model_path)
        latency = round((time.time() - start) * 1000, 1)
        return {
            "success": True,
            "message": "Local YOLOv8n pretrained model is ready",
            "latency_ms": latency,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "latency_ms": round((time.time() - start) * 1000, 1)
        }


@app.get("/api/sample-video")
async def get_sample_video_info():
    """Check if the default sample video exists on the system and return details."""
    sample_path = DEFAULT_SAMPLE_VIDEO
    if not os.path.exists(sample_path):
        candidates = [os.path.join(UPLOADS_DIR, name) for name in os.listdir(UPLOADS_DIR)
                      if os.path.splitext(name)[1].lower() in {".mp4", ".avi", ".mov", ".mkv", ".webm"}]
        if candidates:
            sample_path = max(candidates, key=os.path.getmtime)
    if os.path.exists(sample_path):
        size_bytes = os.path.getsize(sample_path)
        return {
            "available": True,
            "path": sample_path,
            "filename": os.path.basename(sample_path),
            "size_mb": round(size_bytes / (1024 * 1024), 2),
        }
    return {
        "available": False,
        "message": "Sample video not found in Downloads folder"
    }


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a new video for analysis."""
    allowed_exts = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{ext}'. Allowed: {allowed_exts}")
        
    unique_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    target_path = os.path.join(UPLOADS_DIR, unique_name)
    
    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    size_mb = round(os.path.getsize(target_path) / (1024 * 1024), 2)
    return {
        "success": True,
        "filename": unique_name,
        "original_name": file.filename,
        "size_mb": size_mb,
    }


def run_video_job(job_id: str, video_path: str, params: AnalysisRequest):
    """Background task executing the video accident detection pipeline."""
    JOBS[job_id]["status"] = "PROCESSING"
    JOBS[job_id]["start_time"] = time.time()
    
    output_filename = f"analyzed_{job_id}.mp4"
    output_path = os.path.join(OUTPUTS_DIR, output_filename)
    job_snapshots_dir = os.path.join(SNAPSHOTS_DIR, job_id)
    os.makedirs(job_snapshots_dir, exist_ok=True)
    
    def on_progress(p_data: Dict[str, Any]):
        JOBS[job_id].update({
            "progress": p_data.get("progress", 0.0),
            "current_frame": p_data.get("current_frame", 0),
            "total_frames": p_data.get("total_frames", 0),
            "fps": p_data.get("fps", 0.0),
            "eta_seconds": p_data.get("eta_seconds", 0.0),
            "current_risk": p_data.get("current_risk", 0.0),
            "vehicles_detected": p_data.get("vehicles_detected", 0),
            "collisions_count": p_data.get("collisions_count", 0),
            "near_miss_count": p_data.get("near_miss_count", 0),
            "incidents_count": p_data.get("incidents_count", 0),
        })
        
    try:
        detector = AccidentDetector(
            model_id=params.model_id,
            conf_thresh=params.conf_thresh,
            collision_iou_thresh=params.collision_iou_thresh,
            frame_stride=params.frame_stride,
        )
        
        summary = detector.process_video(
            video_path=video_path,
            output_path=output_path,
            snapshot_dir=job_snapshots_dir,
            progress_callback=on_progress
        )
        
        # Attach web URLs to snapshots
        for incident in summary["incidents"]:
            if incident.get("snapshot_file"):
                incident["snapshot_url"] = f"/api/snapshot/{job_id}/{incident['snapshot_file']}"
                
        JOBS[job_id].update({
            "status": "COMPLETED",
            "progress": 100.0,
            "output_video_url": f"/api/video/{job_id}",
            "output_video_filename": output_filename,
            "summary": summary,
            "incidents": summary["incidents"],
            "timeline": summary["timeline"],
            "collisions_count": summary.get("collisions_detected", 0),
            "near_miss_count": summary.get("near_misses_detected", 0),
            "finish_time": time.time(),
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        JOBS[job_id].update({
            "status": "FAILED",
            "error": str(e),
            "finish_time": time.time(),
        })


@app.post("/api/start-analysis")
async def start_analysis(req: AnalysisRequest, background_tasks: BackgroundTasks):
    """Launch accident detection analysis on a specified video."""
    if req.video_source == "sample":
        video_path = DEFAULT_SAMPLE_VIDEO
        if not os.path.exists(video_path):
            info = await get_sample_video_info()
            if not info["available"]:
                raise HTTPException(status_code=404, detail="No sample video found. Upload a video to begin.")
            video_path = info["path"]
    else:
        video_path = os.path.join(UPLOADS_DIR, req.video_source)
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail=f"Uploaded file '{req.video_source}' not found.")
            
    job_id = uuid.uuid4().hex[:10]
    JOBS[job_id] = {
        "job_id": job_id,
        "video_source": req.video_source,
        "video_name": os.path.basename(video_path),
        "location": req.location,
        "status": "PENDING",
        "progress": 0.0,
        "created_at": time.time(),
        "model_id": req.model_id,
        "stride": req.frame_stride,
    }
    
    background_tasks.add_task(run_video_job, job_id, video_path, req)
    return {"success": True, "job_id": job_id}


@app.get("/api/job-status/{job_id}")
async def get_job_status(job_id: str):
    """Get real-time analysis status and telemetry."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return JOBS[job_id]


@app.get("/api/video/{job_id}")
async def stream_output_video(job_id: str):
    """Serve the annotated output H.264 video with HTTP range streaming."""
    output_path = os.path.join(OUTPUTS_DIR, f"analyzed_{job_id}.mp4")
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Processed video not ready or found")
    return FileResponse(output_path, media_type="video/mp4", filename=f"accident_analyzed_{job_id}.mp4")


@app.get("/api/raw-video/{job_id}")
async def stream_raw_video(job_id: str):
    """Serve the original raw video for side-by-side or comparison."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    if job["video_source"] == "sample":
        v_path = DEFAULT_SAMPLE_VIDEO
        if not os.path.exists(v_path):
            info = await get_sample_video_info()
            v_path = info.get("path")
    else:
        v_path = os.path.join(UPLOADS_DIR, job["video_source"])
    if not os.path.exists(v_path):
        raise HTTPException(status_code=404, detail="Original video not found")
    return FileResponse(v_path, media_type="video/mp4")


@app.get("/api/snapshot/{job_id}/{filename}")
async def get_snapshot(job_id: str, filename: str):
    """Serve crash frame snapshot."""
    file_path = os.path.join(SNAPSHOTS_DIR, job_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return FileResponse(file_path, media_type="image/jpeg")


@app.get("/api/report/{job_id}")
async def get_report(job_id: str):
    """Download full incident forensic report in JSON."""
    if job_id not in JOBS or "summary" not in JOBS[job_id]:
        raise HTTPException(status_code=404, detail="Report not available")
    return JSONResponse(content=JOBS[job_id]["summary"])


# Mount static assets
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
