from pathlib import Path
import sys,json,struct
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s
import nfl2k5_scorebug_projection as p
preview=s.NativePreview()
for state in ('pre_snap','after_play','live','kickoff','flag','fumble'):
 c={}
 try:
  g=p.native_geometry(preview.payload,preview.scene,fonts=preview.fonts,texture_span=preview.atlas,runtime_textures=preview.textures,capture=c,visibility_state=state,down=1,distance_yards=10)
  m=c['machine'];live=c['live_decoded']
  print(state,'requests',[m.get(0xa95a00+i*112) for i in range(6)],'colours',[hex(struct.unpack_from('<I',live,0x2d20+q['vertex']*10)[0]) for q in preview.compiled.quads if q['name'].startswith('down:')],flush=True)
  print('material_state',[(hex(m.get(int(v['address'],16)+0x64)),hex(m.get(int(v['address'],16)+0x68))) for v in g['materials']],flush=True)
 finally:
  if c:c['machine'].close()
