"""Database tables for uploaded footage, tracks, locations, and events."""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func

from database import Base


class Video(Base):
    __tablename__ = "videos"

    id = Column(String(36), primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    stored_path = Column(String(600), nullable=False)
    processing_status = Column(String(20), nullable=False, default="queued", index=True)
    error_message = Column(Text, nullable=True)
    frame_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)


class VideoSafetySolution(Base):
    """Persisted per-video safety assessment and authority action plan."""
    __tablename__ = "video_safety_solutions"

    id = Column(String(36), primary_key=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    job_id = Column(String(40), nullable=False, unique=True, index=True)
    video_name = Column(String(255), nullable=False)
    location = Column(String(120), nullable=False)
    total_events = Column(Integer, nullable=False, default=0)
    near_misses = Column(Integer, nullable=False, default=0)
    collisions = Column(Integer, nullable=False, default=0)
    risk_level = Column(String(10), nullable=False)
    priority = Column(String(12), nullable=False)
    possible_factors = Column(Text, nullable=False, default="[]")
    recommended_actions = Column(Text, nullable=False, default="[]")
    event_solutions = Column(Text, nullable=False, default="[]")
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)


class TrackedObject(Base):
    __tablename__ = "tracked_objects"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="SET NULL"), nullable=True, index=True)
    object_id = Column(String(80), nullable=False, index=True)
    object_type = Column(String(30), nullable=False, index=True)
    first_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    trajectory_json = Column(Text, nullable=False, default="[]")
    average_speed_px_s = Column(Float, nullable=True)


class NearMissEvent(Base):
    __tablename__ = "near_miss_events"

    id = Column(String(36), primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="SET NULL"), nullable=True, index=True)
    object_1_id = Column(String(80), nullable=False)
    object_1_type = Column(String(30), nullable=False)
    object_2_id = Column(String(80), nullable=False)
    object_2_type = Column(String(30), nullable=False)
    event_type = Column(String(20), nullable=False, default="NEAR_MISS")
    source_job_id = Column(String(40), nullable=True)
    source_incident_id = Column(String(50), nullable=True)
    ttc = Column(Float, nullable=True)
    ttc_valid = Column(Integer, nullable=False, default=0)
    risk_level = Column(String(10), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    relative_distance = Column(Float, nullable=True)
    trajectory_conflict = Column(Integer, nullable=False, default=0)
    description = Column(Text, nullable=False)


class OfficerAccount(Base):
    __tablename__ = "officer_accounts"

    email = Column(String(254), primary_key=True)
    password_hash = Column(String(160), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LoginAudit(Base):
    __tablename__ = "login_audit"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(254), nullable=False, index=True)
    attempted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    success = Column(Boolean, nullable=False, default=False, index=True)
    source_ip = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    notification_sent = Column(Boolean, nullable=False, default=False)


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"

    id = Column(String(36), primary_key=True)
    email = Column(String(254), nullable=False, index=True)
    code_digest = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    source_ip = Column(String(64), nullable=True)

