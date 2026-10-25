# Personal finger drums and four-limb MIDI

Two new, independently selectable modes extend the earlier palm instrument. They start paused and use the existing MIDI transport and file recorder. No live output is enabled unless `--port` is explicitly supplied. No generic hand shape such as an open palm or a C shape is required for their calibration.

## Personal finger instrument

After Setup.bat, run **PersonalDrums.bat** or:

```powershell
.\.venv\Scripts\python.exe -m gesture_control finger-drums
```

The provisional four bindings are an editable example for a reduced-finger layout:

| Control | Default note |
| --- | --- |
| Left ring | Kick 36 |
| Left pinky | Snare 38 |
| Right index | Closed hi-hat 42 |
| Right middle | Open hi-hat 46 |

These are starting choices, not assumptions that those movements are comfortable or independently trackable. Thumbs and any other digit can be chosen instead; a control can be disabled in the saved profile. The program does not infer physical ability from finger names or length. The unused left index/middle and right ring/pinky tips do not participate in this instrument's detection.

### Calibration in the preview

1. Check the numbered selected fingertips on the preview. Move one selected digit at a time and verify its landmark follows the real movement. If a predicted fingertip is consistently wrong, do not use it as a musical control.
2. Press **1–4** to choose a binding (up to 10 configurable bindings; key 0 selects the tenth).
3. Hold a comfortable rest position briefly, then press **R**. Fully straight fingers are not necessary.
4. Make a small comfortable motion you want to mean a tap, hold briefly, then press **F**. Either movement direction is supported. No physical contact is required.
5. Repeat for the other selected controls. **K** saves the profile locally. A profile can be partially calibrated, but only calibrated enabled bindings generate notes.
6. **Space** arms/pauses. Move from calibrated rest toward tap, then release toward rest to rearm. Four independent movements can produce four notes in one frame. **S** saves MIDI, **C** clears the local take, **P** panics/pauses, Q/Esc exits with preview focus.

Capture needs at least five recent valid samples. Captured endpoints must be distinguishable from the observed tracking noise. Small movement is accepted when separable; the app rejects indistinguishable/noisy captures instead of requiring stretching farther. Controls normalize the chosen tip's movement relative to its own knuckle and a robust palm scale. They do not compare tip lengths to a generic hand or require other fingertips to be valid. Tracking loss, big jumps and frame gaps cancel pending taps.

Profiles are saved under `%USERPROFILE%\.hand-control\finger-drums.json`. They contain selected digit IDs, MIDI assignments and calibration numbers; no camera images are stored. **K** is the explicit save action. Moving the camera or changing your posture can require recalibration.

### Choose different controls or chord notes

```powershell
# Replace all bindings with your preferred four controls; recalibrate each one.
.\.venv\Scripts\python.exe -m gesture_control finger-drums --bind Left:thumb:36 Left:ring:38 Right:index:42 Right:middle:46

# Three comfortable controls assigned C/E/G; no particular hand shape is needed.
.\.venv\Scripts\python.exe -m gesture_control finger-drums --profile c-chord.json --bind Left:ring:60 Right:index:64 Right:middle:67

# Live FL Studio input and local MIDI capture.
.\.venv\Scripts\python.exe -m gesture_control finger-drums --port "HandControl" --record takes\personal.mid
```

`--bind` replaces the in-memory bindings and requires new calibration; K saves that configuration. `--sensitivity` (.25–4) changes the minimum movement-speed gate, not the calibrated endpoints. Higher is easier to trigger. `--fixed-velocity 100` avoids image-speed dynamics during first timing tests. `--hit-y` is only used in four-limb mode; finger mode uses its calibrated relative ranges.

The existing eight-key piano can also exclude unused fingers:

```powershell
.\.venv\Scripts\python.exe -m gesture_control piano --finger-profile "$env:USERPROFILE\.hand-control\finger-drums.json"
```

This option copies enabled finger choices only; that older piano mode still uses a camera strike line. Use the calibrated finger instrument with MIDI note assignments for small-range finger movements and fixed note/chord playing. It is not a held-note/sustain piano implementation.

## Four-limb instrument inspired by Lim and Lee

Run **SetupBody.bat** once to download the pose model, then **FourLimb.bat**. This is an original experimental implementation of the interaction pattern, **not a reproduction of the paper's measured pipeline**. There is no claim of matching its scores or latency. Reference: https://doi.org/10.54941/ahfe1008006

The camera must see both hand controls and both hips/knees with sufficient clarity. A laptop aimed at your face will usually not provide this view. Repositioning it farther away or using an external camera may be necessary; raising/lowering your laptop is not a software substitute for visibility.

- Left hand: snare 38.
- Right hand: hi-hat 42 closed / 46 open.
- Right knee: lift then return triggers kick 36.
- Left knee: raised/rest changes hi-hat openness; a closing stroke can trigger foot chick 44.

Both knees have independent rest/raised calibration. Select **1 left knee** or **2 right knee**, capture comfortable rest with R, raised position with F, and save with K. Raise only within a comfortable range; this is not an exercise protocol. Hidden or uncalibrated knees generate no foot hits. Knee values are measured relative to the same-side hip, reducing shared vertical-translation errors. Whole-body perspective changes still require recalibration. Limb labels come from pose inference on the unmirrored camera image, then coordinates are mirrored for display; check anatomical left/right in preview before live output.

Default hand controls use palm centers and a visible strike line. Move down through that line after a preparatory lift; no pinch or finger opening is required. With two hand strikes and both knee closures, the engine can report four concurrent note events. Left knee also has a continuous-control role; it is not a fourth freely positioned drumstick.

For a view in which small hand landmarks are unreliable, try red and blue markers on hand-held objects or sticks:

```powershell
.\.venv\Scripts\python.exe -m gesture_control four-limb --hand-mode markers --port "HandControl"
```

Red marks the left control, blue the right. This path uses HSV color tracking plus pose, without running hand-landmark inference. Choose a background without similarly sized red/blue objects. The software suppresses ambiguous similarly sized blobs. Color bounds are defaults in `four_limb.py`, not an automatic color-calibration wizard. No sticks are required for palm mode. Marker mode and palm mode are explicit alternatives.

In live mode the left knee also sends MIDI CC4 transitions (0 open / 127 closed). The receiving plugin must support/match that convention. Hi-hat note numbers are switched explicitly, so FPC can use mapped open/closed samples. Local MIDI files currently record notes/velocities, not the CC4 automation stream. Discrete hi-hat and foot-chick events remain in those files. See [FL Studio setup](midi-production.md) for port/FPC routing.

## Personalizing desktop controls too

The [pinch calibration lab](personal-hands.md) lets you choose any two fingers with the thumb anchor and learn comfortable release/contact distances. For example, right index/middle for pointer actions and left ring/pinky for scroll/precision:

```powershell
.\.venv\Scripts\python.exe -m gesture_control hand-calibration --dominant Right --output right-pinch.json
.\.venv\Scripts\python.exe -m gesture_control hand-calibration --dominant Left --primary-finger ring --secondary-finger pinky --output left-pinch.json
.\.venv\Scripts\python.exe -m gesture_control --pinch-profile right-pinch.json --other-pinch-profile left-pinch.json --precision
```

The last command is still preview only. Add `--control` only after checking the calibrated actions. A profile selects pointer/click and right-click fingers and learns thresholds; the other profile selects scroll and precision fingers with its own thresholds. Release the selected contacts briefly to engage; no mandatory open-palm shape. Existing unrelated gesture demos do not automatically inherit these profiles.

## What calibration does not solve

MediaPipe remains a generic pretrained hand/pose model. It may place shortened-finger landmarks incorrectly or infer movement where there is none. This build **does not retrain the neural network for your hands**. Calibration adjusts observed movements and chooses which landmarks matter; it cannot repair consistently wrong predictions. The marker/palm/knee route offers alternatives when finger landmarks do not work. We must evaluate the preview on your actual hands before treating any mapping as reliable.

Both systems remain experimental for music timing, particularly with 30 FPS capture, blur, occlusion or small movements. Tests exercise program logic and synthetic observations; they are not measurements of your tracking accuracy or musical performance. No camera video, medical descriptions or anatomy images are saved by these modes.
