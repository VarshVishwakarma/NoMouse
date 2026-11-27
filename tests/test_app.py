"""Headless tests of the application shell: key handling, CLI, and the full run() loop."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from nomouse import __version__, app
from nomouse.config import AppConfig
from nomouse.controller import MouseController
from nomouse.hud import HudState
from tests.support import FakeMouse, SafeGuard, pinch_hand, pointing_hand


def make_session(**overrides):
    config = AppConfig(**overrides)
    controller = MouseController(config, SafeGuard(), mouse_api=FakeMouse())
    pipeline = app.GesturePipeline(config, controller, (1920, 1080))
    return app.Session(config, pipeline, controller, HudState())


# ---------------------------------------------------------------- key handling

@pytest.mark.parametrize("key", [ord("q"), 27])
def test_quit_keys(key):
    assert app.handle_key(key, make_session()) is True


def test_smoothing_keys_adjust_clamp_and_mark_settings_dirty():
    session = make_session(cursor_smoothing=0.38)
    assert app.handle_key(ord("+"), session) is False
    assert session.config.cursor_smoothing == pytest.approx(0.41)
    assert session.settings_dirty
    for _ in range(100):
        app.handle_key(ord("-"), session)
    assert session.config.cursor_smoothing == 0.0
    for _ in range(100):
        app.handle_key(ord("="), session)
    assert session.config.cursor_smoothing == 1.0


def test_pause_help_and_landmark_keys():
    session = make_session()
    app.handle_key(ord("p"), session)
    assert not session.controller.enabled
    app.handle_key(ord("h"), session)
    assert session.hud.show_help
    app.handle_key(ord("l"), session)
    assert session.config.show_landmarks is False


def test_unrelated_keys_change_nothing():
    session = make_session()
    app.handle_key(255, session)  # what waitKey(1) returns when nothing is pressed
    assert not session.settings_dirty and session.controller.enabled

def test_o_key_toggles_preview_always_on_top_and_marks_settings_dirty():
    class FakeWindowManager:
        def __init__(self):
            self.states = []

        def set_always_on_top(self, enabled):
            self.states.append(enabled)

    session = make_session(preview_always_on_top=True)
    manager = FakeWindowManager()
    session.window_manager = manager

    assert app.handle_key(ord("o"), session) is False
    assert session.config.preview_always_on_top is False
    assert manager.states == [False]
    assert session.settings_dirty

    assert app.handle_key(ord("o"), session) is False
    assert session.config.preview_always_on_top is True
    assert manager.states == [False, True]


# ------------------------------------------------------------------------- CLI

def test_cli_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        app.run(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_cli_parses_options(tmp_path):
    args = app.build_arg_parser().parse_args(["--camera", "2", "--no-save", "--config", str(tmp_path / "c.json")])
    assert args.camera == 2 and args.no_save and args.config == tmp_path / "c.json"


def test_missing_dependency_gives_friendly_error_not_a_traceback(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "pyautogui", None)  # makes `import pyautogui` raise ImportError
    assert app.run([]) == 1
    assert "required package is missing" in capsys.readouterr().err


def test_camera_failure_at_startup_returns_error_code(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "pyautogui", FakeMouse())
    monkeypatch.setitem(sys.modules, "nomouse.tracker", SimpleNamespace(HandTracker=object))

    def no_camera(config):
        raise app.StartupError("Could not open the webcam.")

    monkeypatch.setattr(app, "_open_camera", no_camera)
    assert app.run([]) == 1
    assert "Could not open the webcam" in capsys.readouterr().err


# ------------------------------------------------------- full headless run() loop

class FakeClock:
    """Replaces the `time` module inside nomouse.app so frames advance at a fixed 30 fps."""

    def __init__(self):
        self.now = 100.0

    def perf_counter(self):
        self.now += 1 / 30
        return self.now

    def monotonic(self):
        return self.now

    def sleep(self, _seconds):
        pass


class FakeCap:
    def __init__(self, script):
        self.script = list(script)  # each item: a frame (np.ndarray) or None for a failed read
        self.released = False

    def isOpened(self):
        return True

    def get(self, prop):
        return {cv2.CAP_PROP_FRAME_WIDTH: 640, cv2.CAP_PROP_FRAME_HEIGHT: 480, cv2.CAP_PROP_FPS: 30}.get(prop, 0)

    def set(self, *_args):
        return True

    def read(self):
        if not self.script:
            return False, None
        item = self.script.pop(0)
        return (False, None) if item is None else (True, item)

    def release(self):
        self.released = True


class FakeTracker:
    hands_by_call: list = []
    instances: list = []

    def __init__(self, *_args):
        self.calls = 0
        self.last_inference_ms = 5.0
        self.closed = False
        FakeTracker.instances.append(self)

    def process(self, _frame):
        hand = FakeTracker.hands_by_call[min(self.calls, len(FakeTracker.hands_by_call) - 1)]
        self.calls += 1
        return ([hand] if hand is not None else []), None

    def draw_landmarks(self, *_args):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def headless(monkeypatch, tmp_path):
    """Wire run() to a fake camera, tracker, mouse, clock, and preview window."""
    mouse = FakeMouse()
    clock = FakeClock()
    keys: list[int] = []
    FakeTracker.instances = []
    monkeypatch.setitem(sys.modules, "pyautogui", mouse)
    monkeypatch.setitem(sys.modules, "nomouse.tracker", SimpleNamespace(HandTracker=FakeTracker))
    monkeypatch.setattr(app, "time", clock)
    monkeypatch.setattr(cv2, "namedWindow", lambda *a, **k: None)
    monkeypatch.setattr(cv2, "resizeWindow", lambda *a, **k: None)
    monkeypatch.setattr(cv2, "imshow", lambda *a, **k: None)
    monkeypatch.setattr(cv2, "destroyAllWindows", lambda *a, **k: None)
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *a, **k: 1.0)
    monkeypatch.setattr(cv2, "waitKey", lambda _delay: keys.pop(0) if keys else 255)

    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"safety_guard_enabled": False}))

    def install_camera(script):
        cap = FakeCap(script)
        monkeypatch.setattr(app, "_open_camera", lambda _config: cap)
        return cap

    return SimpleNamespace(mouse=mouse, keys=keys, config_path=config_path, install_camera=install_camera)


def frames(n):
    return [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(n)]


def test_run_loop_moves_cursor_and_cleans_up_on_quit(headless):
    FakeTracker.hands_by_call = [pointing_hand()]
    cap = headless.install_camera(frames(10))
    headless.keys.extend([255] * 8 + [ord("q")])
    assert app.run(["--config", str(headless.config_path)]) == 0
    assert any(e[0] == "move" for e in headless.mouse.events)
    assert cap.released and FakeTracker.instances[0].closed


def test_hotkey_changes_are_saved_on_exit_unless_disabled(headless):
    FakeTracker.hands_by_call = [None]
    headless.install_camera(frames(5))
    headless.keys.extend([ord("+"), ord("l"), ord("q")])
    assert app.run(["--config", str(headless.config_path)]) == 0
    saved = json.loads(headless.config_path.read_text())
    assert saved["cursor_smoothing"] == pytest.approx(0.41)
    assert saved["show_landmarks"] is False
    assert saved["safety_guard_enabled"] is False  # unrelated settings survive the rewrite

    headless.config_path.write_text(json.dumps({"safety_guard_enabled": False}))
    headless.install_camera(frames(5))
    headless.keys.extend([ord("+"), ord("q")])
    assert app.run(["--config", str(headless.config_path), "--no-save"]) == 0
    assert json.loads(headless.config_path.read_text()) == {"safety_guard_enabled": False}


def test_closing_the_preview_window_exits_instead_of_reopening_it(headless, monkeypatch):
    FakeTracker.hands_by_call = [None]
    headless.install_camera(frames(1000))
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *a, **k: 0.0)  # window closed by the user
    assert app.run(["--config", str(headless.config_path)]) == 0  # would hang/loop forever if ignored


def test_camera_failure_during_drag_releases_the_mouse_button(headless):
    # The key safety invariant: a dead webcam must never leave the left button held down.
    FakeTracker.hands_by_call = [pointing_hand()] * 4 + [pinch_hand()] * 20 + [None]
    headless.install_camera(frames(24))  # then every read fails until the loop gives up
    assert app.run(["--config", str(headless.config_path)]) == 0
    events = headless.mouse.events
    assert ("down", "left") in events, "the held pinch should have started a drag"
    assert ("up", "left") in events, "the camera failure must release it"
    assert events.index(("up", "left")) > events.index(("down", "left"))


def test_exception_inside_loop_still_releases_a_held_drag(headless, monkeypatch):
    FakeTracker.hands_by_call = [pointing_hand()] * 4 + [pinch_hand()] * 20
    headless.install_camera(frames(40))

    def boom(*_args, **_kwargs):
        raise ValueError("simulated crash")

    original_waitkey = cv2.waitKey
    calls = {"n": 0}

    def crash_late(delay):
        calls["n"] += 1
        if calls["n"] == 25:
            boom()
        return original_waitkey(delay)

    monkeypatch.setattr(cv2, "waitKey", crash_late)
    with pytest.raises(ValueError, match="simulated crash"):
        app.run(["--config", str(headless.config_path)])
    assert ("up", "left") in headless.mouse.events
