from pathlib import Path
import sys,inspect
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s
import nfl2k5_scorebug_projection as p
from PIL import Image
preview=s.NativePreview();g,c=preview.capture(dict(down=1,away='DAL',home='KC',possession='away'))
try:
 code=inspect.getsource(p.render_native).replace('if z > depth[at] + .001:', 'if False:')
 ns=p.__dict__.copy();exec(code,ns)
 for name,fn in [('depth',p.render_native),('submission',ns['render_native'])]:
  out=ROOT/'reports/b71_s9'/('shipped_'+name+'.png')
  fn(c['live_decoded'],preview.atlas,preview.fonts,g,out,texture_spans=c['texture_spans'],background=Image.new('RGB',(640,480),'#333333'))
  Image.open(out).crop((80,404,552,455)).resize((1416,153)).save(out.with_name(out.stem+'_crop.png'))
finally:c['machine'].close()
