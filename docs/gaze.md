# Calibrated gaze playground

Run after installing the base requirements and downloading both hand and face landmark models:

```powershell
.\.venv\Scripts\python.exe -m gesture_control gaze
.\.venv\Scripts\python.exe -m gesture_control gaze --select blink
.\.venv\Scripts\python.exe -m gesture_control gaze --select dwell --dwell 1.2
```

This mode selects **six large tiles inside its own camera window**. It never moves the Windows cursor or clicks desktop controls. Calibration coordinates belong to the preview window; moving/resizing that window changes the relationship and requires recalibration.

## Calibrate and play

Keep your normal sitting position, use even lighting, and look at each yellow marker in the preview. Hold your gaze for a moment and press **Space**. The app averages at least eight recent open-eye observations, then advances to the next marker. Nine markers are the default; `--points 5` gives a quicker, less comprehensive trial. Press **R** at any time to restart.

Once calibrated, look at the large tiles and watch the pink estimated-gaze pointer. The yellow tile outline is the candidate. Selection flashes green:

- `--select pinch` (default): release your thumb-index pinch first, then pinch to select. Either tracked hand works; right hand takes precedence if both are visible. Separate engage/release thresholds reduce repeated activation.
- `--select blink`: close both eyes deliberately for **0.45–1.5 seconds**, then reopen. The selected tile is the one before closure. The pointer freezes during closure. Ordinary shorter blinks and excessively long closures do nothing. Eye-openness thresholds vary by person; adjust `--blink-threshold` if necessary, in the sandbox first.
- `--select dwell`: hold the same target for the configured interval. One selection fires until you leave that target. Closing eyes or losing the face cancels the timer.

Face loss cancels selection state. Natural single/double blinking is **not** wired to left/right desktop click in this version. Distinguishing deliberate closure from natural behavior still requires personal testing.

## What the algorithm does

This is an original lightweight baseline, not a bundled EyeTrax implementation. MediaPipe iris centers are measured relative to eye corners. The features also include nose-to-eye geometry and eye-center position to account partly for head pose/translation. A regularized linear model maps those features to preview coordinates using your calibration examples. Prediction smoothing trades responsiveness for stability.

The implementation uses actual iris-relative features, rather than labeling nose movement as eye tracking. However, it has no accuracy guarantee, calibration-quality scoring, independent ground truth, learned confidence estimate, or robust compensation for large head motion. A poor or constant calibration can still produce a prediction; assess its behavior against all six tiles and recalibrate if needed. Invalid geometry/face loss disables selection. IR imagery and glasses reflections have not been validated.

The ordinary RGB camera is the intended source. For a later comparison, [EyeTrax](https://github.com/ck-zhang/EyeTrax) provides a more established calibrated gaze library; it should be evaluated in a separate environment before integration.

Automated tests cover iris-feature sensitivity, degenerate geometry, calibration fit/bounds, pinch debouncing, natural versus deliberate closures, frozen blink targets, dwell timing, and face-loss reset. Hardware inference and real-user gaze accuracy remain untested here.
