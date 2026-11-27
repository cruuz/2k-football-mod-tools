"""DESIGN: build the team-building runtime (tools/team_building/runtime.c, with the shared team-need header) into the
proven-unreferenced retail windows of tools/team_building/dead_code.py, with GNU i386 tools.

Each function is its own input section; the sections are packed first-fit decreasing (by size, ties by name) into the
windows in descending size order (ties by address), so a window holds whole functions only. Every window of the list
is claimed: unused bytes are 0xCC. Rejects a section that fits nowhere and unresolved symbols. No retail code is
emitted; the generated module holds only this lane's code. Usage: assemble.py [--check]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.team_building.dead_code import WINDOWS  # noqa: E402

TARGET = ROOT / "mod_editor/core/nfl2k5_team_building_code.py"
NATIVE = {"n_rating": 0x246D80, "n_human": 0x13EC30, "n_team": 0xC4C50, "n_teams": 0xC4BE0,
          "n_at_position": 0xC3CB0, "n_minimum_at": 0x2BD410, "n_maximum_at": 0x2BD400, "n_game_rand": 0x48BC0,
          "n_need": 0x31DEA0, "n_fa_day": 0x324600}
ENTRIES = ("tb_order", "tb_wish_entry")
# b81 #45 (sim speed): the pace page (tools/team_building/pace.c), a fixed page of the scale-out pool
# (nfl2k5_xbe_space.TEAM_BUILDING_PACE_VA); its first words and jump table sit at fixed offsets that the 0x24849A site and
# the economy's rank_any name (pace.c's header comment).
PAGE_VA, PAGE_SIZE = 0x1535000, 0x1000
PAGE_LAYOUT = {"pace_day": 0x00, "pace_head": 0x00}
PAGE_JUMPS = {0x10: "pace_day_entry", 0x18: "pace_rank_twice", 0x20: "pace_rate", 0x28: "pace_lists"}
CFLAGS = ["-m32", "-Os", "-ffreestanding", "-fno-builtin", "-fno-pic", "-fno-pie", "-fno-stack-protector",
          "-fno-asynchronous-unwind-tables", "-fno-unwind-tables", "-fno-jump-tables", "-mpreferred-stack-boundary=2",
          "-mno-sse", "-mno-mmx", "-Wall", "-Wextra", "-Werror"]


def inputs() -> dict:
    """Tables the runtime copies: the economy's aging line and the draft AI's positional value (x 100)."""
    from mod_editor.core import nfl2k5_draft_ai as draft
    from mod_editor.core import nfl2k5_franchise_economy_code as economy
    data = json.loads((ROOT / "data/nfl2k5_franchise_economy.json").read_text())
    decline = data["model"]["decline_after_years_pro"]
    value = [round(draft.VALUE[p] * 100) for p in draft.POSITIONS]
    assert len(decline) == 17 and all(0 < v < 256 for v in decline + value)
    native = dict(NATIVE, economy_value=0x2BD440, economy_room_for_signing=economy.SYMBOLS["economy_room_for_signing"],
                  price_group=economy.SYMBOLS["price_group"])   # b81 #45: the pace page counts by the economy's groups
    assert native["economy_room_for_signing"] == 0x2D82F0          # the economy's pinned entry (revision 9)
    groups = data["revision_10"]["price"]["position_group"]
    assert len(groups) == 17 and max(groups) < 15 == len(data["revision_10"]["price"]["groups"]), \
        "pace.c lists 15 price groups (4 bits each)"
    return {"decline": decline, "value": value, "native": native}


def pack(sizes: dict, aligns: dict) -> dict:
    """{window start: [section, ...]} first-fit decreasing; raises when a section fits nowhere."""
    order = sorted(WINDOWS, key=lambda va: (-WINDOWS[va][0], va))
    fill = {va: 0 for va in order}
    place: dict[int, list[str]] = {}
    for name in sorted(sizes, key=lambda n: (-sizes[n], n)):
        a = aligns[name]
        for va in order:
            at = -(-fill[va] // a) * a
            if at + sizes[name] <= WINDOWS[va][0] and (va + at) % a == 0:
                place.setdefault(va, []).append(name)
                fill[va] = at + sizes[name]
                break
        else:
            raise ValueError(f"{name} ({sizes[name]} bytes) fits in no window")
    return place


def build(source: str | None = None) -> tuple[dict, dict, dict, dict]:
    """(window blobs, placement, symbols, inputs) for runtime.c, or for `source` (runtime.c's text with a change: the
    tests' guard mutations; its header include resolves as runtime.c's does)."""
    info = inputs()
    with tempfile.TemporaryDirectory(prefix="tb-assemble-") as tmp:
        d = Path(tmp)
        obj, elf, pace = d / "runtime.o", d / "runtime.elf", d / "pace.o"
        src = ROOT / "tools/team_building/runtime.c"
        if source is not None:
            src = d / "runtime.c"
            src.write_text(source)
        subprocess.run(["gcc", *CFLAGS, "-iquote", str(ROOT / "tools/team_building"),
                        f"-DTB_DECLINE_AFTER={{{','.join(map(str, info['decline']))}}}",
                        f"-DTB_VALUE={{{','.join(map(str, info['value']))}}}", "-c",
                        str(src), "-o", str(obj)], check=True)
        # b81 #45: the pace page, its own translation unit (only .pace_head and .pace sections)
        # its day entry's frame is ~21 KB: probed a page at a time, top down, as the game's own large frames are (its
        # MSVC code calls _chkstk 0x373630), so a stack with a guard page is grown in order
        subprocess.run(["gcc", *CFLAGS, "-fstack-clash-protection", "-c", str(ROOT / "tools/team_building/pace.c"), "-o",
                        str(pace)], check=True)
        for line in subprocess.check_output(["objdump", "-h", str(pace)], text=True).splitlines():
            parts = line.split()
            if len(parts) > 2 and parts[0].isdigit() and int(parts[2], 16) and parts[1] not in (".pace_head", ".pace") \
                    and parts[1] != ".comment" and not parts[1].startswith(".note"):
                raise ValueError(f"pace.c: unexpected section {parts[1]}")
        headers = subprocess.check_output(["objdump", "-h", str(obj)], text=True)
        sizes, aligns = {}, {}
        for m in re.finditer(r"^\s*\d+\s+(\S+)\s+([0-9a-f]+)\s+[0-9a-f]+\s+[0-9a-f]+\s+[0-9a-f]+\s+2\*\*(\d+)", headers,
                             re.M):
            name, size, align = m.group(1), int(m.group(2), 16), 1 << int(m.group(3))
            if size and (name.startswith(".tb_") or name.startswith(".rodata") or name == ".text"):
                sizes[name], aligns[name] = size, align
            elif size and name not in (".comment",) and not name.startswith(".note"):
                raise ValueError(f"unexpected section {name} ({size} bytes)")
        place = pack(sizes, aligns)
        script = "SECTIONS {\n" + "".join(
            f".w{va:x} {va:#x} : {{ {' '.join('*(' + n + ')' for n in place[va])} }}\n" for va in sorted(place))
        script += f".pace {PAGE_VA:#x} : {{ *pace.o(.pace_head) *pace.o(.pace) }}\n"
        script += "/DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) } }\n"
        script += "".join(f"{name} = {address:#x};\n" for name, address in info["native"].items())
        (d / "link.ld").write_text(script)
        subprocess.run(["ld", "-m", "elf_i386", "-T", str(d / "link.ld"), "-o", str(elf), str(obj), str(pace)],
                       check=True)
        names = {}
        for line in subprocess.check_output(["nm", "-n", str(elf)], text=True).splitlines():
            if len(line.split()) == 3:
                names[line.split()[2].split("@")[1] if line.split()[2].startswith("@") else line.split()[2]] = \
                    int(line.split()[0], 16)
        symbols = {k: v for k, v in names.items() if k.startswith("tb_") or k.startswith("pace_")}
        for name in ENTRIES:
            if name not in symbols:
                raise ValueError(f"{name} is missing")
        for name, offset in PAGE_LAYOUT.items():
            if symbols.get(name) != PAGE_VA + offset:
                raise ValueError(f"{name} must sit at {PAGE_VA + offset:#x}")
        out = d / "pace.bin"
        subprocess.run(["objcopy", "-O", "binary", "--only-section=.pace", str(elf), str(out)], check=True)
        page = out.read_bytes()
        if len(page) > PAGE_SIZE:
            raise ValueError(f"pace page: {len(page)} bytes, capacity {PAGE_SIZE}")
        for offset, name in PAGE_JUMPS.items():
            if page[offset] != 0xE9 or PAGE_VA + offset + 5 + struct.unpack_from("<i", page, offset + 1)[0] != symbols[name]:
                raise ValueError(f"the page's jump at +{offset:#x} does not reach {name}")
        blobs = {}
        for va in sorted(WINDOWS):
            if va not in place:
                blobs[va] = b""
                continue
            out = d / f"w{va:x}.bin"
            subprocess.run(["objcopy", "-O", "binary", f"--only-section=.w{va:x}", str(elf), str(out)], check=True)
            code = out.read_bytes()
            if len(code) > WINDOWS[va][0]:
                raise ValueError(f"window {va:#x}: {len(code)} bytes, capacity {WINDOWS[va][0]}")
            blobs[va] = code
    blobs[PAGE_VA] = page
    return blobs, place, symbols, info


def generate() -> str:
    blobs, place, symbols, info = build()
    lines = ['"""DESIGN: generated original code; reproduce with tools/team_building/assemble.py."""', "",
             "WINDOWS = {"]
    page = blobs.pop(PAGE_VA)
    for va, code in blobs.items():
        size = WINDOWS[va][0]
        names = " ".join(place.get(va, [])) or "unused"
        lines += [f"    {va:#x}: (  # {names}: {len(code)}/{size} bytes", "        bytes.fromhex("]
        lines += ['            "' + code[i:i + 40].hex() + '"' for i in range(0, len(code), 40)] or ['            ""']
        lines += [f'        ).ljust({size}, b"\\xcc")', "    ),"]
    lines += ["}", "RETAIL_SHA256 = {" + ", ".join(f"{va:#x}: {WINDOWS[va][1]!r}" for va in sorted(WINDOWS)) + "}",
              "SYMBOLS = " + repr(dict(sorted(symbols.items()))),
              f"PAGE_VA = {PAGE_VA:#x}", "PAGE = bytes.fromhex("]
    lines += ['    "' + page[i:i + 40].hex() + '"' for i in range(0, len(page), 40)]
    lines += [f').ljust({PAGE_SIZE:#x}, b"\\xcc")',
              "INPUTS = " + repr({"decline_after": info["decline"], "value_x100": info["value"]}), ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    result = generate()
    if args.check:
        if TARGET.read_text() != result:
            raise SystemExit("team-building code template is stale")
    else:
        TARGET.write_text(result)
    print("PROVED OFFLINE: team-building template reproduced")


if __name__ == "__main__":
    main()
