import io
import struct
from types import SimpleNamespace
import unittest
import wave

from gesture_control.experiments.creative import (StrokeTracker, Tone, brush_radius,
                                                 instrument_tone, make_wave, WindowsTonePlayer)


def hand(x=.5, y=.5, pinch=.1):
    return SimpleNamespace(x=x, y=y, pinch=pinch)


class DrawingTests(unittest.TestCase):
    def test_release_and_loss_break_lines(self):
        tracker = StrokeTracker()
        tracker.update(hand(x=.3), 0)
        self.assertEqual(tracker.update(hand(x=.35), .05), ((.3, .5), (.35, .5)))
        tracker.update(None, .1)
        self.assertEqual(tracker.update(hand(x=.4), .15), ((.4, .5), (.4, .5)))
        tracker.update(hand(pinch=1), .2)
        self.assertEqual(tracker.update(hand(x=.45), .25), ((.45, .5), (.45, .5)))

    def test_stall_and_teleport_break_lines(self):
        tracker = StrokeTracker()
        tracker.update(hand(x=.1), 0)
        self.assertEqual(tracker.update(hand(x=.8), .1), ((.8, .5), (.8, .5)))
        self.assertEqual(tracker.update(hand(x=.85), .5), ((.85, .5), (.85, .5)))

    def test_pinching_has_hysteresis(self):
        tracker = StrokeTracker()
        self.assertIsNone(tracker.update(hand(pinch=.4), 0))
        self.assertIsNotNone(tracker.update(hand(pinch=.2), .1))
        self.assertIsNotNone(tracker.update(hand(pinch=.4), .2))
        self.assertIsNone(tracker.update(hand(pinch=.5), .3))

    def test_brush_bounded(self):
        self.assertEqual(brush_radius(hand(pinch=-2), 7), 2)
        self.assertEqual(brush_radius(hand(pinch=20), 7), 24)
        self.assertEqual(brush_radius(None, 7), 7)


class InstrumentTests(unittest.TestCase):
    def test_silence_bypasses_audio_rate_limit(self):
        calls = []
        player = WindowsTonePlayer()
        player.api = SimpleNamespace(PlaySound=lambda *args: calls.append(args))
        player.current = Tone(440, .1, 12)
        player.last_change = 10
        player.play(Tone(), 10.001)
        self.assertEqual(calls, [(None, 0)])
        self.assertEqual(player.current, Tone())

    def test_missing_hand_or_open_pinch_is_silent(self):
        self.assertEqual(instrument_tone(None, hand()), Tone())
        self.assertEqual(instrument_tone(hand(), None), Tone())
        self.assertEqual(instrument_tone(hand(pinch=1), hand()), Tone())

    def test_pitch_and_amplitude_bounded(self):
        for y in (-5, 0, .5, 1, 10):
            tone = instrument_tone(hand(y=y), hand(y=y))
            self.assertGreaterEqual(tone.frequency, 220)
            self.assertLessEqual(tone.frequency, 880)
            self.assertGreaterEqual(tone.volume, 0)
            self.assertLessEqual(tone.volume, .12)

    def test_wave_is_valid_and_caps_amplitude(self):
        data = make_wave(Tone(440, 20, 12))
        with wave.open(io.BytesIO(data)) as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.getframerate(), 22050)
            frames = wav.readframes(wav.getnframes())
        samples = struct.unpack('<' + 'h' * (len(frames) // 2), frames)
        self.assertLessEqual(max(abs(x) for x in samples), round(32767 * .12))


if __name__ == '__main__':
    unittest.main()
