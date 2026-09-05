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
    hits=set(); unaligned=set()

    def reference(source,target,kind,*,candidates=False):
        for start,size,_ in ps.CAVES:
            # Include the cave entry itself: these are dead-code caves, not
            # replacements whose old callers may continue using the entry.
            if start <= target < start+size and not start <= source < start+size:
                (unaligned if candidates else hits).add((source,target,kind))

    for i in range(len(raw)-5):
        if raw[i] in (0xE8,0xE9):
            reference(lo+i,(lo+i+5+struct.unpack_from('<i',raw,i+1)[0])&0xffffffff,'rel32')
        elif raw[i]==15 and 0x80<=raw[i+1]<=0x8f:
            reference(lo+i,(lo+i+6+struct.unpack_from('<i',raw,i+2)[0])&0xffffffff,'jcc32')
    for section in sections:
        start=section.raw_offset
        # Text dwords include C7 callbacks with arbitrary addressing modes.
        # Also report every unaligned non-text candidate, separately from the
        # aligned pointer-table gate: an arbitrary dword is not a proven pointer.
        for off in range(start,start+section.raw_size-3):
            reference(section.virtual_address+off-start,struct.unpack_from('<I',payload,off)[0],
                      'absolute',candidates=section!=text and (off-start)%4!=0)
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
            'unaligned_nontext_candidates':[[hex(a),hex(b),k] for a,b,k in sorted(unaligned)],
            'tail_displacement_candidates':[hex(a) for a in sorted(set(tail))],
            'padding_overlap_candidates':[hex(a) for a in sorted(set(padding))]}


def oracle_audit(payload, *, instruction_budget=250_000):
    """Reservations and conservative reachability, without concealing unknowns.

    The relocation brief allows source_root to be omitted for the pre-rebase
    manifest. Record its drift and separately check current composed stack
    bytes in test_xbe_patch_cave_references.py; never relabel unknown as free.
    """
    from mod_editor.core.nfl2k5_cave_oracle import (
        DEFAULT_MANIFEST, CaveOracle, ReservationManifest, XbeImage)
    root=Path(__file__).resolve().parents[2]
    manifest=ReservationManifest.load(DEFAULT_MANIFEST,XbeImage(payload))
    drift=[relative for relative,expected in manifest.document['source_sha256'].items()
           if not (root/relative).is_file() or
           hashlib.sha256((root/relative).read_bytes()).hexdigest()!=expected]
    oracle=CaveOracle(payload,manifest=manifest,instruction_budget=instruction_budget,
                      reference_budget=6_000_000).analyze()
    queries=[]
    for start,size,_ in ps.CAVES:
        row=oracle.assess(start,size)
        # Include all external witnesses for review, not just assess's first
        # eight (which usually consist of internal speculative branch targets).
        external=[e.report() for e in oracle.witnesses(start,start+size)
                  if e.source is not None and not start<=e.source<start+size]
        row['external_witnesses']=external
        queries.append(row)
    return {'manifest_sha256':hashlib.sha256(DEFAULT_MANIFEST.read_bytes()).hexdigest(),
            'source_root_checked':False,'manifest_source_drift':drift,
            'instruction_budget':instruction_budget,'instruction_count':oracle.instruction_count,
            'reference_budget':oracle.reference_budget,'reference_count':oracle.reference_count,
            'budget_exhausted':{'instructions':oracle._instruction_limit,'references':oracle._reference_limit},
            'unresolved_count':len(oracle.unknowns),
            'unresolved_kinds':sorted(oracle._unknown_kinds),'queries':queries}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xbe',type=Path,default=Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION',
        '/media/noah/Storage/for codex 1.0/extracted'))/'ESPN NFL 2K5 (USA)'/'default.xbe')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--oracle',action='store_true',help='also record stack reservations and oracle uncertainty')
    parser.add_argument('--instruction-budget',type=int,default=250_000)
    args=parser.parse_args()
    result=audit(args.xbe.read_bytes())
    if args.oracle:
        result['oracle']=oracle_audit(args.xbe.read_bytes(),instruction_budget=args.instruction_budget)
    if args.output: args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('_candidates') and k!='oracle'},indent=2))
    if args.oracle:
        print('Oracle verdicts:',[(q['start'],q['verdict']) for q in result['oracle']['queries']])
        if any(q['verdict'] in ('reserved','reachable') for q in result['oracle']['queries']):
            raise SystemExit('oracle found a reserved/reachable span; inspect the report')
    print(f"Tail candidates: {len(result['tail_displacement_candidates'])}; padding overlaps: {len(result['padding_overlap_candidates'])}")
    if result['external_cave_references']: raise SystemExit(1)
