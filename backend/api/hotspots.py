"""Location risk aggregation endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas import HotspotResponse
from services.hotspot import aggregate_hotspots

router = APIRouter(prefix="/api/hotspots", tags=["hotspots"])


@router.get("", response_model=list[HotspotResponse])
def get_hotspots(db: Session = Depends(get_db)):
    return aggregate_hotspots(db)
