"""Bounded XBE-only evidence helpers; never read an archive pack or whole disc."""
import importlib.util
import os
from pathlib import Path
import struct

from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core import nfl2k5_rdata_sites as rdata

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None
ARENA, STACK, RETURN, OUTPUT = 0x2000000, 0x2080000, 0x20F0000, 0x20F1000


def replace(payload, va, value):
    out = bytearray(payload)
    offset = rdata.offset_of(out, va)
    out[offset:offset + len(value)] = value
    for section in _sections(out):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(out, section)
    return bytes(out)


def load(payload):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    uc.mem_map(0x10000, 0x1500000 - 0x10000)
    uc.mem_map(ARENA, 0x100000)
    uc.mem_write(0x10000, payload[:struct.unpack_from("<I", payload, 0x108)[0]])
    for section in _sections(payload):
        uc.mem_write(section.virtual_address, payload[section.raw_offset:section.raw_offset + section.raw_size])
    return uc


def finish_float(uc, entry, esp, *args):
    from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP
    uc.mem_write(esp, struct.pack("<I", RETURN) + b"".join(struct.pack("<f", arg) for arg in args))
    uc.mem_write(RETURN, b"\xd9\x1d" + struct.pack("<I", OUTPUT))
    uc.reg_write(UC_X86_REG_ESP, esp)
    uc.emu_start(entry, RETURN + 6, count=10_000)
    if uc.reg_read(UC_X86_REG_EIP) != RETURN + 6:
        raise AssertionError("bounded guest execution did not reach its declared return")
    return struct.unpack("<f", bytes(uc.mem_read(OUTPUT, 4)))[0]
