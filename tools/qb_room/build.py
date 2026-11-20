"""Compile the quarterback room page (beta 81 piece 3). Development requires GNU as/ld, gcc and pyelftools.

No game input is needed. entry.S and room.c are linked into one relocatable .text at page offset 0; the settings
record, counters and event ring live at fixed page offsets and are resolved here, so the C code holds no writable
data of its own. `--check` reproduces the checked-in template in mod_editor/core/nfl2k5_qb_room_code.py.
"""
from __future__ import annotations

import argparse
import re
import struct
import subprocess
import tempfile
from pathlib import Path

from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent
TARGET = HERE.parents[1] / "mod_editor/core/nfl2k5_qb_room_code.py"
DIVIDER = "# Generated from tools/qb_room by build.py.\n"
GCC_FLAGS = "-m32 -march=i386 -Os -fomit-frame-pointer -fno-builtin -fno-stack-protector -ffreestanding -fno-pic -fno-pie -fno-asynchronous-unwind-tables -Wall -Wextra -Werror".split()
PAGE_SIZE = 0x3000
CODE_LIMIT = 0x2000
# Page data the C code names as extern objects. Offsets are fixed by INTERFACE.md.
DATA = {"qb_settings": 0x2000, "qb_link_ir_store": 0x2020, "qb_counters": 0x2040, "qb_ring": 0x2400,
        "qb_ring_cursor": 0x2E00}
COUNTERS_LIMIT = 0x2400
EXPORTED = ("opening_entry", "room_entry", "opening_pass", "room_pass")


def counter_names():
    source = (HERE / "room.c").read_text(encoding="utf-8")
    block = re.search(r"/\* COUNTERS BEGIN.*?\*/\s*struct counters \{(.*?)\};\s*/\* COUNTERS END \*/", source, re.S)
    if not block:
        raise ValueError("room.c has no counters block")
    fields = [line.strip() for line in block.group(1).splitlines() if line.strip()]
    names = []
    for field in fields:
        match = re.fullmatch(r"u32 (\w+);(\s*/\*.*\*/)?", field)
        if not match:
            raise ValueError(f"counters must be plain u32 fields: {field!r}")
        names.append(match.group(1))
    if len(set(names)) != len(names) or DATA["qb_counters"] + 4 * len(names) > COUNTERS_LIMIT:
        raise ValueError("counter names must be unique and fit 0x2040..0x23FF")
    return names


def compile_page(temp):
    entry, logic, obj, script = (temp / name for name in ("entry.o", "room.o", "page.o", "page.ld"))
    script.write_text("SECTIONS { .text 0 : { *(.text*) *(.rodata*) *(.data*) *(COMMON) *(.bss*) } "
                      "/DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) *(.got*) } }")
    subprocess.run(["as", "--32", "-o", entry, HERE / "entry.S"], check=True)
    subprocess.run(["gcc", *GCC_FLAGS, "-c", HERE / "room.c", "-o", logic], check=True)
    with logic.open("rb") as stream:
        elf = ELFFile(stream)
        for name in (".data", ".bss"):
            section = elf.get_section_by_name(name)
            if section is not None and section.data_size:
                raise ValueError(f"room.c must keep no writable data in the code region ({name})")
    subprocess.run(["ld", "-r", "-m", "elf_i386", "-T", script, "-o", obj, entry, logic], check=True)
    return obj


def collect(temp):
    body = bytearray(b"\xcc" * CODE_LIMIT + bytes(PAGE_SIZE - CODE_LIMIT))
    labels, relocations = {}, []
    with compile_page(temp).open("rb") as stream:
        elf = ELFFile(stream)
        text = elf.get_section_by_name(".text")
        index = elf.get_section_index(".text")
        data = text.data()
        if len(data) >= CODE_LIMIT:
            raise ValueError("the code does not fit below the settings record")
        body[:len(data)] = data
        syms = elf.get_section_by_name(".symtab")
        for symbol in syms.iter_symbols():
            if symbol.name and symbol["st_shndx"] == index and symbol["st_info"]["type"] in ("STT_FUNC", "STT_NOTYPE"):
                labels[symbol.name] = symbol["st_value"]
        rel = elf.get_section_by_name(".rel.text")
        for fixup in rel.iter_relocations() if rel else ():
            field = fixup["r_offset"]
            symbol = syms.get_symbol(fixup["r_info_sym"])
            section, value = symbol["st_shndx"], symbol["st_value"]
            addend = struct.unpack_from("<i", data, field)[0] + value
            if section == index:
                family = "page"
            elif section == "SHN_UNDEF" and symbol.name in DATA:
                family, addend = "page", addend + DATA[symbol.name]
            elif section in ("SHN_UNDEF", "SHN_ABS") and not symbol.name:
                family = "stock"
            else:
                raise ValueError(f"Unsupported relocation to {symbol.name or section}")
            kind = fixup["r_info_type"]
            if kind not in (1, 2):
                raise ValueError(f"Unsupported i386 relocation {kind}")
            relocations.append((field, kind == 2, family, addend & 0xFFFFFFFF))
    return body, len(data), sorted(relocations), {name: labels[name] for name in EXPORTED}


def render():
    with tempfile.TemporaryDirectory(prefix="2k5-qb-room-") as folder:
        raw, code_bytes, fixes, labels = collect(Path(folder))
    lines = [DIVIDER.rstrip(), f"CODE_BYTES = {code_bytes:#x}", "", "_TEMPLATE = b''.join(("]
    pos = 0

    def literal(chunk):
        for start in range(0, len(chunk), 40):
            lines.append(f"    bytes.fromhex('{chunk[start:start + 40].hex()}'),")

    for match in re.finditer(rb"\x00{12,}|\xcc{12,}", bytes(raw)):
        literal(raw[pos:match.start()])
        length = match.end() - match.start()
        lines.append(f"    bytes({length})," if raw[match.start()] == 0 else f"    b'\\xcc' * {length},")
        pos = match.end()
    literal(raw[pos:])
    lines += ["))", "", "# (field offset, PC-relative, address family, offset including ELF addend)", "_RELOCATIONS = ("]
    for offset, relative, family, value in fixes:
        lines.append(f"    ({offset:#06x}, {relative}, {family!r}, {value:#x}),")
    lines += [")", "", "LABELS = {"]
    lines.extend(f"    {name!r}: {offset:#x}," for name, offset in sorted(labels.items()))
    lines += ["}", "", "# Counter name -> page offset, in the order of struct counters in tools/qb_room/room.c.",
              "COUNTERS = {"]
    lines.extend(f"    {name!r}: {DATA['qb_counters'] + 4 * n:#x}," for n, name in enumerate(counter_names()))
    return "\n".join([*lines, "}", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    old = TARGET.read_text(encoding="utf-8")
    prefix, marker, _ = old.partition(DIVIDER)
    if not marker:
        raise ValueError("Missing generated table marker")
    new = prefix + render()
    if args.check:
        if old != new:
            raise SystemExit("The quarterback room native template is stale")
    else:
        TARGET.write_text(new, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
