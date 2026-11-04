#!/usr/bin/env python3
"""Q18 proof (b780 plays2): census and native-lottery evidence that every offense formation lists a run and a pass.

Runs the game's own play lottery 0x2096A0 and offensive commit 0x20B670 under Unicorn on the real executable and composed
PLAY books, with the CPU run share r (0xBF16F8) fixed.  Nothing here is a played game.

    census     lint.resource_coverage over every book (the unexempted list too, to show what retail itself ships)
    lottery    per offense formation, 40 draws of 0x2096A0 at r = 0.0 and r = 1.0: which formations hand back a play of
               the wrong type (a run-less set returns one fixed pass at r = 1.0)
    commit     0x20B670 (category, formation, play) under r: run / pass counts and the offending formations
    shares     the same commit over twelve ordinary situations at r = 0.5: overall run share and its binomial noise

Books come from ``--books DIR`` (TEAM.play, as ``pb/v2/verify3.py --books`` writes them) or ``--rc DIR`` (play-N.bin as
extracted from a disc, with its index.json {entry: sha}); ``--teams BAL,DEN`` restricts them.

    python3 tools/b77/q18_floor_proof.py commit --xbe default.xbe --books DIR --r 1.0 --n 100 --out commit.json
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_play_scoring as s  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as ip  # noqa: E402
from mod_editor.core import nfl2k5_playbook_lint as lint  # noqa: E402

LEAGUE = ("Editor", "GEN", "PRACTICE", "reference", "WCO")
RUN, PASS = 0x8000, 0x2000
SITUATIONS = {
    "1st&10 own25": dict(down=1, distance=10, yard=25), "1st&10 mid": dict(down=1, distance=10, yard=50),
    "1st&10 opp40": dict(down=1, distance=10, yard=60), "2nd&8 mid": dict(down=2, distance=8, yard=50),
    "2nd&7 own35": dict(down=2, distance=7, yard=35), "2nd&2 mid": dict(down=2, distance=2, yard=50),
    "2nd&5 mid": dict(down=2, distance=5, yard=50), "3rd&3 own25": dict(down=3, distance=3, yard=25),
    "3rd&8 mid": dict(down=3, distance=8, yard=50), "1st&G opp3": dict(down=1, distance=3, yard=97),
    "1st&10 own20": dict(down=1, distance=10, yard=20), "2nd&10 mid": dict(down=2, distance=10, yard=50),
}
DEFAULT_COMMIT = dict(down=1, distance=10, yard=30, margin=7, quarter=4, seconds=90)


def read_books(books: Path | None, rc: Path | None, teams: set | None) -> dict:
    out = {}
    if books is not None:
        for p in sorted(books.glob("*.play")):
            raw = p.read_bytes()
            name = ip.parse_playbook_resource(raw).book_name.strip()
            if not teams or name in teams:
                out[name] = raw
    if rc is not None:
        idx = json.loads((rc / "index.json").read_text(encoding="utf-8"))
        for k in sorted(idx, key=int):
            if int(k) >= 4418:
                continue
            raw = (rc / f"play-{k}.bin").read_bytes()
            name = ip.parse_playbook_resource(raw).book_name.strip()
            if not teams or name in teams:
                out.setdefault(name, raw)          # with --books, the disc only supplies the books the packs do not build
    return out


def census(raw: bytes) -> dict:
    book = ip.parse_playbook_resource(raw)
    body = raw[ip.RESOURCE_HEADER_SIZE:]
    from mod_editor.core import nfl2k5_play_library as lib
    bare = {"run": Counter(), "pass": Counter()}
    for f in book.formations:
        if lib.formation_record(body, f.index).type_code >= 4:
            continue
        flags = [book.plays[l.play_index].flags_or_id for l in f.play_links if book.plays[l.play_index].family_id == 0]
        if not any(x & RUN for x in flags):
            bare["run"][f.name.strip()] += 1
        if not any(not x & RUN and x & PASS for x in flags):
            bare["pass"][f.name.strip()] += 1
    findings = lint.resource_coverage(raw)
    return dict(book=book.book_name.strip(), no_run=sum(f.code == "FORMATION_NO_RUN" for f in findings),
                no_pass=sum(f.code == "FORMATION_NO_PASS" for f in findings),
                unexempted_run_less=dict(bare["run"]), unexempted_pass_less=dict(bare["pass"]),
                findings=[(f.code, f.formation_name) for f in findings])


def fixture(xbe: bytes, raw: bytes):
    from tools.b77.p9_harness import Fixture
    fx = Fixture(xbe)
    fx.load_book(raw)
    return fx


def kind_of(fx, pv: int) -> str:
    fl = fx.get(pv + 4)
    return "run" if fl & RUN else "pass" if fl & PASS else "other"


def lottery(xbe: bytes, raw: bytes, seeds: int = 40) -> dict:
    fx = fixture(xbe, raw)
    book = ip.parse_playbook_resource(raw)
    fx.configure(down=1, distance=10, yard=50)
    rows, bad = [], []
    for f in book.formations:
        fv = s.BOOK + ip.FORMATION_BASE + f.index * ip.FORMATION_SIZE
        if (fx.get(fv + 4) >> 8) & 63 > 3:
            continue
        cv = fx.call(0xE1A80, ecx=s.BOOK, edx=fv)
        row = {}
        for r in (0.0, 1.0):
            got = Counter()
            for seed in range(seeds):
                fx.seed(0.5, seed)
                fx.fput(0xBF16F8, r)
                pv = fx.call(0x2096A0, ecx=s.TEAM, edx=8, args=(fv, cv, 0))
                if not pv:
                    got["NULL"] += 1
                    continue
                pi = (pv - s.BOOK - ip.PLAY_BASE) // 96
                got[(kind_of(fx, pv), book.plays[pi].name.strip())] += 1
            row[r] = got
        name = f.name.strip()
        run1 = sum(c for (k, _n), c in row[1.0].items() if k == "run")
        pass0 = sum(c for (k, _n), c in row[0.0].items() if k == "pass")
        rows.append(dict(formation=name, runs_at_1=run1, of=seeds, passes_at_0=pass0,
                         distinct_runs_at_1=len({n for (k, n) in row[1.0] if k == "run"}),
                         distinct_passes_at_0=len({n for (k, n) in row[0.0] if k == "pass"})))
        if run1 != seeds or pass0 != seeds:
            bad.append(rows[-1])
    return dict(book=book.book_name.strip(), formations=len(rows), wrong_type=bad,
                min_distinct_runs_at_1=min((r["distinct_runs_at_1"] for r in rows if r["runs_at_1"]), default=0),
                min_distinct_passes_at_0=min((r["distinct_passes_at_0"] for r in rows if r["passes_at_0"]), default=0))


def commit(xbe: bytes, raw: bytes, r: float, n: int, situations: dict) -> dict:
    fx = fixture(xbe, raw)
    book = ip.parse_playbook_resource(raw)
    kinds, off = Counter(), Counter()
    per = {}
    for name, sit in situations.items():
        k = Counter()
        for seed in range(n):
            fx.state(**sit)
            fx.seed(0.5, seed)
            fx.fput(0xBF16F8, r)
            outp = s.SOURCE + 0x19100
            fx.m.mem_write(outp, bytes(16))
            fx.call(0x20B670, ecx=s.TEAM, edx=outp)
            _cv, fv, pv, _ = struct.unpack("<4I", fx.m.mem_read(outp, 16))
            if not pv:
                k["NULL"] += 1
                continue
            kd = kind_of(fx, pv)
            k[kd] += 1
            if kd != ("run" if r >= 0.99 else "pass" if r <= 0.01 else kd):
                fi = (fv - s.BOOK - ip.FORMATION_BASE) // ip.FORMATION_SIZE if fv else -1
                pi = (pv - s.BOOK - ip.PLAY_BASE) // 96
                off[f"{book.formations[fi].name.strip() if fi >= 0 else '?'} / {book.plays[pi].name.strip()}"] += 1
        per[name] = dict(k)
        kinds.update(k)
    total = sum(kinds.values())
    share = kinds["run"] / total if total else 0.0
    return dict(book=book.book_name.strip(), r=r, n_per_situation=n, situations=len(situations), kinds=dict(kinds),
                run_share=round(share, 4), noise_1sd=round(math.sqrt(share * (1 - share) / total), 4) if total else None,
                off_type_plays=dict(off.most_common(6)), per_situation=per)


def job(args):
    mode, xbe, name, raw, extra = args
    if mode == "lottery":
        return lottery(xbe, raw, **extra)
    if mode == "commit":
        return commit(xbe, raw, **extra)
    return census(raw)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("census", "lottery", "commit", "shares"))
    ap.add_argument("--xbe", type=Path)
    ap.add_argument("--books", type=Path)
    ap.add_argument("--rc", type=Path)
    ap.add_argument("--teams", default="")
    ap.add_argument("--r", type=float, default=1.0)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    teams = {t for t in a.teams.split(",") if t} or None
    books = read_books(a.books, a.rc, teams)
    if a.mode != "census":
        books = {k: v for k, v in books.items() if k not in LEAGUE}
    xbe = a.xbe.read_bytes() if a.xbe else None
    if a.mode == "census":
        extra, mode = {}, "census"
    elif a.mode == "lottery":
        extra, mode = dict(seeds=a.n), "lottery"
    elif a.mode == "commit":
        extra, mode = dict(r=a.r, n=a.n, situations={"1st&10 own30 Q4 +7 90s": DEFAULT_COMMIT}), "commit"
    else:
        extra, mode = dict(r=a.r if a.r != 1.0 else 0.5, n=a.n, situations=SITUATIONS), "commit"
    jobs = [(mode, xbe, name, raw, extra) for name, raw in books.items()]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(job, jobs))
    for row in rows:
        brief = {k: v for k, v in row.items() if k not in ("per_situation", "findings", "unexempted_run_less", "unexempted_pass_less")}
        print(json.dumps(brief), flush=True)
    if a.mode in ("commit", "shares"):
        tot = Counter()
        for row in rows:
            tot.update(row["kinds"])
        print("TOTAL", dict(tot), "run share", round(tot["run"] / max(1, sum(tot.values())), 4), flush=True)
    if a.out:
        a.out.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
