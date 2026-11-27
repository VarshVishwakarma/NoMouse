"""Camera and gesture-control worker used by the desktop dashboard."""

from __future__ import annotations

import statistics
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .app import GesturePipeline
from .config import AppConfig
from .controller import MouseController
from .errors import StartupError
from .hud import WINDOW_NAME
from .safety import WindowBounds, WindowSafetyGuard
from .types import Gesture


@dataclass(frozen=True)
class PerformanceReport:
    fps: float = 0.0
    capture_ms: float = 0.0
    inference_ms: float = 0.0
    decision_ms: float = 0.0
    frame_ms: float = 0.0
    frame_p50_ms: float = 0.0
    frame_p95_ms: float = 0.0
    frames: int = 0
    slow_intervals: int = 0
    tracking_interruptions: int = 0
    detected: bool = False
    gesture: str = "SEARCHING"
    cursor: tuple[int, int] | None = None


class BoundsSnapshot:
    """Thread-safe screen-space preview bounds shared by the GUI and worker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bounds: WindowBounds | None = None

    def set(self, bounds: WindowBounds) -> None:
        with self._lock:
            self._bounds = bounds

    def get(self) -> WindowBounds | None:
        with self._lock:
            return self._bounds


class CameraWorker(QThread):
    """Owns camera, tracker, controller, and pipeline for one live session."""

    frame_ready = Signal(QImage)
    status_changed = Signal(str)
    metrics_updated = Signal(object)
    failure = Signal(str)

    def __init__(self, config: AppConfig, bounds: BoundsSnapshot):
        super().__init__()
        self.config = config
        self.bounds = bounds
        self._stop_requested = threading.Event()
        self._pause_lock = threading.Lock()
        self._pause_requested = False
        self._recenter_requested = threading.Event()
        self._report_lock = threading.Lock()
        self._report = PerformanceReport()

    def request_stop(self) -> None:
        self._stop_requested.set()

    def request_pause(self, paused: bool) -> None:
        with self._pause_lock:
            self._pause_requested = paused

    def request_scroll_recenter(self) -> None:
        self._recenter_requested.set()

    def report(self) -> PerformanceReport:
        with self._report_lock:
            return self._report

    def run(self) -> None:
        cap = None
        tracker = None
        controller = None
        safety = None
        frame_times: deque[float] = deque(maxlen=300)
        frame_intervals: deque[float] = deque(maxlen=60)
        frame_count = slow_intervals = interruptions = 0
        was_tracking = False
        last_report_at = 0.0
        frame_failures = 0
        last_frame_at: float | None = None
        cursor: tuple[int, int] | None = None
        gesture = Gesture.UNKNOWN

        try:
            import pyautogui

            from .tracker import HandTracker

            backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            cap = cv2.VideoCapture(self.config.camera_index, backend)
            if not cap.isOpened():
                raise StartupError(
                    "No camera could be opened. Check camera permissions, close other camera apps, "
                    "or select another camera in Settings."
                )
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.camera_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.camera_height)
            cap.set(cv2.CAP_PROP_FPS, self.config.camera_fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if sys.platform == "win32":
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

            tracker = HandTracker(
                self.config.max_hands,
                self.config.min_detection_confidence,
                self.config.min_tracking_confidence,
                self.config.model_complexity,
            )
            safety = WindowSafetyGuard(
                WINDOW_NAME,
                self.config.safety_guard_enabled,
                bounds_provider=self.bounds.get,
            )
            controller = MouseController(self.config, safety)
            screen = pyautogui.size()
            pipeline = GesturePipeline(self.config, controller, screen)
            self.status_changed.emit("Live · tracking hand")

            while not self._stop_requested.is_set():
                capture_start = time.perf_counter()
                ok, frame = cap.read()
                capture_ms = (time.perf_counter() - capture_start) * 1000.0
                if not ok or frame is None:
                    frame_failures += 1
                    if frame_failures == 1:
                        pipeline.reset()
                        self.status_changed.emit("Camera interrupted · releasing controls")
                    if frame_failures >= 120:
                        raise StartupError("Camera stopped responding. NoMouse stopped control safely.")
                    self._stop_requested.wait(0.01)
                    continue
                frame_failures = 0
                frame_start = time.perf_counter()
                if self.config.mirror_preview:
                    frame = cv2.flip(frame, 1)
                observations, result = tracker.process(frame)
                detected = bool(observations)
                if was_tracking and not detected:
                    interruptions += 1
                was_tracking = detected
                if self.config.show_landmarks:
                    tracker.draw_landmarks(frame, result)

                with self._pause_lock:
                    paused = self._pause_requested
                if controller.enabled == paused and controller.fatal_input_error is None:
                    controller.toggle_enabled()

                decision_start = time.perf_counter()
                outcome = pipeline.step(observations, decision_start)
                decision_ms = (time.perf_counter() - decision_start) * 1000.0
                gesture = outcome.gesture
                cursor = (
                    (round(outcome.cursor_xy[0]), round(outcome.cursor_xy[1]))
                    if outcome.cursor_xy is not None
                    else None
                )
                if self._recenter_requested.is_set():
                    if gesture == Gesture.TWO_FINGERS and outcome.scroll_y is not None:
                        pipeline.scroll_smoother.reset()
                        controller.scroller.reset(outcome.scroll_y, time.monotonic())
                        self._recenter_requested.clear()
                        self.status_changed.emit("Scroll neutral position updated")

                if controller.fatal_input_error is not None:
                    raise StartupError(
                        f"Computer input stopped after an error: {controller.fatal_input_error}. "
                        "Restart NoMouse before trying again."
                    )

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width, channels = rgb.shape
                image = QImage(
                    rgb.data,
                    width,
                    height,
                    channels * width,
                    QImage.Format.Format_RGB888,
                ).copy()
                self.frame_ready.emit(image)

                frame_ms = (time.perf_counter() - frame_start) * 1000.0
                frame_count += 1
                if last_frame_at is not None:
                    interval = frame_start - last_frame_at
                    frame_intervals.append(interval)
                    if interval > 1.0 / 30.0:
                        slow_intervals += 1
                last_frame_at = frame_start
                frame_times.append(frame_ms)
                now = time.monotonic()
                if now - last_report_at >= 0.25:
                    ordered = sorted(frame_times)
                    report = PerformanceReport(
                        fps=0.0 if not frame_intervals else len(frame_intervals) / max(1e-6, sum(frame_intervals)),
                        capture_ms=capture_ms,
                        inference_ms=tracker.last_inference_ms,
                        decision_ms=decision_ms,
                        frame_ms=frame_ms,
                        frame_p50_ms=statistics.median(ordered),
                        frame_p95_ms=ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
                        frames=frame_count,
                        slow_intervals=slow_intervals,
                        tracking_interruptions=interruptions,
                        detected=detected,
                        gesture=gesture.value,
                        cursor=cursor,
                    )
                    with self._report_lock:
                        self._report = report
                    self.metrics_updated.emit(asdict(report))
                    last_report_at = now
        except Exception as exc:
            self.failure.emit(str(exc))
        finally:
            self.status_changed.emit("Stopping safely")
            try:
                if controller is not None:
                    controller.release_all()
                    if controller.fatal_input_error:
                        self.failure.emit(f"Could not confirm mouse-button release: {controller.fatal_input_error}")
            finally:
                try:
                    if tracker is not None:
                        tracker.close()
                except Exception as exc:
                    self.failure.emit(f"Could not close the hand tracker: {type(exc).__name__}")
                finally:
                    if cap is not None:
                        cap.release()
            self.status_changed.emit("Stopped")
