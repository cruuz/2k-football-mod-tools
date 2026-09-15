"""Observe the complete XBE writer stack without copying a disc image.

Retain historical retail reservations; regenerate owned bytes and source seals
from the actual current writers. This is an XBE projection, not a disc receipt.
"""
from pathlib import Path
import hashlib,json,os,subprocess,sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.mycareer_mode import refresh_settings_manifest as projection
from mod_editor.core import nfl2k5_modern_color as color
original=projection.CaveReferenceTests.setUpClass

def setup(cls):
    original()
    cls.patched=color.apply(cls.patched)[0]

output=ROOT/'.scratch/b71-s3-manifest.json'
# Always regenerate from the integration parent, never from an earlier probe.
# rules_patch.apply delegates on behalf of its module argument; observing both
# it and coin_defer/decided_clock/cpu_scrambles would invent duplicate owners.
parent=ROOT/'.scratch/b71-s3-parent-manifest.json'
parent.write_bytes(subprocess.check_output(['git','show','a7440f05:data/nfl2k5_cave_reservations.json'],cwd=ROOT))
helpers=projection.SHARED_HELPERS|{'nfl2k5_rules_patch'}
non_xbe={**projection.NON_XBE,
 'mod_editor/core/nfl2k5_scorebug_exact.py':'scene geometry and atlas author; validated by native rendering and compiler suites',
 'mod_editor/core/nfl2k5_scorebug_mnf_font.py':'pack FONT author; private lookup and relocation covered by native font suites',
 'mod_editor/core/nfl2k5_scorebug_resources.py':'pack compiler; validated by collection loader and resource suites'}
with patch.object(projection,'CHANGED_WRITERS',{'nfl2k5_scorebug_runtime','nfl2k5_modern_color'}), \
     patch.object(projection,'NON_XBE',non_xbe), \
     patch.object(projection,'SHARED_HELPERS',helpers), \
     patch.object(projection,'DEFAULT_MANIFEST',parent), \
     patch.dict(os.environ,NFL2K5_CAVE_MANIFEST=str(parent)), \
     patch.object(projection.CaveReferenceTests,'setUpClass',classmethod(setup)):
    summary=projection.refresh(output)
doc=json.loads(output.read_bytes())
doc['model']='BOUNDED BETA-71 S3 XBE PROJECTION; retained historical retail reservations and freshly observed complete forward XBE stack; no disc build'
doc['b71_s3_projection']=doc.pop('settings_projection')
output.write_text(json.dumps(doc,indent=2)+'\n')
(ROOT/'data/nfl2k5_cave_reservations.json').write_bytes(output.read_bytes())
summary['manifest_sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
print(json.dumps(summary,indent=2))
