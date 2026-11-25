"""Compile the CPU trades pages (beta 81, owner nfl2k5_cpu_trades). Development requires GNU as/ld, gcc and pyelftools;
no game input.

entry.S and trades.c (with tools/common/team_need.h) are linked into one relocatable .text at page offset 0 (at most
CODE_LIMIT bytes). The pages also hold the settings record (+0x1B00), the counters (+0x1B20), the ring cursor (+0x1BE0),
the records of ours during a pending scan (+0x1BE4, six words), the clubs in our records this call (+0x1BFC) and the
event ring (+0x1C00, 64 x 16 bytes), all zero in the template; trades.c reaches them as externs that become relocations of family "page".
`--check` reproduces the checked-in module mod_editor/core/nfl2k5_cpu_trades_code.py.
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
TARGET = HERE.parents[1] / "mod_editor/core/nfl2k5_cpu_trades_code.py"
DIVIDER = "# Generated from tools/cpu_trades by build.py.\n"
GCC_FLAGS = ("-m32 -march=i386 -Os -fomit-frame-pointer -fno-builtin -fno-stack-protector -ffreestanding -fno-pic "
             "-fno-pie -fno-asynchronous-unwind-tables -fno-tree-loop-distribute-patterns -Wall -Wextra -Werror").split()
PAGE_SIZE = 0x2000
CODE_LIMIT = 0x1B00
PAGE = {"ct_settings": 0x1B00, "ct_counters": 0x1B20, "ct_ring_cursor": 0x1BE0, "ct_current": 0x1BE4,
        "ct_round_mask": 0x1BFC, "ct_ring": 0x1C00}
EXPORTED = ("trade_entry", "trade_call", "story_entry", "story_is_ours")


def counter_names():
    """The counters struct's field names in order (between COUNTERS BEGIN and COUNTERS END in trades.c)."""
    text = (HERE / "trades.c").read_text(encoding="utf-8")
    block = text.split("COUNTERS BEGIN", 1)[1].split("COUNTERS END", 1)[0]
    return tuple(re.findall(r"^\s*u32 (\w+);", block, re.M))


def compile_page(temp):
    entry, logic, obj, script = (temp / name for name in ("entry.o", "trades.o", "page.o", "page.ld"))
    script.write_text("SECTIONS { .text 0 : { *entry.o(.text) *trades.o(.text) *(.rodata*) *(.data*) *(COMMON) *(.bss*) "
                      "cpu_trades_end = .; } /DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) *(.got*) } }")
    subprocess.run(["as", "--32", "-o", entry, HERE / "entry.S"], check=True)
    subprocess.run(["gcc", *GCC_FLAGS, "-I", HERE.parent / "common", "-c", HERE / "trades.c", "-o", logic], check=True)
    with logic.open("rb") as stream:
        elf = ELFFile(stream)
        for name in (".data", ".bss"):
            section = elf.get_section_by_name(name)
            if section is not None and section.data_size:
                raise ValueError(f"trades.c must keep no writable data in the pages ({name})")
    subprocess.run(["ld", "-r", "-m", "elf_i386", "-T", script, "-o", obj, entry, logic], check=True)
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
            raise ValueError(f"code or data outside the pages' .text: {stray}")
        data = text.data()
        syms = elf.get_section_by_name(".symtab")
        end = next(s["st_value"] for s in syms.iter_symbols() if s.name == "cpu_trades_end")
        if end > CODE_LIMIT or len(data) != end:
            raise ValueError(f"the CPU trades code ({end:#x} bytes) does not fit below the settings record ({CODE_LIMIT:#x})")
        body[:end] = data
        for symbol in syms.iter_symbols():
            if symbol.name and symbol["st_shndx"] == index and symbol["st_info"]["type"] in ("STT_FUNC", "STT_NOTYPE"):
                labels[symbol.name] = symbol["st_value"]
        rel = elf.get_section_by_name(".rel.text")
        for fixup in rel.iter_relocations() if rel else ():
            field = fixup["r_offset"]
            if field + 4 > end:
                raise ValueError(f"relocation outside the code at {field:#x}")
            symbol = syms.get_symbol(fixup["r_info_sym"])
            section, value = symbol["st_shndx"], symbol["st_value"]
            addend = struct.unpack_from("<i", data, field)[0] + value
            if section == index:
                family = "page"
            elif section == "SHN_UNDEF" and symbol.name in PAGE:
                family, addend = "page", addend + PAGE[symbol.name]
            elif section in ("SHN_UNDEF", "SHN_ABS") and not symbol.name:
                family = "stock"
            else:
                raise ValueError(f"Unsupported relocation to {symbol.name or section}")
            kind = fixup["r_info_type"]
            if kind not in (1, 2):
                raise ValueError(f"Unsupported i386 relocation {kind}")
            relocations.append((field, kind == 2, family, addend & 0xFFFFFFFF))
    return body, end, sorted(relocations), {name: labels[name] for name in EXPORTED}


def render():
    with tempfile.TemporaryDirectory(prefix="2k5-cpu-trades-") as folder:
        raw, code_bytes, fixes, labels = collect(Path(folder))
    lines = [DIVIDER.rstrip(), f"CODE_BYTES = {code_bytes:#x}", f"COUNTER_NAMES = {counter_names()!r}", "",
             "_TEMPLATE = b''.join(("]
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
            raise SystemExit("The CPU trades native template is stale")
    else:
        TARGET.write_text(new, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
