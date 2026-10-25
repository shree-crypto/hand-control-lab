# SPDX-License-Identifier: GPL-3.0-only
"""Independent calibrated finger taps; selected digits need no standard shape."""
from dataclasses import dataclass
import math

from .hand_profile import measure


@dataclass(frozen=True)
class Hit:
    time: float
    note: int
    velocity: int
    duration: float = .08
    hand: str = ""
    finger: str = ""
    label: str = ""


@dataclass
class _State:
    value: float
    time: float
    armed: bool
    last_hit: float = -math.inf
    calibration: tuple = ()


class FingerDrumEngine:
    def __init__(self, profile, sensitivity=1.):
        profile.validate()
        if not math.isfinite(sensitivity) or not .25 <= sensitivity <= 4:
            raise ValueError('Sensitivity must be .25-4')
        self.profile = profile
        self.sensitivity = sensitivity
        self.max_gap = .25
        self.max_step = .6
        self._states = {}

    def reset(self):
        self._states.clear()

    def update(self, hands, now):
        if not isinstance(now, (int, float)) or not math.isfinite(now):
            self.reset()
            return []
        seen = set()
        hits = []
        for binding in self.profile.bindings:
            if not binding.enabled or not binding.calibrated:
                continue
            value = measure(hands.get(binding.hand), binding.finger)
            identity = (binding.hand, binding.finger)
            if value is None:
                continue
            seen.add(identity)
            span = binding.pressed - binding.rest
            progress = (value - binding.rest) / span
            calibration = (binding.rest, binding.pressed)
            state = self._states.get(identity)
            if (state is None or state.calibration != calibration
                    or not 0 < now - state.time <= self.max_gap
                    or abs(value - state.value) > min(self.max_step, max(.08, abs(span) * 4))):
                self._states[identity] = _State(value, now, progress <= .25,
                                                calibration=calibration)
                continue
            previous = (state.value - binding.rest) / span
            dt = now - state.time
            motion = (value - state.value) * (1 if span > 0 else -1)
            if progress <= .25:
                state.armed = True
            if previous < .65 <= progress:
                if state.armed and motion / dt * self.sensitivity >= binding.min_speed:
                    fraction = (.65 - previous) / (progress - previous)
                    hit_time = state.time + fraction * dt
                    if hit_time - state.last_hit >= binding.cooldown:
                        # Velocity follows progress speed so short calibrated strokes
                        # still provide useful dynamics without long-finger bias.
                        velocity = max(1, min(127, round(30 + (progress - previous) / dt * 5)))
                        hits.append(Hit(hit_time, binding.note, velocity, hand=binding.hand,
                                        finger=binding.finger, label=binding.label))
                        state.last_hit = hit_time
                state.armed = False
            state.value, state.time = value, now
        self._states = {key: state for key, state in self._states.items() if key in seen}
        return sorted(hits, key=lambda hit: (hit.time, hit.hand, hit.finger))
