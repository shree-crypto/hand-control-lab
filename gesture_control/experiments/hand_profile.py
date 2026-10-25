# SPDX-License-Identifier: GPL-3.0-only
"""Local per-finger calibration without assumptions about fingertip length."""
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
from statistics import median

FINGERS = {"thumb": (4, 2), "index": (8, 5), "middle": (12, 9),
           "ring": (16, 13), "pinky": (20, 17)}
MIN_MOVEMENT = .015


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _xy(points, index):
    try:
        point = points[index]
        if len(point) >= 2 and all(_finite(v) for v in point[:2]):
            return point[0], point[1]
    except (TypeError, IndexError):
        pass
    return None


def measure(hand, finger):
    """Relative vertical position of ONE chosen tip to its own MCP.

    Wrist and at least two valid MCP anchors establish a median palm scale.
    Other fingertips are never inspected; shortened/missing excluded digits do
    not invalidate the chosen finger. No straight-finger or open-palm test.
    """
    if finger not in FINGERS:
        return None
    points = getattr(hand, "points", ())
    wrist = _xy(points, 0)
    tip = _xy(points, FINGERS[finger][0])
    mcp = _xy(points, FINGERS[finger][1])
    if wrist is None or tip is None or mcp is None:
        return None
    scales = []
    for index in (5, 9, 13, 17):
        anchor = _xy(points, index)
        if anchor is not None:
            scale = math.dist(wrist, anchor)
            if scale > .005:
                scales.append(scale)
    if len(scales) < 2:
        return None
    value = (tip[1] - mcp[1]) / median(scales)
    return value if math.isfinite(value) and abs(value) <= 20 else None


@dataclass
class Binding:
    hand: str
    finger: str
    note: int
    label: str
    rest: float | None = None
    pressed: float | None = None
    min_speed: float = .10
    cooldown: float = .12
    enabled: bool = True

    def __post_init__(self):
        self.validate()

    @property
    def calibrated(self):
        return (self.rest is not None and self.pressed is not None
                and _finite(self.rest) and _finite(self.pressed)
                and abs(self.pressed - self.rest) >= MIN_MOVEMENT)

    def validate(self):
        if self.hand not in ("Left", "Right") or self.finger not in FINGERS:
            raise ValueError("Binding requires Left/Right and a recognized finger")
        if isinstance(self.note, bool) or not isinstance(self.note, int) or not 0 <= self.note <= 127:
            raise ValueError("MIDI note must be an integer from 0 to 127")
        if not isinstance(self.label, str) or not 1 <= len(self.label) <= 48 or any(ord(c) < 32 for c in self.label):
            raise ValueError("Binding label must be 1-48 printable characters")
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be boolean")
        if not _finite(self.min_speed) or not .001 <= self.min_speed <= 20:
            raise ValueError("min_speed must be .001..20 palm units per second")
        if not _finite(self.cooldown) or not .03 <= self.cooldown <= 5:
            raise ValueError("cooldown must be .03..5 seconds")
        if (self.rest is None) != (self.pressed is None):
            raise ValueError("rest and pressed must both be provided or both unset")
        if self.rest is not None:
            if not all(_finite(v) and abs(v) <= 20 for v in (self.rest, self.pressed)):
                raise ValueError("Calibration values must be finite and within -20..20")
            if not self.calibrated:
                raise ValueError("Calibration needs measurable movement (at least .015 palm units)")

    def calibrate(self, rest, pressed):
        # Validate a candidate before changing the existing usable calibration.
        candidate = Binding(self.hand, self.finger, self.note, self.label,
                            rest, pressed, self.min_speed, self.cooldown, self.enabled)
        self.rest, self.pressed = candidate.rest, candidate.pressed


@dataclass
class HandProfile:
    bindings: list[Binding] = field(default_factory=list)

    def __post_init__(self):
        self.validate()

    def validate(self):
        if not isinstance(self.bindings, list) or len(self.bindings) > 10:
            raise ValueError("A profile contains at most ten finger bindings")
        identities = set()
        for binding in self.bindings:
            if not isinstance(binding, Binding):
                raise ValueError("Expected Binding entries")
            binding.validate()
            identity = (binding.hand, binding.finger)
            if identity in identities:
                raise ValueError("Duplicate hand/finger binding")
            identities.add(identity)

    @classmethod
    def default(cls):
        """Provisional accessible four-finger map; each needs user calibration."""
        return cls([Binding("Left", "ring", 36, "Kick"),
                    Binding("Left", "pinky", 38, "Snare"),
                    Binding("Right", "index", 42, "Closed hi-hat"),
                    Binding("Right", "middle", 46, "Open hi-hat")])

    def save(self, path):
        self.validate()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps({"version": 1, "bindings": [asdict(b) for b in self.bindings]},
                          indent=2, allow_nan=False)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(data, encoding="utf-8")
        temporary.replace(target)

    @classmethod
    def load(cls, path):
        source = Path(path)
        if source.stat().st_size > 64_000:
            raise ValueError("Profile exceeds 64 KB")
        raw = json.loads(source.read_text(encoding="utf-8"))
        if (not isinstance(raw, dict) or set(raw) != {"version", "bindings"}
                or type(raw["version"]) is not int or raw["version"] != 1
                or not isinstance(raw["bindings"], list) or len(raw["bindings"]) > 10):
            raise ValueError("Invalid hand profile format")
        required = {"hand", "finger", "note", "label", "rest", "pressed", "min_speed", "cooldown", "enabled"}
        bindings = []
        for entry in raw["bindings"]:
            if not isinstance(entry, dict) or set(entry) != required:
                raise ValueError("Invalid binding fields")
            bindings.append(Binding(**entry))
        return cls(bindings)
