#!/usr/bin/env python3
"""DESIGN: main-only forced-fatigue A/B using the shared k1/r1 route.

No xemu is launched by importing this module or by offline tests. Execute only
through sd2_cpu.sh, which owns the shared lock for both arms.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def preflight(disc):
    # Use the source tree's independent read-only directory parser. Do not
    # copy, compact, patch, or open the disc for writing.
    sys.path.insert(0, str(HERE.parents[1] / 'tools'))
    from nfl_audo_wav_xiso_verify import parse_xdvdfs
    assert disc.stat().st_size == 8012931072, 'candidate D size differs'
    with disc.open('rb') as f:
        entries, _ = parse_xdvdfs(f.fileno(), disc.stat().st_size)
        xbe = entries['default.xbe']
        f.seek(xbe.offset)
        raw = f.read(xbe.size)
    assert hashlib.sha256(raw).hexdigest() == 'f69ee7a3c4fb5e7a6eea50fe6ae0ece740a7f4e72efa85df507145dd85f96b44', 'candidate D XBE differs'


def main():
    assert os.environ['SD2_MODE'] in ('control', 'fixed')
    # The shell retains flock fd 9; reject direct, uncoordinated launches.
    assert Path('/proc/self/fd/9').resolve() == Path('/home/noah/2k-worktrees/.b76-session/xemu.lock')
    disc = Path(sys.argv[sys.argv.index('--xiso') + 1])
    preflight(disc)
    sys.path.insert(0, '/media/noah/Storage/.b76-research/r1/lab')
    import r1_lab_probe as r1
    probe, xr = r1.probe, r1.xr
    # This pair needs frames and small gdb receipts, not 128 MiB snapshots.
    r1.u5.ram_snapshot = lambda *args, **kwargs: None
    original_start = probe.HeadlessRun.start_xemu

    def start(self, xiso):
        assert not self.xemu_binary, 'the SD2 lab uses the stock flatpak'
        self.qmp_port = 4455
        while not xr.port_free(self.qmp_port) or self.qmp_port == self.gdb_port:
            self.qmp_port += 1
        cfg = (self.run_dir / 'xemu.toml').read_text()
        assert "mem_limit = '128'" in cfg
        assert (self.run_dir / 'xbox_hdd.qcow2').is_file()
        command = self.xemu_command(xiso)
        assert f'--filesystem={xiso}:ro' in command
        assert f'tcp:127.0.0.1:{self.gdb_port}' in command
        assert f'tcp:127.0.0.1:{self.qmp_port},server=on,wait=off' in command
        (self.run_dir / 'launch.json').write_text(json.dumps(command, indent=2) + '\n')
        return original_start(self, xiso)

    probe.HeadlessRun.start_xemu = start

    def play(run, pad, out_dir, seconds, frame_seconds):
        mode = os.environ['SD2_MODE']
        command = ['gdb', '-q', '-nx', '-batch', '-ex', 'set pagination off', '-ex', 'set confirm off',
                   '-ex', f'target remote 127.0.0.1:{run.gdb_port}', '-x', str(HERE / 'sd2_gdb.py'),
                   '-ex', 'continue', '-ex', 'detach']
        started, last_frame = time.time(), 0
        frames, state = [], {}
        with (run.logs / 'sd2-gdb.log').open('w') as log:
            proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                while proc.poll() is None:
                    now = time.time()
                    path = run.run_dir / 'force.json'
                    if path.exists():
                        state = json.loads(path.read_text())
                    if state.get('error') or state.get('cycle'):
                        break
                    if state.get('forced'):
                        limit = 60 if mode == 'control' else 180
                        if now - state['forced_at'] >= limit:
                            break
                    elif now - started >= 120:
                        break
                    if now - last_frame >= frame_seconds:
                        frame = run._frame()
                        probe.keep_frame(frame, out_dir, f'sd2-{now-started:04.0f}s')
                        frames.append((now, hashlib.sha256(frame.tobytes()).hexdigest()))
                        last_frame = now
                    if probe.xemu_exit(run) is not None:
                        break
                    time.sleep(0.25)
            finally:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGINT)
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                xr.qmp_call(run.qmp_port, 'cont')
        path = run.run_dir / 'force.json'
        if path.exists():
            state = json.loads(path.read_text())
        elapsed = time.time() - state.get('forced_at', time.time())
        motion = []
        if state.get('forced'):
            for minute in range(3):
                lo = state['forced_at'] + minute * 60
                motion.append(len({h for t, h in frames if lo <= t < lo + 60}) >= 2)
        control = bool(state.get('cycle') and state['cycle']['seconds_since_force'] <= 60)
        fixed = bool(elapsed >= 180 and state.get('completed_lineups', 0) >= 2
                     and state.get('last_completion', 0) - state.get('forced_at', 0) >= 150
                     and len(motion) == 3 and all(motion))
        result = dict(classification='INFERRED', mode=mode, passed=bool(not state.get('error') and
                      (control if mode == 'control' else fixed)), elapsed_after_force=elapsed,
                      state=state, minute_motion=motion, gdb_exit=proc.returncode,
                      frames=len(frames), disc_writes=False)
        (run.run_dir / 'sd2-result.json').write_text(json.dumps(result, indent=2) + '\n')
        return result

    probe.play_on = play
    return probe.main()


if __name__ == '__main__':
    sys.exit(main())
