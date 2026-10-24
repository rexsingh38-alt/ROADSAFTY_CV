import cv2
import math
import numpy as np
import av
import os
import time
from typing import List, Dict, Any, Optional, Tuple, Callable


def apply_nms(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float = 0.40,
              center_dist_thresh: float = 14.0, classes: Optional[List[str]] = None) -> List[int]:
    """Suppress duplicate boxes while preserving overlapping objects of different classes."""
    if len(boxes) == 0:
        return []
    
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        union = areas[i] + areas[order[1:]] - inter
        ovr = inter / np.maximum(union, 1e-6)
        
        # Center proximity check to eliminate multi-class duplicate predictions on the same vehicle
        cdists = np.sqrt((cx[i] - cx[order[1:]]) ** 2 + (cy[i] - cy[order[1:]]) ** 2)
        
        same_class = np.ones(order[1:].shape, dtype=bool) if classes is None else np.array(
            [classes[int(i)] == classes[int(j)] for j in order[1:]], dtype=bool
        )
        vehicle_classes = {"car", "truck", "bus", "motorcycle", "vehicle"}
        cross_label_duplicate = np.array([
            classes is not None
            and classes[int(i)].lower() in vehicle_classes
            and classes[int(j)].lower() in vehicle_classes
            and ovr[index] >= 0.90
            and cdists[index] <= 8.0
            for index, j in enumerate(order[1:])
        ], dtype=bool)
        suppressible = same_class | cross_label_duplicate
        suppression_keep = ((ovr <= iou_thresh) & (cdists > center_dist_thresh)) | ~suppressible
        inds = np.where(suppression_keep)[0]
        order = order[inds + 1]
    return keep



def compute_iou(boxA: Tuple[float, float, float, float], boxB: Tuple[float, float, float, float]) -> float:
    """Compute IoU between two boxes: [x1, y1, x2, y2]."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    
    interW = max(0.0, xB - xA)
    interH = max(0.0, yB - yA)
    interArea = interW * interH
    
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    unionArea = boxAArea + boxBArea - interArea
    
    if unionArea <= 0:
        return 0.0
    return interArea / unionArea


def compatible_track_classes(first: str, second: str) -> bool:
    aliases = {"pedestrian": "person", "human": "person"}
    first = aliases.get(first.lower(), first.lower())
    second = aliases.get(second.lower(), second.lower())
    vehicles = {"car", "truck", "bus", "motorcycle", "vehicle"}
    # COCO labels can fluctuate between car/truck/bus on small or damaged vehicles.
    return first == second or (first in vehicles and second in vehicles)


class VehicleTrack:
    """Represents a tracked vehicle across frames with kinematics and crash memory."""
    def __init__(self, track_id: int, box: Tuple[float, float, float, float], class_name: str, confidence: float, frame_idx: int):
        self.track_id = track_id
        self.box = list(box)  # [x1, y1, x2, y2]
        self.smoothed_box = list(box)
        self.class_name = class_name
        self.confidence = confidence
        self.start_frame = frame_idx
        self.last_frame = frame_idx
        self.misses = 0
        
        # Center coordinates
        cx = (box[0] + box[2]) / 2.0
        cy = (box[1] + box[3]) / 2.0
        self.trajectory = [(cx, cy, frame_idx)]  # list of (x, y, frame)
        self.velocity = (0.0, 0.0)
        self.speed = 0.0
        self.max_speed_seen = 0.0
        self.acceleration = 0.0
        
        # Threat & Crash State
        self.state = "SAFE"  # 'SAFE', 'NEAR_MISS', 'COLLISION'
        self.has_crashed = False  # Persistent crash flag (never resets once crashed)
        self.crash_frame = 0
        self.crash_type = ""
        self.was_in_near_miss = False
        self.near_miss_frame = 0
        self.partner_id: Optional[int] = None
        self.collision_frames_count = 0
        self.near_miss_frames_count = 0
        self.stationary_frames_after_motion = 0
        self.impact_deceleration_seen = False
        self.stationary_observations = 0

    def update(self, box: Tuple[float, float, float, float], confidence: float, frame_idx: int):
        alpha = 0.70  # EMA smoothing factor
        self.box = list(box)
        self.smoothed_box = [
            alpha * box[i] + (1 - alpha) * self.smoothed_box[i]
            for i in range(4)
        ]
        self.confidence = confidence
        self.last_frame = frame_idx
        self.misses = 0
        
        cx = (self.smoothed_box[0] + self.smoothed_box[2]) / 2.0
        cy = (self.smoothed_box[1] + self.smoothed_box[3]) / 2.0
        
        if len(self.trajectory) > 0:
            prev_cx, prev_cy, prev_f = self.trajectory[-1]
            dt = max(1, frame_idx - prev_f)
            vx = (cx - prev_cx) / dt
            vy = (cy - prev_cy) / dt
            current_speed = math.sqrt(vx * vx + vy * vy)
            self.acceleration = (current_speed - self.speed) / dt
            if self.speed - current_speed >= 1.5:
                self.impact_deceleration_seen = True
            self.velocity = (vx, vy)
            self.speed = current_speed
            self.max_speed_seen = max(self.max_speed_seen, current_speed)
            if current_speed <= 1.2:
                self.stationary_observations += 1
            else:
                self.stationary_observations = 0
            if self.max_speed_seen >= 3.0 and current_speed <= 0.8:
                self.stationary_frames_after_motion += 1
            elif current_speed > 1.2:
                self.stationary_frames_after_motion = 0
            # Physical tracking
            if self.has_crashed:
                # If a crashed vehicle is observed actively driving away with high speed & displacement, clear crash state
                if len(self.trajectory) >= 6:
                    p_old = self.trajectory[-6]
                    net_disp = math.sqrt((cx - p_old[0]) ** 2 + (cy - p_old[1]) ** 2)
                    if net_disp > 8.0 and self.speed > 2.5:
                        self.has_crashed = False
            
        self.trajectory.append((cx, cy, frame_idx))
        if len(self.trajectory) > 30:
            self.trajectory.pop(0)

    def extrapolate(self, dt: int = 1):
        """Smooth extrapolation on non-inference frames."""
        if not self.has_crashed:
            vx, vy = self.velocity
            self.smoothed_box[0] += vx * dt
            self.smoothed_box[2] += vx * dt
            self.smoothed_box[1] += vy * dt
            self.smoothed_box[3] += vy * dt


class AccidentDetector:
    """Robust Accident, Near-Miss, and Single-Vehicle Crash Detection Engine."""
    def __init__(
        self,
        model_id: str = "local-yolov8n",
        conf_thresh: float = 0.35,
        collision_iou_thresh: float = 0.12,
        frame_stride: int = 2,
    ):
        self.model_id = model_id
        self.conf_thresh = conf_thresh
        self.collision_iou_thresh = collision_iou_thresh
        self.frame_stride = max(1, frame_stride)
        
        from ultralytics import YOLO
        self.model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "models", "yolov8n.pt"))
        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(f"Local pretrained weights not found: {self.model_path}")
        self.model = YOLO(self.model_path)
        try:
            import torch
            torch.set_num_threads(2)
            torch.set_num_interop_threads(1)
        except (ImportError, RuntimeError):
            pass

        # Interaction heuristics are tuned in a 640px reference coordinate space.
        self.coordinate_scale = 1.0
        self.frame_size = (640, 360)
        self.direct_crash_predictions: List[Dict[str, Any]] = []
        
        self.next_track_id = 1
        self.active_tracks: Dict[int, VehicleTrack] = {}
        self.max_misses = 8
        self.incident_history: List[Dict[str, Any]] = []
        self.active_incident: Optional[Dict[str, Any]] = None
        self.incident_grace_timer = 0  # Grace period to bridge stride intervals

    def reset(self):
        """Reset state."""
        self.next_track_id = 1
        self.active_tracks.clear()
        self.incident_history.clear()
        self.active_incident = None
        self.incident_grace_timer = 0
        self.direct_crash_predictions = []

    def infer_frame(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """Scale-optimized inference (5x faster throughput)."""
        try:
            h_orig, w_orig = frame.shape[:2]
            max_edge = max(h_orig, w_orig)
            scale = 640.0 / max_edge if max_edge > 640 else 1.0
            self.coordinate_scale = 640.0 / max(1, max_edge)
            self.frame_size = (w_orig, h_orig)
            self.direct_crash_predictions = []
            
            if scale < 1.0:
                new_w = int(round(w_orig * scale))
                new_h = int(round(h_orig * scale))
                input_frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            else:
                input_frame = frame
                scale = 1.0
                
            inv_scale = 1.0 / scale
            result = self.model.predict(input_frame, conf=self.conf_thresh, imgsz=640,
                                        verbose=False, device="cpu")
            predictions = []
            for inference_result in result:
                for detected_box in inference_result.boxes:
                    class_id = int(detected_box.cls[0])
                    class_name = inference_result.names[class_id].lower()
                    x1, y1, x2, y2 = detected_box.xyxy[0].cpu().tolist()
                    predictions.append({
                        "class": class_name,
                        "confidence": float(detected_box.conf[0]),
                        "x": (x1 + x2) / 2,
                        "y": (y1 + y2) / 2,
                        "width": x2 - x1,
                        "height": y2 - y1,
                    })
            
            target_classes = {"car", "truck", "bus", "motorcycle", "vehicle", "person", "pedestrian"}
            
            raw_boxes = []
            raw_scores = []
            raw_classes = []
            
            for d in predictions:
                c = d.get("class", "").lower()
                conf = float(d.get("confidence", 0.0))
                if any(label in c for label in ("accident", "crash", "collision")) and conf >= self.conf_thresh:
                    x, y = float(d["x"]) * inv_scale, float(d["y"]) * inv_scale
                    box_w, box_h = float(d["width"]) * inv_scale, float(d["height"]) * inv_scale
                    self.direct_crash_predictions.append({
                        "box": (max(0.0, x - box_w / 2), max(0.0, y - box_h / 2),
                                min(float(w_orig), x + box_w / 2), min(float(h_orig), y + box_h / 2)),
                        "confidence": conf,
                    })
                    continue
                if c in target_classes and conf >= self.conf_thresh:
                    x = float(d["x"]) * inv_scale
                    y = float(d["y"]) * inv_scale
                    w = float(d["width"]) * inv_scale
                    h = float(d["height"]) * inv_scale
                    
                    x1 = max(0.0, x - w / 2.0)
                    y1 = max(0.0, y - h / 2.0)
                    x2 = min(float(w_orig), x + w / 2.0)
                    y2 = min(float(h_orig), y + h / 2.0)
                    
                    raw_boxes.append([x1, y1, x2, y2])
                    raw_scores.append(conf)
                    raw_classes.append(c)
            
            if not raw_boxes:
                return []
            
            keep_indices = apply_nms(
                np.array(raw_boxes), np.array(raw_scores), iou_thresh=0.40,
                center_dist_thresh=14.0 / max(0.01, self.coordinate_scale), classes=raw_classes
            )
            detections = []
            for idx in keep_indices:
                detections.append({
                    "box": tuple(raw_boxes[idx]),
                    "confidence": raw_scores[idx],
                    "class": raw_classes[idx]
                })
            return detections
            
        except Exception as e:
            raise RuntimeError(f"Local YOLO inference failed: {e}") from e

    def update_tracks(self, detections: List[Dict[str, Any]], frame_idx: int):
        """Update tracked vehicles."""
        matched_track_ids = set()
        unmatched_detections = []
        
        for det in detections:
            det_box = det["box"]
            best_iou = 0.0
            best_track_id = None
            
            for track_id, track in self.active_tracks.items():
                if track_id in matched_track_ids:
                    continue
                if not compatible_track_classes(det["class"], track.class_name):
                    continue
                iou = compute_iou(det_box, tuple(track.smoothed_box))
                if iou > best_iou:
                    best_iou = iou
                    best_track_id = track_id
                    
            if best_track_id is not None and best_iou > 0.15:
                self.active_tracks[best_track_id].update(det_box, det["confidence"], frame_idx)
                matched_track_ids.add(best_track_id)
            else:
                unmatched_detections.append(det)
                
        to_delete = []
        for track_id, track in self.active_tracks.items():
            if track_id not in matched_track_ids:
                track.misses += 1
                max_allowed = 120 if track.has_crashed else self.max_misses
                if track.misses > max_allowed:
                    to_delete.append(track_id)
        for tid in to_delete:
            del self.active_tracks[tid]
            
        for det in unmatched_detections:
            new_track = VehicleTrack(self.next_track_id, det["box"], det["class"], det["confidence"], frame_idx)
            self.active_tracks[self.next_track_id] = new_track
            self.next_track_id += 1

    def analyze_threats(self, frame_idx: int, fps: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
        """
        Comprehensive Threat Detection:
        1. RED COLLISION / ACCIDENT:
           - Bounding-box contact with impact deceleration or both objects stopping after motion
           - Single-vehicle roadside stop after sustained movement
           - Direct accident-class detections from a compatible model
        2. YELLOW NEAR MISS:
           - Predicted close approach within 1.5 seconds or close evasive braking
        """
        collisions = []
        near_misses = []
        scale = self.coordinate_scale
        ref_width = self.frame_size[0] * scale
        ref_height = self.frame_size[1] * scale

        # If the configured model has accident-specific classes, preserve those
        # detections as direct evidence instead of treating them as vehicles.
        if self.direct_crash_predictions:
            prediction = max(self.direct_crash_predictions, key=lambda item: item["confidence"])
            box = prediction["box"]
            center = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
            collisions.append({
                "type": "COLLISION", "subtype": "MODEL_DETECTED_ACCIDENT",
                "track_a": 0, "track_b": None, "class_a": "Model detected accident",
                "class_b": None, "severity": round(70 + 30 * prediction["confidence"], 1),
                "center": center, "box": box, "iou": 1.0,
            })
            max_risk = collisions[0]["severity"]

        tracks_list = list(self.active_tracks.values())
        max_risk = max((item["severity"] for item in collisions), default=0.0)
        
        # Reset state for current frame (preserving persistent crash state)
        for t in tracks_list:
            if t.has_crashed:
                t.state = "COLLISION"  # Always RED once crashed!
            else:
                t.state = "SAFE"
            t.partner_id = None
        
        # 1. Pairwise Vehicle Interactions (Collisions & Near Misses)

        # 2. Pairwise Vehicle Interactions (Collisions & Near Misses)
        for i in range(len(tracks_list)):
            for j in range(i + 1, len(tracks_list)):
                tA = tracks_list[i]
                tB = tracks_list[j]
                raw_boxA = tuple(tA.smoothed_box)
                raw_boxB = tuple(tB.smoothed_box)
                boxA = tuple(value * scale for value in raw_boxA)
                boxB = tuple(value * scale for value in raw_boxB)
                
                iou = compute_iou(boxA, boxB)
                
                cxA = (boxA[0] + boxA[2]) / 2.0
                cyA = (boxA[1] + boxA[3]) / 2.0
                cxB = (boxB[0] + boxB[2]) / 2.0
                cyB = (boxB[1] + boxB[3]) / 2.0
                dist = math.sqrt((cxA - cxB) ** 2 + (cyA - cyB) ** 2)
                
                hA = boxA[3] - boxA[1]
                hB = boxB[3] - boxB[1]
                min_h = max(1.0, min(hA, hB))
                delta_y2 = abs(boxA[3] - boxB[3])
                ground_plane_aligned = delta_y2 < (1.1 * min_h)
                
                vxA, vyA = (value * scale for value in tA.velocity)
                vxB, vyB = (value * scale for value in tB.velocity)
                rel_vx = vxA - vxB
                rel_vy = vyA - vyB
                rel_speed = math.sqrt(rel_vx * rel_vx + rel_vy * rel_vy)
                
                dx = cxB - cxA
                dy = cyB - cyA
                closing_rate = -(dx * rel_vx + dy * rel_vy) / max(0.1, dist)
                speed_drop = scale * (max(0.0, -tA.acceleration) + max(0.0, -tB.acceleration))
                
                # COLLISION CHECK (RED)
                # Require impact evidence so a brief 2D box overlap is not called a crash.
                speed_a = tA.speed * scale
                speed_b = tB.speed * scale
                stopped_after_motion = (
                    speed_a < 0.35 and speed_b < 0.35
                    and tA.max_speed_seen * scale > 1.0 and tB.max_speed_seen * scale > 1.0
                )
                overlap_threshold = max(0.12, min(0.28, self.collision_iou_thresh))
                is_direct_impact = ground_plane_aligned and iou >= overlap_threshold and (
                    speed_drop >= 0.30 or stopped_after_motion
                )
                if is_direct_impact:
                    tA.has_crashed = True
                    tB.has_crashed = True
                    tA.state = "COLLISION"
                    tB.state = "COLLISION"
                    tA.partner_id = tB.track_id
                    tB.partner_id = tA.track_id
                    
                    sev = min(100.0, 60.0 + iou * 100.0 + speed_drop * 4.0)
                    raw_cxA = (raw_boxA[0] + raw_boxA[2]) / 2.0
                    raw_cyA = (raw_boxA[1] + raw_boxA[3]) / 2.0
                    raw_cxB = (raw_boxB[0] + raw_boxB[2]) / 2.0
                    raw_cyB = (raw_boxB[1] + raw_boxB[3]) / 2.0
                    center_col = ((raw_cxA + raw_cxB) / 2.0, (raw_cyA + raw_cyB) / 2.0)
                    c_box = (
                        min(raw_boxA[0], raw_boxB[0]), min(raw_boxA[1], raw_boxB[1]),
                        max(raw_boxA[2], raw_boxB[2]), max(raw_boxA[3], raw_boxB[3])
                    )
                    collisions.append({
                        "type": "COLLISION",
                        "subtype": "VEHICLE_COLLISION",
                        "track_a": tA.track_id,
                        "track_b": tB.track_id,
                        "class_a": tA.class_name,
                        "class_b": tB.class_name,
                        "iou": round(iou, 3),
                        "severity": round(sev, 1),
                        "center": center_col,
                        "box": c_box
                    })
                    max_risk = max(max_risk, sev)
                    continue

                # NEAR MISS CHECK (YELLOW)
                # Approaching objects with a predicted close path, or close evasive braking.
                if ground_plane_aligned and not tA.has_crashed and not tB.has_crashed:
                    # Predict closest approach over the next 1.5 seconds. This
                    # distinguishes vehicles converging on each other from
                    # vehicles that happen to be close or already moving apart.
                    rel_speed_sq = rel_vx * rel_vx + rel_vy * rel_vy
                    horizon_frames = max(1.0, fps * 1.5)
                    closest_frames = 0.0
                    if rel_speed_sq > 1e-6:
                        closest_frames = max(0.0, min(horizon_frames,
                            -(dx * rel_vx + dy * rel_vy) / rel_speed_sq))
                    closest_x = dx + rel_vx * closest_frames
                    closest_y = dy + rel_vy * closest_frames
                    closest_distance = math.sqrt(closest_x * closest_x + closest_y * closest_y)
                    interaction_radius = max(22.0, 0.65 * min(hA, hB))
                    ttc_seconds = max(0.0, (dist - interaction_radius) / max(0.1, closing_rate * fps))
                    predicted_conflict = (
                        closing_rate > 0.0 and ttc_seconds <= 1.5
                        and closest_distance <= interaction_radius
                    )
                    evasive_braking = speed_drop >= 0.35 and dist <= interaction_radius * 1.8
                    is_near_miss = predicted_conflict or evasive_braking
                    if is_near_miss:
                        # A vehicle already stopped off the carriageway may be a
                        # crash that happened before this clip began. If traffic
                        # then passes at near-zero separation, flag that vehicle
                        # as a possible roadside crash instead of only a near miss.
                        def stationary_roadside(track, center_x, center_y):
                            off_road_edge = (
                                center_x < 0.35 * ref_width or center_x > 0.65 * ref_width
                            ) and center_y > 0.35 * ref_height
                            return (
                                off_road_edge
                                and track.speed * scale <= 0.55
                                and track.stationary_observations >= max(6, int(fps / self.frame_stride))
                            )

                        stationary_track = None
                        moving_track = None
                        if stationary_roadside(tA, cxA, cyA) and tB.max_speed_seen * scale > 0.8:
                            stationary_track, moving_track = tA, tB
                        elif stationary_roadside(tB, cxB, cyB) and tA.max_speed_seen * scale > 0.8:
                            stationary_track, moving_track = tB, tA

                        if stationary_track and closest_distance <= max(12.0, interaction_radius * 0.5):
                            stationary_track.has_crashed = True
                            stationary_track.state = "COLLISION"
                            stationary_track.crash_frame = frame_idx
                            stationary_track.crash_type = "POSSIBLE_ROADSIDE_CRASH"
                            crash_box = tuple(stationary_track.smoothed_box)
                            crash_center = (
                                (crash_box[0] + crash_box[2]) / 2.0,
                                (crash_box[1] + crash_box[3]) / 2.0,
                            )
                            collisions.append({
                                "type": "COLLISION",
                                "subtype": "POSSIBLE_ROADSIDE_CRASH",
                                "track_a": stationary_track.track_id,
                                "track_b": None,
                                "class_a": stationary_track.class_name,
                                "class_b": None,
                                "severity": 86.0,
                                "center": crash_center,
                                "box": crash_box,
                                "iou": round(iou, 3),
                                "passing_track_id": moving_track.track_id,
                            })
                            stationary_track.partner_id = moving_track.track_id
                            max_risk = max(max_risk, 86.0)
                            continue

                        tA.state = "NEAR_MISS"
                        tB.state = "NEAR_MISS"
                        tA.was_in_near_miss = True
                        tB.was_in_near_miss = True
                        tA.near_miss_frame = frame_idx
                        tB.near_miss_frame = frame_idx
                        tA.partner_id = tB.track_id
                        tB.partner_id = tA.track_id
                        
                        proximity = max(0.0, (interaction_radius - closest_distance) / interaction_radius)
                        urgency = max(0.0, 1.5 - min(1.5, ttc_seconds)) / 1.5
                        nm_sev = round(min(90.0, 40.0 + proximity * 35.0 + urgency * 15.0), 1)
                        near_misses.append({
                            "type": "NEAR_MISS",
                            "track_a": tA.track_id,
                            "track_b": tB.track_id,
                            "class_a": tA.class_name,
                            "class_b": tB.class_name,
                            "severity": nm_sev,
                            "ttc_seconds": round(ttc_seconds, 3),
                            "closest_distance": round(closest_distance, 1),
                            "center_a": ((raw_boxA[0] + raw_boxA[2]) / 2.0, (raw_boxA[1] + raw_boxA[3]) / 2.0),
                            "center_b": ((raw_boxB[0] + raw_boxB[2]) / 2.0, (raw_boxB[1] + raw_boxB[3]) / 2.0),
                            "dist": round(dist, 1)
                        })
                        max_risk = max(max_risk, nm_sev)

        # 2. Single-Vehicle Roadside / Barrier Crash Evaluation
        # YOLOv8n has no crash class, so infer a possible roadside impact from
        # tracked movement followed by a sustained stop near the road edge.
        for t in tracks_list:
            if not t.has_crashed and t.class_name in {"car", "truck", "bus", "motorcycle", "vehicle"}:
                raw_cx = (t.smoothed_box[0] + t.smoothed_box[2]) / 2.0
                raw_cy = (t.smoothed_box[1] + t.smoothed_box[3]) / 2.0
                ref_width = self.frame_size[0] * scale
                ref_height = self.frame_size[1] * scale
                cx = raw_cx * scale
                cy = raw_cy * scale
                at_roadside = cy > 0.35 * ref_height and (
                    cx < 0.34 * ref_width or cx > 0.66 * ref_width
                )
                if at_roadside and len(t.trajectory) >= 8:
                    pts = t.trajectory[-8:]
                    displacement = math.sqrt(
                        (raw_cx - pts[0][0]) ** 2 + (raw_cy - pts[0][1]) ** 2
                    ) * scale
                    stopped_after_motion = (
                        t.max_speed_seen * scale >= 2.0
                        and t.speed * scale <= 0.55
                        and t.stationary_frames_after_motion >= 4
                        and displacement <= 12.0
                    )
                    impact_stop = stopped_after_motion and (
                        t.impact_deceleration_seen
                        or t.near_miss_frame >= frame_idx - max(12, int(fps * 2.0))
                    )
                    if impact_stop:
                        t.has_crashed = True
                        t.crash_frame = frame_idx
                        t.crash_type = "POSSIBLE ROADSIDE IMPACT"
            
            if t.has_crashed:
                t.state = "COLLISION"
                cx = (t.smoothed_box[0] + t.smoothed_box[2]) / 2.0
                cy = (t.smoothed_box[1] + t.smoothed_box[3]) / 2.0
                if not any(c.get("track_a") == t.track_id or c.get("track_b") == t.track_id for c in collisions):
                    collisions.append({
                        "type": "COLLISION",
                        "subtype": t.crash_type or "BARRIER_CRASH",
                        "track_a": t.track_id,
                        "track_b": None,
                        "class_a": t.class_name,
                        "class_b": None,
                        "severity": 86.0,
                        "center": (cx, cy),
                        "box": tuple(t.smoothed_box),
                        "iou": 1.0
                    })
                    max_risk = max(max_risk, 86.0)

        # 3. Persistent Incident Recording (Debounced across strides)
        time_sec = round(frame_idx / fps, 2) if fps > 0 else 0.0
        
        top_event = None
        if collisions:
            top_event = max(collisions, key=lambda c: c["severity"])
        elif near_misses:
            top_event = max(near_misses, key=lambda m: m["severity"])
            
        if top_event is not None:
            self.incident_grace_timer = max(6, self.frame_stride * 3)  # Maintain active incident across frame strides
            e_type = top_event["type"]
            e_sev = top_event["severity"]
            e_ttc = top_event.get("ttc_seconds")
            e_distance = top_event.get("closest_distance", top_event.get("dist"))
            
            if top_event.get("track_b"):
                v_text = f"{top_event.get('class_a')} #{top_event.get('track_a')} & {top_event.get('class_b')} #{top_event.get('track_b')}"
                pair_key = tuple(sorted([top_event.get('track_a'), top_event.get('track_b')]))
            else:
                v_text = f"{top_event.get('class_a', 'Vehicle')} #{top_event.get('track_a')} (Roadside Crash)"
                pair_key = (top_event.get('track_a'), -1)
                
            e_center = top_event.get("center") or top_event.get("center_a")
            e_box = top_event.get("box", (0, 0, 0, 0))
            
            if self.active_incident is None:
                self.active_incident = {
                    "incident_id": len(self.incident_history) + 1,
                    "type": e_type,
                    "color": "red" if e_type == "COLLISION" else "yellow",
                    "pair_key": pair_key,
                    "start_frame": frame_idx,
                    "end_frame": frame_idx,
                    "start_time": time_sec,
                    "end_time": time_sec,
                    "peak_severity": e_sev,
                    "ttc_seconds": e_ttc,
                    "relative_distance": e_distance,
                    "subtype": top_event.get("subtype", ""),
                    "track_a": top_event.get("track_a"),
                    "track_b": top_event.get("track_b"),
                    "class_a": top_event.get("class_a", "vehicle"),
                    "class_b": top_event.get("class_b"),
                    "vehicles": v_text,
                    "center": e_center,
                    "box": e_box,
                    "snapshot_file": None,
                    "frame_count": 1
                }
            else:
                if self.active_incident.get("pair_key") == pair_key:
                    # Same vehicle encounter: if escalated to collision, upgrade the incident cleanly
                    if e_type == "COLLISION" and self.active_incident["type"] != "COLLISION":
                        self.active_incident["type"] = "COLLISION"
                        self.active_incident["color"] = "red"
                    self.active_incident["end_frame"] = frame_idx
                    self.active_incident["end_time"] = time_sec
                    self.active_incident["frame_count"] += 1
                    self.active_incident["ttc_seconds"] = e_ttc
                    self.active_incident["relative_distance"] = e_distance
                    self.active_incident["subtype"] = top_event.get("subtype", self.active_incident.get("subtype", ""))
                    self.active_incident["track_a"] = top_event.get("track_a")
                    self.active_incident["track_b"] = top_event.get("track_b")
                    self.active_incident["class_a"] = top_event.get("class_a", "vehicle")
                    self.active_incident["class_b"] = top_event.get("class_b")
                    if e_sev > self.active_incident["peak_severity"]:
                        self.active_incident["peak_severity"] = e_sev
                        self.active_incident["center"] = e_center
                        self.active_incident["box"] = e_box
                else:
                    # New vehicle encounter: archive previous incident
                    self.incident_history.append(self.active_incident)
                    self.active_incident = {
                        "incident_id": len(self.incident_history) + 1,
                        "type": e_type,
                        "color": "red" if e_type == "COLLISION" else "yellow",
                        "pair_key": pair_key,
                        "start_frame": frame_idx,
                        "end_frame": frame_idx,
                        "start_time": time_sec,
                        "end_time": time_sec,
                        "peak_severity": e_sev,
                        "ttc_seconds": e_ttc,
                        "relative_distance": e_distance,
                        "subtype": top_event.get("subtype", ""),
                        "track_a": top_event.get("track_a"),
                        "track_b": top_event.get("track_b"),
                        "class_a": top_event.get("class_a", "vehicle"),
                        "class_b": top_event.get("class_b"),
                        "vehicles": v_text,
                        "center": e_center,
                        "box": e_box,
                        "snapshot_file": None,
                        "frame_count": 1
                    }
        else:
            if self.incident_grace_timer > 0:
                self.incident_grace_timer -= 1
            elif self.active_incident is not None:
                # Save incident to history
                self.incident_history.append(self.active_incident)
                self.active_incident = None

        return collisions, near_misses, max_risk

    def annotate_frame(
        self,
        frame: np.ndarray,
        frame_idx: int,
        fps: float,
        collisions: List[Dict[str, Any]],
        near_misses: List[Dict[str, Any]],
        risk_score: float,
    ) -> np.ndarray:
        """Render HUD with Red Collisions & Yellow Near Misses."""
        out = frame.copy()
        h, w = out.shape[:2]
        
        COLOR_COLLISION_RED = (0, 0, 255)       # BGR Vivid Red
        COLOR_NEAR_MISS_YELLOW = (0, 215, 255)   # BGR Vivid Amber / Yellow
        COLOR_SAFE_CYAN = (255, 220, 0)          # BGR Electric Cyan
        
        # 1. Proximity connecting lines for Near Misses
        for nm in near_misses:
            ptA = (int(nm["center_a"][0]), int(nm["center_a"][1]))
            ptB = (int(nm["center_b"][0]), int(nm["center_b"][1]))
            cv2.line(out, ptA, ptB, COLOR_NEAR_MISS_YELLOW, 2, cv2.LINE_AA)
            mid = ((ptA[0] + ptB[0]) // 2, (ptA[1] + ptB[1]) // 2)
            cv2.circle(out, mid, 4, COLOR_NEAR_MISS_YELLOW, -1, cv2.LINE_AA)
            cv2.putText(
                out,
                f"{nm['dist']}px",
                (mid[0] + 5, mid[1] - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                COLOR_NEAR_MISS_YELLOW,
                1,
                cv2.LINE_AA,
            )

        # 2. Vehicle Bounding Boxes
        for track_id, track in self.active_tracks.items():
            x1, y1, x2, y2 = [int(v) for v in track.smoothed_box]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            if track.has_crashed or track.state == "COLLISION":
                box_color = COLOR_COLLISION_RED
                box_thickness = 3
                cv2.rectangle(out, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), (0, 0, 180), 1)
                label = f"POSSIBLE CRASH #{track_id}" if track.crash_type.startswith("POSSIBLE") else f"CRASH #{track_id}"
                bg_color = (0, 0, 140)
                text_color = (255, 255, 255)
            elif track.state == "NEAR_MISS":
                box_color = COLOR_NEAR_MISS_YELLOW
                box_thickness = 2
                cv2.rectangle(out, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), (0, 160, 200), 1)
                label = f"NEAR-MISS #{track_id}"
                bg_color = (0, 80, 110)
                text_color = (255, 255, 255)
            else:
                box_color = COLOR_SAFE_CYAN
                box_thickness = 2
                label = f"#{track_id} {track.class_name.upper()} {int(track.confidence * 100)}%"
                bg_color = (12, 14, 20)
                text_color = box_color
                
            cv2.rectangle(out, (x1, y1), (x2, y2), box_color, box_thickness)
            
            # Corner accents
            line_len = min(12, int((x2 - x1) / 3), int((y2 - y1) / 3))
            accent_white = (255, 255, 255)
            cv2.line(out, (x1, y1), (x1 + line_len, y1), accent_white, 2)
            cv2.line(out, (x1, y1), (x1, y1 + line_len), accent_white, 2)
            cv2.line(out, (x2, y1), (x2 - line_len, y1), accent_white, 2)
            cv2.line(out, (x2, y1), (x2, y1 + line_len), accent_white, 2)
            cv2.line(out, (x1, y2), (x1 + line_len, y2), accent_white, 2)
            cv2.line(out, (x1, y2), (x1, y2 - line_len), accent_white, 2)
            cv2.line(out, (x2, y2), (x2 - line_len, y2), accent_white, 2)
            cv2.line(out, (x2, y2), (x2, y2 - line_len), accent_white, 2)
            
            # Label
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            label_y = max(y1 - 6, label_size[1] + 4)
            
            cv2.rectangle(
                out,
                (x1, label_y - label_size[1] - 3),
                (x1 + label_size[0] + 6, label_y + 3),
                bg_color,
                -1,
            )
            cv2.putText(
                out,
                label,
                (x1 + 3, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                text_color,
                1,
                cv2.LINE_AA,
            )
            
        # 3. Collision epicenter crosshairs
        for col in collisions:
            cx, cy = [int(v) for v in col["center"]]
            radius = int(18 + 6 * math.sin(frame_idx * 0.4))
            cv2.circle(out, (cx, cy), radius, COLOR_COLLISION_RED, 2, cv2.LINE_AA)
            cv2.circle(out, (cx, cy), 6, (0, 255, 255), -1, cv2.LINE_AA)
            cv2.line(out, (cx - radius - 5, cy), (cx + radius + 5, cy), COLOR_COLLISION_RED, 1)
            cv2.line(out, (cx, cy - radius - 5), (cx, cy + radius + 5), COLOR_COLLISION_RED, 1)
            box = col.get("box")
            if box and len(box) == 4:
                x1, y1, x2, y2 = [int(v) for v in box]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w - 1, x2), min(h - 1, y2)
                if x2 > x1 and y2 > y1:
                    cv2.rectangle(out, (x1, y1), (x2, y2), COLOR_COLLISION_RED, 3, cv2.LINE_AA)
                    cv2.line(out, (x1, y1), (x2, y2), COLOR_COLLISION_RED, 2, cv2.LINE_AA)
            
            if not col.get("subtype", "").startswith("POSSIBLE"):
                tag = f"CRASH ALERT {int(col['severity'])}%"
                tag_size, _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                tag_x = max(10, min(w - tag_size[0] - 10, cx - tag_size[0] // 2))
                tag_y = max(tag_size[1] + 10, cy - radius - 8)
                cv2.rectangle(out, (tag_x - 4, tag_y - tag_size[1] - 4), (tag_x + tag_size[0] + 4, tag_y + 4), (0, 0, 180), -1)
                cv2.putText(out, tag, (tag_x, tag_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)
            
        # 4. Top Telemetry HUD
        is_narrow = (w < 520)
        hud_h = 52 if is_narrow else 42
        hud_bg = out[0:hud_h, 0:w].copy()
        cv2.rectangle(hud_bg, (0, 0), (w, hud_h), (8, 11, 18), -1)
        cv2.addWeighted(hud_bg, 0.88, out[0:hud_h, 0:w], 0.12, 0, out[0:hud_h, 0:w])
        
        has_active_crash = any(t.has_crashed for t in self.active_tracks.values()) or bool(collisions)
        possible_crash = any(item.get("subtype", "").startswith("POSSIBLE") for item in collisions)
        
        if has_active_crash:
            border_color = COLOR_COLLISION_RED
            crash_score = max((item["severity"] for item in collisions), default=risk_score or 85)
            status_label = "POSSIBLE CRASH" if possible_crash else "CRASH DETECTED"
            status_text = f"{status_label} ({int(crash_score)}%)"
            status_color = COLOR_COLLISION_RED
            badge_bg = (35, 0, 0)
        elif near_misses or risk_score >= 30.0:
            border_color = COLOR_NEAR_MISS_YELLOW
            status_text = f"NEAR MISS ({int(risk_score)}%)" if is_narrow else f"NEAR MISS WARNING ({int(risk_score)}%)"
            status_color = COLOR_NEAR_MISS_YELLOW
            badge_bg = (35, 25, 0)
        else:
            border_color = (0, 220, 100)
            status_text = "TRAFFIC SECURE"
            status_color = (0, 255, 120)
            badge_bg = (0, 30, 15)
            
        cv2.line(out, (0, hud_h), (w, hud_h), border_color, 2)
        
        time_sec = frame_idx / fps if fps > 0 else 0.0
        time_str = f"T: {int(time_sec // 60):02d}:{time_sec % 60:04.1f}s | F:{frame_idx}"
        veh_str = f"Vehicles: {len(self.active_tracks)}"
        
        if is_narrow:
            # 2-Row Layout for Portrait/Narrow videos (e.g. 360x640):
            # Row 1: Centered Status Badge
            badge_fscale = 0.40
            badge_size, _ = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, badge_fscale, 1)
            badge_x = max(10, (w - badge_size[0]) // 2)
            cv2.rectangle(out, (badge_x - 8, 4), (badge_x + badge_size[0] + 8, 24), badge_bg, -1)
            cv2.rectangle(out, (badge_x - 8, 4), (badge_x + badge_size[0] + 8, 24), status_color, 1)
            cv2.putText(out, status_text, (badge_x, 18), cv2.FONT_HERSHEY_SIMPLEX, badge_fscale, status_color, 1, cv2.LINE_AA)
            
            # Row 2: Telemetry (Time on Left, Vehicles on Right)
            cv2.putText(out, time_str, (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (210, 215, 220), 1, cv2.LINE_AA)
            v_size, _ = cv2.getTextSize(veh_str, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
            cv2.putText(out, veh_str, (w - v_size[0] - 10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 230, 255), 1, cv2.LINE_AA)
        else:
            # 1-Row Layout for Widescreen videos:
            cv2.putText(out, time_str, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (220, 220, 220), 1, cv2.LINE_AA)
            
            badge_size, _ = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.46, 2)
            badge_x = (w - badge_size[0]) // 2
            cv2.rectangle(out, (badge_x - 10, 6), (badge_x + badge_size[0] + 10, 34), badge_bg, -1)
            cv2.rectangle(out, (badge_x - 10, 6), (badge_x + badge_size[0] + 10, 34), status_color, 1)
            cv2.putText(out, status_text, (badge_x, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.46, status_color, 2, cv2.LINE_AA)
            
            v_size, _ = cv2.getTextSize(veh_str, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
            cv2.putText(out, veh_str, (w - v_size[0] - 12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 230, 255), 1, cv2.LINE_AA)
        
        return out

    def process_video(
        self,
        video_path: str,
        output_path: str,
        snapshot_dir: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Process full video."""
        self.reset()
        os.makedirs(snapshot_dir, exist_ok=True)
        if os.path.dirname(output_path):
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Unable to open video: {video_path}")
            
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if fps <= 0 or math.isnan(fps):
            fps = 30.0
            
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        container = av.open(output_path, mode="w")
        stream = container.add_stream("h264", rate=int(round(fps)))
        stream.width = w
        stream.height = h
        stream.pix_fmt = "yuv420p"
        
        frame_idx = 0
        last_detections = []
        last_collisions = []
        last_near_misses = []
        last_risk = 0.0
        risk_timeline = []
        start_time = time.time()
        
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                    
                if frame_idx % self.frame_stride == 0:
                    last_detections = self.infer_frame(frame)
                    self.update_tracks(last_detections, frame_idx)
                    last_collisions, last_near_misses, last_risk = self.analyze_threats(frame_idx, fps)
                    
                    if self.active_incident is not None and self.active_incident.get("snapshot_file") is None:
                        snap_name = f"incident_{self.active_incident['incident_id']}_{self.active_incident['type'].lower()}_frame_{frame_idx}.jpg"
                        snap_path = os.path.join(snapshot_dir, snap_name)
                        snap_frame = self.annotate_frame(frame, frame_idx, fps, last_collisions, last_near_misses, last_risk)
                        cv2.imwrite(snap_path, snap_frame)
                        self.active_incident["snapshot_file"] = snap_name
                else:
                    for track in self.active_tracks.values():
                        track.extrapolate(dt=1)
                    last_collisions, last_near_misses, last_risk = self.analyze_threats(frame_idx, fps)
                        
                annotated = self.annotate_frame(frame, frame_idx, fps, last_collisions, last_near_misses, last_risk)
                
                av_frame = av.VideoFrame.from_ndarray(annotated, format="bgr24")
                for packet in stream.encode(av_frame):
                    container.mux(packet)
                    
                time_sec = round(frame_idx / fps, 2)
                if frame_idx % int(max(1, fps // 2)) == 0:
                    risk_timeline.append({
                        "time": time_sec,
                        "frame": frame_idx,
                        "risk": round(last_risk, 1),
                        "vehicles": len(self.active_tracks),
                        "collisions": len(last_collisions),
                        "near_misses": len(last_near_misses)
                    })
                    
                if progress_callback and (frame_idx % 10 == 0 or frame_idx == total_frames - 1):
                    pct = min(100.0, round((frame_idx + 1) / max(1, total_frames) * 100.0, 1))
                    elapsed = time.time() - start_time
                    fps_processed = round((frame_idx + 1) / max(0.1, elapsed), 1)
                    eta = round((total_frames - frame_idx - 1) / max(0.1, fps_processed), 1)
                    
                    collisions_count = len([inc for inc in self.incident_history if inc["type"] == "COLLISION"]) + (1 if self.active_incident and self.active_incident["type"] == "COLLISION" else 0)
                    near_miss_count = len([inc for inc in self.incident_history if inc["type"] == "NEAR_MISS"]) + (1 if self.active_incident and self.active_incident["type"] == "NEAR_MISS" else 0)
                    
                    progress_callback({
                        "progress": pct,
                        "current_frame": frame_idx,
                        "total_frames": total_frames,
                        "fps": fps_processed,
                        "eta_seconds": eta,
                        "current_risk": round(last_risk, 1),
                        "vehicles_detected": len(self.active_tracks),
                        "collisions_count": collisions_count,
                        "near_miss_count": near_miss_count,
                        "incidents_count": len(self.incident_history) + (1 if self.active_incident else 0)
                    })
                    
                frame_idx += 1
                
            for packet in stream.encode():
                container.mux(packet)
                
        finally:
            cap.release()
            container.close()
            
        if self.active_incident is not None:
            self.incident_history.append(self.active_incident)
            self.active_incident = None
            
        total_time = round(time.time() - start_time, 2)
        collisions_list = [inc for inc in self.incident_history if inc["type"] == "COLLISION"]
        near_miss_list = [inc for inc in self.incident_history if inc["type"] == "NEAR_MISS"]
        
        summary = {
            "status": "COMPLETED",
            "video_path": video_path,
            "output_path": output_path,
            "total_frames": total_frames,
            "fps": fps,
            "duration_seconds": round(total_frames / fps, 2),
            "processing_time_seconds": total_time,
            "fps_speed": round(total_frames / max(0.1, total_time), 1),
            "model_id": self.model_id,
            "incidents_detected": len(self.incident_history),
            "collisions_detected": len(collisions_list),
            "near_misses_detected": len(near_miss_list),
            "incidents": self.incident_history,
            "timeline": risk_timeline,
            "peak_risk": max([p["risk"] for p in risk_timeline]) if risk_timeline else 0.0
        }
        
        return summary
