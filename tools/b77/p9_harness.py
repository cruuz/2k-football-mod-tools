#!/usr/bin/env python3
"""b77 p9 native harness: the real selector code of default.xbe over a grid of game states, before and after Modern 2.

Runs under Unicorn the game's own routines on the real executables and a real PLAY book (nothing in the decision path is
stubbed except the kicker's roster-derived range 0x18B120, supplied in yards, exactly as pb/scoring_selectors.py does):

* ``fourth``   the fourth-down dispatcher 0x20B180 (go = ordinary category 0..10, punt = 0x11, field goal = 0x13) and, for the
               fake check, the offensive commit 0x20B670, whose call of 0x2096A0 carries the fake flag (third argument);
* ``two``      the try decision 0x20B2E0 phase 3 (0x208470 -> chart 0x206E70): category 0x13 = kick, 0..10 = two-point play;
* ``defense``  the defense's category (0x20B820 / 0x20B400) against a not-yet-committed 4th-down offense (punt-return set or not);
* ``mix``      the call mix: formation / play / front / coverage choices of 0x20B670 and 0x20B820 over a situation list.

Usage (all paths are arguments; one process, light CPU):

    nice -n 19 ionice -c3 python3 tools/b77/p9_harness.py --retail RETAIL.xbe --before V05.xbe --after P9.xbe \
        --book BOOK.play --out OUT.json [--sections fourth,two,defense,mix] [--samples N]

Nothing here is a played game: the fixture fixes kicker range, time needed (120 s), urgency (0) and the tendency tables (zero).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_cpu_money_downs as md  # noqa: E402
from mod_editor.core import nfl2k5_play_scoring as s  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as ip  # noqa: E402
from pb.scoring_selectors import World  # noqa: E402

KIND = {0x11: "punt", 0x13: "fg"}


def kind(category: int) -> str:
    return KIND.get(category, "go" if category <= 10 else f"other{category}")


class Fixture(World):
    """pb.scoring_selectors.World plus a settable kicker range, record initializer and fake-flag capture."""

    def __init__(self, payload: bytes, range_yards: float = 38.0):
        super().__init__(payload)
        self.range_yards = range_yards

        def fg(u, a, n, d):
            self.environment_calls["0x18b120"] += 1
            self.fput(s.STOP + 0x80, self.range_yards * 91.44)
            u.mem_write(s.STOP + 0x90, b"\xd9\x05" + struct.pack("<I", s.STOP + 0x80) + b"\xc3")
            u.reg_write(self.r.UC_X86_REG_EIP, s.STOP + 0x90)

        self.m.hook_add(self.ucmod.UC_HOOK_CODE, fg, begin=0x18B120, end=0x18B120)
        self.fake: list[int] = []

        def commit(u, a, n, d):
            sp = u.reg_read(self.r.UC_X86_REG_ESP)
            self.fake.append(self.get(sp + 12))

        self.m.hook_add(self.ucmod.UC_HOOK_CODE, commit, begin=0x2096A0, end=0x2096A0)

    def load_book(self, raw: bytes) -> None:
        self.load(raw)
        for team in (s.TEAM, self.defense):
            rec = self.get(team + 0xC)
            self.m.mem_write(rec + 0x2C, bytes(0x30))
            self.call(0x204C80, eax=team)   # the game's per-team play-call record initializer

    def state(self, *, down=4, distance=2, yard=50, margin=0, quarter=2, seconds=600, phase=4, quarter_seconds=900.0,
              ot_bits=0, mode=7):
        self.configure(down=down, distance=distance, yard=yard, margin=margin, quarter=quarter, seconds=seconds, phase=phase)
        self.fput(0xE602B0, quarter_seconds)
        self.put(0xE602A8, ot_bits)
        self.put(0xE5FF80, mode)   # franchise regular season (outside the Anniversary era profiles)

    def seed(self, draw: float, seed: int = 1) -> None:
        rng = random.Random(seed * 7919 + 1)
        self.put(0xE5FCA0, 54)
        self.put(0xE5FCA4, 23)
        for i in range(110):
            self.put(0xE5FCA8 + 4 * i, rng.getrandbits(32))
        self.fput(0xBF1244, draw)
        self.fput(0xBF1484, draw)
        for a in (0xBF16FC, 0xBF1700):
            self.put(a, 0)

    def dispatch(self, draw=0.5, seed=1) -> int:
        self.seed(draw, seed)
        return self.call(0x20B180, ecx=s.TEAM)

    def commit(self, draw=0.5, seed=1):
        """Offensive commit 0x20B670: (category id, fake flag of the last 0x2096A0 call or None)."""
        self.seed(draw, seed)
        self.fake.clear()
        out = s.SOURCE + 0x19100
        self.m.mem_write(out, bytes(16))
        self.call(0x20B670, ecx=s.TEAM, edx=out)
        cv, _fv, _pv, _ = struct.unpack("<4I", self.m.mem_read(out, 16))
        cat = (self.m.mem_read(cv + 4, 1)[0] & 0x3F) if cv else None
        return cat, (self.fake[-1] if self.fake else None)

    def defense_category(self, draw=0.5, seed=1):
        """Category id the CPU defense (0x20B820 -> 0x20B400) picks against an offense that has not committed yet: it predicts the
        offense's 4th-down call through 0x20B180 (so a go-for-it prediction means no punt-return or field-goal-block set)."""
        self.seed(draw, seed)
        out = s.SOURCE + 0x19200
        self.m.mem_write(out, bytes(16))
        self.call(0x20B820, ecx=self.defense, edx=out, args=(0,))
        cv = struct.unpack("<I", self.m.mem_read(out, 4))[0]
        return (self.m.mem_read(cv + 4, 1)[0] & 0x3F) if cv else None

    def try_category(self, draw=0.5, seed=1):
        self.seed(draw, seed)
        cat = self.call(0x20B2E0, ecx=s.TEAM, edi=0)
        return (self.m.mem_read(cat + 4, 1)[0] & 0x3F) if cat else None


def read_executable(path: str) -> bytes:
    return Path(path).read_bytes()


REGULATION_CONTEXTS = (  # (quarter, quarter clock, margin) with 15-minute quarters
    (1, 800, 0), (2, 700, 0), (2, 100, 0), (3, 500, 0), (3, 500, -10), (3, 500, 10), (4, 800, 0), (4, 800, -4),
    (4, 800, -10), (4, 800, 3), (4, 800, 10), (4, 500, -4), (4, 500, 4), (4, 250, -4), (4, 250, -10), (4, 250, 3),
    (4, 250, 8), (4, 100, -3), (4, 100, -4), (4, 100, -10), (4, 100, 0), (4, 100, 3), (4, 100, 8), (4, 25, -4), (4, 25, 2))
OWN_YARDS = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 99)
DISTANCES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20)
OT_MARGINS = (-8, -7, -3, -1, 0, 3)
OT_YARDS = (10, 25, 35, 45, 55, 65, 75, 85, 95)
OT_DISTANCES = (1, 2, 4, 8, 15)
# The fixture's offense is not the home team object, so it reads as the away team: bit 1 (value 2) is its own possession.
OT_BITS = {"no_tracking": 0, "first_possession": 2, "both_possessed": 3}


STATE_KEYS = ("down", "distance", "yard", "margin", "quarter", "seconds", "phase", "quarter_seconds", "ot_bits", "mode")


def native_inputs(fixture: "Fixture", cell: dict) -> dict:
    """The unmodified game's own answers the Modern 2 oracle takes as inputs: field goal test 20AF80 and Hail Mary test 206DD0."""
    fixture.state(**{k: v for k, v in cell.items() if k in STATE_KEYS})
    fixture.seed(0.5)
    fg = bool(fixture.call(0x20AF80))
    hail = bool(fixture.call(0x206DD0))
    return dict(native_fg=fg, hail_mary=hail)


def fourth_down(retail: bytes, before: bytes, after: bytes, book: bytes, range_yards: float, commit_every: int) -> dict:
    fixtures = {name: Fixture(raw, range_yards) for name, raw in (("retail", retail), ("before", before), ("after", after))}
    for f in fixtures.values():
        f.load_book(book)
    rows, fails = [], []
    stats = Counter()

    def classify(cell, want):
        res = {}
        for name, f in fixtures.items():
            f.state(**{k: v for k, v in cell.items() if k in STATE_KEYS})
            res[name] = {"draw0.5": kind(f.dispatch(0.5)), "draw0.97": kind(f.dispatch(0.97))}
        res["oracle"] = want
        rows.append(dict(cell, **res))
        stats["cells"] += 1
        after = res["after"]
        if want in ("go", "fg"):
            ok = after["draw0.5"] == want and after["draw0.97"] == want
        else:   # a retail decision: identical to the unmodified game on this state at both random draws
            ok = all(after[d] == res["retail"][d] for d in after)
        if not ok:
            fails.append(dict(cell, result=res, oracle=want))
        # commit check (fake flag): every forced kick, and a sample of everything else
        if want == "fg" or stats["cells"] % commit_every == 0:
            stats["commit_checks"] += 1
            cat, fake = fixtures["after"].commit(0.5, 1)
            if want == "fg":
                if cat != 0x13 or fake != 0:
                    fails.append(dict(cell, commit_category=cat, fake_flag=fake, error="forced field goal must commit as a real kick (category 0x13, fake flag 0)"))
            elif want == "go":
                if cat in (0x11, 0x13) and fake == 1 or (cat in (0x11, 0x13) and want == "go" and after["draw0.5"] == "go"):
                    # the commit may legitimately retry into a kick only through the native paths; a go decision never fakes
                    if fake == 1:
                        fails.append(dict(cell, commit_category=cat, fake_flag=fake, error="a go decision committed a fake kick"))
            else:
                rcat, rfake = fixtures["retail"].commit(0.5, 1)
                if (cat, fake) != (rcat, rfake):
                    fails.append(dict(cell, commit_after=(cat, fake), commit_retail=(rcat, rfake), error="retail decision changed at commit"))
        return res

    for q, secs, margin in REGULATION_CONTEXTS:
        for yard in OWN_YARDS:
            for dist in DISTANCES:
                if yard + dist > 100:
                    continue
                cell = dict(quarter=q, seconds=secs, margin=margin, yard=yard, distance=dist, down=4, quarter_seconds=900.0, ot_bits=0)
                want = md.decision(level="modern2", own_yard=yard, distance=dist, score_margin=margin, quarter=q, seconds=secs,
                                   quarter_seconds=900.0, home=False, kick_range=range_yards,
                                   **native_inputs(fixtures["retail"], cell))
                classify(cell, want)
    # overtime: period 5, regular-season period (the fixture offense is the away team: its own possession bit is 2)
    for bits_name, bits in OT_BITS.items():
        for margin in OT_MARGINS:
            for yard in OT_YARDS:
                for dist in OT_DISTANCES:
                    cell = dict(quarter=5, seconds=420, margin=margin, yard=yard, distance=dist, down=4, quarter_seconds=900.0,
                                ot_bits=bits, ot_state=bits_name)
                    want = md.decision(level="modern2", own_yard=yard, distance=dist, score_margin=margin, quarter=5, seconds=420,
                                       quarter_seconds=900.0, ot_bits=bits, home=False, kick_range=range_yards,
                                       **native_inputs(fixtures["retail"], cell))
                    res = classify(cell, want)
                    if bits_name == "both_possessed" and margin <= -4:
                        stats["ot_last_possession_cells"] += 1
                        for name in ("retail", "before"):
                            stats[f"ot_last_possession_{name}_kicks_or_punts"] += sum(res[name][d] != "go" for d in res[name])
                        if any(res["after"][d] != "go" for d in res["after"]):
                            fails.append(dict(cell, result=res, error="behind by 4+ on the last possession must always go"))
    early = []
    for bits_name, bits in (("first_possession", 2), ("both_possessed_tied", 3)):
        for down in (1, 2, 3):
            for yard in (80, 85, 90, 95):
                cell = dict(quarter=5, seconds=420, margin=0, yard=yard, distance=10 if down == 1 else 6, down=down,
                            quarter_seconds=900.0, ot_bits=bits)
                out = {}
                for name, fx in fixtures.items():
                    fx.state(**cell)
                    out[name] = kind(fx.dispatch(0.5))
                early.append(dict(bits=bits_name, down=down, yard=yard, **out))
                if bits_name == "first_possession" and out["after"] == "fg":
                    fails.append(dict(cell, result=out, error="first-possession early-down field goal not suppressed"))
                if bits_name != "first_possession" and out["after"] != out["retail"]:
                    fails.append(dict(cell, result=out, error="sudden death early-down logic changed"))
    summary = {name: dict(Counter(r[name]["draw0.5"] for r in rows)) for name in ("retail", "before", "after")}
    return dict(cells=stats["cells"], failures=len(fails), failure_examples=fails[:25], stats=dict(stats), summary_draw0_5=summary,
                early_down_overtime=early, rows=rows)


def two_point(retail: bytes, before: bytes, after: bytes, book: bytes) -> dict:
    fixtures = {name: Fixture(raw) for name, raw in (("retail", retail), ("before", before), ("after", after))}
    for f in fixtures.values():
        f.load_book(book)
    rows, fails = [], []
    for quarter, secs, bits in ((1, 800, 0), (2, 700, 0), (3, 500, 0), (4, 800, 0), (4, 500, 0), (4, 250, 0), (4, 100, 0),
                                (4, 25, 0), (5, 400, 0), (5, 400, 2), (5, 400, 3)):
        for margin in range(-16, 17):
            res = {}
            for name, f in fixtures.items():
                two = 0
                for seed in range(20):
                    f.state(down=1, distance=2, yard=98, margin=margin, quarter=quarter, seconds=secs, phase=3, quarter_seconds=900.0, ot_bits=bits)
                    cat = f.try_category(random.Random(seed * 104729 + 3).random(), seed)
                    two += 1 if (cat is not None and cat <= 10) else 0
                res[name] = two   # of 20 draws; the 5% fake draws keep this just under 20
            want = md.two_point_decision(margin=margin, quarter=quarter, seconds=secs, quarter_seconds=900.0, ot_bits=bits, home=False)
            rows.append(dict(quarter=quarter, seconds=secs, ot_bits=bits, margin=margin, oracle=want, **res))
            got = res["after"] >= 10
            if got != want:
                fails.append(dict(quarter=quarter, seconds=secs, ot_bits=bits, margin=margin, oracle=want, result=res))
    return dict(cells=len(rows), failures=len(fails), failure_examples=fails[:20], rows=rows)


DEFENSE_CELLS = (   # (label, state): the offense is the fixture's away team
    ("OT last possession, down 7, 4th and 2 at own 40", dict(quarter=5, seconds=400, margin=-7, yard=40, distance=2, ot_bits=3)),
    ("OT last possession, down 7, 4th and 8 at own 65", dict(quarter=5, seconds=400, margin=-7, yard=65, distance=8, ot_bits=3)),
    ("OT last possession, down 7, 4th and 4 at opponent 15", dict(quarter=5, seconds=400, margin=-7, yard=85, distance=4, ot_bits=3)),
    ("OT last possession, down 3, 4th and 8 at own 45", dict(quarter=5, seconds=400, margin=-3, yard=45, distance=8, ot_bits=3)),
    ("OT sudden death, tied, 4th and 8 at own 45 (unchanged)", dict(quarter=5, seconds=400, margin=0, yard=45, distance=8, ot_bits=3)),
    ("Q4 1:40 left, down 7, 4th and 12 at own 30", dict(quarter=4, seconds=100, margin=-7, yard=30, distance=12, ot_bits=0)),
    ("Q1, 4th and 3 at the opponent 45", dict(quarter=1, seconds=800, margin=0, yard=55, distance=3, ot_bits=0)),
)


def defense_prediction(retail: bytes, before: bytes, after: bytes, book: bytes) -> dict:
    fixtures = {name: Fixture(raw, 38.0) for name, raw in (("retail", retail), ("before", before), ("after", after))}
    for f in fixtures.values():
        f.load_book(book)
    rows = []
    for label, cell in DEFENSE_CELLS:
        res = {}
        for name, f in fixtures.items():
            f.state(down=4, quarter_seconds=900.0, **cell)
            res[name] = [f.defense_category(0.5, seed) for seed in range(1, 6)]
        rows.append(dict(situation=label, **res))
    return dict(note="defense category ids: 13 base, 14 nickel, 15 dime, 16 prevent, 18 punt return, 20 field goal block, 11 goal line",
                rows=rows)


SITUATIONS = (
    ("1st&10 own25", dict(down=1, distance=10, yard=25)), ("2nd&2 own40", dict(down=2, distance=2, yard=40)),
    ("2nd&8 mid", dict(down=2, distance=8, yard=50)), ("3rd&1 opp40", dict(down=3, distance=1, yard=60)),
    ("3rd&4 own45", dict(down=3, distance=4, yard=45)), ("3rd&8 mid", dict(down=3, distance=8, yard=50)),
    ("3rd&15 own30", dict(down=3, distance=15, yard=30)), ("1st&G opp3", dict(down=1, distance=3, yard=97)),
    ("3rd&G opp1", dict(down=3, distance=1, yard=99)),
)


def concept(name: str) -> str:
    import re
    return re.sub(r"\s+\d+$", "", re.sub(r"^\d+\s+", "", name)).strip()


def entropy(counter: Counter) -> float:
    total = sum(counter.values())
    return -sum(c / total * math.log2(c / total) for c in counter.values()) if total else 0.0


def call_mix(before: bytes, after: bytes, book: bytes, samples: int) -> dict:
    """Offense and defense call variety on one book: the defense commit 0x20B820 (front 0x20A7F0, coverage 0x20AA40)."""
    parsed = ip.parse_playbook_resource(book)
    out = {}
    for name, raw in (("before", before), ("after", after)):
        f = Fixture(raw, 50.0)
        f.load_book(book)
        rows = []
        for label, sit in SITUATIONS:
            f.state(**sit, margin=0, quarter=2, seconds=300)
            off_concepts, off_plays, covers, fronts = Counter(), Counter(), Counter(), Counter()
            for seed in range(samples):
                f.state(**sit, margin=0, quarter=2, seconds=300)
                f.seed(0.5, 1000003 * seed + 17)
                o = s.SOURCE + 0x19100
                f.m.mem_write(o, bytes(16))
                f.call(0x20B670, ecx=s.TEAM, edx=o)
                _cv, _fv, pv, _ = struct.unpack("<4I", f.m.mem_read(o, 16))
                pi, rem = divmod(pv - s.BOOK - ip.PLAY_BASE, 96) if pv else (None, 1)
                if rem == 0 and pi is not None and 0 <= pi < len(parsed.plays):
                    off_plays[parsed.plays[pi].name] += 1
                    off_concepts[concept(parsed.plays[pi].name)] += 1
                d = s.SOURCE + 0x19200
                f.m.mem_write(d, bytes(16))
                for a in (0xBF16FC, 0xBF1700):
                    f.put(a, 0)
                f.call(0x20B820, ecx=f.defense, edx=d, args=(0,))
                _dc, _df, dp, dq = struct.unpack("<4I", f.m.mem_read(d, 16))
                for ptr, bucket in ((dp, fronts), (dq, covers)):
                    pi, rem = divmod(ptr - s.BOOK - ip.PLAY_BASE, 96) if ptr else (None, 1)
                    if rem == 0 and pi is not None and 0 <= pi < len(parsed.plays):
                        bucket[concept(parsed.plays[pi].name)] += 1
            rows.append(dict(situation=label, samples=samples, offense_plays=len(off_plays), offense_concepts=len(off_concepts),
                             offense_concept_entropy=round(entropy(off_concepts), 3), front_concepts=len(fronts),
                             coverage_concepts=len(covers), coverage_entropy=round(entropy(covers), 3),
                             top_coverages=covers.most_common(3)))
        out[name] = rows
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--retail", required=True)
    ap.add_argument("--before", required=True, help="the v0.5 default.xbe")
    ap.add_argument("--after", required=True, help="the repaired (Modern 2) default.xbe")
    ap.add_argument("--book", required=True, help="a PLAY resource (.play, 32 byte header + body)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sections", default="fourth,two,defense,mix")
    ap.add_argument("--range-yards", type=float, default=38.0)
    ap.add_argument("--samples", type=int, default=60)
    ap.add_argument("--commit-every", type=int, default=25)
    args = ap.parse_args(argv)
    retail, before, after, book = (read_executable(a) for a in (args.retail, args.before, args.after, args.book))
    result = dict(retail_sha256=hashlib.sha256(retail).hexdigest(), before_sha256=hashlib.sha256(before).hexdigest(),
                  after_sha256=hashlib.sha256(after).hexdigest(), book_sha256=hashlib.sha256(book).hexdigest(),
                  range_yards=args.range_yards, runtime_witnessed=False,
                  scope="Native instructions of the real XBE with the real book on a bounded fixture; not played-game frequencies")
    sections = set(args.sections.split(","))
    if "fourth" in sections:
        result["fourth"] = fourth_down(retail, before, after, book, args.range_yards, args.commit_every)
        print("fourth: cells", result["fourth"]["cells"], "failures", result["fourth"]["failures"], flush=True)
    if "two" in sections:
        result["two"] = two_point(retail, before, after, book)
        print("two: cells", result["two"]["cells"], "failures", result["two"]["failures"], flush=True)
    if "defense" in sections:
        result["defense"] = defense_prediction(retail, before, after, book)
        print("defense prediction done", flush=True)
    if "mix" in sections:
        result["mix"] = call_mix(before, after, book, args.samples)
        print("mix done", flush=True)
    Path(args.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
