#!/usr/bin/env python3
"""DESIGN: main-operated single attempt, shared probe route plus observed case macros.

DESIGN: no launch on import. The command protocol reuses plan.json/run/cmds.txt.
Main supplies observed navigation and pre-snap gates; no guessed team pulse counts.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import signal
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
SHARED=Path('/media/noah/Storage/.b76-research/u5/lab/u5_tod_probe.py')


def normalized(text):
    return re.sub('[^A-Z0-9]','',text.upper())


def page_matches(text,case):
    """DESIGN: require formation AND every uniquely numbered play label on this page."""
    clean=normalized(text)
    return normalized(case['formation']) in clean and all(normalized(s) in clean for s in case['page_labels'])


class FreezeClock:
    """DESIGN: conservative static-frame/failed-capture and progress deadline guard."""
    def __init__(self,now,limit=60):
        self.limit=limit;self.changed=now;self.digest=None;self.progress=now;self.stage='boot'
    def observe(self,digest,now):
        if digest is not None and digest!=self.digest:
            self.changed=now;self.digest=digest
        if now-self.changed>self.limit:return 'static frame or failed capture longer than 60 seconds'
        if self.stage!='boot' and now-self.progress>self.limit:return 'no observed stage progress for more than 60 seconds'
        return None
    def advance(self,stage,now):
        self.stage=stage;self.progress=now


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bake-dir',type=Path,required=True);ap.add_argument('--run-dir',type=Path,required=True)
    args=ap.parse_args();run_dir=args.run_dir.resolve();plan=json.loads((args.bake_dir/'plan.json').read_text())
    disc=Path(plan['xiso_path']);screens=run_dir/'screens';screens.mkdir(exist_ok=True)
    # PROVED OFFLINE: importing the shared module installs the historic-team rejection.
    # DESIGN: discard its optional TOD/RAM wrappers; no guest-memory writes are needed.
    sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
    # DESIGN: preload helpers from the lab's stack before the shared probe adds its own path.
    import xemu_playbook_create_runtime
    import xemu_practice_runtime
    if Path(xemu_playbook_create_runtime.__file__).resolve()!=ROOT/'tools/xemu_playbook_create_runtime.py':
        raise RuntimeError('wrong runtime helper stack')
    saved=sys.argv;sys.argv=[str(SHARED)]
    try:shared=runpy.run_path(str(SHARED),run_name='pb_shared_route')
    finally:sys.argv=saved
    probe=shared['probe'];probe.start_game=shared['_start_game'];xr=probe.xr
    xr.abort_if_xemu_running()
    attempts=run_dir/'attempt.started'
    with attempts.open('x') as stream:stream.write('DESIGN: one attempt; never restart this directory\n')
    isolation=xr.setup_isolation(run_dir,disc)
    # DESIGN: the shared wrapper sets mem_limit; validate the exact isolated file and backing chain.
    import subprocess,tomllib
    cfg=Path(isolation['config_path']);conf=tomllib.loads(cfg.read_text())
    if str(conf['sys']['mem_limit'])!='128':raise RuntimeError('mem_limit must be 128')
    overlay=Path(isolation['overlay_path']).resolve()
    if Path(conf['sys']['files']['hdd_path']).resolve()!=overlay or overlay==xr.LIVE_HDD.resolve():
        raise RuntimeError('HDD must be an isolated overlay')
    backing=json.loads(subprocess.check_output(['qemu-img','info','--output=json',str(overlay)],text=True))
    if Path(backing['full-backing-filename']).resolve()!=xr.LIVE_HDD.resolve():raise RuntimeError('wrong HDD backing')
    # DESIGN: a read-only flatpak grant prevents accidental writes to the backing HDD.
    class Run(probe.HeadlessRun):
        capture_lock=threading.RLock()
        def _frame(self):
            with self.capture_lock:return super()._frame()
        def screenshot(self,*args,**kwargs):
            with self.capture_lock:return super().screenshot(*args,**kwargs)
        def xemu_command(self,path):
            command=super().xemu_command(path)
            command[2:2]=[f'--filesystem={xr.LIVE_HDD}:ro','--nosocket=pulseaudio']
            if command[command.index('-gdb')+1]!=f'tcp:127.0.0.1:{self.gdb_port}':raise RuntimeError('nonlocal gdb')
            if command[command.index('-qmp')+1]!=f'tcp:127.0.0.1:{self.qmp_port},server=on,wait=off':raise RuntimeError('nonlocal QMP')
            return command
    port=1234
    while not xr.port_free(port) or not xr.port_free(port+1):port+=2
    run=Run(run_dir,xr.pick_display(),port);run.qmp_port=port+1
    cases={r['case']:r for r in plan['cases']};done={};pending=None;seen=0;pad=None
    ledger=dict(status='INFERRED',runtime_witness=False,attempts=1,isolation=isolation,cases=done,outcome='INCOMPLETE')
    stop=threading.Event();guard=FreezeClock(time.monotonic());started=time.monotonic()
    def save():
        (run_dir/'result.json').write_text(json.dumps(ledger,indent=2)+'\n')
    def abort(signum,frame):raise RuntimeError(f'lab stopped by signal {signum}')
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP,signal.SIGUSR1):signal.signal(sig,abort)
    def watch():
        while not stop.wait(1):
            now=time.monotonic();digest=None
            try:digest=hashlib.sha256(run._frame().resize((160,90)).convert('L').tobytes()).hexdigest()
            except Exception:pass
            reason=guard.observe(digest,now)
            if now-started>3600:reason='one-hour attempt limit'
            if reason:
                ledger['freeze']=dict(status='INFERRED',reason=reason,stage=guard.stage,seconds=now-guard.changed)
                ledger['outcome']='STOPPED';save()
                os.kill(os.getpid(),signal.SIGUSR1);return
    def shot(name):
        item=run.screenshot(name,screens)
        return item
    def tap(button,secs=.15):pad.send(f'TAP {button} {secs}',expect='TAPPED',timeout=10)
    try:
        os.environ['XDG_DATA_HOME']=str(run_dir/'xdg');(run_dir/'xdg').mkdir(exist_ok=True)
        run.start_display();pad=xr.Gamepad()
        threading.Thread(target=watch,daemon=True).start()
        run.start_xemu(disc)
        ledger['team_select']=probe.quick_game_home(run,pad,screens,home_team='GIANTS',away_team='COWBOYS',notes=ledger)
        guard.advance('main navigation to Giants offense',time.monotonic());save()
        commands=run_dir/'cmds.txt'
        while True:
            for line in commands.read_text().splitlines()[seen:]:
                seen+=1;line=line.strip()
                if not line or line.startswith('#'):continue
                print('INFERRED: CMD '+line,flush=True)
                fields=line.split();cmd=fields[0]
                if cmd in ('finish','quit'):
                    if cmd=='finish' and (set(done)!=set(cases) or any(not r.get('operator_review') for r in done.values())):
                        raise RuntimeError('ten reviewed cases required; missing cases are not passes')
                    ledger['outcome']='CAPTURED_FOR_REVIEW' if cmd=='finish' else 'INCOMPLETE'
                    return 0 if cmd=='finish' else 2
                if cmd=='case':
                    n=int(fields[1]);case=cases[n]
                    if pending is not None or n in done:raise RuntimeError('case already used or previous case unfinished')
                    if not page_matches(run.ocr_full(),case):raise RuntimeError(f'wrong or unreadable page for case {n}')
                    done[n]=dict(status='INFERRED',formation=case['formation'],formation_index=case['formation_index'],play_index=case['play_index'],concept=case['concept'],playcall=shot(f'{n:02d}-playcall'),snapped=False)
                    tap(case['button']);pending=n;guard.advance(f'case {n} awaiting observed lineup',time.monotonic())
                elif cmd=='snap':
                    n=int(fields[1])
                    if pending!=n or done[n]['snapped']:raise RuntimeError('snap requires the current unsnapped case')
                    # DESIGN: explicit main command confirms the pre-snap lineup; capture around A.
                    done[n]['presnap']=shot(f'{n:02d}-presnap');tap('A',.10)
                    frames=[]
                    for j in range(4):
                        frames.append(shot(f'{n:02d}-snap-{j}'));time.sleep(.20)
                    time.sleep(1.0);done[n]['midplay']=shot(f'{n:02d}-midplay')
                    done[n]['snap_burst']=frames;done[n]['snapped']=True
                    done[n]['snap_claim']='INFERRED: A input plus timed frames; main must verify actual snap'
                    guard.advance(f'case {n} awaiting dead ball and review',time.monotonic())
                elif cmd=='result':
                    n=int(fields[1])
                    if pending!=n or not done[n]['snapped'] or len(fields)<3:raise RuntimeError('result requires snapped case and observed notes')
                    done[n]['operator_review']=' '.join(fields[2:]);done[n]['after']=shot(f'{n:02d}-after')
                    pending=None;guard.advance('main navigation to next case',time.monotonic())
                elif cmd=='shot':shot(fields[1])
                elif cmd=='ocr':print('INFERRED: OCR '+run.ocr_full(),flush=True)
                elif cmd=='tap':tap(fields[1],float(fields[2]) if len(fields)>2 else .15)
                elif cmd in ('hold','release'):pad.send(f'{cmd.upper()} {fields[1]}',expect=cmd.upper(),timeout=10)
                elif cmd=='wait':
                    delay=float(fields[1])
                    if not 0<=delay<=10:raise RuntimeError('wait must be 0..10 seconds')
                    time.sleep(delay)
                else:raise RuntimeError(f'unknown command {cmd}')
                # DESIGN: arbitrary taps do not reset the freeze/progress deadline.
                save()
            time.sleep(.2)
    except Exception as exc:
        ledger['error']=f'{type(exc).__name__}: {exc}'
        try:ledger['failure_frame']=shot('zz-stopped')
        except Exception:pass
        raise
    finally:
        stop.set()
        if pad is not None:pad.quit()
        ledger['shutdown']=run.shutdown();save()

if __name__=='__main__':raise SystemExit(main())
