"""The same native owner obeys a changed JSON design without a code change."""
from pathlib import Path
import hashlib,json,struct,sys,tempfile
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s,nfl2k5_scorebug_runtime as owner
code=hashlib.sha256(owner.code_for(0,0)[0]).hexdigest()
with tempfile.TemporaryDirectory() as directory:
 folder=Path(directory);spec,image=s.load_layout();image.save(folder/'template.png')
 f=spec['fields'][0];assert f['name']=='away_score';f['anchor'][0]+=6;f['size']=40;f['colour']='#FFAA22'
 (folder/'layout.json').write_text(json.dumps(spec))
 p=s.NativePreview(folder=folder);g,c=p.capture()
 try:
  q=next(q for q in p.compiled.quads if q['name']=='away_score:0');points=g['positions'][q['vertex']:q['vertex']+4]
  x=(min(v[0] for v in points)+max(v[0] for v in points))/2;y=max(v[1] for v in points)-min(v[1] for v in points)
  assert abs(x-f['anchor'][0]/3)<.02
  assert abs(y-40*448/1080)<.02
  assert struct.unpack_from('<I',c['live_decoded'],0x2d20+q['vertex']*10)[0]==0xffffaa22
  assert code==hashlib.sha256(owner.code_for(0,0)[0]).hexdigest()
  result=dict(owner_sha256=code,custom_anchor=f['anchor'],native_center_x=x,custom_height=40,native_height=y,colour='0xFFFFAA22',code_changed=False)
 finally:c['machine'].close()
(ROOT/'reports/b71_s6/custom-design.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
