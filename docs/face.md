# Face expression sandbox

After Setup.bat and SetupLabs.bat, run `python -m gesture_control face` from the virtual environment, or select Face expressions in Labs.bat.

Look at the camera with a relaxed face and press **C** to calibrate. Raise your eyebrows or open your mouth and hold for half a second to trigger an on-screen event. Return to neutral to reset. Head tilt is shown as an approximate angle. Tracking loss cancels held gestures. All events remain inside this window; they do not change Windows or invoke shortcuts.

This is a simple geometry experiment, not a trained expression classifier or emotion detector. Camera perspective, glasses and individual facial geometry affect thresholds. C recalibrates at any time. Q/Esc exits with the window focused. Uses the regular RGB camera; no IR inference claim is made.
