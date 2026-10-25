# SPDX-License-Identifier: GPL-3.0-only
"""Camera-independent experimental fingertip tapping, not physical piano sensing.

Camera y grows downward. A fingertip must first be seen above the rearm plane,
then cross the hit plane downwards fast enough. Horizontal movement below the
plane cannot trigger additional notes. All fingers can hit concurrently.
"""
from dataclasses import dataclass
import math

FINGERS = {"thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20}
WHITE_INTERVALS = (0, 2, 4, 5, 7, 9, 11, 12)


@dataclass(frozen=True)
class Hit:
    time: float
    note: int
    velocity: int
    duration: float = .25
    hand: str = ""
    finger: str = ""


@dataclass
class _FingerState:
    x: float
    y: float
    time: float
    armed: bool
    last_hit: float = -math.inf


def positions(hand):
    """Return finite in-frame fingertip coordinates keyed by finger name.

    Accepts runtime.HandData by structural typing; no runtime, camera or NumPy
    imports are needed. Invalid/out-of-view fingertips are omitted.
    """
    points = getattr(hand, "points", ())
    if len(points) != 21:
        return {}
    result = {}
    for name, index in FINGERS.items():
        point = points[index]
        if len(point) < 2:
            continue
        x, y = point[0], point[1]
        if (isinstance(x, (int, float)) and isinstance(y, (int, float))
                and math.isfinite(x) and math.isfinite(y)
                and 0 <= x <= 1 and 0 <= y <= 1):
            result[name] = (float(x), float(y))
    return result


class PianoEngine:
    """Eight-key C-major screen keyboard with independent per-finger triggers.

    sensitivity in [.25, 4] is an inverse speed threshold: larger is easier.
    base_note in [0, 115] keeps the upper octave within MIDI's 0..127 bounds.
    A frame gap over .25 s resets the affected finger's trajectory.
    """
    def __init__(self, hit_y=.62, sensitivity=1.0, base_note=60, include_thumb=True, enabled_fingers=None):
        if not isinstance(hit_y, (int, float)) or not math.isfinite(hit_y) or not .1 <= hit_y <= .9:
            raise ValueError("hit_y must be finite and between .1 and .9")
        if not isinstance(sensitivity, (int, float)) or not math.isfinite(sensitivity) or not .25 <= sensitivity <= 4:
            raise ValueError("sensitivity must be between .25 and 4")
        if isinstance(base_note, bool) or not isinstance(base_note, int) or not 0 <= base_note <= 115:
            raise ValueError("base_note must be an integer between 0 and 115")
        self.hit_y = float(hit_y)
        self.rearm_y = self.hit_y - .07
        self.sensitivity = float(sensitivity)
        self.base_note = base_note
        self.notes = tuple(base_note + interval for interval in WHITE_INTERVALS)
        self.include_thumb = include_thumb
        self.enabled_fingers = enabled_fingers
        self.min_speed = .65 / self.sensitivity
        self.cooldown = .15
        self.max_frame_gap = .25
        self.max_step = .35
        self._states = {}

    def positions(self, hand):
        result = positions(hand)
        if not self.include_thumb:
            result.pop("thumb", None)
        return result

    def note_at(self, x):
        """Map x=0..1 to 8 white notes; out-of-screen coordinates are rejected."""
        if not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1:
            return None
        key = min(7, int(x * 8))
        return self.notes[key]

    def reset(self):
        self._states.clear()

    def update(self, hands, now):
        if not isinstance(now, (int, float)) or not math.isfinite(now):
            self.reset()
            return []
        seen = set()
        hits = []
        for hand_name, hand in hands.items():
            for finger, (x, y) in self.positions(hand).items():
                if self.enabled_fingers is not None and finger not in self.enabled_fingers.get(hand_name,set()):
                    continue
                identity = (hand_name, finger)
                seen.add(identity)
                state = self._states.get(identity)
                if state is None or not 0 < now - state.time <= self.max_frame_gap:
                    # First observation can prepare a lift but never plays a note.
                    self._states[identity] = _FingerState(x, y, now, y <= self.rearm_y)
                    continue
                dt = now - state.time
                dy = y - state.y
                dx = x - state.x
                if math.hypot(dx, dy) > self.max_step:
                    self._states[identity] = _FingerState(x, y, now, y <= self.rearm_y)
                    continue
                crossed = state.y < self.hit_y <= y
                if y <= self.rearm_y:
                    state.armed = True
                if crossed:
                    # Any crossing consumes the arm, including slow/sideways ones.
                    # A new lift is needed before another intentional tap attempt.
                    if (state.armed and now - state.last_hit >= self.cooldown
                            and dy / dt >= self.min_speed
                            and dy >= abs(dx) * 1.2 and abs(dx) <= .08):
                        speed = dy / dt
                        velocity = max(1, min(127, round(30 + speed * 35)))
                        fraction = (self.hit_y - state.y) / dy
                        strike_time = state.time + fraction * dt
                        strike_x = state.x + fraction * dx
                        hits.append(Hit(strike_time, self.note_at(strike_x), velocity,
                                        hand=str(hand_name), finger=finger))
                        state.last_hit = now
                    state.armed = False
                state.x, state.y, state.time = x, y, now
        # Loss of a hand or even a single invalid fingertip cancels its trajectory.
        self._states = {identity: state for identity, state in self._states.items() if identity in seen}
        return sorted(hits, key=lambda hit: (hit.time, hit.hand, hit.finger))
