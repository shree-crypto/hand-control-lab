# SPDX-License-Identifier: GPL-3.0-only
"""Webcam UI. Preview is the default; --control explicitly enables OS output."""
import argparse
import math
from pathlib import Path
import platform
import threading
import time

from .engine import Engine, Hand
from .paths import model_path

ROOT = Path(__file__).resolve().parent.parent
EDGES = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7),
         (7, 8), (5, 9), (9, 10), (10, 11), (11, 12), (9, 13),
         (13, 14), (14, 15), (15, 16), (13, 17), (0, 17),
         (17, 18), (18, 19), (19, 20))


class Capture:
    """Keep only the latest frame so camera stalls do not block the UI/hotkeys."""
    def __init__(self, cv2, index, fps=30):
        self.cv2 = cv2
        self.index = index
        self.requested_fps = fps
        self.frame = None
        self.sequence = 0
        self.timestamp = 0.0
        self.error = None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        cap = None
        try:
            backend = self.cv2.CAP_DSHOW if platform.system() == "Windows" else self.cv2.CAP_ANY
            cap = self.cv2.VideoCapture(self.index, backend)
            if not cap.isOpened():
                raise RuntimeError(f"Cannot open camera {self.index}. Close camera apps, open privacy shutter, check Windows camera permissions, or try --camera 1.")
            cap.set(self.cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(self.cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(self.cv2.CAP_PROP_FPS, self.requested_fps)
            while not self.stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Camera stopped delivering frames. Restart with camera available.")
                with self.lock:
                    self.frame = frame
                    self.sequence += 1
                    self.timestamp = time.monotonic()
        except Exception as exc:
            self.error = str(exc)
        finally:
            if cap is not None:
                cap.release()

    def latest(self):
        with self.lock:
            return self.frame, self.sequence, self.timestamp

    def close(self):
        self.stop.set()
        self.thread.join(timeout=0.5)


def observation(points, width, height, primary=8, secondary=12):
    def distance(a, b):
        return math.hypot((points[a].x - points[b].x) * width,
                          (points[a].y - points[b].y) * height)
    scale = max(distance(0, 9), 1.0)
    return Hand(points[primary].x, points[primary].y, distance(4, primary) / scale,
                distance(4, secondary) / scale)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local hand control. Defaults to preview only; no mouse output.")
    parser.add_argument("--control", action="store_true", help="Allow mouse output on Windows (starts paused)")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--precision", action="store_true", help="Other thumb-middle pinch enables fine pointer movement")
    parser.add_argument("--dominant", choices=("Left", "Right"), default="Right", type=str.title)
    parser.add_argument('--pinch-profile', type=Path, help='Personal thresholds/fingers saved by hand-calibration')
    parser.add_argument('--other-pinch-profile', type=Path, help='Other hand profile: primary scroll, secondary precision')
    parser.add_argument('--scroll-finger', choices=('index','middle','ring','pinky'), default='index')
    parser.add_argument('--precision-finger', choices=('index','middle','ring','pinky'), default='middle')
    parser.add_argument("--model", type=Path, default=model_path('hand_landmarker.task'))
    args = parser.parse_args(argv)
    from .experiments.hand_calibration import load_pinch_profile, FINGERS
    pinch_profile = None
    other_profile = None
    if args.pinch_profile:
        try:
            pinch_profile = load_pinch_profile(args.pinch_profile)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        args.dominant = pinch_profile['dominant']
    if args.other_pinch_profile:
        try:
            other_profile = load_pinch_profile(args.other_pinch_profile)
        except (ValueError,OSError) as exc:
            parser.error(str(exc))
        if other_profile['dominant'] == args.dominant:
            parser.error('Other-hand profile must use the opposite hand')
    if args.control and platform.system() != "Windows":
        parser.error("--control requires Windows 11/10. Preview can run on other systems.")
    if not args.model.is_file():
        print("Hand model missing. Use Download models in the launcher or run hand-control --download-models")
        return 1
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
    except ImportError as exc:
        print(f"Missing dependency: {exc}. Run: python -m pip install -r requirements.txt")
        return 1
    backend = None
    if platform.system() == "Windows":
        from .windows import Windows
        backend = Windows(args.control)
    engine = Engine(precision=args.precision,
                    primary_thresholds=(pinch_profile['primary_on'],pinch_profile['primary_off']) if pinch_profile else (.30,.48),
                    secondary_thresholds=(pinch_profile['secondary_on'],pinch_profile['secondary_off']) if pinch_profile else (.30,.48),
                    scroll_thresholds=(other_profile['primary_on'],other_profile['primary_off']) if other_profile else (.30,.48),
                    precision_thresholds=(other_profile['secondary_on'],other_profile['secondary_off']) if other_profile else (.30,.48))
    capture = None
    detector = None
    title = "Hand Control - " + ("WINDOWS OUTPUT ENABLED" if args.control else "PREVIEW ONLY")
    print(title)
    print("F8: enable/pause | Esc: quit globally on Windows | Q: quit with preview focused")
    primary_name = pinch_profile['primary_finger'] if pinch_profile else 'index'
    secondary_name = pinch_profile['secondary_finger'] if pinch_profile else 'middle'
    scroll_name = other_profile['primary_finger'] if other_profile else args.scroll_finger
    print(f"{args.dominant} hand: pointer, thumb-{primary_name} primary action, thumb-{secondary_name} right click.")
    print(f"Other hand: thumb-{scroll_name} + move up/down to scroll. Primary monitor only.")
    def apply(actions):
        if backend:
            backend.apply(actions)
    try:
        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(args.model)),
            running_mode=vision.RunningMode.VIDEO, num_hands=2,
            min_hand_detection_confidence=0.6, min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.6)
        detector = vision.HandLandmarker.create_from_options(options)
        capture = Capture(cv2, args.camera)
        cv2.namedWindow(title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(title, 800, 600)
        last_sequence = -1
        last_ms = -1
        last_draw = None
        events = ""
        fps = 0.0
        previous_inference = None
        start = time.monotonic()
        while True:
            key = cv2.waitKey(1) & 0xff
            if key in (27, ord("q")) or (backend and backend.pressed(0x1B)):
                break
            if (backend and backend.pressed(0x77)) or (not backend and key == ord(" ")):
                apply(engine.toggle())
            if capture.error:
                raise RuntimeError(capture.error)
            frame, sequence, stamp = capture.latest()
            now = time.monotonic()
            if frame is None or now - stamp > 0.3:
                apply(engine.step(None, None, now))
                if now - start > 10 and frame is None:
                    raise RuntimeError("Camera did not start within 10 seconds.")
                if last_draw is not None:
                    stalled = last_draw.copy()
                    cv2.putText(stalled, "CAMERA STALLED - INPUT RELEASED", (15, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                    cv2.imshow(title, stalled)
                time.sleep(0.005)
                continue
            if sequence == last_sequence:
                time.sleep(0.003)
                continue
            last_sequence = sequence
            frame = cv2.flip(frame, 1)
            height, width = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            ms = max(last_ms + 1, int(now * 1000))
            last_ms = ms
            result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms)
            # Do not act on a frame if inference has fallen behind real time.
            if time.monotonic() - stamp > 0.3:
                apply(engine.step(None, None, time.monotonic()))
                continue
            hands = {}
            for points, categories in zip(result.hand_landmarks, result.handedness):
                label = categories[0].category_name
                if label in hands:  # ambiguous identity: stop input rather than overwrite a hand
                    hands = {}
                    break
                if label == args.dominant:
                    primary = FINGERS[pinch_profile['primary_finger']] if pinch_profile else 8
                    secondary = FINGERS[pinch_profile['secondary_finger']] if pinch_profile else 12
                else:
                    primary = FINGERS[other_profile['primary_finger']] if other_profile else FINGERS[args.scroll_finger]
                    secondary = FINGERS[other_profile['secondary_finger']] if other_profile else FINGERS[args.precision_finger]
                hands[label] = observation(points, width, height, primary, secondary)
                pixels = [(round(p.x * width), round(p.y * height)) for p in points]
                for a, b in EDGES:
                    cv2.line(frame, pixels[a], pixels[b], (80, 230, 130), 2)
                for p in pixels:
                    cv2.circle(frame, p, 3, (240, 240, 240), -1)
                cv2.putText(frame, label, pixels[0], cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
            other_label = "Left" if args.dominant == "Right" else "Right"
            actions = engine.step(hands.get(args.dominant), hands.get(other_label), now)
            apply(actions)
            nonmoves = [a.kind for a in actions if a.kind != "move"]
            if nonmoves:
                events = ", ".join(nonmoves)
            if previous_inference is not None:
                measured = 1 / max(now - previous_inference, 0.001)
                fps = measured if not fps else fps * 0.9 + measured * 0.1
            previous_inference = now
            cv2.rectangle(frame, (int(width * .15), int(height * .18)),
                          (int(width * .85), int(height * .82)), (220, 170, 70), 1)
            if engine.position:
                px = int((engine.position[0] * .70 + .15) * width)
                py = int((engine.position[1] * .64 + .18) * height)
                cv2.circle(frame, (px, py), 9, (0, 230, 255), 2)
            cv2.rectangle(frame, (0, 0), (width, 112), (24, 24, 24), -1)
            mode = "CONTROL" if args.control else "PREVIEW - no mouse output"
            lines = [f"{mode} | {fps:.0f} FPS | {args.dominant} pointer",
                     engine.status,
                     "F8: enable/pause | Esc/Q: quit" if backend else "Space: enable/pause | Esc/Q: quit",
                     f"Last event: {events or '-'}"]
            for i, line in enumerate(lines):
                cv2.putText(frame, line, (12, 24 + i * 25), cv2.FONT_HERSHEY_SIMPLEX, .52, (235, 235, 235), 1)
            cv2.imshow(title, frame)
            last_draw = frame
            if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                break
        return 0
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Stopped: {exc}")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            if backend:
                backend.close()
        finally:
            if capture:
                capture.close()
            if detector:
                detector.close()
            cv2.destroyAllWindows()
