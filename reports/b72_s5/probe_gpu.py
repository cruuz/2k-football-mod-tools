from pathlib import Path
import sys,json,traceback
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core.nfl2k5_scorebug_sprite import NativePreview
from tools.scorebug_sprite.gpu import capture_state
p=NativePreview()
print('preview ready',flush=True)
for wide in (False,True):
 g,c=p.capture({'away':'DET','home':'LV'},wide)
 try:
  r=capture_state(c)
  Path(f'reports/b72_s5/gpu_{wide}.json').write_text(json.dumps(r,indent=2)+'\n')
  print(wide,[(t['name'],len(t['methods'])) for t in r['rows']],flush=True)
 except Exception:
  traceback.print_exc();m=c['machine'];print('last instructions',[hex(x) for x in m.visits[-25:]],flush=True);raise
 finally:c['machine'].close()
