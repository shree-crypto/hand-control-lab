import json
from pathlib import Path
import tempfile
import unittest

from gesture_control.experiments.hand_calibration import (
    calibrate_thresholds, load_pinch_profile, make_profile, save_pinch_profile,
    selected_distances, validate_pinch_profile,
)


def profile():
    return make_profile("Right", "index", "middle", [(.2, .3)] * 8,
                        [.1] * 8, [.12] * 8)


class CalibrationTests(unittest.TestCase):
    def test_reduced_movement_range_is_usable(self):
        on, off = calibrate_thresholds([.18] * 8, [.11] * 8)
        self.assertTrue(.11 < on < off < .18)

    def test_exact_contact_distance_zero_is_supported(self):
        on, off = calibrate_thresholds([.05] * 8, [0.] * 8)
        self.assertTrue(0 < on < off < .05)

    def test_no_separation_is_rejected(self):
        for pressed in ([.2] * 8, [.195] * 8, [.3] * 8):
            with self.assertRaises(ValueError):
                calibrate_thresholds([.2] * 8, pressed)

    def test_noisy_overlapping_states_are_rejected(self):
        with self.assertRaises(ValueError):
            calibrate_thresholds([.1, .3] * 4, [.05, .25] * 4)

    def test_need_eight_fresh_state_observations(self):
        with self.assertRaises(ValueError):
            calibrate_thresholds([.2] * 8, [.1] * 7)

    def test_nonfinite_boolean_and_out_of_range_distances_rejected(self):
        for value in (float("nan"), float("inf"), -1, 6, True):
            with self.assertRaises(ValueError):
                calibrate_thresholds([.2] * 8, [value] * 8)

    def test_selects_different_fingers_without_posture_criteria(self):
        points = [(.5, .5, 0)] * 21
        points[0] = (.2, .6, 0)
        points[9] = (.2, .4, 0)
        points[4] = (.25, .4, 0)
        points[16] = (.27, .4, 0)
        points[20] = (.30, .4, 0)
        result = selected_distances(points, "ring", "pinky")
        self.assertLess(result[0], result[1])
        scaled = [(x * .5, y * .5, z) for x, y, z in points]
        self.assertAlmostEqual(selected_distances(scaled, "ring", "pinky")[0], result[0])

    def test_malformed_hand_rejected(self):
        self.assertIsNone(selected_distances([]))
        self.assertIsNone(selected_distances([(.5, .5, 0)] * 21))
        with self.assertRaises(ValueError):
            selected_distances([], "ring", "ring")


class ProfileTests(unittest.TestCase):
    def test_chosen_digits_and_thresholds_are_stored_without_extra_fields(self):
        result = profile()
        self.assertEqual(result["dominant"], "Right")
        self.assertEqual(result["primary_finger"], "index")
        self.assertTrue(0 < result["primary_on"] < result["primary_off"])

    def test_unknown_fields_and_versions_rejected(self):
        for changes in ({"notes": "extra"}, {"version": 2}, {"version": True},
                        {"dominant": "Unknown"}, {"primary_finger": "thumb"},
                        {"secondary_finger": "index"}):
            candidate = profile()
            candidate.update(changes)
            with self.assertRaises(ValueError):
                validate_pinch_profile(candidate)

    def test_invalid_hysteresis_rejected(self):
        for on, off in ((.4, .2), (0, .3), (.1, float("nan")), (.1, True), (.1, 6)):
            candidate = profile()
            candidate.update(primary_on=on, primary_off=off)
            with self.assertRaises(ValueError):
                validate_pinch_profile(candidate)

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "pinch.json"
            save_pinch_profile(path, profile())
            self.assertEqual(load_pinch_profile(path), profile())
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_duplicate_and_oversize_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pinch.json"
            path.write_text('{"version":1,"version":1}')
            with self.assertRaises(ValueError):
                load_pinch_profile(path)
            path.write_text(" " * 4097)
            with self.assertRaises(ValueError):
                load_pinch_profile(path)


if __name__ == "__main__":
    unittest.main()
