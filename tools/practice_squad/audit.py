#!/usr/bin/env python3
"""Read-only conservative cave and team-tail scan of the private US retail XBE.

Outputs addresses/counts, never executable bytes. Displacement matches are
candidates, not proof that the base register points to a team. Indirect and
computed control flow still requires review; no static sweep proves all play.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_practice_squad as ps


def audit(payload):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM
    if hashlib.sha256(payload).hexdigest() != ps.RETAIL_SHA256:
        raise ValueError('requires the pinned US retail XBE')
    sections=ps._sections(payload)
    text=next(s for s in sections if s.virtual_address==0x11000)
    lo=text.virtual_address
    raw=payload[text.raw_offset:text.raw_offset+text.raw_size]
    hits=set()

    def reference(source,target,kind):
        for start,size,_ in ps.CAVES:
            # Include the cave entry itself: these are dead-code caves, not
            # replacements whose old callers may continue using the entry.
            if start <= target < start+size and not start <= source < start+size:
                hits.add((source,target,kind))

    for i in range(len(raw)-5):
        if raw[i] in (0xE8,0xE9):
            reference(lo+i,(lo+i+5+struct.unpack_from('<i',raw,i+1)[0])&0xffffffff,'rel32')
        elif raw[i]==15 and 0x80<=raw[i+1]<=0x8f:
            reference(lo+i,(lo+i+6+struct.unpack_from('<i',raw,i+2)[0])&0xffffffff,'jcc32')
    for section in sections:
        start=section.raw_offset
        # Every unaligned text dword includes C7 callbacks with arbitrary
        # addressing modes. Every other section includes aligned pointer tables.
        for off in range(start,start+section.raw_size-3,1 if section==text else 4):
            reference(section.virtual_address+off-start,struct.unpack_from('<I',payload,off)[0],'absolute')
    md=Cs(CS_ARCH_X86,CS_MODE_32); md.detail=True; md.skipdata=True
    tail=[]; padding=[]; instructions=0
    for instruction in md.disasm(raw,lo):
        if not instruction.id: continue
        instructions+=1
        for op in instruction.operands:
            if op.type==X86_OP_IMM:
                reference(instruction.address,op.imm&0xffffffff,'decoded immediate/rel8')
            elif op.type==X86_OP_MEM:
                a,b=op.mem.disp,op.mem.disp+op.size
                if a<0x1f4 and b>0x19a:
                    tail.append(instruction.address)
                if any(a<=offset<b for offset in (0x19b,0x1f2,0x1f3)):
                    padding.append(instruction.address)
    return {'retail_sha256':ps.RETAIL_SHA256,'decoded_instructions':instructions,
            'caves':[[hex(a),n] for a,n,_ in ps.CAVES],
            'external_cave_references':[[hex(a),hex(b),k] for a,b,k in sorted(hits)],
            'tail_displacement_candidates':[hex(a) for a in sorted(set(tail))],
            'padding_overlap_candidates':[hex(a) for a in sorted(set(padding))]}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xbe',type=Path,default=Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION',
        '/media/noah/Storage/for codex 1.0/extracted'))/'ESPN NFL 2K5 (USA)'/'default.xbe')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=audit(args.xbe.read_bytes())
    if args.output: args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('_candidates')},indent=2))
    print(f"Tail candidates: {len(result['tail_displacement_candidates'])}; padding overlaps: {len(result['padding_overlap_candidates'])}")
    if result['external_cave_references']: raise SystemExit(1)
