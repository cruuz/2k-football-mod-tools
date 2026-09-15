"""Inspect task outputs without running the external disc build."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_resources as r,nfl2k5_scorebug_runtime as owner
from mod_editor.core.nfl2k5_cave_manifest import source_fingerprints
manifest=json.loads((ROOT/'data/nfl2k5_cave_reservations.json').read_bytes())
assert manifest['source_sha256']==source_fingerprints()
assert r.probe_sizes('mnf')[1]==413568
plan=json.loads((ROOT/'.scratch/testdisc71h/plan.json').read_bytes())
assert all(plan['options'].values())
assert plan['scorebug_version']=='scorebug-mnf-2026-v3'
assert Path(plan['target']).name=='NFL 2K5 MOD TEST 2026-09-15h (scorebug v3 + colour + widescreen).xiso.iso'
for key in ('scorebug','scorebug_runtime','modern_color','widescreen'):assert plan['plan'][key]
print(json.dumps(dict(volume_bytes=r.probe_sizes('mnf')[1],native_heap_bytes=66*5376+sum((s+127)//128*128 for s in (38048,27040)),code_bytes=len(owner.code_for(0,0)[0].rstrip(b'\xcc')),code_budget=owner.CODE_SIZE,manifest_sources_fresh=True,builder_plan=plan['options']),indent=2))
