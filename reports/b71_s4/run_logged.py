"""Run a named command and retain its exit, duration and complete output."""
from pathlib import Path
import datetime,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[2]
out=ROOT/'reports/b71_s4';out.mkdir(exist_ok=True)
name,*command=sys.argv[1:]
start=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic()
env={**os.environ,'PYTHONPATH':str(ROOT)+os.pathsep+str(ROOT/'tools'),'QT_QPA_PLATFORM':'offscreen'}
with (out/(name+'.log')).open('w') as log:
 p=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
row=dict(name=name,command=command,start=start,end=datetime.datetime.now(datetime.timezone.utc).isoformat(),seconds=round(time.monotonic()-t,3),exit=p.returncode)
(out/(name+'.result.json')).write_text(json.dumps(row,indent=2)+'\n')
print(json.dumps(row),flush=True)
raise SystemExit(p.returncode)
