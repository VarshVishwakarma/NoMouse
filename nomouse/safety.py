"""Fail-closed guard for mouse actions near the NoMouse preview window."""
from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass
class WindowBounds:
    x: int
    y: int
    width: int
    height: int

    def contains(self, px: int, py: int, padding: int = 8) -> bool:
        return (self.x - padding <= px <= self.x + self.width + padding and
                self.y - padding <= py <= self.y + self.height + padding)


class WindowSafetyGuard:
    def __init__(self, window_name: str, enabled: bool = True):
        self.window_name = window_name
        self.enabled = enabled
        self.last_reason = ""

    def _bounds(self) -> WindowBounds | None:
        try:
            import cv2
            x, y, width, height = cv2.getWindowImageRect(self.window_name)
            if width > 0 and height > 0:
                return WindowBounds(int(x), int(y), int(width), int(height))
        except Exception:
            pass
        # On Windows, use the native top-level window rectangle as a fallback.
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                hwnd_found = wintypes.HWND()
                callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

                def callback(hwnd, _):
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length <= 0:
                        return True
                    title = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, title, length + 1)
                    if title.value == self.window_name:
                        hwnd_found.value = hwnd
                        return False
                    return True

                user32.EnumWindows(callback_type(callback), 0)
                if hwnd_found.value:
                    rect = wintypes.RECT()
                    if user32.GetWindowRect(hwnd_found, ctypes.byref(rect)):
                        return WindowBounds(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
            except Exception:
                pass
        return None

    def allows_action(self, x: int, y: int) -> bool:
        if not self.enabled:
            self.last_reason = "Safety guard disabled in settings"
            return True
        bounds = self._bounds()
        if bounds is None:
            self.last_reason = "Window bounds unavailable; action blocked"
            return False
        if bounds.contains(x, y):
            self.last_reason = "Action blocked over preview window"
            return False
        self.last_reason = ""
        return True
