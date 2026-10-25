# Two-hand 3D workbench

```powershell
.\.venv\Scripts\python.exe -m gesture_control workbench
.\.venv\Scripts\python.exe -m gesture_control workbench --head
```

This is a standalone cube sandbox, not a Blender integration. It never sends desktop input.

- Pinch thumb and index on either hand, then move to translate the cube.
- Pinch with both hands, spread them to scale, or rotate the line connecting the hands to turn the cube around the screen axis.
- Release pinches to rest. Adding/removing a hand reanchors the manipulation, avoiding jumps. Missing hands release their clutch.
- **R** resets. **Esc/Q** exits using the experiment runtime.

The cube is shown as a wireframe over a dim camera image. Green fingertip markers indicate pinched hands. Scale and translation have bounds. These are virtual transformations derived from image-space movements; the app does not measure physical depth or millimeter dimensions.

`--head` uses face landmarks and an off-axis projection: your estimated eye position moves the view as though the display were a window. It needs the face landmark model from the shared runtime. Head position is an uncalibrated approximation using normalized eye-corner landmarks and a fixed eye-to-screen distance, not metric 6-DoF tracking. It is a single-viewer effect. Missing face tracking smoothly recenters the viewpoint. Fast head or hand movement and occlusions may still reduce tracking quality.

Unit tests cover scale bounds, pinch hysteresis, clutch reanchoring after loss/hand changes, coincident hands, angle wraparound, nonfinite observations, and finite off-axis projection. Actual camera and visual interaction have not been tested on the user's laptop.
