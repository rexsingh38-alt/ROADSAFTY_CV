"""Pydantic response and request schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class VideoUploadResponse(BaseModel):
    video_id: str
    filename: str
    processing_status: str


class VideoStatusResponse(VideoUploadResponse):
    frame_count: int = 0
    error_message: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class EventResponse(BaseModel):
    event_id: str
    timestamp: datetime
    video_id: Optional[str]
    object_1_id: str
    object_1_type: str
    object_2_id: str
    object_2_type: str
    event_type: str = "NEAR_MISS"
    ttc: Optional[float]
    ttc_valid: bool
    risk_level: str
    location: str
    relative_distance: Optional[float]
    trajectory_conflict: bool
    description: str


class HotspotResponse(BaseModel):
    location: str
    latitude: Optional[float]
    longitude: Optional[float]
    total_events: int
    high_risk_events: int
    average_ttc: Optional[float]
    risk_level: str


class AnalyticsResponse(BaseModel):
    total_vehicles_tracked: int
    total_pedestrians_tracked: int
    total_near_miss_events: int
    collision_events: int = 0
    near_miss_events: int = 0
    high_risk_events: int
    medium_risk_events: int
    low_risk_events: int
    high_risk_rate: float = 0
    average_ttc: Optional[float]
    top_risky_locations: list[HotspotResponse]


class DashboardResponse(BaseModel):
    vehicles_tracked: int
    pedestrians_tracked: int
    near_miss_events: int
    collision_events: int = 0
    high_risk_events: int
    risk_hotspots: int
    average_ttc: Optional[float]
    monitoring_status: str


class HealthResponse(BaseModel):
    status: str
    service: str
    demo_mode: bool

