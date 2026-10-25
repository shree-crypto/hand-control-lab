import tempfile
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import MagicMock, patch

from gesture_control.experiments.drum_engine import DrumEngine, Hit
from gesture_control.experiments.midi_instrument import Instrument, Timing, main, merge_simultaneous
from gesture_control.experiments.midi_io import MidiOutput


def hand(x, y):
    return SimpleNamespace(points=[(x, y, 0)] * 21, x=x, y=y, pinch=1.)


class InstrumentTests(unittest.TestCase):
    def make(self, target=None):
        args = SimpleNamespace(piano=False, hit_y=.62, notes=(36,38,42,46), base_note=60,
                               channel=10, fixed_velocity=None, record=target, bpm=120, quantize=None)
        return Instrument(DrumEngine(), MidiOutput(), args)

    def context(self, hands, stamp, key=-1):
        return SimpleNamespace(frame=SimpleNamespace(shape=(480,640,3)), hands=hands,
                               captured_at=stamp, now=stamp + .02, key=key)

    def test_paused_never_records_and_armed_records_two_hands(self):
        player = self.make()
        with patch.dict(sys.modules, {'cv2': MagicMock()}):
            player.process(self.context({'Right':hand(.3,.5)}, 1.))
            player.process(self.context({'Right':hand(.3,.7)}, 1.1))
            self.assertEqual(player.recorder.events, [])
            player.process(self.context({'Left':hand(.1,.5), 'Right':hand(.3,.5)}, 2., ord(' ')))
            player.process(self.context({'Left':hand(.1,.7), 'Right':hand(.3,.7)}, 2.1))
        self.assertEqual({e.note for e in player.recorder.events}, {36,38})
        self.assertTrue(all(e.channel == 9 for e in player.recorder.events))
        self.assertTrue(all(abs(e.time - 2.06) < 1e-8 for e in player.recorder.events))
        player.close()

    def test_explicit_path_autosaves_on_close(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'take.mid'
            player = self.make(path)
            with patch.dict(sys.modules, {'cv2': MagicMock()}):
                player.process(self.context({'Right':hand(.3,.5)}, 1., ord(' ')))
                player.process(self.context({'Right':hand(.3,.7)}, 1.1))
            with patch('builtins.print'):
                player.close()
            self.assertTrue(path.read_bytes().startswith(b'MThd'))
            player.close()

    def test_zero_channel_is_rejected(self):
        with patch('sys.stderr'), self.assertRaises(SystemExit):
            main(['--channel','0'])

    def test_same_time_same_pitch_coalesces_but_flams_remain(self):
        hits = merge_simultaneous([Hit(1,38,60), Hit(1,38,90), Hit(1.03,38,70)])
        self.assertEqual([(h.time,h.velocity) for h in hits], [(1,90),(1.03,70)])

    def test_timing_labels_processing_delay_separately(self):
        timing = Timing()
        timing.update(1,1.02)
        timing.update(1.05,1.08)
        hz, delay = timing.summary()
        self.assertAlmostEqual(hz,20)
        self.assertAlmostEqual(delay,25)


if __name__ == '__main__':
    unittest.main()
