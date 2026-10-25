# Hand Control — first Windows prototype

## Install and open the desktop app

With Python 3.12 x64, clone this repository (or extract the supplied source), install once, then open **Hand Control** with no batch scripts:

```powershell
git clone https://github.com/shree-crypto/hand-control-lab.git
cd hand-control-lab
py -3.12 -m pip install ".[midi]"
hand-control
```

The native launcher has experiment selection, saved camera/MIDI/profile settings, Start/Stop, model downloads and activity messages. `hand-control-gui` opens the same app without a console window on Windows. For a downloaded wheel, use the [Python installation instructions](docs/python-install.md). This package is supplied directly; it has not been published to PyPI.

A [Windows executable/installer build](docs/windows-install.md) is included for a Windows runner. No prebuilt Windows installer is supplied or claimed tested in this source release. The older batch scripts below remain optional source-development shortcuts.

A local webcam controller for Windows 11/10. Original gesture logic built on Google's MediaPipe Hand Landmarker Tasks API. **Controls the desktop after sign-in; does not unlock Windows.** No camera video is saved or uploaded. Setup downloads packages and Google's model once; normal use works offline.

## Get started on your ASUS laptop

1. Install **Python 3.12, Windows x64** from https://www.python.org/downloads/windows/ with the Python launcher enabled.
2. Extract the entire project ZIP to a normal folder, such as `Documents\HandControl`. Don't run it from inside the ZIP.
3. Double-click **Setup.bat**. Internet is needed for packages and the hand model. Administrator privileges are not needed.
4. Double-click **Preview.bat**. Open the camera privacy shutter. Start in a well-lit room with both hands visible.
5. Press **F8**, then open your fingers for a moment. Verify hand labels, tracking, the yellow pointer, and events in the preview. This mode does not move the Windows cursor.
6. Quit the preview with **Esc**, then run **Control.bat**. It starts paused. Press **F8** and open your hands to enable actual mouse control.

**F8 pauses/resumes globally on Windows. Esc quits globally on Windows. Q quits when the preview has focus.** Close the preview window or press Ctrl+C in the console to stop as well. Keep your physical mouse available during trials. Your ordinary Escape key will also quit this prototype when you use it in another application.

## Gestures

| Hand | Gesture | Action |
| --- | --- | --- |
| Right (default dominant) | Move index fingertip | Move pointer within the marked camera rectangle |
| Right | Touch thumb to index, then release within 0.4 seconds | Left click at the pointer's position before the pinch |
| Right | Hold thumb-index pinch for 0.4 seconds, then move | Drag; release fingers to drop |
| Right | Touch thumb to middle finger with index unpinched | One right-click; release to reset |
| Left | Hold thumb-index pinch and move that hand up/down | Scroll; right hand must remain visible |
| Both | Open fingers briefly after enabling/reacquiring tracking | Return to pointer mode |

Use small movements and rest your elbows. The marked rectangle maps to the entire **primary monitor**. The preview is mirrored. If hand labels don't match your intended pointer hand, pass `--dominant Left`. Pinch distances are normalized to palm size and use separate engage/release thresholds to reduce chatter. They may still need tuning for your hands/camera.

Short pinches freeze pointer movement to reduce click drift. Longer holds become drags. Make two separate short pinches for a double click; whether Windows recognizes them as a double click depends on its timing setting and your speed. There is no special auto-double-click gesture.

Scrolling cancels an in-progress click/drag, then requires neutral fingers before pointer input resumes. Losing the dominant hand immediately releases a drag. After more than 0.6 seconds without that hand, control pauses and requires F8 again. Brief loss also requires open fingers before resuming. Camera frames older than 0.3 seconds are ignored. Camera capture runs on a background thread so a stalled camera doesn't block hotkey polling. A completely hung inference call or terminated process is outside these guarantees.

## Options and troubleshooting

Run these from PowerShell in the extracted project folder:

```powershell
# Try a different camera if the RGB webcam isn't camera zero.
.\.venv\Scripts\python.exe -m gesture_control --camera 1

# Use your left hand as the pointer, right hand for scrolling.
.\.venv\Scripts\python.exe -m gesture_control --control --dominant Left

# Run gesture-state tests (does not need webcam, Windows, or third-party packages).
py -3.12 -m unittest discover -s tests -v
```

- **Camera unavailable:** close Teams/Zoom/other camera programs, open the privacy shutter, and enable Windows Settings → Privacy & security → Camera → camera access and desktop app camera access. Try `--camera 1`.
- **No hands detected:** improve lighting, move a little farther back, keep the palm and fingertips visible. Ordinary RGB is the intended source; IR-only footage is not validated.
- **Wrong hand controls pointer:** use `--dominant Left`; watch the on-screen Left/Right labels.
- **Pinches unreliable:** thresholds are in `gesture_control/engine.py` (`Gate.update`). Test changes in preview first.
- **Jitter or lag:** try a steady camera position and clear background. Inference runs at 640×480 requested camera resolution on CPU; actual resolution/FPS depend on the camera. NPU acceleration is not implemented.
- **Doesn't control an administrator application:** Windows restricts input across integrity levels. Test against ordinary desktop apps. This prototype does not drive the lock screen or UAC secure desktop.
- **F8 doesn't respond:** try Fn+F8 if your keyboard uses media functions by default. Physical Escape exits on Windows while the app loop is responsive.
- **Setup fails:** read the console error; use Python 3.12 x64 and check internet access. Direct package versions are pinned to a compatible API baseline; installation and transitive dependencies have not been verified on this laptop.

## Implementation and validation

`gesture_control/engine.py` is independent of camera/Windows APIs. `app.py` converts hand landmarks into normalized observations and draws feedback. `windows.py` sends mouse actions through Win32 `SendInput` and moves the primary-monitor cursor. Windows hotkeys use key-state polling, not a keyboard recording hook. No Windows system settings are changed.

Automated tests exercise click counts, right-click repetition, drag release, tracking loss, hysteresis, scroll priority, and pointer bounds. **Camera inference, Windows input injection, hotkeys, and end-to-end latency have not been tested on your laptop or on a Windows machine in this workspace.** This is a source prototype, not a packaged installer or production accessibility tool.

## Experimental playgrounds

**Personal controls update:** [Personal finger drums and four-limb MIDI](docs/personal-drums.md) add selectable/calibrated digits and palm/marker-plus-knee drumming. Start **PersonalDrums.bat** for the finger preview; **SetupBody.bat**, then **FourLimb.bat** for body controls. The new finger mode starts with left ring/pinky and right index/middle, each uncalibrated until you capture comfortable rest/tap positions. Thumb substitutions and other mappings are configurable. [Hand calibration](docs/personal-hands.md) also personalizes desktop pinch fingers/thresholds. Generic landmark-model accuracy still needs checking on your hands.

**Music production update:** [Air MIDI drums and piano](docs/midi-production.md) can send actual note/velocity events to FL Studio through an explicitly selected MIDI port, or export `.mid` takes. Start with **Drums.bat** for file-only preview; **Piano.bat** opens the eight-white-key finger-tap experiment. **SetupMIDI.bat** installs optional live MIDI dependencies. Windows needs an existing loopMIDI or equivalent port. Camera-based music timing has not been validated for production use.

Run **SetupLabs.bat** after Setup.bat to download the face model, then **Labs.bat** for the experiment menu. These playgrounds never inject Windows mouse/keyboard actions. Use Q/Esc with the window focused to exit them. Desktop control still uses Control.bat and starts paused.

| Mode | What you can try | Guide |
| --- | --- | --- |
| `camera-lab` | RGB discovery, frame-rate/format/brightness reports; optional IR preview via WHIRCAM | [Camera lab](docs/camera-lab.md) |
| `workbench` / `workbench --head` | Two-hand cube manipulation and optional head-coupled 3D perspective | [3D workbench](docs/workbench.md) |
| `gaze` | Calibrated iris-based gaze with pinch selection inside six sandbox tiles | [Gaze](docs/gaze.md) |
| `gaze --select blink` / `--select dwell` | Deliberate long closure or dwell selection; no natural-blink desktop clicks | [Gaze](docs/gaze.md) |
| `draw` / `music --audio` | Air canvas and optional Windows audio instrument | [Creative tools](docs/creative.md) |
| `gestures` / `record --label peace` | Palm command wheel and local static-pose samples/classifier | [Gestures](docs/gestures.md) |
| `face` | Calibrated eyebrow/mouth gestures and head-tilt feedback | [Face](docs/face.md) |
| `backends` | Dependency/provider diagnostics and optional WiLoR image experiment | [Backends](docs/backends.md) |

Use the virtual-environment Python for CLI commands, for example:

```powershell
.\.venv\Scripts\python.exe -m gesture_control workbench --head
.\.venv\Scripts\python.exe -m gesture_control gaze --select blink
.\.venv\Scripts\python.exe -m gesture_control record --label peace
.\.venv\Scripts\python.exe -m gesture_control --control --precision
```

The desktop `--precision` option enables fine pointer movement while the other hand pinches **thumb to middle finger**. Thumb-index remains scroll. Fine mode applies 20% movement gain, preserving the pointer position when changing modes; release the pinch for normal gain. This option changes pointer mapping to relative deltas, so re-enable tracking to recenter its mapping if needed. It is off by default.

The gaze lab uses an original lightweight calibration model, not bundled EyeTrax. IR support is conditional on a separately installed WHIRCAM environment and exposed camera streams. AMD NPU acceleration is not integrated; diagnostics and native CVML evaluation instructions are provided. WiLoR inference is optional, isolated and unbenchmarked. No measured depth or precise gaze accuracy is claimed.

Automated tests cover state machines, geometry, calibration math, data validation and cleanup. GUI rendering, Windows launch scripts, audio, live inference, IR access and end-to-end behavior remain untested on the laptop. Feature implementation and review history are saved as separate local Git commits on `main`.

Project code: GNU General Public License v3.0 only (GPL-3.0-only). Third-party packages and Google's downloaded model retain their respective licenses; see their upstream distributions and [MediaPipe](https://github.com/google-ai-edge/mediapipe).
