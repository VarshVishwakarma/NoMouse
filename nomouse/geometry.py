from __future__ import annotations

import math
from collections.abc import Sequence

Point = Sequence[float]


def distance(a: Point, b: Point) -> float:
    """2D normalized-image distance for MediaPipe x/y landmark coordinates."""
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def angle_degrees(a: Point, b: Point, c: Point) -> float:
    """Angle ABC in the image plane; 180 degrees means nearly straight joints."""
    bax = float(a[0]) - float(b[0])
    bay = float(a[1]) - float(b[1])
    bcx = float(c[0]) - float(b[0])
    bcy = float(c[1]) - float(b[1])
    denom = math.hypot(bax, bay) * math.hypot(bcx, bcy)
    if denom < 1e-9:
        return 0.0
    cosine = max(-1.0, min(1.0, (bax * bcx + bay * bcy) / denom))
    return math.degrees(math.acos(cosine))


def normalize_point(x: float, y: float, margin: float) -> tuple[float, float]:
    """Map a camera region into 0..1 and clamp noisy edge excursions."""
    margin = min(max(float(margin), 0.0), 0.40)
    usable = max(1e-6, 1.0 - 2.0 * margin)
    nx = (float(x) - margin) / usable
    ny = (float(y) - margin) / usable
    return max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))


def to_screen_float(
    x: float,
    y: float,
    screen_width: int,
    screen_height: int,
    margin: float,
    inset_px: float = 0.0,
) -> tuple[float, float]:
    """Map normalized camera coordinates to floating-point desktop coordinates.

    ``inset_px`` keeps the hand-driven pointer a few pixels away from the screen
    edges. PyAutoGUI treats the four exact corner pixels as emergency fail-safe
    points, so without an inset a hand resting at the edge of the active region
    (for example while reaching for a window's close button) would trip it.
    """
    nx, ny = normalize_point(x, y, margin)
    max_x = max(0, screen_width - 1)
    max_y = max(0, screen_height - 1)
    # Never let the inset consume the whole screen on tiny/odd displays.
    inset_x = min(max(0.0, float(inset_px)), max_x / 2.0)
    inset_y = min(max(0.0, float(inset_px)), max_y / 2.0)
    return (
        inset_x + nx * (max_x - 2.0 * inset_x),
        inset_y + ny * (max_y - 2.0 * inset_y),
    )


def to_screen(
    x: float,
    y: float,
    screen_width: int,
    screen_height: int,
    margin: float,
    inset_px: float = 0.0,
) -> tuple[int, int]:
    sx, sy = to_screen_float(x, y, screen_width, screen_height, margin, inset_px)
    return int(round(sx)), int(round(sy))
