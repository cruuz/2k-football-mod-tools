#!/usr/bin/env python3
"""Every offense formation lists a run and a pass (b780 plays2, Q18).

HUNT8 (11/03, confirmed offline, shipped since before v0.8): 94 SOFTDRINK offensive formations in the 32 team books had
no CPU-callable run play and 28 (Full House, Full House Sneak, Wing T) had no pass play.  Retail has one run-less
set per book besides the Hail Mary set ("Gun: Straight" and "Gun: Straight Trips" in two books) and no pass-less set.
The native play lottery 0x2096A0 picks the play type from the CPU's run share r, then a play of that type from the
formation's menu; a formation with no play of the wanted type returns whatever it has.  At r = 1.0 (the CPU burning the
clock) a run-less formation therefore returned ONE fixed pass every time (BAL Singleback Ace "U Out Seam" 40 of 40,
Pistol Wing "PA Z Curl Combo" 40 of 40); retail commits 100 of 100 runs.  On the v0.9 RC XBE, BAL's full commit
(category, formation, play) at r = 1.0 was 88 runs and 12 passes in 100.

The books are at their format limits (270 of 270 play records, 50 of 50 formations, 7 to 85 free name-pool units), so
the fix is menu LINKS only: no record is added, rewritten or renamed.  Each short formation takes one whole page
(three links, the menu page rule) of records the book already lists in a sister formation (same slot kinds and
position codes), chosen by the generator's own sharing rules (``sanity_b778.share_fits``) and, where those find nothing
for a run, by a backfield tolerance of ``RUN_BACK_YD`` with the same quarterback alignment (QB runs keep it):

* every link is lint clean as authored and as the Studio compiler writes it, needs no execution repair and no back-flat
  repair, and the play's other links keep their as-built chains;
* passes also pass the native route initializer (collide / stack / out of bounds) when ``--xbe`` is given and the
  routes do not turn round from the new spots;
* menus stay a multiple of three and at most 36 links (9 for the generator's slot-rule sets): when a page does not fit
  or a candidate is missing, the same number of links of the other kind that another menu also lists give way;
* no link of a No Huddle play is dropped; the first three entries (the default audibles) follow ``order_menu``.

    python3 pb/v2/run_pass_floor.py --check [--xbe XBE]     # exit 1 while any formation lacks a run or a pass
    python3 pb/v2/run_pass_floor.py --apply [--xbe XBE]     # rewrite the menus, catalogs and both manifests
    python3 pb/v2/run_pass_floor.py --csv OUT.csv           # the links that would be (or were) added, one row each

The generator calls ``fix_doc`` on every pack it builds (``pb/v2/generator.build_league``), so a regeneration cannot
bring the defect back; the lint codes FORMATION_NO_RUN / FORMATION_NO_PASS (``nfl2k5_playbook_lint``) fail
``verify3`` if a book ever does.  A changed offense changes the book bytes: regenerate the defense packs and the pins
after it (``python3 pb/v2/defense/regen.py --workers 2``, then ``python3 packaging/repin.py --apply --include-tests``).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_lint as lint  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from pb.v2 import sanity_b778 as sanity  # noqa: E402

PAGE = 3
MENU_MAX = 36                       # links per formation (the native 9-bit link ids)
SLOT_RULE_CAP = 9                   # generator.SLOT_RULE_MENU_CAP: slot-rule sets keep short menus
CARRIER_YD = (2.0, 3.5, 3.5, 5.0)   # carrier displacement allowed at fit tier 0..3 (the generator's own rule is 2 yd)
QB_ALIGN_YD = 3.5                   # quarterback displacement allowed when the alignment class differs (tiers 2, 3)
RUN_USES_MAX = 13                   # SHARE_CAP_B777 run (12) plus the repair loops' one extra
PASS_USES_MAX = 10
YD = sanity.YD_CM
WR, TE, HB, FB, QB = 9, 8, 10, 11, 0
RUN_QB = ("keeper",)                # QB draw / keep / power: shared only into the same QB alignment
NEVER_SHARED = ("direct_snap", "sneak", "reverse", "flea", "special")
TAKE_HANDOFF = 0x16
PRIORITY_HEAVY = {"pa": 0, "quick": 1, "boot": 2, "rollout": 3, "screen": 4, "dropback": 5, "deep": 6}
PRIORITY_OPEN = {"quick": 0, "dropback": 1, "pa": 2, "screen": 3, "boot": 4, "rollout": 5, "deep": 6}
LEVELS = (0, 1, 2)                  # 0 = the generator's rules, 1 = near-duplicates and adjacent alignments allowed,
                                    # 2 = QB runs into back sets, code-bit-only passes, carrier up to 5 yd


def kind_of(flags: int) -> str:
    """The native lottery's own split: 0x8000 is a run, 0x2000 a pass (PLAY header flags, word at +4)."""
    return "run" if flags & 0x8000 else ("pass" if flags & 0x2000 else "other")


def kinds(form: dict) -> tuple:
    return tuple(c & 31 for c in form["position_codes"])


def qb_xz(form: dict) -> tuple:
    return next((x / YD, z / YD) for (x, z), c in zip(form["slot_positions"], form["position_codes"]) if c & 31 == QB)


def menu_kinds(doc: dict, menu) -> Counter:
    plays = {p["id"]: p for p in doc["plays"]}
    return Counter(kind_of(int(plays[p]["play_flags"])) for p in menu)


def short_formations(doc: dict) -> list:
    """[(formation id, 'run' | 'pass')] for every menu without a play of that kind."""
    out = []
    for fid, menu in doc["menus"].items():
        got = menu_kinds(doc, menu)
        out.extend((fid, k) for k in ("run", "pass") if not got[k])
    return out


# ---------------------------------------------------------------------------
# fit of a run in another formation
# ---------------------------------------------------------------------------

def carrier_slots(play: dict) -> list:
    return [i for i, ch in enumerate(play["assignments"]) if any(int(n[0]) == TAKE_HANDOFF for n in (ch or []))]


def run_fit(play: dict, row: dict, ref: dict, form: dict) -> dict | None:
    """How well a run that works in ``ref`` suits ``form``: same slot kinds; a handoff run needs its carrier to stand
    in the backfield within a few yards of where he stands in ``ref``; a QB run needs the same quarterback alignment.
    Returns the distances in yards, or None when it cannot be shared at all."""
    ptype = play.get("play_type")
    if ptype in NEVER_SHARED or kinds(ref) != kinds(form):
        return None
    qb_run = ptype in RUN_QB or row.get("family") == "qb"
    same_align = sanity.qb_alignment(ref) == sanity.qb_alignment(form)
    (rx, rz), (fx, fz) = qb_xz(ref), qb_xz(form)
    qb_yd = math.hypot(rx - fx, rz - fz)
    if not same_align and qb_yd > QB_ALIGN_YD:
        return None
    if qb_run:
        if not same_align or len(sanity.backs(ref)) != len(sanity.backs(form)):
            return None                              # the draw's backs block from the backfield: an empty set designs its own
        car_yd = 0.0
    else:
        cars = carrier_slots(play)
        if not cars:
            return None
        if any(form["slot_positions"][s][1] > sanity.BACK_DEPTH_CM for s in cars):
            return None                              # the carrier must stand in the backfield here too
        car_yd = max(math.hypot(form["slot_positions"][s][0] - ref["slot_positions"][s][0],
                                form["slot_positions"][s][1] - ref["slot_positions"][s][1]) / YD for s in cars)
    return dict(same_align=same_align, exact=ref["position_codes"] == form["position_codes"],
                back_yd=round(car_yd, 2), qb_yd=round(qb_yd, 2), qb_run=qb_run)


def fit_tier(fit: dict) -> int:
    """0 = within the generator's own 2 yd rule, 1 = 3.5 yd with the same alignment, 2 = 3.5 yd across adjacent
    alignments (gun / pistol / under centre), 3 = up to 5 yd."""
    if fit["same_align"] and fit["exact"] and fit["back_yd"] <= CARRIER_YD[0] and fit["qb_yd"] <= 1.0:
        return 0
    if fit["same_align"] and fit["back_yd"] <= CARRIER_YD[1]:
        return 1
    if fit["back_yd"] <= CARRIER_YD[2]:
        return 2
    return 3 if fit["back_yd"] <= CARRIER_YD[3] else 9


def as_built_ok(doc: dict, fid: str, pid: str) -> bool:
    """Linking ``pid`` into ``fid`` leaves the play as the compiler writes it for the formations that already list it
    (``normalize_shared_offense_play``), and needs no repair of its own in the new formation."""
    forms = {f["id"]: f for f in doc["formations"]}
    play = next(p for p in doc["plays"] if p["id"] == pid)
    chains = [[(int(n[0]), list(n[1])) for n in (a or [])] for a in play["assignments"]]
    members = [forms[g] for g, m in doc["menus"].items() if pid in m]
    new = forms[fid]

    def geom(f):
        return [(float(x), float(z)) for x, z in f["slot_positions"]], list(f["position_codes"])

    pos, codes = geom(new)
    flats, repaired = lib.forward_back_flats(chains, pos, codes)
    if repaired:
        return False
    fixed, _ = lint.normalize_offense_play(pos, codes, chains)
    if fixed is not None:
        return False
    try:
        before = lint.normalize_shared_offense_play([geom(f) for f in members], chains)[0]
        after = lint.normalize_shared_offense_play([geom(f) for f in members] + [geom(new)], chains)[0]
    except lint.SharedPlayConflict:
        return False
    return lint._as_bytes(after if after is not None else chains) == lint._as_bytes(before if before is not None else chains)


# ---------------------------------------------------------------------------
# candidates
# ---------------------------------------------------------------------------

def sort_key(c: dict) -> tuple:
    """Best first: closest fit, then records another menu also lists (a record only one menu lists is that menu's own
    and the converter's raw material), then the least shared, then catalog order."""
    return (c["tier"], c["prio"], c["uses"] == 1, c["back_yd"] + c["qb_yd"], c["uses"], c["order"])


def candidates(doc: dict, cat: dict, fid: str, need: str, uses: Counter, *, level: int = 0, no_own: bool = False) -> list:
    """Records of this book that may join the menu of ``fid`` as a ``need`` play at this strictness level, best first
    (the native route check of a pass runs afterwards, on the head of this list: ``accept``).

    Each row: dict(pid, name, concept, play_type, family, home, tier, back_yd, qb_yd, exact, uses, level)."""
    forms = {f["id"]: f for f in doc["formations"]}
    by_name = {f["custom_name"]: f for f in doc["formations"]}
    plays = {p["id"]: p for p in doc["plays"]}
    rows = {r["play"]: r for r in cat["plays"]}
    form, menu = forms[fid], doc["menus"][fid]
    tag = next((r.get("tag") for r in cat["formations"] if r["formation"] == form["custom_name"]), "base")
    names_in_menu = {plays[p]["custom_name"] for p in menu}
    screens = sum(1 for p in menu if "screen" in plays[p]["custom_name"].casefold())
    has_back = bool(sanity.backs(form))
    out = []
    for n, (pid, row) in enumerate(rows.items()):
        p = plays.get(pid)
        if p is None or pid in menu or row.get("home") not in by_name or uses[pid] < (2 if no_own else 1):
            continue
        if kind_of(int(p["play_flags"])) != need or p.get("play_type") == "special":
            continue
        name = p["custom_name"]
        if name in names_in_menu:
            continue
        home = by_name[row["home"]]
        listed = [forms[g] for g, m in doc["menus"].items() if pid in m]
        refs = [home] + [g for g in listed if g is not home]
        if need == "pass":
            if "screen" in name.casefold() and screens >= sanity.MAX_SCREENS:
                continue
            concept = (p.get("concept") or "") + " " + name
            if "Mesh" in concept or "Vert" in concept:
                continue
            if uses[pid] >= PASS_USES_MAX and level < 2:
                continue
            near = listed if level == 0 else []              # level 1: a near-duplicate picture is still a pass
            ref = next((g for g in refs if sanity.share_fits(p, row, g, form, near)), None)
            if ref is None and level >= 2:
                ref = next((g for g in refs if _pass_fits_relaxed(p, row, g, form)), None)
            if ref is None:
                continue
            if sanity.reverses_in(form, p) or not sanity.lint_clean(form, p):
                continue
            fit = dict(same_align=True, exact=ref["position_codes"] == form["position_codes"], back_yd=0.0, qb_yd=0.0)
            tier = level
            prio = (PRIORITY_HEAVY if tag in ("goal", "short") else PRIORITY_OPEN).get(row.get("family"), 9)
        else:
            if uses[pid] >= RUN_USES_MAX and level < 2:
                continue
            fits = [(fit_tier(f), f["back_yd"] + f["qb_yd"], f) for f in (run_fit(p, row, g, form) for g in refs) if f is not None]
            fits = [t for t in fits if t[0] <= (1 if level == 0 else 2 if level == 1 else 3)]
            if not fits:
                continue
            tier, _d, fit = min(fits, key=lambda t: (t[0], t[1]))
            if level < 2 and fit["qb_run"] == has_back:
                continue                      # backs run handoffs; only a back-less set takes QB runs before level 2
            if not sanity.lint_clean(form, p):
                continue
            prio = 0
        if not as_built_ok(doc, fid, pid):
            continue
        out.append(dict(pid=pid, name=name, concept=p.get("concept") or name, play_type=p.get("play_type"),
                        family=row.get("family"), home=row["home"], tier=tier, back_yd=fit["back_yd"],
                        qb_yd=fit["qb_yd"], exact=fit["exact"], uses=uses[pid], order=n, prio=prio, level=level))
    out.sort(key=sort_key)
    return out


def _pass_fits_relaxed(play: dict, row: dict, home: dict, form: dict) -> bool:
    """Level 2 for a pass: the slots line up by kind (position codes may differ in a mirror / ordinal bit), a non-featured
    route runner may change alignment class even to or from the backfield (a TE who stands in the backfield of a full
    house runs the same flat), at most two of them, the featured receiver and the QB never; play-action boots and plays
    named for their alignment keep the generator's rules.  The lint, the reversal check and the native route check still
    apply to the link."""
    if kinds(home) != kinds(form) or play.get("play_type") not in ("pass", "pa_pass"):
        return False
    named = sanity.alignment_named(play["custom_name"])
    if named is not None and sanity.qb_alignment(form) != named:
        return False
    if sanity.is_pa_boot(play) and not sanity.backfield_compatible(home, form):
        return False
    primary = sanity._first_read(play)
    changed = 0
    for s in sanity._runner_slots(play):
        a, b = sanity._side_class(home, s), sanity._side_class(form, s)
        if a == b:
            continue
        if s == primary or s == 0:
            return False
        changed += 1
    return changed <= 2


def pick(cands: list, count: int) -> list:
    """The best ``count`` records, distinct in concept first (a page of three different runs), then by rank."""
    chosen, seen = [], set()
    for c in cands:
        if len(chosen) >= count:
            break
        if c["concept"] in seen:
            continue
        chosen.append(c)
        seen.add(c["concept"])
    for c in cands:
        if len(chosen) >= count:
            break
        if c not in chosen:
            chosen.append(c)
    return chosen


# ---------------------------------------------------------------------------
# one pack
# ---------------------------------------------------------------------------

def menu_cap(doc: dict, fid: str) -> int:
    from mod_editor.core import nfl2k5_offense_concepts as oc
    from pb.v2 import generator as gen
    name = next(f["custom_name"] for f in doc["formations"] if f["id"] == fid)
    spec = oc.FORMATIONS.get(name)
    return SLOT_RULE_CAP if spec is not None and gen.slot_rule_violations(spec) else MENU_MAX


def order_menu(doc: dict, cat: dict, fid: str) -> bool:
    """generator.order_menu on the pack: the first three entries are a run, a quick throw and a shot / play action
    (a run, a run and a quick throw in the goal-line, short-yardage and base sets).  Returns True when the order moved."""
    rows = {r["play"]: r for r in cat["plays"]}
    form = next(f for f in doc["formations"] if f["id"] == fid)
    tag = next((r.get("tag") for r in cat["formations"] if r["formation"] == form["custom_name"]), "base")
    menu = list(doc["menus"][fid])
    fam = {p: (rows.get(p) or {}).get("family") for p in menu}
    runs = [p for p in menu if fam[p] in ("run", "qb")]
    quick = [p for p in menu if fam[p] in ("quick", "screen")]
    shot = [p for p in menu if fam[p] in ("pa", "boot", "deep", "dropback", "rollout")]
    head = []
    lead = runs if tag in ("goal", "short", "base") else quick or shot
    for group in ((lead, runs, quick, shot) if tag in ("goal", "short", "base") else (lead, shot, runs, quick)):
        for p in group:
            if p not in head:
                head.append(p)
                break
        if len(head) >= 3:
            break
    new = head + [p for p in menu if p not in head]
    if new == menu:
        return False
    doc["menus"][fid] = new
    return True


class Checks:
    """The two native checks a link may need: the retail route initializer for a pass (collide / stack / out of bounds)
    and the native handoff exchange planner for a handoff run (the giver and the runner travel no more than retail's
    envelope to the meeting point).  Either is skipped when its XBE-backed machine is not available."""

    def __init__(self, route=None, plan=None):
        self.route, self.plan = route, plan

    def __call__(self, form: dict, play: dict) -> bool:
        if kind_of(int(play["play_flags"])) == "pass":
            return self.route is None or self.route(form, play)
        if self.plan is not None and play.get("play_type") == "run":
            return self.plan(form, play)
        return True


def native_checks(xbe) -> Checks:
    if not xbe or not Path(xbe).is_file():
        return Checks()
    from tools.b77 import p13_handoff_probe as probe
    callback = probe.native_plan_callback(Path(xbe).read_bytes())

    def plan(form: dict, play: dict) -> bool:
        chains = [list(codec.encode_chain([(n[0], tuple(n[1])) for n in (chain or [])])) for chain in play["assignments"]]
        view = lint.PlayView(-1, form["custom_name"], -1, play["custom_name"], int(play.get("play_flags") or 0),
                             [(float(x), float(z)) for x, z in form["slot_positions"]], list(form["position_codes"]), chains)
        return not lint.check_handoffs(lint.as_built(view), callback)

    return Checks(sanity.native_route_checker(xbe), plan)


def accept(doc: dict, fid: str, cands: list, checks, limit: int) -> list:
    """The first ``limit`` candidates that also pass the native checks, keeping the rank order."""
    if checks is None:
        return list(cands[:limit])
    form = next(f for f in doc["formations"] if f["id"] == fid)
    plays = {p["id"]: p for p in doc["plays"]}
    out = []
    for c in cands:
        if len(out) >= limit:
            break
        if not checks(form, plays[c["pid"]]):
            continue
        out.append(c)
    return out


def gather(doc: dict, cat: dict, fid: str, need: str, uses: Counter, route_check, want: int, exclude=(), no_own: bool = False) -> list:
    """Up to ``2 * want`` accepted candidates, taking stricter levels first and widening only while a page is missing."""
    pool = []
    for level in LEVELS:
        found = [c for c in candidates(doc, cat, fid, need, uses, level=level, no_own=no_own)
                 if all(c["pid"] != d["pid"] for d in pool) and c["pid"] not in exclude]
        pool += accept(doc, fid, found, route_check, 2 * want - len(pool))
        if len(pick(pool, want)) >= want and len(pool) >= want:
            break
    pool.sort(key=lambda c: (c["level"],) + sort_key(c))
    return pool


class Converter:
    """Last resort for a formation no sister record fits (the 20-odd shotgun empty sets whose only quarterback-run
    sisters are under-centre, and the full houses whose sisters all start their tight end on the line): one record
    that only this menu lists becomes the generator's own design for the formation, in place (same record id, replace
    index and menu position; the record count, the link count and the page rule do not move), as hurry_b778 does for
    quick game.  The design is a candidate of ``generator.candidates`` for the formation, so it passed the retail
    validator, the reversal check, the lint and (with an XBE) the native route initializer."""

    def __init__(self, retail: bytes, team: str, xbe=None, checker=None):
        import random
        from pb.v2 import build as v2
        from pb.v2 import generator as gen
        self.gen, self.v2, self.random = gen, v2, random
        self.team = team
        self.info = v2.BookInfo(retail, team)
        self.prof = gen.team_profile(team, "2020s")
        self.checker = checker or gen.Checker(xbe)
        self.cache: dict = {}

    def cands(self, fname: str) -> list:
        if fname not in self.cache:
            rng = self.random.Random(self.prof.seed ^ self.gen.stable_hash(fname))
            self.cache[fname] = self.gen.candidates(self.info, self.prof, fname, self.checker, rng)
        return self.cache[fname]


MUST_KEEP = ("tush", "sneak", "keep", "team")


def convert_records(doc: dict, cat: dict, fid: str, need: str, conv: Converter, count: int, quick: set = frozenset()) -> list:
    """Convert up to ``count`` records listed only in ``fid`` (of the other kind, never a must-have or a No Huddle play,
    never the last of that kind) into designs of kind ``need`` built for the formation.  Returns the change rows."""
    from mod_editor.core import nfl2k5_offense_concepts as oc
    from mod_editor.core import nfl2k5_offense_modern as om
    gen, v2 = conv.gen, conv.v2
    forms = {f["id"]: f for f in doc["formations"]}
    plays = {p["id"]: p for p in doc["plays"]}
    rows = {r["play"]: r for r in cat["plays"]}
    form = forms[fid]
    spec = oc.FORMATIONS[form["custom_name"]]
    canon = [tuple(p) for p in spec.positions_cm()]
    order = [canon.index(tuple(p)) for p in form["slot_positions"]]
    uses = Counter(p for m in doc["menus"].values() for p in m)
    menu = doc["menus"][fid]
    other = "pass" if need == "run" else "run"
    protected = {pid for f_, pid in doc.get("no_huddle", []) if f_ == fid}
    # nfl2k5_screen_timing pins each book's whole declared-screen signature (every play whose name holds "screen"): a
    # screen record changes only when it is the formation's only record to give, and then the book's screen pin is
    # regenerated (pb/v2/pins.py); no design takes a name with "screen" in it
    victims = [p for p in reversed(menu) if uses[p] == 1 and kind_of(int(plays[p]["play_flags"])) == other
               and p not in protected and p not in quick and (rows.get(p) or {}).get("must") not in MUST_KEEP]
    plain = [p for p in victims if "screen" not in plays[p]["custom_name"].casefold()]
    victims = plain or victims
    have_other = sum(1 for p in menu if kind_of(int(plays[p]["play_flags"])) == other)
    victims = victims[:max(0, min(count, have_other - 1))]
    has_back = bool(sanity.backs(form))
    tag = next((r.get("tag") for r in cat["formations"] if r["formation"] == form["custom_name"]), "base")
    if need == "run":
        fams = ("run", "qb") if has_back else ("qb",)
    else:
        fams = tuple(PRIORITY_HEAVY if tag in ("goal", "short") else PRIORITY_OPEN)
    ranked = sorted((c for c in conv.cands(form["custom_name"]) if c.family in fams and "screen" not in c.design.name.casefold()
                     and kind_of(
        v2.header_word(conv.info.header_donor(c.design.header)[2], c.design.preference)) == need),
        key=lambda c: (fams.index(c.family), -c.weight))
    # books differ: start each family's list at one of its three best designs, by a hash of the team and the set
    shift = gen.stable_hash(conv.team + form["custom_name"])
    grouped = []
    for fam in fams:
        group = [c for c in ranked if c.family == fam]
        r = shift % min(3, len(group)) if group else 0
        grouped += group[r:] + group[:r]
    ranked = grouped
    names = Counter(p["custom_name"] for p in doc["plays"]) + Counter(f["custom_name"] for f in doc["formations"])
    keys = {v2.chain_key([[(int(n[0]), tuple(n[1])) for n in ch] for ch in p["assignments"]]) for p in doc["plays"]}
    in_menu = {gen._concept_base(plays[q]["custom_name"]) for q in menu}
    done = []
    for pid in victims:
        old = plays[pid]
        for c in ranked:
            d = c.design
            if gen._concept_base(d.name) in in_menu:
                continue
            assignments = [[[int(op), list(vals)] for op, vals in ch] for ch in v2.to_book_order(d.chains, order)]
            if v2.chain_key([[(op, tuple(vals)) for op, vals in ch] for ch in assignments]) in keys:
                continue
            freed = len(old["custom_name"]) + 1 if names[old["custom_name"]] == 1 else 0
            credit = doc.get("_pool_credit", 0) + freed
            bare = d.name.split(" ", 1)[1] if d.name.split(" ", 1)[0] in ("X", "Z", "Y", "U", "HB", "RB", "FB", "Slot") and " " in d.name else d.name
            options = [om.rb_name(n)[:40] for n in (d.name, f"{conv.team} {bare}", bare)] + list(gen.name_variants(c))
            name = next((n for n in options if (0 if names[n] else len(n) + 1) <= credit and len(n) <= 40
                         and n not in {plays[q]["custom_name"] for q in menu if q != pid}), None)
            if name is None:
                continue
            donor_index, donor_name, donor_flags, donor_sig = conv.info.header_donor(d.header)
            flags = v2.header_word(donor_flags, d.preference)
            ptype = d.play_type if d.play_type in packs.PLAY_TYPES else "pass"
            was = old["custom_name"]
            doc["_pool_credit"] = credit - (0 if names[name] else len(name) + 1)
            names[was] -= 1
            names[name] += 1
            old.update(custom_name=name, play_type=ptype, concept=d.concept, play_flags=flags, assignments=assignments,
                       donor=dict(index=donor_index, name=donor_name, flags=donor_flags, signature=donor_sig))
            row = dict(play=pid, play_index=old.get("replace_index"), name=name, concept=d.concept, family=c.family,
                       header=d.header, play_type=ptype, personnel=spec.personnel, home=form["custom_name"],
                       primary=om.letter(c.primary_code) if c.primary_code is not None else None, screen=c.screen_type,
                       must="", routes=sorted(c.routes), deep=c.deep, lane=c.lane, formations=[form["custom_name"]],
                       added_by="b780 plays2")
            old_row = rows.get(pid)
            if old_row is not None:
                old_row.clear()
                old_row.update(row)
            else:
                cat["plays"].append(row)
            keys.add(v2.chain_key([[(op, tuple(vals)) for op, vals in ch] for ch in assignments]))
            in_menu.add(gen._concept_base(d.name))
            done.append(dict(pid=pid, name=name, was=was, concept=d.concept, play_type=ptype, home=form["custom_name"],
                             tier="designed", back_yd=0.0, qb_yd=0.0, exact=True, level="convert", kind=need))
            break
    return done


def fix_doc(doc: dict, cat: dict, route_check=None, converter: Converter | None = None) -> list:
    """Give every short menu of this pack the kind it lacks.  Returns [dict(formation, need, added, dropped, ...)]."""
    forms = {f["id"]: f for f in doc["formations"]}
    plays = {p["id"]: p for p in doc["plays"]}
    protected = {}
    for fid, pid in doc.get("no_huddle", []):
        protected.setdefault(fid, set()).add(pid)
    uses = Counter(p for m in doc["menus"].values() for p in m)
    changes = []
    from pb.v2 import hurry_b778 as hurry
    for fid, need in short_formations(doc):
        quick = hurry.quick_ids(doc, cat)          # pb7's floor: quick-game records never give way here
        form = forms[fid]
        menu = list(doc["menus"][fid])
        cap = menu_cap(doc, fid)
        other = "pass" if need == "run" else "run"
        pool = gather(doc, cat, fid, need, uses, route_check, PAGE)
        added = pick(pool, PAGE)
        status, detail = "ok", ""
        new, dropped = list(menu), []

        def droppable(exclude=()):
            """Links of the other kind another menu also lists, most shared first (never a No Huddle play, never a
            must-have, never the last of that kind)."""
            rows_ = {r["play"]: r for r in cat["plays"]}
            out_ = [p for p in sorted(menu, key=lambda q: -uses[q])
                    if kind_of(int(plays[p]["play_flags"])) == other and uses[p] >= 2 and p not in protected.get(fid, ())
                    and p not in quick and (rows_.get(p) or {}).get("must") not in MUST_KEEP and p not in exclude]
            keep = sum(1 for p in menu if kind_of(int(plays[p]["play_flags"])) == other)
            return out_[:max(0, keep - 1)]

        if not added:
            status = "NO CANDIDATE"
        elif len(added) >= PAGE:
            new = menu + [c["pid"] for c in added]
            if len(new) > cap:
                drop = droppable()
                dropped = drop[:len(new) - cap]
                new = [p for p in new if p not in dropped]
        else:
            # fewer than a page of fits: the same number of links of the other kind give way (the page rule holds), else
            # sister records of the other kind complete the page
            drop = droppable()
            if len(drop) >= len(added):
                dropped = drop[:len(added)]
                new = [p for p in menu if p not in dropped] + [c["pid"] for c in added]
            else:
                fill = gather(doc, cat, fid, other, uses, route_check, PAGE, exclude=set(menu), no_own=True)
                new = menu + [c["pid"] for c in added]
                filler = []
                for c in fill:
                    if len(new) % PAGE == 0:
                        break
                    filler.append(c)
                    new.append(c["pid"])
                added = added + filler
        if added and not (len(new) % PAGE == 0 and PAGE <= len(new) <= cap):
            status, detail = "PAGE", f"{len(menu)} links + {len(added)} - {len(dropped)} does not make a page (cap {cap})"
        if status != "ok":
            conv_rows = []
            if converter is not None:
                conv_rows = convert_records(doc, cat, fid, need, converter, 2 if len(menu) >= 6 and need == "run" else 1, quick)
            if conv_rows:
                changes.append(dict(formation=form["custom_name"], fid=fid, need=need, status="converted", added=conv_rows,
                                    dropped=[], links_before=len(menu), links_after=len(menu)))
            else:
                changes.append(dict(formation=form["custom_name"], fid=fid, need=need, added=[], dropped=[], status=status,
                                    detail=detail))
            continue
        for c in added:
            uses[c["pid"]] += 1
        for pid in dropped:
            uses[pid] -= 1
        doc["menus"][fid] = new
        order_menu(doc, cat, fid)
        changes.append(dict(formation=form["custom_name"], fid=fid, need=need, status=status,
                            added=[{k: c[k] for k in ("pid", "name", "concept", "play_type", "home", "tier", "back_yd", "qb_yd", "exact", "level")}
                                   | dict(kind=kind_of(int(plays[c["pid"]]["play_flags"]))) for c in added],
                            dropped=[dict(pid=p, name=plays[p]["custom_name"]) for p in dropped],
                            links_before=len(menu), links_after=len(new)))
    doc.pop("_pool_credit", None)
    return changes


def update_catalog(cat: dict, doc: dict) -> None:
    sanity._update_catalog(cat, doc)


# ---------------------------------------------------------------------------
# league driver
# ---------------------------------------------------------------------------

def team_docs(folder: Path, manifest: dict):
    for row in manifest["teams"]:
        yield row, folder / Path(row["pack"]).name


def write_manifests(manifest: dict) -> None:
    """pb/v2/manifest.json (links, semantic digest) and the league manifest's digests, as sanity_b778 writes them."""
    (ROOT / "pb/v2/manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    league = json.loads((ROOT / "pb/league_manifest.json").read_text(encoding="utf-8"))
    by = {r["team"]: r for r in manifest["teams"]}
    for r in league["teams"]:
        r["semantic_sha256"] = by[r["team"]]["semantic_sha256"]
    (ROOT / "pb/league_manifest.json").write_text(json.dumps(league, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--packs", type=Path, default=ROOT / "data/playbooks")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--xbe", type=Path, help="retail default.xbe: native route check of every added pass")
    ap.add_argument("--image", type=Path, help="retail XISO (default $NFL2K5_RETAIL_XISO): designs for formations no sister fits")
    ap.add_argument("--csv", type=Path, help="one row per added link")
    ap.add_argument("--json", type=Path, help="the full change list")
    ap.add_argument("--team", action="append")
    ap.add_argument("--refresh-manifests", action="store_true",
                    help="recompute links and semantic digests in pb/v2/manifest.json and pb/league_manifest.json from the packs")
    a = ap.parse_args(argv)
    a.packs = a.packs.resolve()
    xbe = a.xbe or (Path(os.environ["NFL2K5_RETAIL_XBE"]) if os.environ.get("NFL2K5_RETAIL_XBE") else None)
    route_check = native_checks(xbe)
    shipped = a.packs == (ROOT / "data/playbooks").resolve()
    image = a.image or (Path(os.environ["NFL2K5_RETAIL_XISO"]) if os.environ.get("NFL2K5_RETAIL_XISO") else None)
    from pb.v2 import generator as gen
    gen_checker = gen.Checker(xbe if xbe and Path(xbe).is_file() else None)
    opened = None
    if image is not None and Path(image).is_file():
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        opened = OuterImage(image).__enter__()
    manifest = json.loads((ROOT / "pb/v2/manifest.json").read_text(encoding="utf-8"))
    if a.refresh_manifests:
        for row in manifest["teams"]:
            pack = packs.load_pack(ROOT / row["pack"])
            row["links"] = sum(len(m) for _f, m in pack.menus)
            row["semantic_sha256"] = gen.semantic_digest(packs.loads_pack(pack.dumps()))
        write_manifests(manifest)
        print("manifests refreshed")
        return 0
    report, totals, csv_rows, touched = {}, Counter(), [], False
    for row, path in team_docs(a.packs, manifest):
        if a.team and row["team"] not in a.team:
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        catp = ROOT / "pb/v2/catalogs" / f"{row['team']}.json"
        cat = json.loads(catp.read_text(encoding="utf-8"))
        before = short_formations(doc)
        converter = Converter(opened.read_entry(BOOK_ENTRIES[row["team"]]), row["team"], checker=gen_checker) if opened else None
        changes = fix_doc(doc, cat, route_check, converter)
        after = short_formations(doc)
        report[row["team"]] = dict(short_before=len(before), short_after=len(after), changes=changes)
        totals["short_before"] += len(before)
        totals["short_after"] += len(after)
        for c in changes:
            totals[f"{c['need']}_formations"] += 1
            totals["links_added"] += len(c["added"])
            totals["links_dropped"] += len(c["dropped"])
            totals["status_" + c["status"]] += 1
            for ad in c["added"]:
                csv_rows.append(dict(team=row["team"], formation=c["formation"], need=c["need"], play_id=ad["pid"],
                                     play=ad["name"], old_play=ad.get("was", ""), concept=ad["concept"], play_type=ad["play_type"],
                                     home_formation=ad["home"], tier=ad["tier"], back_yd=ad["back_yd"],
                                     qb_yd=ad["qb_yd"], exact_codes=int(ad["exact"]), level=ad["level"],
                                     action=("converted" if ad["level"] == "convert" else "added" if ad["kind"] == c["need"]
                                             else "added (page filler, " + ad["kind"] + ")"),
                                     links_after=c.get("links_after", "")))
            for dr in c["dropped"]:
                csv_rows.append(dict(team=row["team"], formation=c["formation"], need=c["need"], play_id=dr["pid"],
                                     play=dr["name"], old_play="", concept="", play_type="", home_formation="", tier="", back_yd="",
                                     qb_yd="", exact_codes="", level="", action="dropped (listed in another menu)",
                                     links_after=c.get("links_after", "")))
        print(row["team"], f"short {len(before)} -> {len(after)}", f"{sum(len(c['added']) for c in changes)} links added,",
              f"{sum(len(c['dropped']) for c in changes)} dropped", flush=True)
        if a.apply and changes:
            pack = packs.loads_pack(json.dumps(doc))
            check = packs.check_pack(pack)
            if not check.ok:
                raise SystemExit(f"{row['team']}: {check.text()}")
            packs.save_pack(pack, path)
            touched = True
            if shipped:
                update_catalog(cat, doc)
                catp.write_text(json.dumps(cat, indent=1) + "\n", encoding="utf-8", newline="\n")
                row["links"] = sum(len(m) for _f, m in pack.menus)
                row["semantic_sha256"] = gen.semantic_digest(packs.loads_pack(pack.dumps()))
    if a.apply and touched and shipped:
        write_manifests(manifest)
    if a.csv:
        fields = ["team", "formation", "need", "play_id", "play", "old_play", "concept", "play_type", "home_formation", "tier",
                  "back_yd", "qb_yd", "exact_codes", "level", "action", "links_after"]
        with a.csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(csv_rows)
    if a.json:
        a.json.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("TOTAL", dict(totals))
    return 1 if (a.check and totals["short_before"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
