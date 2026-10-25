from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gesture_control.experiments.midi_io import MidiOutput, NoteEvent, Recorder


class FakePort:
    def __init__(self):
        self.messages = []
        self.released = threading.Event()
        self.closed = False

    def send(self, message):
        self.messages.append(message)
        if message.type == 'note_off':
            self.released.set()

    def close(self):
        self.closed = True


def fake_mido(port):
    return SimpleNamespace(Message=lambda kind, **kw: SimpleNamespace(type=kind, **kw),
                           open_output=lambda name: port, get_output_names=lambda: ['loopMIDI Port'])


def read_events(data):
    """Small independent parser for our explicit-status format-0 output."""
    assert data[:4] == b'MThd'
    assert struct.unpack('>IHHH', data[4:14]) == (6, 0, 1, 480)
    assert data[14:18] == b'MTrk'
    length = int.from_bytes(data[18:22], 'big')
    track = data[22:]
    assert len(track) == length
    cursor = 0
    tick = 0
    events = []
    while cursor < len(track):
        delta = 0
        while True:
            byte = track[cursor]
            cursor += 1
            delta = (delta << 7) | (byte & 127)
            if byte < 128:
                break
        tick += delta
        status = track[cursor]
        cursor += 1
        if status == 255:
            kind, size = track[cursor:cursor+2]
            cursor += 2
            payload = track[cursor:cursor+size]
            cursor += size
            events.append((tick, status, kind, payload))
        else:
            note, velocity = track[cursor:cursor+2]
            cursor += 2
            events.append((tick, status, note, velocity))
    return events


class MidiTests(unittest.TestCase):
    def test_dry_run_does_not_import_mido(self):
        with patch('gesture_control.experiments.midi_io.importlib.import_module', side_effect=AssertionError('unexpected import')):
            output = MidiOutput()
            event = output.trigger(36, 100, 10)
            self.assertEqual(event, NoteEvent(10, 36, 100))
            output.panic()
            output.close()
        with self.assertRaises(RuntimeError):
            output.trigger(36, 100, 11)

    def test_ranges_are_checked(self):
        for kwargs in ({'time': float('nan')}, {'note': 128}, {'velocity': -1},
                       {'channel': 16}, {'duration': 0}, {'duration': float('inf')}, {'note': True}):
            params = dict(time=1, note=36, velocity=100)
            params.update(kwargs)
            with self.assertRaises(ValueError):
                NoteEvent(**params)

    def test_noteoff_runs_without_another_trigger(self):
        port = FakePort()
        with patch.dict(sys.modules, {'mido': fake_mido(port)}):
            output = MidiOutput('loopMIDI Port')
            try:
                output.trigger(36, 100, time.monotonic(), duration=.02)
                self.assertTrue(port.released.wait(1), 'Background scheduler did not release note')
                self.assertEqual([m.type for m in port.messages[:2]], ['note_on', 'note_off'])
            finally:
                output.close()
        self.assertTrue(port.closed)

    def test_old_deadline_does_not_release_retrigger(self):
        port = FakePort()
        with patch.dict(sys.modules, {'mido': fake_mido(port)}):
            output = MidiOutput('loopMIDI Port')
            try:
                now = time.monotonic()
                output.trigger(36, 90, now, duration=10)
                output.trigger(36, 100, now + 1, duration=10)
                self.assertEqual([m.type for m in port.messages], ['note_on', 'note_off', 'note_on'])
                with output._condition:
                    output._release_due_locked(now + 10.5)
                    self.assertIn((9, 36), output._active)
                    self.assertEqual(len(port.messages), 3)
                    output._release_due_locked(now + 11)
                    self.assertNotIn((9, 36), output._active)
                    self.assertEqual(port.messages[-1].type, 'note_off')
            finally:
                output.close()

    def test_panic_releases_notes_and_sends_channel_modes(self):
        port = FakePort()
        with patch.dict(sys.modules, {'mido': fake_mido(port)}):
            output = MidiOutput('loopMIDI Port')
            output.trigger(40, 100, time.monotonic(), duration=10)
            output.panic()
            self.assertFalse(output._active)
            controls = [m.control for m in port.messages if m.type == 'control_change']
            self.assertEqual(controls, [64, 123, 120])
            output.close()

    def test_missing_optional_package_has_actionable_error(self):
        with patch('gesture_control.experiments.midi_io.importlib.import_module', side_effect=ImportError('not found')):
            with self.assertRaisesRegex(RuntimeError, 'python-rtmidi'):
                MidiOutput.list_ports()


class RecordingTests(unittest.TestCase):
    def save(self, recorder, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            target = recorder.save(Path(directory) / 'nested' / 'take.mid', **kwargs)
            return read_events(target.read_bytes())

    def test_simultaneous_hits_duration_and_tempo(self):
        recorder = Recorder()
        recorder.record(NoteEvent(10, 36, 100, .1))
        recorder.record(NoteEvent(10, 42, 70, .2))
        recorder.record(NoteEvent(10.5, 38, 90, .1))
        events = self.save(recorder)
        self.assertEqual(events[0], (0, 255, 81, (500000).to_bytes(3, 'big')))
        notes = [event for event in events if event[1] != 255]
        self.assertEqual(notes, [(0, 153, 36, 100), (0, 153, 42, 70),
                                 (96, 137, 36, 0), (192, 137, 42, 0),
                                 (480, 153, 38, 90), (576, 137, 38, 0)])
        self.assertEqual(events[-1][1:3], (255, 47))

    def test_explicit_start_preserves_leading_silence(self):
        recorder = Recorder(start_time=10)
        recorder.record(NoteEvent(11, 36, 100))
        notes = [event for event in self.save(recorder) if event[1] != 255]
        self.assertEqual(notes[0][0], 960)

    def test_quantization_is_optional_and_preserves_note_length(self):
        recorder = Recorder(start_time=0)
        recorder.record(NoteEvent(.19, 36, 100, .1))
        original = [event for event in self.save(recorder) if event[1] != 255]
        quantized = [event for event in self.save(recorder, quantize=.25) if event[1] != 255]
        self.assertEqual(original[0][0], 182)
        self.assertEqual(quantized[0][0], 240)
        self.assertEqual(quantized[1][0] - quantized[0][0], 96)

    def test_retrigger_clips_old_noteoff_before_new_noteon(self):
        recorder = Recorder(start_time=0)
        recorder.record(NoteEvent(0, 36, 100, 1))
        recorder.record(NoteEvent(.1, 36, 110, 1))
        notes = [event for event in self.save(recorder) if event[1] != 255]
        self.assertEqual(notes, [(0, 153, 36, 100), (96, 137, 36, 0),
                                 (96, 153, 36, 110), (1056, 137, 36, 0)])

    def test_simultaneous_same_note_coalesces_but_other_channels_remain(self):
        recorder = Recorder(start_time=0)
        recorder.record(NoteEvent(0, 60, 70, .1, channel=0))
        recorder.record(NoteEvent(0, 60, 100, .2, channel=0))
        recorder.record(NoteEvent(0, 60, 80, .1, channel=1))
        notes = [event for event in self.save(recorder) if event[1] != 255]
        self.assertEqual(notes, [(0, 144, 60, 100), (0, 145, 60, 80),
                                 (96, 129, 60, 0), (192, 128, 60, 0)])

    def test_quantization_collision_has_only_one_noteoff(self):
        recorder = Recorder(start_time=0)
        recorder.record(NoteEvent(.1, 36, 90, .1))
        recorder.record(NoteEvent(.11, 36, 100, .2))
        notes = [event for event in self.save(recorder, quantize=.25) if event[1] != 255]
        self.assertEqual(notes, [(120, 153, 36, 100), (312, 137, 36, 0)])

    def test_invalid_start_tempo_quantization_rejected(self):
        with self.assertRaises(ValueError):
            Recorder(start_time=-1)
        recorder = Recorder(start_time=5)
        with self.assertRaises(ValueError):
            recorder.record(NoteEvent(4, 36, 100))
        for params in ({'bpm': 0}, {'bpm': float('nan')}, {'quantize': 0},
                       {'bpm': 1e-300}, {'quantize': 1e-300}):
            with self.assertRaises(ValueError):
                self.save(recorder, **params)


if __name__ == '__main__':
    unittest.main()
