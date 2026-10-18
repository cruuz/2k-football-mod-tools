#!/usr/bin/env python3
"""Offense variety report for composed team books (b776 job pb1). Read only.

Reads PLAY resources (``<TEAM>.play`` files, e.g. extracted from a disc or written by
``pb/v2/verify.py --books``) and reports, per team and league-wide:

* formations by family (alignment x backfield, plus heavy and direct-snap sets);
* plays by family (run, QB run, quick, dropback, play action, boot/rollout, screen, trick, direct snap);
* run schemes, classified from the blocking and the exchange (zone, reach, power, counter, trap, draw,
  toss, iso, sneak, QB keep, ...) and the number of distinct line-blocking signatures;
* route segment kind usage (0-11) and distinct route shapes over every receiver chain;
* the first read (the play-call "primary" receiver) by roster position;
* screens per menu and the most repeated screen type in one menu;
* duplicate play records (identical eleven chains under two records) and plays shared across teams.

Everything is classified from the bytes, so retail, b775 and new books are measured the same way.
Usage: variety.py DIR [DIR ...] [--json OUT]   (each DIR holds the 32 <TEAM>.play files)
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_lint as lint  # noqa: E402

YD = codec.YD_CM
TEAMS = ("ARZ", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX",
         "KC", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "OAK", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB",
         "TEN", "WAS")
KIND_LABEL = {lib.WR: "WR", lib.TE: "TE", lib.HB: "HB", lib.FB: "FB", lib.QB: "QB"}


# ---------------------------------------------------------------------------
# Formation family (geometry first, so retail and new books compare)
# ---------------------------------------------------------------------------

def formation_family(view: lint.PlayView) -> str:
    kinds, pos = view.kinds, view.positions
    q = lint.qb_slot(view)
    center = next((s for s, k in enumerate(kinds) if k == lib.C), None)
    snap_to = None
    if center is not None:
        snap_to = next((int(n.operands[0]) for n in view.chains[center] if n.op == 0x02), None)
    qz = pos[q][1] if q is not None else 0.0
    if snap_to is not None and q is not None and snap_to != q:
        return "Direct snap"
    if qz <= -420:
        align = "Gun"
    elif qz <= codec.SHOTGUN_DEPTH_THRESHOLD_CM:
        align = "Pistol"
    else:
        align = "UC"
    backs = [s for s, k in enumerate(kinds) if k in (lib.HB, lib.FB, lib.TE, lib.WR)
             and pos[s][1] <= -2.5 * YD and abs(pos[s][0]) <= 4.5 * YD]
    tes = sum(1 for k in kinds if k == lib.TE)
    wrs = sum(1 for k in kinds if k == lib.WR)
    if len(backs) == 0:
        back = "Empty"
    elif len(backs) == 1:
        back = "Single"
    elif len(backs) >= 3:
        back = "Full House"
    else:
        a, b = sorted(backs, key=lambda s: pos[s][1])        # deeper first
        xa, xb = pos[a][0], pos[b][0]
        if abs(xa - xb) <= 0.6 * YD:
            back = "I"
        elif abs(xb) >= 1.0 * YD and abs(xa) <= 0.6 * YD:
            back = "Offset I"
        else:
            back = "Split"
    heavy = tes >= 3 or (tes >= 2 and wrs <= 1)
    if align == "UC":
        name = {"Single": "Singleback", "I": "I-Form", "Offset I": "Strong/Weak I", "Split": "Split Backs",
                "Full House": "Full House", "Empty": "Empty UC"}[back]
    else:
        name = f"{align} {back}"
    return name + (" Heavy" if heavy else "")


# ---------------------------------------------------------------------------
# Play family and run scheme
# ---------------------------------------------------------------------------

def _ops(chain):
    return [n.op for n in chain]


def play_family(view: lint.PlayView) -> str:
    q = lint.qb_slot(view)
    flags = view.play_flags
    qb = view.chains[q] if q is not None else []
    if formation_family(view) == "Direct snap":
        return "direct snap"
    if flags & 0x1000:
        return "trick"
    if lint.is_pass(view):
        if any(n.op == 0x13 for n in qb):
            return "trick"
        if lint.screen_receiver(view) is not None or "screen" in view.play_name.lower():
            return "screen"
        lateral = any(n.op == 0x04 and int(n.operands[0]) == 1 for n in qb)
        pa = any(n.op == 0x14 for n in qb)
        if lateral:
            return "boot/rollout"
        if pa:
            return "play action"
        cls = flags & 0xF000
        return "quick" if cls == 0x2000 else "dropback"
    if any(n.op == 0x13 for n in qb):
        return "run"
    return "QB run"


def run_scheme(view: lint.PlayView) -> str | None:
    fam = play_family(view)
    if fam not in ("run", "QB run", "direct snap", "trick"):
        return None
    kinds, chains = view.kinds, view.chains
    q = lint.qb_slot(view)
    ol = [s for s, k in enumerate(kinds) if k in lib.OL_KINDS]
    legs = [[n for n in chains[s] if n.op == 0x11] for s in ol]
    pulls = sum(1 for lg in legs if any(int(n.operands[0]) == 2 for n in lg))
    zone = sum(1 for lg in legs if lg and int(lg[0].operands[0]) == 8)
    reach = sum(1 for lg in legs if lg and int(lg[0].operands[0]) == 0 and abs(lg[0].operands[5]) > 0.1)
    setfirst = sum(1 for lg in legs if lg and int(lg[0].operands[0]) == 1)
    pairs = lint.handoff_pairs(view)
    if fam == "QB run":
        qb = chains[q]
        drop = any(n.op == 0x04 and n.operands[2] < -6 * codec.FT_CM for n in qb)
        if any(n.op == 0x04 and n.operands[2] < -6 * codec.FT_CM for n in qb) and setfirst >= 3:
            return "QB draw"
        if pulls:
            return "QB power"
        lead = sum(1 for s, k in enumerate(kinds) if k in (lib.HB, lib.FB, lib.TE) and view.positions[s][1] < view.positions[q][1]
                   and abs(view.positions[s][0] - view.positions[q][0]) <= 1.2 * YD)
        if lead >= 1 and view.positions[q][1] > -3 * YD:
            return "QB sneak (stacked)" if lead >= 2 else "QB sneak"
        return "QB keep" if not drop else "QB draw"
    if not pairs:
        return "other"
    giver, target, k, hole = pairs[0]
    tk = kinds[target]
    if tk in (lib.WR, lib.TE):
        return "reverse/end around"
    if fam == "direct snap":
        return "direct snap"
    hole_x = abs(codec.HANDOFF_HOLE_CM[hole]) / YD if 0 <= hole < len(codec.HANDOFF_HOLE_CM) else 0
    if k in (1, 3):
        return "toss" if k == 1 else "pitch"
    if setfirst >= 3:
        return "draw"
    lead = any(any(n.op == 0x11 and int(n.operands[0]) == 4 for n in chains[s])
               for s, kk in enumerate(kinds) if kk in (lib.FB, lib.TE, lib.HB) and s != target)
    if k == 5 or (pulls and hole_x < 2 and any(n.op == 0x16 and int(n.operands[0]) == 1 for n in chains[target])):
        return "counter"
    if pulls >= 2:
        return "power (two pullers)"
    if pulls == 1:
        guard_pull = [s for s, lg in zip(ol, legs) if any(int(n.operands[0]) == 2 for n in lg)]
        dist = max(abs(n.operands[5]) for s in guard_pull for n in chains[s] if n.op == 0x11 and int(n.operands[0]) == 2) / codec.FT_CM
        if dist <= 8:
            return "trap"
        return "power" if hole_x >= 2 else "counter"
    if zone >= 3:
        return "outside zone" if hole_x >= 3 else "inside zone"
    if reach >= 3:
        return "stretch/reach"
    if lead:
        return "iso/lead"
    return "duo/drive" if hole_x < 3 else "off tackle"


def ol_signature(view: lint.PlayView) -> bytes:
    ol = [s for s, k in enumerate(view.kinds) if k in lib.OL_KINDS]
    return b"".join(n.to_bytes() for s in ol for n in view.chains[s])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def route_shape(chain) -> tuple | None:
    segs = [n for n in chain if n.op == 0x12]
    if not segs:
        return None
    kinds = tuple(int(n.operands[0]) for n in segs)
    stem = segs[0].operands[2] / YD if kinds[0] in (0, 10) else 0.0
    band = "s" if stem <= 4.5 else "m" if stem <= 9.5 else "d"
    pre = tuple("blk" if n.op == 0x11 else "fake" if n.op == 0x17 else "" for n in chain if n.op in (0x11, 0x17))
    return (pre[:1],) + kinds + (band,)


def position_label(code: int) -> str:
    kind = code & 31
    base = KIND_LABEL.get(kind, f"k{kind}")
    if kind == lib.WR:
        return f"WR{(code >> 5) // 2 + 1}" if False else f"WR{(code >> 5) + 1}"
    return f"{base}{(code >> 5) + 1}"


def play_key(view: lint.PlayView) -> str:
    return hashlib.sha1(b"".join(n.to_bytes() for ch in view.chains for n in ch)).hexdigest()[:16]


def screen_type(view: lint.PlayView) -> str | None:
    if play_family(view) != "screen":
        return None
    s = lint.first_read_slot(view)
    if s is None:
        return "screen"
    kind = view.kinds[s]
    q = lint.qb_slot(view)
    mode = next((int(n.operands[0]) for n in view.chains[q] if n.op == 0x06), 0)
    shape = route_shape(view.chains[s])
    return f"{KIND_LABEL.get(kind, kind)} m{mode} {shape[1:] if shape else ''}"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def team_report(raw: bytes) -> dict:
    views = list(lint.resource_views(raw))
    book = insp.parse_playbook_resource(raw)
    body = raw[32:]
    from mod_editor.core.nfl2k5_complete_offense import ordinary_indices
    fs, ps = ordinary_indices(book, body)
    ordinary = [v for v in views if v.play in ps or v.formation in fs]
    by_play: dict[int, lint.PlayView] = {}
    for v in ordinary:
        by_play.setdefault(v.play, v)
    forms = {}
    menus = defaultdict(list)
    for v in ordinary:
        forms.setdefault(v.formation, (v.formation_name, formation_family(v)))
        menus[v.formation].append(v)
    fam_forms = Counter(f for _, f in forms.values())
    fam_plays = Counter(play_family(v) for v in by_play.values())
    schemes = Counter(s for s in (run_scheme(v) for v in by_play.values()) if s)
    ol_sigs = {ol_signature(v) for v in by_play.values() if run_scheme(v)}
    kinds = Counter()
    shapes = Counter()
    primary = Counter()
    primary_role = Counter()
    for v in by_play.values():
        if not lint.is_pass(v):
            continue
        for s, k in enumerate(v.kinds):
            if k in lint.RECEIVER_KINDS:
                for n in v.chains[s]:
                    if n.op == 0x12:
                        kinds[int(n.operands[0])] += 1
                sh = route_shape(v.chains[s])
                if sh and not all(k2 == 9 for k2 in sh[1:-1]):
                    shapes[sh] += 1
        r = lint.first_read_slot(v)
        if r is not None:
            primary[position_label(v.codes[r])] += 1
    # primary by link (what the play-call screen shows across menus)
    for v in ordinary:
        if lint.is_pass(v):
            r = lint.first_read_slot(v)
            if r is not None:
                x, z = v.positions[r]
                k = v.kinds[r]
                role = ("back" if k in (lib.HB, lib.FB) and z <= -2.5 * YD else
                        "TE" if k == lib.TE else
                        "outside WR" if k == lib.WR and abs(x) >= 12 * YD else "slot/inside")
                primary_role[role] += 1
    screens_per_menu = []
    same_screen_max = []
    for f, vs in menus.items():
        types = Counter(t for t in (screen_type(v) for v in vs) if t)
        screens_per_menu.append(sum(types.values()))
        same_screen_max.append(max(types.values()) if types else 0)
    short_menus = sum(1 for vs in menus.values() if len(vs) % 3)
    lanes = defaultdict(set)
    for v in by_play.values():
        sch = run_scheme(v)
        pairs = lint.handoff_pairs(v) if sch else []
        if pairs:
            lane = (2, 4, 3, 3, 2, 2, 1, 1, 0)[pairs[0][3]]
            lanes[min(lane, 4 - lane)].add(sch)
    deep = 0
    for v in by_play.values():
        if lint.is_pass(v) and play_family(v) != "screen":
            r = lint.first_read_slot(v)
            if r is not None:
                end = lint.route_end_depth(v.chains[r], v.positions[r][1])
                deep += end is not None and end >= 20 * YD
    keys = Counter(play_key(v) for v in by_play.values())
    dup = sum(c - 1 for c in keys.values() if c > 1)
    return dict(
        formations=len(forms), plays=len(by_play), links=len(ordinary),
        menu_sizes=dict(min=min(len(v) for v in menus.values()), max=max(len(v) for v in menus.values()),
                        mean=round(sum(len(v) for v in menus.values()) / len(menus), 1)),
        formation_families=dict(fam_forms.most_common()), play_families=dict(fam_plays.most_common()),
        run_schemes=dict(schemes.most_common()), run_blocking_signatures=len(ol_sigs),
        route_kinds={str(k): kinds.get(k, 0) for k in range(12)}, route_kinds_used=sum(1 for k in range(12) if kinds.get(k)),
        route_shapes=len(shapes), primary_by_position=dict(primary.most_common()),
        primary_by_alignment=dict(primary_role.most_common()),
        screens_per_menu_max=max(screens_per_menu), same_screen_in_menu_max=max(same_screen_max),
        duplicate_play_records=dup, play_keys=sorted(keys), short_menu_formations=short_menus,
        run_schemes_per_lane={str(k): len(v) for k, v in sorted(lanes.items())}, deep_shot_plays=deep,
        formation_names=sorted(n for n, _ in forms.values()))


def summarize(label: str, rows: dict) -> dict:
    league = dict(label=label, teams=len(rows))
    def mean(key):
        return round(sum(r[key] for r in rows.values()) / len(rows), 1)
    for key in ("formations", "plays", "links", "run_blocking_signatures", "route_kinds_used", "route_shapes",
                "duplicate_play_records", "short_menu_formations", "deep_shot_plays"):
        league[key + "_mean"] = mean(key)
    fam = Counter(); pf = Counter(); rs = Counter(); rk = Counter(); prim = Counter(); role = Counter()
    for r in rows.values():
        fam.update(r["formation_families"]); pf.update(r["play_families"]); rs.update(r["run_schemes"])
        rk.update({int(k): v for k, v in r["route_kinds"].items()}); prim.update(r["primary_by_position"])
        role.update(r["primary_by_alignment"])
    league["formation_families_total"] = dict(fam.most_common())
    league["formation_family_kinds"] = len(fam)
    league["play_families_total"] = dict(pf.most_common())
    league["run_schemes_total"] = dict(rs.most_common())
    league["run_scheme_kinds"] = len(rs)
    league["route_kinds_total"] = {str(k): rk.get(k, 0) for k in range(12)}
    tot = sum(prim.values()) or 1
    league["primary_by_position_pct"] = {k: round(100 * v / tot, 1) for k, v in prim.most_common()}
    tot = sum(role.values()) or 1
    league["primary_by_alignment_pct"] = {k: round(100 * v / tot, 1) for k, v in role.most_common()}
    league["screens_per_menu_max"] = max(r["screens_per_menu_max"] for r in rows.values())
    league["same_screen_in_menu_max"] = max(r["same_screen_in_menu_max"] for r in rows.values())
    # cross-team uniqueness of play records (exact eleven chains)
    owners = defaultdict(set)
    for t, r in rows.items():
        for k in r["play_keys"]:
            owners[k].add(t)
    uniq = {t: round(100 * sum(1 for k in r["play_keys"] if len(owners[k]) == 1) / max(1, len(r["play_keys"])), 1)
            for t, r in rows.items()}
    league["team_unique_play_pct_mean"] = round(sum(uniq.values()) / len(uniq), 1)
    league["team_unique_play_pct_min"] = min(uniq.values())
    league["distinct_plays_league"] = len(owners)
    names = defaultdict(set)
    for t, r in rows.items():
        for n in r["formation_names"]:
            names[n].add(t)
    league["distinct_formation_names_league"] = len(names)
    return league


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--teams", nargs="*")
    args = ap.parse_args(argv)
    out = {}
    for d in args.dirs:
        rows = {}
        for t in args.teams or TEAMS:
            p = d / f"{t}.play"
            if p.exists():
                rows[t] = team_report(p.read_bytes())
        out[str(d)] = dict(league=summarize(d.name, rows), teams={t: {k: v for k, v in r.items() if k != "play_keys"}
                                                                  for t, r in rows.items()})
        lg = out[str(d)]["league"]
        print(f"== {d}")
        for k, v in lg.items():
            print(f"  {k}: {v}")
    if args.json:
        args.json.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
