from types import SimpleNamespace
import unittest

from gesture_control.experiments.piano_engine import FINGERS, PianoEngine, positions


def hand(fingers=None, y=.8):
    # Default fingertips are already below the plane and cannot accidentally play.
    points = [(.5, y, 0)] * 21
    for name, coordinate in (fingers or {}).items():
        points[FINGERS[name]] = (*coordinate, 0)
    return SimpleNamespace(points=points, pinch=1., x=.5, y=y)


class PianoTests(unittest.TestCase):
    def test_excluded_fingers_never_generate_notes(self):
        piano=PianoEngine(enabled_fingers={'Left':{'ring'},'Right':{'index'}})
        all_up={name:(.2,.5) for name in FINGERS}
        all_down={name:(.2,.7) for name in FINGERS}
        piano.update({'Left':hand(all_up),'Right':hand(all_up)},1.)
        hits=piano.update({'Left':hand(all_down),'Right':hand(all_down)},1.1)
        self.assertEqual({(h.hand,h.finger) for h in hits},{('Left','ring'),('Right','index')})
    def test_large_vertical_jump_does_not_play(self):
        piano = PianoEngine()
        piano.update({'Right': hand({'index': (.2,.2)})}, 0)
        self.assertEqual(piano.update({'Right': hand({'index': (.2,.8)})}, .05), [])

    def test_crossing_time_interpolated(self):
        piano = PianoEngine()
        piano.update({'Right': hand({'index': (.2,.5)})}, 1.)
        hits = piano.update({'Right': hand({'index': (.2,.7)})}, 1.1)
        self.assertAlmostEqual(hits[0].time,1.06)

    def test_initial_observation_never_plays(self):
        piano = PianoEngine()
        self.assertEqual(piano.update({"Right": hand()}, 0), [])
        self.assertEqual(piano.update({"Right": hand()}, .1), [])

    def test_lift_then_downward_tap_plays_one_note(self):
        piano = PianoEngine()
        piano.update({"Right": hand({"index": (.2, .5)})}, 0)
        hits = piano.update({"Right": hand({"index": (.2, .65)})}, .1)
        self.assertEqual(len(hits), 1)
        self.assertEqual((hits[0].note, hits[0].hand, hits[0].finger), (62, "Right", "index"))
        self.assertGreaterEqual(hits[0].velocity, 1)
        self.assertLessEqual(hits[0].velocity, 127)
        self.assertEqual(hits[0].duration, .25)

    def test_no_repeat_while_held_or_sliding_below_plane(self):
        piano = PianoEngine()
        piano.update({"Right": hand({"index": (.2, .5)})}, 0)
        self.assertEqual(len(piano.update({"Right": hand({"index": (.2, .65)})}, .1)), 1)
        for t, x in ((.2, .3), (.3, .5), (.4, .8)):
            self.assertEqual(piano.update({"Right": hand({"index": (x, .7)})}, t), [])

    def test_lateral_crossing_is_not_a_tap(self):
        piano = PianoEngine()
        piano.update({"Right": hand({"index": (.2, .5)})}, 0)
        self.assertEqual(piano.update({"Right": hand({"index": (.7, .65)})}, .1), [])

    def test_rearm_requires_lift_and_respects_cooldown(self):
        piano = PianoEngine()
        piano.update({"Right": hand({"index": (.2, .5)})}, 0)
        piano.update({"Right": hand({"index": (.2, .65)})}, .1)
        piano.update({"Right": hand({"index": (.2, .5)})}, .12)
        self.assertEqual(piano.update({"Right": hand({"index": (.2, .65)})}, .14), [])
        piano.update({"Right": hand({"index": (.2, .5)})}, .3)
        self.assertEqual(len(piano.update({"Right": hand({"index": (.2, .65)})}, .4)), 1)

    def test_chords_and_both_hands(self):
        piano = PianoEngine()
        lifted = {"index": (.1, .5), "middle": (.3, .5)}
        pressed = {"index": (.1, .7), "middle": (.3, .7)}
        piano.update({"Left": hand(lifted), "Right": hand(lifted)}, 0)
        hits = piano.update({"Left": hand(pressed), "Right": hand(pressed)}, .1)
        self.assertEqual(len(hits), 4)
        self.assertEqual({h.hand for h in hits}, {"Left", "Right"})

    def test_tracking_loss_requires_new_lift(self):
        piano = PianoEngine()
        piano.update({"Right": hand({"index": (.2, .5)})}, 0)
        piano.update({}, .05)
        self.assertEqual(piano.update({"Right": hand({"index": (.2, .65)})}, .1), [])

    def test_stale_frame_and_reverse_time_do_not_trigger(self):
        for second in (1, -.1):
            piano = PianoEngine()
            piano.update({"Right": hand({"index": (.2, .5)})}, 0)
            self.assertEqual(piano.update({"Right": hand({"index": (.2, .65)})}, second), [])

    def test_slow_crossing_does_not_play(self):
        piano = PianoEngine()
        piano.update({"Right": hand({"index": (.2, .5)})}, 0)
        for i in range(1, 15):
            self.assertEqual(piano.update({"Right": hand({"index": (.2, .5 + .01 * i)})}, i * .1), [])

    def test_sensitivity_changes_speed_requirement(self):
        piano = PianoEngine(sensitivity=4)
        piano.update({"Right": hand({"index": (.2, .54)})}, 0)
        hits = piano.update({"Right": hand({"index": (.2, .63)})}, .2)
        self.assertEqual(len(hits), 1)

    def test_key_mapping_and_midi_bounds(self):
        piano = PianoEngine(base_note=115)
        self.assertEqual(piano.notes, (115, 117, 119, 120, 122, 124, 126, 127))
        self.assertEqual([piano.note_at((i + .5) / 8) for i in range(8)],
                         [115, 117, 119, 120, 122, 124, 126, 127])
        self.assertEqual(piano.note_at(1), 127)
        for x in (-1, 2, float("nan")):
            self.assertIsNone(piano.note_at(x))
        for kwargs in ({"base_note": 116}, {"base_note": 60.5}, {"hit_y": 0},
                       {"sensitivity": 0}, {"sensitivity": float("inf")}):
            with self.assertRaises(ValueError):
                PianoEngine(**kwargs)

    def test_positions_omit_invalid_and_can_exclude_thumb(self):
        data = hand({"thumb": (.2, .5), "index": (-1, .5)})
        self.assertNotIn("index", positions(data))
        self.assertIn("thumb", positions(data))
        self.assertNotIn("thumb", PianoEngine(include_thumb=False).positions(data))


if __name__ == "__main__":
    unittest.main()
