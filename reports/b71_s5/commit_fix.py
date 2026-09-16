"""Commit the checked sampling correction and regenerated native evidence."""
from pathlib import Path
import subprocess
from run_logged import ROOT,run
base=['git','--git-dir=.scratch/b71-s5-git','--work-tree=.']
files=subprocess.check_output(base+['diff','--name-only'],cwd=ROOT,text=True).splitlines()
files=[p for p in files if p!='ASTRA_REPORT.md']
files+=['reports/b71_s5/prove_projection_identity.py','reports/b71_s5/projection-identity.json']
files=sorted(set(files))
if run('repin-opaque-commit',['python3','packaging/repin.py','--apply']):raise SystemExit(1)
subprocess.run(base+['add','--',*files],cwd=ROOT,check=True)
raise SystemExit(run('commit-opaque',base+['commit','-m','Sample atlas strips opaquely and prove the final native sprite output','--',*files]))
