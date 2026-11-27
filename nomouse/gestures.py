"""Hand-pose classification and predictable consecutive-frame confirmation."""
from __future__ import annotations

from collections import deque

from .geometry import angle_degrees, distance
from .types import Gesture, HandObservation

FINGER_JOINTS = {
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}


def classify_hand(hand: HandObservation, pinch_threshold: float = 0.34) -> Gesture:
    """Classify a single frame. Temporal confirmation belongs to GestureConsensus."""
    p = hand.landmarks
    if len(p) != 21:
        return Gesture.UNKNOWN
    try:
        if not all(0.0 <= float(coord) <= 1.5 for point in p for coord in point[:2]):
            return Gesture.UNKNOWN
        extended: dict[str, bool] = {}
        for name, (mcp, pip, dip, tip) in FINGER_JOINTS.items():
            pip_angle = angle_degrees(p[mcp], p[pip], p[dip])
            dip_angle = angle_degrees(p[pip], p[dip], p[tip])
            extended[name] = pip_angle > 145.0 and dip_angle > 135.0

        index, middle, ring, pinky = (extended[k] for k in ("index", "middle", "ring", "pinky"))
        open_count = sum(extended.values())
        thumb_tip_to_pinky_base = distance(p[4], p[17])
        thumb_mcp_to_pinky_base = distance(p[2], p[17])
        thumb_open = thumb_tip_to_pinky_base > thumb_mcp_to_pinky_base

        # Normalize pinch by palm width. Keep multi-finger gestures higher priority,
        # but classify PINCH before FIST because the index can be bent while pinching.
        palm_width = max(distance(p[5], p[17]), 0.035)
        pinch_ratio = distance(p[4], p[8]) / palm_width

        if open_count == 4:
            return Gesture.OPEN_PALM if thumb_open else Gesture.FOUR_FINGERS
        if index and middle and ring and not pinky:
            return Gesture.THREE_FINGERS
        if index and middle and not ring and not pinky:
            return Gesture.TWO_FINGERS
        if pinch_ratio < min(0.50, max(0.20, float(pinch_threshold))) and not middle and not ring and not pinky:
            return Gesture.PINCH
        if open_count == 0:
            return Gesture.FIST
        if index and not middle and not ring and not pinky:
            return Gesture.POINT
        return Gesture.UNKNOWN
    except (IndexError, TypeError, ValueError, ZeroDivisionError):
        return Gesture.UNKNOWN


class GestureConsensus:
    """Consecutive-frame transition confirmation with brief UNKNOWN tolerance.

    A short run of one noisy frame cannot change the active gesture. Using explicit
    consecutive counts avoids majority-vote latency and makes the time cost of each
    gesture confirmation understandable and tunable.
    """
    def __init__(
        self,
        window: int = 3,
        required_frames: int = 2,
        required_by_gesture: dict[Gesture, int] | None = None,
        unknown_grace_frames: int = 1,
    ):
        self.history: deque[Gesture] = deque(maxlen=max(1, int(window)))
        self.required_frames = max(1, int(required_frames))
        self.required_by_gesture = {k: max(1, int(v)) for k, v in (required_by_gesture or {}).items()}
        self.unknown_grace_frames = max(0, int(unknown_grace_frames))
        self.unknown_count = 0
        self.current = Gesture.UNKNOWN
        self.pending = Gesture.UNKNOWN
        self.pending_count = 0

    def reset(self) -> None:
        self.history.clear()
        self.current = Gesture.UNKNOWN
        self.pending = Gesture.UNKNOWN
        self.pending_count = 0
        self.unknown_count = 0

    def update(self, candidate: Gesture) -> Gesture:
        if candidate == Gesture.UNKNOWN:
            # A single ambiguous frame is common during normal hand movement. Keep
            # the last confirmed pose briefly, but the app must not dispatch actions
            # on the ambiguous frame. Persistent UNKNOWN still resets the state.
            self.pending = Gesture.UNKNOWN
            self.pending_count = 0
            self.unknown_count += 1
            if self.unknown_count <= self.unknown_grace_frames:
                return self.current
            self.current = Gesture.UNKNOWN
            self.history.clear()
            return self.current
        self.unknown_count = 0
        self.history.append(candidate)
        if candidate == self.current:
            self.pending = Gesture.UNKNOWN
            self.pending_count = 0
            return self.current
        if candidate != self.pending:
            self.pending = candidate
            self.pending_count = 1
        else:
            self.pending_count += 1
        required = self.required_by_gesture.get(candidate, self.required_frames)
        if self.pending_count >= required:
            self.current = candidate
            self.pending = Gesture.UNKNOWN
            self.pending_count = 0
        return self.current
