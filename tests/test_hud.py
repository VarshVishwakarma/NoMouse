import numpy as np
import pytest

from nomouse.config import AppConfig
from nomouse.hud import HELP_LINES, HudState, _text_size, ascii_text, draw_hud
from nomouse.types import FrameMetrics, Gesture


def _blank(w=640, h=480):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _metrics(**kwargs):
    return FrameMetrics(fps=30.0, inference_ms=8.0, **kwargs)


@pytest.mark.parametrize("size", [(640, 480), (1280, 720), (320, 240)])
@pytest.mark.parametrize("enabled", [True, False])
def test_hud_draws_for_every_gesture_without_error(size, enabled):
    for gesture in Gesture:
        frame = _blank(*size)
        draw_hud(frame, gesture, _metrics(), enabled, AppConfig(), show_help=True, now=0.0)
        assert frame.any()


def test_hud_skips_frames_too_small_to_be_legible():
    frame = _blank(100, 80)
    draw_hud(frame, Gesture.POINT, _metrics(), True, AppConfig())
    assert not frame.any()


def test_safety_hold_and_scroll_states_render():
    frame = _blank()
    draw_hud(frame, Gesture.TWO_FINGERS, _metrics(safety_blocked=True), True, AppConfig(), now=0.0)
    assert frame[10:90, 10:320].any()


def test_toast_only_draws_while_notification_is_live():
    config = AppConfig()
    center_strip = (slice(480 - 90, 480 - 45), slice(150, 490))

    expired = _blank()
    draw_hud(expired, Gesture.POINT, _metrics(notification="LEFT CLICK", notification_until=1.0), True,
             config, now=5.0)
    assert not expired[center_strip].any()

    live = _blank()
    draw_hud(live, Gesture.POINT, _metrics(notification="LEFT CLICK", notification_until=6.0), True,
             config, now=5.0)
    assert live[center_strip].any()


def test_help_card_is_hidden_unless_requested():
    config = AppConfig()
    without, with_help = _blank(), _blank()
    draw_hud(without, Gesture.POINT, _metrics(), True, config, show_help=False, now=0.0)
    draw_hud(with_help, Gesture.POINT, _metrics(), True, config, show_help=True, now=0.0)
    assert with_help.sum() > without.sum()


def test_ascii_text_replaces_characters_opencv_cannot_draw():
    # OpenCV's built-in fonts render "?" for these, which showed up in drag notifications.
    assert ascii_text("DROP \u2014 RELEASED") == "DROP - RELEASED"
    assert ascii_text("TRACK LOST \u2014 DRAG RELEASED").isascii()
    assert ascii_text("caf\u00e9").isascii()


def test_help_card_auto_hides_and_can_be_toggled():
    state = HudState.at_startup(show_help=True, now=100.0, seconds=8.0)
    assert state.help_visible(105.0)
    assert not state.help_visible(108.5)
    state.toggle_help()
    assert state.help_visible(500.0)  # manual toggle never auto-hides
    state.toggle_help()
    assert not state.help_visible(500.0)


def test_help_not_shown_at_startup_when_disabled():
    state = HudState.at_startup(show_help=False, now=0.0)
    assert not state.help_visible(0.0)


def test_help_rows_fit_on_one_line_without_overlapping():
    # Card is 360 px wide at scale 1 with 18 px padding either side; keep a visible gap between columns.
    inner_width, min_gap = 360 - 2 * 18, 14
    for gesture, action in HELP_LINES:
        used = _text_size(gesture, 0.40, 1)[0] + _text_size(action, 0.40, 1)[0]
        assert used + min_gap <= inner_width, f"{gesture!r} / {action!r} would collide ({used}px of {inner_width}px)"
