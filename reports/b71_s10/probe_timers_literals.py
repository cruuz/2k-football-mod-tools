"""Timers clear without a draw call; enumerate native phase formatter literals."""
from pathlib import Path
import json,sys,struct
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'tests/mod_editor')]
from test_nfl2k5_scorebug_down_visibility import Sequence
from mod_editor.core import nfl2k5_scorebug_sprite as s
import unicorn
p=s.NativePreview();seq=Sequence(p,False);m=seq.machine;out={};writes=[]
def trace(uc,access,va,size,value,data):
 if va in [0xa95a00+i*112 for i in range(6)]:writes.append(dict(pc=hex(m.uc.reg_read(m.x.UC_X86_REG_EIP)),address=hex(va),value=value))
hook=m.uc.hook_add(unicorn.UC_HOOK_MEM_WRITE,trace)
try:
 seq.configure('pre_snap',latch=False)
 for _ in range(40):seq.step()
 # FC9C0 returns before altering element requests in phase zero. The timer
 # itself is native FC730; the subsequent native integrator expires it.
 m.put(0xe602b4,0)
 for index in range(6):
  m.run(0xfc730,(struct.unpack('<I',struct.pack('<f',.1))[0],),ecx=index)
  rows=[]
  for _ in range(12):
   writes.clear();row=seq.step();row['writers']=list(writes);rows.append(row)
  assert rows[0]['requests'][index]==1
  assert rows[-1]['requests'][index]==0
  assert any(w['pc']=='0xfcf19' and w['address']==hex(0xa95a00+index*112) for r in rows for w in r['writers'])
  out['timer_'+str(index)]=rows
 buffer=m.alloc(256);literal=[]
 for phase in range(6):
  m.put(0xe602b4,phase)
  for period in (1,5):
   m.put(0xe602c4,period);m.uc.mem_write(buffer,bytes(256));m.run(0xfc7d0,ecx=buffer)
   literal.append(dict(phase=phase,period=period,text=m.read_string(buffer)))
 out['native_literals']=literal
finally:m.uc.hook_del(hook);seq.close()
Path(__file__).with_name('timers_literals.json').write_text(json.dumps(out,indent=2)+'\n')
print('All six native timed requests cleared at FCf19 without calling the draw loop.',flush=True)
print(json.dumps(literal,indent=2),flush=True)
