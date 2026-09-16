"""Check regenerated source seals and show the atlas fix leaves XBE bytes identical."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
old=json.loads(subprocess.check_output(['git','--git-dir=.scratch/b71-s5-git','--work-tree=.','show','d006dddc:data/nfl2k5_cave_reservations.json'],cwd=ROOT))
path=ROOT/'data/nfl2k5_cave_reservations.json';new=json.loads(path.read_bytes())
assert all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in new['source_sha256'].items())
assert new['stack_xbe_sha256']==old['stack_xbe_sha256']
assert new['allocator_layout']==old['allocator_layout']
result=dict(source_seals=len(new['source_sha256']),all_current=True,stack_xbe_sha256=new['stack_xbe_sha256'],
 same_xbe_and_allocations_as_before_atlas_uv_fix=True,manifest_bytes=path.stat().st_size,
 manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),runtime_witnessed=False,disc_built=False)
(ROOT/'reports/b71_s5/projection-identity.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
