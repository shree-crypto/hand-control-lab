# Webcam control project survey

Research date: 2026-10-24. Exa searches requested 18 results across hand control and gaze/blink control, followed by direct repository, source-file, and license reads. Findings below are from documentation and static code inspection. None of these projects was run on the user's Windows laptop, and upstream claims of accuracy, frame rate, or reliability are not independently verified.

## Recommendation

Build a small original controller on the official [MediaPipe Hand Landmarker Tasks API](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python). Existing projects establish feasibility, but the closest desktop project has licensing ambiguity and observable interaction defects. Reuse the maintained tracking dependency and general interaction patterns; do not copy uncertain application code. Use VIDEO mode with increasing timestamps, two-hand detection, scale-normalized pinch thresholds, hysteresis, release-to-rearm actions, and explicit pause/engagement controls.

For the next eye phase, evaluate **EyeTrax** first in an overlay-only calibration experiment before enabling mouse injection. Gaze estimation and head-controlled cursor movement must be evaluated as different capabilities.

## Hand-control candidates

| Project | Evidence and license | Assessment |
| --- | --- | --- |
| [Rcidshacker/airmouse](https://github.com/Rcidshacker/airmouse) | Windows, two hands, cursor/click/drag/scroll, system shortcuts, SendInput/pynput, MediaPipe Tasks. README says MIT; [root contents](https://api.github.com/repos/Rcidshacker/airmouse/contents) contain no LICENSE file at inspection. Small project, not an established maintained platform. | Closest conceptual match, but avoid adopting wholesale. Actual source defects below contradict some polished README claims. |
| [NamanGaonkar/Dual-Hand-Virtual-Mouse-Visualization-](https://github.com/NamanGaonkar/Dual-Hand-Virtual-Mouse-Visualization-) | Dual-hand cursor, pinch clicks/scroll, OpenCV/MediaPipe/PyAutoGUI. [MIT license file](https://github.com/NamanGaonkar/Dual-Hand-Virtual-Mouse-Visualization-/blob/main/LICENSE) verified. | Small demonstration rather than a dependable desktop controller; README installation order and placeholder clone URL need correction. Candidate for ideas, not a reason to replace the original controller. |
| [happyananya/Hand-Gesture-and-Facial-Movement-Controlled-Virtual-Mouse](https://github.com/happyananya/Hand-Gesture-and-Facial-Movement-Controlled-Virtual-Mouse) | Documents hand mode and face mode, GUI launcher, sustained wink clicks. README claims MIT; standalone license not verified here. | Helpful separation of input modes. Face cursor explicitly uses head/nose movement, not calibrated eye gaze. |
| [abhishekprajapatt/gesturemouse](https://github.com/abhishekprajapatt/gesturemouse) | Documents Windows, dual-hand zoom, tray icon, pinch click/drag. | Repository metadata says MIT while README file tree says GPL-3.0. Verify actual license before reuse. README says ongoing research; no independent performance evidence. |

### Airmouse source findings

These are static findings in the default branch inspected on the research date; upstream may change.

- [right_hand.py](https://raw.githubusercontent.com/Rcidshacker/airmouse/main/core/gestures/right_hand.py): a held thumb-middle pinch triggers right-click repeatedly after each cooldown, without release-to-rearm. It emits a single click on the first pinch, then calls `double_click()` after a second quick pinch, resulting in three injected clicks for that pair. Pinch detection uses one fixed normalized-image 3D-distance threshold, without hand-size normalization or separate close/open thresholds.
- [left_hand.py](https://raw.githubusercontent.com/Rcidshacker/airmouse/main/core/gestures/left_hand.py): open palm, V sign, four fingers, and pinch shortcuts can repeat whenever cooldown elapses while the pose stays held. This can repeatedly toggle desktop or cycle windows. It does correctly release held Ctrl when the hand disappears.
- [tracker.py](https://raw.githubusercontent.com/Rcidshacker/airmouse/main/core/tracker.py): uses `RunningMode.IMAGE` for every webcam frame, rather than VIDEO/LIVE_STREAM temporal tracking. Handedness comments are inconsistent with each other, so mirror/label behavior needs an actual camera check.
- [requirements.txt](https://github.com/Rcidshacker/airmouse/blob/main/requirements.txt): unpinned OpenCV, MediaPipe, NumPy, screeninfo, pynput, psutil. This does not provide a reproducible installation.

## Eye and blink candidates

| Project | License / capability | Recommendation |
| --- | --- | --- |
| [ck-zhang/EyeTrax](https://github.com/ck-zhang/EyeTrax) | [MIT license verified](https://raw.githubusercontent.com/ck-zhang/EyeTrax/master/LICENSE). Actual calibrated screen-coordinate prediction, 5/9-point and dense calibration, optional smoothing, model persistence, blink flag. | Best next experiment. Its [gaze implementation](https://raw.githubusercontent.com/ck-zhang/EyeTrax/master/src/eyetrax/gaze.py) uses current FaceLandmarker Tasks VIDEO mode, eye/iris features and head orientation, then learned mapping. This is substantially more relevant than mapping a nose landmark to the screen. Needs accuracy/comfort evaluation locally. |
| [NativeSensors/EyeGestures](https://github.com/NativeSensors/EyeGestures) | [GPL-3.0 license verified](https://raw.githubusercontent.com/NativeSensors/EyeGestures/main/LICENSE). Webcam gaze software, calibration and fixation outputs. | Worth comparing if EyeTrax is inadequate. Python README example imports v4 but instantiates v3, so inspect a pinned release and working example rather than copying README blindly. GPL permits personal experimentation; account for its terms if distributing a combined application. |
| [antoinelame/GazeTracking](https://github.com/antoinelame/GazeTracking) | Repository declares MIT. Pupils, horizontal/vertical gaze ratios, eyes-closed flag. | Useful for coarse directional gestures and learning. Pupil coordinates and gaze ratios are not calibrated screen pixel coordinates. Dlib-based setup may be less convenient on Windows. |
| [google/project-gameface](https://github.com/google/project-gameface) | Apache-2.0, Windows/Android. Head movement and facial gestures. Archived September 5, 2025. | Good face-control reference, not a maintained gaze-pointer base. |
| [Dont-Copy-That-Floppy/Eye-Tracking-Cursor](https://github.com/Dont-Copy-That-Floppy/Eye-Tracking-Cursor) | GPL-3.0 metadata. README advertises single blink left-click, double blink right-click, long blink drag. | Do not adopt: source inspection reveals serious correctness gaps, detailed below. |

EyeTrax's inspected [pyproject.toml](https://raw.githubusercontent.com/ck-zhang/EyeTrax/master/pyproject.toml) specifies `numpy>=1.22,<2`, `mediapipe>=0.10`, scikit-learn, scipy, screeninfo, OpenCV, and pyvirtualcam. Its broad dependency ranges still need a tested Windows lockfile. Keep this optional eye experiment separate from the hand prototype's environment initially.

The purported Eye-Tracking-Cursor implementation is a useful warning against relying on feature lists. Its [blink_detector.py](https://raw.githubusercontent.com/Dont-Copy-That-Floppy/Eye-Tracking-Cursor/main/blink_detector.py) loads a **5-point** dlib predictor but accesses landmark indices **36–47**, which requires the 68-point model. Its function named `process_double_blink` is chosen by the duration of one closure, not two closures, and `double_blink_interval` is unused. Its [eye_tracker.py](https://raw.githubusercontent.com/Dont-Copy-That-Floppy/Eye-Tracking-Cursor/main/eye_tracker.py) maps the average eye-region landmark location, without tracking iris/pupil displacement; that primarily measures face/head position. Its [main.py](https://github.com/Dont-Copy-That-Floppy/Eye-Tracking-Cursor/blob/main/main.py) changes an app flag on stop without signalling the eye-tracker loop. Advertised feature completion is not evidence of working gaze control.

## Eye interaction design for phase two

Implement the user's single/double-blink mapping as an **optional calibrated experiment**. Natural blinks are frequent and should not click. Start with a deliberate long blink or asymmetric wink, or use gaze for pointing and a hand pinch for selection, while measuring false activations. Blink recognition should report closure/opening transitions, not click once per closed-eye video frame.

If single deliberate blink means left-click and two deliberate blinks mean right-click, delay the single-click until the second-blink interval expires. Otherwise a double blink will first perform an unwanted left-click. Freeze the pointer at the last stable open-eye location while closed; reject face loss and uncertain measurements; require reopening before another activation; add cooldown and explicit pause. Closure timing, bilateral thresholds, glasses, lighting, and gaze calibration must be tested with this user rather than treated as universal constants.

Suggested evaluation: overlay-only nine-point target task, median/95th-percentile target error, false click rate during ordinary reading, deliberate blink confusion matrix, recovery after head movement, and comfortable use over ten minutes. Desktop injection follows only after the overlay task is useful. No claim of precise eye navigation is justified from the laptop's IR/Windows Hello support alone.
