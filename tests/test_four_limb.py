from types import SimpleNamespace
import unittest

from gesture_control.experiments.four_limb import FourLimbEngine, knee_measure, select_blob


def hand(x=.3, y=.5):
    return SimpleNamespace(points=[(x, y, 0)] * 21)


def pose(left=.2, right=.2, hip_y=.45, visibility=1):
    points = [(.5, .5, 0, visibility)] * 33
    points[23] = (.4, hip_y, 0, visibility)
    points[24] = (.6, hip_y, 0, visibility)
    points[25] = (.4, hip_y + left, 0, visibility)
    points[26] = (.6, hip_y + right, 0, visibility)
    return points


def calibrated(**kwargs):
    engine = FourLimbEngine(**kwargs)
    engine.calibrate_knee("Left", .2, .1)
    engine.calibrate_knee("Right", .2, .1)
    return engine


class FourLimbTests(unittest.TestCase):
    def test_uncalibrated_knees_never_fire(self):
        engine = FourLimbEngine()
        engine.update({}, pose(.1, .1), 0)
        self.assertEqual(engine.update({}, pose(), .1), [])
        self.assertEqual(engine.knee_status["Left"], "uncalibrated")

    def test_knee_measure_subtracts_body_translation(self):
        self.assertAlmostEqual(knee_measure(pose(), "Left"), .2)
        self.assertAlmostEqual(knee_measure(pose(hip_y=.3), "Left"), .2)

    def test_visibility_and_invalid_pose_are_rejected(self):
        self.assertIsNone(knee_measure(pose(visibility=.5), "Left"))
        self.assertIsNone(knee_measure(None, "Right"))
        self.assertIsNone(knee_measure([], "Left"))
        self.assertIsNone(knee_measure(pose(left=float("nan")), "Left"))

    def test_four_controls_can_fire_in_one_frame(self):
        engine = calibrated()
        engine.update({"Left": hand(.3, .5), "Right": hand(.7, .5)}, pose(.1, .1), 0)
        # Hand plane crossings occur after the same-frame pedal close.
        hits = engine.update({"Left": hand(.3, .65), "Right": hand(.7, .65)}, pose(), .1)
        self.assertEqual(len(hits), 4)
        self.assertEqual({hit.note for hit in hits}, {36, 38, 42, 44})
        self.assertFalse(engine.hat_open)
        self.assertEqual([(cc.control, cc.value) for cc in engine.cc_events], [(4, 127)])

    def test_lift_opens_hat_and_right_hand_uses_open_note(self):
        engine = calibrated()
        engine.update({"Right": hand(.7, .5)}, pose(), 0)
        engine.update({"Right": hand(.7, .5)}, pose(left=.1), .1)
        hits = engine.update({"Right": hand(.7, .7)}, pose(left=.1), .2)
        self.assertTrue(engine.hat_open)
        self.assertEqual([hit.note for hit in hits], [46])
        self.assertEqual(engine.hat_cc, 0)

    def test_hand_before_same_frame_pedal_close_uses_open_hat(self):
        engine = calibrated()
        engine.update({"Right": hand(.7, .5)}, pose(left=.1), 0)
        hits = engine.update({"Right": hand(.7, .7)}, pose(), .1)
        hand_hit = next(hit for hit in hits if hit.hand == "Right")
        pedal = next(event for event in engine.cc_events if event.value == 127)
        self.assertLess(hand_hit.time, pedal.time)
        self.assertEqual(hand_hit.note, 46)
        self.assertFalse(engine.hat_open)

    def test_hand_before_same_frame_pedal_open_uses_closed_hat(self):
        engine = calibrated()
        engine.update({"Right": hand(.7, .5)}, pose(), 0)
        hits = engine.update({"Right": hand(.7, .7)}, pose(left=.1), .1)
        hand_hit = next(hit for hit in hits if hit.hand == "Right")
        pedal = next(event for event in engine.cc_events if event.value == 0)
        self.assertLess(hand_hit.time, pedal.time)
        self.assertEqual(hand_hit.note, 42)
        self.assertTrue(engine.hat_open)

    def test_loss_and_reacquisition_do_not_emit_pedal_notes(self):
        engine = calibrated()
        engine.update({}, pose(.1, .1), 0)
        engine.update({}, None, .05)
        self.assertEqual(engine.update({}, pose(), .1), [])
        self.assertEqual(engine.cc_events, [])

    def test_stale_knee_frame_cannot_fire(self):
        engine = calibrated()
        engine.update({}, pose(.1, .1), 0)
        self.assertEqual(engine.update({}, pose(), .5), [])

    def test_whole_body_translation_does_not_fire_knees(self):
        engine = calibrated()
        engine.update({}, pose(hip_y=.4), 0)
        self.assertEqual(engine.update({}, pose(hip_y=.5), .1), [])
        self.assertFalse(engine.hat_open)

    def test_knee_cooldown_blocks_fast_rearmed_repeat(self):
        engine = calibrated()
        engine.update({}, pose(right=.1), 0)
        self.assertEqual(len(engine.update({}, pose(), .05)), 1)
        engine.update({}, pose(right=.1), .1)
        self.assertEqual(engine.update({}, pose(), .15), [])

    def test_large_knee_jump_suppresses_events(self):
        engine = calibrated()
        engine.update({}, pose(.06, .06), 0)
        self.assertEqual(engine.update({}, pose(.24, .24), .05), [])
        self.assertFalse(engine.hat_available)

    def test_kick_needs_lift_not_small_bounce(self):
        engine = calibrated()
        engine.update({}, pose(), 0)
        engine.update({}, pose(right=.16), .1)
        self.assertEqual(engine.update({}, pose(), .2), [])

    def test_repeated_knee_rest_does_not_repeat(self):
        engine = calibrated()
        engine.update({}, pose(right=.1), 0)
        self.assertEqual([hit.note for hit in engine.update({}, pose(), .1)], [36])
        self.assertEqual(engine.update({}, pose(), .2), [])

    def test_direction_is_learned_from_calibration(self):
        engine = FourLimbEngine()
        engine.calibrate_knee("Right", .1, .2)
        engine.update({}, pose(right=.2), 0)
        self.assertEqual([hit.note for hit in engine.update({}, pose(right=.1), .1)], [36])

    def test_marker_mode_works_without_hand_landmarks(self):
        engine = FourLimbEngine(hand_mode="markers")
        engine.update({}, None, 0, {"Left": (.3, .5), "Right": (.7, .5)})
        hits = engine.update({}, None, .1, {"Left": (.3, .7), "Right": (.7, .7)})
        self.assertEqual({hit.note for hit in hits}, {38, 42})

    def test_marker_loss_does_not_bridge_hits(self):
        engine = FourLimbEngine(hand_mode="markers")
        engine.update({}, None, 0, {"Left": (.3, .5)})
        engine.update({}, None, .05, {})
        self.assertEqual(engine.update({}, None, .1, {"Left": (.3, .7)}), [])

    def test_blob_ambiguity_and_area_rejection(self):
        self.assertEqual(select_blob([(100, 10, 20)], 10000), (10, 20))
        self.assertIsNone(select_blob([(100, 10, 20), (90, 30, 40)], 10000))
        self.assertIsNone(select_blob([(1, 10, 20), (1000, 30, 40)], 10000))
        self.assertEqual(select_blob([(100, 10, 20), (20, 30, 40)], 10000), (10, 20))

    def test_calibration_validation_and_reset_preserves_endpoints(self):
        engine = calibrated()
        engine.reset()
        self.assertEqual(engine.calibration["Right"].rest, .2)
        with self.assertRaises(ValueError):
            engine.calibrate_knee("Right", .2, .201)
        with self.assertRaises(ValueError):
            engine.calibrate_knee("Wrong", .2, .1)


if __name__ == "__main__":
    unittest.main()
