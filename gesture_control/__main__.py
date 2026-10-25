# SPDX-License-Identifier: GPL-3.0-only
"""Launch desktop preview or an explicitly selected experiment."""
import importlib
import sys

MODES = {
    "camera-lab": ("camera_lab", []),
    "workbench": ("workbench", []),
    "gaze": ("gaze", []),
    "draw": ("creative", []),
    "music": ("creative", ["--instrument"]),
    "gestures": ("gestures", []),
    "record": ("gestures", ["--record"]),
    "backends": ("backends", []),
    "face": ("face", []),
    "drums": ("midi_instrument", []),
    "piano": ("midi_instrument", ["--piano"]),
    "finger-drums": ("personalized_midi", []),
    "four-limb": ("personalized_midi", ["--four-limb"]),
    "hand-calibration": ("hand_calibration", []),
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("labs", "--labs"):
        print("Experiments (no desktop input):")
        for mode in MODES:
            print(f"  python -m gesture_control {mode} --help")
        return 0
    if argv and argv[0] in MODES:
        module, defaults = MODES[argv.pop(0)]
        return importlib.import_module(f".experiments.{module}", __package__).main(defaults + argv)
    from .app import main as desktop_main
    return desktop_main(argv)

if __name__ == "__main__":
    raise SystemExit(main())
