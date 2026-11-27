"""Simple, stateful gesture-to-mouse controller with safe recovery behavior."""
from __future__ import annotations

import math
import sys
import time

from .config import AppConfig
from .safety import WindowSafetyGuard
from .scrolling import WHEEL_DELTA, RateScroller
from .types import Gesture


class MouseController:
    def __init__(self, config: AppConfig, safety: WindowSafetyGuard, mouse_api=None):
        self.config = config
        self.safety = safety
        if mouse_api is None:
            import pyautogui as mouse_api
        self.mouse_api = mouse_api
        self.fail_safe_exception = getattr(mouse_api, "FailSafeException", RuntimeError)
        self.enabled = True
        # This now means a two-finger gesture is currently active, not a toggle mode.
        self.scroll_mode = False
        self.dragging = False
        self.held_buttons: set[str] = set()
        self.fatal_input_error: str | None = None
        self._last_move_xy: tuple[int, int] | None = None
        self.pinch_started_at: float | None = None
        self.pinch_drag_started = False
        self.two_fingers_started_at: float | None = None
        self.two_finger_start_y: float | None = None
        self.two_finger_moved = False
        self.two_finger_did_scroll = False
        self.scroller = RateScroller(
            deadzone_px=config.scroll_deadzone_px,
            full_speed_px=config.scroll_full_speed_px,
            max_speed=config.scroll_max_speed,
            wheel_step=config.scroll_wheel_step,
            invert=config.scroll_invert,
        )
        # PyAutoGUI passes ``scroll()`` straight through as the raw wheel delta on
        # Windows (120 = one notch), but treats it as whole notches elsewhere.
        self.raw_wheel_units = sys.platform == "win32"
        self._wheel_carry = 0
        self.last_gesture = Gesture.UNKNOWN
        self.last_click_at = float("-inf")
        self.last_right_click_at = float("-inf")
        self.last_double_click_at = float("-inf")
        self.last_browser_back_at = float("-inf")
        self.pending_double_click_since: float | None = None
        self.transition_guard = False
        self.action_lock = False
        self.neutral_frames = 0
        self.notification = "Ready"
        self.notification_until = time.monotonic() + 2.0
        self.mouse_api.FAILSAFE = True
        self.mouse_api.PAUSE = 0.0

    def notify(self, message: str, duration: float = 1.5) -> None:
        self.notification = message
        self.notification_until = time.monotonic() + duration

    def toggle_enabled(self) -> None:
        if self.fatal_input_error is not None:
            self.notify("INPUT ERROR: RESTART REQUIRED", 3.0)
            return
        self.enabled = not self.enabled
        # When re-enabled, resynchronize with the real system pointer; it may have
        # been moved manually while NoMouse was paused.
        self._last_move_xy = None
        if not self.enabled:
            self.release_all()
            self._reset_two_finger()
            self.notify("CONTROL PAUSED")
        else:
            self.notify("CONTROL RESUMED")

    def _safe_action(self) -> bool:
        try:
            x, y = self.mouse_api.position()
            allowed = self.safety.allows_action(int(x), int(y))
            if not allowed:
                self.notify("SAFETY BLOCK: PREVIEW WINDOW", 1.0)
            return allowed
        except Exception:
            self.notify("SAFETY CHECK UNAVAILABLE", 1.0)
            return False

    def _execute(self, method_name: str, *args, **kwargs) -> bool:
        """Execute input and fail closed when the operating-system API fails."""
        try:
            getattr(self.mouse_api, method_name)(*args, **kwargs)
            return True
        except self.fail_safe_exception:
            self._disable_after_input_error("FAIL-SAFE ACTIVATED")
            return False
        except Exception as exc:
            self._disable_after_input_error(f"{method_name} failed: {type(exc).__name__}")
            return False

    def _disable_after_input_error(self, reason: str) -> None:
        self.enabled = False
        self.fatal_input_error = reason
        self.notify(f"INPUT ERROR: {reason}", 3.0)
        if self.held_buttons:
            self.release_all()

    def move(self, x: int, y: int) -> None:
        """Send only meaningful pointer updates; skip duplicate sub-pixel outputs."""
        if not self.enabled:
            return
        point = (round(x), round(y))
        previous = self._last_move_xy
        deadband = float(getattr(self.config, "cursor_move_deadband_px", 0.7))
        if previous is not None and math.hypot(point[0] - previous[0], point[1] - previous[1]) < deadband:
            return
        if self._execute("moveTo", point[0], point[1], duration=0):
            self._last_move_xy = point

    def _emit_click(self, button: str, now: float) -> bool:
        if not self._safe_action():
            return False
        if self._execute("click", button=button):
            if button == "left":
                self.last_click_at = now
                self.notify("LEFT CLICK")
            else:
                self.last_right_click_at = now
                self.notify("RIGHT CLICK")
            return True
        return False

    def _reset_two_finger(self) -> None:
        self.two_fingers_started_at = None
        self.two_finger_start_y = None
        self.two_finger_moved = False
        self.two_finger_did_scroll = False
        self.scroll_mode = False
        self.scroller.reset()
        self._wheel_carry = 0

    def _send_wheel(self, delta: int) -> bool:
        """Send a wheel delta in 1/120-notch units, adapting to the platform."""
        if self.raw_wheel_units:
            return self._execute("scroll", delta)
        self._wheel_carry += delta
        notches = int(self._wheel_carry / WHEEL_DELTA)  # truncates toward zero
        if notches == 0:
            return True
        self._wheel_carry -= notches * WHEEL_DELTA
        return self._execute("scroll", notches)

    def _handle_two_finger_scroll(self, y: float, now: float) -> None:
        if self.two_finger_start_y is not None and abs(y - self.two_finger_start_y) >= self.config.scroll_deadzone_px:
            self.two_finger_moved = True
        wheel_delta = self.scroller.update(y, now)
        if wheel_delta == 0:
            return
        self.two_finger_did_scroll = True
        self.two_finger_moved = True
        if self._safe_action() and self._send_wheel(wheel_delta):
            self.notify("SCROLL DOWN" if wheel_delta < 0 else "SCROLL UP", 0.5)

    def update(
        self,
        gesture: Gesture,
        index_xy: tuple[float, float] | None,
        screen_size: tuple[int, int],
        now: float,
        raw_gesture: Gesture | None = None,
        scroll_y: float | None = None,
    ) -> None:
        previous = self.last_gesture
        raw_gesture = gesture if raw_gesture is None else raw_gesture
        was_dragging = self.dragging

        if gesture in (Gesture.POINT, Gesture.OPEN_PALM, Gesture.FIST):
            self.neutral_frames += 1
            if self.neutral_frames >= 3:
                self.action_lock = False
        else:
            self.neutral_frames = 0

        if not self.enabled:
            self.last_gesture = gesture
            return

        # Suppress a transient three-finger double-click when the raw classifier
        # already sees four fingers. The simpler primary double-click is two quick
        # pinch taps, which the OS recognizes as a normal double-click.
        if self.pending_double_click_since is not None:
            if raw_gesture == Gesture.FOUR_FINGERS or gesture != Gesture.THREE_FINGERS:
                self.pending_double_click_since = None
                self.transition_guard = False

        # A held pinch becomes a drag. Releasing the pinch drops it; a short pinch
        # followed by release produces a left click. There is no PINCH -> FIST dance.
        just_dropped = False
        if self.dragging and gesture != Gesture.PINCH:
            self.release_all()
            self.notify("DROP — RELEASED")
            just_dropped = True

        if gesture == Gesture.PINCH:
            if previous != Gesture.PINCH:
                self.pinch_started_at = now
                self.pinch_drag_started = False
            if (
                self.config.left_click_enabled
                and not self.dragging
                and not self.action_lock
                and self.pinch_started_at is not None
                and now - self.pinch_started_at >= self.config.drag_hold_s
            ):
                if self._safe_action():
                    # A native input function can raise after changing OS state.
                    # Track the uncertain state before crossing that boundary.
                    self.held_buttons.add("left")
                    self.dragging = True
                    if self._execute("mouseDown", button="left"):
                        self.pinch_drag_started = True
                        self.notify("DRAGGING — RELEASE PINCH TO DROP")
            if self.dragging and index_xy is not None:
                self.move(round(index_xy[0]), round(index_xy[1]))
        elif previous == Gesture.PINCH:
            if (not was_dragging and not just_dropped and not self.pinch_drag_started and
                    self.pinch_started_at is not None and gesture != Gesture.UNKNOWN):
                held = now - self.pinch_started_at
                if (
                    held < self.config.drag_hold_s
                    and self.config.left_click_enabled
                    and not self.action_lock
                    and now - self.last_click_at >= self.config.click_cooldown_s
                ):
                    self._emit_click("left", now)
            self.pinch_started_at = None
            self.pinch_drag_started = False

        # Pointing moves the pointer. While pinch-dragging, the app supplies a palm
        # anchor so movement remains stable even though the fingertips touch.
        # The confirmed gesture lags the real hand by a frame or two, so also require
        # that *this* frame still looks like pointing; otherwise the cursor follows
        # the curling fingertip just before a click or fist and lands off-target.
        if gesture == Gesture.POINT and raw_gesture == Gesture.POINT and index_xy is not None:
            self.move(round(index_xy[0]), round(index_xy[1]))

        # Two fingers use a simple trackpad interaction: a mostly-stationary tap
        # right-clicks; vertical movement scrolls. Scroll uses its own lightly filtered
        # coordinate, separate from cursor smoothing, so a slow cursor profile cannot
        # add unnecessary delay to wheel control.
        scroll_position_y = scroll_y if scroll_y is not None else (index_xy[1] if index_xy is not None else None)
        if gesture == Gesture.TWO_FINGERS:
            self.scroll_mode = True
            if previous != Gesture.TWO_FINGERS:
                self.two_fingers_started_at = now
                self.two_finger_start_y = scroll_position_y
                self.two_finger_moved = False
                self.two_finger_did_scroll = False
                self.scroller.reset(scroll_position_y, now)
            # The confirmed gesture can lag the raw frame by one confirmation
            # frame. Do not fall back to the pointer coordinate and interpret a
            # transition pose as scroll movement; only a frame currently classified
            # as TWO_FINGERS may move the scroll engine.
            if self.config.scroll_enabled and raw_gesture == Gesture.TWO_FINGERS and scroll_position_y is not None:
                self._handle_two_finger_scroll(scroll_position_y, now)
        else:
            self.scroll_mode = False
            if previous == Gesture.TWO_FINGERS:
                started = self.two_fingers_started_at
                held = now - started if started is not None else float("inf")
                suppress_click = gesture in (
                    Gesture.THREE_FINGERS, Gesture.FOUR_FINGERS, Gesture.OPEN_PALM, Gesture.UNKNOWN,
                )
                if (self.config.right_click_enabled and not self.two_finger_did_scroll and not self.two_finger_moved and
                        not suppress_click and held <= getattr(self.config, "right_click_tap_max_s", 0.45) and
                        not self.action_lock and now - self.last_right_click_at >= self.config.right_click_cooldown_s):
                    self._emit_click("right", now)
                self._reset_two_finger()

        # Optional legacy three-finger double-click is off by default. Two quick
        # pinch taps are easier to learn and work with normal OS double-click timing.
        if getattr(self.config, "three_finger_double_click_enabled", False):
            if gesture == Gesture.THREE_FINGERS and previous != Gesture.THREE_FINGERS:
                if raw_gesture == Gesture.THREE_FINGERS and not self.action_lock:
                    self.pending_double_click_since = now
                    self.transition_guard = True
            if gesture == Gesture.THREE_FINGERS and self.pending_double_click_since is not None:
                if raw_gesture == Gesture.THREE_FINGERS and not self.action_lock:
                    elapsed = now - self.pending_double_click_since
                    if (elapsed >= self.config.double_click_commit_delay_s and
                            now - self.last_double_click_at >= self.config.double_click_cooldown_s and
                            self._safe_action()):
                        if self._execute("doubleClick", interval=0.08):
                            self.last_double_click_at = now
                            self.action_lock = True
                            self.pending_double_click_since = None
                            self.transition_guard = False
                            self.notify("DOUBLE CLICK")

        # Four fingers with the thumb tucked remains an optional advanced shortcut.
        if gesture == Gesture.FOUR_FINGERS and previous != Gesture.FOUR_FINGERS:
            self.pending_double_click_since = None
            self.transition_guard = False
            cooled_down = now - self.last_browser_back_at >= self.config.browser_back_cooldown_s
            if self.config.browser_back_enabled and not self.action_lock and cooled_down and self._safe_action():
                if self._execute("hotkey", "alt", "left"):
                    self.last_browser_back_at = now
                    self.action_lock = True
                    self.notify("BROWSER BACK")

        # Open palm is a pause pose: no pointer movement, and a drag always drops.
        # Fist is simply idle unless a previous drag was active (now released above).
        self.last_gesture = gesture

    def handle_tracking_loss(self) -> None:
        """Cancel pending gestures and release any held mouse button safely."""
        was_dragging = self.dragging
        if was_dragging:
            self.release_all()
            self.notify("TRACK LOST — DRAG RELEASED")
        else:
            self.pinch_started_at = None
            self.pinch_drag_started = False
        self._reset_two_finger()
        self.pending_double_click_since = None
        self.transition_guard = False
        self.neutral_frames = 0
        self.action_lock = False
        self.last_gesture = Gesture.UNKNOWN

    def release_all(self) -> None:
        if "left" in self.held_buttons:
            try:
                self.mouse_api.mouseUp(button="left")
            except Exception as exc:
                self.enabled = False
                self.fatal_input_error = f"mouseUp failed: {type(exc).__name__}"
                self.notify(f"INPUT ERROR: {self.fatal_input_error}", 5.0)
                self.dragging = True
            else:
                self.held_buttons.discard("left")
                self.dragging = False
        else:
            self.dragging = False
        self.pinch_started_at = None
        self.pinch_drag_started = False
