"""Compile the authored 32-bit scheduled quarterback rules. Development requires GNU as/ld, gcc and pyelftools.
No game input is needed. The Studio links the checked-in template against four verified routines on the user's disc.
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
TARGET = HERE.parents[1] / "mod_editor/core/nfl2k5_sim_qb_injuries_code.py"
DIVIDER = "# Generated from tools/qb_sim_injuries by build.py.\n"
PIECES = (
    ("clinical", 0), ("positions", 0x1400), ("stability", 0x1C00), ("recovery", 0x2000), ("fixture_start", 0x3100),
    ("clinical_return", 0x3200), ("contest", 0x3300), ("redzone", 0x3500),
    ("context", 0x3600), ("completed_entry", 0x3840), ("duration", 0x3900),
    ("passing", 0x3A00), ("completed_pass", 0x3D00),
)
GCC_FLAGS = "-m32 -march=i386 -Os -fomit-frame-pointer -fno-builtin -fno-stack-protector -ffreestanding -fno-pic -fno-pie -fno-asynchronous-unwind-tables -Wall -Wextra -Werror".split()

# Expressions that refer to another authored object. Intra-object references come from the ELF symbol table.
LOCAL = {
    "qb_capture_flags": "clinical_return.clinical_return", "qb_duration_adjust": "duration.revise",
    "CACHED_YEAR": "clinical.season_year", "CACHED_WEEK": "clinical.season_week",
    "CACHED_HOME": "clinical.club_a", "CACHED_AWAY": "clinical.club_b",
    "CACHED_CLUB_A": "clinical.club_a", "CACHED_CLUB_B": "clinical.club_b",
    "MATCH_INITIALIZER": "recovery.match_hook", "CONTINUE_CAPTURE": "clinical.continue_capture",
    "WEEKLY_ENTRY": "recovery.match_hook", "PREPARE": "recovery.prepare",
    "RESTORE": "recovery.restore_match", "UNDO": "recovery.undo_count", "MEDICAL_ENTRY": "clinical.supplement",
    "CONTEST_ENTRY": "contest.fit", "REDZONE_ENTRY": "redzone.adjust", "GAIN_ENTRY": "passing.passing_scale",
    "FIXTURE_ACTIVE": "context.active", "COMPLETED_PASS": "completed_pass.completed_catch_scale",
    "REDZONE_GAIN": "redzone.adjust", "COMPLETED_GAIN": "passing.passing_scale",
    "POSITIONS": "positions.positions", "POS_CACHED_YEAR": "positions.pos_year", "QB_PRIVATE_RNG": "clinical.private_rng",
    "STABILITY": "stability.stability", "STAB_FACTOR": "stability.stab_factor",
}
EXTERNAL = {
    "qb_depth_helper": ("depth", 0), "RATING_TABLE": ("bank", 0x3B00),
    "RZ_ADDR": ("bank", 0x3D80), "BASE_MULTIPLIER": ("bank", 0x3D84),
    "STANDARD_PASS": ("pass_converter", 0), "RZ_LINE": ("red_zone_line", 0), "RETURN_SLOT": ("sim_data", 12),
    "SLOPE_ADDR": ("mix_slope", 0), "BIAS_ADDR": ("mix_bias", 0),
}
STOCK = {
    "GAMECAST_BIND_RESOURCES": 0x6C780, "GAMECAST_RETURN": 0xEC00C,
    "WEEKLY_OR_PAUSE_RETURN": 0x10B95F, "WEEKLY_INNER_RETURN": 0x10B9E0, "WEEKLY_OUTER_RETURN": 0xC7B58,
    "LEAGUE_KIND": 0xE576A0, "GAME_KIND": 0xE5FF80, "LEAGUE_STAGE": 0xE576A4,
    "ROSTER_ROOT": 0xB72918, "LEAGUE_YEAR": 0xE576B8, "LEAGUE_WEEK": 0xE576B4,
    "NATIVE_INIT": 0x10B280, "NATIVE_MEDICAL": 0x1028B0, "DEFENSE_SIDE": 0xA971A0,
    "YARD_CONVERT": 0x106480, "SPOT": 0xA97200,
}
FLOATS = {"PHYS_REDZONE": .64, "PHYS_GAIN": .91, "PHYS_SLOPE": .4, "PHYS_BIAS": 8.5}
EXPORTED = {
    "clinical": ("supplement", "before_primary", "continue_capture", "finished", "descriptor", "duration",
                 "group", "weeks", "private_rng", "ordinary_thresholds", "special_thresholds", "length_thresholds"),
    "context": ("match_entry", "gamecast_screen_entry", "medical", "contest", "slope", "bias", "flat", "active"),
    "recovery": ("depth_hook", "match_hook"), "duration": ("revise",),
    "redzone": ("adjust",), "passing": ("passing_scale",),
    "completed_entry": ("route_completed_pass",), "completed_pass": ("completed_catch_scale",),
    "positions": ("positions", "pos_sampled", "pos_descriptor", "pos_duration", "pos_duration_accept", "pos_enabled",
                  "pos_scale", "pos_zero", "pos_accept", "pos_slots", "pos_year", "pos_week", "pos_club_a", "pos_club_b",
                  "pos_key", "pos_seq", "pos_hash", "pos_sample", "pos_wide", "pos_class", "victim_side",
                  "victim_slot", "accept_ptr", "pos_plays", "pos_hits", "pos_commits", "pos_effective",
                  "pos_week_group"),
    "stability": ("stability", "stab_factor", "stab_reference", "stab_year", "stab_zero", "stab_mode", "stab_class",
                  "stab_starters", "stab_sum", "stab_count"),
}


def compile_piece(label, temp):
    obj = temp / (label + ".o")
    if label != "recovery":
        subprocess.run(["as", "--32", "-o", obj, HERE / (label + ".S")], check=True)
        return obj
    entry = temp / "entry.o"
    logic = temp / "logic.o"
    script = temp / "recovery.ld"
    script.write_text("SECTIONS { .text 0 : { *(.text*) *(.rodata*) *(.data*) *(COMMON) *(.bss*) BYTE(0); } "
                      "/DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) *(.got*) } }")
    subprocess.run(["as", "--32", "-o", entry, HERE / "recovery_entry.S"], check=True)
    subprocess.run(["gcc", *GCC_FLAGS, "-c", HERE / "recovery.c", "-o", logic], check=True)
    subprocess.run(["ld", "-r", "-m", "elf_i386", "-T", script, "-o", obj, entry, logic], check=True)
    return obj


def collect(temp):
    body = bytearray(b"\xcc" * 0x4000)
    labels, relocations = {}, []
    end = 0
    for name, base in PIECES:
        with compile_piece(name, temp).open("rb") as stream:
            elf = ELFFile(stream)
            text = elf.get_section_by_name(".text")
            index = elf.get_section_index(".text")
            data = text.data()
            if end > base or base + len(data) > len(body):
                raise ValueError(f"{name} does not fit its reserved interval")
            body[base:base + len(data)] = data
            end = base + len(data)
            syms = elf.get_section_by_name(".symtab")
            for symbol in syms.iter_symbols():
                if symbol.name and symbol["st_shndx"] == index:
                    labels[f"{name}.{symbol.name}"] = base + symbol["st_value"]
            for fixup in elf.get_section_by_name(".rel.text").iter_relocations():
                field = fixup["r_offset"]
                symbol = syms.get_symbol(fixup["r_info_sym"])
                section, value = symbol["st_shndx"], symbol["st_value"]
                addend = struct.unpack_from("<i", data, field)[0] + value
                if section == index:
                    target = ("bank", base)
                elif section in ("SHN_UNDEF", "SHN_ABS"):
                    target = symbol.name or ("stock", 0)
                else:
                    raise ValueError(f"Unsupported {name} relocation to {section}")
                kind = fixup["r_info_type"]
                if kind not in (1, 2):
                    raise ValueError(f"Unsupported i386 relocation {kind}")
                relocations.append((base + field, kind == 2, target, addend))
    targets = dict(EXTERNAL)
    targets.update((name, ("bank", labels[symbol])) for name, symbol in LOCAL.items())
    targets.update((name, ("stock", va)) for name, va in STOCK.items())
    targets.update((name, ("literal", int.from_bytes(struct.pack("<f", value), "little"))) for name, value in FLOATS.items())
    resolved = []
    for field, relative, target, addend in relocations:
        family, value = targets[target] if isinstance(target, str) else target
        resolved.append((field, relative, family, value + addend))
    exported = {key: labels[f"{part}.{key}"] for part, keys in EXPORTED.items() for key in keys}
    return body, sorted(resolved), exported


def render():
    with tempfile.TemporaryDirectory(prefix="2k5-quarterbacks-") as folder:
        raw, fixes, labels = collect(Path(folder))
    lines = [DIVIDER.rstrip(), "_TEMPLATE = b''.join(("]
    pos = 0

    def literal(chunk):
        for start in range(0, len(chunk), 40):
            lines.append(f"    bytes.fromhex('{chunk[start:start + 40].hex()}'),")

    for match in re.finditer(rb"\x00{12,}|\xcc{12,}", bytes(raw)):
        literal(raw[pos:match.start()])
        byte = raw[match.start()]
        fill = "bytes" if byte == 0 else "b'\\xcc' * "
        length = match.end() - match.start()
        lines.append(f"    {fill}({length})," if byte == 0 else f"    {fill}{length},")
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
            raise SystemExit("The scheduled quarterback native template is stale")
    else:
        TARGET.write_text(new, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
