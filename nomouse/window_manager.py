"""Keep the NoMouse OpenCV preview visible while using other applications.

OpenCV's TOPMOST property is attempted first. On Windows, native SetWindowPos is
also used because some OpenCV/HighGUI backends do not consistently preserve this
property while another application becomes active. Calls use NOACTIVATE so the
preview does not steal keyboard focus from the app the user is working in.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any

import cv2

HWND_TOPMOST_VALUE = -1
HWND_NOTOPMOST_VALUE = -2
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
_WINDOW_POS_FLAGS = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW


class PreviewWindowManager:
    """Manage preview z-order without activating it over the user's work.

    ``platform_name`` and ``user32`` are injectable to allow deterministic tests
    without a Windows desktop. When always-on-top is enabled, ``ensure_visible``
    also restores the preview if another action minimized it.
    """

    def __init__(
        self,
        window_name: str,
        always_on_top: bool = True,
        *,
        platform_name: str | None = None,
        user32: Any | None = None,
    ) -> None:
        self.window_name = window_name
        self.always_on_top = bool(always_on_top)
        self.platform_name = sys.platform if platform_name is None else platform_name
        self._injected_user32 = user32

    def set_always_on_top(self, enabled: bool) -> bool:
        """Set preview z-order; return whether a native Windows window was found."""
        self.always_on_top = bool(enabled)
        self._set_opencv_topmost(self.always_on_top)
        return self._apply_native(restore_if_minimized=self.always_on_top)

    def ensure_visible(self) -> bool:
        """Reassert topmost status and restore a minimized preview without focus theft."""
        if not self.always_on_top:
            return False
        self._set_opencv_topmost(True)
        return self._apply_native(restore_if_minimized=True)

    def _set_opencv_topmost(self, enabled: bool) -> None:
        prop = getattr(cv2, "WND_PROP_TOPMOST", None)
        if prop is None:
            return
        try:
            cv2.setWindowProperty(self.window_name, prop, 1.0 if enabled else 0.0)
        except Exception:
            # Native Win32 fallback below covers Windows builds where HighGUI's
            # topmost property is unsupported or fails for this window backend.
            pass

    def _user32(self):
        if self._injected_user32 is not None:
            return self._injected_user32
        if self.platform_name != "win32":
            return None
        try:
            return ctypes.windll.user32
        except (AttributeError, OSError):
            return None

    def _apply_native(self, restore_if_minimized: bool) -> bool:
        user32 = self._user32()
        if user32 is None or self.platform_name != "win32":
            return False
        try:
            # ctypes defaults Win32 return values to c_int, which can truncate HWNDs
            # on 64-bit Windows. Declare the native signatures for real DLL functions;
            # injected fakes used by unit tests intentionally skip this block.
            if self._injected_user32 is None:
                user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
                user32.FindWindowW.restype = wintypes.HWND
                user32.IsIconic.argtypes = [wintypes.HWND]
                user32.IsIconic.restype = wintypes.BOOL
                user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
                user32.ShowWindow.restype = wintypes.BOOL
                user32.SetWindowPos.argtypes = [
                    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                    ctypes.c_int, ctypes.c_int, wintypes.UINT,
                ]
                user32.SetWindowPos.restype = wintypes.BOOL
            hwnd = user32.FindWindowW(None, self.window_name)
            if not hwnd:
                return False  # First frame may not have created the native handle yet.
            if restore_if_minimized and user32.IsIconic(hwnd):
                # SW_SHOWNOACTIVATE restores without stealing focus from the browser/editor.
                user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            insert_after = ctypes.c_void_p(
                HWND_TOPMOST_VALUE if self.always_on_top else HWND_NOTOPMOST_VALUE
            )
            return bool(user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, _WINDOW_POS_FLAGS))
        except Exception:
            # Window-management failure must not stop camera tracking or mouse control.
            return False
