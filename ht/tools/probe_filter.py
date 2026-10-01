#!/usr/bin/env python3
"""PROVED OFFLINE: native historic franchise filter capacity, without xemu."""
import hashlib
import json
from pathlib import Path
import struct
import sys
from unicorn import UC_HOOK_CODE
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from nfl2k5_historic_quick_game_native import TeamSelectCPU,disc_evidence
retail=Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')
raw=(retail/'default.xbe').read_bytes()
resources,context,identities=disc_evidence(retail)
results=[]
for size in (None,50,51,65):
    cpu=TeamSelectCPU(raw,resources,context,identities)
    root=cpu.r(0xb72918)
    if size is not None:
        table,strings=0x26d0000,0x26e0000
        template=cpu.read(cpu.r(root+0x5c),16)
        for i in range(size):
            row=bytearray(template)
            struct.pack_into('<I',row,12,strings+128*i)
            cpu.write(table+16*i,row)
            cpu.write(strings+128*i,(f'club{i:03d}'+'\0').encode('utf-16le'))
        cpu.w(root+0x58,size);cpu.w(root+0x5c,table)
    writes=[]
    def before_store(uc,at,n,data):
        index=cpu.reg('esi')
        writes.append(dict(index=index,out_of_bounds=index>=50,address=hex(cpu.reg('esp')+16+4*index)))
        if index>=50:
            uc.emu_stop()  # record attempted spill; never execute the out-of-bounds store
    cpu.uc.hook_add(UC_HOOK_CODE,before_store,begin=0x2d1613,end=0x2d1613)
    try:
        returned=cpu.run(0x2d15a0)
    except AssertionError:
        assert writes and writes[-1]['out_of_bounds'] and cpu.reg('eip')==0x2d1613
        returned=None
    overflow=any(w['out_of_bounds'] for w in writes)
    results.append(dict(input='retail 75 descriptors' if size is None else f'{size} synthetic unique selector strings',
                        unique_attempts=len(writes),returned_menu_count=None if overflow else returned,
                        stopped_before_out_of_bounds_write=overflow,first_spill=next((w for w in writes if w['out_of_bounds']),None)))
    if size is None:
        assert returned==34 and len(writes)==33
        cpu.w(0xc8f15c,0)
        all_label=cpu.text(cpu.run(0x2d1630))
        cpu.w(0xc8f15c,1)
        first_label=cpu.text(cpu.run(0x2d1630))
    elif size==50:
        assert returned==51 and not overflow
    else:
        assert overflow and writes[-1]['index']==50
image=XbeImage(raw)
result=dict(label='PROVED OFFLINE',xbe_sha256=hashlib.sha256(raw).hexdigest(),
            code_sha256=hashlib.sha256(image.read(0x2d15a0,0x150)).hexdigest(),
            functions=dict(count='0x2d15a0',name='0x2d1630',selector='0xc8f15c'),
            capacity=dict(unique_franchise_strings=50,menu_entries_including_all=51,local_array_bytes=200),
            native_labels=dict(all=all_label,first=first_label),
            evidence='Both functions reserve 0xc8 stack bytes and clear 0x32 dwords. Count scans every descriptor '
                     'and writes a new string at ESP+0x10+4*ESI without checking ESI<50; it returns unique_count+1. '
                     'The name getter uses the same array and returns its ALL label for index zero.',
            results=results,limitation='Native count/string comparison executed. Synthetic tests halt immediately '
                     'before the first store beyond the array; no live menu, graphics, or game was run.')
(ROOT/'ht/evidence/franchise_filter.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
