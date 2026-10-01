"""Catalog only authored sponsor rectangles and shared helper dependencies."""
from pathlib import Path
import json,hashlib,re
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'packaging/nfl2k5_scorebug_template_pngs.json';doc=json.loads(p.read_text())
doc['files']={k:v for k,v in doc['files'].items() if not k.startswith('data/nfl2k5_stadium_shared_art/')}
for image in sorted((ROOT/'data/nfl2k5_stadium_shared_art/venues').rglob('*.png')):
 with Image.open(image) as im:doc['files'][str(image.relative_to(ROOT))]=dict(width=im.width,height=im.height,size=image.stat().st_size,sha256=hashlib.sha256(image.read_bytes()).hexdigest())
p.write_text(json.dumps(doc,indent=2,sort_keys=True)+'\n')
checker=ROOT/'packaging/check_2k5_mod_studio_release.py';text=checker.read_text()
text=re.sub(r'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "[0-9a-f]{64}"','SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "'+hashlib.sha256(p.read_bytes()).hexdigest()+'"',text);checker.write_text(text)
allow=ROOT/'packaging/release-allowlist.txt';text=allow.read_text()
text='\n'.join(line for line in text.splitlines() if not (
    line.startswith('data/nfl2k5_stadium_shared_art/')
    or line in {'mod_editor/core/nfl2k5_stadium_shared_art.py',
                'mod_editor/core/nfl2k5_model_fan_art.py',
                'tools/nfl2k5_residual_sponsor_art.py', 'tools/nfl2k5_fan_art_2026.py'}
    or line.startswith('# fb:') or line.startswith('# fb2:')))
required={'mod_editor/core/nfl2k5_stadium_shared_art.py','mod_editor/core/nfl2k5_model_fan_art.py','tools/nfl2k5_residual_sponsor_art.py'}
required.update(str(p.relative_to(ROOT)) for p in (ROOT/'data/nfl2k5_stadium_shared_art').rglob('*') if p.is_file())
missing=sorted(required-set(text.splitlines()))
if missing:allow.write_text(text.rstrip()+'\n\n# fb2: u4 model banner wiring and residual sponsor panels.\n'+'\n'.join(missing)+'\n')
