# Personal pinch calibration

This playground learns comfortable thumb-to-finger distances for **your selected hand and fingers**. You do not need to form a particular open-palm shape, fully straighten fingers, or touch the thumb tip exactly. Calibration only needs two reliably distinguishable distance states.

```powershell
# Right hand, index for primary action and middle for secondary action:
.\.venv\Scripts\python.exe -m gesture_control hand-calibration

# Choose a different pair on the other hand:
.\.venv\Scripts\python.exe -m gesture_control hand-calibration --dominant Left --primary-finger ring --secondary-finger pinky
```

The thumb is always the anchor. Choose any two different fingers from `index`, `middle`, `ring`, and `pinky`. The preview labels their roles; all other fingertips are marked `unused` and do not define the pinch action. Choose whichever pair gives you comfortable, repeatable movement. Tracking can still be inaccurate for any particular hand; calibration cannot repair incorrect landmark predictions.

## Capture three comfortable states

1. Hold your fingers comfortably **released**, without stretching. Hold briefly, then press **O**. This captures both selected distances.
2. Make the motion you want to mean primary action: bring your thumb and selected primary finger closer together. Hold briefly, then press **P**.
3. Do the same for your secondary finger, then press **R**.
4. Press **S** to validate and save. Once all observations are usable, the preview shows whether each calibrated pinch is on or off.

Each capture needs at least eight observations from the last 0.8 seconds. Capturing clears the observation buffer so you cannot immediately reuse the same frames for the next state. Missing tracking clears the live buffer. Repeat **O**, **P**, or **R** to replace a poor capture.

The calibrated thresholds are derived from the gap between the mean released and pressed distances. Separate engage and release thresholds provide hysteresis. Even a small movement range can work when it is larger than observed jitter. If the two states overlap or vary too much, saving is rejected; try another pair or a slower, steadier motion rather than stretching farther than is comfortable.

The lab never controls the desktop. Default save location is `%USERPROFILE%\.hand-control\pinch.json`. Use `--output PATH` to choose another location. It stores only the hand label, selected finger names, and four numeric thresholds, with a schema version. It does not store video, landmark recordings, anatomy descriptions, or medical information.

## Integration API

`load_pinch_profile(path)` validates and returns:

```json
{
  "version": 1,
  "dominant": "Right",
  "primary_finger": "index",
  "secondary_finger": "middle",
  "primary_on": 0.13,
  "primary_off": 0.17,
  "secondary_on": 0.174,
  "secondary_off": 0.246
}
```

Distances are thumb-tip to selected fingertip, normalized by wrist-to-middle-MCP distance in image pixels. `selected_distances(points, primary, secondary, width, height)` uses the same convention and returns the two distances. Thresholds must satisfy `0 < on < off <= 5`. Unknown or duplicate JSON fields, unsupported versions/fingers, and non-finite values are rejected.

The desktop app can use this profile through its separately integrated `--pinch-profile PATH` option. Try it in desktop **preview** before enabling real mouse output. Other experiments may have their own gesture mappings and do not automatically inherit this profile.

Automated tests cover reduced movement ranges, noisy or indistinguishable states, selected finger geometry, hysteresis validation, strict JSON loading, and save/load round trips. Personal hand tracking and threshold usability must still be tested on your camera.
