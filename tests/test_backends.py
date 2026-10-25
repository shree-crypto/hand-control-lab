import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gesture_control.experiments.backends import capability_report, main, summarize, validate_image


class FakeArray:
    shape = (1000000, 3)
    dtype = "float32"


class BackendTests(unittest.TestCase):
    def test_array_summary_does_not_serialize_values(self):
        self.assertEqual(summarize(FakeArray()),
                         {"type": "FakeArray", "shape": [1000000, 3], "dtype": "float32"})

    def test_nested_summary_is_bounded_and_json_safe(self):
        output = summarize({str(i): [float("nan")] * 100 for i in range(100)})
        self.assertEqual(output["_omitted_entries"], 80)
        self.assertLess(len(json.dumps(output, allow_nan=False)), 8000)

    def test_deep_summary_is_truncated(self):
        value = {"a": {"b": {"c": {"d": [1, 2, 3]}}}}
        self.assertTrue(summarize(value)["a"]["b"]["c"]["d"]["truncated"])

    def test_default_report_does_not_import_runtime(self):
        with patch("gesture_control.experiments.backends.package_status", return_value={"module_available": False}):
            report = capability_report()
        self.assertFalse(report["runtime_probed"])
        self.assertNotIn("onnxruntime_available_providers", report)
        self.assertIn("wilor_mini", report["packages"])

    def test_invalid_input_path_and_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                validate_image(Path(directory) / "missing.png")
            path = Path(directory) / "model.pkl"
            path.write_bytes(b"x")
            with self.assertRaises(ValueError):
                validate_image(path)

    def test_image_size_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.png"
            with path.open("wb") as output:
                output.truncate(50 * 1024 * 1024 + 1)
            with self.assertRaises(ValueError):
                validate_image(path)

    def test_reports_write_error_without_traceback(self):
        with patch("gesture_control.experiments.backends.capability_report", return_value={"ok": True}):
            self.assertEqual(main(["--output", "/missing-parent/report.json"]), 1)


if __name__ == "__main__":
    unittest.main()
