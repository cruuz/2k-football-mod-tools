#!/usr/bin/env python3
"""b77 / a4pd: does the installed stub return the right per-bin weight? The game's own formation weight (0x207EF0) runs under
Unicorn for a shotgun set on a staged team with the franchise key stored the way the game stores it, for every down 1..4 and yards
to go from 1 to 25 (and the half-yard cut points), and its result is compared with the weight table the executable carries.

    python3 tools/b77/a4_bins_probe.py --xbe default.xbe --book KC.play --team KC [--before default_before.xbe]

With ``--before`` an executable without the stub also runs, and every case inside the 10 yard line must equal it exactly.
Nothing here is a gameplay result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_moment_gun_weight as gw            # noqa: E402
from mod_editor.core import nfl2k5_play_scoring as s                  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as ip            # noqa: E402
from mod_editor.core import nfl2k5_stock_books as sb                   # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage               # noqa: E402
from tools.b77.a4_callmix import Mix                                   # noqa: E402

CODE, OUT = s.SOURCE + 0x1E000, s.SOURCE + 0x1E100


def expected_bin(down: int, togo: float):
    """The stub's bin index for a down and yards to go, or None when it must give the retail constant."""
    if down == 1:
        return 0
    if down == 2:
        return 1 if togo <= 3.5 else 2 if togo <= 7.5 else 3
    if down in (3, 4):
        return 4 if togo <= 3.5 else 5 if togo <= 6.5 else 6
    return None


class Probe:
    def __init__(self, xbe: bytes, book_raw: bytes, key: str, category: int = 0):
        self.m = Mix(xbe)
        self.m.load(book_raw)
        base = s.SOURCE + 0x1F000
        self.m.m.mem_write(base, bytes(0x200))
        self.m.m.mem_write(base + 0x100, (key + "\0").encode("utf-16le"))
        self.m.put(base + 4, base + 0x100)
        roster = base + 0x200
        self.m.put(s.TEAM + 0x1C, roster)
        self.m.put(roster + 0x110, base)
        self.m.put(roster + 0x128, category)
        body = book_raw[32:]
        # the first shotgun set of the book (type 0..3, gun flag), as the lottery would present it
        self.gun = next(f.index for f in self.m.book.formations
                        if (struct.unpack_from("<I", body, ip.FORMATION_BASE + f.index * ip.FORMATION_SIZE + 4)[0] & 0xC0000) == 0x80000
                        and ((struct.unpack_from("<I", body, ip.FORMATION_BASE + f.index * ip.FORMATION_SIZE + 4)[0] >> 8) & 0x3F) < 4)

    def weight(self, down: int, togo: float, yard: float = 50, mode: int = 0, row: int = 0) -> float:
        m = self.m
        m.configure(down=down, distance=togo, yard=yard)
        m.put(0xE5FF80, mode)
        m.put(0xBF1858, row)
        formation = s.BOOK + ip.FORMATION_BASE + self.gun * ip.FORMATION_SIZE
        code = (b"\x68" + struct.pack("<I", s.SOURCE + 0x1E200) + b"\x68" + struct.pack("<I", s.TEAM)       # push arg2 / push arg1 (the team)
                + b"\xbf" + struct.pack("<I", formation) + b"\xb8\x01\x00\x00\x00"                         # mov edi, formation / mov eax, 1
                + b"\xe8" + struct.pack("<i", 0x207EF0 - (CODE + 22 + 5)) + b"\xd9\x1d" + struct.pack("<I", OUT) + b"\xc3")
        m.m.mem_write(CODE, code)
        m.m.mem_write(s.SOURCE + 0x1E200, bytes(0x100))
        m.m.ctl_remove_cache(CODE, CODE + 64)
        m.call(CODE)
        return struct.unpack("<f", m.m.mem_read(OUT, 4))[0]


def table_row(xbe: bytes, key: str) -> list[float]:
    image = XbeImage(xbe)
    owned = sb.allocation(xbe)
    rows = gw.decode_bin_table(image.read(owned["va"] + sb.BIN_TABLE_OFFSET, gw.BIN_TABLE_SIZE))
    return rows[sb.key_order().index(key)]


def check(xbe: bytes, book: bytes, key: str, before: bytes | None = None) -> dict:
    """Run every case; ``mismatches`` must be empty (and ``inside_the_10_differences`` too when ``before`` is given)."""
    row = table_row(xbe, key)
    probe = Probe(xbe, book, key)
    togos = [float(d) for d in range(1, 26)] + [3.4, 3.6, 6.4, 6.6, 7.4, 7.6]
    bad, cases = [], 0
    for down in (1, 2, 3, 4):
        for togo in togos:
            got = probe.weight(down, togo)
            want = row[expected_bin(down, togo)]
            cases += 1
            if abs(got - want) > 1e-4 * max(1.0, want):
                bad.append(dict(down=down, togo=togo, got=got, want=want))
    odd = [probe.weight(d, 5.0) for d in (0, 5, 9)]
    if any(abs(v - 0.05) > 1e-6 for v in odd):
        bad.append(dict(kind="down outside 1..4 must be retail", got=odd))
    moments = gw.weights()
    for r in (0, 38, 50):                                           # Anniversary mode: the moment's weight at every down and distance
        for down, togo in ((1, 10.0), (2, 2.0), (3, 5.0), (4, 12.0)):
            got = probe.weight(down, togo, mode=8, row=r)
            cases += 1
            if abs(got - moments[r]) > 1e-4:
                bad.append(dict(kind="moment", row=r + 1, down=down, togo=togo, got=got, want=moments[r]))
    for label, other in (("historic side (category 4)", Probe(xbe, book, key, category=4)), ("unknown franchise key", Probe(xbe, book, "ZZZ"))):
        for down in (1, 2, 3, 4):
            for togo in (2.0, 5.0, 10.0):
                got = other.weight(down, togo)
                cases += 1
                if abs(got - 0.05) > 1e-6:
                    bad.append(dict(kind=label + " must be retail", down=down, togo=togo, got=got))
    result = dict(team=key, row=row, cases=cases, mismatches=bad)
    if before is not None:
        ref = Probe(before, book, key)
        near = [(d, t, y) for d in (1, 2, 3, 4) for t in (1.0, 5.0, 10.0) for y in (92, 95, 99)]
        diff = [dict(down=d, togo=t, yard=y, got=probe.weight(d, t, y), before=ref.weight(d, t, y)) for d, t, y in near]
        result["inside_the_10_cases"] = len(near)
        result["inside_the_10_differences"] = [r for r in diff if r["got"] != r["before"]]
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xbe", type=Path, required=True)
    ap.add_argument("--book", type=Path, required=True)
    ap.add_argument("--team", required=True)
    ap.add_argument("--before", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    result = check(args.xbe.read_bytes(), args.book.read_bytes(), args.team, args.before.read_bytes() if args.before else None)
    print(json.dumps(result, indent=1))
    if args.out:
        args.out.write_text(json.dumps(result, indent=1), encoding="utf-8", newline="\n")
    return 1 if result["mismatches"] or result.get("inside_the_10_differences") else 0


if __name__ == "__main__":
    raise SystemExit(main())
