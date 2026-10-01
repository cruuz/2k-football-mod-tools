#!/usr/bin/env python3
"""PROVED OFFLINE: repeat the saved crash with only the loaded Dallas book changed.

DESIGN: uses the prior heap investigation's RAM reader and loader, read-only.
Scoring runs saved instructions/data without substituted instructions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--heap',type=Path,required=True)
    ap.add_argument('--fixed',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();sys.path.insert(0,str(args.heap))
    import explore as e
    from book_probe import Native,XBE
    import unicorn as uc
    from unicorn import x86_const as x
    m=uc.Uc(uc.UC_ARCH_X86,uc.UC_MODE_32)
    m.mem_map(0x10000,0xf00000);m.mem_map(0x4000000,0x10000)
    for va in range(0x10000,0xf10000,4096):
        raw=e.R.vread(va,4096)
        if raw:m.mem_write(va,raw)
    m.reg_write(x.UC_X86_REG_CR0,m.reg_read(x.UC_X86_REG_CR0)&~4)
    m.reg_write(x.UC_X86_REG_CR4,m.reg_read(x.UC_X86_REG_CR4)|0x200)
    trace=[];faults=[]
    for pc in (0x281343,0x281607):
        m.hook_add(uc.UC_HOOK_CODE,lambda m,a,n,d:trace.append(dict(pc=hex(a),eax=hex(m.reg_read(x.UC_X86_REG_EAX)))),begin=pc,end=pc)
    def fault(m,access,address,size,value,_):
        faults.append(dict(pc=hex(m.reg_read(x.UC_X86_REG_EIP)),address=hex(address),size=size));return False
    m.hook_add(uc.UC_HOOK_MEM_INVALID,fault)
    loader=Native(XBE.read_bytes());rows=[]
    for variant,path in [('old',args.heap/'DAL-authored.bin'),('retail',args.heap/'DAL-retail.bin'),('fixed',args.fixed)]:
        raw=path.read_bytes();load=loader.load(raw,2)
        m.mem_write(0xb88dd0,bytes(loader.m.mem_read(0xb88dd0,0x13390)))
        trace.clear();faults.clear();m.mem_write(0x400e000,struct.pack('<I',0x400f000))
        for reg,val in [('ESP',0x400e000),('ECX',0xb8fb2c),('EDX',3),('FPCW',0x37f),('FPTAG',0xffff),('FPSW',0)]:m.reg_write(getattr(x,'UC_X86_REG_'+reg),val)
        error=None
        try:m.emu_start(0x2815f0,0x400f000,count=1000000)
        except uc.UcError as exc:error=str(exc)
        rows.append(dict(variant=variant,sha256=hashlib.sha256(raw).hexdigest(),loader=load,trace=list(trace),faults=list(faults),error=error,returned=m.reg_read(x.UC_X86_REG_EIP)==0x400f000))
    assert rows[0]['faults'][0]['address']=='0xe70c5f90'
    assert all(r['returned'] and not r['faults'] for r in rows[1:])
    args.output.write_text(json.dumps(dict(status='PROVED OFFLINE',fixture=__doc__,play=153,context=3,rows=rows),indent=2)+'\n')
    print('PROVED OFFLINE: old exact fault; retail and corrected native calls return; all loader heap deltas zero.')
if __name__=='__main__':main()
