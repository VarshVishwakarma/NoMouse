import pytest

from nomouse.config import AppConfig
from nomouse.controller import MouseController
from nomouse.types import Gesture
from tests.support import BlockGuard, FakeMouse, SafeGuard


def make_controller(**overrides):
    mouse = FakeMouse()
    values = dict(
        click_cooldown_s=0.10,
        right_click_cooldown_s=0.10,
        double_click_cooldown_s=0.10,
        browser_back_cooldown_s=0.10,
        right_click_tap_max_s=0.45,
        drag_hold_s=0.40,
        scroll_deadzone_px=20.0,
        double_click_commit_delay_s=0.14,
        three_finger_double_click_enabled=False,
    )
    values.update(overrides)
    return MouseController(AppConfig(**values), SafeGuard(), mouse_api=mouse), mouse


def update(controller, gesture, t, xy=(400.0, 300.0), raw_gesture=None):
    controller.update(gesture, xy, (1920, 1080), t, raw_gesture=raw_gesture)


def events(mouse, name):
    return [event for event in mouse.events if event[0] == name]


def test_short_pinch_and_release_produces_one_left_click():
    c, m = make_controller()
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.PINCH, 1.0)
    update(c, Gesture.PINCH, 1.08)
    update(c, Gesture.POINT, 1.15)
    assert events(m, "click") == [("click", "left")]
    assert not events(m, "down")


def test_two_quick_pinches_produce_two_left_clicks_for_normal_os_double_click():
    c, m = make_controller(click_cooldown_s=0.08)
    update(c, Gesture.POINT, 0.8)
    update(c, Gesture.PINCH, 1.0)
    update(c, Gesture.POINT, 1.12)
    update(c, Gesture.POINT, 1.18)
    update(c, Gesture.PINCH, 1.25)
    update(c, Gesture.POINT, 1.38)
    assert events(m, "click") == [("click", "left"), ("click", "left")]


def test_hold_pinch_starts_drag_and_release_drops_without_clicking():
    c, m = make_controller()
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.PINCH, 1.0)
    update(c, Gesture.PINCH, 1.2)
    assert not c.dragging
    update(c, Gesture.PINCH, 1.43, (410.0, 305.0))
    assert c.dragging
    update(c, Gesture.PINCH, 1.50, (450.0, 350.0))
    assert ("move", 450, 350) in m.events
    update(c, Gesture.POINT, 1.58, (470.0, 360.0))
    assert not c.dragging
    assert ("down", "left") in m.events
    assert ("up", "left") in m.events
    assert not events(m, "click")


def test_tracking_loss_cancels_short_pinch_without_click():
    c, m = make_controller()
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.PINCH, 1.0)
    c.handle_tracking_loss()
    update(c, Gesture.POINT, 1.2)
    assert not events(m, "click")


def test_short_two_finger_tap_right_clicks_if_no_vertical_motion():
    c, m = make_controller()
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.TWO_FINGERS, 1.0, (400, 300))
    update(c, Gesture.TWO_FINGERS, 1.1, (401, 301))
    update(c, Gesture.POINT, 1.2, (400, 300))
    assert events(m, "click") == [("click", "right")]
    assert not events(m, "scroll")


def test_two_finger_hand_held_below_start_scrolls_down_continuously_then_stops_on_return():
    c, m = make_controller()
    c.raw_wheel_units = True
    update(c, Gesture.POINT, 0.9, (400, 300))
    update(c, Gesture.TWO_FINGERS, 1.0, (400, 300))
    for i in range(1, 16):                      # hold 100 px below the start for 0.5 s
        update(c, Gesture.TWO_FINGERS, 1.0 + i / 30, (400, 400))
    held = events(m, "scroll")
    assert len(held) >= 3, "scrolling should be continuous while the hand stays offset"
    assert all(event[1] < 0 for event in held)  # negative wheel units = scroll down
    for i in range(1, 16):                      # return to the start and rest
        update(c, Gesture.TWO_FINGERS, 1.6 + i / 30, (400, 300))
    count_after_return = len(events(m, "scroll"))
    for i in range(1, 16):
        update(c, Gesture.TWO_FINGERS, 2.2 + i / 30, (400, 300))
    assert len(events(m, "scroll")) == count_after_return, "must stop at neutral"
    assert all(event[1] < 0 for event in events(m, "scroll")), "return must not scroll upward"
    update(c, Gesture.POINT, 3.0, (400, 300))
    assert not events(m, "click")


def test_scroll_sends_raw_wheel_units_on_windows_and_whole_notches_elsewhere():
    deltas = {}
    for raw in (True, False):
        c, m = make_controller()
        c.raw_wheel_units = raw
        update(c, Gesture.TWO_FINGERS, 1.0, (400, 300))
        for i in range(1, 31):
            update(c, Gesture.TWO_FINGERS, 1.0 + i / 30, (400, 420))
        deltas[raw] = [event[1] for event in events(m, "scroll")]
    # Windows: 1/3-notch steps (40 of 120). Elsewhere PyAutoGUI wants whole notches.
    assert all(d % 40 == 0 and abs(d) < 120 * 3 for d in deltas[True])
    assert all(isinstance(d, int) and d != 0 and abs(d) < 10 for d in deltas[False])
    assert abs(sum(deltas[True])) / 120 == pytest.approx(abs(sum(deltas[False])), abs=1.01)


def test_small_two_finger_movement_cancels_right_click_even_without_scroll_trigger():
    c, m = make_controller()
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.TWO_FINGERS, 1.0, (400, 300))
    update(c, Gesture.TWO_FINGERS, 1.1, (400, 325))
    update(c, Gesture.POINT, 1.2, (400, 300))
    assert not events(m, "click")
    assert not events(m, "scroll")


def test_long_stationary_two_finger_hold_does_not_toggle_a_hidden_mode():
    c, m = make_controller()
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.TWO_FINGERS, 1.0, (400, 300))
    update(c, Gesture.TWO_FINGERS, 1.4, (400, 300))
    update(c, Gesture.TWO_FINGERS, 1.8, (400, 300))
    update(c, Gesture.POINT, 2.0, (400, 300))
    assert not c.scroll_mode
    assert not events(m, "click")
    assert not events(m, "scroll")


def test_three_finger_double_click_is_disabled_by_default_in_simple_mode():
    c, m = make_controller()
    update(c, Gesture.THREE_FINGERS, 1.0, raw_gesture=Gesture.THREE_FINGERS)
    update(c, Gesture.THREE_FINGERS, 1.2, raw_gesture=Gesture.THREE_FINGERS)
    update(c, Gesture.THREE_FINGERS, 1.4, raw_gesture=Gesture.THREE_FINGERS)
    assert not events(m, "double")


def test_optional_three_finger_double_click_can_be_enabled_for_advanced_users():
    c, m = make_controller(three_finger_double_click_enabled=True)
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.THREE_FINGERS, 1.0, raw_gesture=Gesture.THREE_FINGERS)
    update(c, Gesture.THREE_FINGERS, 1.2, raw_gesture=Gesture.THREE_FINGERS)
    assert len(events(m, "double")) == 1


def test_four_finger_navigation_fires_once_until_neutral_release():
    c, m = make_controller()
    update(c, Gesture.POINT, 0.8)
    update(c, Gesture.FOUR_FINGERS, 1.0, raw_gesture=Gesture.FOUR_FINGERS)
    update(c, Gesture.FOUR_FINGERS, 1.1, raw_gesture=Gesture.FOUR_FINGERS)
    assert events(m, "hotkey") == [("hotkey", "alt", "left")]
    update(c, Gesture.POINT, 1.2)
    update(c, Gesture.POINT, 1.3)
    update(c, Gesture.POINT, 1.4)
    update(c, Gesture.FOUR_FINGERS, 1.5, raw_gesture=Gesture.FOUR_FINGERS)
    assert len(events(m, "hotkey")) == 2


def test_three_to_four_transition_does_not_double_click_before_browser_back():
    c, m = make_controller(three_finger_double_click_enabled=True)
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.THREE_FINGERS, 1.0, raw_gesture=Gesture.THREE_FINGERS)
    update(c, Gesture.FOUR_FINGERS, 1.05, raw_gesture=Gesture.FOUR_FINGERS)
    assert not events(m, "double")
    assert events(m, "hotkey") == [("hotkey", "alt", "left")]


def test_safety_guard_blocks_clicks_and_scrolls():
    mouse = FakeMouse()
    c = MouseController(AppConfig(click_cooldown_s=0.1, drag_hold_s=0.4), BlockGuard(), mouse_api=mouse)
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.PINCH, 1.0)
    update(c, Gesture.POINT, 1.1)
    assert not events(mouse, "click")


def test_tracking_loss_during_drag_releases_held_mouse_button():
    c, m = make_controller()
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.PINCH, 1.0)
    update(c, Gesture.PINCH, 1.43)
    assert c.dragging
    c.handle_tracking_loss()
    assert not c.dragging
    assert ("up", "left") in m.events


def test_repeated_identical_cursor_coordinates_do_not_spam_mouse_events():
    c, m = make_controller()
    update(c, Gesture.POINT, 1.0, xy=(410, 300))
    update(c, Gesture.POINT, 1.03, xy=(410, 300))
    update(c, Gesture.POINT, 1.06, xy=(410, 300))
    assert events(m, 'move') == [('move', 410, 300)]


def test_scroll_uses_independent_scroll_coordinate_not_slow_cursor_coordinate():
    c, m = make_controller()
    c.update(Gesture.POINT, (400.0, 300.0), (1920, 1080), 0.9)
    c.update(Gesture.TWO_FINGERS, (400.0, 300.0), (1920, 1080), 1.0, scroll_y=300.0)
    # Cursor coordinate remains fixed, but the independent scrolling coordinate moves.
    for i in range(1, 11):
        c.update(Gesture.TWO_FINGERS, (400.0, 300.0), (1920, 1080), 1.0 + i / 30, scroll_y=420.0)
    assert events(m, 'scroll')
    assert all(event[1] < 0 for event in events(m, 'scroll'))


def test_pausing_during_drag_releases_left_button():
    c, m = make_controller()
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.PINCH, 1.0)
    update(c, Gesture.PINCH, 1.43)
    assert c.dragging
    c.toggle_enabled()
    assert not c.enabled
    assert not c.dragging
    assert ('up', 'left') in m.events


def test_mouse_down_exception_attempts_release_and_locks_out_further_input():
    class UncertainMouse(FakeMouse):
        def mouseDown(self, button="left"):
            self.events.append(("down", button))
            raise OSError("input call failed after reaching the OS")

    mouse = UncertainMouse()
    c = MouseController(AppConfig(drag_hold_s=0.25), SafeGuard(), mouse_api=mouse)
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.PINCH, 1.0)
    update(c, Gesture.PINCH, 1.3)
    assert ("down", "left") in mouse.events
    assert ("up", "left") in mouse.events
    assert not c.held_buttons
    assert not c.dragging
    assert not c.enabled
    assert c.fatal_input_error is not None
    before = len(mouse.events)
    c.toggle_enabled()
    update(c, Gesture.POINT, 1.5)
    assert not c.enabled
    assert len(mouse.events) == before


def test_failed_mouse_release_keeps_explicit_uncertain_button_state():
    class UncertainReleaseMouse(FakeMouse):
        def mouseUp(self, button="left"):
            raise OSError("mouse release rejected")

    mouse = UncertainReleaseMouse()
    c = MouseController(AppConfig(drag_hold_s=0.25), SafeGuard(), mouse_api=mouse)
    update(c, Gesture.POINT, 0.9)
    update(c, Gesture.PINCH, 1.0)
    update(c, Gesture.PINCH, 1.3)
    assert c.dragging and c.held_buttons == {"left"}

    c.handle_tracking_loss()
    assert c.dragging and c.held_buttons == {"left"}
    assert not c.enabled
    assert "mouseUp failed" in c.fatal_input_error
    c.toggle_enabled()
    assert not c.enabled


def test_input_api_failure_disables_controller_instead_of_reporting_success():
    class FailingMoveMouse(FakeMouse):
        def moveTo(self, x, y, duration=0):
            raise OSError("desktop input unavailable")

    mouse = FailingMoveMouse()
    c = MouseController(AppConfig(), SafeGuard(), mouse_api=mouse)
    c.move(500, 300)
    assert not c.enabled
    assert "moveTo failed" in c.fatal_input_error
    assert "INPUT ERROR" in c.notification


def test_optional_interactions_can_be_disabled_without_affecting_other_actions():
    c, mouse = make_controller(right_click_enabled=False, scroll_enabled=False, browser_back_enabled=False)
    update(c, Gesture.TWO_FINGERS, 1.0, (400, 300))
    update(c, Gesture.TWO_FINGERS, 1.1, (400, 450))
    update(c, Gesture.POINT, 1.2, (400, 300))
    update(c, Gesture.FOUR_FINGERS, 1.4, raw_gesture=Gesture.FOUR_FINGERS)
    assert not events(mouse, "click")
    assert not events(mouse, "scroll")
    assert not events(mouse, "hotkey")
