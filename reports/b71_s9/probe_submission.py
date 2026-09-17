"""Execute retail shape submission into a bounded RAM command stream."""
from pathlib import Path
import sys,json,struct,hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s,nfl2k5_scorebug_ingame as scene
import unicorn
p=s.NativePreview();g,c=p.capture(dict(down=1));m=c['machine'];b=c['body']
try:
 off=scene.layout.sbpos.va_to_off(p.payload,0x28110)
 m.uc.mem_write(0x28110,p.payload[off:off+6]);m.uc.ctl_remove_cache(0x28110,0x28116)
 context=m.alloc(0x400);head=m.alloc(128);gpu=m.alloc(65536)
 m.put(head,context);m.put(0xa6aa6c,head);m.put(context+4,m.get(b+0x1c0+4));m.put(context+12,gpu)
 # Boundary substitutions: material shader/texture binder and stream declaration;
 # no material selection, visibility, descriptor iteration or index-copy replacement.
 m.uc.mem_write(0x24160,bytes.fromhex('c20800'));m.uc.mem_write(0x315c0,b'\xc3')
 m.uc.mem_write(0x22950,bytes.fromhex('8b44240cc20c00'))
 rows=[]
 def trace(u,va,size,data):
  if va==0x24555:
   mat=m.uc.reg_read(m.x.UC_X86_REG_ECX);desc=m.uc.reg_read(m.x.UC_X86_REG_EDI)
   rows.append(dict(descriptor=hex(desc-b),material=(mat-b-0x1c0)//128,name=m.read_string(m.get(mat)),visible=not(m.get(mat+8)&1),commands=hex(m.get(desc+0x78)-b),words=m.get(desc+0x7c)&65535))
 hook=m.uc.hook_add(unicorn.UC_HOOK_CODE,trace)
 m.run(0x243d0,(m.get(b+256+0x20),0,0),ecx=b+scene.layout.SHAPE,edx=c['matrices'],limit=200000)
 m.uc.hook_del(hook)
 submitted=bytes(m.uc.mem_read(gpu,m.get(context+12)-gpu));cursor=0
 for row in rows:
  if not row['visible']:continue
  commands=bytes(m.uc.mem_read(b+int(row['commands'],16),row['words']*4))
  at=submitted.find(commands,cursor)
  assert at>=cursor,(row,cursor)
  row['gpu_word_offset']=at//4;row['command_sha256']=hashlib.sha256(commands).hexdigest();cursor=at+len(commands)
 print(json.dumps(dict(rows=rows,words_written=len(submitted)//4,gpu_stream_sha256=hashlib.sha256(submitted).hexdigest(),command_bytes_preserved_in_order=True),indent=2))
 # Execute the real material state encoder with a deliberately invalid cache.
 for i in range(4):m.put(context+0x20+i*4,~m.get(b+0x1c0+0x60+i*4)&0xffffffff)
 m.put(context+12,gpu)
 m.run(0x2fc80,(0,),ecx=context,edx=b+0x1c0+0x60)
 print('render_state_words', [hex(m.get(a)) for a in range(gpu,m.get(context+12),4)])
except BaseException:
 print('last_visits',[hex(a) for a in m.visits[-20:]])
 raise
finally:m.close()
