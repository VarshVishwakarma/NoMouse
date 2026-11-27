"""Print local environment and dependency diagnostics for NoMouse support reports.

This tool does not open the webcam, inspect desktop content, or send mouse input.
Run from the project folder with the project's virtual-environment Python.
"""
from __future__ import annotations

import platform
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# (module, required). Dev-only tools are reported but never fail the check.
MODULES = (
    ("numpy", True),
    ("cv2", True),
    ("mediapipe", True),
    ("pyautogui", True),
    ("pytest", False),
)


def main() -> int:
    from nomouse import __version__

    print(f"NoMouse {__version__} diagnostic")
    print("=" * 40)
    print(f"Python: {sys.version.split()[0]} ({platform.architecture()[0]})")
    print(f"Executable: {sys.executable}")
    print(f"Platform: {platform.platform()}")
    failed = False

    if sys.version_info[:2] not in ((3, 10), (3, 11), (3, 12)):
        print("  WARNING: the pinned dependencies are tested with Python 3.10-3.12 (3.11 recommended).")

    for module_name, required in MODULES:
        try:
            module = __import__(module_name)
            print(f"{module_name}: {getattr(module, '__version__', 'version unknown')}")
            if module_name == "mediapipe" and not hasattr(module, "solutions"):
                print("  ERROR: mediapipe.solutions is unavailable; install the pinned requirements in this venv.")
                failed = True
            if module_name == "cv2" and not hasattr(module, "VideoCapture"):
                print("  ERROR: cv2.VideoCapture is unavailable; check OpenCV installation.")
                failed = True
        except Exception as exc:
            label = "IMPORT FAILED" if required else "not installed (optional, only needed to run tests)"
            print(f"{module_name}: {label} ({type(exc).__name__}: {exc})")
            failed = failed or required

    try:
        from nomouse.config import default_config_path, load_config

        config = load_config()
        print(f"Settings: {default_config_path()}")
        print(
            f"  loaded (camera_index={config.camera_index}, "
            f"resolution={config.camera_width}x{config.camera_height})"
        )
    except Exception as exc:
        print(f"Settings: FAILED ({type(exc).__name__}: {exc})")
        failed = True

    print("\nThis check does not test camera hardware or real mouse input.")
    print("If imports fail, run: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
