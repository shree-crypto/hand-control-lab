# SPDX-License-Identifier: GPL-3.0-only
"""Learn thumb-to-finger pinch thresholds from comfortable personal movements."""
import argparse
from collections import deque
import json
from math import hypot, isfinite
from pathlib import Path
from statistics import mean, pstdev


FINGERS = {"index": 8, "middle": 12, "ring": 16, "pinky": 20}
PROFILE_KEYS = {"version", "dominant", "primary_finger", "secondary_finger",
                "primary_on", "primary_off", "secondary_on", "secondary_off"}
DEFAULT_PROFILE = Path.home() / ".hand-control" / "pinch.json"


def selected_distances(points, primary="index", secondary="middle", width=640, height=480):
    """Return palm-normalized thumb distances without judging hand posture."""
    if primary not in FINGERS or secondary not in FINGERS or primary == secondary:
        raise ValueError("Choose two different fingers: index, middle, ring, pinky")
    selected = (0,9,4,FINGERS[primary],FINGERS[secondary])
    if len(points) != 21 or not all(len(points[i]) >= 2 and all(isfinite(v) for v in points[i][:2]) for i in selected):
        return None
    def distance(a, b):
        return hypot((points[a][0] - points[b][0]) * width,
                     (points[a][1] - points[b][1]) * height)
    palm = distance(0, 9)
    if palm < 5:
        return None
    return distance(4, FINGERS[primary]) / palm, distance(4, FINGERS[secondary]) / palm


def calibrate_thresholds(released, pressed):
    """Derive hysteresis from two observed states, including small movement ranges."""
    released, pressed = list(released), list(pressed)
    if min(len(released), len(pressed)) < 8:
        raise ValueError("Capture at least eight observations of each state")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) and 0 <= v <= 5
               for v in released + pressed):
        raise ValueError("Distances must be finite palm-normalized values between 0 and 5")
    up, down = mean(released), mean(pressed)
    gap = up - down
    noise = max(pstdev(released), pstdev(pressed))
    if gap < max(.01, noise * 4):
        raise ValueError("Released and pinched observations overlap; retry slower or choose another finger")
    return down + gap * .30, down + gap * .70


def validate_pinch_profile(profile):
    """Only allow controller settings, never extra arbitrary fields."""
    if not isinstance(profile, dict) or set(profile) != PROFILE_KEYS:
        raise ValueError("Pinch profile has missing or unknown fields")
    if type(profile["version"]) is not int or profile["version"] != 1:
        raise ValueError("Unsupported pinch profile version")
    if profile["dominant"] not in ("Left", "Right"):
        raise ValueError("Profile dominant hand must be Left or Right")
    primary, secondary = profile["primary_finger"], profile["secondary_finger"]
    if not isinstance(primary, str) or not isinstance(secondary, str) or primary not in FINGERS or secondary not in FINGERS or primary == secondary:
        raise ValueError("Profile must choose two different supported fingers")
    for prefix in ("primary", "secondary"):
        on, off = profile[f"{prefix}_on"], profile[f"{prefix}_off"]
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) for v in (on, off)):
            raise ValueError("Pinch thresholds must be finite numbers")
        if not 0 < on < off <= 5:
            raise ValueError("Pinch thresholds must satisfy 0 < on < off <= 5")
    return dict(profile)


def load_pinch_profile(path):
    path = Path(path)
    if path.stat().st_size > 4096:
        raise ValueError("Pinch profile is unexpectedly large")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate pinch profile key")
            result[key] = value
        return result
    return validate_pinch_profile(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs))


def make_profile(dominant, primary, secondary, released, pressed_primary, pressed_secondary):
    p_on, p_off = calibrate_thresholds([v[0] for v in released], pressed_primary)
    s_on, s_off = calibrate_thresholds([v[1] for v in released], pressed_secondary)
    return validate_pinch_profile({"version": 1, "dominant": dominant,
        "primary_finger": primary, "secondary_finger": secondary,
        "primary_on": p_on, "primary_off": p_off,
        "secondary_on": s_on, "secondary_off": s_off})


def save_pinch_profile(path, profile):
    profile = validate_pinch_profile(profile)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class PinchCalibration:
    def __init__(self, dominant="Right", primary="index", secondary="middle", output=DEFAULT_PROFILE):
        self.dominant, self.primary, self.secondary = dominant, primary, secondary
        self.output = Path(output)
        self.recent = deque(maxlen=30)
        self.released = []
        self.pressed_primary = []
        self.pressed_secondary = []
        self.message = "O relaxed release; P primary contact; R secondary contact; S save"
        self.live = None
        self.state = {"primary": False, "secondary": False}

    def profile(self):
        return make_profile(self.dominant, self.primary, self.secondary, self.released,
                            self.pressed_primary, self.pressed_secondary)

    def process(self, ctx):
        import cv2
        height, width = ctx.frame.shape[:2]
        hand = ctx.hands.get(self.dominant)
        self.live = selected_distances(hand.points, self.primary, self.secondary, width, height) if hand else None
        if self.live is None:
            self.recent.clear()
            self.state = {"primary": False, "secondary": False}
        else:
            self.recent.append((ctx.now, self.live))
        if ctx.key in (ord("o"), ord("p"), ord("r")):
            samples = [v for t, v in self.recent if ctx.now - t <= .8]
            if len(samples) < 8:
                self.message = "Need 8+ fresh observations; hold the comfortable state briefly"
            elif ctx.key == ord("o"):
                self.released = samples
                self.message = "Released state captured. P: primary contact; R: secondary contact"
                self.recent.clear()
            elif ctx.key == ord("p"):
                self.pressed_primary = [v[0] for v in samples]
                self.message = "Primary contact captured. O: release; R: secondary; S: save"
                self.recent.clear()
            else:
                self.pressed_secondary = [v[1] for v in samples]
                self.message = "Secondary contact captured. O: release; P: primary; S: save"
                self.recent.clear()
        if ctx.key == ord("s"):
            try:
                save_pinch_profile(self.output, self.profile())
                self.message = "Saved personal pinch settings (no desktop output in this lab)"
                print(f"Saved pinch profile: {self.output}")
            except (OSError, ValueError) as exc:
                self.message = str(exc)
        try:
            profile = self.profile()
        except ValueError:
            profile = None
        if profile and self.live:
            for index, label in enumerate(("primary", "secondary")):
                threshold = profile[label + ("_off" if self.state[label] else "_on")]
                self.state[label] = self.live[index] < threshold
        if hand:
            for label, tip in {"thumb": 4, **FINGERS}.items():
                px = round(hand.points[tip][0] * width)
                py = round(hand.points[tip][1] * height)
                role = "anchor" if label == "thumb" else "PRIMARY" if label == self.primary else "SECONDARY" if label == self.secondary else "unused"
                color = (0, 220, 255) if role != "unused" else (130, 130, 130)
                cv2.circle(ctx.frame, (px, py), 6, color, 2)
                cv2.putText(ctx.frame, f"{label}: {role}", (px + 7, py + 4), cv2.FONT_HERSHEY_SIMPLEX, .38, color, 1)
        live = "Hand missing; move into view" if self.live is None else f"{self.primary}: {self.live[0]:.3f} | {self.secondary}: {self.live[1]:.3f}"
        state = f"Release:{bool(self.released)} Primary:{bool(self.pressed_primary)} Secondary:{bool(self.pressed_secondary)}"
        lines = [f"PERSONAL PINCH LAB | {self.dominant} hand | no desktop output", live,
                 "O: comfortable release | P: primary | R: secondary | S: save", self.message, state]
        if profile:
            lines.append("Calibrated preview: " + ", ".join(f"{k}={'ON' if v else 'off'}" for k, v in self.state.items()))
        cv2.rectangle(ctx.frame, (0, 0), (width, len(lines) * 23 + 12), (20, 20, 20), -1)
        for i, line in enumerate(lines):
            cv2.putText(ctx.frame, line[:100], (9, 22 + i * 23), cv2.FONT_HERSHEY_SIMPLEX, .41, (235, 235, 235), 1)
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--dominant", choices=("Left", "Right"), default="Right", type=str.title)
    parser.add_argument("--primary-finger", choices=tuple(FINGERS), default="index")
    parser.add_argument("--secondary-finger", choices=tuple(FINGERS), default="middle")
    parser.add_argument("--output", type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args(argv)
    if args.primary_finger == args.secondary_finger:
        parser.error("Primary and secondary fingers must be different")
    from .runtime import run
    return run(PinchCalibration(args.dominant, args.primary_finger, args.secondary_finger, args.output),
               camera=args.camera, title="Personal pinch calibration")
