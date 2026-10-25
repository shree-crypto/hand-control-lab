import json
from pathlib import Path
import tempfile
import unittest

from gesture_control.experiments.gestures import (
    PinchEdge, PoseClassifier, PoseStore, normalize, valid_feature, wheel_segment)


class GestureTests(unittest.TestCase):
    def test_normalization_ignores_translation_and_uniform_scale(self):
        points = [(i * .01, i * .02, i * -.005) for i in range(21)]
        transformed = [(x * 3 + 10, y * 3 - 4, z * 3 + 1) for x, y, z in points]
        for a, b in zip(normalize(points), normalize(transformed)):
            self.assertAlmostEqual(a, b)

    def test_invalid_landmarks_rejected(self):
        for points in ([], [(0, 0, 0)] * 21, [(float("nan"), 0, 0)] * 21):
            with self.assertRaises(ValueError):
                normalize(points)

    def test_pinch_edge_needs_release_and_only_fires_once(self):
        edge = PinchEdge()
        self.assertFalse(edge.update(.1))
        self.assertFalse(edge.update(.7))
        self.assertTrue(edge.update(.1))
        self.assertFalse(edge.update(.1))
        self.assertFalse(edge.update(.4))
        self.assertFalse(edge.update(None))
        self.assertFalse(edge.update(.1))
        self.assertFalse(edge.update(.7))
        self.assertTrue(edge.update(.1))

    def test_center_has_no_command(self):
        self.assertIsNone(wheel_segment(.5, .55))
        self.assertEqual(wheel_segment(.8, .55), 0)

    def test_storage_roundtrip_and_invalid_label(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "poses.json"
            store = PoseStore(path)
            with self.assertRaises(ValueError):
                store.add("../escape", [0.] * 63)
            store.add("open palm", [0.] * 63)
            store.save()
            loaded = PoseStore(path)
            loaded.load()
            self.assertEqual(loaded.samples, store.samples)

    def test_storage_rejects_wrong_feature_and_version(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "poses.json"
            for data in ({"version": 2, "samples": []},
                         {"version": 1, "samples": [{"label": "a", "feature": [0], "session": "x"}]}):
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    PoseStore(path).load()
        self.assertFalse(valid_feature([float("inf")] * 63))

    def test_classifier_requires_multiple_labels_and_samples(self):
        with self.assertRaises(ValueError):
            PoseClassifier([{"label": "one", "feature": [0.] * 63}] * 3)

    def test_classifier_recognizes_clusters_and_rejects_unknown(self):
        samples = ([{"label": "one", "feature": [0.] * 63}] * 3
                   + [{"label": "two", "feature": [1.] * 63}] * 3)
        model = PoseClassifier(samples)
        self.assertEqual(model.predict([0.01] * 63), "one")
        self.assertEqual(model.predict([1.01] * 63), "two")
        self.assertEqual(model.predict([.5] * 63), "Unknown")
        self.assertEqual(model.predict([0]), "Unknown")


if __name__ == "__main__":
    unittest.main()
