"""Read-only executable reference census, including record aliases and indirect loops."""
from pathlib import Path
import sys,json,struct
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
p=(ROOT/'extracted/ESPN NFL 2K5 (USA)/default.xbe').read_bytes();im=XbeImage(p)
cs=Cs(CS_ARCH_X86,CS_MODE_32);cs.detail=True;cs.skipdata=True
refs=[]
for s in im.sections:
 if not s.executable:continue
 for va,size,mn,op in cs.disasm_lite(im.read(s.start,s.raw_size),s.start):
  if any(0xa959c0 <= int(v,16) < 0xa95c60 for v in __import__('re').findall(r'0x[0-9a-f]+',op)) or '0xba2f14' in op:
   refs.append(dict(va=hex(va),instruction=mn+' '+op));print(hex(va),mn,op)
# All aligned/unaligned pointer constants anywhere, to detect stored aliases too.
for target in (0xa95a00,0xa95ae0,0xa95b50,0xa95bc0,0xa95c30,0xba2f14):
 hits=[];needle=struct.pack('<I',target)
 for s in im.sections:
  data=p[s.raw:s.raw+s.raw_size];at=0
  while (at:=data.find(needle,at))>=0:hits.append(hex(s.start+at));at+=1
 print('RAW_REFERENCE',hex(target),hits)
Path(__file__).with_name('writer_references.json').write_text(json.dumps(refs,indent=2)+'\n')
for i in range(6):
 at=0xa959c0+i*112
 print('ELEMENT_FIELDS',i,'canonical_origin',hex(at+8),'request',hex(at+0x40),'callback',hex(struct.unpack('<I',im.read(at+12,4))[0]),'closed/open',struct.unpack('<2f',im.read(at+0x34,8)))
