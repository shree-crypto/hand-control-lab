import unittest
from types import SimpleNamespace

from gesture_control.experiments.drum_engine import DrumEngine


def hand(x, y):
    return SimpleNamespace(points=[(x, y, 0.0)] * 21, x=x, y=y, pinch=1.0)


class DrumEngineTests(unittest.TestCase):
    def test_initial_hand_below_plane_cannot_strike(self):
        engine = DrumEngine()
        self.assertEqual(engine.update({"Right": hand(.3, .7)}, 0), [])
        self.assertEqual(engine.update({"Right": hand(.3, .8)}, .05), [])

    def test_downward_hit_interpolates_time_and_pad(self):
        engine = DrumEngine()
        engine.update({"Right": hand(.3, .5)}, 1.0)
        hits = engine.update({"Right": hand(.3, .7)}, 1.1)
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual((hit.note, hit.hand, hit.pad), (38, "Right", "Snare"))
        self.assertAlmostEqual(hit.time, 1.06)
        self.assertEqual(hit.duration, .08)
        self.assertTrue(1 <= hit.velocity <= 127)

    def test_rebound_below_lift_margin_cannot_repeat(self):
        engine = DrumEngine()
        engine.update({"Right": hand(.3, .5)}, 0)
        self.assertEqual(len(engine.update({"Right": hand(.3, .7)}, .1)), 1)
        engine.update({"Right": hand(.3, .59)}, .3)
        self.assertEqual(engine.update({"Right": hand(.3, .7)}, .4), [])

    def test_preparatory_lift_rearms_for_next_hit(self):
        engine = DrumEngine()
        engine.update({"Right": hand(.3, .5)}, 0)
        engine.update({"Right": hand(.3, .7)}, .1)
        engine.update({"Right": hand(.3, .5)}, .25)
        self.assertEqual(len(engine.update({"Right": hand(.3, .7)}, .35)), 1)

    def test_slow_crossing_is_rejected_and_consumes_arm(self):
        engine = DrumEngine()
        engine.update({"Right": hand(.3, .5)}, 0)
        engine.update({"Right": hand(.3, .60)}, .18)
        self.assertEqual(engine.update({"Right": hand(.3, .63)}, .36), [])
        self.assertEqual(engine.update({"Right": hand(.3, .8)}, .4), [])

    def test_lateral_crossing_is_rejected(self):
        engine = DrumEngine()
        engine.update({"Right": hand(.1, .5)}, 0)
        engine.update({"Right": hand(.1, .60)}, .1)
        self.assertEqual(engine.update({"Right": hand(.4, .64)}, .12), [])

    def test_loss_and_reacquire_never_bridges_strike(self):
        engine = DrumEngine()
        engine.update({"Right": hand(.3, .5)}, 0)
        engine.update({}, .05)
        self.assertEqual(engine.update({"Right": hand(.3, .7)}, .1), [])

    def test_stale_gap_never_bridges_strike(self):
        engine = DrumEngine()
        engine.update({"Right": hand(.3, .5)}, 0)
        self.assertEqual(engine.update({"Right": hand(.3, .7)}, .5), [])

    def test_large_tracking_jump_never_strikes(self):
        engine = DrumEngine()
        engine.update({"Right": hand(.3, .2)}, 0)
        self.assertEqual(engine.update({"Right": hand(.3, .8)}, .03), [])

    def test_both_hands_can_hit_simultaneously(self):
        engine = DrumEngine()
        engine.update({"Left": hand(.1, .5), "Right": hand(.8, .5)}, 0)
        hits = engine.update({"Left": hand(.1, .7), "Right": hand(.8, .7)}, .1)
        self.assertEqual({hit.hand for hit in hits}, {"Left", "Right"})
        self.assertEqual({hit.note for hit in hits}, {36, 46})

    def test_cooldown_is_per_hand(self):
        engine = DrumEngine(cooldown=.2)
        engine.update({"Right": hand(.3, .5), "Left": hand(.8, .5)}, 0)
        engine.update({"Right": hand(.3, .7), "Left": hand(.8, .55)}, .05)
        hits = engine.update({"Right": hand(.3, .5), "Left": hand(.8, .7)}, .1)
        self.assertEqual([hit.hand for hit in hits], ["Left"])
        self.assertEqual(engine.update({"Right": hand(.3, .7), "Left": hand(.8, .7)}, .15), [])

    def test_sensitivity_and_speed_change_velocity(self):
        velocities = []
        for sensitivity in (.5, 1, 10):
            engine = DrumEngine(sensitivity=sensitivity)
            engine.update({"Right": hand(.3, .5)}, 0)
            velocities.append(engine.update({"Right": hand(.3, .7)}, .1)[0].velocity)
        self.assertLess(velocities[0], velocities[1])
        self.assertEqual(velocities[2], 127)

    def test_custom_notes_and_pad_crossing_position(self):
        engine = DrumEngine(notes=(10, 20, 30, 40))
        engine.update({"Right": hand(.24, .5)}, 0)
        hit = engine.update({"Right": hand(.26, .7)}, .1)[0]
        self.assertEqual(hit.note, 20)  # crossing x=.252, not old x=.24

    def test_wrist_palm_point_ignores_fingertips(self):
        value = hand(.3, .5)
        value.points[8] = (.9, .9, 0)
        self.assertEqual(DrumEngine.position(value), (.3, .5))

    def test_configuration_resets_pending_stroke(self):
        engine = DrumEngine()
        engine.update({"Right": hand(.3, .5)}, 0)
        engine.configure(hit_y=.7, sensitivity=2)
        self.assertEqual(engine.update({"Right": hand(.3, .8)}, .1), [])

    def test_invalid_landmarks_and_time_reset(self):
        engine = DrumEngine()
        self.assertIsNone(engine.position(SimpleNamespace(points=[])))
        self.assertIsNone(engine.position(hand(float("nan"), .5)))
        engine.update({"Right": hand(.3, .5)}, 0)
        self.assertEqual(engine.update({"Right": hand(.3, .7)}, float("nan")), [])
        self.assertEqual(engine.update({"Right": hand(.3, .7)}, .1), [])

    def test_invalid_configuration_fails_clearly(self):
        for kwargs in ({"notes": (36,)}, {"notes": (36, 38, 42, 200)},
                       {"hit_y": 1}, {"sensitivity": 0}, {"cooldown": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                DrumEngine(**kwargs)


if __name__ == "__main__":
    unittest.main()
