# SPDX-License-Identifier: GPL-3.0-only
"""Experimental four-limb drumming: palms/colored markers plus calibrated knees.

Inspired by camera-based drumming interaction ideas, not a literal replication
of any paper. No camera, MIDI port, or machine-learning model opens on import.
"""
from dataclasses import dataclass
import math
from types import SimpleNamespace

from .drum_engine import DrumEngine


@dataclass(frozen=True)
class Hit:
    time: float
    note: int
    velocity: int
    duration: float = .08
    hand: str = ""
    label: str = ""

    @property
    def pad(self):
        return self.label


@dataclass(frozen=True)
class ControlChange:
    time: float
    control: int
    value: int


@dataclass(frozen=True)
class KneeCalibration:
    rest: float
    raised: float


@dataclass(frozen=True)
class ColorRange:
    lower: tuple
    upper: tuple
    lower2: object = None
    upper2: object = None


DEFAULT_COLORS = {
    "Left": ColorRange((0, 100, 70), (10, 255, 255), (170, 100, 70), (179, 255, 255)),
    "Right": ColorRange((95, 100, 70), (130, 255, 255)),
}


def select_blob(candidates, image_area, min_area_ratio=.0005, max_area_ratio=.08,
                ambiguity_ratio=.6):
    """Select (area,cx,cy) only when one plausible color blob dominates."""
    if not math.isfinite(image_area) or image_area <= 0:
        return None
    plausible = [c for c in candidates if len(c) == 3 and all(math.isfinite(v) for v in c)
                 and min_area_ratio * image_area <= c[0] <= max_area_ratio * image_area]
    plausible.sort(key=lambda c: c[0], reverse=True)
    if not plausible or (len(plausible) > 1 and plausible[1][0] >= plausible[0][0] * ambiguity_ratio):
        return None
    return plausible[0][1], plausible[0][2]


def detect_markers(frame, colors=None, min_area_ratio=.0005, max_area_ratio=.08,
                   ambiguity_ratio=.6):
    """Find red Left and blue Right markers; normalized coordinates or omissions.

    Colors label the marker, not anatomical handedness; place the red marker on
    your left hand/stick and blue on your right. Similar-size same-color blobs
    are ambiguous and suppressed. HSV limits can be supplied in ``colors``.
    """
    import cv2
    import numpy as np
    if frame is None or len(frame.shape) != 3 or frame.shape[2] != 3:
        return {}
    height, width = frame.shape[:2]
    if width <= 0 or height <= 0:
        return {}
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    positions = {}
    kernel = np.ones((3, 3), dtype=np.uint8)
    for side, bounds in (DEFAULT_COLORS if colors is None else colors).items():
        mask = cv2.inRange(hsv, np.array(bounds.lower, dtype=np.uint8), np.array(bounds.upper, dtype=np.uint8))
        if bounds.lower2 is not None and bounds.upper2 is not None:
            extra = cv2.inRange(hsv, np.array(bounds.lower2, dtype=np.uint8), np.array(bounds.upper2, dtype=np.uint8))
            mask = cv2.bitwise_or(mask, extra)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            moments = cv2.moments(contour)
            if moments["m00"]:
                candidates.append((area, moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]))
        point = select_blob(candidates, width * height, min_area_ratio, max_area_ratio, ambiguity_ratio)
        if point is not None:
            positions[side] = (point[0] / width, point[1] / height)
    return positions


def _side(side):
    value = str(side).title()
    if value not in ("Left", "Right"):
        raise ValueError("side must be Left or Right")
    return value


def knee_measure(pose, side, min_visibility=.6):
    """Anatomical knee y minus same-side hip y; None when hidden or malformed.

    MediaPipe indices: Left hip23/knee25, Right hip24/knee26. Subtracting the
    hip removes shared vertical translation; perspective changes still require
    recalibration. This is an image-space measurement, not joint angle.
    """
    side = _side(side)
    try:
        if pose is None or len(pose) != 33:
            return None
        hip, knee = (pose[23], pose[25]) if side == "Left" else (pose[24], pose[26])
        if len(hip) < 4 or len(knee) < 4 or not all(math.isfinite(float(v)) for v in (*hip[:4], *knee[:4])):
            return None
        if hip[3] < min_visibility or knee[3] < min_visibility:
            return None
        # Off-image hips/knees can have deceptively high visibility estimates.
        if not all(0 <= p[0] <= 1 and 0 <= p[1] <= 1 for p in (hip, knee)):
            return None
        return float(knee[1] - hip[1])
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


@dataclass
class _KneeState:
    previous: object = None
    lifted: bool = False
    last_hit: float = float("-inf")


class FourLimbEngine:
    """Two hand hits, a kick knee and a hi-hat pedal knee, each independent.

    Left knee opens/closes hi-hat, rather than inventing a fourth instrument.
    CC4 transitions are exposed as ``cc_events`` for optional MIDI routing;
    note hits are returned. They do not automatically send anything to MIDI.
    """
    def __init__(self, hand_mode="palm", hit_y=.62, sensitivity=1.0,
                 hand_notes=(38, 42), kick_note=36, open_hat_note=46,
                 foot_chick_note=44):
        if hand_mode not in ("palm", "markers"):
            raise ValueError("hand_mode must be palm or markers")
        notes = (*hand_notes, kick_note, open_hat_note, foot_chick_note)
        if len(hand_notes) != 2 or any(isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= 127 for n in notes):
            raise ValueError("MIDI notes must be integers from 0 to 127, with two hand_notes")
        self.hand_mode = hand_mode
        self.hand_notes = tuple(hand_notes)
        self.kick_note = kick_note
        self.open_hat_note = open_hat_note
        self.foot_chick_note = foot_chick_note
        self.drum = DrumEngine(hit_y=hit_y, sensitivity=sensitivity)
        self.hit_y = self.drum.hit_y
        self.sensitivity = self.drum.sensitivity
        self.calibration = {}
        self.reset()

    @property
    def hat_cc(self):
        """Common pedal convention: zero open, 127 closed (plugin may differ)."""
        return 0 if self.hat_open else 127

    def reset(self):
        """Clear pending gestures; keep personal calibration."""
        self.drum.reset()
        self.knees = {side: _KneeState() for side in ("Left", "Right")}
        self.knee_status = {side: "uncalibrated" if side not in self.calibration else "waiting" for side in self.knees}
        self.knee_progress = {side: None for side in self.knees}
        self.hat_open = False
        self.hat_available = False
        self.cc_events = []

    def calibrate_knee(self, side, rest, raised):
        side = _side(side)
        rest, raised = float(rest), float(raised)
        if not all(math.isfinite(v) for v in (rest, raised)) or abs(rest - raised) < .015:
            raise ValueError("Rest and raised knee measurements must be finite and at least .015 apart")
        self.calibration[side] = KneeCalibration(rest, raised)
        self.reset()

    def set_calibration(self, side, rest, raised):
        self.calibrate_knee(side, rest, raised)

    def _update_knee(self, side, pose, now):
        state = self.knees[side]
        calibration = self.calibration.get(side)
        measure = knee_measure(pose, side)
        self.knee_progress[side] = None
        if calibration is None or measure is None:
            self.knee_status[side] = "uncalibrated" if calibration is None else "not visible"
            state.previous = None
            state.lifted = False
            if side == "Left":
                self.hat_available = False
            return []
        progress = (measure - calibration.rest) / (calibration.raised - calibration.rest)
        if not math.isfinite(progress) or not -.75 <= progress <= 1.75:
            self.knee_status[side] = "out of calibrated range"
            state.previous = None
            state.lifted = False
            if side == "Left":
                self.hat_available = False
            return []
        self.knee_progress[side] = progress
        self.knee_status[side] = "raised" if progress >= .65 else "rest" if progress <= .35 else "moving"
        if side == "Left":
            self.hat_available = True
        previous = state.previous
        state.previous = (progress, now)
        if previous is None:
            state.lifted = progress >= .65
            if side == "Left":
                # Acquisition establishes state silently; never a pedal strike.
                if progress >= .65:
                    self.hat_open = True
                elif progress <= .35:
                    self.hat_open = False
            return []
        old, then = previous
        dt = now - then
        if dt <= 0 or dt > .25 or abs(progress - old) > 1.4:
            state.lifted = progress >= .65
            if side == "Left":
                # No new state guessed after a stale/jumping observation.
                self.hat_available = False
                state.previous = None
            return []
        if progress >= .65:
            state.lifted = True
            if side == "Left" and not self.hat_open:
                self.hat_open = True
                # Preserve the estimated threshold-crossing order within a frame.
                opened_at = then + (.65 - old) / (progress - old) * dt if old < .65 <= progress else now
                self.cc_events.append(ControlChange(opened_at, 4, 0))
        crossed = old > .35 >= progress
        if not crossed:
            return []
        armed = state.lifted
        state.lifted = False
        speed = (old - progress) / dt
        strike_time = then + (old - .35) / (old - progress) * dt
        if side == "Left" and self.hat_open:
            self.hat_open = False
            self.cc_events.append(ControlChange(strike_time, 4, 127))
        if not armed or speed * self.sensitivity < .8 or strike_time - state.last_hit < .18:
            return []
        state.last_hit = strike_time
        velocity = max(1, min(127, round(speed * self.sensitivity * 20)))
        if side == "Right":
            return [Hit(strike_time, self.kick_note, velocity, hand="Right knee", label="Kick")]
        return [Hit(strike_time, self.foot_chick_note, velocity, hand="Left knee", label="Foot chick")]

    def update(self, hands, pose, now, markers=None):
        self.cc_events = []
        if not math.isfinite(now):
            self.reset()
            return []
        previous_hat = self.hat_open
        previous_hat_available = self.hat_available
        # Detect pedal changes first, then apply their times to each hand onset.
        hits = self._update_knee("Left", pose, now)
        hits += self._update_knee("Right", pose, now)
        if self.hand_mode == "markers":
            source = {}
            for side, point in (markers or {}).items():
                if side not in ("Left", "Right"):
                    continue
                try:
                    x, y = point
                    if not all(math.isfinite(v) and 0 <= v <= 1 for v in (x, y)):
                        continue
                    source[side] = SimpleNamespace(points=[(x, y, 0)] * 21)
                except (TypeError, ValueError):
                    continue
        else:
            source = hands
        # Respect UI calibration changes while retaining the underlying detector.
        if self.drum.hit_y != self.hit_y or self.drum.sensitivity != self.sensitivity:
            self.drum.configure(hit_y=self.hit_y, sensitivity=self.sensitivity)
        for hit in self.drum.update(source, now):
            left = hit.hand == "Left"
            # Reacquisition establishes a state without claiming a transition.
            # Otherwise a hit before a same-frame pedal close must stay open.
            hat_at_hit = previous_hat if previous_hat_available else self.hat_open
            for event in sorted(self.cc_events, key=lambda event: event.time):
                if event.time <= hit.time:
                    hat_at_hit = event.value == 0
            note = self.hand_notes[0] if left else self.open_hat_note if hat_at_hit else self.hand_notes[1]
            label = "Snare" if left else "Open hat" if hat_at_hit else "Closed hat"
            hits.append(Hit(hit.time, note, hit.velocity, hit.duration, hit.hand, label))
        return sorted(hits, key=lambda hit: (hit.time, hit.hand))
