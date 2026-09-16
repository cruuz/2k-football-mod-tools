"""Read-only instruction evidence; no retail executable bytes are exported."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
from nfl2k5_scorebug_position_patch import va_to_off
p=(ROOT/'extracted/ESPN NFL 2K5 (USA)/default.xbe').read_bytes()
cs=Cs(CS_ARCH_X86,CS_MODE_32)
for arg in sys.argv[1:]:
 start,end=(int(v,16) for v in arg.split(':'))
 print('\nROUTINE',hex(start),hex(end))
 off=va_to_off(p,start)
 for i in cs.disasm(p[off:off+end-start],start):print(f'{i.address:08x}  {i.mnemonic:9} {i.op_str}')
