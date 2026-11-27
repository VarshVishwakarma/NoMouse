from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Gesture(str, Enum):
    POINT = "POINT"
    PINCH = "PINCH"
    TWO_FINGERS = "TWO FINGERS"
    THREE_FINGERS = "THREE FINGERS"
    FOUR_FINGERS = "FOUR FINGERS"
    OPEN_PALM = "OPEN PALM"
    FIST = "FIST"
    UNKNOWN = "SEARCHING"


@dataclass(frozen=True)
class HandObservation:
    # MediaPipe image-normalized x/y coordinates (0.0 to 1.0).
    landmarks: tuple[tuple[float, float, float], ...]
    handedness: str = "Right"
    confidence: float = 0.0


@dataclass
class FrameMetrics:
    fps: float = 0.0
    inference_ms: float = 0.0
    cursor_x: int | None = None
    cursor_y: int | None = None
    mode: str = "MOUSE"
    safety_blocked: bool = False
    notification: str = ""
    notification_until: float = 0.0
