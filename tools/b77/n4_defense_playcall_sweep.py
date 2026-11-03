#!/usr/bin/env python3
"""Every club's defensive play call, checked offline against every situation (b780 n4). Read only; no emulator.

Smuzz 11/02: "After 3-4 plays into a quick play and MyNFL game, the game freezes at this exact screen and
commentators repeat lines" (the human Patriots on defense at the play-call screen, 3-4 page, OFFENSE CHOSE Kings, at
Seattle). This sweep runs, under Unicorn on a disc's own executable and books, the native code that runs on that
screen for each club's defensive book:

* menus: the native preview / play-list models (``category_menu_problems``, ``menu_link_problems``) and the
  defensive audible table (``audible_table_problems``);
* selection: the CPU defense orchestrator 0x20B820 and the offense commit 0x20B670 (frz_suite selectors: every
  down / distance / field position / clock state of the focused set, ``--samples`` random draws each, plus every
  formation context 0x2096A0), which map the offense's personnel to a defensive package;
* the human Coach's Pick 0xAA660 (the play-calling option "Let Coach Pick" runs it on entry, the L button runs it
  too): the pick and the native menu walks that place it on its page, both sides;
* ``--lineup``: the native slot filler 0x189360 over every personnel category x slot x tier x fatigue, with
  rested, tired, injured and mixed rosters (frz_suite caller).

A call that does not return inside its instruction budget is a FAULT (a loop the game would hang in).

usage: n4_defense_playcall_sweep.py (--disc ISO | --dir EXTRACTED) [--teams NE,SEA|ALL] [--samples N] [--lineup]
                                     [--out receipt.json]
``--dir`` holds default.xbe, entry5.bin and <TEAM>.play files (frz_probe's extraction layout).
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

TEAM_KEYS = ("ARZ ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC MIA MIN NE NO NYG NYJ OAK PHI PIT SD SEA "
             "SF STL TB TEN WAS").split()


def extract(disc: Path, out: Path) -> Path:
    """default.xbe, entry 5 (rosters) and the 32 club books of a disc image (read only)."""
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    from mod_editor.core import modpack
    xc = modpack._xdvdfs_module()
    out.mkdir(parents=True, exist_ok=True)
    fd = os.open(disc, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        size = os.fstat(fd).st_size
        base = int(xc.locate_xdvdfs_base(fd, size))
        entries, _ = xc.parse_xdvdfs(fd, size, base)
        e = entries["default.xbe"]
        os.lseek(fd, base + e.sector * 2048, os.SEEK_SET)
        (out / "default.xbe").write_bytes(os.read(fd, e.size))
    finally:
        os.close(fd)
    with OuterImage(disc) as image:
        (out / "entry5.bin").write_bytes(image.read_entry(5))
        for key, index in BOOK_ENTRIES.items():
            if key in TEAM_KEYS:
                (out / f"{key}.play").write_bytes(image.read_entry(index))
    return out


def menu_checks(raw: bytes) -> list[str]:
    from mod_editor.core import nfl2k5_playbook_inspector as ip
    from mod_editor.core import nfl2k5_playbook_pack as pack
    problems = list(ip.category_menu_problems(raw)) + list(ip.menu_link_problems(raw))
    problems += list(pack.audible_table_problems(raw))
    return problems


def coach_pick(xbe: bytes, raw: bytes, samples: int) -> dict:
    """The human Coach's Pick 0xAA660 for both sides over the focused situations (UI state push stubbed)."""
    import random
    from pb.scoring_selectors import World
    from mod_editor.core import nfl2k5_play_scoring as s
    m = World(xbe)
    m.load(raw)
    pane, menu = s.SOURCE + 0x1E000, s.SOURCE + 0x1E800
    placed = {}

    def push(u, a, n, d):
        sp = u.reg_read(m.r.UC_X86_REG_ESP)
        u.reg_write(m.r.UC_X86_REG_ESP, sp + 4)
        u.reg_write(m.r.UC_X86_REG_EIP, m.get(sp))

    def finish(u, a, n, d):        # 0xAA8A0: the pick is on its page; the rest is presentation
        placed["at"] = a
        u.reg_write(m.r.UC_X86_REG_EIP, s.STOP)
        u.reg_write(m.r.UC_X86_REG_ESP, s.STACK + 4)
    m.m.hook_add(m.ucmod.UC_HOOK_CODE, push, begin=0x6E390, end=0x6E390)
    m.m.hook_add(m.ucmod.UC_HOOK_CODE, finish, begin=0xAA8A0, end=0xAA8A0)
    states = [dict(down=d, distance=n, yard=y) for d in (1, 2, 3, 4) for n in (1, 3, 7, 10, 15) for y in (5, 25, 50, 80)]
    states += [dict(margin=mg, quarter=q, seconds=t) for mg in (-8, 0, 8) for q in (2, 4) for t in (30, 120)]
    row = dict(cases=0, faults=[])
    rng = random.Random(11022026)
    for side in (1, 0):
        for state in states:
            for _ in range(samples):
                m.configure(**state)
                draw = rng.random()
                m.fput(0xBF1244, draw); m.fput(0xBF1484, draw)
                m.m.mem_write(pane, bytes(0x200)); m.m.mem_write(menu, bytes(0x200))
                m.put(pane + 0xC, side); m.put(pane + 0x20, s.BOOK)
                placed.clear(); row["cases"] += 1
                try:
                    m.call(0xAA660, esi=pane, ebx=menu)
                    if not placed:
                        raise RuntimeError("returned without placing the pick")
                except Exception as exc:  # noqa: BLE001
                    row["faults"].append(dict(side="defense" if side else "offense", state=state, error=str(exc)[:240]))
    return row


def sweep(directory: Path, teams: list[str], samples: int, lineup: bool, out: Path | None) -> dict:
    import frz_suite as fs
    xbe = (directory / "default.xbe").read_bytes()
    result = dict(schema="n4_defense_playcall_sweep/v1", directory=str(directory), samples=samples, teams=[])
    original_books = fs.books
    try:
        fs.books = lambda d: [(k, (d / f"{k}.play").read_bytes()) for k in teams]
        with tempfile.TemporaryDirectory() as tmp:
            sel = fs.selectors(directory, Path(tmp) / "sel.json", samples=samples, focused=True)
            if lineup:
                from frz_probe import rr
                doc = rr.load_body((directory / "entry5.bin").read_bytes()[32:], scheme="one_pool")
                keep = set(teams)
                aliases = {"ARI": "ARZ", "LAC": "SD", "LV": "OAK", "LAR": "STL"}
                load = rr.load_body

                class Subset:
                    def __getattr__(self, name):
                        return getattr(doc, name)
                subset = Subset()
                subset.teams = [t for t in doc.teams[:32] if aliases.get(t.abbreviation, t.abbreviation) in keep]
                rr.load_body = lambda *a, **k: subset
                try:
                    lin = fs.caller(directory, Path(tmp) / "lineup.json")
                finally:
                    rr.load_body = load
            else:
                lin = dict(teams=[])
    finally:
        fs.books = original_books
    sel_rows = {r["team"]: r for r in sel["teams"]}
    lin_rows = {r["team"]: r for r in lin["teams"]}
    for team in teams:
        raw = (directory / f"{team}.play").read_bytes()
        cp = coach_pick(xbe, raw, max(1, samples // 2))
        row = dict(team=team, menu_problems=menu_checks(raw),
                   selectors=dict(cases=sel_rows[team]["cases"], faults=sel_rows[team]["faults"][:10]),
                   coach_pick=dict(cases=cp["cases"], faults=cp["faults"][:10]))
        if team in lin_rows:
            row["lineup"] = dict(cases=lin_rows[team]["cases"], faults=lin_rows[team]["faults"][:10])
        result["teams"].append(row)
        print(team, "menus", len(row["menu_problems"]), "selectors", row["selectors"]["cases"],
              len(sel_rows[team]["faults"]), "coach_pick", cp["cases"], len(cp["faults"]),
              "lineup", (row.get("lineup") or {}).get("cases"), len((row.get("lineup") or {}).get("faults", [])),
              flush=True)
        if out:
            out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    result["faults"] = sum(len(t["menu_problems"]) + len(t["selectors"]["faults"]) + len(t["coach_pick"]["faults"])
                           + len((t.get("lineup") or {}).get("faults", [])) for t in result["teams"])
    if out:
        out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--disc", type=Path)
    src.add_argument("--dir", type=Path)
    ap.add_argument("--teams", default="ALL")
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--lineup", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    teams = TEAM_KEYS if a.teams == "ALL" else a.teams.split(",")
    t0 = time.time()
    if a.disc:
        with tempfile.TemporaryDirectory() as tmp:
            res = sweep(extract(a.disc, Path(tmp)), teams, a.samples, a.lineup, a.out)
    else:
        res = sweep(a.dir, teams, a.samples, a.lineup, a.out)
    print("DONE", len(res["teams"]), "teams, faults", res["faults"], f"{time.time() - t0:.0f}s")
    return 1 if res["faults"] else 0


if __name__ == "__main__":
    sys.exit(main())
