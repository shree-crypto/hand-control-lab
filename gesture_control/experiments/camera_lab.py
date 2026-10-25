# SPDX-License-Identifier: GPL-3.0-only
"""Bounded RGB/IR camera diagnostics, isolated from desktop control.

Camera drivers may block inside read(). Camera work therefore runs in a spawned
process; the parent remains responsive and can stop a stalled driver process.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, field
import importlib.util
import json
import math
import multiprocessing as mp
from pathlib import Path
import platform
from queue import Empty, Full
import time


@dataclass
class Metrics:
    """Summarize producer frame timestamps, not preview-loop iterations."""
    first_timestamp: float | None = None
    last_timestamp: float | None = None
    frame_count: int = 0
    brightness: deque = field(default_factory=lambda: deque(maxlen=120))

    def observe(self, sequence: int, timestamp: float, brightness: float | None = None):
        if sequence < 1 or not math.isfinite(timestamp):
            return
        if self.last_timestamp is not None and timestamp < self.last_timestamp:
            return
        if sequence <= self.frame_count:
            return
        if self.first_timestamp is None:
            self.first_timestamp = timestamp
            self._first_sequence = sequence
        self.last_timestamp = timestamp
        self.frame_count = sequence
        if brightness is not None and math.isfinite(brightness):
            self.brightness.append(brightness)

    def summary(self):
        elapsed = (self.last_timestamp - self.first_timestamp
                   if self.first_timestamp is not None and self.last_timestamp is not None else 0)
        frames_since_first = self.frame_count - getattr(self, "_first_sequence", self.frame_count)
        return {
            "frames_captured": self.frame_count,
            "measured_fps": round(frames_since_first / elapsed, 2) if elapsed > 0 else None,
            "sample_span_seconds": round(elapsed, 3),
            "mean_pixel_brightness_0_1": (round(sum(self.brightness) / len(self.brightness), 4)
                                          if self.brightness else None),
        }


def json_safe(value):
    """Camera wrapper metadata can contain enums or NumPy scalars."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return str(value)


def _put_latest(queue, message):
    try:
        queue.put_nowait(message)
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
        try:
            queue.put_nowait(message)
        except Full:
            pass


def _worker(options, queue, stop):
    """Runs only in a spawned process; imports and driver calls stay bounded."""
    cap = None
    sequence = 0
    try:
        if options["operation"] == "list_ir":
            import whircam
            queue.put({"kind": "groups", "groups": json_safe(whircam.find_groups())})
            return
        import cv2
        import numpy as np
        if options["ir"]:
            import whircam
            cap = whircam.IRCam(group=options["camera"])
            info = {
                "source": "infrared", "camera_index": options["camera"],
                "reported": json_safe(getattr(cap, "info", {})),
                "formats": json_safe(getattr(cap, "formats", [])),
                "advertised_fps": json_safe(getattr(cap, "fps", None)),
            }
        else:
            backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
            cap = cv2.VideoCapture(options["camera"], backend)
            if not cap.isOpened():
                raise RuntimeError(f"Camera {options['camera']} could not be opened")
            info = {
                "source": "rgb", "camera_index": options["camera"],
                "advertised_fps": json_safe(float(cap.get(cv2.CAP_PROP_FPS))),
                "reported_width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "reported_height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            }
        queue.put({"kind": "opened", "info": info})
        while not stop.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError("Camera read returned no frame")
            sequence += 1
            timestamp = time.monotonic()
            maximum = np.iinfo(frame.dtype).max if np.issubdtype(frame.dtype, np.integer) else 1.0
            message = {
                "kind": "frame", "sequence": sequence, "timestamp": timestamp,
                "info": info,
                "shape": list(frame.shape), "dtype": str(frame.dtype),
                "brightness": float(frame.mean()) / maximum,
            }
            if options["preview"]:
                message["frame"] = frame
            _put_latest(queue, message)
    except Exception as exc:
        # Avoid exception reprs containing handles/pointers or full camera buffers.
        _put_latest(queue, {"kind": "error", "error": f"{type(exc).__name__}: {exc}"})
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        # A bounded/latest-frame queue may still hold buffered frames at stop.
        # Do not let its feeder keep the camera worker alive indefinitely.
        if sequence:
            queue.cancel_join_thread()


def _run_source(*, camera=0, infrared=False, duration=10.0, preview=False, list_ir=False):
    context = mp.get_context("spawn")
    queue = context.Queue(maxsize=4)
    stop = context.Event()
    options = {"operation": "list_ir" if list_ir else "capture",
               "camera": camera, "ir": infrared, "preview": preview}
    process = context.Process(target=_worker, args=(options, queue, stop), daemon=True)
    report = {"source": "infrared" if infrared else "rgb", "camera_index": camera,
              "status": "starting", "depth_verified": False}
    metrics = Metrics()
    started = time.monotonic()
    last_frame = None
    cv2 = None
    if preview:
        import cv2 as cv2_module
        cv2 = cv2_module
    process_started = False
    try:
        process.start()
        process_started = True
        while time.monotonic() - started < duration:
            if cv2 is not None:
                key = cv2.waitKey(1) & 0xff
                if key in (27, ord("q")):
                    report["stopped_by_user"] = True
                    break
            try:
                message = queue.get(timeout=0.03)
            except Empty:
                if not process.is_alive():
                    report["status"] = "error"
                    report.setdefault("error", "Camera process exited without a final report")
                    break
                continue
            if message["kind"] == "groups":
                report.update(status="ok", groups=message["groups"])
                break
            if message["kind"] == "opened":
                report.update(message["info"])
                report["status"] = "opened"
            elif message["kind"] == "error":
                report.update(status="error", error=message["error"])
                break
            elif message["kind"] == "frame":
                report.update(message["info"])
                metrics.observe(message["sequence"], message["timestamp"], message["brightness"])
                report.update(status="ok", actual_shape=message["shape"], dtype=message["dtype"])
                last_frame = time.monotonic()
                if cv2 is not None:
                    frame = message["frame"]
                    # Convert high-bit-depth IR to a preview only; keep report dtype intact.
                    if frame.dtype.name != "uint8":
                        frame = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype("uint8")
                    if len(frame.shape) == 2:
                        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                    else:
                        frame = frame.copy()
                    fps = metrics.summary()["measured_fps"]
                    cv2.putText(frame, f"{report['source'].upper()} camera {camera} | {fps or 0:.1f} FPS", (10, 25),
                                cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 220, 255), 2)
                    cv2.putText(frame, "Esc/Q closes | diagnostics only", (10, 52),
                                cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 220, 255), 1)
                    cv2.imshow("Camera Lab", frame)
                    if cv2.getWindowProperty("Camera Lab", cv2.WND_PROP_VISIBLE) < 1:
                        report["stopped_by_user"] = True
                        break
        if report["status"] in ("starting", "opened"):
            report.update(status="timeout", error="No camera frames/groups arrived before the deadline")
        elif last_frame is not None and time.monotonic() - last_frame > 2 and not report.get("stopped_by_user"):
            report.update(status="stalled", error="No new camera frame for more than two seconds")
    finally:
        stop.set()
        if process_started:
            process.join(timeout=0.5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
                report["worker_terminated_after_timeout"] = True
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            if not process.is_alive():
                process.close()
        queue.cancel_join_thread()
        queue.close()
        if cv2 is not None:
            cv2.destroyAllWindows()
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    if not list_ir:
        report.update(metrics.summary())
    return report


def build_parser():
    parser = argparse.ArgumentParser(description="Inspect actual RGB/IR camera capability. No desktop input is generated.")
    parser.add_argument("--ir", action="store_true", help="Use optional Windows whircam IR backend")
    parser.add_argument("--list", action="store_true", help="List IR source groups or probe RGB indices")
    parser.add_argument("--camera", type=int, default=0, help="RGB index or whircam group index")
    parser.add_argument("--duration", type=float, default=10, help="Maximum seconds per source, including startup (default: 10)")
    parser.add_argument("--max-index", type=int, default=3, help="Highest RGB index to probe with --list (default: 3)")
    parser.add_argument("--output", type=Path, help="Optional local JSON report path")
    parser.add_argument("--no-preview", action="store_true", help="Capture metrics without opening a window")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be a finite positive number")
    if args.camera < 0 or not 0 <= args.max_index <= 20:
        parser.error("--camera must be nonnegative; --max-index must be between 0 and 20")
    if args.ir and platform.system() != "Windows":
        print("IR discovery requires Windows and an exposed Windows Hello IR source. RGB mode remains available.")
        return 1
    dependency = "whircam" if args.ir else "cv2"
    if importlib.util.find_spec(dependency) is None:
        if args.ir:
            print('Optional IR backend is missing. In a separate Windows environment, install: python -m pip install "whircam[full]"')
        else:
            print("OpenCV is missing. Run the project's Setup.bat or install requirements.txt.")
        return 1
    if args.ir and not args.list and importlib.util.find_spec("cv2") is None:
        print('IR capture also needs NumPy/OpenCV; install whircam[full] in a separate environment.')
        return 1
    print("Camera Lab: no mouse/keyboard output. IR, physical depth and predicted depth are separate capabilities.", flush=True)
    try:
        if args.list and not args.ir:
            reports = []
            for index in range(args.max_index + 1):
                print(f"Probing RGB camera {index} (up to {args.duration:g}s)...", flush=True)
                report = _run_source(camera=index, duration=args.duration)
                reports.append(report)
                print(f"  {report['status']}: {report.get('actual_shape', report.get('error', ''))}", flush=True)
        else:
            reports = [_run_source(camera=args.camera, infrared=args.ir, duration=args.duration,
                                   preview=not (args.list or args.no_preview), list_ir=args.list and args.ir)]
        result = {"schema_version": 1, "platform": platform.system(), "cameras": reports,
                  "notes": ["Advertised FPS may differ from delivered FPS.",
                            "Brightness is a normalized mean pixel value, not calibrated illuminance.",
                            "Depth capability is reported metadata only; no depth accuracy is verified.",
                            "No inference model, authentication, or desktop-control action is run."]}
        encoded = json.dumps(json_safe(result), indent=2, allow_nan=False)
        print(encoded)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n", encoding="utf-8")
            print(f"Saved report: {args.output}")
        return 0 if any(r["status"] == "ok" for r in reports) else 1
    except (OSError, RuntimeError, ImportError) as exc:
        print(f"Camera Lab stopped: {exc}")
        return 1
    except KeyboardInterrupt:
        print("Camera Lab stopped by user.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
