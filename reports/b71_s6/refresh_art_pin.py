"""Pin the reviewed authored PNG and seal its catalog without relaxing checks."""
from pathlib import Path
import hashlib,json,re,struct
ROOT=Path(__file__).resolve().parents[2]
path=ROOT/'data/nfl2k5_scorebug_sprite/template.png';data=path.read_bytes()
catalog=ROOT/'packaging/nfl2k5_scorebug_template_pngs.json';document=json.loads(catalog.read_text())
key=str(path.relative_to(ROOT));before=document['files'][key]
w,h=struct.unpack_from('>II',data,16)
document['files'][key]=dict(height=h,sha256=hashlib.sha256(data).hexdigest(),size=len(data),width=w)
catalog.write_text(json.dumps(document,indent=2,sort_keys=True)+'\n')
sha=hashlib.sha256(catalog.read_bytes()).hexdigest()
checker=ROOT/'packaging/check_2k5_mod_studio_release.py'
s,count=re.subn(r'(?m)^SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "[0-9a-f]+"$',f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{sha}"',checker.read_text());assert count==1
checker.write_text(s)
result=dict(path=key,before=before,after=document['files'][key],catalog_sha256=sha)
(ROOT/'reports/b71_s6/art-pin.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
