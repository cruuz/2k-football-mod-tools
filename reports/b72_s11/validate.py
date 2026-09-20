"""Run the job's offline validations sequentially with retained receipts."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
COMMANDS = {
    'fit': ['reports/b72_s11/fit.py'],
    'repin': ['packaging/repin.py', '--apply'],
    'regression': ['tests/mod_editor/test_nfl2k5_scorebug_logo_retention.py'],
    'sprite': ['tests/mod_editor/test_nfl2k5_scorebug_sprite.py'],
    'baseline': ['reports/b72_s11/player_scale.py', 'baseline'],
    'final': ['reports/b72_s11/player_scale.py', 'final'],
    'audit': ['reports/b72_s11/audit.py'],
    'sheets': ['reports/b72_s11/sheets.py'],
    'events': ['reports/b72_s11/retained_sequences.py'],
    'checks': ['reports/b72_s11/run_checks.py'],
    'owner': ['reports/b72_s11/scan_owner.py'],
    'closures': ['reports/b72_s11/run_closures.py'],
}


def main():
    for name in sys.argv[1:] or COMMANDS:
        command = [sys.executable, *COMMANDS[name]]
        start = time.monotonic()
        with (OUT/(name+'_validation.log')).open('w', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=ROOT,
                env=dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM='offscreen'),
                stdout=log, stderr=subprocess.STDOUT, timeout=1800)
        row = dict(check=name, command=command, exit_code=result.returncode, seconds=round(time.monotonic()-start, 2))
        print(json.dumps(row), flush=True)
        with (OUT/'validation_progress.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row)+'\n')
        if result.returncode:
            return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
