# SafeRoad AI Pretrained Accident Detection Studio

The project dashboard combines the pretrained video analysis frontend with the SafeRoad authentication and traffic data APIs. Video inference uses local pretrained YOLOv8n weights from `backend/models/yolov8n.pt`; no Roboflow account, API key, or external inference connection is needed.

## Start the complete website

From the project root, double-click `run-website.bat`. It starts:

- Frontend and login: `http://127.0.0.1:5500`
- Pretrained video analyzer API: `http://127.0.0.1:8001`
- SafeRoad authentication and traffic API: `http://127.0.0.1:8002`

The launcher uses the Python environment in `backend/.venv`. If it is not installed yet, follow the setup steps in `backend/README.md`.

## Use the dashboard

1. Sign in or select **Create account**. Set an email and password with at least eight characters; Gmail codes are not used.
2. Upload an MP4, AVI, MOV, or MKV traffic clip, or select a sample video when one is available.
3. Choose the analysis speed and confidence, then start analysis.
4. Review the detected objects, risk events, video overlay, timestamps, snapshots, and downloadable report.

The model detects vehicles and people. Collision and near-miss alerts are generated from tracked object positions and motion heuristics, so they are potential incidents for human review rather than guaranteed crash classifications. Without camera calibration, distance and time-to-collision estimates are image-space approximations.
