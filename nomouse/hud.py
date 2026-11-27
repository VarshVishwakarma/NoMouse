"""Preview-window HUD: a compact status card, help overlay, and toast notifications.

Everything here is drawn with plain OpenCV primitives. Translucent panels only
blend the small region they cover (not the full frame), so the overlay stays
cheap even on slow machines, and all sizes scale with the frame so the HUD looks
the same at 640x480 and at 1280x720.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import cv2

from . import __version__
from .types import FrameMetrics, Gesture

WINDOW_NAME = "NoMouse | Touchless Control"

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_AA = cv2.LINE_AA

# Colors are BGR (OpenCV order).
_PANEL = (30, 24, 20)
_TEXT = (245, 240, 235)
_TEXT_DIM = (170, 160, 150)
_ACCENT = (250, 190, 90)
_GREEN = (130, 225, 120)
_AMBER = (70, 190, 250)
_RED = (95, 95, 240)

_GESTURE_COLORS: dict[Gesture, tuple[int, int, int]] = {
    Gesture.POINT: _ACCENT,
    Gesture.PINCH: _AMBER,
    Gesture.TWO_FINGERS: (255, 150, 185),
    Gesture.THREE_FINGERS: (200, 220, 120),
    Gesture.FOUR_FINGERS: (120, 150, 255),
    Gesture.OPEN_PALM: _GREEN,
    Gesture.FIST: (170, 170, 170),
    Gesture.UNKNOWN: (110, 105, 100),
}

HELP_LINES: tuple[tuple[str, str], ...] = (
    ("Index finger", "Move the cursor"),
    ("Quick pinch", "Left-click"),
    ("Hold pinch", "Drag and drop"),
    ("Two quick pinches", "Double-click"),
    ("Two fingers, tap", "Right-click"),
    ("Two fingers, up / down", "Scroll"),
    ("4 fingers, thumb tucked", "Browser back"),
    ("Open palm / fist", "Rest (no action)"),
    ("O", "Toggle preview always-on-top"),
)

FOOTER_TEXT = "H Help   P Pause   +/- Smoothing   L Landmarks   O Topmost   Q Quit"


@dataclass
class HudState:
    """User-toggled HUD state. The help card auto-hides shortly after startup."""

    show_help: bool = False
    auto_hide_at: float | None = None

    @classmethod
    def at_startup(cls, show_help: bool, now: float, seconds: float = 8.0) -> HudState:
        return cls(show_help=show_help, auto_hide_at=(now + seconds) if show_help else None)

    def help_visible(self, now: float) -> bool:
        if self.auto_hide_at is not None and now >= self.auto_hide_at:
            self.show_help = False
            self.auto_hide_at = None
        return self.show_help

    def toggle_help(self) -> None:
        self.show_help = not self.show_help
        self.auto_hide_at = None


def ascii_text(text: str) -> str:
    """OpenCV's Hershey fonts cannot draw non-ASCII; replace instead of showing '?'."""
    replacements = {"\u2014": "-", "\u2013": "-", "\u2019": "'", "\u00b7": "|"}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("ascii", "replace").decode("ascii")


def _text_size(text: str, scale: float, thickness: int) -> tuple[int, int]:
    (width, height), _ = cv2.getTextSize(text, _FONT, scale, thickness)
    return width, height


def _put(frame, text: str, org: tuple[int, int], scale: float, color, thickness: int = 1) -> None:
    cv2.putText(frame, text, org, _FONT, scale, color, thickness, _AA)


def _rounded_rect(img, x1: int, y1: int, x2: int, y2: int, radius: int, color) -> None:
    radius = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    cv2.rectangle(img, (x1 + radius, y1), (x2 - radius, y2), color, -1)
    cv2.rectangle(img, (x1, y1 + radius), (x2, y2 - radius), color, -1)
    for cx, cy in ((x1 + radius, y1 + radius), (x2 - radius, y1 + radius),
                   (x1 + radius, y2 - radius), (x2 - radius, y2 - radius)):
        cv2.circle(img, (cx, cy), radius, color, -1, _AA)


def _panel(frame, x1: int, y1: int, x2: int, y2: int, radius: int, alpha: float, color=_PANEL) -> None:
    """Blend a rounded translucent panel, touching only the pixels it covers."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w - 1, x2), min(h - 1, y2)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    roi = frame[y1:y2 + 1, x1:x2 + 1]
    layer = roi.copy()
    _rounded_rect(layer, 0, 0, x2 - x1, y2 - y1, radius, color)
    cv2.addWeighted(layer, alpha, roi, 1.0 - alpha, 0.0, dst=roi)


def _pill(frame, text: str, right: int, top: int, height: int, scale: float, color) -> int:
    """Draw a solid status pill whose right edge is ``right``; return its left edge."""
    text = ascii_text(text)
    text_w, text_h = _text_size(text, scale, 1)
    pad = height // 2
    left = right - text_w - pad * 2
    _rounded_rect(frame, left, top, right, top + height, height // 2, color)
    _put(frame, text, (left + pad, top + (height + text_h) // 2), scale, (25, 20, 15), 1)
    return left


def _corner_brackets(frame, x1: int, y1: int, x2: int, y2: int, length: int, color, thickness: int,
                     avoid: tuple[int, int, int, int] | None = None) -> None:
    for (cx, cy, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        if avoid is not None and avoid[0] - length <= cx <= avoid[2] and avoid[1] - length <= cy <= avoid[3]:
            continue  # this corner would peek out from under the status card
        cv2.line(frame, (cx, cy), (cx + dx * length, cy), color, thickness, _AA)
        cv2.line(frame, (cx, cy), (cx, cy + dy * length), color, thickness, _AA)


def _fps_color(fps: float) -> tuple[int, int, int]:
    if fps >= 24:
        return _GREEN
    if fps >= 15:
        return _AMBER
    return _RED


def _draw_status_card(frame, s: float, gesture: Gesture, metrics: FrameMetrics, enabled: bool) -> None:
    x, y = int(12 * s), int(12 * s)
    card_w, card_h = int(300 * s), int(70 * s)
    h, w = frame.shape[:2]
    card_w = min(card_w, w - 2 * x)
    _panel(frame, x, y, x + card_w, y + card_h, int(12 * s), 0.74)
    inner = int(14 * s)

    title_scale = 0.62 * s
    _put(frame, "NoMouse", (x + inner, y + int(28 * s)), title_scale, _TEXT, 2)
    title_w, _ = _text_size("NoMouse", title_scale, 2)
    _put(frame, f"v{__version__}", (x + inner + title_w + int(8 * s), y + int(28 * s)), 0.38 * s, _TEXT_DIM)

    if metrics.safety_blocked:
        label, color = "SAFETY HOLD", _RED
    elif enabled:
        label, color = "ACTIVE", _GREEN
    else:
        label, color = "PAUSED", _AMBER
    _pill(frame, label, x + card_w - inner, y + int(10 * s), int(24 * s), 0.42 * s, color)

    row_y = y + int(54 * s)
    dot = _GESTURE_COLORS.get(gesture, _TEXT_DIM)
    cv2.circle(frame, (x + inner + int(5 * s), row_y - int(5 * s)), max(3, int(5 * s)), dot, -1, _AA)
    name = ascii_text(gesture.value)
    _put(frame, name, (x + inner + int(18 * s), row_y), 0.46 * s, _TEXT)

    stats = f"{metrics.fps:4.0f} fps  {metrics.inference_ms:4.1f} ms"
    stats_w, _ = _text_size(stats, 0.38 * s, 1)
    _put(frame, stats, (x + card_w - inner - stats_w, row_y), 0.38 * s, _fps_color(metrics.fps))


def _draw_help_card(frame, s: float) -> None:
    h, w = frame.shape[:2]
    line_h = int(23 * s)
    pad = int(18 * s)
    card_w = min(int(360 * s), w - int(24 * s))
    card_h = pad * 2 + int(26 * s) + line_h * len(HELP_LINES)
    x = (w - card_w) // 2
    y = max(int(90 * s), (h - card_h) // 2)
    if y + card_h > h - int(40 * s):
        y = max(int(8 * s), h - int(40 * s) - card_h)
    _panel(frame, x, y, x + card_w, y + card_h, int(14 * s), 0.84)
    _put(frame, "Gestures", (x + pad, y + pad + int(10 * s)), 0.52 * s, _TEXT, 1)
    col2 = x + card_w - pad
    for i, (gesture, action) in enumerate(HELP_LINES):
        ty = y + pad + int(34 * s) + i * line_h
        _put(frame, gesture, (x + pad, ty), 0.40 * s, _ACCENT)
        action_w, _ = _text_size(action, 0.40 * s, 1)
        _put(frame, action, (col2 - action_w, ty), 0.40 * s, _TEXT)


def _draw_toast(frame, s: float, metrics: FrameMetrics, now: float) -> None:
    if not metrics.notification:
        return
    remaining = metrics.notification_until - now
    if remaining <= 0:
        return
    h, w = frame.shape[:2]
    text = ascii_text(metrics.notification)
    scale = 0.52 * s
    text_w, text_h = _text_size(text, scale, 1)
    pad_x, pad_y = int(16 * s), int(10 * s)
    box_w = min(w - int(24 * s), text_w + pad_x * 2)
    x1 = (w - box_w) // 2
    y2 = h - int(40 * s)
    y1 = y2 - text_h - pad_y * 2
    fade = max(0.0, min(1.0, remaining / 0.35))  # fade out over the last 350 ms
    _panel(frame, x1, y1, x1 + box_w, y2, int(12 * s), 0.80 * fade)
    if fade > 0.35:
        _put(frame, text, (x1 + (box_w - text_w) // 2, y2 - pad_y), scale, _GREEN if fade > 0.6 else _TEXT_DIM)


def _draw_footer(frame, s: float) -> None:
    h, w = frame.shape[:2]
    text_w, _ = _text_size(FOOTER_TEXT, 0.38 * s, 1)
    org = (max(int(8 * s), (w - text_w) // 2), h - int(14 * s))
    _put(frame, FOOTER_TEXT, org, 0.38 * s, (20, 16, 14), 3)  # outline keeps it legible on bright backgrounds
    _put(frame, FOOTER_TEXT, org, 0.38 * s, (225, 220, 214), 1)


def draw_hud(
    frame,
    gesture: Gesture,
    metrics: FrameMetrics,
    enabled: bool,
    config,
    show_help: bool = False,
    now: float | None = None,
) -> None:
    """Draw the full HUD onto ``frame`` in place."""
    h, w = frame.shape[:2]
    if h < 120 or w < 160:
        return  # Too small to render legibly; skip rather than draw garbage.
    now = time.monotonic() if now is None else now
    s = max(0.75, min(w / 640.0, h / 480.0))

    # Active-region guide: corner brackets are less visually noisy than a full box.
    margin_x = int(w * config.active_margin)
    margin_y = int(h * config.active_margin)
    guide_color = _ACCENT if enabled else _AMBER
    card = (int(12 * s), int(12 * s), int(12 * s) + min(int(300 * s), w - int(24 * s)), int(12 * s) + int(70 * s))
    _corner_brackets(frame, margin_x, margin_y, w - margin_x, h - margin_y,
                     int(22 * s), guide_color, max(1, int(2 * s)), avoid=card)

    _draw_status_card(frame, s, gesture, metrics, enabled)
    if show_help:
        _draw_help_card(frame, s)
    _draw_toast(frame, s, metrics, now)
    _draw_footer(frame, s)
