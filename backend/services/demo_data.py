"""Seed a repeatable, realistic event set for an offline judge demo."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from models import Location, NearMissEvent

LOCATIONS = [
    ("Junction A", 28.6139, 77.2090),
    ("Market Road", 28.6182, 77.2155),
    ("College Crossing", 28.6092, 77.2180),
    ("Junction B", 28.6080, 77.2035),
    ("Main Highway", 28.6200, 77.1990),
]
SAMPLE_COUNTS = {"Junction A": {"HIGH": 3, "MEDIUM": 6, "LOW": 3},
                 "Market Road": {"HIGH": 3, "MEDIUM": 5, "LOW": 3},
                 "College Crossing": {"HIGH": 2, "MEDIUM": 4, "LOW": 2},
                 "Junction B": {"HIGH": 0, "MEDIUM": 2, "LOW": 2},
                 "Main Highway": {"HIGH": 0, "MEDIUM": 0, "LOW": 2}}
PAIRS = [("car", "person"), ("motorcycle", "person"), ("bus", "person"), ("car", "motorcycle")]


def seed_demo_data(db) -> None:
    locations = {}
    for name, lat, lon in LOCATIONS:
        location = db.query(Location).filter(Location.name == name).first()
        if location is None:
            location = Location(name=name, latitude=lat, longitude=lon)
            db.add(location)
        else:
            location.latitude, location.longitude = lat, lon
        locations[name] = location
    db.flush()
    if db.query(NearMissEvent).count() > 0:
        db.commit()
        return
    now = datetime.now(timezone.utc)
    n = 0
    for location_name, risk_counts in SAMPLE_COUNTS.items():
        for risk, count in risk_counts.items():
            for _ in range(count):
                n += 1
                type_1, type_2 = PAIRS[n % len(PAIRS)]
                ttc = {"HIGH": .8 + (n % 7) * .1, "MEDIUM": 1.7 + (n % 12) * .1,
                       "LOW": 3.2 + (n % 8) * .2}[risk]
                db.add(NearMissEvent(
                    id=str(uuid4()), timestamp=now - timedelta(minutes=(n - 1) * 27),
                    video_id=None, object_1_id=f"{type_1.upper()}-{(n * 7) % 90 + 1:03d}", object_1_type=type_1,
                    object_2_id=f"{type_2.upper()}-{(n * 11) % 90 + 1:03d}", object_2_type=type_2,
                    ttc=round(ttc, 1), ttc_valid=1, risk_level=risk, location_id=locations[location_name].id,
                    relative_distance=round(35 + (n * 13) % 120, 1), trajectory_conflict=1,
                    description=f"Potential {risk.lower()}-risk path conflict between a {type_1} and a {type_2} at {location_name}."))
    db.commit()
