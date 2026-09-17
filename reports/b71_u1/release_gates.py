"""Stage each product from this worktree, gate it, then remove the stage."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time

repo = Path(__file__).resolve().parents[2]
env = dict(os.environ, QT_QPA_PLATFORM='offscreen', MOD_STUDIO_NO_UPDATE_CHECK='1',
           PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
failed = False
with tempfile.TemporaryDirectory(prefix='b71-u1-release-gates-') as folder:
    for product, allowlist in (('2k5', 'release-allowlist.txt'), ('apf2k8', 'apf2k8-release-allowlist.txt')):
        stage = Path(folder)/product
        commands = [
            [sys.executable, 'packaging/stage_release.py', 'packaging/'+allowlist, str(stage)],
            [sys.executable, f'packaging/check_{product}_mod_studio_release.py', str(stage)],
            [sys.executable, str(stage/f'packaging/check_{product}_mod_studio_runtime.py')],
            [sys.executable, f'packaging/check_{product}_mod_studio_release.py', str(stage)],
        ]
        for command in commands:
            start = time.monotonic()
            p = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True)
            print(json.dumps(dict(command=command, exit_code=p.returncode,
                                  seconds=round(time.monotonic()-start, 3))), flush=True)
            print(p.stdout, p.stderr, flush=True)
            if p.returncode:
                failed = True
                break
print('CLEANED staged release trees', flush=True)
sys.exit(int(failed))
