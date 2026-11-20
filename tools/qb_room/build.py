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
# Further code pieces (INTERFACE.md): the tail of page 3 after the cursor and the menu slot holds .text.tail; page +
# 0x2200..0x23FF is reserved for code (zero until used), so the counters must end by 0x2200.
TAIL_START, TAIL_LIMIT = 0x2E10, 0x3000
RESERVED_CODE = (0x2200, 0x2400)
# Page data the C code names as extern objects. Offsets are fixed by INTERFACE.md.
DATA = {"qb_settings": 0x2000, "qb_link_ir_store": 0x2020, "qb_counters": 0x2040, "qb_ring": 0x2400,
        "qb_ring_cursor": 0x2E00, "qb_menu": 0x2E04,
        # moves.c's plain (non-volatile) names for the same counters and cursor (it is their only writer in a pass).
        "qb_counters_plain": 0x2040, "qb_ring_cursor_plain": 0x2E00}
COUNTERS_LIMIT = RESERVED_CODE[0]
EXPORTED = ("opening_entry", "room_entry", "opening_pass", "room_pass", "emergency_pass", "sign_entry", "sign_after",
            "pregame_entry", "floor_seat", "sign_ungated")


def counter_names():
    source = (HERE / "room.h").read_text(encoding="utf-8")
    block = re.search(r"/\* COUNTERS BEGIN.*?\*/\s*struct counters \{(.*?)\};\s*/\* COUNTERS END \*/", source, re.S)
    if not block:
        raise ValueError("room.h has no counters block")
    fields = [line.strip() for line in block.group(1).splitlines() if line.strip()]
    names = []
    for field in fields:
        match = re.fullmatch(r"u32 (\w+);(\s*/\*.*)?", field)
        if not match and field.startswith("/*"):
            continue
        if not match:
            raise ValueError(f"counters must be plain u32 fields: {field!r}")
        names.append(match.group(1))
    if len(set(names)) != len(names) or DATA["qb_counters"] + 4 * len(names) > COUNTERS_LIMIT:
        raise ValueError("counter names must be unique and fit 0x2040..0x21FF (112 counters)")
    return names


def compile_page(temp):
    entry, logic, moves, obj, script = (temp / name for name in ("entry.o", "room.o", "moves.o", "page.o", "page.ld"))
    # Piece 3 (the two entries, room.c's code and tables) first, exactly as before stage 4a; then moves.c and the
    # 4a stubs (entry.S section .text.sign), so adding 4a does not move a byte of piece 3. One output section: the
    # tail piece (functions marked TAIL in moves.c) is placed at page + 0x2E10 in it, so every label and relocation
    # stays page-relative; the bytes between the two pieces are not code and are never copied.
    script.write_text("SECTIONS { .text 0 : { *entry.o(.text) *room.o(.text*) *room.o(.rodata*) "
                      "*moves.o(.text) *moves.o(.rodata*) "
                      "*entry.o(.text.sign) *entry.o(.text.floor) *(.rodata*) *(.data*) *(COMMON) *(.bss*) "
                      f"qb_main_end = .; . = {TAIL_START:#x}; *(.text.tail) qb_tail_end = .; }} "
                      "/DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) *(.got*) } }")
    subprocess.run(["as", "--32", "-o", entry, HERE / "entry.S"], check=True)
    for source, output in (("room.c", logic), ("moves.c", moves)):
        subprocess.run(["gcc", *GCC_FLAGS, "-c", HERE / source, "-o", output], check=True)
        with output.open("rb") as stream:
            elf = ELFFile(stream)
            for name in (".data", ".bss"):
                section = elf.get_section_by_name(name)
                if section is not None and section.data_size:
                    raise ValueError(f"{source} must keep no writable data in the code region ({name})")
    subprocess.run(["ld", "-r", "-m", "elf_i386", "-T", script, "-o", obj, entry, logic, moves], check=True)
    return obj


def collect(temp):
    body = bytearray(b"\xcc" * CODE_LIMIT + bytes(PAGE_SIZE - CODE_LIMIT))
    labels, relocations = {}, []
    with compile_page(temp).open("rb") as stream:
        elf = ELFFile(stream)
        text = elf.get_section_by_name(".text")
        index = elf.get_section_index(".text")
        stray = [sec.name for sec in elf.iter_sections() if sec["sh_flags"] & 2 and sec.name != ".text" and sec.data_size]
        if stray:
            raise ValueError(f"code or data outside the page's .text: {stray}")
        data = text.data()
        syms = elf.get_section_by_name(".symtab")
        ends = {s.name: s["st_value"] for s in syms.iter_symbols() if s.name in ("qb_main_end", "qb_tail_end")}
        main_end, tail_end = ends["qb_main_end"], ends["qb_tail_end"]
        if main_end >= CODE_LIMIT:
            raise ValueError("the code does not fit below the settings record")
        if tail_end > TAIL_LIMIT or len(data) != tail_end:
            raise ValueError("the tail piece does not fit page + 0x2E10..0x2FFF")
        body[:main_end] = data[:main_end]
        body[TAIL_START:tail_end] = data[TAIL_START:tail_end]
        for symbol in syms.iter_symbols():
            if symbol.name and symbol["st_shndx"] == index and symbol["st_info"]["type"] in ("STT_FUNC", "STT_NOTYPE"):
                labels[symbol.name] = symbol["st_value"]
        rel = elf.get_section_by_name(".rel.text")
        for fixup in rel.iter_relocations() if rel else ():
            field = fixup["r_offset"]
            if not (field + 4 <= main_end or TAIL_START <= field and field + 4 <= tail_end):
                raise ValueError(f"relocation outside the code pieces at {field:#x}")
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
    return body, (main_end, tail_end - TAIL_START), sorted(relocations), {name: labels[name] for name in EXPORTED}


def render():
    with tempfile.TemporaryDirectory(prefix="2k5-qb-room-") as folder:
        raw, (code_bytes, tail_bytes), fixes, labels = collect(Path(folder))
    lines = [DIVIDER.rstrip(), f"CODE_BYTES = {code_bytes:#x}",
             f"CODE_TAIL = ({TAIL_START:#x}, {tail_bytes:#x})             # (page offset, bytes): the second code piece",
             f"CODE_RESERVED = ({RESERVED_CODE[0]:#x}, {RESERVED_CODE[1]:#x})        # reserved for code, zero until used",
             "", "_TEMPLATE = b''.join(("]
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
