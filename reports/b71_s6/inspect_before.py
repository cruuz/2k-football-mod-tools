from pathlib import Path
import hashlib,json,sys,subprocess
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s,nfl2k5_scorebug_exact as e,nfl2k5_scorebug_ingame as r
out=ROOT/'reports/b71_s6'
BASE='0520e2e1df15818fe86494a13b7c55966d2a039c'
for name in ('assets','exact','resources','sprite'):
 path='mod_editor/core/nfl2k5_scorebug_'+name+'.py'
 before=subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)
 if before!=(ROOT/path).read_bytes():
  raise SystemExit('Historical baseline probe: run this script in the S5 '+BASE[:8]+' checkout. Preserve the already captured before artifacts.')
p=s.NativePreview();stats={}
for team in ('DEN','KC'):
 source=Image.open(ROOT/'data/nfl2k5_scorebug_mnf/logos'/f'{team.lower()}.png').convert('RGBA')
 panel=e.mnf_panel(team,'home');panel.save(out/f'{team}_before_input.png')
 span=p.chunks[1+sorted(r.TEAM_LOGOS).index(team)];ch,b,_=r.decode(span);t=r.tx.parse_texture(b,ch)
 decoded=Image.frombytes('RGBA',(t.width,t.height),r.tx.texture_to_rgba(b,ch,t));decoded.save(out/f'{team}_before_p8.png')
 a=np.asarray(panel);d=np.asarray(decoded);src=np.asarray(source)
 stats[team]=dict(source_size=list(source.size),source_zero_alpha=int((src[:,:,3]==0).sum()),source_black_transparent=int(((src[:,:,3]==0)&(src[:,:,:3].max(2)==0)).sum()),panel_zero_alpha=int((a[:,:,3]==0).sum()),panel_black_transparent=int(((a[:,:,3]==0)&(a[:,:,:3].max(2)==0)).sum()),transparent_pixels_made_visible=int(((a[:,:,3]==0)&(d[:,:,3]>0)).sum()),opaque_pixels_made_translucent=int(((a[:,:,3]==255)&(d[:,:,3]<255)).sum()),max_false_alpha=int(d[:,:,3][a[:,:,3]==0].max()))
ch,b,_=r.decode(p.atlas);t=r.tx.parse_texture(b,ch);decoded=Image.frombytes('RGBA',(t.width,t.height),r.tx.texture_to_rgba(b,ch,t));decoded.save(out/'atlas_before.png')
p.compiled.atlas.save(out/'atlas_before_input.png')
for name in ('body_left','body_middle','wing','capsule','red','plate'):
 box=p.compiled.cells[name];a=np.asarray(p.compiled.atlas.crop(box));d=np.asarray(decoded.crop(box));stats[name]=dict(alpha_max_error=int(abs(a[:,:,3].astype(int)-d[:,:,3]).max()),opaque_pixels_made_translucent=int(((a[:,:,3]==255)&(d[:,:,3]<255)).sum()),transparent_pixels_made_visible=int(((a[:,:,3]==0)&(d[:,:,3]>0)).sum()),rgba_unique=len(np.unique(d.reshape(-1,4),axis=0)))
(out/'before-diagnostics.json').write_text(json.dumps(stats,indent=2)+'\n');print(json.dumps(stats,indent=2))
