"""Verify current seals and byte-identical S5 XBE owner and allocator output."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
GIT=['git','--git-dir=.scratch/b71-s6-git','--work-tree=.']
BASE=json.loads((ROOT/'.scratch/b71-s6-base.json').read_text())['base']
old=json.loads(subprocess.check_output(GIT+['show',BASE+':data/nfl2k5_cave_reservations.json'],cwd=ROOT))
new=json.loads((ROOT/'data/nfl2k5_cave_reservations.json').read_bytes())
assert all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in new['source_sha256'].items())
assert new['stack_xbe_sha256']==old['stack_xbe_sha256']
assert new['allocator_layout']==old['allocator_layout']
unchanged={}
for name in ('nfl2k5_scorebug_runtime.py','nfl2k5_scorebug_sprite_code.py','nfl2k5_xbe_space.py'):
 path='mod_editor/core/'+name
 before=subprocess.check_output(GIT+['show',BASE+':'+path],cwd=ROOT)
 assert before==(ROOT/path).read_bytes()
 unchanged[path]=hashlib.sha256(before).hexdigest()
result=dict(source_seals=len(new['source_sha256']),all_current=True,stack_xbe_sha256=new['stack_xbe_sha256'],same_xbe_and_allocations_as_s5=True,unchanged_owner_sources=unchanged,manifest_bytes=(ROOT/'data/nfl2k5_cave_reservations.json').stat().st_size,runtime_witnessed=False,disc_built=False,projection_model=new['model'])
assert result['manifest_bytes']<8*1024**2
(ROOT/'reports/b71_s6/projection-identity.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
