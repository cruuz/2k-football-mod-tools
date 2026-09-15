"""Run offline checks and record exit status, elapsed time and complete output."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[2]
args = sys.argv[1:]
label = args.pop(0)
lock = None
if label.startswith("test_"):
    # Two coordinators may drain the queue while long native files finish.
    # Each standalone suite still executes once; retries use a fresh label.
    lock = root / ".scratch" / "check-locks" / label
    lock.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            time.sleep(.1)
    records = Path(__file__).with_name("commands.jsonl")
    prior = next((json.loads(line) for line in reversed((records.read_text() if records.exists() else "").splitlines())
                  if json.loads(line)["log"] == f"reports/b71_apf4/{label}.log"), None)
    if prior is not None:
        lock.rmdir()
        print("Reused completed standalone result:", json.dumps(prior))
        sys.exit(prior["exit_code"])
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
begin = time.monotonic()
environment = dict(os.environ, PYTHONPATH=str(root), QT_QPA_PLATFORM="offscreen")
result = subprocess.run(args, cwd=root, env=environment, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True)
elapsed = time.monotonic() - begin
path = Path(__file__).parent / (label + ".log")
path.write_text(result.stdout, encoding="utf-8", newline="\n")
record = dict(command=args, started_utc=started, elapsed_seconds=round(elapsed, 3),
              exit_code=result.returncode, log=path.relative_to(root).as_posix())
with (Path(__file__).parent / "commands.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
    stream.write(json.dumps(record, sort_keys=True) + "\n")
print(json.dumps(record))
print(result.stdout[-6000:])
if lock is not None:
    lock.rmdir()
sys.exit(result.returncode)
