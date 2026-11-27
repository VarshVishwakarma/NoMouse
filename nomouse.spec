# PyInstaller onedir build. Run with: python -m PyInstaller --clean --noconfirm nomouse.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


def _include_mediapipe_module(name):
    optional_subtrees = (
        "mediapipe.tasks.python.test",
        "mediapipe.tasks.python.benchmark",
        "mediapipe.tasks.python.genai.",
    )
    return not any(name.startswith(subtree) for subtree in optional_subtrees)


mediapipe_datas, mediapipe_binaries, mediapipe_hidden = collect_all(
    "mediapipe",
    filter_submodules=_include_mediapipe_module,
    exclude_datas=["**/test/**", "**/benchmark/**"],
)
model_file = Path(SPECPATH) / "nomouse" / "models" / "hand_landmarker.task"
mediapipe_datas.append((str(model_file), "nomouse/models"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=mediapipe_binaries,
    datas=mediapipe_datas,
    hiddenimports=mediapipe_hidden + ["cv2", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NoMouse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NoMouse",
)
