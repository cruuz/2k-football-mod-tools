#!/usr/bin/env python3
"""b77 / a4: how often does the CPU's real offensive commit (0x20B670) call a shotgun or pistol set, by situation?

The game's own selector runs under Unicorn on a given executable and a given composed PLAY book (the harness of p48o's
call-mix check, reduced to the offensive formation draw). With ``--row N`` the Anniversary state a moment leaves in memory
is set first (game mode word 0xE5FF80 = 8, selected physical row 0xBF1858 = N - 1), so the executable's era weight for
that moment is what the formation weight returns; without ``--row`` it is the ordinary game.

    python3 tools/b77/a4_callmix.py --xbe default.xbe --book DEN.play --row 39 --samples 100 --out mix.json

Nothing here is a gameplay result. Fixture (as p48o's): kicker range 50 yd, no tendency history, urgency 0, 120 s needed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_play_scoring as s            # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as ip      # noqa: E402
from pb.scoring_selectors import World                           # noqa: E402

SITUATIONS = {
    "1st&10 own25": dict(down=1, distance=10, yard=25),
    "1st&10 own20": dict(down=1, distance=10, yard=20),
    "1st&10 opp40": dict(down=1, distance=10, yard=60),
    "2nd&8 mid": dict(down=2, distance=8, yard=50),
    "2nd&7 own35": dict(down=2, distance=7, yard=35),
    "3rd&3 own25": dict(down=3, distance=3, yard=25),
    "3rd&8 mid": dict(down=3, distance=8, yard=50),
    "1st&G opp3": dict(down=1, distance=3, yard=97),
    # franchise bins (yard 50: beyond the 10 yard line, where the rule acts)
    "1st&10 mid": dict(down=1, distance=10, yard=50),
    "2nd&2 mid": dict(down=2, distance=2, yard=50), "2nd&5 mid": dict(down=2, distance=5, yard=50), "2nd&10 mid": dict(down=2, distance=10, yard=50),
    "3rd&2 mid": dict(down=3, distance=2, yard=50), "3rd&5 mid": dict(down=3, distance=5, yard=50), "3rd&10 mid": dict(down=3, distance=10, yard=50),
    # the seven bins of the per-bin weights, at the selector's representative distances (a4_eras.TEAM_BINS)
    "2nd&6 mid": dict(down=2, distance=6, yard=50), "2nd&11 mid": dict(down=2, distance=11, yard=50),
}
MODE_WORD, ROW_WORD = 0xE5FF80, 0xBF1858


class Mix(World):
    def sample(self, seed: int):
        rng = random.Random(seed)
        self.put(0xE5FCA0, 54)
        self.put(0xE5FCA4, 23)
        for index in range(110):
            self.put(0xE5FCA8 + 4 * index, rng.getrandbits(32))
        self.fput(0xBF1244, rng.random())
        self.fput(0xBF1484, rng.random())
        for a in (0xBF16FC, 0xBF1700):
            self.put(a, 0)
        out = s.SOURCE + 0x19100
        self.m.mem_write(out, bytes(16))
        self.call(0x20B670, ecx=s.TEAM, edx=out)
        return struct.unpack("<4I", self.m.mem_read(out, 16))


def run(xbe: bytes, book_raw: bytes, situations: dict, samples: int, row: int | None, team: str | None = None, category: int = 0) -> dict:
    """``team`` names a separate roster record linked from the live team's +0x1c.
    The roster record, not the live team, owns the key at +0x110 and category at +0x128."""
    m = Mix(xbe)
    m.load(book_raw)
    if team is not None:
        base = s.SOURCE + 0x1F000
        m.m.mem_write(base, bytes(0x200))
        m.m.mem_write(base + 0x100, (team + "\0").encode("utf-16le"))
        m.put(base + 4, base + 0x100)                       # key object: +4 -> the key string
        roster = base + 0x200
        m.put(s.TEAM + 0x1C, roster)
        m.put(roster + 0x110, base)
        m.put(roster + 0x128, category)
    special = {}
    rec = m.get(s.TEAM + 0xC)
    m.m.mem_write(rec + 0x2C, bytes(0x30))
    m.call(0x204C80, eax=s.TEAM)                  # the per-team play-call record the game builds after the books load
    book = m.book
    body = book_raw[32:]
    flags = {f.index: struct.unpack_from("<I", body, ip.FORMATION_BASE + f.index * ip.FORMATION_SIZE + 4)[0] for f in book.formations}
    out = {}
    for name, sit in situations.items():
        m.configure(**sit)
        run_share = 0.5
        m.fput(0xBF16F8, run_share)
        m.put(MODE_WORD, 8 if row is not None else 0)
        m.put(ROW_WORD, (row - 1) if row is not None else 0)
        forms, faults = Counter(), 0
        for seed in range(samples):
            m.configure(**sit)
            m.fput(0xBF16F8, run_share)
            m.put(MODE_WORD, 8 if row is not None else 0)
            m.put(ROW_WORD, (row - 1) if row is not None else 0)
            try:
                _cv, fv, _pv, _ = m.sample(1000003 * seed + 17)
            except s.ScoringError:
                faults += 1
                continue
            n, rem = divmod(fv - s.BOOK - ip.FORMATION_BASE, ip.FORMATION_SIZE)
            forms[n if rem == 0 and 0 <= n < len(book.formations) else -1] += 1
        total = sum(forms.values())
        gun = sum(c for n, c in forms.items() if n >= 0 and flags[n] & 0xC0000 == 0x80000 and ((flags[n] >> 8) & 0x3F) < 4)
        out[name] = dict(samples=total, faults=faults, gun_pct=round(100.0 * gun / total, 1) if total else None,
                         top=[(book.formations[n].name.strip() if n >= 0 else "?", c) for n, c in forms.most_common(5)])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xbe", type=Path, required=True)
    ap.add_argument("--book", type=Path, required=True)
    ap.add_argument("--row", type=int, help="physical Anniversary row 1..51 (omit for the ordinary game)")
    ap.add_argument("--team", help="franchise key (exhibition, season or franchise game: omit --row)")
    ap.add_argument("--samples", type=int, default=100)
    ap.add_argument("--situation", action="append", choices=sorted(SITUATIONS))
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    chosen = {k: SITUATIONS[k] for k in (args.situation or SITUATIONS)}
    result = run(args.xbe.read_bytes(), args.book.read_bytes(), chosen, args.samples, args.row, args.team)
    for name, r in result.items():
        print(f"{name:14s} gun {r['gun_pct']}%  n={r['samples']} faults={r['faults']}  {r['top'][:3]}", flush=True)
    if args.out:
        args.out.write_text(json.dumps(dict(xbe=str(args.xbe), book=str(args.book), row=args.row, team=args.team, samples=args.samples, results=result), indent=1),
                            encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
