# SPDX-License-Identifier: GPL-3.0-only
"""Shared RGB tracking and window lifecycle for sandbox experiments."""
from dataclasses import dataclass
from math import hypot, isfinite
from statistics import median
from pathlib import Path
import time

from ..app import Capture, EDGES
from ..paths import model_path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class HandData:
    points: list
    pinch: float
    x: float
    y: float


@dataclass
class Context:
    frame: object
    hands: dict
    face: object
    now: float
    key: int = -1
    captured_at: float | None = None
    pose: object = None


def hand_data(points, width, height):
    """Reject malformed model output before it reaches any gesture handler."""
    if len(points) != 21:
        return None
    def valid(i):
        return len(points[i]) == 3 and all(isfinite(v) for v in points[i])
    def distance(a, b):
        return hypot((points[a][0] - points[b][0]) * width,
                     (points[a][1] - points[b][1]) * height)
    if not valid(0):
        return None
    scales = [distance(0, i) for i in (5, 9, 13, 17) if valid(i)]
    if len(scales) < 2:
        return None
    scale = median(scales)
    if scale < 5:
        return None
    pinch = distance(4, 8) / scale if valid(4) and valid(8) else float('inf')
    pointer = points[8] if valid(8) else points[0]
    return HandData(points, pinch, pointer[0], pointer[1])


def close_resource(resource):
    if resource is not None:
        close = getattr(resource, "close", None)
        if close:
            try:
                close()
            except Exception as exc:
                print(f"Cleanup warning: {exc}")


def run(handler, camera=0, with_face=False, title="Gesture playground", camera_fps=30,
        with_pose=False, with_hands=True):
    """Run one sandbox. Models stay local; download is a separate explicit step."""
    required = []
    hand_path = model_path('hand_landmarker.task')
    face_path = model_path('face_landmarker.task')
    pose_path = model_path('pose_landmarker_lite.task')
    if with_hands:
        required.append(hand_path)
    if with_face:
        required.append(face_path)
    if with_pose:
        required.append(pose_path)
    missing = [p.name for p in required if not p.is_file()]
    if missing:
        print("Missing models: " + ", ".join(missing))
        print('Use Download models in the launcher or run hand-control --download-models')
        close_resource(handler)
        return 1
    try:
        import cv2
        import numpy as np
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
    except ImportError as exc:
        print(f"Missing dependency: {exc}. Run Setup.bat first.")
        close_resource(handler)
        return 1
    capture = hand_tracker = face_tracker = pose_tracker = None
    last_sequence = -1
    last_timestamp = -1
    last_frame = None
    pending_key = -1
    start = time.monotonic()
    title = title + " - SANDBOX (no desktop input)"
    print(title + "\nEsc/Q: quit with window focused. No video is recorded.")
    try:
        if with_hands:
            hand_tracker = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=str(hand_path)),
                running_mode=vision.RunningMode.VIDEO, num_hands=2,
                min_hand_detection_confidence=.6, min_hand_presence_confidence=.6,
                min_tracking_confidence=.6))
        if with_face:
            face_tracker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=str(face_path)),
                running_mode=vision.RunningMode.VIDEO, num_faces=1,
                min_face_detection_confidence=.6, min_face_presence_confidence=.6,
                min_tracking_confidence=.6))
        if with_pose:
            pose_tracker = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=str(pose_path)),
                running_mode=vision.RunningMode.VIDEO, num_poses=1,
                min_pose_detection_confidence=.6, min_pose_presence_confidence=.6,
                min_tracking_confidence=.6))
        cv2.namedWindow(title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(title, 960, 720)
        capture = Capture(cv2, camera, fps=camera_fps)
        while True:
            key = cv2.waitKey(1)
            if key >= 0:
                pending_key = key & 0xff
            if pending_key in (27, ord("q")):
                break
            if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                break
            if capture.error:
                raise RuntimeError(capture.error)
            raw, sequence, stamp = capture.latest()
            now = time.monotonic()
            if raw is None or now - stamp > .3:
                if now - start > 10 and raw is None:
                    raise RuntimeError("Camera did not start within 10 seconds")
                # Feed loss through handlers even when the camera stalls, stopping sound/clutches.
                frame = last_frame.copy() if last_frame is not None else np.zeros((480, 640, 3), dtype=np.uint8)
                if handler.process(Context(frame, {}, None, now, pending_key)) is False:
                    break
                pending_key = -1
                cv2.putText(frame, "WAITING FOR FRESH CAMERA FRAME", (15, 460), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 100, 255), 1)
                cv2.imshow(title, frame)
                time.sleep(.015)
                continue
            if sequence == last_sequence:
                time.sleep(.003)
                continue
            last_sequence = sequence
            frame = cv2.flip(raw, 1)
            last_frame = frame.copy()
            height, width = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            timestamp = max(last_timestamp + 1, int(now * 1000))
            last_timestamp = timestamp
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = hand_tracker.detect_for_video(image, timestamp) if hand_tracker else None
            hands = {}
            for landmarks, categories in zip(result.hand_landmarks, result.handedness) if result else []:
                label = categories[0].category_name
                if label in hands:
                    hands = {}
                    break
                points = [(p.x, p.y, p.z) for p in landmarks]
                observation = hand_data(points, width, height)
                if observation is not None:
                    hands[label] = observation
                    pixels = [(round(x * width), round(y * height)) if all(isfinite(v) for v in (x,y)) else None for x, y, _ in points]
                    for a, b in EDGES:
                        if pixels[a] is not None and pixels[b] is not None:
                            cv2.line(frame, pixels[a], pixels[b], (80, 170, 100), 1)
            face = None
            if face_tracker:
                result = face_tracker.detect_for_video(image, timestamp)
                if result.face_landmarks:
                    values = [(p.x, p.y, p.z) for p in result.face_landmarks[0]]
                    if all(all(isfinite(v) for v in p) for p in values):
                        face = values
            pose = None
            if pose_tracker:
                # Estimate anatomy from the original camera image; only mirror x
                # for the selfie preview, preserving anatomical limb labels.
                pose_rgb = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
                pose_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=pose_rgb)
                result = pose_tracker.detect_for_video(pose_image, timestamp)
                if result.pose_landmarks:
                    pose = [(1-p.x, p.y, p.z, p.visibility) for p in result.pose_landmarks[0]]
            if time.monotonic() - stamp > .5:
                hands, face, pose = {}, None, None
                cv2.putText(frame, "TRACKING DELAY - input ignored", (10, height - 15), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 100, 255), 1)
            if handler.process(Context(frame, hands, face, time.monotonic(), pending_key, stamp, pose)) is False:
                break
            pending_key = -1
            cv2.imshow(title, frame)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"Experiment stopped: {exc}")
        return 1
    finally:
        for resource in (handler, capture, hand_tracker, face_tracker, pose_tracker):
            close_resource(resource)
        cv2.destroyAllWindows()
