"""Commit only the named final previews and their proof sources."""
from pathlib import Path
import subprocess
from run_logged import ROOT,run
out=ROOT/'reports/b71_s5'
files=sorted(str(p.relative_to(ROOT)) for p in out.iterdir() if p.is_file() and
 (p.suffix=='.png' and p.name not in ('first.png','first_crop.png','second.png') or
  p.suffix=='.py' and p.name not in ('write_report.py','commit_previews.py') or
  p.name in ('states.json','measurements.json','volume.json','day_43.json','day_169.json','studio-preview.json')))
git=['git','--git-dir=.scratch/b71-s5-git','--work-tree=.']
if run('repin-previews',['python3','packaging/repin.py','--apply']):raise SystemExit(1)
subprocess.run(git+['add','--',*files],cwd=ROOT,check=True)
raise SystemExit(run('commit-previews',git+['commit','-m','Record native sprite previews for all requested states and both aspects','--',*files]))
