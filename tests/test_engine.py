import unittest

from gesture_control.engine import Engine, Gate, Hand


def hand(index=1.0, middle=1.0, x=.5, y=.5):
    return Hand(x, y, index, middle)


def kinds(actions):
    return [a.kind for a in actions]


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.e = Engine()
        self.e.toggle()
        self.e.step(hand(), None, 0)
        self.e.step(hand(), None, .2)

    def test_starts_paused(self):
        e = Engine()
        self.assertEqual(e.step(hand(.1), None, 0), [])
        self.assertFalse(e.armed)

    def test_requires_open_hand_after_arming(self):
        e = Engine()
        e.toggle()
        for t in (0, .5, 1, 2):
            self.assertEqual(e.step(hand(.1), None, t), [])

    def test_short_pinch_one_click_on_release(self):
        self.assertNotIn("click", kinds(self.e.step(hand(.1), None, .3)))
        self.assertNotIn("click", kinds(self.e.step(hand(.1), None, .4)))
        self.assertEqual(kinds(self.e.step(hand(), None, .5)), ["click"])
        self.assertNotIn("click", kinds(self.e.step(hand(), None, .6)))

    def test_short_pinch_freezes_click_position(self):
        self.e.step(hand(), None, .25)
        self.assertNotIn("move", kinds(self.e.step(hand(.1, x=.8), None, .3)))
        self.assertNotIn("move", kinds(self.e.step(hand(x=.9), None, .5)))

    def test_two_pinches_produce_two_clicks_not_three(self):
        events = []
        for t, h in ((.3, hand(.1)), (.4, hand()), (.5, hand(.1)), (.6, hand())):
            events += kinds(self.e.step(h, None, t))
        self.assertEqual(events.count("click"), 2)

    def test_drag_down_once_up_once_without_extra_click(self):
        events = []
        for t, h in ((.3, hand(.1)), (.8, hand(.1)), (1, hand(.1)), (1.1, hand())):
            events += kinds(self.e.step(h, None, t))
        self.assertEqual(events.count("down"), 1)
        self.assertEqual(events.count("up"), 1)
        self.assertNotIn("click", events)

    def test_loss_releases_drag_immediately_and_disarms(self):
        self.e.step(hand(.1), None, .3)
        self.e.step(hand(.1), None, .8)
        self.assertEqual(kinds(self.e.step(None, None, .81)), ["up"])
        self.e.step(None, None, 1.5)
        self.assertFalse(self.e.armed)

    def test_missing_other_hand_does_not_stop_pointer(self):
        self.assertIn("move", kinds(self.e.step(hand(), None, .3)))

    def test_reacquiring_pinched_hand_cannot_click(self):
        self.e.step(hand(.1), None, .3)
        self.e.step(None, None, .35)
        self.assertEqual(self.e.step(hand(.1), None, .4), [])
        self.assertEqual(self.e.step(hand(), None, .5), [])

    def test_pause_releases_drag(self):
        self.e.step(hand(.1), None, .3)
        self.e.step(hand(.1), None, .8)
        self.assertEqual(kinds(self.e.toggle()), ["up"])
        self.assertFalse(self.e.armed)

    def test_right_click_does_not_repeat_while_held(self):
        events = []
        for t in (.3, .5, 1, 2):
            events += kinds(self.e.step(hand(middle=.1), None, t))
        self.assertEqual(events.count("right_click"), 1)
        self.e.step(hand(), None, 2.1)
        self.assertIn("right_click", kinds(self.e.step(hand(middle=.1), None, 2.2)))

    def test_scroll_cancels_pending_click(self):
        self.e.step(hand(.1), None, .3)
        self.e.step(hand(.1), hand(.1), .4)
        self.e.step(hand(), hand(.1, y=.3), .5)
        events = kinds(self.e.step(hand(), hand(), .6))
        self.assertNotIn("click", events)

    def test_scroll_releases_drag(self):
        self.e.step(hand(.1), None, .3)
        self.e.step(hand(.1), None, .8)
        self.assertEqual(kinds(self.e.step(hand(.1), hand(.1), .9)), ["up"])

    def test_scroll_direction_and_pointer_freeze(self):
        self.e.step(hand(), hand(.1), .3)
        actions = self.e.step(hand(), hand(.1, y=.3), .4)
        self.assertEqual(kinds(actions), ["scroll"])
        self.assertGreater(actions[0].x, 0)

    def test_pointer_is_bounded(self):
        actions = self.e.step(hand(x=4, y=-3), None, .3)
        self.assertEqual((actions[0].x, actions[0].y), (1, 0))

    def test_gate_has_hysteresis(self):
        gate = Gate()
        self.assertFalse(gate.update(.35))
        self.assertTrue(gate.update(.2))
        self.assertTrue(gate.update(.4))
        self.assertFalse(gate.update(.5))


if __name__ == "__main__":
    unittest.main()
