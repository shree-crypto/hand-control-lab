# SPDX-License-Identifier: GPL-3.0-only
"""Calibrated gaze playground. Never emits desktop mouse events."""
import argparse
from collections import deque
from math import hypot, isfinite, sqrt


def distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])


def extract_features(face, width=640, height=480):
    """Iris position relative to each eye, head geometry, and eye openness.

    Returns (feature tuple, mean eye-aspect ratio), or None for unusable geometry.
    Landmarker iris centers are 468 and 473; this is not nose-only tracking.
    """
    if face is None or len(face) < 478:
        return None
    p = [(v[0] * width, v[1] * height) for v in face]
    if not all(isfinite(v) for point in p for v in point):
        return None
    features = []
    openness = []
    centers = []
    for outer, inner, upper, lower, iris in ((33, 133, 159, 145, 468), (362, 263, 386, 374, 473)):
        a, b = p[outer], p[inner]
        length = distance(a, b)
        if length < 3:
            return None
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        center = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        dx, dy = p[iris][0] - center[0], p[iris][1] - center[1]
        features.extend(((dx * ux + dy * uy) / length, (-dx * uy + dy * ux) / length))
        openness.append(distance(p[upper], p[lower]) / length)
        centers.append(center)
    eye_span = distance(*centers)
    if eye_span < 5:
        return None
    cx = (centers[0][0] + centers[1][0]) / 2
    cy = (centers[0][1] + centers[1][1]) / 2
    features.extend(((p[1][0] - cx) / eye_span, (p[1][1] - cy) / eye_span,
                     cx / width, cy / height))
    return tuple(features), sum(openness) / 2


def solve(matrix, values):
    """Pivoted Gaussian elimination for the small regularized calibration fit."""
    rows = [list(row) + [value] for row, value in zip(matrix, values)]
    n = len(rows)
    for col in range(n):
        pivot = max(range(col, n), key=lambda i: abs(rows[i][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise ValueError("Calibration is singular; vary your gaze and retry")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        divisor = rows[col][col]
        rows[col] = [v / divisor for v in rows[col]]
        for row in range(n):
            if row != col:
                scale = rows[row][col]
                rows[row] = [a - scale * b for a, b in zip(rows[row], rows[col])]
    return [row[-1] for row in rows]


class Calibration:
    def __init__(self, regularization=0.15):
        self.regularization = regularization
        self.weights = None
        self.means = None
        self.scales = None

    def fit(self, features, targets):
        if len(features) < 5 or len(features) != len(targets):
            raise ValueError("Need at least five matching calibration observations")
        dim = len(features[0])
        if not dim or any(len(v) != dim for v in features):
            raise ValueError("Inconsistent calibration feature dimensions")
        if not all(isfinite(v) for sample in features for v in sample):
            raise ValueError("Calibration features must be finite")
        if any(len(t) != 2 or not all(isfinite(v) for v in t) for t in targets):
            raise ValueError("Calibration targets must be finite coordinate pairs")
        self.means = [sum(v[i] for v in features) / len(features) for i in range(dim)]
        self.scales = [max(.005, sqrt(sum((v[i] - self.means[i]) ** 2 for v in features) / len(features))) for i in range(dim)]
        design = [self._design(v) for v in features]
        gram = [[sum(v[i] * v[j] for v in design) + (self.regularization if i == j and i else 0)
                 for j in range(dim + 1)] for i in range(dim + 1)]
        self.weights = [solve(gram, [sum(v[i] * t[axis] for v, t in zip(design, targets))
                                    for i in range(dim + 1)]) for axis in (0, 1)]

    def _design(self, features):
        return [1.0] + [(v - m) / s for v, m, s in zip(features, self.means, self.scales)]

    def predict(self, features):
        if self.weights is None:
            return None
        if len(features) != len(self.means) or not all(isfinite(v) for v in features):
            return None
        row = self._design(features)
        return tuple(max(0.0, min(1.0, sum(a * b for a, b in zip(row, weights)))) for weights in self.weights)


class Selection:
    """Debounced lab-only selections; natural blinks do nothing."""
    def __init__(self, mode="pinch", dwell=1.0, blink_min=.45, blink_max=1.5):
        self.mode, self.dwell = mode, dwell
        self.blink_min, self.blink_max = blink_min, blink_max
        self.reset()

    def reset(self):
        self.pinch_latched = True  # require release after tracking loss/calibration
        self.target = None
        self.since = None
        self.dwelled = False
        self.closed_since = None
        self.closed_target = None

    def update(self, now, target, closed=False, pinch=False, valid=True):
        if not valid:
            self.reset()
            return None
        if closed:
            if self.closed_since is None:
                self.closed_since = now
                self.closed_target = self.target
            self.pinch_latched = True
            self.since = None
            return None
        blink_target = None
        if self.closed_since is not None:
            duration = now - self.closed_since
            if self.blink_min <= duration <= self.blink_max:
                blink_target = self.closed_target
            self.closed_since = None
            self.closed_target = None
        if target != self.target:
            self.target, self.since, self.dwelled = target, now, False
        elif self.since is None:
            self.since = now
        if not pinch:
            self.pinch_latched = False
        if self.mode == "pinch" and pinch and not self.pinch_latched:
            self.pinch_latched = True
            return target
        if self.mode == "blink" and blink_target is not None:
            return blink_target
        if self.mode == "dwell" and target is not None and not self.dwelled and now - self.since >= self.dwell:
            self.dwelled = True
            return target
        return None


def target_at(point):
    if point is None:
        return None
    x, y = point
    # Gutters avoid selecting while gaze rests between tiles.
    col, row = min(2, int(x * 3)), min(1, int(y * 2))
    if abs(x - (col + .5) / 3) > .14 or abs(y - (row + .5) / 2) > .19:
        return None
    return row * 3 + col


class GazeLab:
    def __init__(self, mode="pinch", points=9, dwell=1.0, blink_threshold=.17):
        self.selection = Selection(mode=mode, dwell=dwell)
        self.points = ([(x, y) for y in (.2, .5, .8) for x in (.15, .5, .85)]
                       if points == 9 else [(.15, .2), (.85, .2), (.5, .5), (.15, .8), (.85, .8)])
        self.blink_threshold = blink_threshold
        self.restart()

    def restart(self):
        self.model = Calibration()
        self.samples = []
        self.recent = deque(maxlen=24)
        self.point = None
        self.selected = None
        self.selected_until = 0
        self.pinch_active = False
        self.selection.reset()
        self.message = "Look at marker; hold gaze, then SPACE to capture"

    def process(self, ctx):
        import cv2
        if ctx.key == ord("r"):
            self.restart()
        frame = ctx.frame
        height, width = frame.shape[:2]
        data = extract_features(ctx.face, width, height)
        valid = data is not None
        closed = bool(valid and data[1] < self.blink_threshold)
        if valid and not closed:
            self.recent.append((ctx.now, data[0]))
        else:
            self.recent.clear()
        calibrating = len(self.samples) < len(self.points)
        if calibrating:
            self.selection.reset()
            if ctx.key == ord(" "):
                recent = [v for t, v in self.recent if ctx.now - t < .65]
                if len(recent) < 8:
                    self.message = "Need 8+ recent open-eye frames; hold gaze and retry SPACE"
                else:
                    average = tuple(sum(v[i] for v in recent) / len(recent) for i in range(len(recent[0])))
                    self.samples.append(average)
                    self.recent.clear()
                    self.message = "Look at next marker; hold gaze, then SPACE"
                    if len(self.samples) == len(self.points):
                        self.model.fit(self.samples, self.points)
                        self.message = "Calibrated estimate - try large targets; R recalibrates"
            # Do not advance beyond target count on the completion frame.
            if len(self.samples) < len(self.points):
                target = self.points[len(self.samples)]
                center = (round(target[0] * width), round(target[1] * height))
                cv2.circle(frame, center, 20, (0, 220, 255), -1)
                cv2.circle(frame, center, 5, (0, 0, 0), -1)
            text = f"CALIBRATION {len(self.samples)}/{len(self.points)} | SPACE capture | R reset"
        else:
            if valid and not closed:
                prediction = self.model.predict(data[0])
                if prediction is not None:
                    self.point = prediction if self.point is None else tuple(a * .75 + b * .25 for a, b in zip(self.point, prediction))
            if not valid:
                self.point = None
            hand = ctx.hands.get("Right") or ctx.hands.get("Left")
            self.pinch_active = hand is not None and hand.pinch < (.48 if self.pinch_active else .30)
            pinch = self.pinch_active
            target = target_at(self.point)
            chosen = self.selection.update(ctx.now, target, closed, pinch, valid)
            if chosen is not None:
                self.selected, self.selected_until = chosen, ctx.now + .6
            for tile in range(6):
                col, row = tile % 3, tile // 3
                lo = (round((col / 3 + .025) * width), round((row / 2 + .06) * height))
                hi = (round(((col + 1) / 3 - .025) * width), round(((row + 1) / 2 - .06) * height))
                color = (80, 230, 120) if tile == self.selected and ctx.now < self.selected_until else ((0, 220, 255) if tile == target else (110, 110, 110))
                cv2.rectangle(frame, lo, hi, color, 3)
                cv2.putText(frame, str(tile + 1), (lo[0] + 10, lo[1] + 34), cv2.FONT_HERSHEY_SIMPLEX, .8, color, 2)
            if self.point:
                cv2.circle(frame, (round(self.point[0] * width), round(self.point[1] * height)), 9, (255, 100, 220), 2)
            text = f"GAZE LAB | select: {self.selection.mode} | {'EYES CLOSED' if closed else 'FACE LOST' if not valid else 'estimated gaze'}"
        cv2.rectangle(frame, (0, 0), (width, 66), (20, 20, 20), -1)
        cv2.putText(frame, text, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, .45, (235, 235, 235), 1)
        cv2.putText(frame, self.message[:88], (10, 46), cv2.FONT_HERSHEY_SIMPLEX, .40, (235, 235, 235), 1)
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Calibrated gaze playground; no desktop input")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--select", choices=("pinch", "blink", "dwell"), default="pinch")
    parser.add_argument("--points", type=int, choices=(5, 9), default=9)
    parser.add_argument("--dwell", type=float, default=1.0)
    parser.add_argument("--blink-threshold", type=float, default=.17)
    args = parser.parse_args(argv)
    if args.dwell < .4 or not .05 <= args.blink_threshold <= .4:
        parser.error("Use dwell >=0.4 seconds and blink-threshold between .05 and .4")
    from .runtime import run
    return run(GazeLab(args.select, args.points, args.dwell, args.blink_threshold),
               camera=args.camera, with_face=True, title="Gaze lab - sandbox only")
