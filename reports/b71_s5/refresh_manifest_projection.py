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
    # Bootstrap only the named S5 RX reservation; actual writer receipts below
    # replace this temporary geometry. All other allocations must stay exact.
    from mod_editor.core import nfl2k5_xbe_space as space
    from tests.nfl2k5_allocator_stack import REQUESTS
    boot=json.loads(parent.read_bytes());old=boot['allocator_layout']['allocations']
    wanted=space.plan(REQUESTS)['allocations'];current={(a['owner'],a['kind']):a for a in wanted}
    for a in old:
        key=a['owner'],a['kind']
        if key not in current:continue
        b=current[key]
        if key==('nfl2k5_scorebug_runtime','code'):
            lo,hi=a['va'],a['va']+a['size']
            for row in boot['spans']:
                start,end=int(row['start'],0),int(row['end'],0)
                if row['owner']==a['owner'] and lo<=start<end<=hi:
                    end=b['va']+b['size'] if (start,end)==(lo,hi) else end+b['va']-lo
                    start+=b['va']-lo;row.update(start=hex(start),end=hex(end),size=end-start)
            a.update(b)
        elif (a['va'],a['size'])!=(b['va'],b['size']):
            raise ValueError('S5 unexpectedly moved another owner: '+str(key))
    seed=ROOT/'.scratch/b71-s5-bootstrap.json';seed.write_text(json.dumps(boot)+'\n')
    with patch.dict(os.environ,NFL2K5_CAVE_MANIFEST=str(seed)):
        original()
    cls.patched=color.apply(cls.patched)[0]

output=ROOT/'.scratch/b71-s5-manifest.json'
# Always regenerate from the integration parent, never from an earlier probe.
# rules_patch.apply delegates on behalf of its module argument; observing both
# it and coin_defer/decided_clock/cpu_scrambles would invent duplicate owners.
parent=ROOT/'.scratch/b71-s5-parent-manifest.json'
parent.write_bytes(subprocess.check_output(['git','show','cea8a3c8:data/nfl2k5_cave_reservations.json'],cwd=ROOT))
helpers=projection.SHARED_HELPERS|{'nfl2k5_rules_patch'}
non_xbe={**projection.NON_XBE,
 'mod_editor/core/nfl2k5_scorebug_sprite.py':'PNG/JSON pack compiler and read-only native preview; no XBE writer',
 'mod_editor/core/nfl2k5_scorebug_sprite_code.py':'generated instructions installed and observed through nfl2k5_scorebug_runtime',
 'tools/nfl2k5_scorebug_reference.py':'disc copy dispatcher; sprite default covered by resource round trips',
 'tools/nfl2k5_scorebug_exact.py':'offline scene comparison and pack compiler pins; no XBE writer',
 'tools/nfl2k5_scorebug_projection.py':'offline native raster geometry and FONT parser; no XBE writer',
 'mod_editor/core/nfl2k5_build_settings.py':'saved colour and Arrowhead options; no XBE write',
 'mod_editor/core/nfl2k5_modern_arrowhead.py':'pack scene art and combined colour composition; no XBE write',
 'tools/nfl2k5_modern_arrowhead_art.py':'offline bitmap author; no XBE write',
 'mod_editor/core/nfl2k5_scorebug_exact.py':'scene geometry and atlas author; validated by native rendering and compiler suites',
 'mod_editor/core/nfl2k5_scorebug_mnf_font.py':'pack FONT author; private lookup and relocation covered by native font suites',
 'mod_editor/core/nfl2k5_scorebug_resources.py':'pack compiler; validated by collection loader and resource suites'}
with patch.object(projection,'CHANGED_WRITERS',{'nfl2k5_scorebug_runtime','nfl2k5_scorebug_ingame','nfl2k5_xbe_space','nfl2k5_modern_color'}), \
     patch.object(projection,'NON_XBE',non_xbe), \
     patch.object(projection,'SHARED_HELPERS',helpers), \
     patch.object(projection,'DEFAULT_MANIFEST',parent), \
     patch.dict(os.environ,NFL2K5_CAVE_MANIFEST=str(parent)), \
     patch.object(projection.CaveReferenceTests,'setUpClass',classmethod(setup)):
    summary=projection.refresh(output)
doc=json.loads(output.read_bytes())
doc['model']='BOUNDED BETA-71 S5 XBE PROJECTION; retained historical retail reservations and freshly observed complete forward XBE stack; no disc build'
doc['b71_s5_projection']=doc.pop('settings_projection')
output.write_text(json.dumps(doc,indent=2)+'\n')
(ROOT/'data/nfl2k5_cave_reservations.json').write_bytes(output.read_bytes())
summary['manifest_sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
print(json.dumps(summary,indent=2))
