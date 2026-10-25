import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from gesture_control.engine import Engine, Gate
from gesture_control.app import observation
from gesture_control.experiments.four_limb import FourLimbEngine
from gesture_control.experiments.hand_profile import Binding, HandProfile
from gesture_control.experiments.finger_drums import FingerDrumEngine
from gesture_control.experiments.midi_io import MidiOutput
from gesture_control.experiments.personalized_midi import PersonalInstrument, save_knees, validate_knees
from gesture_control.experiments.hand_calibration import selected_distances


def args(path=None):
    return SimpleNamespace(piano=False,record=None,bpm=120,quantize=None,fixed_velocity=None,
                           channel=10,hit_y=.62,hand_mode='markers',profile=path)


def hand(value):
    points=[(.5,.5,0)]*21
    points[0]=(.5,.8,0)
    points[16]=(.55,.5+value*.3,0)
    points[8]=points[12]=(float('nan'),0,0)
    return SimpleNamespace(points=points)


class Frame:
    shape=(480,640,3)
    def copy(self):
        return self


class PersonalIntegrationTests(unittest.TestCase):
    def test_pinch_selected_fingers_ignore_other_invalid_tips(self):
        points=hand(.05).points
        self.assertIsNotNone(selected_distances(points,'ring','pinky'))

    def test_noisy_endpoint_is_not_accepted_as_small_movement(self):
        profile=HandProfile([Binding('Left','ring',36,'Kick')])
        lab=PersonalInstrument(FingerDrumEngine(profile),MidiOutput(),args(),profile)
        for i in range(8):
            lab.calibration_key(SimpleNamespace(hands={'Left':hand(0)},now=i*.03,key=ord('r') if i==7 else -1))
        for i in range(8):
            lab.calibration_key(SimpleNamespace(hands={'Left':hand(.02 if i%2 else -.02)},now=.3+i*.03,key=ord('f') if i==7 else -1))
        self.assertFalse(profile.bindings[0].calibrated)
        self.assertIn('noise',lab.status)
        lab.close()
    def test_knee_dataclasses_roundtrip(self):
        engine=FourLimbEngine()
        engine.calibrate_knee('Left',.3,.2)
        engine.calibrate_knee('Right',.25,.15)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'knees.json'
            save_knees(path,engine.calibration)
            decoded=validate_knees(json.loads(path.read_text()))
            self.assertEqual(decoded['Left'],{'rest':.3,'raised':.2})

    def test_capture_small_calibration_with_excluded_digits_invalid(self):
        profile=HandProfile([Binding('Left','ring',36,'Kick')])
        lab=PersonalInstrument(FingerDrumEngine(profile),MidiOutput(),args(),profile)
        for i in range(8):
            lab.calibration_key(SimpleNamespace(hands={'Left':hand(0)},now=i*.03,key=ord('r') if i==7 else -1))
        for i in range(8):
            lab.calibration_key(SimpleNamespace(hands={'Left':hand(.05)},now=.3+i*.03,key=ord('f') if i==7 else -1))
        self.assertTrue(profile.bindings[0].calibrated)
        self.assertFalse(lab.enabled)
        lab.close()

    def test_stale_marker_frame_never_detected(self):
        engine=FourLimbEngine(hand_mode='markers')
        lab=PersonalInstrument(engine,MidiOutput(),args())
        lab.enabled=True
        ctx=SimpleNamespace(hands={},pose=None,now=2.,captured_at=None,key=-1,frame=Frame())
        with patch.dict(sys.modules,{'cv2':MagicMock()}), patch('gesture_control.experiments.four_limb.detect_markers') as detect:
            lab.process(ctx)
        detect.assert_not_called()
        self.assertEqual(lab.recorder.events,[])
        lab.close()

    def test_selected_pointer_finger_and_custom_gate_thresholds(self):
        points=[SimpleNamespace(x=.5,y=.5)]*21
        points[0]=SimpleNamespace(x=.5,y=.8)
        points[16]=SimpleNamespace(x=.7,y=.4)
        h=observation(points,640,480,16,20)
        self.assertEqual((h.x,h.y),(.7,.4))
        engine=Engine(primary_thresholds=(.11,.16),secondary_thresholds=(.2,.25),scroll_thresholds=(.3,.35))
        self.assertFalse(engine.index.update(.12))
        self.assertTrue(engine.index.update(.10))
        self.assertTrue(engine.index.update(.14))
        self.assertFalse(engine.index.update(.17))

    def test_cc4_dry_run_and_validation(self):
        output=MidiOutput()
        output.control_change(4,127)
        with self.assertRaises(ValueError):
            output.control_change(4,128)
        output.close()
        with self.assertRaises(RuntimeError):
            output.control_change(4,0)


if __name__=='__main__':
    unittest.main()
