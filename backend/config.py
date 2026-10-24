"""Environment-backed settings for the SafeRoad AI demo backend."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


DEMO_MODE = _bool("DEMO_MODE", True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'saferoad.db').as_posix()}")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads"))).resolve()
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", str(BASE_DIR / "processed"))).resolve()
YOLO_MODEL_PATH = Path(os.getenv("YOLO_MODEL_PATH", str(BASE_DIR / "models" / "yolov8n.pt"))).resolve()
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 300)
MAX_VIDEO_FRAMES = _int("MAX_VIDEO_FRAMES", 5000)
# A lighter default keeps the dashboard responsive while a clip is analyzed.
PROCESS_EVERY_N_FRAMES = max(1, _int("PROCESS_EVERY_N_FRAMES", 4))
YOLO_CONFIDENCE = _float("YOLO_CONFIDENCE", 0.35)
HIGH_RISK_TTC_SECONDS = _float("HIGH_RISK_TTC_SECONDS", 1.5)
MEDIUM_RISK_TTC_SECONDS = _float("MEDIUM_RISK_TTC_SECONDS", 3.0)
MAX_CONFLICT_DISTANCE_PX = _float("MAX_CONFLICT_DISTANCE_PX", 180.0)
ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",") if origin.strip()]
GMAIL_USER = os.getenv("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip()
LOGIN_ALERT_TO = os.getenv("LOGIN_ALERT_TO", "").strip()
# Explicitly opt into a browser-visible OTP only for this local development origin.
LOGIN_DEV_OTP = _bool("LOGIN_DEV_OTP", False)
LOCAL_LOGIN_ORIGINS = [origin.strip() for origin in os.getenv(
    "LOCAL_LOGIN_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500"
).split(",") if origin.strip()]

AUTH_SECRET = os.getenv("AUTH_SECRET", "").strip()
if not AUTH_SECRET:
    secret_file = BASE_DIR / ".auth-secret"
    try:
        AUTH_SECRET = secret_file.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        AUTH_SECRET = secrets.token_hex(32)
        try:
            secret_file.write_text(AUTH_SECRET, encoding="ascii")
        except FileExistsError:
            AUTH_SECRET = secret_file.read_text(encoding="ascii").strip()

VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}
TRACKED_CLASSES = VEHICLE_CLASSES | {"person"}

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
