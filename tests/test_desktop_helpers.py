import unittest

from gesture_control.desktop import App, describe_mode, model_status_text, worker_status


class DesktopHelperTests(unittest.TestCase):
    def test_missing_model_status_identifies_missing_names(self):
        text = model_status_text({"hand": True, "face": False})
        self.assertIn("face", text)
        self.assertNotIn("hand", text)

    def test_ready_models(self):
        self.assertEqual(model_status_text({"hand": True}), "Models ready")
        self.assertIn("not checked", model_status_text({}))

    def test_worker_status_distinguishes_exit_failure(self):
        self.assertIn("Running", worker_status(True, 1))
        self.assertIn("Ready", worker_status(False))
        self.assertIn("Finished", worker_status(False, 0))
        self.assertIn("problem", worker_status(False, 1))

    def test_descriptions_distinguish_os_control_from_playgrounds(self):
        self.assertIn("Windows", describe_mode("control"))
        self.assertIn("without moving", describe_mode("preview"))
        self.assertIn("playground", describe_mode("gaze"))
        self.assertIn("Choose", describe_mode("unknown-mode"))


class FakeWidget:
    def __init__(self):
        self.value = None
        self.destroyed = False
        self.callbacks = []

    def configure(self, **kwargs):
        self.value = kwargs

    def set(self, value):
        self.value = value

    def after(self, delay, callback):
        self.callbacks.append(callback)

    def destroy(self):
        self.destroyed = True


class ShutdownTests(unittest.TestCase):
    def test_window_survives_until_worker_is_reaped(self):
        class Controller:
            running = True
            stopped = False
            polls = 0

            def stop(self):
                self.stopped = True

            def poll(self):
                self.polls += 1
                if self.polls >= 2:
                    self.running = False

        app = App.__new__(App)
        app.closed = False
        app.controller = Controller()
        app.root = FakeWidget()
        app.start_button = FakeWidget()
        app.stop_button = FakeWidget()
        app.status = FakeWidget()
        app.close()
        self.assertTrue(app.controller.stopped)
        self.assertFalse(app.root.destroyed)
        app.root.callbacks.pop(0)()
        self.assertFalse(app.root.destroyed)
        app.root.callbacks.pop(0)()
        self.assertTrue(app.root.destroyed)


if __name__ == "__main__":
    unittest.main()
