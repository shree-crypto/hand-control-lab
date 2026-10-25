# Validation and delivery

This source prototype was checked in a Linux/Python 3.12 workspace without a webcam, Windows input APIs, or installed model runtimes.

- 211 automated tests pass: gesture events, precision mapping, 3D math/clutches, gaze features/calibration/selections, drawing/audio mappings, pose storage/classification, camera metrics/process guards, backend reports, resource cleanup, drum/piano strike detection, MIDI scheduling/export, personalized finger calibration, calibrated knee/marker controls, custom pinch thresholds, excluded-digit handling, packaging metadata, launcher settings/routes and worker lifecycle.
- The 0.3.1 Python wheel builds successfully and installs into an isolated Python 3.12 environment without contacting a package index when dependencies are deliberately skipped for the packaging smoke check. Installed console entrypoints, route enumeration and headless self-test pass outside the source directory. This check does not install or validate the camera/MIDI dependencies.
- The Tkinter window's visual rendering and Windows executable/installer have not been tested in this headless Linux environment. Windows build scripts and CI workflow are provided; no native `.exe` or remote release has been built/published here.
- Every experiment's `--help` route runs without optional model dependencies.
- Python sources compile; metadata-only backend diagnostics run without models or downloads.
- No live MediaPipe inference, GUI interaction, Windows batch execution, Windows mouse injection, Windows audio, WHIRCAM IR access, WiLoR model loading or AMD CVML acceleration was validated in this workspace.
- Live MIDI transport into FL Studio, webcam hit accuracy and motion-to-audio latency are also untested. The included MIDI routing example is synthetic, not a camera performance recording.
- Personalized hand landmark placement, usable movement ranges, anatomical pose labeling and knee/marker accuracy require validation on the user's laptop. Synthetic tests with shortened or invalid excluded fingertips do not establish performance on real hands. The Lim/Lee-inspired mode is not an exact implementation of their evaluated pipeline.

Run checks from the project folder:

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 -m compileall -q gesture_control tools
py -3.12 -m gesture_control labs
py -3.12 -m gesture_control backends --doctor
```

First laptop trial: Setup.bat, SetupLabs.bat, then Labs.bat camera inspection and cube modes. Try gaze only after camera/face tracking works. Desktop output remains separate in Control.bat.

The distribution ZIP includes `history.bundle`, a portable local Git history. To create a separate checkout containing the feature commits, install Git and run `git clone history.bundle hand-control-history` from the extracted folder. The normal source folder runs without Git. No branch was pushed or published remotely.

Implemented experimental paths: RGB/conditional IR camera lab, two-hand cube, approximate head parallax, calibrated gaze with pinch/long closure/dwell, palm wheel, static-pose recording/classifier, air drawing, Windows audio instrument, facial expression lab, optional desktop precision and backend diagnostics/WiLoR image adapter. Actual IR hand/gaze inference, measured-depth manipulation, AMD native SDK integration, model performance claims and full desktop eye control remain future work.
