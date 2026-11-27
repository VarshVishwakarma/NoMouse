from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import cv2
import numpy as np

from nomouse.config import AppConfig
from nomouse.gui_worker import BoundsSnapshot, CameraWorker
from nomouse.safety import WindowBounds


class FakeCapture:
    def __init__(self, opened: bool, frame: np.ndarray | None = None):
        self.opened = opened
        self.frame = frame
        self.released = False
        self.worker: CameraWorker | None = None
        self.settings: dict[int, float] = {}

    def isOpened(self) -> bool:
        return self.opened

    def set(self, *_args) -> bool:
        self.settings[int(_args[0])] = float(_args[1])
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.worker is not None:
            self.worker.request_stop()
        return self.frame is not None, self.frame

    def release(self) -> None:
        self.released = True


def install_fake_pyautogui(monkeypatch) -> None:
    fake = ModuleType("pyautogui")
    fake.FAILSAFE = True
    fake.PAUSE = 0.1
    fake.size = lambda: (1920, 1080)
    monkeypatch.setitem(sys.modules, "pyautogui", fake)


def test_worker_closes_tracker_and_camera_after_stop(monkeypatch):
    install_fake_pyautogui(monkeypatch)
    capture = FakeCapture(True, np.zeros((32, 32, 3), dtype=np.uint8))
    monkeypatch.setattr(cv2, "VideoCapture", lambda *_args: capture)

    tracker_state = {"closed": False}

    class FakeTracker:
        def __init__(self, *_args):
            pass

        def process(self, _frame):
            return [], SimpleNamespace(hand_landmarks=[])

        def close(self):
            tracker_state["closed"] = True

    monkeypatch.setitem(sys.modules, "nomouse.tracker", SimpleNamespace(HandTracker=FakeTracker))

    worker = CameraWorker(AppConfig(show_landmarks=False, camera_fps=24), BoundsSnapshot())
    capture.worker = worker
    worker.run()

    assert capture.released
    assert capture.settings[cv2.CAP_PROP_FPS] == 24
    assert tracker_state["closed"]


def test_worker_surfaces_camera_startup_failure_and_releases_capture(monkeypatch):
    install_fake_pyautogui(monkeypatch)
    capture = FakeCapture(False)
    monkeypatch.setattr(cv2, "VideoCapture", lambda *_args: capture)
    bounds = BoundsSnapshot()
    bounds.set(WindowBounds(0, 0, 20, 20))
    worker = CameraWorker(AppConfig(), bounds)
    failures: list[str] = []
    worker.failure.connect(failures.append)

    worker.run()

    assert capture.released
    assert failures
    assert "No camera could be opened" in failures[0]
