"""Record exact job commands, UTC start, elapsed seconds, exit status and output."""
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[2]
label, command = sys.argv[1:]
start = datetime.datetime.now(datetime.timezone.utc).isoformat()
clock = time.monotonic()
result = subprocess.run(command, shell=True, cwd=root, executable="/bin/bash",
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
row = dict(label=label, command=command, start_utc=start,
           seconds=round(time.monotonic() - clock, 3), exit_code=result.returncode)
(Path(__file__).parent / (label + ".log")).write_text(result.stdout)
with (Path(__file__).parent / "commands.jsonl").open("a") as handle:
    handle.write(json.dumps(row) + "\n")
print(json.dumps(row), flush=True)
print(result.stdout, end="", flush=True)
sys.exit(result.returncode)
