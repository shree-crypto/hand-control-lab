# SPDX-License-Identifier: GPL-3.0-only
"""Explicit model download into writable per-user storage, never the install folder."""
from pathlib import Path
import urllib.request
from .paths import MODEL_NAMES, app_data_dir, model_path

MODEL_URLS={
    'hand_landmarker.task':'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
    'face_landmarker.task':'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
    'pose_landmarker_lite.task':'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
}


def model_status():
    return {name:model_path(name).is_file() and model_path(name).stat().st_size>1_000_000 for name in MODEL_NAMES}


def download_models(names=None):
    for name in (MODEL_NAMES if names is None else names):
        if name not in MODEL_URLS:
            raise ValueError('Unknown tracking model')
        available=model_path(name)
        if available.is_file() and available.stat().st_size>1_000_000:
            continue
        target=app_data_dir()/'models'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix('.download')
        try:
            with urllib.request.urlopen(MODEL_URLS[name],timeout=30) as response, temporary.open('wb') as output:
                total=0
                while chunk:=response.read(128*1024):
                    total+=len(chunk)
                    if total>20_000_000:
                        raise ValueError('Unexpected model size')
                    output.write(chunk)
            if total<1_000_000:
                raise ValueError('Incomplete tracking model download')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
