# SPDX-License-Identifier: GPL-3.0-only
"""Sandbox command wheel and local static-pose recorder (no OS actions)."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import time
import uuid

LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,31}$")
MAX_SAMPLES = 5000
MAX_BYTES = 8_000_000
COMMANDS = ("Orbit", "Pan", "Zoom", "Brush", "Undo", "Palette")


def normalize(points):
    """Translation/scale-normalized 21-point pose; orientation is preserved."""
    if len(points) != 21 or any(len(p) != 3 for p in points):
        raise ValueError("Expected 21 xyz landmarks")
    if any(not math.isfinite(v) for p in points for v in p):
        raise ValueError("Landmarks must be finite")
    origin = points[0]
    scale = math.dist(points[0], points[9])
    if scale < 1e-6:
        raise ValueError("Palm scale is too small")
    return [(v - o) / scale for p in points for v, o in zip(p, origin)]


def valid_feature(feature):
    return (isinstance(feature, list) and len(feature) == 63
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) and abs(v) <= 50 for v in feature))


def rms(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / len(a))


class PoseStore:
    def __init__(self, path):
        self.path = Path(path)
        self.samples = []
        self.session = uuid.uuid4().hex[:12]

    def load(self):
        if not self.path.exists():
            return
        if self.path.stat().st_size > MAX_BYTES:
            raise ValueError("Pose file exceeds 8 MB")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("Unknown pose file format")
        samples = data.get("samples")
        if not isinstance(samples, list) or len(samples) > MAX_SAMPLES:
            raise ValueError("Invalid sample collection")
        for sample in samples:
            if (not isinstance(sample, dict) or not isinstance(sample.get("label"), str)
                    or not LABEL.fullmatch(sample["label"])
                    or not valid_feature(sample.get("feature"))
                    or not isinstance(sample.get("session"), str)
                    or len(sample["session"]) > 64):
                raise ValueError("Invalid pose sample")
        self.samples = samples

    def add(self, label, feature):
        if not LABEL.fullmatch(label) or not valid_feature(feature):
            raise ValueError("Invalid label or landmark features")
        if len(self.samples) >= MAX_SAMPLES:
            raise ValueError("Sample limit reached (5000)")
        self.samples.append({"label": label, "feature": feature, "session": self.session})

    def save(self):
        encoded = json.dumps({"version": 1, "samples": self.samples}, allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_BYTES:
            raise ValueError("Pose collection exceeds size limit")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(self.path)


class PoseClassifier:
    def __init__(self, samples):
        groups = defaultdict(list)
        for sample in samples:
            groups[sample["label"]].append(sample["feature"])
        if len(groups) < 2 or any(len(g) < 3 for g in groups.values()):
            raise ValueError("Record at least 3 samples for each of 2 or more labels")
        self.models = {}
        for label, features in groups.items():
            center = [sum(column) / len(features) for column in zip(*features)]
            radius = min(.55, max(.08, max(rms(f, center) for f in features) * 2))
            self.models[label] = (center, radius)

    def predict(self, feature):
        if not valid_feature(feature):
            return "Unknown"
        ranked = sorted((rms(feature, center), label, radius)
                        for label, (center, radius) in self.models.items())
        distance, label, radius = ranked[0]
        # Reject distant or ambiguous poses rather than forcing every frame to a label.
        if distance > radius or (len(ranked) > 1 and ranked[1][0] - distance < .025):
            return "Unknown"
        return label


class PinchEdge:
    """Release is required before first action or after tracking loss."""
    def __init__(self):
        self.held = True

    def update(self, distance):
        if distance is None:
            self.held = True
            return False
        active = distance < (.48 if self.held else .30)
        edge = active and not self.held
        self.held = active
        return edge


def open_palm(points):
    if len(points) != 21:
        return False
    return all(math.dist(points[tip], points[0]) > math.dist(points[pip], points[0]) * 1.15
               for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)))


def wheel_segment(x, y):
    dx, dy = x - .5, y - .55
    if math.hypot(dx, dy) < .10:
        return None
    return int((math.atan2(dy, dx) % (2 * math.pi)) / (2 * math.pi) * len(COMMANDS))


class GestureLab:
    def __init__(self, store, label, record=False):
        self.store = store
        self.label = label
        self.record = record
        self.model = None
        self.edge = PinchEdge()
        self.palm_since = None
        self.message = "Sandbox only: commands never control Windows"
        self.prediction = "Untrained"
        self.last_record = -math.inf

    def process(self, ctx):
        import cv2
        frame = ctx.frame
        height, width = frame.shape[:2]
        right, left = ctx.hands.get("Right"), ctx.hands.get("Left")
        feature = None
        if right:
            try:
                feature = normalize(right.points)
            except ValueError:
                pass
        if self.model and feature:
            self.prediction = self.model.predict(feature)
        elif not right:
            self.prediction = "Hand missing"
        if ctx.key in (ord("r"), ord("R")) and self.record:
            if feature and ctx.now - self.last_record > .25:
                try:
                    self.store.add(self.label, feature)
                    self.store.save()
                    self.last_record = ctx.now
                    self.message = f"Saved pose '{self.label}' ({len(self.store.samples)} total)"
                except (ValueError, OSError) as exc:
                    self.message = str(exc)
            else:
                self.message = "Show your right hand before recording"
        if ctx.key in (ord("t"), ord("T")):
            try:
                self.model = PoseClassifier(self.store.samples)
                self.message = "Classifier ready; accuracy has not been evaluated"
            except ValueError as exc:
                self.message = str(exc)
        palm = left and open_palm(left.points)
        if not palm:
            self.palm_since = None
        elif self.palm_since is None:
            self.palm_since = ctx.now
        visible = self.palm_since is not None and ctx.now - self.palm_since >= .35
        click = self.edge.update(right.pinch if right else None)
        selected = wheel_segment(right.x, right.y) if visible and right else None
        if visible:
            center = (int(width * .5), int(height * .55))
            radius = int(min(width, height) * .29)
            cv2.circle(frame, center, radius, (130, 130, 130), 2)
            for i, command in enumerate(COMMANDS):
                angle = (i + .5) * 2 * math.pi / len(COMMANDS)
                px = int(center[0] + math.cos(angle) * radius)
                py = int(center[1] + math.sin(angle) * radius)
                color = (0, 240, 255) if i == selected else (230, 230, 230)
                cv2.putText(frame, command, (px - 30, py), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 2)
            if click and selected is not None:
                self.message = f"Sandbox command: {COMMANDS[selected]}"
        lines = ["COMMAND WHEEL / STATIC POSE LAB",
                 "Hold left palm open; point right hand and pinch to choose",
                 f"Pose: {self.prediction} | Samples: {len(self.store.samples)}",
                 f"R: save '{self.label}' | T: train | Esc/Q: quit" if self.record else "T: train saved poses | Esc/Q: quit",
                 self.message]
        cv2.rectangle(frame, (0, 0), (width, 138), (22, 22, 22), -1)
        for i, line in enumerate(lines):
            cv2.putText(frame, line[:90], (10, 23 + i * 25), cv2.FONT_HERSHEY_SIMPLEX, .45, (235, 235, 235), 1)
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--record", action="store_true", help="Enable explicit R-key sample recording")
    parser.add_argument("--label", default="open-palm", help="Static pose name; restart with a new label for another class")
    parser.add_argument("--data", type=Path, default=Path.home() / ".hand-control" / "poses.json")
    args = parser.parse_args(argv)
    if not LABEL.fullmatch(args.label):
        parser.error("Label must be 1-32 letters, numbers, spaces, underscores or hyphens; start with letter/number")
    store = PoseStore(args.data)
    try:
        store.load()
    except (ValueError, OSError) as exc:
        parser.error(f"Cannot load pose samples: {exc}")
    from .runtime import run
    return run(GestureLab(store, args.label, args.record), camera=args.camera,
               title="Gesture command wheel and pose recorder")


if __name__ == "__main__":
    raise SystemExit(main())
