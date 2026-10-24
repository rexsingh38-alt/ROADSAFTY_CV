"""A compact centroid tracker for hackathon-scale roadside video demos."""
from math import hypot

from services.trajectory import center


class CentroidTracker:
    def __init__(self, max_distance_px: float = 110.0, max_missed_frames: int = 8):
        self.max_distance_px = max_distance_px
        self.max_missed_frames = max_missed_frames
        self.next_id = 1
        self.tracks: dict[str, dict] = {}

    def update(self, detections: list[dict], frame_index: int) -> list[dict]:
        candidates = []
        claimed_ids = set()
        for detection in detections:
            point = center(detection["box"])
            best_id, best_distance = None, self.max_distance_px
            for object_id, track in self.tracks.items():
                if (object_id in claimed_ids or track["class_name"] != detection["class_name"]
                        or frame_index - track["last_frame"] > self.max_missed_frames):
                    continue
                old = track["points"][-1]["position"]
                gap_distance = hypot(point[0] - old[0], point[1] - old[1])
                if gap_distance < best_distance:
                    best_id, best_distance = object_id, gap_distance
            if best_id is None:
                best_id = f"OBJ-{self.next_id:03d}"
                self.next_id += 1
                self.tracks[best_id] = {"class_name": detection["class_name"], "points": [], "last_frame": frame_index}
            track = self.tracks[best_id]
            claimed_ids.add(best_id)
            track["points"].append({"frame": frame_index, "position": point, "box": detection["box"]})
            track["points"] = track["points"][-120:]
            track["last_frame"] = frame_index
            candidates.append({**detection, "object_id": best_id, "position": point,
                               "history": track["points"]})
        return candidates
