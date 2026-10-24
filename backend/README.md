# SafeRoad AI backend

FastAPI backend for the SafeRoad AI near-miss traffic safety demo. It stores videos, tracked objects, traffic locations, and potential near-miss events in SQLite. The API reports observed risk indicators; it does not predict accidents with certainty.

## How it is organized

```text
backend/
├── main.py                 # FastAPI app, CORS, health, database startup
├── config.py               # Environment settings and risk thresholds
├── database.py             # SQLAlchemy engine and sessions
├── models.py               # SQLite tables
├── schemas.py              # Typed API response schemas
├── api/
│   ├── video.py            # Uploads and processing status
│   ├── events.py           # Event search, detail, and delete
│   ├── hotspots.py         # Risk-by-location aggregation
│   └── analytics.py        # Dashboard and analytics summaries
├── services/
│   ├── detector.py         # Demo detector and YOLO adapter
│   ├── tracker.py          # Centroid-based object IDs
│   ├── trajectory.py       # Path and direction helpers
│   ├── ttc.py              # Approximate time-to-collision calculation
│   ├── risk_engine.py      # Configurable LOW/MEDIUM/HIGH rules
│   ├── hotspot.py          # Event aggregation
│   ├── demo_data.py        # Repeatable sample dataset
│   └── video_processor.py  # Background video pipeline
├── uploads/                # Saved source video files
├── processed/              # Reserved for rendered/annotated output
└── requirements.txt
```

## Install and run

Python 3.10 or newer is recommended. From PowerShell:

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn main:app --reload --port 8002
```

Keep the provided `.env` to run real video processing. To switch back to simulated mode, copy `.env.example` to `.env` and set `DEMO_MODE=true`.

For the default demo-only mode, install the smaller dependency set instead:

```powershell
python -m pip install -r requirements-demo.txt
```

`requirements.txt` also installs Ultralytics, PyTorch, and OpenCV for real video inference; these packages are large. The default simulated demo does not need them.

The API starts at `http://127.0.0.1:8002`. Interactive API documentation is at `http://127.0.0.1:8002/docs`. The SQLite database is created as `backend/saferoad.db` on first start. Set `DEMO_MODE=true` in the environment for sample-data demo mode; the current local `.env` is configured for real video processing.

### Email and password sign-in

Use **Create account** on the login page to set up an account with an email address and a password of at least eight characters. Sign in with those same details on later visits. Existing accounts created by the earlier local OTP flow can use **Create account** with the same email to set their password. Passwords are salted and hashed; dashboard APIs require a signed bearer session that expires after eight hours. Sign-in attempts are recorded in the `login_audit` table. Keep `backend/.auth-secret` local and do not share it.

This configuration is open self-registration: anyone who can receive a code at a Gmail address can create an officer account. Add an office approval/invitation policy before exposing the service beyond a trusted demo.

## Demo mode and real processing

### Demo mode (`DEMO_MODE=true`)

- Starts without a camera, YOLO weights, or network access to a model repository.
- Seeds 37 repeatable near-miss examples at five sample locations.
- Uses example dashboard totals of 1,248 vehicles and 436 pedestrians.
- Accepts MP4 and AVI uploads, saves the file, and simulates three potential interaction records so the upload and status flow can be demonstrated.
- A demo upload is **not decoded or analyzed frame by frame**. Its `frame_count` remains zero by design.

### Video processing mode (`DEMO_MODE=false`)

- Uses OpenCV to read the uploaded file and Ultralytics YOLO to detect `person`, `car`, `motorcycle`, `bus`, and `truck`.
- Requires an existing model file. Put YOLO weights at `backend/models/yolov8n.pt`, or set `YOLO_MODEL_PATH` to another local weights file. The server does not automatically download model weights.
- A centroid tracker assigns temporary object IDs. TTC is calculated from pixel positions and estimated pixel velocity. Without camera calibration, perspective correction, and real-world scale, it is only an approximate indicator and should be reviewed by a human.
- Processing runs as an in-process FastAPI background task, suitable for a small demo. A production deployment should use a durable job queue and worker process.

Example PowerShell setup for a real processing run:

```powershell
$env:DEMO_MODE = "false"
$env:YOLO_MODEL_PATH = ".\models\yolov8n.pt"
uvicorn main:app --reload
```

## Database tables

- `videos`: uploaded filename, safe stored path, processing status, frame count, timestamps, and error text.
- `tracked_objects`: per-video object ID/type, sampled path JSON, and estimated image-space speed.
- `near_miss_events`: timestamp, involved tracks, TTC and validity, risk, location, and explanation.
- `locations`: hotspot label and optional latitude/longitude.

Demo totals for tracked vehicles/pedestrians are dashboard sample values rather than 1,684 individual seeded track rows. Uploaded demo simulations add their own event and track records.

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Service and database health |
| POST | `/api/video/upload` | Upload an MP4/AVI; form fields: `file`, optional `location` |
| GET | `/api/video` | List recent uploads (`skip`, `limit`) |
| GET | `/api/video/{video_id}` | Check `queued`, `processing`, `completed`, or `failed` status |
| GET | `/api/events` | List events; optional `risk_level`, `date` (`YYYY-MM-DD`), `location`, `skip`, `limit` |
| GET | `/api/events/{event_id}` | Event details |
| DELETE | `/api/events/{event_id}` | Delete an event |
| GET | `/api/hotspots` | Event counts, high-risk counts, average TTC, and risk by location |
| GET | `/api/analytics` | Event/risk totals, sample/observed object totals, average TTC, top locations |
| GET | `/api/dashboard` | Main dashboard card data in one response |

### Upload example

```powershell
curl.exe -F "file=@sample-traffic.mp4" -F "location=Junction A" http://127.0.0.1:8000/api/video/upload
```

Example upload response (`202 Accepted`):

```json
{
  "video_id": "cda5a622-0b09-4f2d-8501-35451a475c06",
  "filename": "sample-traffic.mp4",
  "processing_status": "queued"
}
```

Processing status response:

```json
{
  "video_id": "cda5a622-0b09-4f2d-8501-35451a475c06",
  "filename": "sample-traffic.mp4",
  "processing_status": "completed",
  "frame_count": 0,
  "error_message": null,
  "created_at": "2026-10-23T10:30:00",
  "processed_at": "2026-10-23T10:30:01"
}
```

### Sample responses for the remaining endpoints

`GET /api/health`

```json
{"status":"ok","service":"SafeRoad AI Backend","demo_mode":true}
```

`GET /api/dashboard`

```json
{"vehicles_tracked":1248,"pedestrians_tracked":436,"near_miss_events":37,"high_risk_events":8,"risk_hotspots":4,"average_ttc":2.42,"monitoring_status":"DEMO"}
```

`GET /api/analytics`

```json
{"total_vehicles_tracked":1248,"total_pedestrians_tracked":436,"total_near_miss_events":37,"high_risk_events":8,"medium_risk_events":17,"low_risk_events":12,"average_ttc":2.42,"top_risky_locations":[{"location":"Junction A","latitude":28.6139,"longitude":77.209,"total_events":12,"high_risk_events":3,"average_ttc":2.11,"risk_level":"HIGH"}]}
```

`GET /api/events?risk_level=HIGH&location=Junction%20A`

```json
[{"event_id":"cda5a622-0b09-4f2d-8501-35451a475c06","timestamp":"2026-10-23T10:00:00Z","video_id":null,"object_1_id":"CAR-008","object_1_type":"car","object_2_id":"PERSON-012","object_2_type":"person","ttc":1.0,"ttc_valid":true,"risk_level":"HIGH","location":"Junction A","relative_distance":48.0,"trajectory_conflict":true,"description":"Potential high-risk path conflict between a car and a person at Junction A."}]
```

`GET /api/events/{event_id}` returns one event with the same fields as the event list. `DELETE /api/events/{event_id}` returns `{"message":"Near-miss event deleted","event_id":"..."}`. A malformed UUID returns `400`; a valid but missing ID returns `404`.

`GET /api/hotspots`

```json
[{"location":"Market Road","latitude":28.6182,"longitude":77.2155,"total_events":11,"high_risk_events":3,"average_ttc":2.31,"risk_level":"HIGH"}]
```

`GET /api/video`

```json
[{"video_id":"cda5a622-0b09-4f2d-8501-35451a475c06","filename":"sample-traffic.mp4","processing_status":"completed","frame_count":0,"error_message":null,"created_at":"2026-10-23T10:30:00","processed_at":"2026-10-23T10:30:01"}]
```

`GET /api/video/{video_id}` returns one record in the same shape. Upload errors use JSON `detail` messages; examples include `415` for unsupported formats, `413` for oversized files, and `404` for unknown video IDs.

## Connecting the existing frontend

The dashboard is connected through the root-level `backend-bridge.js`. It reads `/api/dashboard`, `/api/events`, `/api/hotspots`, and `/api/analytics`; the sidebar shows whether the API is online. Its video upload control sends `file` and `location` form fields to `/api/video/upload` and polls the returned video status. If the API is offline, the dashboard keeps its built-in sample data. The bridge currently uses `http://127.0.0.1:8002/api` for the real-analysis server; change `API_BASE` in `backend-bridge.js` if you choose a different port.

Configure the sender Gmail and start the backend, then open the root `login.html` in a browser (or use a local static-file server). CORS is enabled for local development; set `ALLOWED_ORIGINS` to comma-separated trusted origins when needed.

## Safety and error notes

- Upload names are replaced with generated UUID paths; only `.mp4` and `.avi` are accepted and a configurable size cap is enforced.
- Detection confidence and risk/TTC thresholds can be changed through environment variables listed in `.env.example`.
- Image-space TTC is not a calibrated road-speed estimate. It does not account for camera perspective or guarantee a collision/accident outcome.
- Keep camera footage access restricted and define retention/deletion policies before using real identifiable footage.
