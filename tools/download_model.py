# SPDX-License-Identifier: GPL-3.0-only
"""Download Google's versioned model once; runtime uses the local file offline."""
from pathlib import Path
import argparse
import urllib.request

URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"


def download(name, url):
    target = Path(__file__).resolve().parent.parent / "models" / name
    if target.is_file() and target.stat().st_size > 1_000_000:
        print(f"Model already present: {target}")
        return 0
    target.parent.mkdir(exist_ok=True)
    temporary = target.with_suffix(".download")
    print(f"Downloading {name} from Google...", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=30) as response, temporary.open("wb") as output:
            total = 0
            while chunk := response.read(128 * 1024):
                total += len(chunk)
                if total > 20_000_000:
                    raise ValueError("Unexpected model size")
                output.write(chunk)
        if temporary.stat().st_size < 1_000_000:
            raise ValueError("Downloaded model is unexpectedly small")
        temporary.replace(target)
        print(f"Saved {target}")
        return 0
    except (OSError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        print(f"Download failed: {exc}. Check internet access and try again.")
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Download local MediaPipe models")
    parser.add_argument("--face", action="store_true", help="Also download face landmarks for gaze/head labs")
    parser.add_argument("--pose", action="store_true", help="Also download body pose for the four-limb drum lab")
    args = parser.parse_args(argv)
    if download("hand_landmarker.task", URL):
        return 1
    if args.face:
        if download("face_landmarker.task", "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"):
            return 1
    if args.pose:
        return download("pose_landmarker_lite.task", "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
