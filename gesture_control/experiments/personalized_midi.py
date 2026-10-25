# SPDX-License-Identifier: GPL-3.0-only
"""Personal finger calibration and four-limb drum instruments."""
import argparse
from collections import deque
from math import isfinite
from pathlib import Path
from statistics import median, pstdev

from .midi_instrument import Instrument, merge_simultaneous
from .midi_io import MidiOutput
from .hand_profile import Binding, HandProfile, measure, FINGERS
from .finger_drums import FingerDrumEngine


class PersonalInstrument(Instrument):
    def __init__(self, engine, output, args, profile=None):
        super().__init__(engine, output, args)
        self.profile = profile
        self.selected = 0
        self.samples = {}
        self.rest = {}
        self.rest_noise = {}
        self.status = 'Calibrate comfortable rest/tap positions before arming'

    def current_values(self, ctx):
        if self.profile:
            return {i: measure(ctx.hands.get(b.hand), b.finger) if b.enabled else None for i,b in enumerate(self.profile.bindings)}
        from .four_limb import knee_measure
        return {i: knee_measure(ctx.pose, side) for i,side in enumerate(('Left','Right'))}

    def calibration_key(self, ctx):
        values = self.current_values(ctx)
        for identity, value in values.items():
            history = self.samples.setdefault(identity, deque(maxlen=40))
            if value is None or not isfinite(value):
                history.clear()
            else:
                history.append((ctx.now,value))
        if ord('1') <= ctx.key <= ord('9'):
            self.selected = min(ctx.key - ord('1'), len(values)-1)
        elif ctx.key == ord('0') and len(values)==10:
            self.selected = 9
        if ctx.key in (ord('r'),ord('f')):
            self.enabled = False
            self.engine.reset()
            self.output.panic()
            recent = [v for t,v in self.samples.get(self.selected,[]) if ctx.now-t < .6]
            if len(recent) < 5:
                self.status = 'Need 5 fresh visible samples; hold a comfortable position briefly'
                return
            value = median(recent)
            if ctx.key == ord('r'):
                self.rest[self.selected] = value
                self.rest_noise[self.selected] = pstdev(recent)
                self.status = 'Rest captured. Move comfortably, then F captures tap/raised position.'
            elif self.selected not in self.rest:
                self.status = 'Capture rest with R first'
            else:
                try:
                    noise = max(pstdev(recent), self.rest_noise.get(self.selected,0))
                    if abs(value-self.rest[self.selected]) < max(.015,4*noise):
                        raise ValueError('Movement overlaps tracking noise; hold steady or choose another control')
                    if self.profile:
                        self.profile.bindings[self.selected].calibrate(self.rest[self.selected],value)
                    else:
                        side = ('Left','Right')[self.selected]
                        self.engine.calibrate_knee(side,self.rest[self.selected],value)
                    self.status = 'Calibrated. Verify landmarks; SPACE arms MIDI, K saves calibration.'
                except ValueError as exc:
                    self.status = str(exc)
            self.samples.clear()
        elif ctx.key == ord('k'):
            try:
                if self.profile:
                    self.profile.save(self.args.profile)
                else:
                    save_knees(self.args.profile,self.engine.calibration)
                self.status = f'Saved calibration: {self.args.profile.name}'
                print(f'Calibration saved: {self.args.profile}')
            except (ValueError,OSError) as exc:
                self.status = f'Profile save failed: {exc}'

    def process(self, ctx):
        import cv2
        if self.output.error:
            raise RuntimeError(self.output.error)
        self.common_key(ctx.key)
        self.calibration_key(ctx)
        self.timing.update(ctx.captured_at,ctx.now)
        now = ctx.captured_at if ctx.captured_at is not None else ctx.now
        controls = []
        if self.profile:
            hits = self.engine.update(ctx.hands if self.enabled else {},now)
        else:
            from .four_limb import detect_markers
            fresh = ctx.captured_at is not None and 0 <= ctx.now-ctx.captured_at <= .5
            markers = detect_markers(ctx.frame) if self.args.hand_mode == 'markers' and fresh else None
            hits = self.engine.update(ctx.hands if self.enabled else {}, ctx.pose if self.enabled else None,
                                      now,markers=markers if self.enabled else None)
            controls = self.engine.cc_events
            if markers:
                h,w = ctx.frame.shape[:2]
                for label,(x,y) in markers.items():
                    cv2.circle(ctx.frame,(round(x*w),round(y*h)),10,(0,240,255),2)
        # Preserve subframe pedal/note order even though delivery is at dispatch.
        timeline = [(event.time,0,event) for event in controls]
        timeline += [(hit.time,1,hit) for hit in merge_simultaneous(hits)]
        for _, kind, event in sorted(timeline,key=lambda entry:entry[:2]):
            if kind == 0:
                self.output.control_change(event.control,event.value,channel=self.args.channel-1)
            else:
                self.emit([event],ctx)
        h,w = ctx.frame.shape[:2]
        hz,delay = self.timing.summary()
        lines = [('PERSONAL FINGER DRUMS' if self.profile else 'FOUR-LIMB DRUMS - research-inspired'),
                 ('ARMED' if self.enabled else 'PAUSED') + (' | PREVIEW/FILE ONLY' if self.output.dry_run else ' | LIVE MIDI'),
                 '1-9 select | R rest | F tap/raise | K save profile',
                 'SPACE arm/pause | S save MIDI | C clear take | P panic | Q quit',
                 self.status,
                 f'{hz:.0f} tracked FPS | capture-handler {delay:.0f}ms | {len(self.recorder.events)} notes']
        if self.profile:
            for i,binding in enumerate(self.profile.bindings):
                active = ctx.now-self.flashes.get(binding.note,-100)<.15
                lines.append(f'{">" if i==self.selected else " "}{i+1} {binding.hand} {binding.finger}: {binding.label} [{binding.note}] '
                             + ('DISABLED' if not binding.enabled else 'READY' if binding.calibrated else 'NEEDS CALIBRATION') + (' HIT' if active else ''))
                hand = ctx.hands.get(binding.hand)
                if hand:
                    point = hand.points[FINGERS[binding.finger][0]]
                    if all(isfinite(v) for v in point[:2]):
                        center=(round(point[0]*w),round(point[1]*h))
                        cv2.circle(ctx.frame,center,9,(0,230,255) if i==self.selected else (255,150,50),2)
                        cv2.putText(ctx.frame,str(i+1),center,cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),1)
        else:
            for i,side in enumerate(('Left','Right')):
                lines.append(f'{">" if i==self.selected else " "}{i+1} {side} knee: {self.engine.knee_status.get(side,"not calibrated")}')
            lines.append('Left hand snare | right hand hat | right knee kick | left knee hat/chick')
            lines.append('Hat state: '+('OPEN' if self.engine.hat_open else 'CLOSED'))
            if ctx.pose:
                for i in (23,24,25,26):
                    x,y,_,visibility=ctx.pose[i]
                    if visibility >= .6 and isfinite(x) and isfinite(y):
                        cv2.circle(ctx.frame,(round(x*w),round(y*h)),7,(0,200,255),2)
            line=round(self.args.hit_y*h)
            cv2.line(ctx.frame,(0,line),(w-1,line),(0,200,255),2)
        # A translucent panel keeps the landmark markers visible during calibration.
        overlay = ctx.frame.copy()
        cv2.rectangle(overlay,(0,0),(w,min(h,len(lines)*22+10)),(15,15,15),-1)
        cv2.addWeighted(overlay,.65,ctx.frame,.35,0,ctx.frame)
        for i,text in enumerate(lines):
            cv2.putText(ctx.frame,text[:98],(8,22+i*22),cv2.FONT_HERSHEY_SIMPLEX,.43,(240,240,240),1)
        return True


def save_knees(path, calibration):
    import json
    from dataclasses import asdict, is_dataclass
    data={'version':1,'knees':{side:asdict(value) if is_dataclass(value) else value for side,value in calibration.items()}}
    # Validate through the loader before committing any file.
    validate_knees(data)
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2),encoding='utf-8')


def validate_knees(data):
    if not isinstance(data,dict) or set(data)!={'version','knees'} or data['version']!=1:
        raise ValueError('Invalid knee profile')
    knees=data['knees']
    if not isinstance(knees,dict) or set(knees)-{'Left','Right'}:
        raise ValueError('Invalid knee sides')
    from .four_limb import FourLimbEngine
    engine=FourLimbEngine()
    for side, values in knees.items():
        if isinstance(values,dict):
            if set(values)!={'rest','raised'}:
                raise ValueError('Invalid knee calibration fields')
            rest,raised=values['rest'],values['raised']
        elif isinstance(values,(list,tuple)) and len(values)==2:
            rest,raised=values
        else:
            raise ValueError('Invalid knee calibration pair')
        engine.calibrate_knee(side,rest,raised)
    return {side:{'rest':value.rest,'raised':value.raised} for side,value in engine.calibration.items()}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--four-limb',action='store_true')
    parser.add_argument('--camera',type=int,default=0)
    parser.add_argument('--fps',type=int,choices=(30,60,120),default=60)
    parser.add_argument('--profile',type=Path)
    parser.add_argument('--bind',nargs='+',help='Replace bindings: Left:ring:36 Right:index:38 ... (all require calibration)')
    parser.add_argument('--hand-mode',choices=('palm','markers'),default='palm')
    parser.add_argument('--port')
    parser.add_argument('--record',type=Path)
    parser.add_argument('--bpm',type=float,default=120)
    parser.add_argument('--channel',type=int,default=10)
    parser.add_argument('--fixed-velocity',type=int)
    parser.add_argument('--hit-y',type=float,default=.62)
    parser.add_argument('--sensitivity',type=float,default=1)
    args=parser.parse_args(argv)
    args.piano=False
    args.quantize=None
    if not (1<=args.channel<=16 and 20<=args.bpm<=300 and .25<=args.hit_y<=.85 and .25<=args.sensitivity<=4):
        parser.error('Invalid channel/BPM/strike line/sensitivity')
    if args.fixed_velocity is not None and not 1<=args.fixed_velocity<=127:
        parser.error('Velocity must be 1-127')
    args.profile=args.profile or Path.home()/'.hand-control'/('knees.json' if args.four_limb else 'finger-drums.json')
    try:
        profile=None
        if args.four_limb:
            if args.bind:
                raise ValueError('--bind belongs to finger-drums')
            from .four_limb import FourLimbEngine
            engine=FourLimbEngine(hand_mode=args.hand_mode,hit_y=args.hit_y,sensitivity=args.sensitivity)
            if args.profile.is_file():
                import json
                if args.profile.stat().st_size>16384:
                    raise ValueError('Knee profile too large')
                for side,values in validate_knees(json.loads(args.profile.read_text(encoding='utf-8'))).items():
                    engine.calibrate_knee(side,values['rest'],values['raised'])
        else:
            profile=HandProfile.load(args.profile) if args.profile.is_file() else HandProfile.default()
            if args.bind:
                bindings=[]
                for spec in args.bind:
                    side,finger,note=spec.split(':')
                    bindings.append(Binding(side.title(),finger.lower(),int(note),f'MIDI {note}'))
                profile=HandProfile(bindings)
            if not profile.bindings:
                raise ValueError('Select at least one finger binding')
            engine=FingerDrumEngine(profile,sensitivity=args.sensitivity)
        output=MidiOutput(args.port)
    except (ValueError,TypeError,RuntimeError,OSError) as exc:
        print(f'Cannot start personalized instrument: {exc}')
        return 1
    from .runtime import run
    return run(PersonalInstrument(engine,output,args,profile),camera=args.camera,camera_fps=args.fps,
               with_pose=args.four_limb,with_hands=not(args.four_limb and args.hand_mode=='markers'),
               title='Four-limb MIDI' if args.four_limb else 'Personal finger MIDI')
