from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebar_v3 as v3
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
for i in Cs(CS_ARCH_X86,CS_MODE_32).disasm(v3.VISIBILITY_CODE[:v3.COLOR_VA-v3.VISIBILITY_VA],v3.VISIBILITY_VA):
 print(hex(i.address),i.mnemonic,i.op_str)
