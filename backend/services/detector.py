"""Detector interface with a deterministic demo detector and optional YOLO."""
from config import DEMO_MODE, YOLO_CONFIDENCE, YOLO_MODEL_PATH, TRACKED_CLASSES


class MockDetector:
    """Generate plausible moving boxes for a video demo without a model file."""
    def detect(self, frame, frame_index: int) -> list[dict]:
        height, width = frame.shape[:2]
        phase = (frame_index // 2) % 40
        items = [
            ("car", .18 + phase * .008, .64, .20, .13),
            ("person", .63, .28 + phase * .006, .045, .12),
            ("motorcycle", .55 - phase * .004, .58, .07, .065),
        ]
        output = []
        for label, x, y, w, h in items:
            x = min(max(x, .03), .90)
            y = min(max(y, .12), .80)
            output.append({"class_name": label, "confidence": .86,
                           "box": (x * width, y * height, (x + w) * width, (y + h) * height)})
        return output


class YoloDetector:
    """Thin adapter for Ultralytics YOLO so the rest of the pipeline stays modular."""
    def __init__(self) -> None:
        if not YOLO_MODEL_PATH.is_file():
            raise FileNotFoundError(f"YOLO weights not found: {YOLO_MODEL_PATH}. Set YOLO_MODEL_PATH to a model file.")
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("Ultralytics is not installed. Install backend requirements to process real footage.") from exc
        self.model = YOLO(str(YOLO_MODEL_PATH))
        # Limit CPU contention so video analysis does not freeze the local UI.
        try:
            import torch
            torch.set_num_threads(2)
            torch.set_num_interop_threads(1)
        except (ImportError, RuntimeError):
            pass

    def detect(self, frame, frame_index: int) -> list[dict]:
        results = self.model.predict(frame, conf=YOLO_CONFIDENCE, imgsz=480, verbose=False)
        output = []
        for result in results:
            names = result.names
            for box in result.boxes:
                class_name = names[int(box.cls[0])].lower()
                if class_name not in TRACKED_CLASSES:
                    continue
                coords = box.xyxy[0].cpu().tolist()
                output.append({"class_name": class_name, "confidence": float(box.conf[0]),
                               "box": tuple(float(value) for value in coords)})
        return output


def create_detector():
    if DEMO_MODE:
        return MockDetector()
    return YoloDetector()
