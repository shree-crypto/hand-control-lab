# -*- mode: python ; coding: utf-8 -*-
"""Windows x64, onedir build. Run from any cwd with PyInstaller."""
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

PROJECT = Path(SPECPATH).resolve().parent
sys.path.insert(0,str(PROJECT))
MODEL_NAMES = (
    "hand_landmarker.task",
    "face_landmarker.task",
    "pose_landmarker_lite.task",
)
datas = []
binaries = []
hiddenimports = collect_submodules("gesture_control")
for package in ("mediapipe", "cv2", "mido", "rtmidi"):
    package_data, package_binaries, package_hidden = collect_all(package)
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_hidden
hiddenimports += [
    "mido.backends.rtmidi",
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
]
for name in MODEL_NAMES:
    model = PROJECT / "models" / name
    if not model.is_file():
        raise SystemExit(f"Missing {model}; run python tools/download_model.py --face --pose")
    datas.append((str(model), "models"))
datas.append((str(PROJECT / "LICENSE"), "."))
datas.append((str(PROJECT / "NOTICE"), "."))
datas.append((str(PROJECT / "LICENSES"), "LICENSES"))

analysis = Analysis(
    [str(PROJECT / "packaging" / "entry.py")],
    pathex=[str(PROJECT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="HandControl",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    contents_directory="_internal",
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="HandControl",
)
