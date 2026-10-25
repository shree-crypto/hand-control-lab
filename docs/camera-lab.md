# Camera Lab

This experiment inventories the camera streams the operating system actually exposes. It never injects desktop input, runs biometric authentication, or changes Windows security settings.

```powershell
# Probe RGB cameras 0 through 3; each probe includes startup in its deadline.
.\.venv\Scripts\python.exe -m gesture_control camera-lab --list --duration 3

# Preview RGB source 0 for up to 15 seconds and save its observed metrics.
.\.venv\Scripts\python.exe -m gesture_control camera-lab --camera 0 --duration 15 --output reports\rgb.json

# Capture metrics without a preview window.
.\.venv\Scripts\python.exe -m gesture_control camera-lab --no-preview --duration 10
```

Preview closes with **Esc**, **Q**, or its window close button. The measurement also stops at the requested deadline. Camera calls run in a spawned subprocess so a blocking driver read cannot indefinitely trap the main preview loop. A worker that fails to stop is terminated after a short grace period; the OS then reclaims its handles. The JSON records forced termination. RGB probing does not enumerate friendly device names: it tests numeric OpenCV indices.

## Optional infrared backend

[WHIRCAM](https://github.com/jacksonfcs/Windows-Hello-IR-Camera-Python) wraps Windows `MediaFrameSourceGroup` APIs and can expose IR devices omitted by OpenCV. Install its optional packages in a **separate environment** before trying this backend. This project does not install them automatically. For example, create another Python 3.12 environment, then install `whircam[full]` there. Run the project from that environment:

```powershell
python -m gesture_control camera-lab --ir --list --duration 10
python -m gesture_control camera-lab --ir --camera 0 --duration 10 --output reports\ir.json
```

`--camera` selects a WHIRCAM **group index** in IR mode, not an OpenCV camera index. The report includes wrapper-provided source information and formats when available. The optional `depth_available` field may appear inside `reported`; it remains a **hardware/driver claim**, not verified depth capture. This experiment intentionally previews IR intensity frames only. A `read_depth()` method in a library does not mean the laptop has a physical depth stream.

## Interpreting the report

- `actual_shape` and `dtype` describe delivered frames, rather than requested or advertised settings.
- `measured_fps` uses timestamps and sequence numbers generated where frames are captured. It does not count repeated preview redraws. It includes frames captured but dropped by the bounded preview queue.
- `frames_captured` is the most recently received producer sequence; a few final frames may not reach the parent at shutdown.
- `mean_pixel_brightness_0_1` is the average normalized pixel value of recent received frames. It is not calibrated light intensity and is not comparable between RGB and IR as a physical measurement.
- `depth_verified` stays false. This lab performs no depth calibration, measured-depth accuracy test, or RGB-to-IR registration.
- A successful IR preview says nothing by itself about hand/eye model accuracy, dark-room range, sensor synchronization, or simultaneous availability with Windows Hello.

Camera access can fail because of closed shutters, Windows permissions, another application, unavailable driver formats, protected sensor paths, or missing hardware. The tool reports the observed failure and preserves sign-in configuration. Improve room lighting and compare reports manually before considering IR as a tracking input.

Pure report/FPS utilities have automated tests. Actual RGB/IR access, frame formats, GUI preview and Windows driver behavior have not been tested in this cloud workspace or on the user's laptop.
