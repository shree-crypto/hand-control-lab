import unittest

from gesture_control.experiments.finger_drums import FingerDrumEngine
from gesture_control.experiments.hand_profile import Binding, HandProfile
from test_hand_profile import hand


class FingerDrumTests(unittest.TestCase):
    def setUp(self):
        self.profile = HandProfile([Binding("Left", "ring", 36, "Kick", -.10, -.08),
                                    Binding("Right", "index", 38, "Snare", -.10, -.08)])
        self.engine = FingerDrumEngine(self.profile)

    def test_uncalibrated_never_plays(self):
        engine = FingerDrumEngine(HandProfile.default())
        self.assertEqual(engine.update({"Left": hand({"ring": -.10})}, 0), [])
        self.assertEqual(engine.update({"Left": hand({"ring": -.08})}, .1), [])

    def test_reduced_motion_selected_digit_can_play(self):
        self.engine.update({"Left": hand({"ring": -.10})}, 0)
        hits = self.engine.update({"Left": hand({"ring": -.08})}, .1)
        self.assertEqual(len(hits), 1)
        self.assertEqual((hits[0].note, hits[0].finger, hits[0].label), (36, "ring", "Kick"))
        self.assertAlmostEqual(hits[0].time, .065)

    def test_reverse_direction_calibration(self):
        self.profile.bindings[0].calibrate(-.08, -.10)
        self.engine.update({"Left": hand({"ring": -.08})}, 0)
        self.assertEqual(len(self.engine.update({"Left": hand({"ring": -.10})}, .1)), 1)

    def test_acquisition_held_press_and_tracking_loss_do_not_play(self):
        self.assertEqual(self.engine.update({"Left": hand({"ring": -.08})}, 0), [])
        self.assertEqual(self.engine.update({"Left": hand({"ring": -.08})}, .1), [])
        self.engine.update({"Left": hand({"ring": -.10})}, .2)
        self.engine.update({}, .25)
        self.assertEqual(self.engine.update({"Left": hand({"ring": -.08})}, .3), [])

    def test_disabled_binding_never_plays(self):
        self.profile.bindings[0].enabled = False
        self.engine.update({"Left": hand({"ring": -.10})}, 0)
        self.assertEqual(self.engine.update({"Left": hand({"ring": -.08})}, .1), [])

    def test_four_simultaneous_independent_fingers(self):
        profile = HandProfile.default()
        for binding in profile.bindings:
            binding.calibrate(-.1, -.08)
        engine = FingerDrumEngine(profile)
        resting = {"Left": hand({"ring": -.1, "pinky": -.1}), "Right": hand({"index": -.1, "middle": -.1})}
        pressing = {"Left": hand({"ring": -.08, "pinky": -.08}), "Right": hand({"index": -.08, "middle": -.08})}
        engine.update(resting, 0)
        hits = engine.update(pressing, .1)
        self.assertEqual(len(hits), 4)
        self.assertEqual(hits, sorted(hits, key=lambda hit: (hit.time, hit.hand, hit.finger)))

    def test_cooldown_and_rearm(self):
        self.engine.update({"Left": hand({"ring": -.10})}, 0)
        self.engine.update({"Left": hand({"ring": -.08})}, .1)
        self.engine.update({"Left": hand({"ring": -.10})}, .11)
        self.assertEqual(self.engine.update({"Left": hand({"ring": -.08})}, .15), [])
        self.engine.update({"Left": hand({"ring": -.10})}, .25)
        self.assertEqual(len(self.engine.update({"Left": hand({"ring": -.08})}, .35)), 1)

    def test_jump_and_gap_do_not_play(self):
        self.engine.update({"Left": hand({"ring": -.1})}, 0)
        self.assertEqual(self.engine.update({"Left": hand({"ring": .9})}, .1), [])
        self.engine.reset()
        self.engine.update({"Left": hand({"ring": -.1})}, 0)
        self.assertEqual(self.engine.update({"Left": hand({"ring": -.08})}, 1), [])

    def test_jump_guard_adapts_to_small_calibrated_strokes(self):
        self.engine.update({"Left": hand({"ring": -.1})}, 0)
        self.assertEqual(self.engine.update({"Left": hand({"ring": .02})}, .1), [])

    def test_calibration_change_resets_prior_arm(self):
        self.engine.update({"Left": hand({"ring": -.1})}, 0)
        self.profile.bindings[0].calibrate(-.12, -.1)
        self.assertEqual(self.engine.update({"Left": hand({"ring": -.1})}, .1), [])


if __name__ == "__main__":
    unittest.main()
