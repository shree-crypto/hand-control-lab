# SPDX-License-Identifier: GPL-3.0-only
"""A two-hand cube sandbox. No desktop input or physical-depth measurement."""
import argparse
from dataclasses import dataclass
import math


def clamp(value, low, high):
    return max(low, min(high, value))


def project(point, eye=(0.0, 0.0, 4.0)):
    """Intersect eye-to-point ray with z=0 display plane; units are virtual."""
    x, y, z = point
    ex, ey, ez = eye
    if not all(math.isfinite(v) for v in (*point, *eye)) or ez <= 0:
        return None
    distance = ez - z
    if distance < 0.1:
        return None
    factor = ez / distance
    return ex + (x - ex) * factor, ey + (y - ey) * factor


@dataclass
class Transform:
    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0
    roll: float = 0.0


class Controller:
    """Clutched relative manipulation. Every change in hand set reanchors."""
    def __init__(self):
        self.transform = Transform()
        self.gates = {}
        self.mode = ()
        self.anchor = None
        self.saved = Transform()
        self.status = "Pinch one hand to move; pinch both to scale/rotate"

    def reset(self):
        self.__init__()

    def update(self, hands):
        active = {}
        for label in ("Left", "Right"):
            hand = hands.get(label)
            if hand is None or not all(math.isfinite(v) for v in (hand.x, hand.y, hand.pinch)):
                self.gates[label] = False
                continue
            pinched = hand.pinch < (0.48 if self.gates.get(label, False) else 0.30)
            self.gates[label] = pinched
            if pinched:
                active[label] = (hand.x, hand.y)
        mode = tuple(sorted(active))
        if not mode:
            self.mode = ()
            self.anchor = None
            self.status = "REST - pinch to grab"
            return self.transform
        if len(mode) == 2:
            left, right = active["Left"], active["Right"]
            midpoint = ((left[0] + right[0]) / 2, (left[1] + right[1]) / 2)
            dx, dy = right[0] - left[0], right[1] - left[1]
            span = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)
            sample = (*midpoint, span, angle)
        else:
            sample = (*active[mode[0]], 1.0, 0.0)
        if mode != self.mode or self.anchor is None:
            self.mode = mode
            self.anchor = sample
            self.saved = Transform(**vars(self.transform))
            self.status = "GRABBED - move gently"
            return self.transform
        self.transform.x = clamp(self.saved.x + (sample[0] - self.anchor[0]) * 4, -2, 2)
        self.transform.y = clamp(self.saved.y - (sample[1] - self.anchor[1]) * 4, -1.5, 1.5)
        if len(mode) == 2:
            # Very small separation has no stable angle or scale interpretation.
            if self.anchor[2] > .04 and sample[2] > .04:
                self.transform.scale = clamp(self.saved.scale * sample[2] / self.anchor[2], .2, 2.5)
                delta = math.atan2(math.sin(sample[3] - self.anchor[3]), math.cos(sample[3] - self.anchor[3]))
                self.transform.roll = self.saved.roll - delta
            self.status = "TWO HANDS - move / spread / rotate connecting line"
        else:
            self.status = "ONE HAND - move; release pinch to rest"
        return self.transform


def cube_points(transform):
    """Fixed tilted cube with interactive translation, scale and screen roll."""
    points = []
    ca, sa = math.cos(.55), math.sin(.55)
    cb, sb = math.cos(.35), math.sin(.35)
    cr, sr = math.cos(transform.roll), math.sin(transform.roll)
    for x, y, z in ((-.6, -.6, -.6), (.6, -.6, -.6), (.6, .6, -.6), (-.6, .6, -.6),
                    (-.6, -.6, .6), (.6, -.6, .6), (.6, .6, .6), (-.6, .6, .6)):
        x, z = ca * x + sa * z, -sa * x + ca * z
        y, z = cb * y - sb * z, sb * y + cb * z
        x, y = cr * x - sr * y, sr * x + cr * y
        points.append((x * transform.scale + transform.x,
                       y * transform.scale + transform.y,
                       z * transform.scale - 2.5))
    return points


class Workbench:
    def __init__(self, head=False):
        self.controller = Controller()
        self.head = head
        self.eye = (0.0, 0.0, 4.0)

    def process(self, ctx):
        import cv2
        if ctx.key in (ord("r"), ord("R")):
            self.controller.reset()
            self.eye = (0.0, 0.0, 4.0)
        transform = self.controller.update(ctx.hands)
        target = (0.0, 0.0, 4.0)
        tracked = False
        if self.head and ctx.face and len(ctx.face) > 263:
            a, b = ctx.face[33], ctx.face[263]
            if all(math.isfinite(v) for v in (*a[:2], *b[:2])):
                target = (clamp(((a[0] + b[0]) / 2 - .5) * 3, -.8, .8),
                          clamp((.5 - (a[1] + b[1]) / 2) * 3, -.6, .6), 4.0)
                tracked = True
        self.eye = tuple(old * .8 + new * .2 for old, new in zip(self.eye, target))
        frame = ctx.frame
        frame[:] = (frame * .20).astype(frame.dtype)
        height, width = frame.shape[:2]
        pixels = []
        unit = min(width, height) * .31
        for point in cube_points(transform):
            screen = project(point, self.eye)
            pixels.append(None if screen is None else (round(width / 2 + screen[0] * unit), round(height / 2 - screen[1] * unit)))
        edges = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                 (0, 4), (1, 5), (2, 6), (3, 7))
        for i, (a, b) in enumerate(edges):
            if pixels[a] is not None and pixels[b] is not None:
                cv2.line(frame, pixels[a], pixels[b], (100, 220, 255) if i < 4 else (210, 150, 90), 3, cv2.LINE_AA)
        for label, hand in ctx.hands.items():
            color = (80, 240, 140) if self.controller.gates.get(label) else (160, 160, 160)
            center = (int(hand.x * width), int(hand.y * height))
            cv2.circle(frame, center, 10, color, 2)
            cv2.putText(frame, label, (center[0] + 12, center[1]), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
        lines = ["3D SANDBOX | R: reset | Esc/Q: exit",
                 self.controller.status,
                 f"Scale: {transform.scale:.2f} | virtual units, no measured depth"]
        if self.head:
            lines.append("Head parallax: " + ("tracking" if tracked else "face missing - returning to center"))
            lines.append("Approximate uncalibrated eye position; one-viewer effect")
        for i, line in enumerate(lines):
            cv2.putText(frame, line, (12, 24 + i * 23), cv2.FONT_HERSHEY_SIMPLEX, .49, (240, 240, 240), 1)
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Two-hand cube manipulation sandbox; never sends OS input.")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--head", action="store_true", help="Add approximate head-coupled off-axis perspective (face model required)")
    args = parser.parse_args(argv)
    from .runtime import run
    return run(Workbench(args.head), camera=args.camera, with_face=args.head, title="Two-hand 3D workbench")


if __name__ == "__main__":
    raise SystemExit(main())
