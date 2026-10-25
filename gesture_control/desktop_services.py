# SPDX-License-Identifier: GPL-3.0-only
"""Validated launcher settings and one managed worker process."""
from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from .models import download_models, model_status
from .paths import app_data_dir

MODE_LABELS={
    'preview':'Hand control preview', 'control':'Windows mouse control',
    'finger-drums':'Personal finger drums', 'four-limb':'Hands and knees drums',
    'hand-calibration':'Calibrate desktop gestures', 'piano':'Piano experiment',
    'drums':'Palm drum pads', 'workbench':'Two-hand 3D cube', 'gaze':'Eye navigation experiment',
    'draw':'Air drawing', 'music':'Air instrument', 'gestures':'Command wheel',
    'face':'Face expressions', 'camera-lab':'Camera inspection', 'backends':'System diagnostics',
}


@dataclass
class Settings:
    camera:int=0
    fps:int=60
    midi_port:str=''
    live_midi:bool=False
    record_path:str=''
    finger_profile:str=''
    pinch_profile:str=''
    other_pinch_profile:str=''
    hand_mode:str='palm'
    sensitivity:float=1.0
    dominant_hand:str='Right'
    primary_finger:str='index'
    secondary_finger:str='middle'


def validate_settings(settings):
    if not isinstance(settings,Settings):
        raise ValueError('Invalid settings')
    if type(settings.camera) is not int or not 0<=settings.camera<=32:
        raise ValueError('Choose a camera number between 0 and 32')
    if type(settings.fps) is not int or settings.fps not in (30,60,120):
        raise ValueError('Camera rate must be 30, 60 or 120')
    if type(settings.live_midi) is not bool:
        raise ValueError('Invalid MIDI output selection')
    if settings.hand_mode not in ('palm','markers'):
        raise ValueError('Choose palm or marker tracking')
    fingers=('index','middle','ring','pinky')
    if settings.dominant_hand not in ('Left','Right') or settings.primary_finger not in fingers or settings.secondary_finger not in fingers:
        raise ValueError('Choose a supported calibration hand and contact fingers')
    if settings.primary_finger==settings.secondary_finger:
        raise ValueError('Choose different primary and secondary contact fingers')
    if type(settings.sensitivity) not in (int,float) or not .25<=settings.sensitivity<=4:
        raise ValueError('Sensitivity must be between 0.25 and 4')
    for name in ('midi_port','record_path','finger_profile','pinch_profile','other_pinch_profile'):
        value=getattr(settings,name)
        if not isinstance(value,str) or len(value)>4096 or '\x00' in value or '\n' in value or '\r' in value:
            raise ValueError(f'Invalid {name.replace("_"," ")}')
    if settings.live_midi and not settings.midi_port.strip():
        raise ValueError('Choose a MIDI port or turn off live MIDI')
    return settings


def load_settings():
    path=app_data_dir()/'settings.json'
    if not path.is_file():
        return Settings()
    if path.stat().st_size>65536:
        raise ValueError('Saved settings are too large')
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or set(data)-{f.name for f in fields(Settings)}:
        raise ValueError('Saved settings contain unknown fields')
    return validate_settings(Settings(**data))


def save_settings(settings):
    validate_settings(settings)
    target=app_data_dir()/'settings.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.tmp')
    temp.write_text(json.dumps(asdict(settings),indent=2,allow_nan=False),encoding='utf-8')
    temp.replace(target)


def launch_arguments(mode,settings):
    validate_settings(settings)
    if mode not in MODE_LABELS:
        raise ValueError('Choose an available experiment')
    if mode=='backends':
        return ['backends','--doctor']
    args=[] if mode in ('preview','control') else [mode]
    if mode=='control':
        args.append('--control')
    args+=['--camera',str(settings.camera)]
    musical=mode in ('finger-drums','four-limb','piano','drums')
    if musical:
        args+=['--fps',str(settings.fps),'--sensitivity',str(settings.sensitivity)]
        if settings.live_midi:
            args+=['--port',settings.midi_port]
        if settings.record_path:
            args+=['--record',settings.record_path]
    if mode=='four-limb':
        args+=['--hand-mode',settings.hand_mode]
    if mode=='finger-drums' and settings.finger_profile:
        args+=['--profile',settings.finger_profile]
    if mode=='piano' and settings.finger_profile:
        args+=['--finger-profile',settings.finger_profile]
    if mode in ('preview','control'):
        if settings.pinch_profile:
            args+=['--pinch-profile',settings.pinch_profile]
        if settings.other_pinch_profile:
            args+=['--other-pinch-profile',settings.other_pinch_profile]
    if mode=='music':
        args.append('--audio')
    if mode=='hand-calibration':
        args+=['--dominant',settings.dominant_hand,'--primary-finger',settings.primary_finger,
               '--secondary-finger',settings.secondary_finger]
        if settings.pinch_profile:
            args+=['--output',settings.pinch_profile]
    return args


def available_midi_ports():
    from .experiments.midi_io import MidiOutput
    return MidiOutput.list_ports()


def worker_command(arguments,log_path,stop_path):
    executable=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,'-m','gesture_control.desktop_entry']
    return executable+['--worker','--log-file',str(log_path),'--stop-file',str(stop_path),'--',*arguments]


class Controller:
    def __init__(self):
        self.process=None
        self.log_path=app_data_dir()/'logs'/'latest.log'
        self.stop_path=None
        self.deadline=None
        self.stage=0
        self.last_code=None

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def start(self,mode,settings):
        if self.running:
            raise ValueError('Stop the running experiment first')
        arguments=launch_arguments(mode,settings)
        self.log_path.parent.mkdir(parents=True,exist_ok=True)
        self.log_path.write_text('',encoding='utf-8')
        self.stop_path=app_data_dir()/'logs'/f'stop-{uuid4().hex}'
        env=os.environ.copy()
        # Ensure package source can be found even when a user launches elsewhere.
        if not getattr(sys,'frozen',False):
            root=str(Path(__file__).resolve().parent.parent)
            env['PYTHONPATH']=root+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
        options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        self.process=subprocess.Popen(worker_command(arguments,self.log_path,self.stop_path),env=env,
                                      stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**options)
        self.deadline=None
        self.stage=0
        self.last_code=None

    def stop(self):
        if self.running and self.deadline is None:
            self.stop_path.touch()
            self.deadline=time.monotonic()+2.5

    def poll(self):
        if self.process is None:
            return self.last_code
        code=self.process.poll()
        if code is None and self.deadline is not None and time.monotonic()>=self.deadline:
            try:
                self.process.terminate() if self.stage==0 else self.process.kill()
            except ProcessLookupError:
                pass
            self.stage+=1
            self.deadline=time.monotonic()+1
            return None
        if code is not None:
            self.last_code=code
            self.process=None
            if self.stop_path:
                self.stop_path.unlink(missing_ok=True)
        return code

    def read_log(self):
        try:
            with self.log_path.open('rb') as log:
                log.seek(0,2)
                length=log.tell()
                log.seek(max(0,length-65536))
                return log.read().decode('utf-8',errors='replace')
        except OSError:
            return ''
