"""Window-manager tests use a fake Win32 API; no desktop is required."""
from __future__ import annotations

import ctypes

from nomouse import window_manager as wm


class FakeUser32:
    def __init__(self, *, iconic=False, hwnd=123):
        self.iconic = iconic
        self.hwnd = hwnd
        self.show_calls = []
        self.position_calls = []
        self.find_calls = []

    def FindWindowW(self, class_name, window_name):
        self.find_calls.append((class_name, window_name))
        return self.hwnd

    def IsIconic(self, hwnd):
        return self.iconic

    def ShowWindow(self, hwnd, command):
        self.show_calls.append((hwnd, command))
        self.iconic = False
        return 1

    def SetWindowPos(self, hwnd, insert_after, x, y, width, height, flags):
        self.position_calls.append((hwnd, insert_after, x, y, width, height, flags))
        return 1


def test_set_topmost_uses_no_activate_and_restores_minimized_window(monkeypatch):
    fake = FakeUser32(iconic=True)
    props = []
    monkeypatch.setattr(wm.cv2, "WND_PROP_TOPMOST", 5, raising=False)
    monkeypatch.setattr(wm.cv2, "setWindowProperty", lambda *args: props.append(args))
    manager = wm.PreviewWindowManager("NoMouse | Touchless Control", user32=fake, platform_name="win32")

    assert manager.set_always_on_top(True) is True
    assert fake.show_calls == [(123, wm.SW_SHOWNOACTIVATE)]
    assert props == [("NoMouse | Touchless Control", 5, 1.0)]
    assert len(fake.position_calls) == 1
    hwnd, insert_after, _x, _y, _w, _h, flags = fake.position_calls[0]
    assert hwnd == 123
    assert insert_after.value == ctypes.c_void_p(wm.HWND_TOPMOST_VALUE).value
    assert flags & wm.SWP_NOACTIVATE
    assert flags & wm.SWP_SHOWWINDOW


def test_toggle_off_removes_topmost_without_restoring_minimized_window(monkeypatch):
    fake = FakeUser32(iconic=True)
    props = []
    monkeypatch.setattr(wm.cv2, "WND_PROP_TOPMOST", 5, raising=False)
    monkeypatch.setattr(wm.cv2, "setWindowProperty", lambda *args: props.append(args))
    manager = wm.PreviewWindowManager("NoMouse | Touchless Control", user32=fake, platform_name="win32")

    assert manager.set_always_on_top(False) is True
    assert fake.show_calls == []
    assert props[-1][-1] == 0.0
    assert fake.position_calls[0][1].value == ctypes.c_void_p(wm.HWND_NOTOPMOST_VALUE).value


def test_ensure_visible_reasserts_topmost_and_restores_minimized_preview():
    fake = FakeUser32(iconic=True)
    manager = wm.PreviewWindowManager("NoMouse | Touchless Control", user32=fake, platform_name="win32")
    assert manager.ensure_visible() is True
    assert fake.show_calls == [(123, wm.SW_SHOWNOACTIVATE)]
    assert len(fake.position_calls) == 1


def test_non_windows_without_native_api_is_safe(monkeypatch):
    monkeypatch.setattr(wm.cv2, "WND_PROP_TOPMOST", 5, raising=False)
    monkeypatch.setattr(wm.cv2, "setWindowProperty", lambda *_args: None)
    manager = wm.PreviewWindowManager("NoMouse | Touchless Control", platform_name="linux")
    assert manager.set_always_on_top(True) is False
    assert manager.ensure_visible() is False
