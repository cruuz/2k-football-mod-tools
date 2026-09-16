"""Checkpoint complete proofs while the independent XBE gates continue."""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/b71_s6'
files=['data/nfl2k5_cave_reservations.json','docs/mod_editor/sprite_scorebug.md']
files+=sorted(str(p.relative_to(ROOT)) for p in OUT.iterdir() if p.is_file() and not p.name.startswith('gate-'))
git=['git','--git-dir=.scratch/b71-s6-git','--work-tree=.']
subprocess.run(['python3','packaging/repin.py','--apply'],cwd=ROOT,check=True)
subprocess.run(git+['diff','--check'],cwd=ROOT,check=True)
subprocess.run(git+['add','--',*files],cwd=ROOT,check=True)
subprocess.run(git+['commit','-m','Record S6 native visual proofs and equivalent bounded cave projection','--',*files],cwd=ROOT,check=True)
