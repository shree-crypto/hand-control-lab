# SPDX-License-Identifier: GPL-3.0-only
"""Camera-independent, clutched air-drum strikes for four horizontal MIDI pads.

Image coordinates increase downward. Strikes use palm center, not fingertips, so
an open palm or fist can play. This module does not open cameras or MIDI ports.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Hit:
    time: float
    note: int
    velocity: int
    duration: float = .08
    hand: str = ""
    pad: str = ""


@dataclass
class _Stroke:
    previous: object = None
    armed: bool = False
    last_hit: float = float("-inf")


class DrumEngine:
    """Detect one hit per downward crossing after a visible preparatory lift.

    ``notes`` maps left-to-right regions to MIDI notes. ``position(hand)`` is
    the normalized palm point the renderer should draw. ``hit_y`` and
    ``sensitivity`` may be adjusted live; use ``configure`` to clear pending
    strokes when changing settings. ``reset`` preserves no input history.
    """

    PAD_NAMES = ("Kick", "Snare", "Closed hat", "Open hat")

    def __init__(self, notes=(36, 38, 42, 46), hit_y=.62, sensitivity=1.0,
                 cooldown=.12, lift=.10, min_speed=.65, max_gap=.20,
                 max_step=.35):
        if len(notes) != 4 or any(isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= 127 for n in notes):
            raise ValueError("notes must contain four integer MIDI notes from 0 to 127")
        self.notes = tuple(notes)
        self.cooldown = self._positive(cooldown, "cooldown")
        self.lift = self._positive(lift, "lift")
        self.min_speed = self._positive(min_speed, "min_speed")
        self.max_gap = self._positive(max_gap, "max_gap")
        self.max_step = self._positive(max_step, "max_step")
        self.strokes = {}
        self.configure(hit_y=hit_y, sensitivity=sensitivity)

    @staticmethod
    def _positive(value, name):
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(name + " must be finite and positive")
        return value

    def configure(self, *, hit_y=None, sensitivity=None):
        plane = self.hit_y if hit_y is None and hasattr(self, "hit_y") else hit_y
        gain = self.sensitivity if sensitivity is None and hasattr(self, "sensitivity") else sensitivity
        if plane is None or not math.isfinite(float(plane)) or not self.lift < float(plane) < .95:
            raise ValueError("hit_y must satisfy lift < hit_y < .95 in normalized image space")
        gain = self._positive(gain, "sensitivity")
        self.hit_y = float(plane)
        self.sensitivity = gain
        self.reset()

    def reset(self):
        self.strokes.clear()

    @staticmethod
    def position(hand):
        """Return mean wrist/MCP palm center, or None for malformed landmarks.

        Drawing this same point avoids a visual fingertip crossing that the
        detector cannot see. Five landmarks (0,5,9,13,17) resist finger motion.
        """
        try:
            points = hand.points
            if len(points) != 21:
                return None
            palm = [points[i] for i in (0, 5, 9, 13, 17)]
            if not all(len(p) >= 2 and all(math.isfinite(float(v)) for v in p[:2]) for p in palm):
                return None
            x = sum(float(p[0]) for p in palm) / len(palm)
            y = sum(float(p[1]) for p in palm) / len(palm)
            if not (0 <= x <= 1 and 0 <= y <= 1):
                return None
            return x, y
        except (AttributeError, TypeError, IndexError, ValueError, OverflowError):
            return None

    def update(self, hands, now):
        """Return ordered Hit events for independently tracked left/right hands.

        No hit occurs on acquisition, invalid time, a gap above max_gap, or an
        implausibly large step. Only predominantly downward plane crossings
        count. Below-plane dwell, jitter and shallow rebounds cannot repeat.
        """
        if not math.isfinite(now):
            self.reset()
            return []
        hits = []
        for label in ("Left", "Right"):
            state = self.strokes.setdefault(label, _Stroke())
            current = self.position(hands[label]) if label in hands else None
            if current is None:
                state.previous = None
                state.armed = False
                continue
            x, y = current
            previous = state.previous
            state.previous = (x, y, now)
            if previous is None:
                state.armed = y <= self.hit_y - self.lift
                continue
            px, py, then = previous
            dt = now - then
            dx, dy = x - px, y - py
            if dt <= 0 or dt > self.max_gap or math.hypot(dx, dy) > self.max_step:
                # This sample becomes the next baseline, never a strike itself.
                state.armed = y <= self.hit_y - self.lift
                continue
            if y <= self.hit_y - self.lift:
                state.armed = True
            crossed = py < self.hit_y <= y
            if not crossed:
                continue
            was_armed = state.armed
            state.armed = False
            speed = dy / dt
            downward = dy > 0 and dy >= abs(dx) * .7
            if not was_armed or not downward or speed * self.sensitivity < self.min_speed:
                continue
            ratio = (self.hit_y - py) / dy
            strike_time = then + ratio * dt
            if strike_time - state.last_hit < self.cooldown:
                continue
            strike_x = px + ratio * dx
            pad_index = min(3, max(0, int(strike_x * 4)))
            velocity = max(1, min(127, round(speed * self.sensitivity * 127 / 4)))
            hits.append(Hit(strike_time, self.notes[pad_index], velocity,
                            hand=label, pad=self.PAD_NAMES[pad_index]))
            state.last_hit = strike_time
        return sorted(hits, key=lambda hit: (hit.time, hit.hand))


# Short alias for integrations that prefer Engine beside other engines.
Engine = DrumEngine


def position(hand):
    """Public palm-center helper shared by strike detection and pad rendering."""
    return DrumEngine.position(hand)
