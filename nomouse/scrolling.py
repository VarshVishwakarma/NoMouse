"""Rate-based scrolling: hold your hand above or below where it started to scroll.

Think of a joystick. The height where the two-finger pose begins is the neutral
point. Moving past a small dead zone scrolls, and the farther you go the faster it
scrolls; moving back to neutral stops. Because speed depends on *where your hand
is* rather than on *how it just moved*, the return motion never scrolls the other
way and there is nothing to "re-arm" between scrolls.

Output is in raw wheel-delta units, where ``WHEEL_DELTA`` (120) equals one notch
of a physical mouse wheel. Many apps accept finer steps, which keeps slow scrolling
smooth; ``wheel_step`` sets the finest step that is sent.
"""
from __future__ import annotations

import math

WHEEL_DELTA = 120            # one physical wheel notch
START_SPEED = 1.5            # notches/second right outside the dead zone
CURVE_EXPONENT = 1.6         # >1 keeps small offsets gentle and large ones quick
MAX_FRAME_DT = 0.1           # never "catch up" more than this after a stalled frame
FOLLOW_TAU = 0.8             # seconds for the neutral point to follow slow drift


class RateScroller:
    def __init__(
        self,
        deadzone_px: float = 20.0,
        full_speed_px: float = 200.0,
        max_speed: float = 25.0,
        wheel_step: int = 40,
        invert: bool = False,
    ) -> None:
        self.deadzone_px = max(1.0, float(deadzone_px))
        self.full_speed_px = max(1.0, float(full_speed_px))
        self.max_speed = max(0.1, float(max_speed))
        self.wheel_step = max(1, min(WHEEL_DELTA, int(wheel_step)))
        self.invert = bool(invert)
        self.reset()

    def reset(self, y: float | None = None, now: float | None = None) -> None:
        """Make ``y`` the neutral point (or clear it, if ``y`` is None)."""
        self.anchor_y: float | None = None if y is None else float(y)
        self.last_time: float | None = now
        self.carry = 0.0

    def speed(self, offset_px: float) -> float:
        """Scroll speed in notches/second for a hand offset (always >= 0)."""
        excess = abs(offset_px) - self.deadzone_px
        if excess <= 0.0:
            return 0.0
        ramp = min(1.0, excess / self.full_speed_px)
        start = min(START_SPEED, self.max_speed)
        return start + (self.max_speed - start) * ramp ** CURVE_EXPONENT

    def update(self, y: float, now: float) -> int:
        """Return the wheel delta to send this frame (0 for none).

        Negative values scroll down. Screen Y grows downward, so a hand held
        *below* the neutral point scrolls down (unless ``invert`` is set).
        """
        y = float(y)
        if self.anchor_y is None:
            self.reset(y, now)
            return 0
        dt = 0.0 if self.last_time is None else min(MAX_FRAME_DT, max(0.0, now - self.last_time))
        self.last_time = now

        offset = y - self.anchor_y
        speed = self.speed(offset)
        if speed == 0.0:
            # Resting inside the dead zone: let the neutral point follow slow drift
            # (a tired arm sinking) without ever absorbing a deliberate movement.
            self.anchor_y += (1.0 - math.exp(-dt / FOLLOW_TAU)) * offset
            self.carry = 0.0
            return 0

        direction = -1.0 if offset > 0 else 1.0
        if self.invert:
            direction = -direction
        if self.carry * direction < 0:
            self.carry = 0.0  # reversed direction: drop leftovers from the other way
        self.carry += direction * speed * WHEEL_DELTA * dt

        steps = int(abs(self.carry) // self.wheel_step)
        if steps == 0:
            return 0
        emit = int(math.copysign(steps * self.wheel_step, self.carry))
        self.carry -= emit
        return emit
