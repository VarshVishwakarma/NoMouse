from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def default_config_path() -> Path:
    """Where settings live when no ``--config`` is given.

    A source checkout (the folder containing ``main.py``) uses its own ``config/``
    folder, resolved from the package location rather than the working directory,
    so shortcuts and launches from other folders behave the same. A pip-installed
    copy must not write into site-packages, so it uses a per-user location instead.
    """
    if (PROJECT_ROOT / "main.py").exists():
        return PROJECT_ROOT / "config" / "settings.json"
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "NoMouse" / "settings.json"


DEFAULT_CONFIG_PATH = default_config_path()


@dataclass
class AppConfig:
    camera_index: int = 0
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30
    model_complexity: int = 0
    mirror_preview: bool = True
    max_hands: int = 1
    min_detection_confidence: float = 0.60
    min_tracking_confidence: float = 0.55
    active_margin: float = 0.08
    cursor_smoothing: float = 0.38
    cursor_move_deadband_px: float = 0.7
    screen_edge_inset_px: int = 2
    click_confirm_frames: int = 2
    right_click_confirm_frames: int = 2
    double_click_confirm_frames: int = 3
    browser_back_confirm_frames: int = 3
    gesture_history: int = 3
    click_cooldown_s: float = 0.16
    right_click_cooldown_s: float = 0.45
    double_click_cooldown_s: float = 0.55
    browser_back_cooldown_s: float = 0.80
    double_click_commit_delay_s: float = 0.14
    scroll_deadzone_px: float = 20.0
    scroll_max_speed: float = 25.0
    scroll_full_speed_px: float = 200.0
    scroll_wheel_step: int = 40
    scroll_invert: bool = False
    scroll_filter_min_cutoff: float = 3.0
    right_click_tap_max_s: float = 0.45
    drag_hold_s: float = 0.42
    three_finger_double_click_enabled: bool = False
    left_click_enabled: bool = True
    right_click_enabled: bool = True
    scroll_enabled: bool = True
    browser_back_enabled: bool = True
    pinch_threshold: float = 0.34
    hud_enabled: bool = True
    show_landmarks: bool = True
    show_help_on_start: bool = True
    safety_guard_enabled: bool = True
    # Keep the OpenCV preview visible above other apps for demos and daily use.
    preview_always_on_top: bool = True
    onboarding_complete: bool = False


# Settings are clamped to safe/meaningful ranges when loaded from disk. This prevents
# a hand-edited or damaged JSON file from setting impossible thresholds or timings.
_FLOAT_RANGES: dict[str, tuple[float, float]] = {
    "min_detection_confidence": (0.10, 0.99),
    "min_tracking_confidence": (0.10, 0.99),
    "active_margin": (0.0, 0.35),
    "cursor_smoothing": (0.0, 1.0),
    "cursor_move_deadband_px": (0.0, 10.0),
    "click_cooldown_s": (0.05, 1.5),
    "right_click_cooldown_s": (0.05, 2.0),
    "double_click_cooldown_s": (0.05, 2.0),
    "browser_back_cooldown_s": (0.10, 3.0),
    "double_click_commit_delay_s": (0.05, 1.0),
    "scroll_deadzone_px": (5.0, 150.0),
    "scroll_max_speed": (1.0, 80.0),
    "scroll_full_speed_px": (40.0, 800.0),
    "scroll_filter_min_cutoff": (0.5, 12.0),
    "pinch_threshold": (0.20, 0.50),
    "right_click_tap_max_s": (0.10, 1.0),
    "drag_hold_s": (0.25, 1.25),
}
_INT_RANGES: dict[str, tuple[int, int]] = {
    "screen_edge_inset_px": (0, 20),
    "scroll_wheel_step": (10, 120),
    "camera_index": (0, 16),
    "camera_width": (320, 1920),
    "camera_height": (240, 1080),
    "camera_fps": (10, 60),
    "model_complexity": (0, 1),
    "max_hands": (1, 2),
    "click_confirm_frames": (1, 8),
    "right_click_confirm_frames": (1, 8),
    "double_click_confirm_frames": (1, 8),
    "browser_back_confirm_frames": (1, 8),
    "gesture_history": (1, 9),
}
_BOOL_FIELDS = {
    "mirror_preview",
    "three_finger_double_click_enabled",
    "scroll_invert",
    "hud_enabled",
    "show_landmarks",
    "show_help_on_start",
    "safety_guard_enabled",
    "preview_always_on_top",
    "onboarding_complete",
    "left_click_enabled",
    "right_click_enabled",
    "scroll_enabled",
    "browser_back_enabled",
}


def sanitize_config(config: AppConfig) -> AppConfig:
    """Clamp externally sourced settings and replace values of the wrong type."""
    defaults = AppConfig()
    for name, (lo, hi) in _FLOAT_RANGES.items():
        try:
            value = float(getattr(config, name))
            if not (value == value and abs(value) != float("inf")):
                raise ValueError("not finite")
            setattr(config, name, min(hi, max(lo, value)))
        except (TypeError, ValueError, OverflowError):
            setattr(config, name, getattr(defaults, name))
    for name, (lo, hi) in _INT_RANGES.items():
        try:
            raw_value = getattr(config, name)
            if isinstance(raw_value, bool):
                raise TypeError("boolean is not a valid integer setting")
            value = int(raw_value)
            setattr(config, name, min(hi, max(lo, value)))
        except (TypeError, ValueError, OverflowError):
            setattr(config, name, getattr(defaults, name))
    for name in _BOOL_FIELDS:
        if not isinstance(getattr(config, name), bool):
            setattr(config, name, getattr(defaults, name))
    return config


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path is not None else default_config_path()
    if not config_path.exists():
        return AppConfig()
    try:
        raw: Any = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("settings root must be a JSON object")
        allowed = {field.name for field in fields(AppConfig)}
        clean = {k: v for k, v in raw.items() if k in allowed}
        return sanitize_config(AppConfig(**clean))
    except (OSError, ValueError, TypeError) as exc:  # ValueError covers JSON decode errors
        print(f"[NoMouse] Could not load settings ({exc}); using defaults.")
        return AppConfig()


def save_config(config: AppConfig, path: str | Path | None = None) -> None:
    """Write settings atomically so a crash mid-write cannot corrupt the file."""
    config_path = Path(path) if path is not None else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(sanitize_config(config)), indent=2) + "\n"
    temp_path = config_path.with_name(config_path.name + ".tmp")
    temp_path.write_text(payload, encoding="utf-8")
    os.replace(temp_path, config_path)
