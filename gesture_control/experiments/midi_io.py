# SPDX-License-Identifier: GPL-3.0-only
"""Optional live MIDI and dependency-free Standard MIDI File recording.

Importing this module never imports mido or opens a MIDI port. ``MidiOutput()``
is a dry run; name an existing port to send MIDI. On Windows, a separately
configured loopMIDI port can connect this app to a DAW.
"""
from dataclasses import dataclass
import heapq
import importlib
import math
from pathlib import Path
import struct
import sys
import threading
import time


def _finite(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if value < 0 or (positive and value == 0):
        raise ValueError(f'{name} must be {"positive" if positive else "nonnegative"}')
    return value


def _integer(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'{name} must be an integer from {low} to {high}')


@dataclass(frozen=True)
class NoteEvent:
    time: float
    note: int
    velocity: int
    duration: float = .08
    channel: int = 9

    def __post_init__(self):
        _finite(self.time, 'time')
        _finite(self.duration, 'duration', positive=True)
        _finite(self.time + self.duration, 'note end time')
        _integer(self.note, 0, 127, 'note')
        _integer(self.velocity, 0, 127, 'velocity')
        _integer(self.channel, 0, 15, 'channel')


def _mido():
    try:
        return importlib.import_module('mido')
    except ImportError as exc:
        raise RuntimeError('Live MIDI needs optional mido and python-rtmidi packages. '
                           'Install them in your chosen environment; file recording works without them.') from exc


class MidiOutput:
    def __init__(self, port_name=None):
        if port_name is not None and (not isinstance(port_name, str) or not port_name.strip()):
            raise ValueError('port_name must name an existing port, or be None for dry run')
        self.port_name = port_name
        self.dry_run = port_name is None
        self.error = None
        self._api = None
        self._port = None
        self._condition = threading.Condition()
        self._active = {}  # (channel, note) -> generation token
        self._channels = set()
        self._queue = []  # (monotonic deadline, token, channel, note)
        self._generation = 0
        self._closed = False
        self._thread = None
        if self.dry_run:
            return
        self._api = _mido()
        try:
            # No virtual=True: Windows callers must configure an existing port.
            self._port = self._api.open_output(port_name)
        except Exception as exc:
            raise RuntimeError(f'Cannot open MIDI output {port_name!r}: {exc}') from exc
        self._thread = threading.Thread(target=self._schedule, name='hand-control-midi-noteoffs', daemon=True)
        self._thread.start()

    @staticmethod
    def list_ports():
        try:
            return list(_mido().get_output_names())
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f'Cannot list MIDI outputs: {exc}') from exc

    def _send(self, message_type, **values):
        if self._port is not None:
            self._port.send(self._api.Message(message_type, **values))

    def trigger(self, note, velocity, now, duration=.08, channel=9):
        event = NoteEvent(now, note, velocity, duration, channel)
        with self._condition:
            if self._closed:
                raise RuntimeError('MIDI output is closed')
            if self.error:
                raise RuntimeError(self.error)
            if self.dry_run:
                return event
            key = (channel, note)
            try:
                if key in self._active:
                    self._send('note_off', note=note, velocity=0, channel=channel)
                    del self._active[key]
                self._channels.add(channel)
                if velocity == 0:
                    self._send('note_off', note=note, velocity=0, channel=channel)
                    return event
                self._generation += 1
                token = self._generation
                # Register before send so cleanup can try note_off even if the
                # backend raises after partially sending note_on.
                self._active[key] = token
                self._send('note_on', note=note, velocity=velocity, channel=channel)
                heapq.heappush(self._queue, (now + duration, token, channel, note))
                self._condition.notify_all()
            except Exception as exc:
                self.error = f'MIDI send failed: {exc}'
                self._panic_locked()
                raise RuntimeError(self.error) from exc
        return event

    def control_change(self, control, value, channel=9):
        _integer(control,0,127,'control')
        _integer(value,0,127,'value')
        _integer(channel,0,15,'channel')
        with self._condition:
            if self._closed or self.error:
                raise RuntimeError(self.error or 'MIDI output is closed')
            if not self.dry_run:
                self._channels.add(channel)
                try:
                    self._send('control_change',control=control,value=value,channel=channel)
                except Exception as exc:
                    self.error=f'MIDI controller send failed: {exc}'
                    self._panic_locked()
                    raise RuntimeError(self.error) from exc

    def _release_due_locked(self, now):
        while self._queue and self._queue[0][0] <= now:
            _, token, channel, note = heapq.heappop(self._queue)
            key = (channel, note)
            if self._active.get(key) != token:
                continue  # an old deadline must not cut short a retrigger
            self._send('note_off', note=note, velocity=0, channel=channel)
            del self._active[key]

    def _schedule(self):
        with self._condition:
            while not self._closed:
                try:
                    self._release_due_locked(time.monotonic())
                except Exception as exc:
                    self.error = f'MIDI note release failed: {exc}'
                    self._panic_locked()
                    print(self.error, file=sys.stderr, flush=True)
                    return
                delay = max(0, self._queue[0][0] - time.monotonic()) if self._queue else None
                self._condition.wait(delay)

    def _panic_locked(self):
        failures = []
        for channel, note in list(self._active):
            try:
                self._send('note_off', note=note, velocity=0, channel=channel)
            except Exception as exc:
                failures.append(str(exc))
        self._active.clear()
        self._queue.clear()
        # Channel mode messages supplement individual note releases, including
        # notes whose backend send partially succeeded before an exception.
        for channel in self._channels:
            for controller in (64, 123, 120):
                try:
                    self._send('control_change', control=controller, value=0, channel=channel)
                except Exception as exc:
                    failures.append(str(exc))
        self._condition.notify_all()
        return failures

    def panic(self):
        with self._condition:
            failures = self._panic_locked()
            if failures:
                self.error = 'MIDI panic could not release all notes: ' + '; '.join(failures)
                raise RuntimeError(self.error)

    def close(self):
        failures = []
        with self._condition:
            if self._closed:
                return
            self._closed = True
            failures = self._panic_locked()
            self._condition.notify_all()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        if self._port is not None:
            try:
                self._port.close()
            except Exception as exc:
                failures.append(str(exc))
        if failures:
            self.error = 'MIDI cleanup failed: ' + '; '.join(failures)
            raise RuntimeError(self.error)


def _variable_length(value):
    if not 0 <= value <= 0x0fffffff:
        raise ValueError('MIDI delta time exceeds Standard MIDI File limits')
    data = [value & 0x7f]
    while value >> 7:
        value >>= 7
        data.insert(0, 0x80 | (value & 0x7f))
    return bytes(data)


class Recorder:
    """Record original hits and export their MIDI-voice-safe timeline.

    Non-overlapping durations are preserved. A same-channel/pitch retrigger
    clips the preceding voice, and simultaneous duplicates share one voice.
    Quantization is export-only and never changes ``events``.
    """
    def __init__(self, start_time=None):
        if start_time is not None:
            _finite(start_time, 'start_time')
        self.start_time = start_time
        self.events = []

    def record(self, event):
        if not isinstance(event, NoteEvent):
            raise TypeError('record expects a NoteEvent')
        if self.start_time is None:
            self.start_time = event.time
        if event.time < self.start_time:
            raise ValueError('Note time precedes recording start_time')
        self.events.append(event)

    def save(self, path, bpm=120, quantize=None):
        _finite(bpm, 'bpm', positive=True)
        raw_tempo = 60_000_000 / bpm
        if not math.isfinite(raw_tempo) or not 1 <= raw_tempo <= 0xffffff:
            raise ValueError('bpm is outside the MIDI tempo range')
        tempo = round(raw_tempo)
        if quantize is not None:
            _finite(quantize, 'quantize beat fraction', positive=True)
        ticks_per_beat = 480
        if quantize is not None and quantize * ticks_per_beat < 1:
            raise ValueError('quantize grid must be at least one MIDI tick (1/480 beat)')
        # Use the encoded tempo for consistent timing, even for unusual BPMs.
        ticks_per_second = ticks_per_beat * 1_000_000 / tempo
        scheduled = []
        # MIDI has no identity for individual voices at the same channel/pitch.
        # Build per-note timelines before writing note-offs so a previous hit
        # cannot later cut off the voice produced by a retrigger.
        timelines = {}
        start = self.start_time if self.start_time is not None else 0
        for index, event in enumerate(self.events):
            if not isinstance(event, NoteEvent):
                raise TypeError('Recorder.events must contain NoteEvent objects')
            relative = event.time - start
            if relative < 0:
                raise ValueError('Note time precedes recording start_time')
            raw_tick = relative * ticks_per_second
            raw_duration = event.duration * ticks_per_second
            if not math.isfinite(raw_tick) or not math.isfinite(raw_duration):
                raise ValueError('Recording time exceeds MIDI range')
            tick = round(raw_tick)
            if quantize is not None:
                grid = quantize * ticks_per_beat
                if not math.isfinite(grid):
                    raise ValueError('quantize grid exceeds MIDI range')
                # Quantize onset only. Preserve the recorded note duration.
                tick = round(math.floor(tick / grid + .5) * grid)
            off_tick = tick + max(1, round(raw_duration))
            timelines.setdefault((event.channel, event.note), []).append(
                (tick, off_tick, event.velocity, index))
        for (channel, note), entries in timelines.items():
            # Events can become simultaneous after optional quantization. One
            # shared voice uses the loudest velocity and longest requested end.
            coalesced = {}
            for tick, off_tick, velocity, index in entries:
                existing = coalesced.get(tick)
                if existing is None:
                    coalesced[tick] = (off_tick, velocity, index)
                else:
                    end, previous_velocity, previous_index = existing
                    coalesced[tick] = (max(end, off_tick), max(previous_velocity, velocity),
                                       min(previous_index, index))
            ordered = sorted(coalesced.items())
            for position, (tick, (off_tick, velocity, index)) in enumerate(ordered):
                if velocity == 0:
                    # A zero-velocity event is an explicit release, not a new
                    # voice. The previous voice is clipped to this tick below.
                    scheduled.append((tick, 0, index, bytes((0x80 | channel, note, 0))))
                    continue
                if position + 1 < len(ordered):
                    off_tick = min(off_tick, ordered[position + 1][0])
                scheduled.append((tick, 1, index, bytes((0x90 | channel, note, velocity))))
                scheduled.append((off_tick, 0, index, bytes((0x80 | channel, note, 0))))
        scheduled.sort(key=lambda item: item[:3])
        track = bytearray(b'\x00\xff\x51\x03' + tempo.to_bytes(3, 'big'))
        previous = 0
        for tick, _, _, message in scheduled:
            track.extend(_variable_length(tick - previous))
            track.extend(message)
            previous = tick
        track.extend(b'\x00\xff\x2f\x00')
        data = b'MThd' + struct.pack('>IHHH', 6, 0, 1, ticks_per_beat)
        data += b'MTrk' + struct.pack('>I', len(track)) + bytes(track)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target
