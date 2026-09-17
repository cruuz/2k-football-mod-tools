"""Exercise the history predicate the earlier zero-count fixture omitted."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'tests/mod_editor')]
from test_nfl2k5_scorebug_down_visibility import Sequence
from mod_editor.core import nfl2k5_scorebug_sprite as s
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
p=s.NativePreview();im=XbeImage(p.payload);results=[]
for wide in (False,True):
 seq=Sequence(p,wide);m=seq.machine
 try:
  seq.configure('pre_snap',latch=False)
  m.uc.mem_write(0xa7940,im.read(0xa7940,6));m.uc.ctl_remove_cache(0xa7940,0xa7946)
  # Actual A7940/A7970 ring reader; sampled history entries are explicit inputs.
  m.put(0xb6ff64,2)
  for index,team in ((1,0xe5fc20),(2,0xe5fc60)):
   a=0xb6e7f0+(index%5)*0x4b0;m.put(a,index);m.put(a+0x30,team)
  for _ in range(45):row=seq.step()
  entered,draw=seq.native_draw();row.update(aspect=wide,native_draw_elements=entered,history='different +0x20 team values',draws=[dict(callback=d['callback'],text=d['text']) for d in draw['draws']])
  assert row['latch']==0 and row['requests']==[1,1,0,0,1,0]
  assert 0 in entered and 4 in entered
  results.append(row)
  m.put(0xb6e7f0+0x4b0+0x30,0xe5fc60)
  for _ in range(45):row=seq.step()
  row.update(aspect=wide,history='equal +0x20 team values')
  assert row['requests']==[1,1,0,0,0,0] and row['visible_glyphs']==5
  results.append(row)
 finally:seq.close()
Path(__file__).with_name('history_probe.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2),flush=True)
