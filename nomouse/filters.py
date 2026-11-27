"""Low-latency coordinate filtering for webcam-driven cursor motion.

The One Euro filter uses the previous *raw* sample for its derivative and the
previous filtered sample for its output. Keeping those histories separate is
important: mixing them makes the velocity estimate depend on filter lag and can
produce unnecessary cutoff changes (the old implementation did that).
"""
from __future__ import annotations

import math


class OneEuroFilter:
    """Adaptive low-pass filter: stable at rest, responsive during fast motion."""

    def __init__(self, min_cutoff: float = 2.0, beta: float = 0.008, d_cutoff: float = 1.0):
        self.min_cutoff = max(0.01, float(min_cutoff))
        self.beta = max(0.0, float(beta))
        self.d_cutoff = max(0.01, float(d_cutoff))
        self._raw_prev: float | None = None
        self._filtered_prev: float | None = None
        self._dx_prev = 0.0
        self._t_prev: float | None = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        cutoff = max(0.01, float(cutoff))
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / max(float(dt), 1e-6))

    def reset(self) -> None:
        self._raw_prev = None
        self._filtered_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    def __call__(self, value: float, timestamp: float) -> float:
        value = float(value)
        timestamp = float(timestamp)
        if self._raw_prev is None or self._filtered_prev is None or self._t_prev is None:
            self._raw_prev = value
            self._filtered_prev = value
            self._dx_prev = 0.0
            self._t_prev = timestamp
            return value

        # Clamp pathological/non-monotonic timestamps without letting a bad delta
        # poison the filter. Store the effective timestamp too, so a clock regression
        # cannot make the next sample's delta artificially large.
        timestamp = max(timestamp, self._t_prev + 1e-4)
        dt = timestamp - self._t_prev
        derivative = (value - self._raw_prev) / dt
        edx = self._dx_prev + self._alpha(self.d_cutoff, dt) * (derivative - self._dx_prev)
        cutoff = self.min_cutoff + self.beta * abs(edx)
        filtered = self._filtered_prev + self._alpha(cutoff, dt) * (value - self._filtered_prev)

        self._raw_prev = value
        self._filtered_prev = filtered
        self._dx_prev = edx
        self._t_prev = timestamp
        return filtered


class AxisSmoother:
    """Apply independent, time-aware One Euro filters to X and Y coordinates."""

    def __init__(self, min_cutoff: float = 2.0, beta: float = 0.008):
        self.x = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self.y = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)

    def reset(self) -> None:
        self.x.reset()
        self.y.reset()

    def apply(self, x: float, y: float, timestamp: float) -> tuple[float, float]:
        return self.x(x, timestamp), self.y(y, timestamp)
