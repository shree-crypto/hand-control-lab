# SPDX-License-Identifier: GPL-3.0-only
"""Calibrated facial-expression playground, with no desktop output."""
import argparse
from math import atan2, degrees, hypot, isfinite


def measurements(face, width=640, height=480):
    if face is None or len(face) < 468:
        return None
    face = [(p[0] * width, p[1] * height, p[2]) for p in face]
    if not all(all(isfinite(v) for v in p) for p in face):
        return None
    def dist(a, b):
        return hypot(face[a][0] - face[b][0], face[a][1] - face[b][1])
    scale = dist(10, 152)
    if scale < 5:
        return None
    return {
        "brow": (dist(105, 159) + dist(334, 386)) / (2 * scale),
        "mouth": dist(13, 14) / max(dist(61, 291), 1),
        "tilt": degrees(atan2(face[263][1] - face[33][1], face[263][0] - face[33][0])),
    }


class Hold:
    def __init__(self):
        self.since = None
        self.fired = False

    def update(self, active, now):
        if not active:
            self.since, self.fired = None, False
            return False
        if self.since is None:
            self.since = now
        if now - self.since >= .5 and not self.fired:
            self.fired = True
            return True
        return False


class FaceLab:
    def __init__(self):
        self.baseline = None
        self.holds = {"brow": Hold(), "mouth": Hold()}
        self.event = "C: calibrate with a relaxed face"
        self.count = 0

    def process(self, ctx):
        import cv2
        height, width = ctx.frame.shape[:2]
        values = measurements(ctx.face, width, height)
        if ctx.key == ord("c") and values:
            self.baseline = values
            self.event = "Calibrated - raise brows or open mouth and hold"
            self.holds = {"brow": Hold(), "mouth": Hold()}
        active = {}
        if values and self.baseline:
            active = {"brow": values["brow"] > self.baseline["brow"] * 1.3 + .005,
                      "mouth": values["mouth"] > max(.25, self.baseline["mouth"] + .15)}
        for name, hold in self.holds.items():
            if hold.update(active.get(name, False), ctx.now):
                self.count += 1
                self.event = f"{name.upper()} event #{self.count} (sandbox only)"
        height, width = ctx.frame.shape[:2]
        if ctx.face:
            for i in (13, 14, 33, 61, 105, 159, 263, 291, 334, 386):
                x, y, _ = ctx.face[i]
                cv2.circle(ctx.frame, (round(x * width), round(y * height)), 3, (60, 230, 200), -1)
        cv2.rectangle(ctx.frame, (0, 0), (width, 100), (24, 24, 24), -1)
        lines = ["FACE PLAYGROUND | C calibrate | Q/Esc quit", self.event,
                 f"Head tilt: {values['tilt']:.1f} deg" if values else "Face missing - gestures reset"]
        for i, line in enumerate(lines):
            cv2.putText(ctx.frame, line, (12, 25 + 28 * i), cv2.FONT_HERSHEY_SIMPLEX, .5, (235, 235, 235), 1)
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args(argv)
    from .runtime import run
    return run(FaceLab(), camera=args.camera, with_face=True, title="Face expressions")
