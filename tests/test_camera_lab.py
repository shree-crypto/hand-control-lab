import json
import math
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from gesture_control.experiments.camera_lab import Metrics, build_parser, json_safe, main


class MetricsTests(unittest.TestCase):
    def test_fps_uses_capture_sequence_not_consumer_message_count(self):
        metrics = Metrics()
        metrics.observe(1, 10, .2)
        metrics.observe(31, 11, .4)
        self.assertEqual(metrics.summary()["measured_fps"], 30)
        self.assertEqual(metrics.summary()["frames_captured"], 31)
        self.assertEqual(metrics.summary()["mean_pixel_brightness_0_1"], .3)

    def test_one_sample_does_not_invent_fps(self):
        metrics = Metrics()
        metrics.observe(7, 4)
        self.assertIsNone(metrics.summary()["measured_fps"])

    def test_duplicate_stale_and_nonfinite_samples_are_ignored(self):
        metrics = Metrics()
        metrics.observe(1, 10)
        metrics.observe(1, 11)
        metrics.observe(2, 9)
        metrics.observe(3, math.nan)
        self.assertEqual(metrics.summary()["frames_captured"], 1)

    def test_no_samples_is_json_serializable(self):
        data = Metrics().summary()
        self.assertEqual(data["frames_captured"], 0)
        json.dumps(data, allow_nan=False)

    def test_json_safe_handles_reported_enums_and_nonfinite_values(self):
        value = json_safe({"fps": math.inf, "shape": (640, 480), "custom": object()})
        self.assertIsNone(value["fps"])
        self.assertEqual(value["shape"], [640, 480])
        json.dumps(value, allow_nan=False)

    def test_expected_cli_flags(self):
        args = build_parser().parse_args(["--ir", "--list", "--camera", "1", "--duration", "2", "--output", "report.json"])
        self.assertTrue(args.ir)
        self.assertTrue(args.list)
        self.assertEqual(args.camera, 1)
        self.assertEqual(args.duration, 2)

    def test_missing_whircam_on_windows_is_graceful_before_spawning(self):
        output = io.StringIO()
        with patch("gesture_control.experiments.camera_lab.platform.system", return_value="Windows"), \
             patch("gesture_control.experiments.camera_lab.importlib.util.find_spec", return_value=None), \
             patch("gesture_control.experiments.camera_lab._run_source") as run, redirect_stdout(output):
            self.assertEqual(main(["--ir", "--list"]), 1)
        self.assertIn("whircam[full]", output.getvalue())
        run.assert_not_called()

    def test_ir_on_other_platform_is_graceful_before_spawning(self):
        output = io.StringIO()
        with patch("gesture_control.experiments.camera_lab.platform.system", return_value="Linux"), \
             patch("gesture_control.experiments.camera_lab._run_source") as run, redirect_stdout(output):
            self.assertEqual(main(["--ir", "--list"]), 1)
        self.assertIn("requires Windows", output.getvalue())
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
