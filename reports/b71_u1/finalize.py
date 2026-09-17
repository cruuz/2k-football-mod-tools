"""Commit only explicit evidence paths, export and verify the private branch."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
records = []
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
clock = time.monotonic()
receipt = ROOT / '.scratch/delivery.json'


def command(args):
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    begin = time.monotonic()
    result = subprocess.run(args, text=True, capture_output=True)
    row = dict(command=args, start_utc=stamp, seconds=round(time.monotonic()-begin, 3),
               exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
    records.append(row)
    print(json.dumps(row), flush=True)
    if result.returncode:
        raise RuntimeError(f'command failed: {args}')
    return result.stdout.strip()


status = 1
try:
    command([sys.executable, 'packaging/repin.py', '--apply'])
    command([sys.executable, 'reports/b71_u1/render_command_report.py'])
    command(['git', '--git-dir=.scratch/private.git', 'diff', '--check'])
    evidence = sorted(str(p.relative_to(ROOT)) for p in (ROOT/'reports/b71_u1').iterdir()
                      if p.is_file() and p.suffix in ('.py', '.json', '.jsonl', '.txt', '.log'))
    paths = ['ASTRA_REPORT.md', 'ASTRA_LAST_MESSAGE.md', *evidence]
    command(['git', '--git-dir=.scratch/private.git', 'add', '--', *paths])
    command(['git', '--git-dir=.scratch/private.git', 'commit', '-m',
             'Document Linux update reproduction, compatibility and release validation', '--', *paths])
    command(['git', '--git-dir=.scratch/private.git', 'bundle', 'create', '.scratch/astra-b71-u1.bundle',
             '02bbadd184e85498a441d3be71e70f8de94b9b0a..astra/b71-u1-linux-update'])
    command(['git', '--git-dir=.scratch/private.git', 'bundle', 'verify', '.scratch/astra-b71-u1.bundle'])
    command(['git', '--git-dir=.scratch/private.git', 'bundle', 'list-heads', '.scratch/astra-b71-u1.bundle'])
    command(['git', '--git-dir=.scratch/private.git', 'diff', '--exit-code', 'HEAD', '--', *paths])
    original = command(['git', 'rev-parse', 'HEAD'])
    assert original == '02bbadd184e85498a441d3be71e70f8de94b9b0a'
    assert (ROOT/'ASTRA_LAST_MESSAGE.md').read_text().rstrip().endswith('ASTRA_DONE')
    command(['git', '--git-dir=.scratch/private.git', 'log', '-2', '--oneline'])
    status = 0
finally:
    bundle = ROOT/'.scratch/astra-b71-u1.bundle'
    result = dict(command=['python3', 'reports/b71_u1/finalize.py'], start_utc=started,
                  seconds=round(time.monotonic()-clock, 3), exit_code=status, commands=records,
                  bundle_bytes=bundle.stat().st_size if bundle.exists() else None,
                  bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest() if bundle.exists() else None)
    receipt.write_text(json.dumps(result, indent=2)+'\n')
    print('FINALIZATION', json.dumps({k:v for k,v in result.items() if k != 'commands'}), flush=True)
sys.exit(status)
