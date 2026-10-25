# Four-limb drumming engine

This experimental implementation combines two independent hand strikes with two calibrated knee controls. It is inspired by camera-based drumming interaction ideas; it is not a validated or literal replication of a Lim/Lee paper. Webcam timing and MIDI/audio latency have not been tested on the user's laptop.

Default mapping:

| Control | MIDI output |
| --- | --- |
| Left hand downward strike | Snare 38 |
| Right hand downward strike | Closed hi-hat 42, or open hi-hat 46 while left knee is raised |
| Right knee returns downward after a lift | Kick 36 |
| Left knee raises / lowers | Opens / closes hi-hat; closing can trigger foot-chick 44 |

The left knee acts as a hi-hat pedal. It is not an arbitrary fourth instrument. Both hands, the kick and the pedal close can trigger in the same frame. Fixed hand mappings do not depend on which quarter of the image the hand occupies.

## Inputs and calibration

`FourLimbEngine.update(hands, pose, now, markers=None)` returns note `Hit` values with `time`, `note`, `velocity`, `duration`, `hand`, and `label` (`pad` is an alias for label). Use captured-frame timestamps for `now` to estimate motion independently of inference delays. MIDI playback still needs to be dispatched using current runtime time.

The `pose` input contains 33 MediaPipe anatomical landmarks `(x, y, z, visibility)`. `knee_measure(pose, side)` returns normalized knee Y minus same-side hip Y when both landmarks have visibility >= .6 and are inside the image. This subtracts shared vertical body translation; it does not remove every perspective or pose change.

Calibrate each knee personally with `engine.calibrate_knee('Left', rest_value, raised_value)` and the equivalent Right call. Record rest and raised values from the same seated camera setup, with hips and knees visible. The endpoints determine direction, so no fixed body-proportion assumption is used. Endpoints must differ by at least .015 in normalized image coordinates. `engine.calibration` stores `KneeCalibration(rest, raised)` values. `reset()` clears pending movement but retains these calibrations. Recalibrate after moving the camera or changing seating position.

`knee_status`, `knee_progress`, `hat_open`, and `hat_available` support UI feedback. Progress zero is the personal rest endpoint and one the raised endpoint. Raised progress >= .65 arms a return; passing below .35 closes the pedal/fires a kick when fast enough. Per-knee cooldown and stale/gap/jump guards suppress duplicate strikes.

Missing or low-visibility knees suppress foot events. The hi-hat retains its last known state during loss (`hat_available=False`) and establishes state silently on reacquisition. This does not infer unseen foot movement. Hand strikes can continue independently.

`cc_events` exposes optional `ControlChange(time, control=4, value)` transitions from the latest update. The convention here is 0=open, 127=closed, and may differ between plugins. These are metadata for the caller to route; the engine itself sends no MIDI. Discrete note mapping works without routing CC4.

## Marker option

`hand_mode='markers'` uses `markers={'Left': (x,y), 'Right': (x,y)}` instead of hand-landmarker output. This path does not need hand landmarks. `detect_markers(frame)` provides a lightweight HSV blob detector with lazy OpenCV/NumPy imports: **red labels Left, blue labels Right**, regardless of screen side. Wear/hold the corresponding color and avoid similarly colored clothing/backgrounds.

Color bounds can be supplied as `ColorRange` values to `detect_markers(frame, colors=...)`. Red includes a second hue interval for HSV wraparound. Tiny/oversized blobs and similar-size competing blobs are rejected. Marker centroids use the same clutched downward crossing detector as palms, with a visible preparatory lift and per-hand cooldown. Markers are ordinary visible RGB color, not tracked by the IR camera. Illumination, motion blur and occlusion can still cause missed markers.
