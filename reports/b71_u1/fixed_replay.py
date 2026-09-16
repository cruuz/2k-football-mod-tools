"""Exercise the fixed updater on actual release payloads, entirely offscreen.

The beta-71 archive is overlaid with this job's updater/launcher/GUI hooks.
This tests the new code, not an impossible retroactive fix in beta-70's code.
"""
from pathlib import Path
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from unittest.mock import patch
import venv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from mod_editor.core import self_update as U

BASE = Path('/tmp/claude-1000/-home-noah-Desktop-2K5-8-Editors/7d06c350-f66f-4c4d-acf4-cdbdbedff1da/scratchpad')
OLD = next((BASE / 'b70/ship/assets70').glob('2K5*.tar.gz'))
NEW = next((BASE / 'b71/ship/assets71').glob('2K5*.tar.gz'))
PATCHES = ('mod_editor/core/self_update.py', 'mod_editor/core/update_check.py', 'mod_editor/gui/studio_qt.py',
           'mod_editor/gui/update_ui.py', 'tools/launch_2k5_mod_studio.sh')

with tempfile.TemporaryDirectory(prefix='b71-u1-fixed-') as tmp:
    parent = Path(tmp)
    with tarfile.open(OLD) as archive:
        archive.extractall(parent, filter='data')
    root = parent / OLD.name.removesuffix('.tar.gz')
    venv.EnvBuilder(with_pip=False, system_site_packages=True, symlinks=True).create(root/'.venv')
    python = root/'.venv/bin/python3'
    new = parent / NEW.name
    with tarfile.open(NEW) as source, tarfile.open(new, 'w:gz') as dest:
        for member in source:
            relative = member.name.partition('/')[2]
            if relative in PATCHES:
                payload = (REPO / relative).read_bytes()
                member.size = len(payload)
                dest.addfile(member, io.BytesIO(payload))
            else:
                dest.addfile(member, source.extractfile(member) if member.isfile() else None)
    digest = hashlib.sha256(new.read_bytes()).hexdigest()
    new.with_name(new.name + '.sha256').write_text(f'{digest}  {new.name}\n')
    print('OVERLAID ARCHIVE', digest, 'patches', PATCHES, flush=True)
    files = [new, new.with_name(new.name+'.sha256')]
    document = {'tag_name':'beta-71.1', 'assets':[
        {'name':p.name, 'browser_download_url':'https://local.invalid/'+p.name, 'size':p.stat().st_size}
        for p in files]}
    def opener(url, timeout):
        return next(p for p in files if p.name == url.rsplit('/',1)[1]).open('rb')
    env = dict(QT_QPA_PLATFORM='offscreen', MOD_STUDIO_NO_UPDATE_CHECK='1',
               XDG_STATE_HOME=str(parent/'state'), XDG_CONFIG_HOME=str(parent/'config'),
               XDG_CACHE_HOME=str(parent/'cache'), PYTHONDONTWRITEBYTECODE='1')
    children = []
    popen = subprocess.Popen
    def record(*args, **kwargs):
        p = popen(*args, **kwargs)
        children.append(p)
        print('CHILD', json.dumps(dict(command=args[0], cwd=str(kwargs.get('cwd')), pid=p.pid)), flush=True)
        return p
    try:
        with patch.dict(os.environ, env), patch.object(U.subprocess, 'Popen', record):
            install = U.detect_install(root, executable=str(python))
            print('FIXED DETECTION', install, flush=True)
            start = time.monotonic()
            plan = U.run_update(document, install=install, work=parent/'download', opener=opener,
                                progress=lambda message, *_: print(message, flush=True) if message != 'Unpacking' else None)
            print('SUCCESS', round(time.monotonic()-start, 3), plan.notes, flush=True)
            print('LIVE CHILDREN', [(p.pid,p.poll()) for p in children], flush=True)
        utility_bin = parent/'utilities'
        utility_bin.mkdir()
        for name in ('bash','readlink','dirname','mkdir','tail'):
            (utility_bin/name).symlink_to(shutil.which(name))
        launch_env = dict(os.environ, **env)
        launch_env['PATH'] = str(utility_bin)
        launch_env.pop('MOD_STUDIO_PYTHON', None)
        command = [str(root/'tools/launch_2k5_mod_studio.sh'), '--update-check']
        result = subprocess.run(command, cwd=parent, env=launch_env, text=True, capture_output=True, timeout=60)
        print('REAL LAUNCHER, NO PYTHON ON PATH', json.dumps(dict(command=command, exit_code=result.returncode,
                                                                stdout=result.stdout, stderr=result.stderr)), flush=True)
        assert result.returncode == 0 and result.stdout.strip() == '1.0.0rc96'
        print('MODE', oct((root/'tools/launch_2k5_mod_studio.sh').stat().st_mode & 0o777), flush=True)
        assert not list((root/'mod_editor').rglob('__pycache__'))
        print('NO APP BYTECODE CACHES; PREVIOUS KEPT', root.with_name(root.name+'.previous').is_dir(), flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                print('STOPPED TEST GUI', child.pid, child.returncode, flush=True)
print('CLEANED all temporary extracted releases and runtimes', flush=True)
