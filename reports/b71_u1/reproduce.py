"""Run shipped beta-70's updater against the local, sidecar-verified beta-71 archive.

No network, display, or writes outside a disposable sandbox. Full tarballs are
extracted sequentially; the installed app's own updater handles the update.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time

BASE = Path('/tmp/claude-1000/-home-noah-Desktop-2K5-8-Editors/7d06c350-f66f-4c4d-acf4-cdbdbedff1da/scratchpad')
OLD = next((BASE / 'b70/ship/assets70').glob('2K5*.tar.gz'))
NEW = next((BASE / 'b71/ship/assets71').glob('2K5*.tar.gz'))
PROBE = 'import mod_editor; import mod_editor.gui.studio_qt; print(mod_editor.__version__)'


def run(command, cwd, env):
    start = time.monotonic()
    p = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=60)
    print(json.dumps(dict(command=command, cwd=str(cwd), exit_code=p.returncode,
                          seconds=round(time.monotonic()-start, 3), stdout=p.stdout, stderr=p.stderr)), flush=True)
    return p


for archive in (OLD, NEW):
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.with_name(archive.name + '.sha256').read_text().split()[0] == digest
    print('SHA256', archive, digest, flush=True)

for local_runtime in (False, True):
    with tempfile.TemporaryDirectory(prefix='b71-u1-repro-') as tmp:
        parent = Path(tmp)
        with tarfile.open(OLD) as archive:
            archive.extractall(parent, filter='data')
        root = parent / OLD.name.removesuffix('.tar.gz')
        interpreter = Path(sys.executable)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                   PYTHONPATH=str(root), QT_QPA_PLATFORM='offscreen', MOD_STUDIO_NO_UPDATE_CHECK='1',
                   XDG_STATE_HOME=str(parent / 'state'))
        env.pop('DISPLAY', None)
        env.pop('WAYLAND_DISPLAY', None)
        if local_runtime:
            run([sys.executable, '-m', 'venv', '--without-pip', '--system-site-packages', str(root / '.venv')], root, env)
            interpreter = root / '.venv/bin/python3'
            env['PATH'] = str(interpreter.parent) + ':' + env['PATH']
        print('CASE', 'home-local-venv' if local_runtime else 'system-python', flush=True)
        assert run([str(interpreter), '-B', '-c', PROBE], root, env).returncode == 0
        assert run(['/bin/bash', str(root / 'tools/launch_2k5_mod_studio.sh'), '--help'], root, env).returncode == 0
        # A stale cache in the original tree must not become a new app cache.
        cache = root / 'mod_editor/__pycache__/sentinel.pyc'
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(b'old bytecode sentinel')
        child = '''
import os, sys, subprocess, json
from pathlib import Path
from mod_editor.core import self_update as U
new = Path(sys.argv[1])
files = [new, new.with_name(new.name + '.sha256')]
doc = {'tag_name':'beta-71', 'assets':[{'name':p.name, 'browser_download_url':'https://local.invalid/'+p.name, 'size':p.stat().st_size} for p in files]}
def opener(url, timeout):
    return next(p for p in files if p.name == url.rsplit('/',1)[1]).open('rb')
spawn = None
if sys.argv[2] == 'False':
    # Exercise imports without opening the GUI; retain the real planned command.
    def spawn(command, cwd):
        print('planned relaunch', command, flush=True)
        r = subprocess.run([command[0], '-B', '-c', 'import mod_editor; import mod_editor.gui.studio_qt; print(mod_editor.__version__)'], cwd=cwd, text=True, capture_output=True)
        print('headless relaunch probe', r.returncode, r.stdout, r.stderr, flush=True)
try:
    detected = U.detect_install()
    print('shipped auto-detection', detected, flush=True)
    try:
        U.plan_update(doc, detected)
    except U.SelfUpdateError as exc:
        print('RAW RELEASE UPDATE BUTTON REFUSED:', exc, flush=True)
    # The shipped archive contains an allowlisted tests/ file, which its own
    # detector mistakes for a source ZIP. Explicitly isolate the apply path:
    # this is a controlled runtime-loss reproduction, not an exact GUI witness.
    install = U.InstallKind('tarball', U.ROOT, (sys.executable, '-m', 'mod_editor', '--studio'))
    plan = U.run_update(doc, install=install, work=Path(sys.argv[3]), opener=opener, spawn_tarball=spawn)
    print('UPDATE RETURNED SUCCESS', plan.notes, flush=True)
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(1)
'''
        run([str(interpreter), '-B', '-c', child, str(NEW), str(local_runtime), str(parent/'download')], root, env)
        previous = root.with_name(root.name + '.previous')
        print('layout', sorted(p.name for p in parent.iterdir()), flush=True)
        print('after', json.dumps(dict(
            app_at_root=(root/'mod_editor/__main__.py').is_file(),
            nested_new_top=(root/NEW.name.removesuffix('.tar.gz')).exists(),
            launcher_mode=oct((root/'tools/launch_2k5_mod_studio.sh').stat().st_mode & 0o777),
            interpreter=str(interpreter), interpreter_exists=interpreter.exists(),
            previous_runtime=(previous/'.venv/bin/python3').exists(),
            new_cache=list(map(str, root.rglob('__pycache__'))),
            old_cache=(previous/'mod_editor/__pycache__/sentinel.pyc').exists(),
        )), flush=True)
        if local_runtime:
            # A SteamOS-style PATH has shell utilities but no system Python.
            utility_bin = parent / 'utilities'
            utility_bin.mkdir()
            for name in ('bash', 'readlink', 'dirname', 'mkdir', 'tail'):
                (utility_bin/name).symlink_to('/usr/bin/'+name)
            env['PATH'] = str(root/'.venv/bin') + ':' + str(utility_bin)
            result = run(['/bin/bash', str(root/'tools/launch_2k5_mod_studio.sh'), '--help'], root, env)
            assert result.returncode == 1
            assert 'Python 3 is not installed' in result.stderr
        else:
            assert run(['/bin/bash', str(root/'tools/launch_2k5_mod_studio.sh'), '--help'], root, env).returncode == 0
        print('CLEANUP sandbox', flush=True)
