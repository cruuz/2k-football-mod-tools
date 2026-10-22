#!/usr/bin/env python3
"""No Huddle plays and quick game for weak offensive lines (b778, job pb7) on the shipped SOFTDRINK offense packs.

Noah (10/22, after his 10/21 stream): "fix the no huddle plays. I need a good variety of runs and passes ... for
different situations ... And some more plays with quicker passes, you know, for bad offensive line teams."

1. ``no_huddle``  The No Huddle panel (Noah's stream 5:03:20, "NO HUDDLE" with A / B / L / R pages) reads the PLAY
                  book header table at 0x4C: five (formation index, menu link) byte pairs for the offense, five for
                  the defense (native 0xFEFA0 -> 0xFF09C, entry side * 5 + button; 0xE13F0 reads link word
                  ``aux + link * 2`` of that formation). The complete-offense compiler kept the retail formation
                  indices and wrote links 0, 1, 2, 2, 2, so the five plays were whatever the new books held there:
                  TEN had Tush Push (Goal Line Sneak), X Slant Flat, RB Slants Out, Bubble Screen (Gun Wildcat) and
                  Z Hitch Seam. The pack now names its five plays (``no_huddle``) and the compiler writes them. The
                  five roles, in table order: an inside run (a draw first), a quick-game pass, a sideline (clock
                  stopping) pass, a screen and one shot down the field, each from the book's own shotgun 11 /
                  10 personnel sets where it has one (no substitution in a hurry-up), never from a goal line, short
                  yardage or wildcat set. Spike, fake spike and kneel are native buttons and are not in the table.
2. ``quick``      Quick game (a quick drop, the primary and at least three routes finish within 7.5 yd, at most one
                  clear-out deeper) was 4 to 15 percent of each book's links, and many normal-down menus had none
                  (OAK 8 of 15, GB 9 of 23). Every normal-down menu (the passing sets and the 11 / 10 personnel base
                  sets) now lists at least ``QUICK_MIN`` quick-game plays, and ``QUICK_MIN_WEAK`` in a book whose
                  line is weak (``ol_grades.json``: mean pass blocking of the best two tackles, two guards and
                  centre on the shipped roster below ``WEAK_OL_PASS_BLOCK``), where the book's records allow it.
                  Nothing is added or removed in count (records, formations, links and pages stay as they were);
                  only weak duplicates give way, in this order:
                  a. a link: a dropback / deep pass another menu also lists becomes a quick-game record of the
                     book that passes the generator's sharing rules there (pb5 ``refill_candidates``);
                  b. a record: a dropback / deep / play-action pass listed only in this menu, whose concept another
                     record still carries, becomes an engine quick-game design built in this formation (same id,
                     record slot and menu position; ``convert_record``);
                  c. a relocation: such a record from another normal-down menu becomes the design here and its old
                     menu position gets a pass the refill rules allow there.
                  Every design passes the generator's candidate checks (retail validator, no reversal, lint clean,
                  the native route initializer with ``--xbe``) and fits the book's name pool.

    python3 pb/v2/hurry_b778.py --check --xbe XBE       # counts per rule, exit 1 when anything would change
    python3 pb/v2/hurry_b778.py --apply --xbe XBE       # write the packs, catalogs and both manifests

PROVED OFFLINE on the packs' own data (and the retail route initializer with ``--xbe``); gameplay is for the emulator
and Noah to witness.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

RULES = ("no_huddle", "quick")
OL_GRADES = Path(__file__).resolve().parent / "ol_grades.json"

#: Mean pass blocking (best two tackles, two guards and the centre on the shipped roster) below which a line is weak.
WEAK_OL_PASS_BLOCK = 79.0
#: Quick-game plays on every normal-down menu: every book, and books with a weak line.
QUICK_MIN, QUICK_MIN_WEAK = 1, 2
QUICK_MAX_YD = 7.5             # a quick-game route finishes within 7.5 yd of the line
QUICK_DROP_CM = -500.0         # QB Special Move depth of a quick drop (-457.2 cm); 7 and 8 yd drops are slower
PAGE, MENU_MAX = 3, 36
QB, WR, TE, HB, FB = 0, 9, 8, 10, 11
ROUTE, DROP, PASS = 0x12, 0x04, 0x06
YD_CM = 91.44
OUTSIDE_KINDS = (5, 6, 7)      # route kinds that break toward the sideline (codec.ROUTE_OUTSIDE_KINDS)
TEAM_ALIAS = {"ARZ": "ARI", "STL": "LAR", "SD": "LAC", "OAK": "LV"}

# No Huddle roles in table order. Entries 1-4 sit on A, B, L, R (stream stills); entry 0 is the panel's first page.
NH_ROLES = ("inside_run", "quick", "sideline", "screen", "shot")
NH_FORM_TAGS = ("pass", "spread", "empty", "base")       # never goal / short (or the wildcat set)


def ol_grades() -> dict:
    return json.loads(OL_GRADES.read_text(encoding="utf-8"))


def weak_line(team: str, grades: dict | None = None) -> bool:
    row = (grades or ol_grades())["teams"].get(TEAM_ALIAS.get(team, team))
    return row is not None and row["pass_block"] < WEAK_OL_PASS_BLOCK


# ---------------------------------------------------------------------------
# play classes (pack geometry)
# ---------------------------------------------------------------------------

def _ctx(form: dict):
    from mod_editor.core import nfl2k5_offense_concepts as oc
    return oc.FormationContext.build([(float(x), float(z)) for x, z in form["slot_positions"]], form["position_codes"])


def _chain(play: dict, slot: int) -> list:
    return [(int(n[0]), list(n[1])) for n in (play["assignments"][slot] or [])]


def qb_drop_cm(play: dict) -> float | None:
    for n in play["assignments"][0] or []:
        if n[0] == DROP and int(n[1][0]) == 0:
            return float(n[1][2])
    return None


def primary_slot(play: dict) -> int | None:
    for n in play["assignments"][0] or []:
        if n[0] == PASS:
            read = int(n[1][1])
            return read + 5 if read else None
    return None


def route_ends(play: dict, form: dict) -> dict:
    """{slot: end depth in yards (99 = keeps running)} for every route runner (not pass blockers)."""
    from mod_editor.core import nfl2k5_offense_concepts as oc
    ctx = _ctx(form)
    out = {}
    for q in ctx.players:
        if q.kind not in (WR, TE, HB, FB):
            continue
        chain = _chain(play, q.slot)
        kinds = [int(n[1][0]) for n in chain if n[0] == ROUTE]
        if not kinds or all(k in (9, 10) for k in kinds):
            continue
        end = oc.route_end_depth_yd(ctx, q.slot, chain)
        out[q.slot] = 99.0 if end is None else end
    return out


def is_quick_game(play: dict, form: dict, row: dict | None = None) -> bool:
    """Quick game: a quick drop (or none: gun catch-and-throw), the primary and three or more routes finish within
    QUICK_MAX_YD, at most one clear-out deeper. Screens are their own family."""
    if play.get("play_type") != "pass" or (row or {}).get("family") == "screen":
        return False
    drop = qb_drop_cm(play)
    if drop is None or drop < QUICK_DROP_CM:
        return False
    ends = route_ends(play, form)
    prim = primary_slot(play)
    short = sum(1 for v in ends.values() if v <= QUICK_MAX_YD)
    return prim in ends and ends[prim] <= QUICK_MAX_YD and short >= 3 and len(ends) - short <= 1


def _last_kind(play: dict, slot: int) -> int | None:
    kinds = [int(n[1][0]) for n in _chain(play, slot) if n[0] == ROUTE]
    return kinds[-1] if kinds else None


def role_score(role: str, play: dict, row: dict, form: dict) -> float:
    """How well ``play`` fills a No Huddle role (0 = not at all)."""
    name, family, ptype = play["custom_name"], row.get("family"), play.get("play_type")
    if role == "inside_run":
        if ptype != "run" or family != "run" or row.get("header") == "run_toss":
            return 0.0
        for word, score in (("Draw", 5), ("Inside Zone", 4), ("Trap", 3.5), ("Duo", 3.5), ("Dive", 3), ("Iso", 3),
                            ("Counter", 2), ("Power", 2)):
            if word in name:
                return score - (0.5 if name.endswith("Wk") else 0.0)
        return 0.0
    if ptype != "pass" or family == "trick":
        return 0.0
    if role == "screen":
        if family != "screen":
            return 0.0
        return 4.0 if "Bubble" in name else 3.0 if row.get("header") == "quick_screen" else 2.0
    prim = primary_slot(play)
    ends = route_ends(play, form)
    if prim not in ends:
        return 0.0
    if role == "quick":
        if not is_quick_game(play, form, row):
            return 0.0
        for word, score in (("Slant Flat", 5), ("Double Slants", 5), ("Stick", 4.5), ("Spacing", 4.5),
                            ("Snag", 4), ("Slants", 4)):
            if word in name:
                return score
        return 3.0
    if role == "sideline":
        kind = form["position_codes"][prim] & 31
        if family == "screen" or kind not in (WR, TE) or not 3.0 <= ends[prim] <= 15.0 \
                or _last_kind(play, prim) not in OUTSIDE_KINDS:
            return 0.0
        drop = qb_drop_cm(play)
        if drop is not None and drop < -700.0:
            return 0.0
        for word, score in (("Quick Outs", 5), ("Outs", 4.5), ("Smash", 4), ("Comeback", 4), ("Out", 3.5),
                            ("Sail", 3), ("Whip", 3)):
            if word in name:
                return score
        return 2.5
    if role == "shot":
        if family not in ("deep", "dropback") or ends[prim] < 15.0:
            return 0.0
        deep = sum(1 for v in ends.values() if v >= 15.0)
        for word, score in (("Four Verts", 5), ("Verts", 5), ("Seams", 4.5), ("Seam", 4), ("Go", 4), ("Post", 3.5)):
            if word in name:
                return score + 0.2 * deep
        return 2.0 + 0.2 * deep
    return 0.0


# ---------------------------------------------------------------------------
# rule 1: no huddle
# ---------------------------------------------------------------------------

def nh_formations(doc: dict, catalog: dict) -> list[dict]:
    """Formations the No Huddle draws from, best first: shotgun 11 then 10 / 12 personnel non-special sets in book
    slot order (the page-one order: the team's most likely normal-down sets first), then every other non-special set."""
    rows = {f["formation"]: f for f in catalog["formations"]}

    def key(f):
        r = rows.get(f["custom_name"], {})
        special = r.get("tag") not in NH_FORM_TAGS or f["custom_name"] == "Gun Wildcat"
        pers = {"11": 0, "10": 1, "12": 2}.get(r.get("personnel"), 3)
        return (special, r.get("align") != "gun", pers, f.get("replace_index") if f.get("replace_index") is not None
                else 100 + doc["formations"].index(f))
    out = sorted(doc["formations"], key=key)
    return [f for f in out if rows.get(f["custom_name"], {}).get("tag") in NH_FORM_TAGS
            and f["custom_name"] != "Gun Wildcat"]


def formation_bonus(form: dict, catalog_row: dict) -> float:
    """Hurry-up sets: shotgun 11 personnel first (the base set: no substitution between snaps), then shotgun 10, other
    shotgun, pistol."""
    align, pers = catalog_row.get("align"), catalog_row.get("personnel")
    if align == "gun":
        return {"11": 3.0, "10": 2.0}.get(pers, 1.0)
    return 0.5 if align == "pistol" else 0.0


def pick_no_huddle(doc: dict, catalog: dict) -> list:
    """[(formation id, play id)] for NH_ROLES: role fit plus the formation bonus, then the formation's page-one
    rank and the play's menu position; no play twice."""
    rows = {r["play"]: r for r in catalog["plays"]}
    frows = {f["formation"]: f for f in catalog["formations"]}
    plays = {p["id"]: p for p in doc["plays"]}
    forms = nh_formations(doc, catalog)
    taken, out = set(), []
    for role in NH_ROLES:
        best = None
        for rank, f in enumerate(forms):
            bonus = formation_bonus(f, frows.get(f["custom_name"], {}))
            for pos, pid in enumerate(doc["menus"][f["id"]]):
                if pid in taken:
                    continue
                s = role_score(role, plays[pid], rows.get(pid, {}), f)
                if s <= 0:
                    continue
                key = (-(s + bonus), rank, pos)
                if best is None or key < best[0]:
                    best = (key, f["id"], pid)
        if best is None:
            raise SystemExit(f"{doc['book']['team']}: no play fits the No Huddle role {role}")
        taken.add(best[2])
        out.append([best[1], best[2]])
    return out


def fix_no_huddle(doc: dict, catalog: dict) -> list:
    want = pick_no_huddle(doc, catalog)
    if doc.get("no_huddle") == want:
        return []
    names = {p["id"]: p["custom_name"] for p in doc["plays"]}
    fnames = {f["id"]: f["custom_name"] for f in doc["formations"]}
    doc["no_huddle"] = want
    return [dict(entry=n, role=role, formation=fnames[f], play=names[p]) for n, (role, (f, p)) in
            enumerate(zip(NH_ROLES, want))]


# ---------------------------------------------------------------------------
# rule 2: quick game volume
# ---------------------------------------------------------------------------

def quick_ids(doc: dict, catalog: dict) -> set:
    rows = {r["play"]: r for r in catalog["plays"]}
    by_name = {f["custom_name"]: f for f in doc["formations"]}
    out = set()
    for p in doc["plays"]:
        row = rows.get(p["id"], {})
        home = by_name.get(row.get("home"))
        if home is not None and is_quick_game(p, home, row):
            out.add(p["id"])
    return out


def quick_share(doc: dict, quick: set) -> tuple[int, int]:
    links = [pid for m in doc["menus"].values() for pid in m]
    return sum(1 for pid in links if pid in quick), len(links)


def menu_floor_report(doc: dict, catalog: dict) -> dict:
    """{quick-game plays on a normal-down menu (4 = 4 or more): menus}, plus the book's quick-game link share."""
    quick = quick_ids(doc, catalog)
    hist = Counter(min(4, sum(1 for q in doc["menus"][fid] if q in quick)) for fid in floor_menus(doc, catalog))
    q, total = quick_share(doc, quick)
    return dict(menus={str(k): hist[k] for k in sorted(hist)}, records=len(quick), links=f"{q}/{total}")


#: Engine quick-game concepts a converted record may take (the book's least used first).
QUICK_CONCEPTS = ("Slant Flat", "Double Slants", "Quick Outs", "Spacing", "Stick", "Snag", "Whip Seam", "Y Pivot")
LETTERS = ("X", "Z", "Y", "U", "Slot", "RB", "FB", "RB2", "H")
SLOW_FAMILIES = ("dropback", "deep")            # links that may give way (weak_link)
CONVERT_FAMILIES = ("dropback", "deep", "pa")   # records that may become quick game (weak_record): 7-8 yd drops


def quick_floor(team: str, grades: dict | None = None) -> int:
    """Quick-game plays every non-special menu of this book lists at least."""
    return QUICK_MIN_WEAK if weak_line(team, grades) else QUICK_MIN


def floor_menus(doc: dict, catalog: dict) -> list[str]:
    """Menus the floor applies to, pass-first: the passing sets (catalog tag pass / spread / empty) and the base sets
    with 11 or 10 personnel; not goal line, short yardage, the wildcat set or the 12 / 21 / 22 personnel base sets."""
    rows = {f["formation"]: f for f in catalog["formations"]}
    order = {"spread": 0, "empty": 0, "pass": 1, "base": 2}
    out = []
    for f in doc["formations"]:
        row = rows.get(f["custom_name"], {})
        tag = row.get("tag")
        if tag == "base" and row.get("personnel") not in ("11", "10", "00"):
            continue
        if tag in order and f["custom_name"] != "Gun Wildcat":
            out.append((order[tag], f.get("replace_index") if f.get("replace_index") is not None else 99, f["id"]))
    return [fid for *_k, fid in sorted(out)]


def weak_link(doc: dict, catalog: dict, fid: str, uses: Counter, keep: set) -> int | None:
    """Menu position of a weak duplicate link in ``fid``: a dropback or deep pass (not a must-have, not in ``keep``)
    that another menu also lists, so the record stays in the book. Most widely listed first, then the concept
    repeated most in this menu, then the last position."""
    from pb.v2 import generator as gen
    rows = {r["play"]: r for r in catalog["plays"]}
    plays = {p["id"]: p for p in doc["plays"]}
    menu = doc["menus"][fid]
    bases = Counter(gen._concept_base(plays[q]["custom_name"]) for q in menu)
    best = None
    for pos, pid in enumerate(menu):
        r = rows.get(pid, {})
        if plays[pid].get("play_type") != "pass" or r.get("family") not in SLOW_FAMILIES or r.get("must") \
                or pid in keep or uses[pid] < 2:
            continue
        key = (-uses[pid], -bases[gen._concept_base(plays[pid]["custom_name"])], -pos)
        if best is None or key < best[0]:
            best = (key, pos)
    return None if best is None else best[1]


def weak_record(doc: dict, catalog: dict, fid: str, uses: Counter, keep: set) -> str | None:
    """A record listed only in ``fid`` that may become a quick-game play: a dropback, deep or play-action pass (not a
    must-have, not in ``keep``) whose concept another record of the book still carries (no concept leaves the book)."""
    from pb.v2 import generator as gen
    rows = {r["play"]: r for r in catalog["plays"]}
    plays = {p["id"]: p for p in doc["plays"]}
    groups = Counter()
    for p in doc["plays"]:
        r = rows.get(p["id"], {})
        if p.get("play_type") in ("pass", "pa_pass") and r.get("family") in CONVERT_FAMILIES:
            groups[gen._concept_base(p["custom_name"])] += 1
    out = []
    for pos, pid in enumerate(doc["menus"][fid]):
        r = rows.get(pid, {})
        if plays[pid].get("play_type") not in ("pass", "pa_pass") or r.get("family") not in CONVERT_FAMILIES \
                or r.get("must") \
                or pid in keep or uses[pid] != 1 or groups[gen._concept_base(plays[pid]["custom_name"])] < 2:
            continue
        out.append((-groups[gen._concept_base(plays[pid]["custom_name"])], -pos, pid))
    return min(out)[2] if out else None


def _design_problem(form: dict, design, flags: int, route_check=None) -> str | None:
    """The generator's candidate checks (``generator.Checker``) on pack geometry: the retail validator, no route
    reversal, no back-flat or execution repair needed, lint clean, and (with ``route_check``) the native route
    initializer finds no collision, stacked landmark or out-of-bounds route."""
    from mod_editor.core import nfl2k5_play_codec as codec
    from mod_editor.core import nfl2k5_play_library as lib
    from mod_editor.core import nfl2k5_playbook_lint as lint
    from mod_editor.core import nfl2k5_route_reversal as rr
    from pb.v2 import sanity_b778 as sanity
    try:
        enc = [[n.to_bytes() for n in codec.encode_chain(c)] for c in design.chains]
    except Exception as exc:  # noqa: BLE001
        return f"encode: {exc}"
    if any(len(e) > 15 or not e for e in enc):
        return "chain length"
    asg = [(0, e) for e in enc]
    try:
        for i in range(11):
            asg[i] = (codec.build_descriptor(flags, asg, i, 0), asg[i][1])
        codec.validate_sync(asg)
        err = codec.validate_play(flags, asg)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    if err:
        return "validator: " + err
    ctx = _ctx(form)
    for q in ctx.players:
        if q.slot != design.primary and design.chains[q.slot] and rr.reversals(q.z, design.chains[q.slot]):
            return f"route reversal in slot {q.slot}"
    pos = [(float(x), float(z)) for x, z in form["slot_positions"]]
    codes = list(form["position_codes"])
    _flats, repaired = lib.forward_back_flats(design.chains, pos, codes)
    if repaired:
        return "needs back-flat repair"
    fixed, _ = lint.normalize_offense_play(pos, codes, design.chains)
    if fixed is not None:
        return "needs execution repair"
    play = dict(custom_name=design.name, play_type="pass", play_flags=flags,
                assignments=[[[int(n[0]), list(n[1])] for n in ch] for ch in design.chains])
    if not sanity.lint_clean(form, play):
        return "lint"
    if route_check is not None and not route_check(form, play):
        return "route check"
    return None


def _quick_donor(doc: dict, catalog: dict) -> dict:
    """Header donor of the book's quick-game records (catalog header ``quick``): their retail donor and flags."""
    rows = {r["play"]: r for r in catalog["plays"]}
    for p in doc["plays"]:
        if rows.get(p["id"], {}).get("header") == "quick" and p.get("play_type") == "pass":
            return p["donor"]
    raise SystemExit(f"{doc['book']['team']}: no quick-header record to take the header from")


def quick_designs(form: dict, order: list[str]):
    """Engine quick-game designs for ``form`` (pack slot order), concepts in ``order``."""
    from mod_editor.core import nfl2k5_offense_concepts as oc
    from mod_editor.core import nfl2k5_offense_modern as om
    ctx = _ctx(form)
    codes = form["position_codes"]
    for name in order:
        try:
            d = oc.design(name, ctx)
        except oc.ConceptUnavailable:
            continue
        oc.fill_unassigned(ctx, d)
        if any(not ch for ch in d.chains) or d.play_type != "pass" or d.header != "quick":
            continue
        who = om.letter(codes[d.primary]) if d.primary is not None else ""
        if who and not d.name.startswith(("PA", "Y ", "Mesh", "Four")):
            d.name = f"{who} {d.name}"
        d.name = om.rb_name(d.name)[:40]
        yield name, d


def convert_record(doc: dict, catalog: dict, pid: str, fid: str, route_check=None) -> dict | None:
    """Turn record ``pid`` (listed only in ``fid``) into an engine quick-game design built in that formation, in
    place: same id, record slot and menu position. The concept must be new to that menu (the book's least used
    quick concept first), the design must pass ``_design_problem`` and ``is_quick_game`` and differ from every
    record of the book."""
    from pb.v2 import generator as gen
    from mod_editor.core import nfl2k5_offense_modern as om
    from pb.v2 import build as v2
    rows = {r["play"]: r for r in catalog["plays"]}
    plays = {p["id"]: p for p in doc["plays"]}
    form = next(f for f in doc["formations"] if f["id"] == fid)
    frows = {f["formation"]: f for f in catalog["formations"]}
    donor = _quick_donor(doc, catalog)
    used = Counter()
    for p in doc["plays"]:
        for c in QUICK_CONCEPTS:
            if c in p["custom_name"] or c == (p.get("concept") or ""):
                used[c] += 1
    order = sorted(QUICK_CONCEPTS, key=lambda c: (used[c], QUICK_CONCEPTS.index(c)))
    in_menu = {gen._concept_base(plays[q]["custom_name"]) for q in doc["menus"][fid] if q != pid}
    keys = {v2.chain_key([[(int(n[0]), tuple(n[1])) for n in ch] for ch in p["assignments"]]) for p in doc["plays"]}
    names = Counter(p["custom_name"] for p in doc["plays"]) + Counter(f["custom_name"] for f in doc["formations"])
    old_name = plays[pid]["custom_name"]
    freed = len(old_name) + 1 if names[old_name] == 1 else 0
    for concept, d in quick_designs(form, order):
        if gen._concept_base(d.name) in in_menu or any(concept in plays[q]["custom_name"]
                                                       for q in doc["menus"][fid] if q != pid):
            continue
        # the book's name pool is nearly full (20 to 40 UTF-16 units free once the defense is in): names are
        # interned, so a new name costs nothing when the book already has it and otherwise must fit in what the old
        # name frees plus what earlier conversions in this book saved (doc["_pool_credit"])
        credit = doc.get("_pool_credit", 0) + freed
        bare = d.name.split(" ", 1)[1] if " " in d.name and d.name.split(" ", 1)[0] in LETTERS else d.name
        options = [d.name, f"{doc['book']['team']} {bare}", bare]
        options += sorted(n for n in names if n.endswith(" " + bare) and n.split(" ", 1)[0] == d.name.split(" ", 1)[0])
        pick = next((n for n in options if (0 if names[n] else len(n) + 1) <= credit and len(n) <= 40), None)
        if pick is None:
            continue
        d.name = pick
        doc["_pool_credit"] = credit - (0 if names[pick] else len(pick) + 1)
        flags = v2.header_word(int(donor["flags"]), d.preference)
        assignments = [[[int(n[0]), list(n[1])] for n in ch] for ch in d.chains]
        play = dict(custom_name=d.name, play_type="pass", play_flags=flags, assignments=assignments)
        if not is_quick_game(play, form, {"family": "quick"}):
            continue
        if v2.chain_key(d.chains) in keys or _design_problem(form, d, flags, route_check):
            continue
        old = plays[pid]
        was = old["custom_name"]
        old.update(custom_name=d.name, play_type="pass", concept=d.concept, donor=dict(donor), play_flags=flags,
                   assignments=assignments)
        new_row = dict(play=pid, play_index=old.get("replace_index"), name=d.name, concept=d.concept,
                       family="quick", header="quick", play_type="pass",
                       personnel=frows.get(form["custom_name"], {}).get("personnel"), home=form["custom_name"],
                       primary=om.letter(form["position_codes"][d.primary]) if d.primary is not None else None,
                       screen=None, must="", routes=sorted(gen._route_names(d)), deep=False, lane=None,
                       formations=[form["custom_name"]], added_by="b778 pb7")
        row = rows.get(pid)
        if row is not None:
            row.clear()
            row.update(new_row)
        else:
            catalog["plays"].append(new_row)
        return dict(record=pid, was=was, now=d.name, concept=concept)
    return None


def quick_menus(doc: dict, catalog: dict, floor: int, checker=None) -> list:
    """Bring every normal-down menu (``floor_menus``) up to ``floor`` quick-game plays without changing any count:
    a weak duplicate link (``weak_link``) gives way to a quick-game record of the book that passes the generator's
    sharing rules there (pb5 ``refill_candidates``: same personnel, route runners keep their alignment class, no
    near duplicate, lint clean, no reversal, native route check), in the same menu position; failing that, a weak
    duplicate record listed only in this menu becomes a new quick-game design (``convert_record``)."""
    from pb.v2 import sanity_b778 as sanity
    forms = {f["id"]: f for f in doc["formations"]}
    plays = {p["id"]: p for p in doc["plays"]}
    keep = {pid for _f, pid in doc.get("no_huddle", [])}
    changes = []
    for fid in floor_menus(doc, catalog):
        quick = quick_ids(doc, catalog)
        while sum(1 for q in doc["menus"][fid] if q in quick) < floor:
            uses = Counter(pid for menu in doc["menus"].values() for pid in menu)
            pos = weak_link(doc, catalog, fid, uses, keep)
            cands = [] if pos is None else \
                [q for q in sanity.refill_candidates(doc, catalog, fid, uses, checker) if q in quick]
            if pos is not None and cands:
                out = doc["menus"][fid][pos]
                doc["menus"][fid][pos] = cands[0]
                changes.append(dict(formation=forms[fid]["custom_name"], kind="link", position=pos,
                                    was=plays[out]["custom_name"], now=plays[cands[0]]["custom_name"]))
                continue
            pid = weak_record(doc, catalog, fid, uses, keep)
            conv = convert_record(doc, catalog, pid, fid, checker) if pid else None
            if conv is not None:
                conv.update(formation=forms[fid]["custom_name"], kind="record",
                            position=doc["menus"][fid].index(pid))
                changes.append(conv)
                quick = quick_ids(doc, catalog)
                continue
            moved = relocate_record(doc, catalog, fid, pos, uses, keep, quick, floor, checker) \
                if pos is not None else None
            if moved is None:
                break
            changes.append(moved)
            quick = quick_ids(doc, catalog)
    return changes


def relocate_record(doc: dict, catalog: dict, fid: str, pos: int, uses: Counter, keep: set, quick: set, floor: int,
                    checker=None) -> dict | None:
    """No quick-game record of the book may join ``fid`` and none of its own records may convert: a weak duplicate
    record listed in exactly one OTHER menu becomes a quick-game design built in ``fid`` and takes the weak link at
    ``pos``; its old menu position gets the first pass the pb5 refill rules allow there (``refill_candidates``), so
    every menu keeps its length. Old menus that already meet the floor are used first; goal line, short yardage and
    wildcat menus are never touched."""
    from pb.v2 import sanity_b778 as sanity
    forms = {f["id"]: f for f in doc["formations"]}
    plays = {p["id"]: p for p in doc["plays"]}
    rows = {f["formation"]: f for f in catalog["formations"]}
    options = []
    for other in doc["menus"]:
        name = forms[other]["custom_name"]
        if other == fid or rows.get(name, {}).get("tag") not in NH_FORM_TAGS or name == "Gun Wildcat":
            continue                                  # goal line, short yardage and wildcat menus stay as they are
        rid = weak_record(doc, catalog, other, uses, keep)
        if rid is None:
            continue
        spare = sum(1 for q in doc["menus"][other] if q in quick) - floor
        options.append((spare < 1, rid, other))
    for _bad, rid, other in sorted(options):
        rpos = doc["menus"][other].index(rid)
        trial = {k: list(v) for k, v in doc["menus"].items()}
        trial_doc = dict(doc, menus=trial)
        trial[other].remove(rid)
        use2 = Counter(p for m in trial.values() for p in m)
        refill = [q for q in sanity.refill_candidates(trial_doc, catalog, other, use2, checker)
                  if q != rid and plays[q].get("play_type") in ("pass", "pa_pass")]   # a pass gives way to a pass
        if not refill:
            continue
        was = plays[rid]["custom_name"]
        out_pid = doc["menus"][fid][pos]
        conv = convert_record(doc, catalog, rid, fid, checker)
        if conv is None:
            continue
        doc["menus"][other][rpos] = refill[0]
        doc["menus"][fid][pos] = rid
        conv.update(formation=forms[fid]["custom_name"], kind="relocated", position=pos,
                    replaced_link=plays[out_pid]["custom_name"], was=was, from_formation=forms[other]["custom_name"],
                    from_position=rpos, refill=plays[refill[0]]["custom_name"])
        return conv
    return None


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def fix_doc(doc: dict, catalog: dict, rules=RULES, checker=None, grades=None) -> dict:
    out = {}
    if "quick" in rules:
        out["quick"] = quick_menus(doc, catalog, quick_floor(doc["book"]["team"], grades), checker)
    if "no_huddle" in rules:
        out["no_huddle"] = fix_no_huddle(doc, catalog)
    return out


def main(argv=None) -> int:
    from mod_editor.core import nfl2k5_playbook_pack as packs
    from pb.v2 import generator as gen
    from pb.v2 import sanity_b778 as sanity
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rule", action="append", choices=RULES)
    ap.add_argument("--team", action="append")
    ap.add_argument("--json", type=Path, help="write the per-team change list here")
    ap.add_argument("--xbe", type=Path, help="retail default.xbe: native route check for added links")
    args = ap.parse_args(argv)
    if args.check == args.apply:
        ap.error("pass exactly one of --check / --apply")
    rules = tuple(args.rule or RULES)
    if "quick" in rules and args.xbe is None:
        ap.error("the quick rule needs --xbe (the native route check decides which pairings may be linked)")
    grades = ol_grades()
    manifest = json.loads((ROOT / "pb/v2/manifest.json").read_text())
    checker = sanity.native_route_checker(args.xbe) if args.xbe and "quick" in rules else None
    totals, report = Counter(), {}
    for row in manifest["teams"]:
        if args.team and row["team"] not in args.team:
            continue
        path = ROOT / row["pack"]
        doc = json.loads(path.read_text(encoding="utf-8"))
        catp = ROOT / "pb/v2/catalogs" / f"{row['team']}.json"
        cat = json.loads(catp.read_text(encoding="utf-8"))
        before = menu_floor_report(doc, cat)
        changes = fix_doc(doc, cat, rules, checker, grades)
        changes["quick_menus"] = dict(weak_line=weak_line(row["team"], grades), floor=quick_floor(row["team"], grades),
                                      before=before, after=menu_floor_report(doc, cat))
        report[row["team"]] = changes
        for k in rules:
            totals[k] += len(changes.get(k) or [])
        if args.check or not any(changes.get(r) for r in rules):
            continue
        doc.pop("_pool_credit", None)
        pack = packs.loads_pack(json.dumps(doc))
        packs.save_pack(pack, path)
        sanity._update_catalog(cat, doc)
        catp.write_text(json.dumps(cat, indent=1) + "\n", encoding="utf-8", newline="\n")
        row["links"] = sum(len(m) for _f, m in pack.menus)
        row["semantic_sha256"] = gen.semantic_digest(packs.loads_pack(pack.dumps()))
    if args.apply and any(totals.values()):
        (ROOT / "pb/v2/manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8",
                                                    newline="\n")
        league = json.loads((ROOT / "pb/league_manifest.json").read_text())
        by = {r["team"]: r for r in manifest["teams"]}
        for r in league["teams"]:
            if r["team"] in by:
                r["semantic_sha256"] = by[r["team"]]["semantic_sha256"]
        (ROOT / "pb/league_manifest.json").write_text(json.dumps(league, indent=2) + "\n", encoding="utf-8",
                                                      newline="\n")
    if args.json:
        args.json.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(dict(totals))
    return 1 if args.check and any(totals[r] for r in rules) else 0


if __name__ == "__main__":
    raise SystemExit(main())
