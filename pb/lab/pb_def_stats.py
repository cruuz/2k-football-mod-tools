#!/usr/bin/env python3
"""PROVED OFFLINE mechanism: invoke retail stat reader on main's copied guest RAM.
DESIGN: slot-based reporting supports retail and final roster without guessing identity.
"""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
import sys
sys.path.insert(0,'/media/noah/Storage/.b76-research/r1/re')
from guest_stats import GuestVM,SELECTORS
from unicorn import x86_const as reg

class CheckedGuestVM(GuestVM):
    def call_float(self,fn,ecx,edx,stack_args=()):
        # DESIGN: same reader as r1, with an explicit instruction-budget return check.
        mu=self.mu;sp=self.STACK
        for a in reversed(stack_args):
            sp-=4;mu.mem_write(sp,struct.pack('<I',a))
        sp-=4;mu.mem_write(sp,struct.pack('<I',self.RET))
        mu.reg_write(reg.UC_X86_REG_ESP,sp);mu.reg_write(reg.UC_X86_REG_ECX,ecx);mu.reg_write(reg.UC_X86_REG_EDX,edx)
        mu.emu_start(fn,self.RET,count=2_000_000)
        if mu.reg_read(reg.UC_X86_REG_EIP)!=self.RET:raise RuntimeError('Native stat reader exceeded its instruction budget')
        stub=self.RET+0x100
        mu.mem_write(stub,b'\xd9\x1d'+struct.pack('<I',self.RET+0x800)+b'\xf4')
        mu.emu_start(stub,stub+6,count=10)
        value=struct.unpack('<f',bytes(mu.mem_read(self.RET+0x800,4)))[0]
        if not math.isfinite(value):raise RuntimeError('Native stat reader returned nonfinite data')
        return value

def read(path):
    vm=CheckedGuestVM(str(path));rows=[]
    for side,base in (('copy0',0xB30C4C),('copy1',0xB321A0)):
        for slot in range(65):
            va=base+slot*0x54;record=vm.read(va,0x54)
            if not any(record):continue
            stats={k:round(vm.stat(va,v,0),3) for k,v in dict(SELECTORS,sacks=184).items()}
            rows.append(dict(side=side,slot=slot,record_sha256=hashlib.sha256(record).hexdigest(),stats=stats))
    return dict(snapshot=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),players=rows,
        scope='PROVED OFFLINE: native 0xCB240 on RAM copy; side-to-team identity requires frames')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('snapshots',nargs='+',type=Path);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--delete-after',action='store_true');a=ap.parse_args()
    result=[read(p) for p in a.snapshots];a.out.write_text(json.dumps(result,indent=2)+'\n')
    if a.delete_after:
        for p in a.snapshots:p.unlink()
    print(json.dumps([dict(snapshot=r['snapshot'],occupied=len(r['players'])) for r in result]))
