import unittest

from gesture_control.experiments.gaze import Calibration, Selection, extract_features, target_at


def face():
    points = [(0.0, 0.0, 0.0)] * 478
    for index, point in {33: (.30, .4, 0), 133: (.40, .4, 0), 159: (.35, .38, 0),
                         145: (.35, .42, 0), 468: (.35, .4, 0), 362: (.60, .4, 0),
                         263: (.70, .4, 0), 386: (.65, .38, 0), 374: (.65, .42, 0),
                         473: (.65, .4, 0), 1: (.50, .5, 0)}.items():
        points[index] = point
    return points


class GazeFeaturesTests(unittest.TestCase):
    def test_requires_iris_landmarks(self):
        self.assertIsNone(extract_features(None))
        self.assertIsNone(extract_features(face()[:468]))

    def test_rejects_degenerate_or_nonfinite_geometry(self):
        self.assertIsNone(extract_features([(0, 0, 0)] * 478))
        f = face()
        f[468] = (float("nan"), .4, 0)
        self.assertIsNone(extract_features(f))

    def test_iris_motion_changes_features_without_head_motion(self):
        f = face()
        before, ear = extract_features(f)
        f[468] = (.36, .4, 0)
        after, _ = extract_features(f)
        self.assertGreater(after[0], before[0])
        self.assertEqual(before[4:], after[4:])
        self.assertGreater(ear, .17)

    def test_eyelid_closure_changes_openness(self):
        f = face()
        for upper, lower in ((159, 145), (386, 374)):
            f[upper] = f[lower]
        self.assertEqual(extract_features(f)[1], 0)


class CalibrationTests(unittest.TestCase):
    def test_does_not_predict_before_calibration(self):
        self.assertIsNone(Calibration().predict((1, 2)))

    def test_fits_coordinate_relationship_and_bounds(self):
        features = [(x, y) for y in (0, .5, 1) for x in (0, .5, 1)]
        model = Calibration(.01)
        model.fit(features, features)
        predicted = model.predict((.2, .7))
        self.assertAlmostEqual(predicted[0], .2, delta=.02)
        self.assertAlmostEqual(predicted[1], .7, delta=.02)
        self.assertEqual(model.predict((-100, 100)), (0, 1))

    def test_rejects_invalid_samples(self):
        model = Calibration()
        with self.assertRaises(ValueError):
            model.fit([(0, 0)] * 4, [(0, 0)] * 4)
        with self.assertRaises(ValueError):
            model.fit([(float("nan"), 1)] * 5, [(0, 0)] * 5)

    def test_constant_inputs_remain_finite(self):
        model = Calibration()
        model.fit([(1, 1)] * 5, [(.2, .3)] * 5)
        self.assertAlmostEqual(model.predict((1, 1))[0], .2)


class SelectionTests(unittest.TestCase):
    def test_pinch_requires_release_and_fires_once(self):
        s = Selection()
        self.assertIsNone(s.update(0, 0, pinch=True))
        self.assertIsNone(s.update(.1, 0, pinch=False))
        self.assertEqual(s.update(.2, 0, pinch=True), 0)
        self.assertIsNone(s.update(.5, 0, pinch=True))

    def test_natural_blink_does_not_select(self):
        s = Selection("blink")
        s.update(0, 2)
        s.update(.1, 2, closed=True)
        self.assertIsNone(s.update(.25, 3))

    def test_deliberate_blink_selects_frozen_target(self):
        s = Selection("blink")
        s.update(0, 2)
        s.update(.1, 2, closed=True)
        s.update(.4, 4, closed=True)
        self.assertEqual(s.update(.7, 5), 2)
        self.assertIsNone(s.update(.8, 5))

    def test_too_long_closure_does_not_select(self):
        s = Selection("blink")
        s.update(0, 2)
        s.update(.1, 2, closed=True)
        self.assertIsNone(s.update(2, 2))

    def test_face_loss_cancels_blink_and_pinch(self):
        s = Selection("blink")
        s.update(0, 2)
        s.update(.1, 2, closed=True)
        s.update(.3, None, valid=False)
        self.assertIsNone(s.update(.7, 2))

    def test_dwell_fires_once_and_restarts_on_target_change(self):
        s = Selection("dwell", dwell=.8)
        s.update(0, 2)
        self.assertEqual(s.update(.9, 2), 2)
        self.assertIsNone(s.update(1.9, 2))
        s.update(2, 3)
        self.assertIsNone(s.update(2.5, 3))
        self.assertEqual(s.update(2.9, 3), 3)

    def test_face_loss_prevents_dwell_accumulation(self):
        s = Selection("dwell", dwell=.8)
        s.update(0, 2)
        s.update(.7, None, valid=False)
        self.assertIsNone(s.update(1, 2))
        self.assertIsNone(s.update(1.5, 2))

    def test_natural_blink_does_not_rearm_completed_dwell(self):
        s = Selection("dwell", dwell=.8)
        s.update(0, 2)
        self.assertEqual(s.update(.9, 2), 2)
        s.update(1, 2, closed=True)
        s.update(1.1, 2)
        self.assertIsNone(s.update(2.1, 2))

    def test_gutters_have_no_target(self):
        self.assertIsNone(target_at(None))
        self.assertIsNone(target_at((1 / 3, .25)))
        self.assertEqual(target_at((1 / 6, .25)), 0)


if __name__ == "__main__":
    unittest.main()
