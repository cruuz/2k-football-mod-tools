from pathlib import Path
import sys,hashlib,struct,json
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_ingame as scene,nfl2k5_scorebug_runtime as runtime,nfl2k5_scorebug_resources as a,platform_compat as io
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
iso=Path('/home/noah/2K5 Mod Studio Builds/NFL 2K5 MOD TEST 2026-09-16n (sprite scorebug pass 2 + everything).xiso.iso')
with iso.open('rb') as f:
 entries,_=scene.layout.xc.parse_xdvdfs(f.fileno(),iso.stat().st_size)
 x=entries['default.xbe'];p=io.pread(f.fileno(),x.size,x.byte_offset)
 pack=entries['vc_53450030/0'];data=io.pread(f.fileno(),323808,pack.byte_offset+a.HUD_START+a.HUD_SIZE)
 chunks=scene.tx.parse_chunks(data);decoded=scene.decode(data[chunks[-1].offset:chunks[-1].end_offset])[1]
 code,state=runtime.sites(p);expected,_=runtime.code_for(code['va'],state['va'])
 print('owner code identical',p[code['raw']:code['raw']+code['size']]==expected,code)
 print('scene',len(decoded),hashlib.sha256(decoded).hexdigest())
 import nfl2k5_scorebug_projection as projection
 for slot,(material,indices) in enumerate(projection.submission_batches(decoded)):
  print('disc_n_submission',slot,'raw_material',material,'vertices',sorted(set(indices)))
 print('fields')
 for i in range(struct.unpack_from('<I',decoded,16520)[0]):
  print(struct.unpack_from('<8I6i',decoded,16544+i*56))
 for va,size in ((0xfc7d0,0x1be),(0xfbc70,0x47),(0x243d0,0x5a8),(0xfc9c0,0x309)):
  off=scene.layout.sbpos.va_to_off(p,va);retail=(ROOT/'extracted/ESPN NFL 2K5 (USA)/default.xbe').read_bytes();r=scene.layout.sbpos.va_to_off(retail,va)
  print('routine',hex(va),'identical',p[off:off+size]==retail[r:r+size])

from capstone import Cs,CS_ARCH_X86,CS_MODE_32
cs=Cs(CS_ARCH_X86,CS_MODE_32)
start,end=0xfc9c0,0xfccc9
a=scene.layout.sbpos.va_to_off(p,start);r=scene.layout.sbpos.va_to_off(retail,start)
changed=[start+i for i,(x,y) in enumerate(zip(p[a:a+end-start],retail[r:r+end-start])) if x!=y]
print('changed visibility bytes',[hex(v) for v in changed])
for ins in cs.disasm(p[a:a+end-start],start):
 if any(ins.address<=v<ins.address+ins.size for v in changed):print(hex(ins.address),ins.mnemonic,ins.op_str)
