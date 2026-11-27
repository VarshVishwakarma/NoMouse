"""MediaPipe wrapper. The camera frames stay on the local machine."""
from __future__ import annotations

import time

import cv2
import mediapipe as mp

from .errors import StartupError
from .types import HandObservation


class HandTracker:
    def __init__(
        self,
        max_hands: int = 1,
        detection_confidence: float = 0.65,
        tracking_confidence: float = 0.60,
        model_complexity: int = 0,
    ):
        self._mp = mp
        if not hasattr(mp, "solutions"):
            raise StartupError(
                "This NoMouse release uses MediaPipe's legacy Hands API. "
                "Install the pinned dependency set from requirements.txt inside the active .venv: "
                "python -m pip install -r requirements.txt"
            )
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            model_complexity=min(1, max(0, int(model_complexity))),
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )
        self._draw = mp.solutions.drawing_utils
        self._connections = mp.solutions.hands.HAND_CONNECTIONS
        self.last_inference_ms = 0.0

    def process(self, bgr_frame):
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        start = time.perf_counter()
        result = self._hands.process(rgb)
        self.last_inference_ms = (time.perf_counter() - start) * 1000.0
        observations: list[HandObservation] = []
        if result.multi_hand_landmarks:
            for idx, hand in enumerate(result.multi_hand_landmarks):
                handedness = "Right"
                confidence = 0.0
                if result.multi_handedness and idx < len(result.multi_handedness):
                    classification = result.multi_handedness[idx].classification[0]
                    handedness = classification.label
                    confidence = float(classification.score)
                points = tuple((float(p.x), float(p.y), float(p.z)) for p in hand.landmark)
                observations.append(HandObservation(points, handedness, confidence))
        return observations, result

    def draw_landmarks(self, frame, result) -> None:
        if result.multi_hand_landmarks:
            for hand in result.multi_hand_landmarks:
                self._draw.draw_landmarks(frame, hand, self._connections)

    def close(self) -> None:
        self._hands.close()
