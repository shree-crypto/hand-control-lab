from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from gesture_control import desktop_services as service
from gesture_control.desktop_entry import main
from gesture_control.paths import model_path


class DesktopServicesTests(unittest.TestCase):
    def test_midi_needs_explicit_enable(self):
        settings=service.Settings(midi_port='HandControl 1')
        self.assertNotIn('--port',service.launch_arguments('finger-drums',settings))
        args=service.launch_arguments('finger-drums',replace(settings,live_midi=True))
        self.assertEqual(args[args.index('--port')+1],'HandControl 1')
        self.assertNotIn('--port',service.launch_arguments('preview',replace(settings,live_midi=True)))

    def test_invalid_settings_and_modes_rejected(self):
        for settings in (service.Settings(camera=-1),service.Settings(fps=0),service.Settings(live_midi=True),
                         service.Settings(sensitivity=float('nan')),service.Settings(record_path='bad\x00file')):
            with self.assertRaises(ValueError):
                service.validate_settings(settings)
        with self.assertRaises(ValueError):
            service.launch_arguments('arbitrary-command',service.Settings())

    def test_user_paths_stay_separate_arguments(self):
        args=service.launch_arguments('piano',service.Settings(finger_profile='C:/My profiles/left.json'))
        self.assertIn('C:/My profiles/left.json',args)
        self.assertEqual(args.count('--finger-profile'),1)

    def test_personal_calibration_fingers_available_from_launcher(self):
        settings=service.Settings(dominant_hand='Left',primary_finger='ring',secondary_finger='pinky',pinch_profile='left.json')
        args=service.launch_arguments('hand-calibration',settings)
        self.assertEqual(args[args.index('--primary-finger')+1],'ring')
        self.assertEqual(args[args.index('--secondary-finger')+1],'pinky')
        self.assertEqual(args[args.index('--output')+1],'left.json')

    def test_settings_roundtrip_and_unknown_field_rejected(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(service,'app_data_dir',return_value=Path(folder)):
            settings=service.Settings(camera=2,finger_profile='profile.json')
            service.save_settings(settings)
            self.assertEqual(service.load_settings(),settings)
            (Path(folder)/'settings.json').write_text('{"shell_command":"no"}')
            with self.assertRaises(ValueError):
                service.load_settings()

    def test_worker_arguments_support_frozen_and_python(self):
        with patch.object(service.sys,'frozen',False,create=True):
            command=service.worker_command(['backends','--doctor'],Path('a b.log'),Path('stop'))
            self.assertIn('gesture_control.desktop_entry',command)
        with patch.object(service.sys,'frozen',True,create=True):
            command=service.worker_command(['backends','--doctor'],Path('a b.log'),Path('stop'))
            self.assertEqual(command[1],'--worker')
            self.assertIn('a b.log',command)

    def test_diagnostic_worker_really_runs_without_camera_dependencies(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(service,'app_data_dir',return_value=Path(folder)):
            controller=service.Controller()
            controller.start('backends',service.Settings())
            deadline=time.monotonic()+5
            try:
                while controller.running and time.monotonic()<deadline:
                    time.sleep(.02)
                self.assertEqual(controller.poll(),0)
                self.assertIn('runtime_probed',controller.read_log())
            finally:
                if controller.running:
                    controller.process.kill()
                    controller.process.wait(timeout=2)

    def test_stop_escalation_is_bounded_and_reaped(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(service,'app_data_dir',return_value=Path(folder)):
            controller=service.Controller()
            controller.process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
            controller.stop_path=Path(folder)/'stop'
            try:
                controller.stop()
                self.assertTrue(controller.stop_path.is_file())
                controller.deadline=time.monotonic()-1
                controller.poll()
                controller.process.wait(timeout=2)
                self.assertIsNotNone(controller.poll())
                self.assertFalse(controller.running)
            finally:
                if controller.process is not None and controller.process.poll() is None:
                    controller.process.kill()
                    controller.process.wait(timeout=2)

    def test_model_path_rejects_unknown_and_resolves_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'models').mkdir()
            model=root/'models'/'hand_landmarker.task'
            model.write_bytes(b'model')
            with patch('gesture_control.paths.app_data_dir',return_value=root/'cache'),patch.object(sys,'_MEIPASS',root,create=True):
                self.assertEqual(model_path('hand_landmarker.task'),model)
            with self.assertRaises(ValueError):
                model_path('../other.file')

    def test_self_test_headless_report(self):
        with tempfile.TemporaryDirectory() as folder,patch('builtins.print'):
            report=Path(folder)/'report.json'
            self.assertEqual(main(['--self-test','--report',str(report)]),0)
            data=json.loads(report.read_text())
            self.assertTrue(data['ok'])
            self.assertTrue(data['routes']['finger-drums'])


if __name__=='__main__':
    unittest.main()
