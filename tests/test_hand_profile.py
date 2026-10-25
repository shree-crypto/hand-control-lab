import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from gesture_control.experiments.hand_profile import Binding, FINGERS, HandProfile, measure


def hand(values=None):
    points = [(float("nan"), float("nan"), 0)] * 21
    points[0] = (.5, .7, 0)
    for index in (5, 9, 13, 17):
        points[index] = (.5, .5, 0)
    for finger, value in (values or {}).items():
        points[FINGERS[finger][0]] = (.5, .5 + value * .2, 0)
    return SimpleNamespace(points=points)


class HandProfileTests(unittest.TestCase):
    def test_defaults_exclude_specific_short_digits_and_are_uncalibrated(self):
        profile = HandProfile.default()
        self.assertEqual([(b.hand, b.finger) for b in profile.bindings],
                         [("Left", "ring"), ("Left", "pinky"), ("Right", "index"), ("Right", "middle")])
        self.assertTrue(all(not b.calibrated for b in profile.bindings))

    def test_measure_ignores_unselected_nan_tips(self):
        self.assertAlmostEqual(measure(hand({"ring": -.1}), "ring"), -.1)
        self.assertIsNone(measure(hand({"ring": -.1}), "index"))

    def test_measure_translation_and_scale_invariant(self):
        original = hand({"ring": -.1})
        moved = SimpleNamespace(points=[(x * 2 + 3, y * 2 - 5, z) for x, y, z in original.points])
        self.assertAlmostEqual(measure(original, "ring"), measure(moved, "ring"))

    def test_calibration_supports_small_and_reverse_motion(self):
        binding = Binding("Left", "ring", 36, "Kick")
        binding.calibrate(-.1, -.08)
        self.assertTrue(binding.calibrated)
        binding.calibrate(-.08, -.1)
        self.assertTrue(binding.calibrated)
        with self.assertRaises(ValueError):
            binding.calibrate(-.1, -.099)
        self.assertEqual((binding.rest, binding.pressed), (-.08, -.1))

    def test_profile_roundtrip_and_strict_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            profile = HandProfile.default()
            profile.save(path)
            restored = HandProfile.load(path)
            self.assertEqual(restored, profile)
            raw = json.loads(path.read_text())
            raw["bindings"][0]["unexpected"] = True
            path.write_text(json.dumps(raw))
            with self.assertRaises(ValueError):
                HandProfile.load(path)

    def test_invalid_binding_and_duplicate_rejected(self):
        for kwargs in ({"note": 128}, {"note": True}, {"rest": 0}, {"label": ""}, {"min_speed": 0}):
            values = dict(hand="Left", finger="ring", note=36, label="Kick")
            values.update(kwargs)
            with self.assertRaises(ValueError):
                Binding(**values)
        b = Binding("Left", "ring", 36, "Kick")
        with self.assertRaises(ValueError):
            HandProfile([b, b])


if __name__ == "__main__":
    unittest.main()
