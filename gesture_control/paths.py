# SPDX-License-Identifier: GPL-3.0-only
"""Separate read-only application assets from per-user files."""
import os
from pathlib import Path
import sys

MODEL_NAMES = ('hand_landmarker.task','face_landmarker.task','pose_landmarker_lite.task')


def app_data_dir():
    if os.environ.get('LOCALAPPDATA'):
        return Path(os.environ['LOCALAPPDATA']) / 'HandControl'
    return Path.home() / '.local' / 'share' / 'HandControl'


def model_path(name):
    if name not in MODEL_NAMES:
        raise ValueError('Unknown tracking model')
    cache=app_data_dir()/'models'/name
    if cache.is_file():
        return cache
    bundle=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))/'models'/name
    return bundle if bundle.is_file() else cache
