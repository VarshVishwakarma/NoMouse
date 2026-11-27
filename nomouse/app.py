"""Application wiring: camera -> hand tracker -> gesture pipeline -> mouse controller -> preview.

The per-frame decision logic lives in :class:`GesturePipeline`, which has no camera,
window, or OS-input dependencies of its own. That keeps the control loop testable
with synthetic hand observations and a fake mouse.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2

from . import __version__
from .config import AppConfig, default_config_path, load_config, save_config
from .controller import MouseController
from .errors import StartupError
from .filters import AxisSmoother, OneEuroFilter
from .geometry import to_screen_float
from .gestures import GestureConsensus, classify_hand
from .hud import WINDOW_NAME, HudState, draw_hud
from .safety import WindowSafetyGuard
from .types import FrameMetrics, Gesture, HandObservation
from .window_manager import PreviewWindowManager

PALM_LANDMARKS = (0, 5, 9, 13, 17)
SCROLL_REFERENCE_HEIGHT = 1080.0  # scroll distances are measured as if the screen were this tall
MAX_FRAME_FAILURES = 120
SMOOTHING_STEP = 0.03
KEY_ESC = 27


def build_cursor_smoother(config: object) -> AxisSmoother:
    """Map the user-facing slider to a responsive adaptive filter.

    A larger ``cursor_smoothing`` value prioritizes steadiness at rest. Fast motion
    still raises the cutoff through the One Euro derivative term. This is a tuning
    policy, not a performance guarantee.
    """
    amount = min(1.0, max(0.0, float(config.cursor_smoothing)))  # type: ignore[attr-defined]
    min_cutoff = 2.0 + (1.0 - amount) * 3.0  # 5 Hz responsive -> 2 Hz steadier
    return AxisSmoother(min_cutoff=min_cutoff, beta=0.008)


@dataclass
class FrameOutcome:
    """What the pipeline decided for one frame (useful for the HUD and for tests)."""

    raw_gesture: Gesture = Gesture.UNKNOWN
    gesture: Gesture = Gesture.UNKNOWN
    cursor_xy: tuple[float, float] | None = None
    scroll_y: float | None = None
    dispatched: bool = False


class GesturePipeline:
    """Turn hand observations into confirmed gestures and controller updates."""

    def __init__(self, config: AppConfig, controller: MouseController, screen_size: tuple[int, int]):
        self.config = config
        self.controller = controller
        self.screen_size = screen_size
        self.consensus = GestureConsensus(
            config.gesture_history,
            config.click_confirm_frames,
            required_by_gesture={
                Gesture.PINCH: config.click_confirm_frames,
                Gesture.TWO_FINGERS: config.right_click_confirm_frames,
                Gesture.THREE_FINGERS: config.double_click_confirm_frames,
                Gesture.FOUR_FINGERS: config.browser_back_confirm_frames,
            },
        )
        self.smoother = build_cursor_smoother(config)
        self.scroll_smoother = OneEuroFilter(min_cutoff=config.scroll_filter_min_cutoff, beta=0.006)
        self.current_gesture = Gesture.UNKNOWN

    def rebuild_smoother(self) -> None:
        self.smoother = build_cursor_smoother(self.config)

    def reset(self) -> None:
        """Cancel pending gestures, release any drag, and clear all filter history."""
        self.controller.handle_tracking_loss()
        self.consensus.reset()
        self.smoother.reset()
        self.scroll_smoother.reset()
        self.current_gesture = Gesture.UNKNOWN

    def _cursor_anchor(self, hand: HandObservation, raw_gesture: Gesture) -> tuple[float, float, float]:
        anchor = hand.landmarks[8]
        # Follow the palm during a pinch-drag; the fingertip itself moves as the
        # fingers close and would make the dragged cursor jump.
        if self.controller.dragging and raw_gesture in (Gesture.FIST, Gesture.PINCH):
            anchor = tuple(  # type: ignore[assignment]
                sum(hand.landmarks[i][axis] for i in PALM_LANDMARKS) / len(PALM_LANDMARKS)
                for axis in range(3)
            )
        return anchor

    @staticmethod
    def _scroll_anchor_y(hand: HandObservation) -> float:
        """Track the palm center, not a moving fingertip, for scroll intent."""
        return sum(hand.landmarks[index][1] for index in PALM_LANDMARKS) / len(PALM_LANDMARKS)

    def step(
        self,
        observations: Sequence[HandObservation],
        now_perf: float,
        now_mono: float | None = None,
    ) -> FrameOutcome:
        config = self.config
        screen_w, screen_h = self.screen_size
        outcome = FrameOutcome()
        raw_scroll_y: float | None = None

        if observations:
            hand = observations[0]
            outcome.raw_gesture = classify_hand(hand, config.pinch_threshold)
            anchor = self._cursor_anchor(hand, outcome.raw_gesture)
            raw_sx, raw_sy = to_screen_float(
                anchor[0], anchor[1], screen_w, screen_h,
                config.active_margin, config.screen_edge_inset_px,
            )
            outcome.cursor_xy = self.smoother.apply(raw_sx, raw_sy, now_perf)
            _, palm_screen_y = to_screen_float(
                anchor[0],
                self._scroll_anchor_y(hand),
                screen_w,
                screen_h,
                config.active_margin,
                config.screen_edge_inset_px,
            )
            raw_scroll_y = palm_screen_y * (SCROLL_REFERENCE_HEIGHT / max(1, screen_h))

        # Feed UNKNOWN through the consensus so one transient missed/ambiguous frame
        # gets a short grace period instead of immediately wiping filter history.
        previous = self.current_gesture
        self.current_gesture = self.consensus.update(outcome.raw_gesture if observations else Gesture.UNKNOWN)
        current = self.current_gesture
        outcome.gesture = current

        scroll_y: float | None = None
        # Do not feed a frame into the scroll filter merely because temporal
        # consensus still holds TWO_FINGERS. During a transition, the confirmed
        # pose may lag the current frame (e.g. the raw classifier already sees
        # POINT). Treating that new pose's fingertip coordinate as scroll input
        # can create a sudden false scroll in the transition direction.
        if (
            current == Gesture.TWO_FINGERS
            and outcome.raw_gesture == Gesture.TWO_FINGERS
            and raw_scroll_y is not None
        ):
            if previous != Gesture.TWO_FINGERS:
                # Begin each scroll gesture with a fresh baseline; pointer filter
                # history must not bias the neutral point.
                self.scroll_smoother.reset()
            scroll_y = self.scroll_smoother(raw_scroll_y, now_perf)
        elif current != Gesture.TWO_FINGERS and previous == Gesture.TWO_FINGERS:
            self.scroll_smoother.reset()

        outcome.scroll_y = scroll_y
        # Never execute mouse actions from a low-confidence/ambiguous frame. The
        # consensus preserves the previous pose for one frame, but dispatch waits
        # until the classifier returns a usable observation again.
        if observations and outcome.raw_gesture != Gesture.UNKNOWN and current != Gesture.UNKNOWN:
            self.controller.update(
                current,
                outcome.cursor_xy,
                self.screen_size,
                time.monotonic() if now_mono is None else now_mono,
                raw_gesture=outcome.raw_gesture,
                scroll_y=scroll_y,
            )
            outcome.dispatched = True
        elif current == Gesture.UNKNOWN and previous != Gesture.UNKNOWN:
            self.controller.handle_tracking_loss()
            self.smoother.reset()
            self.scroll_smoother.reset()
        return outcome


@dataclass
class Session:
    """Mutable UI/session state shared by the loop and the key handler."""

    config: AppConfig
    pipeline: GesturePipeline
    controller: MouseController
    hud: HudState
    settings_dirty: bool = False
    window_manager: PreviewWindowManager | None = None


def handle_key(key: int, session: Session) -> bool:
    """Apply a keyboard command. Returns ``True`` when the user asked to quit."""
    if key in (ord("q"), KEY_ESC):
        return True
    config, controller = session.config, session.controller
    if key == ord("p"):
        controller.toggle_enabled()
    elif key in (ord("+"), ord("=")):
        config.cursor_smoothing = min(1.0, config.cursor_smoothing + SMOOTHING_STEP)
        session.pipeline.rebuild_smoother()
        session.settings_dirty = True
        controller.notify(f"SMOOTHING {config.cursor_smoothing:.2f}")
    elif key in (ord("-"), ord("_")):
        config.cursor_smoothing = max(0.0, config.cursor_smoothing - SMOOTHING_STEP)
        session.pipeline.rebuild_smoother()
        session.settings_dirty = True
        controller.notify(f"SMOOTHING {config.cursor_smoothing:.2f}")
    elif key == ord("l"):
        config.show_landmarks = not config.show_landmarks
        session.settings_dirty = True
        controller.notify("LANDMARKS ON" if config.show_landmarks else "LANDMARKS OFF")
    elif key == ord("h"):
        session.hud.toggle_help()
    elif key in (ord("o"), ord("O")):
        config.preview_always_on_top = not config.preview_always_on_top
        if session.window_manager is not None:
            session.window_manager.set_always_on_top(config.preview_always_on_top)
        session.settings_dirty = True
        controller.notify("PREVIEW ALWAYS ON TOP" if config.preview_always_on_top else "PREVIEW NORMAL Z-ORDER")
    return False


def _open_camera(config: AppConfig):
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(config.camera_index, backend)
    if not cap.isOpened():
        cap.release()
        raise StartupError(
            "Could not open the webcam. Check Windows camera permissions, close other "
            "camera apps, or change camera_index in config/settings.json (or use --camera)."
        )
    # A small capture buffer avoids processing stale frames when inference is slower
    # than the webcam. Drivers may ignore one or more requested properties.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.camera_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.camera_height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if sys.platform == "win32":
        try:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        except Exception:
            pass
    return cap


def _window_closed() -> bool:
    """True if the user closed the preview window with its close button."""
    try:
        return cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nomouse",
        description="Touchless mouse control with your webcam. Everything runs locally.",
    )
    parser.add_argument("--version", action="version", version=f"NoMouse {__version__}")
    parser.add_argument("--config", type=Path, default=None, metavar="PATH",
                        help=f"settings file to use (default: {default_config_path()})")
    parser.add_argument("--camera", type=int, default=None, metavar="N",
                        help="camera index to use; overrides camera_index in the settings file")
    parser.add_argument("--no-save", action="store_true",
                        help="do not write smoothing/landmark changes made with hotkeys back to the settings file")
    return parser


def _print_banner(config: AppConfig, cap) -> None:
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or config.camera_width)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or config.camera_height)
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    print(f"\nNoMouse {__version__}")
    print(f"  Camera     {width}x{height} (driver reports {fps:.0f} fps)")
    print("  Model      MediaPipe Tasks HandLandmarker (bundled local model)")
    print(f"  Smoothing  {config.cursor_smoothing:.2f}   (+ steadier, - faster)")
    print("  Press H in the preview window for the gesture guide, Q to quit.")
    print("  Fail-safe: move the physical mouse into a screen corner to pause control.\n")


def run(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    config_path = args.config if args.config is not None else default_config_path()
    config = load_config(config_path)
    if args.camera is not None:
        config.camera_index = max(0, args.camera)

    cap = None
    tracker = None
    controller = None
    window_ready = False
    session: Session | None = None

    try:
        import pyautogui  # Imported lazily: it needs a desktop session.

        from .tracker import HandTracker

        cap = _open_camera(config)
        tracker = HandTracker(
            config.max_hands,
            config.min_detection_confidence,
            config.min_tracking_confidence,
            config.model_complexity,
        )
        safety = WindowSafetyGuard(WINDOW_NAME, config.safety_guard_enabled)
        controller = MouseController(config, safety)
        screen_w, screen_h = pyautogui.size()
        pipeline = GesturePipeline(config, controller, (screen_w, screen_h))
        window_manager = PreviewWindowManager(WINDOW_NAME, config.preview_always_on_top)
        session = Session(
            config=config,
            pipeline=pipeline,
            controller=controller,
            hud=HudState.at_startup(config.show_help_on_start, time.monotonic()),
            window_manager=window_manager,
        )
        metrics = FrameMetrics()

        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or config.camera_width)
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or config.camera_height)
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        window_h = 600
        cv2.resizeWindow(WINDOW_NAME, int(window_h * actual_width / max(1, actual_height)), window_h)
        # Set topmost immediately, then retry after the first imshow creates the native HWND.
        window_manager.set_always_on_top(config.preview_always_on_top)
        window_ready = True
        _print_banner(config, cap)

        previous_frame_at: float | None = None
        fps_estimate = 0.0
        frame_failures = 0
        last_failure_notice = 0
        last_window_maintenance = 0.0

        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                frame_failures += 1
                # Most important recovery invariant: a failed camera read cannot leave
                # a drag held. Do this on the first failed frame, not after a timeout.
                if frame_failures == 1:
                    pipeline.reset()
                    print("Warning: webcam frame unavailable; pending gestures cancelled and drag released.")
                if frame_failures - last_failure_notice >= 15:
                    print(f"Warning: waiting for webcam frame ({frame_failures}/{MAX_FRAME_FAILURES}).")
                    last_failure_notice = frame_failures
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                if frame_failures >= MAX_FRAME_FAILURES:
                    print("Error: webcam did not recover; shutting down safely.", file=sys.stderr)
                    break
                time.sleep(0.01)
                continue

            frame_failures = 0
            last_failure_notice = 0
            if config.mirror_preview:
                frame = cv2.flip(frame, 1)
            now_perf = time.perf_counter()
            dt = 1.0 / 30.0 if previous_frame_at is None else max(1e-4, now_perf - previous_frame_at)
            previous_frame_at = now_perf
            instant_fps = min(240.0, 1.0 / dt)
            fps_estimate = instant_fps if fps_estimate == 0 else (0.88 * fps_estimate + 0.12 * instant_fps)

            observations, result = tracker.process(frame)
            outcome = pipeline.step(observations, now_perf)

            if config.show_landmarks:
                tracker.draw_landmarks(frame, result)
            now_mono = time.monotonic()
            metrics.fps = fps_estimate
            metrics.inference_ms = tracker.last_inference_ms
            metrics.mode = "TWO-FINGER SCROLL" if outcome.gesture == Gesture.TWO_FINGERS else "MOUSE"
            metrics.cursor_x = int(outcome.cursor_xy[0]) if outcome.cursor_xy is not None else None
            metrics.cursor_y = int(outcome.cursor_xy[1]) if outcome.cursor_xy is not None else None
            metrics.notification = controller.notification
            metrics.notification_until = controller.notification_until
            metrics.safety_blocked = bool(safety.last_reason and "blocked" in safety.last_reason.lower())
            if config.hud_enabled:
                hud_gesture = Gesture.UNKNOWN if outcome.raw_gesture == Gesture.UNKNOWN else outcome.gesture
                draw_hud(
                    frame, hud_gesture, metrics, controller.enabled, config,
                    show_help=session.hud.help_visible(now_mono), now=now_mono,
                )
            cv2.imshow(WINDOW_NAME, frame)
            # Reassert the preview z-order periodically. On Windows this also restores
            # an accidentally minimized preview without activating it over the target app.
            if config.preview_always_on_top and now_mono - last_window_maintenance >= 0.5:
                window_manager.ensure_visible()
                last_window_maintenance = now_mono

            key = cv2.waitKey(1) & 0xFF
            if handle_key(key, session) or _window_closed():
                break
    except KeyboardInterrupt:
        pass
    except StartupError as exc:
        print(f"\nNoMouse could not start: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"\nNoMouse could not start: a required package is missing ({exc}).\n"
            "Run install_windows.bat (or: python -m pip install -r requirements.txt) and try again.",
            file=sys.stderr,
        )
        return 1
    finally:
        if controller is not None:
            controller.release_all()
        if tracker is not None:
            try:
                tracker.close()
            except Exception:
                pass
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        if window_ready:
            cv2.destroyAllWindows()
        if session is not None and session.settings_dirty and not args.no_save:
            try:
                save_config(config, config_path)
                print(f"Saved your smoothing/landmark choices to {config_path}")
            except OSError as exc:
                print(f"Could not save settings ({exc}).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
