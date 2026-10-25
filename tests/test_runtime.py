import unittest
from gesture_control.experiments.runtime import hand_data
from gesture_control.experiments.face import Hold, measurements
from gesture_control.experiments.runtime import close_resource, run
from unittest.mock import Mock, patch


class RuntimeTests(unittest.TestCase):
    def test_invalid_landmarks_rejected(self):
        self.assertIsNone(hand_data([], 640, 480))
        self.assertIsNone(hand_data([(0, 0, float('nan'))] * 21, 640, 480))
        self.assertIsNone(hand_data([(0, 0, 0)] * 21, 640, 480))

    def test_valid_hand_pinch_normalized(self):
        points = [(0, 0, 0)] * 21
        points[9] = (.1, 0, 0)
        points[5] = points[13] = points[17] = (.1, 0, 0)
        points[8] = (.01, 0, 0)
        value = hand_data(points, 640, 480)
        self.assertAlmostEqual(value.pinch, .1)

    def test_excluded_fingertip_does_not_drop_entire_hand(self):
        points = [(0, 0, 0)] * 21
        for i in (5,9,13,17):
            points[i] = (.1,0,0)
        points[8] = (float('nan'),0,0)
        value = hand_data(points,640,480)
        self.assertIsNotNone(value)
        self.assertEqual(value.pinch,float('inf'))

    def test_face_hold_fires_once_until_released(self):
        hold = Hold()
        self.assertFalse(hold.update(True, 0))
        self.assertTrue(hold.update(True, .6))
        self.assertFalse(hold.update(True, 1))
        self.assertFalse(hold.update(False, 1.1))
        self.assertFalse(hold.update(True, 1.2))
        self.assertTrue(hold.update(True, 1.8))

    def test_face_loss_invalid(self):
        self.assertIsNone(measurements(None))
        self.assertIsNone(measurements([]))

    def test_early_missing_model_closes_handler(self):
        handler = Mock()
        with patch('pathlib.Path.is_file', return_value=False), patch('builtins.print'):
            self.assertEqual(run(handler), 1)
        handler.close.assert_called_once()

    def test_cleanup_failure_does_not_escape(self):
        resource = Mock()
        resource.close.side_effect = OSError('driver cleanup failed')
        with patch('builtins.print'):
            close_resource(resource)
        resource.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
