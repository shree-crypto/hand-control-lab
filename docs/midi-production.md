# Air MIDI drums and mini piano for FL Studio

These modes generate **MIDI notes**, not a recording of synthesized drum audio. They can drive FPC, a sampler or a piano instrument in FL Studio through an existing MIDI port. They can also save a `.mid` file without any MIDI packages installed.

`examples/routing-check-100bpm.mid` is a generated two-bar kick/snare/hat example for checking note mappings by importing it into FL Studio. It is synthetic test data, not a recording of webcam performance.

## Start with drums

1. Run the existing **Setup.bat** for camera dependencies/model. Face tracking is not required.
2. Run **Drums.bat** for a preview/file-only session. Space arms/pauses. Lift your palm above the faint line, then strike downward through the yellow line in the desired region. Both hands work independently.
3. Four left-to-right regions send MIDI notes **36 kick, 38 snare, 42 closed hat, 46 open hat**. Those are General MIDI conventions, not a guarantee about the loaded FPC preset.
4. Press **S** to save a take under `HandControl\midi` in your user folder. This is MIDI data; without FL Studio or another synthesizer this mode is silent. **C** clears the local take; **P** sends panic and pauses. Q/Esc exits with the window focused.

Hits use palm center (the blue marker), not fingertips. A strike must have sufficient downward velocity and cross the line after a preparatory lift. A held-down hand, sideways sweep or shallow rebound does not repeatedly trigger. Missing/stale tracking cancels the trajectory. Dynamics are inferred from image-space speed, not measured force.

## Live FL Studio route on Windows

1. Install [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html), create a port named **HandControl**, and leave loopMIDI running. It creates the Windows virtual MIDI cable. The author's page lists older Windows releases; current driver behavior on this Windows 11 laptop has not been tested here.
2. Run **SetupMIDI.bat** to install optional `mido` and `python-rtmidi`. The script lists available output port names. Use the exact displayed name, which may include a suffix.
3. In **FL Studio → Options → MIDI Settings**, find that port under **Input**, enable it and select the generic controller type if no dedicated script exists. Ensure MIDI remote control is enabled. Do not route FL Studio's MIDI output back into this app.
4. Load **FPC**, select its channel, and load your drum sounds. Check each pad's MIDI note mapping against 36/38/42/46, or change our `--notes` values to match the preset. FL Studio may label MIDI octaves differently; use numeric note mappings rather than octave names alone.
5. From PowerShell in the extracted project folder:

```powershell
.\.venv\Scripts\python.exe -m gesture_control drums --list-ports
.\.venv\Scripts\python.exe -m gesture_control drums --port "HandControl" --record takes\drums.mid --bpm 120
```

6. In FL Studio select your pattern and FPC channel. Right-click Record and ensure **Notes** is selected, arm recording, then press Play. Our notes should light FL Studio's MIDI activity indicator and record into the selected instrument's piano roll. Space arms our detector while its own preview has focus; then leave it armed while you record in FL Studio. Q/Esc in our window exits it; they are not global shortcuts in these modes.

Windows RtMidi does not create virtual ports itself; `--port` opens an existing port. Omitting `--port` always means local preview/file capture only. No MIDI output is enabled implicitly.

Official references: [MIDI setup](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/app_wiz5.htm), [note recording](https://www.image-line.com/fl-studio-learning-content/fl-studio-online-manual/html/recording_scores.htm), [FPC pad mapping](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/plugins/FPC.htm), [RtMidi Windows virtual-port limitation](https://mido.readthedocs.io/en/stable/backends/rtmidi.html).

## Tuning and MIDI files

```powershell
# Adjust strike plane and make slower gestures easier to trigger.
.\.venv\Scripts\python.exe -m gesture_control drums --port "HandControl" --hit-y .65 --sensitivity 1.4

# Custom FPC notes, or fixed velocity when camera-derived dynamics are unstable.
.\.venv\Scripts\python.exe -m gesture_control drums --notes 36 40 42 46 --fixed-velocity 100

# Save on exit; optional 16th-note export quantization (OFF by default).
.\.venv\Scripts\python.exe -m gesture_control drums --record takes\beat.mid --bpm 120 --quantize .25

# Eight white notes C D E F G A B C starting at MIDI 60.
.\.venv\Scripts\python.exe -m gesture_control piano --port "HandControl" --record takes\piano.mid
```

File timing begins at the first recorded strike; the app does not synchronize to FL Studio transport or MIDI clock. Its BPM dot is a local visual guide, not a DAW metronome. Record live in FL Studio for song-position alignment. Export quantization changes file onsets only; live output remains unquantized. FL Studio has its own input-quantize settings, which can independently affect a recording. Files contain note events, velocities and a tempo event, not drum samples or plugin settings.

The mini piano is a **finger-tap experiment**, with all ten fingertips able to trigger an eight-white-key layout. It supports simultaneous taps/chords but uses fixed 0.25-second notes. It does not implement a full chromatic keyboard, held key durations, sustain pedal or hammer-action dynamics. Finger occlusion and coupled finger movement make it less reliable than the palm-based drum mode.

## Accuracy and latency: what remains to measure

This is a playable prototype for experimentation, not verified production-grade drum hardware. At 30 FPS, camera samples are about **33.3 ms apart**; at 60 FPS, about **16.7 ms**. Exposure, capture buffering, inference, MIDI delivery and FL Studio's audio buffer add more latency. Hardware-advertised FPS may exceed actual tracked-frame throughput. The UI shows tracked-frame throughput and software capture-to-handler delay; neither is a measurement of physical motion-to-audio latency.

The capture timestamp is when OpenCV returns the frame, not the sensor's exposure timestamp. Interpolated strike times improve the file's estimate of a line crossing; they cannot backdate an already-delivered live MIDI note or remove unpredictable capture delay. No model change can guarantee missing sub-frame motion is recovered.

Music modes request 640x480 at 60 FPS by default. `--fps 30`, `--fps 60` or `--fps 120` requests a different rate; drivers can ignore it. Use the measured tracked-frame throughput to judge what was actually achieved. Requesting 120 FPS does not add sensor capability or guarantee faster model inference.

For a production trial, use RGB, even lighting, a clear camera angle and a low-latency FL Studio audio configuration appropriate to your interface. Start with kick/snare at 80-100 BPM, then add hats. Measure missed hits, extra hits, velocity consistency and timing against FL Studio's metronome across repeated takes before attempting fast rolls. A constant offset can be calibrated; random jitter and missed hits remain problems even after quantization. A high-frame-rate camera, a physical pad or contact sensor may be needed if the built-in camera fails those tests. No extra hardware is needed for the first experiment.

Drum detector defaults include a 120 ms per-hand cooldown; piano uses 150 ms per finger. They intentionally suppress rapid retriggers and may reject fast repeated notes. Adjusting thresholds requires checking false positives again. No millimeter accuracy, guaranteed latency, fast-roll reliability or real-world hit accuracy has been established.

## Engineering checks

Note-offs use a background scheduler so normal inference delays do not leave notes held. Retriggers and panic release active notes. Physical device removal or blocked MIDI driver calls can still fail; the app reports backend errors. Never use a MIDI loopback configuration that creates a feedback loop.

Tests cover downward strikes, lift/rebound/cooldown rules, concurrent hands/fingers, capture gaps/jumps, velocity bounds, MIDI note-off scheduling, repeat-note behavior and parsed MIDI-file events. Real camera performance, Windows MIDI routing, FL Studio recording and audio latency have not been tested in this workspace.

Related projects examined as references, without copying code: [HandTrack_To_MIDI](https://github.com/frkatona/HandTrack_To_MIDI) and [Gestural-Midi-Instrument](https://github.com/iliasmahboub/Gestural-Midi-Instrument). Their MIDI routing examples support feasibility; their demos do not establish this laptop's timing performance. Webcam drum demos claiming millimeter accuracy or zero latency were not treated as measured evidence.
