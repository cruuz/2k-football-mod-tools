"""Measure RGB error in the requested ink rectangles of the saved native renders."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.nfl2k5_scorebug_exact import wide_reference

out=ROOT/'reports/b71_s4'
m=json.loads((out/'measurements.json').read_bytes())
path=Path(m['reference']['path'])
assert hashlib.sha256(path.read_bytes()).hexdigest()==m['reference']['sha256']
source=Image.open(path).convert('RGB')
reference=Image.new('RGB',(640,480))
reference.paste(source.resize((640,448),Image.Resampling.LANCZOS),(0,16))
results={}
for aspect in ('43','wide'):
 render_path=out/('render_'+aspect+'.png')
 pixels=np.asarray(Image.open(render_path).convert('RGB')).astype(float)
 wanted=np.asarray(wide_reference(reference) if aspect=='wide' else reference).astype(float)
 c=m['comparisons'][aspect];rows={}
 for callback,row in c['text'].items():
  a,b,d,e=[round(v) for v in row['reference_ink_box']]
  role=c['callback_roles'][callback]
  rows[role]=dict(reference_source_box=m['reference']['text_source_boxes'][role],
                 measured_hud_box=[a,b,d,e],compared_pixels=(d-a)*(e-b),
                 rgb_mae=float(np.abs(wanted[b:e,a:d]-pixels[b:e,a:d]).mean()))
 results[aspect]=dict(render_sha256=hashlib.sha256(render_path.read_bytes()).hexdigest(),text=rows)
result=dict(reference_sha256=m['reference']['sha256'],comparisons=results,
            method='Same rounded HUD reference rectangles and RGB absolute-error mean as compare(); includes the background within each ink bounding box, no glyph segmentation.')
(out/'text_rgb_mae.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
