import math
from types import SimpleNamespace
import unittest

from gesture_control.experiments.workbench import Controller, Transform, cube_points, project


def hand(x, y=.5, pinch=.1):
    return SimpleNamespace(x=x, y=y, pinch=pinch)


class WorkbenchTests(unittest.TestCase):
    def test_one_hand_reanchors_after_loss(self):
        c = Controller()
        c.update({"Right": hand(.4)})
        c.update({"Right": hand(.5)})
        self.assertAlmostEqual(c.transform.x, .4)
        c.update({})
        c.update({"Right": hand(.9)})
        self.assertAlmostEqual(c.transform.x, .4)

    def test_switching_hand_count_does_not_jump(self):
        c = Controller()
        c.update({"Right": hand(.7)})
        c.update({"Right": hand(.8)})
        before = vars(c.transform).copy()
        c.update({"Right": hand(.8), "Left": hand(.2)})
        self.assertEqual(vars(c.transform), before)
        c.update({"Left": hand(.1)})
        self.assertEqual(vars(c.transform), before)

    def test_scale_is_bounded(self):
        c = Controller()
        c.update({"Left": hand(.4), "Right": hand(.5)})
        c.update({"Left": hand(-5), "Right": hand(5)})
        self.assertEqual(c.transform.scale, 2.5)
        c.update({"Left": hand(.4), "Right": hand(.401)})
        self.assertGreaterEqual(c.transform.scale, .2)

    def test_pinch_hysteresis(self):
        c = Controller()
        c.update({"Right": hand(.5, pinch=.2)})
        c.update({"Right": hand(.6, pinch=.4)})
        self.assertAlmostEqual(c.transform.x, .4)
        c.update({"Right": hand(.7, pinch=.6)})
        self.assertEqual(c.mode, ())

    def test_coincident_hands_no_division_by_zero(self):
        c = Controller()
        c.update({"Left": hand(.5), "Right": hand(.5)})
        c.update({"Left": hand(.5), "Right": hand(.8)})
        self.assertEqual(c.transform.scale, 1)

    def test_nonfinite_hand_releases_clutch(self):
        c = Controller()
        c.update({"Right": hand(.5)})
        c.update({"Right": hand(float("nan"))})
        self.assertEqual(c.mode, ())

    def test_angle_crossing_pi_is_continuous(self):
        c = Controller()
        c.update({"Left": hand(.7, .5), "Right": hand(.3, .501)})
        c.update({"Left": hand(.7, .5), "Right": hand(.3, .499)})
        self.assertLess(abs(c.transform.roll), .02)

    def test_project_rejects_invalid_near_plane(self):
        self.assertIsNone(project((0, 0, 4)))
        self.assertIsNone(project((0, 0, float("nan"))))
        self.assertIsNone(project((0, 0, -2), eye=(0, 0, 0)))

    def test_off_axis_parallax_varies_with_depth(self):
        self.assertEqual(project((.2, .3, 0), eye=(.5, 0, 4)), (.2, .3))
        near = project((0, 0, -1), eye=(.5, 0, 4))[0]
        far = project((0, 0, -3), eye=(.5, 0, 4))[0]
        self.assertGreater(far, near)

    def test_cube_extremes_remain_projectable(self):
        for point in cube_points(Transform(scale=2.5, roll=100)):
            projected = project(point, eye=(.8, -.6, 4))
            self.assertIsNotNone(projected)
            self.assertTrue(all(math.isfinite(v) for v in projected))


if __name__ == "__main__":
    unittest.main()
