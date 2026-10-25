# SPDX-License-Identifier: GPL-3.0-only
"""Air drums and a mini piano: explicit live MIDI output or local MIDI export."""
import argparse
from collections import deque
from datetime import datetime
from dataclasses import replace
from pathlib import Path
import time

from .midi_io import MidiOutput, NoteEvent, Recorder


def merge_simultaneous(hits):
    """One pitch onset for identical-time duplicates, preserving distinct flams."""
    groups = {}
    for hit in hits:
        key = (hit.note, round(hit.time, 6))
        old = groups.get(key)
        if old is None:
            groups[key] = hit
        else:
            groups[key] = replace(old, velocity=max(old.velocity, hit.velocity),
                                  duration=max(old.duration, hit.duration))
    return sorted(groups.values(), key=lambda hit: hit.time)


class Timing:
    def __init__(self):
        self.intervals = deque(maxlen=120)
        self.delays = deque(maxlen=120)
        self.previous = None

    def update(self, captured, dispatched):
        if captured is None:
            self.previous = None
            return
        if self.previous is not None and 0 < captured - self.previous < .5:
            self.intervals.append(captured - self.previous)
        self.previous = captured
        self.delays.append(max(0, dispatched - captured))

    def summary(self):
        hz = len(self.intervals) / sum(self.intervals) if self.intervals else 0
        delay = 1000 * sum(self.delays) / len(self.delays) if self.delays else 0
        return hz, delay


class Instrument:
    def __init__(self, engine, output, args):
        self.engine, self.output, self.args = engine, output, args
        self.recorder = Recorder()
        self.enabled = False
        self.status = "SPACE to arm. Lift hands above line, then tap downward."
        self.timing = Timing()
        self.flashes = {}
        self.last_saved_count = 0
        self.closed = False

    def save(self):
        if not self.recorder.events:
            self.status = "No MIDI notes recorded yet"
            return
        path = self.args.record
        if path is None:
            name = ('piano-' if self.args.piano else 'drums-') + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.mid'
            path = Path.home() / 'HandControl' / 'midi' / name
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.recorder.save(path, bpm=self.args.bpm, quantize=self.args.quantize)
            self.last_saved_count = len(self.recorder.events)
            self.status = f"Saved {len(self.recorder.events)} notes: {path.name}"
            print(f"MIDI saved: {path}")
        except (ValueError, OSError) as exc:
            self.status = f"Save failed: {exc}"
            print(self.status)

    def common_key(self, key):
        if key == ord(' '):
            self.enabled = not self.enabled
            self.engine.reset()
            self.output.panic()
            self.status = "ARMED - lift above the line before a hit" if self.enabled else "PAUSED"
        elif key in (ord('p'), ord('P')):
            self.output.panic()
            self.engine.reset()
            self.enabled = False
            self.status = "PANIC - paused; all notes released"
        elif key in (ord('c'), ord('C')):
            self.recorder = Recorder()
            self.last_saved_count = 0
            self.status = "Local take cleared (FL Studio recording is separate)"
        elif key in (ord('s'), ord('S')):
            self.save()

    def emit(self, hits, ctx):
        for hit in merge_simultaneous(hits):
            velocity = self.args.fixed_velocity or hit.velocity
            self.output.trigger(hit.note, velocity, ctx.now, duration=hit.duration, channel=self.args.channel - 1)
            self.recorder.record(NoteEvent(hit.time, hit.note, velocity, hit.duration, self.args.channel - 1))
            self.flashes[hit.note] = ctx.now
            self.status = f"{hit.hand} | MIDI {hit.note} | velocity {velocity}"

    def process(self, ctx):
        import cv2
        if self.output.error:
            raise RuntimeError(f"MIDI output failed: {self.output.error}")
        self.common_key(ctx.key)
        self.timing.update(ctx.captured_at, ctx.now)
        sample_time = ctx.captured_at if ctx.captured_at is not None else ctx.now
        hits = self.engine.update(ctx.hands if self.enabled else {}, sample_time)
        self.emit(hits, ctx)
        height, width = ctx.frame.shape[:2]
        line = round(self.args.hit_y * height)
        count = 8 if self.args.piano else 4
        labels = ('C', 'D', 'E', 'F', 'G', 'A', 'B', 'C') if self.args.piano else ('Kick', 'Snare', 'Closed hat', 'Open hat')
        notes = tuple(self.args.base_note + offset for offset in (0, 2, 4, 5, 7, 9, 11, 12)) if self.args.piano else self.args.notes
        for i, (label, note) in enumerate(zip(labels, notes)):
            x0, x1 = round(i * width / count), round((i + 1) * width / count) - 1
            active = ctx.now - self.flashes.get(note, -100) < .15
            color = (70, 230, 130) if active else (130, 140, 160)
            cv2.rectangle(ctx.frame, (x0, line), (x1, height - 35), color, 3)
            cv2.putText(ctx.frame, f'{label} {note}', (x0 + 5, min(height - 10, line + 25)), cv2.FONT_HERSHEY_SIMPLEX, .40, color, 1)
        cv2.line(ctx.frame, (0, line), (width - 1, line), (0, 200, 255), 2)
        lift = round((self.args.hit_y - (.07 if self.args.piano else .10)) * height)
        cv2.line(ctx.frame, (0, lift), (width - 1, lift), (80, 100, 100), 1)
        if self.args.piano:
            from .piano_engine import positions
        else:
            from .drum_engine import position
        for label, hand in ctx.hands.items():
            points = positions(hand).values() if self.args.piano else [position(hand)]
            for point in points:
                if point:
                    cv2.circle(ctx.frame, (round(point[0] * width), round(point[1] * height)), 7, (255, 180, 50), 2)
        hz, delay = self.timing.summary()
        beat = (ctx.now * self.args.bpm / 60) % 1
        cv2.circle(ctx.frame, (width - 18, 18), 6, (60, 230, 100) if beat < .12 else (70, 70, 70), -1)
        lines = [f"{'PIANO' if self.args.piano else 'DRUMS'} | {'ARMED' if self.enabled else 'PAUSED'} | " + ('FILE/PREVIEW ONLY' if self.output.dry_run else 'LIVE MIDI'),
                 'SPACE arm/pause | S save .mid | C clear take | P panic | Q exit',
                 self.status,
                 f'{hz:.1f} tracked frames/s | capture-to-handler {delay:.0f} ms (not audio latency)',
                 f'{len(self.recorder.events)} notes | {self.args.bpm:g} BPM visual guide (not DAW synced)']
        cv2.rectangle(ctx.frame, (0, 0), (width, 124), (20, 20, 20), -1)
        for i, text in enumerate(lines):
            cv2.putText(ctx.frame, text[:96], (10, 22 + 23 * i), cv2.FONT_HERSHEY_SIMPLEX, .43, (235, 235, 235), 1)
        return True

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.output.close()
        finally:
            if self.args.record and len(self.recorder.events) > self.last_saved_count:
                self.save()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--piano', action='store_true')
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--fps', type=int, choices=(30,60,120), default=60, help='Requested camera rate; actual rate/tracking throughput may be lower')
    parser.add_argument('--list-ports', action='store_true')
    parser.add_argument('--port', help='Exact existing MIDI output port; omit for preview/file recording only')
    parser.add_argument('--notes', type=int, nargs=4, default=(36, 38, 42, 46), metavar=('KICK','SNARE','HAT','OPEN_HAT'))
    parser.add_argument('--channel', type=int, help='MIDI channel 1-16; default drums 10, piano 1')
    parser.add_argument('--hit-y', type=float, default=.62, help='Strike line as fraction of camera height')
    parser.add_argument('--sensitivity', type=float, default=1.0)
    parser.add_argument('--fixed-velocity', type=int, help='Override stroke-derived velocity, 1-127')
    parser.add_argument('--base-note', type=int, default=60)
    parser.add_argument('--finger-profile', type=Path, help='Piano only: use just the enabled hand/finger bindings from a personal drum profile')
    parser.add_argument('--record', type=Path, help='MIDI file path; also saves take on exit')
    parser.add_argument('--bpm', type=float, default=120)
    parser.add_argument('--quantize', type=float, default=None, help='Export-only grid in quarter-note beats, e.g. .25 for 16ths; default off')
    args = parser.parse_args(argv)
    if args.channel is None:
        args.channel = 1 if args.piano else 10
    if not (1 <= args.channel <= 16 and .25 <= args.hit_y <= .85 and .25 <= args.sensitivity <= 4 and 20 <= args.bpm <= 300):
        parser.error('Use channel 1-16, hit-y .25-.85, sensitivity .25-4, BPM 20-300')
    if any(not 0 <= v <= 127 for v in args.notes) or not 0 <= args.base_note <= 115:
        parser.error('MIDI notes must be 0-127; base-note 0-115')
    if args.fixed_velocity is not None and not 1 <= args.fixed_velocity <= 127:
        parser.error('fixed-velocity must be 1-127')
    if args.quantize is not None and not .03125 <= args.quantize <= 4:
        parser.error('quantize must be .03125-4 quarter-note beats')
    if args.list_ports:
        try:
            ports = MidiOutput.list_ports()
            print('\n'.join(ports) if ports else 'No MIDI outputs found. Create a loopMIDI port and leave loopMIDI running.')
            return 0
        except (ImportError, RuntimeError, OSError) as exc:
            print(f'Cannot list MIDI ports: {exc}. Run SetupMIDI.bat for live output dependencies.')
            return 1
    try:
        if args.piano:
            from .piano_engine import PianoEngine
            enabled=None
            if args.finger_profile:
                from .hand_profile import HandProfile
                profile=HandProfile.load(args.finger_profile)
                enabled={side:{b.finger for b in profile.bindings if b.enabled and b.hand==side} for side in ('Left','Right')}
            engine = PianoEngine(hit_y=args.hit_y, sensitivity=args.sensitivity, base_note=args.base_note,enabled_fingers=enabled)
        else:
            if args.finger_profile:
                raise ValueError('--finger-profile belongs to piano mode; use finger-drums for calibrated finger MIDI')
            from .drum_engine import DrumEngine
            engine = DrumEngine(hit_y=args.hit_y, sensitivity=args.sensitivity, notes=args.notes)
        output = MidiOutput(args.port)
    except (ValueError, ImportError, RuntimeError, OSError) as exc:
        print(f'Cannot start MIDI instrument: {exc}')
        return 1
    from .runtime import run
    print('No audio synthesizer is included in this mode. Live sound comes from your selected FL Studio instrument.')
    print('Press S to export MIDI. Export timing starts at the first hit; it is not synchronized to the DAW transport.')
    return run(Instrument(engine, output, args), camera=args.camera, camera_fps=args.fps,
               title='Air MIDI Piano' if args.piano else 'Air MIDI Drums')
