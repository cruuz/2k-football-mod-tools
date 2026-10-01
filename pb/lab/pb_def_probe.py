#!/usr/bin/env python3
"""DESIGN: main-only non-interactive Giants/Cowboys CPU route; never imported in tests.
Uses the shared u5 route and r1 neutral-controller procedure. No live command file.
"""
import json
from pathlib import Path
import sys
import subprocess
import time
sys.path.insert(0, '/media/noah/Storage/.b76-research/u5/lab')
import u5_tod_probe as u5
probe=u5.probe
xr=probe.xr
log=probe.log
# DESIGN: retain shared isolation/team selection, omit weather writes and duplicate RAM hook.
probe.start_game=u5._start_game
probe.watch=u5._watch
STATE={'snaps':[]}
JOBS=[]

def quick_game_cpu(run, pad, out_dir, *, home_team, away_team="", explore=False, notes=None):
    """probe.quick_game_home with the controller left neutral before START (CPU vs CPU)."""
    notes = notes if notes is not None else {}
    state, text = probe.reach_menu(run, pad, out_dir, notes)
    notes["menu_reached"] = state
    if state != "team-select":
        run.screenshot("02-main-menu", out_dir)
        text = probe.open_quick_game(run, pad)
    run.screenshot("03-team-select", out_dir)
    slot = probe.cycle_slot_to(run, pad, probe.HOME_SLOT, home_team, "home")
    probe.tap(pad, "LEFT", settle=1.0)
    probe.tap(pad, "LEFT", settle=1.0)
    try:
        left = probe.cycle_slot_to(run, pad, probe.AWAY_SLOT, away_team, "away")
    finally:
        probe.tap(pad, "RIGHT", settle=1.0)
        probe.tap(pad, "RIGHT", settle=1.0)
    home_after, home_read = probe.read_slot(run, probe.HOME_SLOT)
    if home_read != home_team:
        raise xr.GateError("team-select", f"home slot changed while choosing the away team: {home_after!r}")
    run.screenshot("04-team-select-home", out_dir)
    probe.tap(pad, "LEFT", settle=1.5)          # DESIGN: neutral controller -> CPU vs CPU
    run.screenshot("04b-controller-neutral", out_dir)
    notes["cpu_vs_cpu"] = "one LEFT from the home side before START"
    probe.hold(pad, "START", xr.START_HOLD)
    time.sleep(4.0)
    run.screenshot("05-coach-matchup", out_dir)
    probe.start_game(run, pad, notes)
    log("game starting (CPU vs CPU)")
    return f"{left} AT {home_after}"[:200]


probe.quick_game_home=quick_game_cpu

def snap(run,name):
    if name in STATE['snaps']:return
    u5.ram_snapshot(run,name)
    path=Path(run.run_dir)/'snaps'/f'{name}.bin'
    if not path.exists() or path.stat().st_size!=0x8000000:
        raise RuntimeError(f'Incomplete RAM copy: {name}')
    STATE['snaps'].append(name)
    stats=Path(run.run_dir)/'stats';stats.mkdir(exist_ok=True)
    with (stats/f'{name}.log').open('w') as log_file:
        process=subprocess.Popen(['taskset','-c','0-23',sys.executable,
            str(Path(__file__).with_name('pb_def_stats.py')),str(path),
            '--out',str(stats/f'{name}.json'),'--delete-after'],stdout=log_file,stderr=subprocess.STDOUT)
    JOBS.append((name,process))


def watch_game(run,pad,out_dir,seconds,frame_seconds):
    # DESIGN: timed frames and five-minute RAM receipts, never operator deadlines.
    snap(run,'opening')
    started=time.monotonic();last_frame=-frame_seconds;last_read=-20;last_snapshot=0
    last_digest=None;same_since=started;seen={};outcome='watch-time-limit'
    while time.monotonic()-started<seconds:
        elapsed=time.monotonic()-started
        if probe.xemu_exit(run) is not None:
            outcome='xemu-exit';break
        if elapsed-last_frame>=frame_seconds:
            probe.keep_frame(run._frame(),out_dir,f'def-{elapsed:05.0f}s');last_frame=elapsed
        if elapsed-last_snapshot>=300:
            snap(run,f'timer-{int(elapsed):04d}');last_snapshot=elapsed
        if elapsed-last_read>=20:
            last_read=elapsed;text=probe.screen_text(run).upper()
            for word in ('HALFTIME','HALF TIME','FINAL','GAME OVER','4TH','OVERTIME'):
                if word in text:seen.setdefault(word,round(elapsed,1))
            if 'HALFTIME' in text or 'HALF TIME' in text:snap(run,'halftime')
            if 'FINAL' in text and ('4TH' in seen or 'OVERTIME' in seen or elapsed>900):
                snap(run,'final');outcome='final';break
            digest=probe.safe_digest(run)
            if digest is not None and digest==last_digest:
                if time.monotonic()-same_since>=120:
                    # DESIGN: a static screen may be a modal. Preserve evidence, do not hide it with a nudge.
                    snap(run,'static-stop');outcome='static-screen-120s';break
            else:last_digest=digest;same_since=time.monotonic()
        time.sleep(1)
    if outcome!='xemu-exit':snap(run,'watch-end')
    for name,process in JOBS:
        if process.wait(timeout=180):raise RuntimeError(f'Native stats failed: {name}')
    result=dict(status='INFERRED',ended=outcome,elapsed=round(time.monotonic()-started,1),
        seen=seen,snapshots=STATE['snaps'],operator_commands=False,automatic_nudges=0,
        review='Static-frame detector cannot detect every animated menu stall. Main checks stat progress and frames.')
    (Path(run.run_dir)/'defense-watch.json').write_text(json.dumps(result,indent=2)+'\n')
    if outcome!='final':raise RuntimeError(f'Incomplete CPU game: {outcome}')
    return result

probe.play_on=watch_game
if __name__=='__main__':
    code=probe.main()
    for name,process in JOBS:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill();process.wait()
    args=sys.argv[1:];run_dir=Path(args[args.index('--run-dir')+1])
    receipt=run_dir/'defense-watch.json'
    complete=receipt.is_file() and json.loads(receipt.read_text())['ended']=='final'
    sys.exit(code if code else (0 if complete else 3))
