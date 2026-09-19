"""Native retained sequence, request writer trace and event occlusion differential."""
from pathlib import Path
import sys,json,struct,hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'tests/mod_editor')]
from test_nfl2k5_scorebug_down_visibility import Sequence
from mod_editor.core import nfl2k5_scorebug_sprite as s,nfl2k5_scorebug_ingame as scene
from prove_states import refresh,raster
from PIL import Image,ImageChops
import unicorn
OUT=Path(__file__).resolve().parent
STAGES=[('kickoff','kickoff',None,1),('ball_on','after_play',True,1),
        ('latched_pre_snap','pre_snap',None,1)]
STAGES += [('after_kickoff_down_'+str(d),'pre_snap',False if d==1 else None,d) for d in range(1,5)]
STAGES += [('flag','flag',None,2)]
STAGES += [('after_flag_down_'+str(d),'pre_snap',None,d) for d in range(1,5)]
STAGES += [('fumble','fumble',None,3),('after_fumble','pre_snap',None,3)]
preview=s.NativePreview();records=[]
for wide in (False,True):
 aspect='169' if wide else '43';seq=Sequence(preview,wide);m=seq.machine;writes=[]
 def write(uc,access,va,size,value,data):
  if va in (0xa95a00,0xa95ae0,0xa95b50,0xa95bc0,0xa95c30):
   writes.append(dict(pc=hex(m.uc.reg_read(m.x.UC_X86_REG_EIP)),address=hex(va),value=value))
 hook=m.uc.hook_add(unicorn.UC_HOOK_MEM_WRITE,write)
 try:
  for name,state,latch,down in STAGES:
   seq.configure(state,down=down,latch=latch)
   frames=[]
   for frame in range(65):
    writes.clear();row=seq.step()
    row['writers']=list(writes)
    frames.append(row)
   entered,draw=seq.native_draw();g=draw|seq.geometry;c=seq.capture
   refresh(g,c)
   visible=seq.read()['visible_glyphs']
   event_visible = any(i in entered for i in (2,3,4,5))
   assert visible==(0 if state=='kickoff' or event_visible else 5),(name,visible)
   if name.startswith('after_'):assert frames[-1]['requests']==[1,1,0,0,0,0]
   path=OUT/(name+'_'+aspect+'.png')
   raster(preview,seq.mode,g,c,path)
   # Differential: identical native geometry/material state, remove only the
   # owner's down colours. Zero changed pixels proves full event occlusion.
   actual=c['live_decoded'];masked=bytearray(actual)
   for q in seq.rows:
    for j in range(4):struct.pack_into('<I',masked,scene.layout.S1+(q['vertex']+j)*10,0)
   c['live_decoded']=bytes(masked)
   tmp=ROOT/'.scratch/b72-s1-masked-label.png';raster(preview,seq.mode,g,c,tmp);c['live_decoded']=actual
   diff=ImageChops.difference(Image.open(path).convert('RGB'),Image.open(tmp).convert('RGB'))
   changed=sum(any(v) for v in diff.getdata());tmp.unlink()
   if state in ('flag','fumble','kickoff') or name in ('ball_on','latched_pre_snap'):assert changed==0,(name,aspect,changed)
   else:assert changed>25,(name,aspect,changed)
   im=Image.open(path).convert('RGB').crop((0,16,640,464)).resize(s.DISPLAY[wide]['size'],Image.Resampling.LANCZOS)
   im.save(OUT/(name+'_'+aspect+'_display.png'))
   result=dict(aspect=aspect,name=name,input=dict(state=state,latch_call=latch,down=down),frames=frames,
               native_draw_elements=entered,draws=[dict(callback=d['callback'],text=d['text']) for d in draw['draws']],
               down_changed_pixels=changed,runtime_witnessed=False)
   records.append(result);print(name,aspect,'requests',frames[-1]['requests'],'glyphs',visible,'visible label pixels',changed,flush=True)
 finally:
  m.uc.hook_del(hook);seq.close()
(OUT/'native_sequence.json').write_text(json.dumps(dict(stages=records,runtime_witnessed=False,
 boundaries=['Synthetic gameplay objects and predicate returns, not a full gameplay simulation',
 'FC330/FC340 are native latch calls; their high-level world callers are not executed',
 'No request, slide, binding, material or colour is reset between sequence stages',
 'Native CPU rendering and software raster only; no NV2A or emulator']),indent=2)+'\n')
print('PROVED native sequence and occlusion; played symptom cause remains UNWITNESSED',flush=True)
