import datetime, json, pathlib, shlex, subprocess, sys, time
root = pathlib.Path(__file__).resolve().parent
label, *cmd = sys.argv[1:]
log = root / 'audit' / (label + '.log')
start = datetime.datetime.now(datetime.timezone.utc).isoformat()
t0 = time.monotonic()
with log.open('w') as out:
    p = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT)
record = dict(label=label, command=shlex.join(cmd), start_utc=start, end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), seconds=round(time.monotonic()-t0,3), exit_code=p.returncode, log=str(log.relative_to(root.parent)))
with (root / 'commands.jsonl').open('a') as f: f.write(json.dumps(record)+'\n')
print(json.dumps(record), flush=True)
print(log.read_text(errors='replace')[-16000:], end='', flush=True)
sys.exit(p.returncode)
