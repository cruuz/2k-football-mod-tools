"""Full write allowlist and all-state field containment for the sprite owner."""
from pathlib import Path
import json,struct,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s,nfl2k5_scorebug_runtime as owner,nfl2k5_scorebug_exact as exact,nfl2k5_scorebug_resources as art
p=s.NativePreview();g,c=p.capture();m=c['machine'];patch=owner.apply(p.payload)[0];code,data=owner.sites(patch);labels=owner.code_for(code['va'],data['va'])[1]
# Displaced native visibility/setup calls have separate coverage. Isolate only
# our engine's writes here while preserving each original call instruction.
m.uc.mem_write(0xfc1a0,b'\xc3');m.uc.ctl_remove_cache(0xfc1a0,0xfc1f9)
allowed=[(m.STACK,m.STACK+0x10000,'stack'),(data['va'],data['va']+data['size'],'owner state'),(c['body']+0x1c0,c['body']+0x740,'scene materials'),(c['body']+0x2660,c['body']+0x2660+286*6,'positions'),(c['body']+0x2d20,c['body']+0x2d20+286*10,'UV and color')]
callbacks=[0xa95884+i*40 for i in range(5)]+[0xa95924,0xa9594c,0xa95984,0xa9596c,0xa959a4,0xa959cc,0xa95a3c,0xa95aec]
allowed += [(a,a+4,'bar callback or event material pointer') for a in callbacks]
result={}
for hook,args in [('setup',()),('update',(0x3c888889,))]:
 m.run(labels[hook],args,limit=500000)
 foreign=[(hex(a),size) for a,size,_ in m.writes if not any(lo<=a and a+size<=hi for lo,hi,_ in allowed)]
 result[hook]=dict(writes=len(m.writes),foreign=foreign)
 if foreign:raise AssertionError(result)
c['machine'].close()
# Deliberately oversized profile must fail the freeze-class volume gate.
with tempfile.TemporaryDirectory() as directory:
 folder=Path(directory);spec,image=s.load_layout();spec['atlas']=[512,512];image.save(folder/'template.png');(folder/'layout.json').write_text(json.dumps(spec))
 with p.pack_path.open('rb') as stream:
  view=art.PackView.from_fd(stream.fileno(),0,p.pack_path.stat().st_size)
  try:s.appendix(view,folder)
  except s.SpriteError as e:result['oversized_refusal']=str(e)
  else:raise AssertionError('oversized sprite profile was accepted')
# Receipts came from actual native captures of every matrix state/aspect.
states=json.loads((ROOT/'reports/b71_s6/states.json').read_text());errors=[];maxerror=0
for name,state in states.items():
 for f in p.compiled.spec['fields']:
  b=state['glyph_boxes'].get(f['name'])
  if b is None:continue
  lo,top,hi,bottom=exact.hud_box(f['box'])
  if name.endswith('_169'):lo,hi=[320+(v-320)*27/32 for v in (lo,hi)]
  error=max(0,lo-b[0],top-b[1],b[2]-hi,b[3]-bottom);maxerror=max(maxerror,error)
  if error>1:errors.append((name,f['name'],error))
result['field_containment']=dict(states=len(states),max_hud_error=maxerror,errors=errors)
if errors:raise AssertionError(result)
(ROOT/'reports/b71_s6/owner-bounds.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
