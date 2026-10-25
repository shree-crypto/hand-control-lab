import unittest
from gesture_control.engine import Engine, PointerMapper


class PrecisionTests(unittest.TestCase):
    def test_gain_and_no_jump_on_switch(self):
        mapper = PointerMapper()
        self.assertEqual(mapper.update(.5, .5), (.5, .5))
        self.assertAlmostEqual(mapper.update(.7, .5, .2)[0], .54)
        self.assertAlmostEqual(mapper.update(.7, .5, 1)[0], .54)
        self.assertAlmostEqual(mapper.update(.8, .5, 1)[0], .64)

    def test_target_clamped(self):
        mapper = PointerMapper()
        mapper.update(.5, .5)
        self.assertEqual(mapper.update(3, -2), (1, 0))

    def test_default_is_unchanged(self):
        self.assertFalse(Engine().precision_enabled)
        self.assertTrue(Engine(precision=True).precision_enabled)


if __name__ == "__main__":
    unittest.main()
