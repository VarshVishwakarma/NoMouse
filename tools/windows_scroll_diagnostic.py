"""Manual Windows-only mouse-wheel diagnostic for NoMouse.

WARNING: This utility sends real scroll events to the window under the pointer.
Keep the pointer over a harmless page and do not run while editing important text.
Press U to scroll up, D to scroll down, and Q to quit in this console.
"""
from __future__ import annotations

import sys
import time


def main() -> int:
    if sys.platform != "win32":
        print("This diagnostic is Windows-only.")
        return 1

    import ctypes
    import msvcrt

    user32 = ctypes.windll.user32
    MOUSEEVENTF_WHEEL = 0x0800
    WHEEL_DELTA = 120
    print("NoMouse Windows mouse-wheel diagnostic")
    print("Place the pointer over a harmless page/window first.")
    print("U = scroll up | D = scroll down | Q = quit")
    try:
        while True:
            if msvcrt.kbhit():
                key = msvcrt.getch().lower()
                if key == b"q":
                    return 0
                if key == b"u":
                    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, WHEEL_DELTA, 0)
                    print("Sent wheel UP")
                elif key == b"d":
                    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, -WHEEL_DELTA, 0)
                    print("Sent wheel DOWN")
            time.sleep(0.02)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
