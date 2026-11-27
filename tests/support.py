"""Shared test doubles and synthetic-hand builders (no camera or OS input needed)."""
from __future__ import annotations

from nomouse.types import HandObservation


class FakeMouse:
    class FailSafeException(Exception):
        pass

    def __init__(self):
        self.events = []
        self.FAILSAFE = True
        self.PAUSE = 0.1
        self.xy = (400, 300)

    def position(self):
        return self.xy

    def size(self):
        return (1920, 1080)

    def moveTo(self, x, y, duration=0):
        self.xy = (x, y)
        self.events.append(("move", x, y))

    def click(self, button="left"):
        self.events.append(("click", button))

    def doubleClick(self, interval=0.08):
        self.events.append(("double", interval))

    def mouseDown(self, button="left"):
        self.events.append(("down", button))

    def mouseUp(self, button="left"):
        self.events.append(("up", button))

    def scroll(self, clicks):
        self.events.append(("scroll", clicks))

    def hotkey(self, *keys):
        self.events.append(("hotkey", *keys))


class SafeGuard:
    last_reason = ""

    def allows_action(self, x, y):
        return True


class BlockGuard:
    last_reason = "test block"

    def allows_action(self, x, y):
        return False


def translate(hand: HandObservation, dx: float, dy: float) -> HandObservation:
    """Shift every landmark of a synthetic hand in normalized image coordinates."""
    return HandObservation(tuple((x + dx, y + dy, z) for x, y, z in hand.landmarks))


_FINGERS = {
    "index": (5, 6, 7, 8, 0.40),
    "middle": (9, 10, 11, 12, 0.48),
    "ring": (13, 14, 15, 16, 0.56),
    "pinky": (17, 18, 19, 20, 0.64),
}


def make_hand(extended: tuple[str, ...], thumb_open: bool = False) -> HandObservation:
    """A coherent 21-point hand with the named fingers straight and the rest curled."""
    points = [(0.50, 0.82, 0.0) for _ in range(21)]
    points[1] = (0.43, 0.70, 0.0)
    points[2] = (0.39, 0.65, 0.0)
    points[3] = (0.34, 0.60, 0.0)
    points[4] = (0.28, 0.54, 0.0) if thumb_open else (0.49, 0.63, 0.0)
    for name, (mcp, pip, dip, tip, x) in _FINGERS.items():
        points[mcp] = (x, 0.58, 0.0)
        if name in extended:
            points[pip], points[dip], points[tip] = (x, 0.43, 0.0), (x, 0.27, 0.0), (x, 0.10, 0.0)
        else:
            points[pip], points[dip], points[tip] = (x, 0.44, 0.0), (x + 0.045, 0.49, 0.0), (x + 0.08, 0.45, 0.0)
    return HandObservation(tuple(points))


def pointing_hand() -> HandObservation:
    return make_hand(("index",))


def two_finger_hand() -> HandObservation:
    return make_hand(("index", "middle"))


def fist_hand() -> HandObservation:
    return make_hand(())


def pinch_hand() -> HandObservation:
    """Bent index with thumb/index tips touching and the other fingers folded."""
    p = [(0.50, 0.80, 0.0) for _ in range(21)]
    thumb = ((0.50, 0.88, 0.0), (0.47, 0.77, 0.0), (0.45, 0.70, 0.0), (0.47, 0.62, 0.0), (0.50, 0.55, 0.0))
    p[0:5] = thumb
    p[5], p[6], p[7], p[8] = (0.42, 0.62, 0.0), (0.42, 0.50, 0.0), (0.48, 0.48, 0.0), (0.50, 0.55, 0.0)
    for mcp, pip, dip, tip, x in ((9, 10, 11, 12, 0.50), (13, 14, 15, 16, 0.57), (17, 18, 19, 20, 0.64)):
        p[mcp], p[pip], p[dip], p[tip] = (x, 0.63, 0.0), (x, 0.53, 0.0), (x + 0.045, 0.54, 0.0), (x + 0.085, 0.60, 0.0)
    return HandObservation(tuple(p))
