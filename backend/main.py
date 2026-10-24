"""FastAPI application entry point for SafeRoad AI."""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from api import analytics, auth, events, hotspots, pretrained, reports, video
from config import ALLOWED_ORIGINS, DEMO_MODE
from database import Base, SessionLocal, engine
import models  # Register SQLAlchemy tables before create_all.
from schemas import HealthResponse
from services.auth_security import read_session
from services.demo_data import seed_demo_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("saferoad")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
        event_columns = {column["name"] for column in inspect(engine).get_columns("near_miss_events")}
        with engine.begin() as connection:
            if "event_type" not in event_columns:
                connection.execute(text("ALTER TABLE near_miss_events ADD COLUMN event_type VARCHAR(20) NOT NULL DEFAULT 'NEAR_MISS'"))
            if "source_job_id" not in event_columns:
                connection.execute(text("ALTER TABLE near_miss_events ADD COLUMN source_job_id VARCHAR(40)"))
            if "source_incident_id" not in event_columns:
                connection.execute(text("ALTER TABLE near_miss_events ADD COLUMN source_incident_id VARCHAR(50)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_near_miss_events_event_type ON near_miss_events (event_type)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_near_miss_events_source_job_id ON near_miss_events (source_job_id)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_near_miss_source_incident ON near_miss_events (source_job_id, source_incident_id)"))
        if DEMO_MODE:
            with SessionLocal() as db:
                seed_demo_data(db)
        logger.info("SafeRoad AI backend ready (DEMO_MODE=%s)", DEMO_MODE)
    except SQLAlchemyError:
        logger.exception("Database initialization failed")
        raise
    yield


app = FastAPI(
    title="SafeRoad AI API",
    description=("Backend for roadside near-miss analysis. Risk levels and TTC values are "
                 "approximate indicators for review, not certain accident predictions."),
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def require_officer_session(request: Request, call_next):
    path = request.url.path
    public_paths = {"/api/health", "/api/auth/login", "/api/auth/register", "/api/auth/request-otp", "/api/auth/verify-otp"}
    if path.startswith("/api/") and path not in public_paths and request.method != "OPTIONS":
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        email = read_session(token) if scheme.lower() == "bearer" and token else None
        if not email:
            return JSONResponse(status_code=401, content={"detail": "Please sign in to access this service."})
        request.state.officer_email = email
    return await call_next(request)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_: Request, exc: SQLAlchemyError):
    logger.exception("Database operation failed", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Database operation failed. Please retry."})


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception):
    logger.exception("Unexpected backend error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "An unexpected backend error occurred."})


@app.get("/", tags=["health"])
def root():
    return {"service": "SafeRoad AI Backend", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "service": "SafeRoad AI Backend", "demo_mode": DEMO_MODE}


app.include_router(video.router)
app.include_router(events.router)
app.include_router(hotspots.router)
app.include_router(analytics.router)
app.include_router(pretrained.router)
app.include_router(reports.router)
app.include_router(auth.router)
