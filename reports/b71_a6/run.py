"""Run a command with a durable elapsed-time and exit-code receipt."""
from pathlib import Path
import datetime,json,os,shlex,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'reports/b71_a6'
def run(label,argv,env=None,log_label=None):
 start=time.monotonic(); now=datetime.datetime.now(datetime.timezone.utc).isoformat()
 target=REPORT/((log_label or label)+'.log')
 with target.open('w') as log:
  p=subprocess.run(argv,cwd=ROOT,env={**os.environ,'QT_QPA_PLATFORM':'offscreen','PYTHONPATH':str(ROOT)+':'+str(ROOT/'tools'),**(env or {})},stdout=log,stderr=subprocess.STDOUT)
 row=dict(label=label,command=shlex.join(argv),exit_code=p.returncode,seconds=round(time.monotonic()-start,3),started=now,log=str(target.relative_to(ROOT)))
 with (REPORT/'commands.jsonl').open('a') as out: out.write(json.dumps(row)+'\n')
 print(json.dumps({k:v for k,v in row.items() if k != "command"}),flush=True)
 return p.returncode
if __name__=='__main__':sys.exit(run(sys.argv[1],sys.argv[2:]))
