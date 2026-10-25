# SPDX-License-Identifier: GPL-3.0-only
"""Air drawing and a local, opt-in Windows air instrument. No desktop input."""
import argparse
from dataclasses import dataclass
from datetime import datetime
import io
import math
from pathlib import Path
import platform
import struct
import tempfile
import wave


def clamp(value, low, high):
    return max(low, min(high, value))


class StrokeTracker:
    """Return disconnected segments on release, hand loss, stalls or large jumps."""
    def __init__(self):
        self.active = False
        self.previous = None
        self.last_time = None

    def update(self, hand, now):
        if hand is None:
            self.reset()
            return None
        active = hand.pinch < (0.48 if self.active else 0.30)
        self.active = active
        if not active:
            self.previous = None
            self.last_time = now
            return None
        point = (clamp(hand.x, 0, 1), clamp(hand.y, 0, 1))
        previous = self.previous
        if (self.last_time is None or now - self.last_time > .25 or
                (previous is not None and math.dist(previous, point) > .18)):
            previous = None
        self.previous = point
        self.last_time = now
        return previous or point, point

    def reset(self):
        self.active = False
        self.previous = None
        self.last_time = None


def brush_radius(other, fallback):
    if other is None:
        return int(clamp(fallback, 2, 24))
    return round(2 + clamp(other.pinch / 1.8, 0, 1) * 22)


@dataclass(frozen=True)
class Tone:
    frequency: float = 0.0
    volume: float = 0.0
    note: int = 0


def instrument_tone(right, left):
    """Right pinch gates playback, right height picks note, left height volume."""
    if right is None or left is None or right.pinch >= .48:
        return Tone()
    note = round(clamp(1 - right.y, 0, 1) * 24)
    # Twenty-five semitones starting at A3, all well within ordinary hearing.
    frequency = 220 * 2 ** (note / 12)
    volume = round(clamp(1 - left.y, 0, 1) * 12) / 100
    return Tone(frequency, volume, note)


def make_wave(tone, sample_rate=22050):
    """Bounded mono PCM waveform. Whole cycles keep loop boundary discontinuity small."""
    volume = clamp(tone.volume, 0, .12)
    frequency = clamp(tone.frequency, 220, 880)
    cycles = max(1, round(frequency * .12))
    count = max(1, round(sample_rate * cycles / frequency))
    pcm = bytearray()
    for i in range(count):
        sample = round(32767 * volume * math.sin(2 * math.pi * cycles * i / count))
        pcm.extend(struct.pack('<h', sample))
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)
    return buffer.getvalue()


class WindowsTonePlayer:
    """Uses asynchronous WAV playback; no audio worker or network dependencies."""
    def __init__(self, enabled=False):
        self.api = None
        self.message = 'VISUAL ONLY - use --audio on Windows for sound'
        self.current = Tone()
        self.last_change = 0.0
        self.directory = None
        if enabled and platform.system() == 'Windows':
            import winsound
            self.api = winsound
            self.directory = tempfile.TemporaryDirectory(prefix='hand-control-audio-')
            self.message = 'AUDIO ON - max 12% digital amplitude; check speaker volume'
        elif enabled:
            self.message = 'VISUAL ONLY - Windows winsound audio unavailable on this platform'

    def play(self, tone, now):
        if self.api is None or tone == self.current:
            return
        # Silence must never be delayed by the update limiter.
        if tone.volume <= 0 or tone.frequency <= 0:
            self.api.PlaySound(None, 0)
            self.current = Tone()
            return
        if now - self.last_change < .12:
            return
        name = Path(self.directory.name) / f'{tone.note}-{round(tone.volume * 100)}.wav'
        if not name.exists():
            name.write_bytes(make_wave(tone))
        self.api.PlaySound(str(name), self.api.SND_FILENAME | self.api.SND_ASYNC | self.api.SND_LOOP | self.api.SND_NODEFAULT)
        self.current = tone
        self.last_change = now

    def close(self):
        if self.api is not None:
            self.api.PlaySound(None, 0)
        if self.directory is not None:
            self.directory.cleanup()


class Drawing:
    def __init__(self):
        self.canvas = None
        self.tracker = StrokeTracker()
        self.radius = 7
        self.color_index = 0
        self.colors = [(80, 230, 255), (90, 240, 90), (255, 150, 80), (210, 80, 255), (255, 255, 255)]
        self.message = 'Pinch right thumb/index to draw; release to lift pen'

    def process(self, ctx):
        import cv2
        import numpy as np
        height, width = ctx.frame.shape[:2]
        if self.canvas is None or self.canvas.shape != ctx.frame.shape:
            self.canvas = np.zeros_like(ctx.frame)
            self.tracker.reset()
        key = ctx.key
        if key in (ord('c'), ord('C')):
            self.canvas.fill(0)
            self.tracker.reset()
        elif key in (ord('+'), ord('=')):
            self.radius = min(24, self.radius + 1)
        elif key in (ord('-'), ord('_')):
            self.radius = max(2, self.radius - 1)
        elif ord('1') <= key <= ord('5'):
            self.color_index = key - ord('1')
        elif key in (ord('s'), ord('S')):
            folder = Path.home() / 'HandControl' / 'drawings'
            try:
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / ('drawing-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.png')
                if not cv2.imwrite(str(target), self.canvas):
                    raise OSError('Image writer failed')
                self.message = f'Saved {target.name} in {folder}'
            except OSError as exc:
                self.message = f'Save failed: {exc}'
        right = ctx.hands.get('Right')
        left = ctx.hands.get('Left')
        radius = brush_radius(left, self.radius)
        segment = self.tracker.update(right, ctx.now)
        if segment:
            a, b = segment
            points = [(round(x * (width - 1)), round(y * (height - 1))) for x, y in (a, b)]
            cv2.line(self.canvas, *points, self.colors[self.color_index], radius * 2, cv2.LINE_AA)
            cv2.circle(self.canvas, points[-1], radius, self.colors[self.color_index], -1, cv2.LINE_AA)
        # Bright paint on a dim camera; saved image contains paint only on black.
        ctx.frame[:] = np.maximum((ctx.frame * .25).astype('uint8'), self.canvas)
        if right:
            cv2.circle(ctx.frame, (round(right.x * (width - 1)), round(right.y * (height - 1))), radius + 3, (180, 180, 180), 1)
        lines = ['AIR DRAW | sandbox only', f'Brush {radius}px | left thumb/index separation changes size',
                 'C clear | 1-5 color | +/- brush (without left hand) | S save', self.message]
        draw_labels(cv2, ctx.frame, lines)
        return True

    def close(self):
        pass


class Instrument:
    def __init__(self, audio=False):
        self.player = WindowsTonePlayer(audio)

    def process(self, ctx):
        import cv2
        tone = instrument_tone(ctx.hands.get('Right'), ctx.hands.get('Left'))
        try:
            self.player.play(tone, ctx.now)
        except (RuntimeError, OSError) as exc:
            self.player.close()
            self.player.api = None
            self.player.message = f'AUDIO UNAVAILABLE: {exc}'
        height, width = ctx.frame.shape[:2]
        lines = ['AIR INSTRUMENT | sandbox only', self.player.message,
                 'Both hands visible. Right pinch plays; right height = pitch.',
                 'Left height = volume. Release pinch or hide either hand = silence.',
                 f'{tone.frequency:.0f} Hz | volume {tone.volume:.2f}' if tone.volume else 'SILENT']
        cv2.rectangle(ctx.frame, (20, height - 60), (width - 20, height - 30), (40, 40, 40), -1)
        if tone.frequency:
            length = round((width - 40) * tone.volume / .12)
            cv2.rectangle(ctx.frame, (20, height - 60), (20 + length, height - 30), (90, 220, 120), -1)
            x = round(20 + tone.note / 24 * (width - 40))
            cv2.circle(ctx.frame, (x, height - 90), 12, (80, 220, 255), -1)
        draw_labels(cv2, ctx.frame, lines)
        return True

    def close(self):
        self.player.close()


def draw_labels(cv2, frame, lines):
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 24 * len(lines) + 10), (20, 20, 20), -1)
    for index, line in enumerate(lines):
        cv2.putText(frame, line, (10, 23 + index * 24), cv2.FONT_HERSHEY_SIMPLEX, .47, (240, 240, 240), 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--instrument', action='store_true', help='Run the air instrument instead of drawing')
    parser.add_argument('--audio', action='store_true', help='Opt in to sound on Windows; instrument mode only')
    args = parser.parse_args(argv)
    if args.audio and not args.instrument:
        parser.error('--audio is only available with --instrument / music mode')
    from .runtime import run
    handler = Instrument(args.audio) if args.instrument else Drawing()
    return run(handler, camera=args.camera, with_face=False,
               title='Air Instrument' if args.instrument else 'Air Drawing')


if __name__ == '__main__':
    raise SystemExit(main())
