# SPDX-License-Identifier: GPL-3.0-only
"""Camera-independent gesture state machine; coordinates are normalized to 0..1."""
from dataclasses import dataclass
from math import exp


@dataclass(frozen=True)
class Hand:
    x: float
    y: float
    index_pinch: float
    middle_pinch: float


@dataclass(frozen=True)
class Action:
    kind: str
    x: float = 0
    y: float = 0


class Gate:
    def __init__(self, on=.30, off=.48):
        if not 0 < on < off:
            raise ValueError('Gesture thresholds require 0 < on < off')
        self.on, self.off = on, off
        self.active = False

    def update(self, distance):
        self.active = distance < (self.off if self.active else self.on)
        return self.active


class PointerMapper:
    """Relative gain changes preserve the current pointer position."""
    def __init__(self):
        self.raw = None
        self.target = None

    def update(self, x, y, gain=1.0):
        if self.raw is None:
            self.target = (x, y)
        else:
            self.target = tuple(max(0.0, min(1.0, p + (v - old) * gain))
                                for p, v, old in zip(self.target, (x, y), self.raw))
        self.raw = (x, y)
        return self.target


class Engine:
    def __init__(self, precision=False, primary_thresholds=(.30,.48), secondary_thresholds=(.30,.48),
                 scroll_thresholds=(.30,.48), precision_thresholds=(.30,.48)):
        self.armed = False
        self.status = "PAUSED - F8 to enable"
        self.dragging = False
        self.position = None
        self.last_time = None
        self.last_seen = None
        self.precision_enabled = precision
        self.primary_thresholds = primary_thresholds
        self.secondary_thresholds = secondary_thresholds
        self.scroll_thresholds = scroll_thresholds
        self.precision_thresholds = precision_thresholds
        self._reset()

    def _reset(self):
        self.index = Gate(*self.primary_thresholds)
        self.middle = Gate(*self.secondary_thresholds)
        self.other = Gate(*self.scroll_thresholds)
        self.precision = Gate(*self.precision_thresholds)
        self.mapper = PointerMapper()
        self.pinch_start = None
        self.right_latched = False
        self.scroll_y = None
        self.scroll_remainder = 0.0
        self.neutral_since = None
        self.wait_neutral = True
        self.position = None
        self.last_time = None

    def release(self):
        actions = [Action("up")] if self.dragging else []
        self.dragging = False
        self._reset()
        return actions

    def toggle(self):
        actions = self.release()
        self.armed = not self.armed
        self.last_seen = None
        self.status = "Release selected pinches to begin" if self.armed else "PAUSED - F8 to enable"
        return actions

    def step(self, hand, other, now):
        if not self.armed:
            return []
        if hand is None:
            actions = self.release()
            if self.last_seen is None:
                self.last_seen = now
            if now - self.last_seen > 0.6:
                self.armed = False
                self.status = "Tracking lost - PAUSED; F8 to resume"
            else:
                self.status = "Hand missing - input released"
            return actions
        self.last_seen = now
        index = self.index.update(hand.index_pinch)
        middle = self.middle.update(hand.middle_pinch)
        scroll = self.other.update(other.index_pinch) if other else False
        if other is None:
            self.other.active = False
            self.precision.active = False
        fine = self.precision.update(other.middle_pinch) if other and self.precision_enabled else False
        if self.wait_neutral:
            if index or middle or scroll:
                self.neutral_since = None
            elif self.neutral_since is None:
                self.neutral_since = now
            elif now - self.neutral_since >= 0.15:
                self.wait_neutral = False
            self.status = "Release selected pinches to begin"
            return []
        # Scroll takes priority and cancels pending clicks/drags.
        if scroll:
            actions = [Action("up")] if self.dragging else []
            self.dragging = False
            self.pinch_start = None
            self.right_latched = True
            if self.scroll_y is not None:
                self.scroll_remainder += (self.scroll_y - other.y) * 18
                ticks = int(self.scroll_remainder)
                if ticks:
                    actions.append(Action("scroll", ticks))
                    self.scroll_remainder -= ticks
            self.scroll_y = other.y
            self.status = "SCROLL - move other hand up/down"
            return actions
        if self.scroll_y is not None:
            self.scroll_y = None
            self.scroll_remainder = 0
            self.wait_neutral = True
            self.neutral_since = None
            self.status = "Release pinches after scrolling"
            return []
        actions = []
        # Cursor stays fixed during a short pinch to prevent click-position drift.
        if (not index and self.pinch_start is None and not middle) or (index and self.pinch_start is not None and now - self.pinch_start >= 0.4):
            x = max(0.0, min(1.0, (hand.x - 0.15) / 0.70))
            y = max(0.0, min(1.0, (hand.y - 0.18) / 0.64))
            if self.precision_enabled:
                x, y = self.mapper.update(x, y, .2 if fine else 1.0)
            dt = 1 / 30 if self.last_time is None else max(0.001, now - self.last_time)
            alpha = 1 - exp(-dt / 0.045)
            if self.position is None:
                self.position = (x, y)
            else:
                self.position = tuple(p + alpha * (v - p) for p, v in zip(self.position, (x, y)))
            actions.append(Action("move", *self.position))
        self.last_time = now
        if index:
            if self.pinch_start is None:
                self.pinch_start = now
            elif now - self.pinch_start >= 0.4 and not self.dragging:
                actions.append(Action("down"))
                self.dragging = True
            self.status = "DRAG" if self.dragging else "PINCH - release to click; hold to drag"
        elif self.pinch_start is not None:
            actions.append(Action("up") if self.dragging else Action("click"))
            self.dragging = False
            self.pinch_start = None
            self.status = "POINTER"
        else:
            self.status = "POINTER"
        # One right-click per thumb-middle pinch, never a repeat while held.
        if middle and not index and not self.right_latched:
            actions.append(Action("right_click"))
            self.right_latched = True
            self.status = "RIGHT CLICK"
        elif not middle:
            self.right_latched = False
        elif index:
            self.right_latched = True
        if fine and self.status == "POINTER":
            self.status = "PRECISION - 20% movement gain"
        return actions
