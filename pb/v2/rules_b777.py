#!/usr/bin/env python3
"""PROVED OFFLINE b777 playbook rules on composed team books (job pb4, Noah 10/20).

Script-checked rules, per book (offense formations only):

* ``duplicate_plays``: two menu entries with the same formation alignment, the same personnel and the same
  assignments for all eleven players (must be 0);
* ``duplicate_records``: two offense records with the same personnel and identical assignments (reported: they sit in
  different formations, so they are different plays, but one record would do);
* ``near_duplicates``: one record listed in two formations whose route runners (every skill player on a run) stand
  within 2 yd of each other, i.e. the same play on the field (reported; the generator refuses them);
* slot rule (generated formations; the retained retail Hail Mary and Clock sets are skipped): formations that put an outside receiver (WR1 / WR2 by the book's depth-role ordinals) inside another
  receiver or within 7 yd of the ball, or the slot receiver (WR3+) outside while that happens: at most
  ``--slot-formations`` per book and ``--slot-share`` of the book's links;
* ``mesh_share`` and ``verts_share``: links whose play is a mesh concept, or sends three or more receivers on plain
  vertical routes (go / seam, fade, bender), as a share of the book's pass links (caps ``--mesh-share``, ``--verts-share``);
* menus: every offense menu lists a multiple of three plays and at most 36;
* defense families: every book keeps a formation with plays behind each defense / kicking play-call code retail books
  carry (goal line, base 3-4 or 4-3, nickel, dime, prevent, the eight kicking units) and no empty category.

Also reports the league-wide count of distinct plays.  Exit status 1 when a rule fails.

    python3 pb/v2/rules_b777.py BOOKS_DIR [--json out.json]
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402

UTILITY = ("Editor", "PRACTICE", "reference", "GEN", "WCO")
# retail formations every modern book keeps unchanged (spike / kneel and the Hail Mary): not the slot rule's business
RETAINED_RETAIL = ("Hail Mary", "Clock")
YD = codec.YD_CM
WR, TE = 9, 8
SKILL = (lib.WR, lib.TE, lib.HB, lib.FB)
PLAIN_VERTICAL = {(0,), (6, 0), (1, 0)}


def _route_kinds(raw_nodes) -> tuple:
    kinds = []
    for raw in raw_nodes:
        node = codec.Node.from_bytes(raw)
        if node.op == 0x12:
            kinds.append(int(node.operands[0]))
    return tuple(kinds)


def _slot_violations(players, roles) -> list[str]:
    elig = [p for p in players if p[1] in (WR, TE) and not (p[3] <= -2.5 and abs(p[2]) < 3.5)]
    out, inside_outer = [], False
    for s, kind, x, z in players:
        if s not in roles:
            continue
        same = [q for q in elig if (q[2] < 0) == (x < 0)]
        outermost = abs(x) >= max(abs(q[2]) for q in same) - 0.01
        if roles[s] < 2 and (not outermost or abs(x) < 7.0):
            out.append(f"WR{roles[s] + 1}@{x:+.1f}")
            inside_outer = True
    for s, kind, x, z in players:
        if s in roles and roles[s] >= 2 and inside_outer:
            same = [q for q in elig if (q[2] < 0) == (x < 0)]
            if abs(x) >= max(abs(q[2]) for q in same) - 0.01 and abs(x) >= 12:
                out.append(f"WR{roles[s] + 1}@{x:+.1f} outside")
    return out


# Defense and special-teams play-call codes every team book carries in retail (all 32 books): goal line 0x0B,
# base front 0x0D (3-4 or 4-3), nickel 0x0E, dime 0x0F, prevent 0x10 and the eight kicking units 0x11-0x18.  A code
# the native call or CPU defense asks for with no formation behind it reads a NULL formation (Discord, Uncanny: a book
# without its base front froze on defense).
REQUIRED_DEFENSE_CODES = (0x0B, 0x0D, 0x0E, 0x0F, 0x10) + tuple(range(0x11, 0x19))


def defense_families(raw: bytes) -> dict:
    book = insp.parse_playbook_resource(raw)
    rows = insp.category_menu_rows(raw)
    have = {}
    for r in rows:
        links = sum(len(book.formations[m].play_links) for m in r["members"])
        if links:
            have.setdefault(r["code"] & 0x3F, []).append((r["name"], len(r["members"]), links))
    missing = [hex(c) for c in REQUIRED_DEFENSE_CODES if c not in have]
    return dict(missing_codes=missing, empty_categories=insp.category_menu_problems(raw),
                families={hex(c): v for c, v in sorted(have.items()) if c >= 0x0B})


def book_rules(raw: bytes) -> dict:
    book = insp.parse_playbook_resource(raw)
    body = raw[insp.RESOURCE_HEADER_SIZE:]
    seen, records, dup_plays = set(), {}, []
    homes: dict[int, list] = {}
    links_total = pass_links = mesh = verts = slot_links = 0
    slot_forms, menus_bad = [], []
    for f in book.formations:
        rec = lib.formation_record(body, f.index)
        if rec.type_code >= 4 or not f.play_links:
            continue
        codes = lib.category_positions(body, lib.formation_category(body, f.index))
        if not lib.is_offense_category(codes):
            continue
        retained = f.name.strip() in RETAINED_RETAIL
        players = [(s, codes[s] & 31, rec.slots[s].x[0] / YD, rec.slots[s].z[0] / YD) for s in range(11)]
        roles = {s: codes[s] >> 5 for s in range(11) if codes[s] & 31 == WR}
        n = len(f.play_links)
        if (n % 3 and f.name.strip() != "Clock") or n > insp.FORMATION_PLAY_LINKS:   # Clock: spike + kneel (accepted)
            menus_bad.append((f.name, n))
        viol = [] if retained else _slot_violations(players, roles)
        if viol:
            slot_forms.append((f.name, n, viol))
            slot_links += n
        geo = tuple((round(x * 2), round(z * 2)) for _s, _k, x, z in players)
        for link in f.play_links:
            p = book.plays[link.play_index]
            flags, chains = lib.play_chains(body, link.play_index)
            assign = hashlib.sha1(repr((flags & ~0x1FF, [b"".join(c) for _d, c in chains])).encode()).hexdigest()
            sig = (geo, tuple(c & 31 for c in codes), assign)
            links_total += 1
            if sig in seen:
                dup_plays.append((f.name, p.name))
            seen.add(sig)
            records.setdefault((tuple(c & 31 for c in codes), assign), set()).add(link.play_index)
            homes.setdefault(link.play_index, []).append(players)
            if flags & 0xF000 in (0x6000, 0x2000):
                pass_links += 1
                if "mesh" in p.name.lower():
                    mesh += 1
                vk = [_route_kinds(c) for (_d, c), (_s, kind, x, z) in zip(chains, players) if kind in (WR, TE)]
                if sum(1 for k in vk if k in PLAIN_VERTICAL) >= 3:
                    verts += 1
    dup_records = sum(len(v) - 1 for v in records.values())
    near = 0
    for idx, lists in homes.items():
        flags, chains = lib.play_chains(body, idx)
        runners = {s for s, (_d, c) in enumerate(chains) if any(k not in (9, 10) for k in _route_kinds(c))}
        for i in range(len(lists)):
            for j in range(i + 1, len(lists)):
                a, b = lists[i], lists[j]
                skill = [s for s in range(11) if a[s][1] in SKILL]
                moved = [abs(a[s][2] - b[s][2]) + abs(a[s][3] - b[s][3]) for s in (runners or skill) if s in skill]
                if max(moved, default=0.0) < 2.0:
                    near += 1
    fam = defense_families(raw)
    return dict(book=book.book_name, defense=fam, links=links_total, pass_links=pass_links, duplicate_plays=len(dup_plays),
                duplicate_play_rows=dup_plays[:10], duplicate_records=dup_records, near_duplicates=near,
                slot_formations=len(slot_forms), slot_links=slot_links,
                slot_share=round(slot_links / max(1, links_total), 4), slot_rows=slot_forms,
                mesh_links=mesh, mesh_share=round(mesh / max(1, pass_links), 4),
                verts_links=verts, verts_share=round(verts / max(1, pass_links), 4), bad_menus=menus_bad,
                signatures=sorted(f"{hash(s) & 0xFFFFFFFFFFFF:x}" for s in seen))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("books", type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--slot-formations", type=int, default=4)
    ap.add_argument("--slot-share", type=float, default=0.08)
    ap.add_argument("--mesh-share", type=float, default=0.03)
    ap.add_argument("--verts-share", type=float, default=0.06)
    args = ap.parse_args(argv)
    rows, fails, league = {}, [], set()
    for p in sorted([*args.books.glob("*.play"), *args.books.glob("*.bin")]):
        if p.stem in UTILITY:
            continue
        r = book_rules(p.read_bytes())
        league.update(r.pop("signatures"))
        rows[p.stem] = r
        bad = []
        if r["duplicate_plays"]:
            bad.append("duplicates")       # duplicate_records (same assignments listed under two records) is reported only
        if r["slot_formations"] > args.slot_formations or r["slot_share"] > args.slot_share:
            bad.append("slot rule")
        if r["mesh_share"] > args.mesh_share:
            bad.append("mesh")
        if r["verts_share"] > args.verts_share:
            bad.append("verticals")
        if r["bad_menus"]:
            bad.append("menus")
        if r["defense"]["missing_codes"] or r["defense"]["empty_categories"]:
            bad.append("defense families")
        if bad:
            fails.append((p.stem, bad))
        print(f"{p.stem:4} links {r['links']:4} dup {r['duplicate_plays']}/{r['duplicate_records']} near {r['near_duplicates']:3} "
              f"slot {r['slot_formations']} forms {r['slot_share']:.3f} mesh {r['mesh_share']:.3f} verts {r['verts_share']:.3f} "
              f"{'FAIL ' + ','.join(bad) if bad else 'ok'}")
    summary = dict(books=len(rows), mean_links=round(sum(r["links"] for r in rows.values()) / max(1, len(rows)), 1),
                   league_distinct_plays=len(league), failures=fails)
    print(summary)
    if args.json:
        args.json.write_text(json.dumps(dict(schema="pb_v2_rules_b777/v1", status="PROVED OFFLINE", summary=summary,
                                             teams=rows), indent=1) + "\n", encoding="utf-8", newline="\n")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
