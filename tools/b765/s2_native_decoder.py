"""Reusable offline check of the game's actual in-place chunk decoder.

Callers own the input/scope pins. This only executes recognized retail decoder
code on a supplied chunk and checks its original scratch allocation. It is an
offline CPU proof, not evidence of rendered gameplay.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct


def prove_chunk(data,chunk,xbe):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
    from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_EAX
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
    from mod_editor.core import nfl2k5_modern_metlife as ml
    executable=Path(xbe).read_bytes()
    digest=hashlib.sha256(executable).hexdigest()
    if digest!=RETAIL_SHA256:
        raise ValueError("Native decoder proof needs the recognized retail XBE")
    code=XbeImage(executable).read(0x4D000,0x2000)
    decoded,_=ml._tools()[0].decode_chunk(data,chunk)
    body=data[chunk.body_offset:chunk.end_offset]
    base,stack,stop=0x10000000,0x20000000,0x30000000
    uc=Uc(UC_ARCH_X86,UC_MODE_32)
    uc.mem_map(0x4D000,0x2000);uc.mem_write(0x4D000,code)
    allocation=len(decoded)+chunk.overlap_scratch_bytes
    mapped=(allocation+4095+4096)&~4095
    uc.mem_map(base,mapped);uc.mem_map(stack,0x10000);uc.mem_map(stop,0x1000)
    uc.mem_write(stop,b"\xf4");uc.mem_write(base,bytes([0xCC])*allocation)
    source=base+allocation-len(body);uc.mem_write(source,body)
    uc.mem_write(base+allocation,bytes([0xA5])*128)
    sp=stack+0x8000;uc.mem_write(sp,struct.pack("<I",stop))
    uc.reg_write(UC_X86_REG_ESP,sp);uc.reg_write(UC_X86_REG_ECX,source);uc.reg_write(UC_X86_REG_EDX,base)
    access=dict(max_read=0,max_write=0)
    def read_hook(_uc,_type,address,size,_value,_user):
        if base<=address<base+mapped:
            access["max_read"]=max(access["max_read"],address+size-base)
    def write_hook(_uc,_type,address,size,_value,_user):
        if base<=address<base+mapped:
            access["max_write"]=max(access["max_write"],address+size-base)
    uc.hook_add(UC_HOOK_MEM_READ,read_hook);uc.hook_add(UC_HOOK_MEM_WRITE,write_hook)
    uc.emu_start(0x4DC00,stop,count=20_000_000)
    if (bytes(uc.mem_read(base,len(decoded)))!=decoded
            or bytes(uc.mem_read(base+allocation,128))!=bytes([0xA5])*128
            or access["max_read"]>allocation or access["max_write"]>len(decoded)
            or uc.reg_read(UC_X86_REG_EAX)!=len(decoded)):
        raise ValueError("Native in-place decoder or allocation guard differs")
    return dict(xbe_sha256=digest,scratch=chunk.overlap_scratch_bytes,
                decoded_bytes=len(decoded),stored_bytes=len(body),offset_bits=body[8],
                exact_native_output=True,guard_unchanged=True,**access)
