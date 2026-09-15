from pathlib import Path
import sys,json,time
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_modern_arrowhead as art,nfl2k5_modern_color as colour
packs=ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030'
names=sys.argv[1:] or ['s13nd.iff']
for name in names:
 t=time.monotonic(); pin=next(p for p in art._pins()['bundles'] if p['name']==name)
 with art._outer_image()(packs) as archive:
  e=archive.entries[pin['outer']];retail=archive.read(e.virtual_offset,e.size)
 graded,_=colour.modern_bundle(retail,outer_index=pin['outer'])
 combined,edits=art.combined_bundle(retail,graded,outer_index=pin['outer'])
 print(json.dumps(dict(name=name,sha256=art.sha(combined),seconds=time.monotonic()-t,edits=edits)),flush=True)
