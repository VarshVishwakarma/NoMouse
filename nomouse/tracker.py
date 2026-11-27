"""Local MediaPipe Tasks hand-landmarker wrapper."""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import mediapipe as mp

from .errors import StartupError
from .types import HandObservation

_MODEL_PATH = Path(__file__).resolve().parent / "models" / "hand_landmarker.task"


class HandTracker:
    def __init__(
        self,
        max_hands: int = 1,
        detection_confidence: float = 0.65,
        tracking_confidence: float = 0.60,
        model_complexity: int = 0,
    ):
        del model_complexity  # Kept for compatibility with existing callers and settings.
        if not _MODEL_PATH.is_file():
            raise StartupError(f"The bundled hand-tracking model is missing: {_MODEL_PATH.name}")
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(_MODEL_PATH)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=detection_confidence,
            min_hand_presence_confidence=tracking_confidence,
            min_tracking_confidence=tracking_confidence,
        )
        self._hands = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self.last_inference_ms = 0.0
        self._last_timestamp_ms = -1
        self._connections = mp.tasks.vision.HandLandmarksConnections.HAND_CONNECTIONS

    def process(self, bgr_frame):
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = max(time.monotonic_ns() // 1_000_000, self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp_ms
        start = time.perf_counter()
        result = self._hands.detect_for_video(image, timestamp_ms)
        self.last_inference_ms = (time.perf_counter() - start) * 1000.0
        observations: list[HandObservation] = []
        for index, landmarks in enumerate(result.hand_landmarks):
            handedness = "Right"
            confidence = 0.0
            if index < len(result.handedness) and result.handedness[index]:
                category = result.handedness[index][0]
                handedness = category.category_name
                confidence = float(category.score)
            points = tuple((float(p.x), float(p.y), float(p.z)) for p in landmarks)
            observations.append(HandObservation(points, handedness, confidence))
        return observations, result

    def draw_landmarks(self, frame, result) -> None:
        height, width = frame.shape[:2]
        for landmarks in result.hand_landmarks:
            points = [
                (round(p.x * (width - 1)), round(p.y * (height - 1)))
                for p in landmarks
            ]
            for connection in self._connections:
                cv2.line(
                    frame,
                    points[connection.start],
                    points[connection.end],
                    (90, 220, 130),
                    2,
                    cv2.LINE_AA,
                )
            for point in points:
                cv2.circle(frame, point, 3, (230, 250, 235), -1, cv2.LINE_AA)

    def close(self) -> None:
        self._hands.close()
