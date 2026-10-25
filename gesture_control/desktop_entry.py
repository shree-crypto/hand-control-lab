# SPDX-License-Identifier: GPL-3.0-only
"""Installed GUI launcher, worker entry and headless packaging diagnostics."""
import argparse
import importlib.util
import importlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import threading
import traceback

VERSION='0.3.1'


def self_test(report=None):
    from .paths import app_data_dir
    from .models import model_status
    from .desktop_services import MODE_LABELS, Settings, launch_arguments
    result={'version':VERSION,'frozen':bool(getattr(sys,'frozen',False)),
            'python':sys.version.split()[0], 'app_data':str(app_data_dir()),
            'models':model_status(),'routes':{},'modules':{}}
    for mode in MODE_LABELS:
        launch_arguments(mode,Settings())
        result['routes'][mode]=True
    for module in ('tkinter','cv2','mediapipe','mido','rtmidi'):
        result['modules'][module]=importlib.util.find_spec(module) is not None
    result['ok']=all(result['routes'].values())
    if getattr(sys,'frozen',False):
        result['ok']=result['ok'] and all(result['models'].values()) and all(result['modules'].values())
        result['import_errors']={}
        for module in result['modules']:
            try:
                importlib.import_module(module)
            except Exception as exc:
                result['import_errors'][module]=str(exc)
        result['ok']=result['ok'] and not result['import_errors']
    text=json.dumps(result,indent=2)
    if report:
        path=Path(report)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding='utf-8')
    if sys.stdout is not None:
        print(text)
    return 0 if result['ok'] else 1


def worker(argv):
    parser=argparse.ArgumentParser()
    parser.add_argument('--log-file',type=Path,required=True)
    parser.add_argument('--stop-file',type=Path,required=True)
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args(argv)
    arguments=args.arguments[1:] if args.arguments[:1]==['--'] else args.arguments
    args.log_file.parent.mkdir(parents=True,exist_ok=True)
    done=threading.Event()
    def watch_stop():
        import _thread
        while not done.wait(.1):
            if args.stop_file.exists():
                _thread.interrupt_main()
                return
    with args.log_file.open('a',encoding='utf-8',buffering=1) as log:
        previous=(sys.stdout,sys.stderr)
        sys.stdout=sys.stderr=log
        try:
            threading.Thread(target=watch_stop,daemon=True,name='hand-control-stop').start()
            from .__main__ import main as cli
            return cli(arguments)
        except KeyboardInterrupt:
            return 0
        except SystemExit as exc:
            return exc.code if isinstance(exc.code,int) else 1
        except Exception:
            traceback.print_exc()
            return 1
        finally:
            done.set()
            sys.stdout,sys.stderr=previous


def main(argv=None):
    multiprocessing.freeze_support()
    arguments=list(sys.argv[1:] if argv is None else argv)
    if arguments[:1]==['--worker']:
        return worker(arguments[1:])
    if '--self-test' in arguments:
        parser=argparse.ArgumentParser()
        parser.add_argument('--self-test',action='store_true')
        parser.add_argument('--report')
        options=parser.parse_args(arguments)
        return self_test(options.report)
    if arguments==['--version']:
        if sys.stdout is not None:
            print(VERSION)
        return 0
    if arguments==['--download-models']:
        from .models import download_models
        try:
            download_models()
            print('Tracking models ready.')
            return 0
        except (OSError,ValueError) as exc:
            print(f'Model download failed: {exc}')
            return 1
    if arguments:
        from .__main__ import main as cli
        return cli(arguments)
    from .desktop import main as gui
    return gui()


if __name__=='__main__':
    raise SystemExit(main())
