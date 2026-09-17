from pathlib import Path
import sys,json,struct
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s,nfl2k5_scorebug_ingame as scene
p=s.NativePreview();g,c=p.capture(dict(down=1,away='DAL',home='KC'));m=c['machine'];b=c['body']
try:
 print('SHAPE',hex(scene.layout.SHAPE),'instance',hex(m.get(0xa9552c)-b),'shape pointer',hex(m.get(m.get(0xa9552c)+8)-b))
 shape=b+scene.layout.SHAPE
 print('shape fields',[(hex(i),hex(m.get(shape+i))) for i in (0x50,0x54,0x70,0x80,0x90)])
 for i,mat in enumerate(g['materials']):
  a=int(mat['address'],16)
  print('material',i,mat,'shader',hex(m.get(a+4)),'next',hex(m.get(a+28)),'flags60',hex(m.get(a+0x60)),'flags70',hex(m.get(a+0x70)))
 for k in range(m.get(shape+0x54)&65535):
  a=m.get(shape+0x70)+k*128
  print('draw_descriptor',k,'offset',hex(a-b),'material',m.get(a)&65535,'commands',hex(m.get(a+0x78)-b),'words',m.get(a+0x7c)&65535)
 for q in p.compiled.quads:
  if q['name']=='plate' or q['name'].startswith('down:'):
   a=b+scene.layout.S1+q['vertex']*10
   print('quad',q['name'],'material',q['material'],'vertex',q['vertex'],'z',q['z'],'rgba',hex(m.get(a)),'uv',struct.unpack('<2h',m.uc.mem_read(a+4,4)))
 print('volume',p.volume['appended_bytes'])
finally:m.close()
