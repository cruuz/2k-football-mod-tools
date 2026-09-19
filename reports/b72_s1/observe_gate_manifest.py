"""Observe a fresh pure-XBE gate manifest without touching the release manifest.

The complete scaleout safety-gate fixture executes real writers under Recorder.
No parent source hash or historic disc observation is promoted to a fresh one.
"""
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import ast,hashlib,importlib,inspect,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_cave_manifest as builder,nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256,MANIFEST_SCHEMA,ReservationManifest,XbeImage
from mod_editor.core.nfl2k5_bump_strength import _sections,section_digest
from tests.mod_editor import test_xbe_patch_memory_writes as gate
from tests import nfl2k5_allocator_stack  # preload every owner used by compose

parent=ROOT/'data/nfl2k5_cave_reservations.json';parent_hash=hashlib.sha256(parent.read_bytes()).hexdigest()
# Preload every lazily imported core writer in the fixture before wrapping.
tree=ast.parse(Path(gate.__file__).read_text())
for node in ast.walk(tree):
 if isinstance(node,ast.ImportFrom) and node.module=='mod_editor.core':
  for alias in node.names:importlib.import_module('mod_editor.core.'+alias.name)
retail=gate.XBE.read_bytes();assert len(retail)<16*1024**2 and hashlib.sha256(retail).hexdigest()==RETAIL_SHA256
fingerprints=builder.source_fingerprints();recorder=builder.Recorder(retail)
modules=[m for name,m in tuple(sys.modules.items()) if m is not None and
 (name.startswith('mod_editor.core.nfl2k5_') or name.startswith('nfl2k5_'))]
with ExitStack() as context:
 for module in modules:
  for name in ('apply','apply_xbe','xbe_apply','plan_patch','apply_arc_table','patch_xbe','apply_chop_block'):
   function=getattr(module,name,None)
   if inspect.isfunction(function) and function.__module__==module.__name__:
    context.enter_context(patch.object(module,name,recorder.wrapper(module,name)))
 gate.ScaleoutOwnerTests.setUpClass()
 final=gate.ScaleoutOwnerTests.patched
assert all(section_digest(final,s)==s.stored_digest for s in _sections(final))
spans=recorder.finish(final)
assert fingerprints==builder.source_fingerprints()
document=dict(schema=MANIFEST_SCHEMA,retail_sha256=RETAIL_SHA256,complete=True,
 model='Observed pure XBE safety-gate composition with all allocator owners; no disc or resource build',
 stack_image_size=XbeImage(final).image_size,stack_xbe_sha256=hashlib.sha256(final).hexdigest(),
 section_digests_verified=True,allocator_layout=space.layout(final),source_sha256=fingerprints,
 image_steps=[],steps=recorder.steps,spans=spans,release_manifest=False,disc_built=False)
ReservationManifest(document,XbeImage(retail),source_root=ROOT)
assert hashlib.sha256(parent.read_bytes()).hexdigest()==parent_hash
out=ROOT/'.scratch/b72-s1-gate-manifest.json'
out.write_text(json.dumps(document,indent=2)+'\n',newline='\n')
summary=dict(manifest=str(out.relative_to(ROOT)),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
 steps=len(recorder.steps),spans=len(spans),release_manifest_changed=False,disc_built=False,
 source_sha256=fingerprints,stack_xbe_sha256=document['stack_xbe_sha256'])
(Path(__file__).parent/'gate_manifest_summary.json').write_text(json.dumps(summary,indent=2)+'\n',newline='\n')
print(json.dumps({k:v for k,v in summary.items() if k!='source_sha256'},indent=2))
