#!/usr/bin/env python3
"""SOFTDRINK 2K28 offense generator v3 (b776 job pb1): every team book unique, varied and full.

Builds one complete-offense pack per team from the modern catalog (``mod_editor/core/nfl2k5_offense_modern.py``
plus the base engine ``nfl2k5_offense_concepts``):

1. **Capacity.**  The pack replaces the book's ordinary offense and appends into its free records, leaving room
   for what the team's defense pack appends and for the PAT fake field goal: offense formations =
   50 - retained - defense appends, offense plays = 270 - retained - defense appends - 1.
2. **Formations.**  A team profile (era profile x Madden 27 family / personnel shares from
   ``pb/research/madden27_team_tree.json`` x the team package's real 2025 tendencies) weights every catalog set;
   must-have families are placed first (goal line sneak set, heavy, full house / wing-T, pistol, wildcat, empty
   under centre for the QB keep), then the rest by weight with a seeded draw, so every book differs.
3. **Personnel groups.**  Pistol sets get their own play-call group ("Pistol", 11 personnel) and the book may
   add 13 personnel ("Jumbo") and the second-back package ("Pony"); groups reuse spare stock records, else
   append (26 records at most); a set whose group cannot be placed is dropped.
4. **Candidates.**  Per formation: retail-template runs (both directions, every applicable scheme and carrier),
   combo pass calls sampled by team weights, the engine's named concepts, screens of each type, tricks and the
   QB runs.  Every candidate passes the retail validator, the playbook linter (no repairs needed) and the
   native route initializer check (no collisions or stacked landmarks) in its formation.
5. **Selection.**  Must-have plays first, then a greedy pick per formation scored by team weight, novelty of the
   concept, routes and route kinds league-unused so far, under-represented primary receivers and menu balance
   (one screen of each type per menu, two at most).  Picked records are then shared into sister formations of
   the same personnel when they pass the same checks there, filling menus to ``menu_target``.
6. **Era profile.**  ``--era 2010s`` reweights families (more under centre, I-form and 21/12 personnel, less
   pistol/empty) and limits the catalog to sets tagged for that era; the 2010-2019 bank job runs this unchanged.

DESIGN on PROVED OFFLINE grammar; nothing here is a gameplay witness.
"""
from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_offense_modern as om  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_lint as lint  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from pb.v2 import build as v2  # noqa: E402

TREE = ROOT / "pb" / "research" / "madden27_team_tree.json"
VERSION = "3.0.0"
YD = codec.YD_CM

# ---------------------------------------------------------------------------
# Era profiles (the engine's era parameter)
# ---------------------------------------------------------------------------

ERA_PROFILES = {
    "2020s": dict(label="2020+", family_scale={}, personnel_scale={}, catalog_era="2020s",
                  gun_bias=1.0, uc_bias=1.0),
    # A later job builds the 2010-2019 bank from this profile: more under centre, I-form and 21/12 personnel,
    # fewer pistol, empty and 10 personnel sets.  Team weights still come from the team tree.
    "2010s": dict(label="2010-2019", family_scale={"Pistol": 0.4, "Empty": 0.6, "Wildcat": 0.6, "I-Form": 1.8,
                                                   "Strong": 1.6, "Weak": 1.6, "Full House": 1.2, "Singleback": 1.3},
                  personnel_scale={"21": 1.6, "12": 1.2, "10": 0.6, "00": 0.6, "13": 0.8}, catalog_era="2010s",
                  gun_bias=0.65, uc_bias=1.5),
}

FAMILY_GROUP = {"Gun": "gun", "Empty": "gun", "Wildcat": "gun", "Pistol": "pistol", "Singleback": "singleback",
                "I-Form": "uc2", "Strong": "uc2", "Weak": "uc2", "Split Backs": "uc2", "Full House": "uc2",
                "Wing T": "uc2", "Heavy": "uc2", "Goal Line": "gl"}

# scheme weights by offensive family (DESIGN, from the research section 4 typical usage per tree)
RUN_WEIGHTS = {
    "wide_zone": {"Outside Zone": 3, "HB Stretch": 3, "Inside Zone": 2, "Inside Zone Split": 2.5, "Zone Toss": 2,
                  "HB Counter": 1, "Crack Toss": 1.2, "Lead Stretch": 1.2, "HB Draw": 1, "01 Trap": 0.6},
    "mcvay": {"Outside Zone": 3, "Inside Zone": 2, "Crack Toss": 2.5, "HB Stretch": 2, "HB Counter": 1.5,
              "Inside Zone Split": 1.5, "Zone Toss": 1.5, "HB Draw": 1},
    "power": {"Power G": 3, "Counter GT": 3, "HB Counter": 2.5, "HB Dive": 2, "HB Iso": 2.5, "01 Trap": 1.5,
              "Pin Pull Sweep": 2, "HB Sweep": 1.5, "HB Off Tackle": 2, "HB Slam": 1.5, "Inside Trap": 1.5},
    "west_coast": {"Inside Zone": 2.5, "HB Draw": 2, "01 Trap": 1.5, "HB Counter": 1.5, "HB Dive": 1.5,
                   "Outside Zone": 1.5, "HB Toss": 1.2, "HB Iso": 1.2},
    "spread": {"Inside Zone": 2.5, "HB Draw": 2.5, "01 Trap": 2, "HB Counter": 1.5, "Direct Snap Power": 1,
               "Outside Zone": 1.2, "Inside Trap": 1.2},
    "vertical": {"Power G": 1.5, "Inside Zone": 2, "HB Counter": 1.5, "HB Toss": 1.2, "HB Draw": 1.5,
                 "Outside Zone": 1.5, "HB Sweep": 1},
}
PASS_WEIGHTS = {     # combo family weights by offensive family
    "wide_zone": {"quick": 0.8, "dropback": 1.0, "deep": 1.1, "pa": 1.8, "boot": 1.8, "rollout": 1.0, "screen": 1.0},
    "mcvay": {"quick": 1.0, "dropback": 1.1, "deep": 1.0, "pa": 1.6, "boot": 1.5, "rollout": 0.8, "screen": 1.2},
    "power": {"quick": 0.8, "dropback": 0.9, "deep": 1.3, "pa": 1.8, "boot": 1.2, "rollout": 0.6, "screen": 0.8},
    "west_coast": {"quick": 1.6, "dropback": 1.2, "deep": 0.8, "pa": 1.0, "boot": 0.9, "rollout": 1.0, "screen": 1.6},
    "spread": {"quick": 1.6, "dropback": 1.3, "deep": 1.0, "pa": 0.7, "boot": 0.6, "rollout": 1.0, "screen": 1.5},
    "vertical": {"quick": 0.9, "dropback": 1.2, "deep": 1.7, "pa": 1.3, "boot": 1.0, "rollout": 0.8, "screen": 0.8},
}

# menu composition by formation tag: share of a menu per call family
MENU_MIX = {
    "goal": {"run": 0.5, "qb": 0.12, "pa": 0.25, "quick": 0.13},
    "short": {"run": 0.45, "qb": 0.06, "pa": 0.27, "quick": 0.1, "dropback": 0.06, "deep": 0.06},
    "base": {"run": 0.36, "qb": 0.04, "pa": 0.18, "quick": 0.14, "dropback": 0.16, "deep": 0.06, "screen": 0.06},
    "pass": {"run": 0.24, "qb": 0.03, "pa": 0.06, "quick": 0.24, "dropback": 0.25, "deep": 0.08, "screen": 0.1},
    "spread": {"run": 0.12, "qb": 0.06, "quick": 0.3, "dropback": 0.32, "deep": 0.1, "screen": 0.1},
    "empty": {"run": 0.0, "qb": 0.1, "quick": 0.4, "dropback": 0.36, "deep": 0.1, "screen": 0.04},
}

# formations every book carries when its personnel exists (the must-have families)
MUST_FORMATIONS = ("Goal Line Sneak", "Goal Line", "Gun Wildcat", "Empty Trey", "Singleback Doubles",
                   "Gun Doubles", "Gun Trips TE", "Gun Bunch X Nasty", "Pistol Doubles", "I-Form Pro",
                   "I-Form Tight", "Full House", "Wing T", "Gun Empty Trey", "Singleback Ace", "Gun Spread")

LONG_SETS = ("Trips", "Empty", "Trey", "Y-Slot", "Tight Open", "Spread")
GROUP_NAMES = {"Pistol": "Pistol", "Kings Long": "Kings Long", "13": "Jumbo", "P2": "Pony"}
STOCK_NAMES = {"11": "Kings", "12": "Ace", "21": "Pro", "22": "Jokers", "23": "Jacks", "20": "Queens", "10": "Flush",
               "00": "5 Wide", "01": "Straight"}
GROUP_CODES = {"Pistol": 5, "Kings Long": 9, "13": 1, "P2": 7}


def tree() -> dict:
    return json.loads(TREE.read_text(encoding="utf-8"))["teams"]


# ---------------------------------------------------------------------------
# Team profile
# ---------------------------------------------------------------------------

@dataclass
class Profile:
    team: str
    era: str
    family: str
    feature: str
    depth_step: int
    fam_w: dict
    pers_w: dict
    run_w: dict
    pass_w: dict
    pa_pct: float
    signature: list
    seed: int


def team_profile(team: str, era: str = "2020s") -> Profile:
    pkg = v2.load_package(team)
    t = pkg.get("tendencies", {})
    row = tree()[team]
    ep = ERA_PROFILES[era]
    gun = row["gun"] / 100.0
    fam_w = {"gun": (0.4 + gun) * ep["gun_bias"], "pistol": 0.25 + row["pistol"] / 12.0,
             "singleback": 0.4 + row["singleback"] / 30.0, "uc2": (0.3 + row["uc_two_back"] / 9.0) * ep["uc_bias"],
             "gl": 0.6}
    pistol_real = float(t.get("pistol_pct", 3.0))
    fam_w["pistol"] *= 0.8 + min(pistol_real, 35.0) / 15.0
    pers = row["personnel"]
    pers_w = {"11": 0.5 + pers["11"] / 40.0, "12": 0.3 + pers["12"] / 12.0, "21": 0.25 + pers["21"] / 7.0,
              "13": 0.15 + pers["13"] / 4.0, "22": 0.2 + pers["22+23"] / 8.0, "23": 0.2 + pers["22+23"] / 8.0,
              "20": 0.15 + pers["10+20+00"] / 12.0, "10": 0.15 + pers["10+20+00"] / 6.0,
              "00": 0.1 + pers["10+20+00"] / 10.0, "01": 0.1 + pers["10+20+00"] / 12.0, "P2": 0.25}
    for k, s in ep["personnel_scale"].items():
        pers_w[k] = pers_w.get(k, 0.2) * s
    family = pkg.get("family") or "west_coast"
    pass_w = dict(PASS_WEIGHTS.get(family, PASS_WEIGHTS["west_coast"]))
    pa = float(t.get("play_action_pct", 22.0))
    pass_w["pa"] *= pa / 22.0
    pass_w["boot"] *= pa / 22.0
    seed = int.from_bytes(hashlib.sha256(f"{team}:{era}:pb1".encode()).digest()[:4], "little")
    return Profile(team, era, family, pkg.get("feature", "WR1"), int(pkg.get("depth_step", 0) or 0), fam_w, pers_w,
                   dict(RUN_WEIGHTS.get(family, RUN_WEIGHTS["west_coast"])), pass_w, pa,
                   [s["formation"] for s in row.get("signature", [])], seed)


def formation_weight(prof: Profile, name: str) -> float:
    spec = oc.FORMATIONS[name]
    fam = om.formation_family(name)
    group = FAMILY_GROUP.get(fam, "singleback")
    if spec.align == "pistol":
        group = "pistol"
    w = prof.fam_w.get(group, 0.5) * prof.pers_w.get(spec.personnel, 0.2)
    w *= ERA_PROFILES[prof.era]["family_scale"].get(fam, 1.0)
    if name in prof.signature:
        w *= 3.0
    if any(name.startswith(s.split(" ")[0]) and s.split(" ")[1:2] == name.split(" ")[1:2] for s in prof.signature):
        w *= 1.4
    return w


# ---------------------------------------------------------------------------
# Capacity and personnel groups
# ---------------------------------------------------------------------------

def defense_appends(team: str) -> tuple[int, int]:
    path = ROOT / "data" / "playbooks" / f"softdrink_{team.lower()}_defense.2k5book"
    if not path.exists():
        return 0, 0
    doc = json.loads(path.read_text(encoding="utf-8"))
    return (sum(1 for f in doc["formations"] if f.get("replace_index") is None),
            sum(1 for p in doc["plays"] if p.get("replace_index") is None))


def capacity(info: v2.BookInfo, team: str) -> dict:
    book = info.book
    ret_f = len(book.formations) - len(info.forms)
    ret_p = len(book.plays) - len(info.plays)
    df, dp = defense_appends(team)
    free = insp.PLAY_CAPACITY - ret_p - dp - len(info.plays)
    # the PAT fake field goal takes a free record, else one ordinary offensive record (a full book)
    special_mode = "append" if free >= 1 else "replace"
    plays = insp.PLAY_CAPACITY - ret_p - dp - 1 if free >= 1 else len(info.plays) - 1
    return dict(formations=insp.FORMATION_CAPACITY - ret_f - df, plays=plays,
                retained_formations=ret_f, retained_plays=ret_p, defense_append_formations=df,
                defense_append_plays=dp, special_additions=1, special_mode=special_mode,
                free_play_records=max(0, free), categories=len(book.categories))


@dataclass
class GroupPlan:
    """personnel key (or twin) -> category index, codes in book slot order, canonical order map, edit values."""
    index: dict = field(default_factory=dict)       # key -> category index
    codes: dict = field(default_factory=dict)       # key -> tuple of 11 position codes (book order)
    order: dict = field(default_factory=dict)       # key -> canonical slot order (book slot -> canonical)
    edits: dict = field(default_factory=dict)       # category index -> (positions, code, name) to write
    new: set = field(default_factory=set)           # appended indices


def retained_categories(info: v2.BookInfo) -> set[int]:
    used = set()
    body = info.body
    for f in info.book.formations:
        if f.index in info.forms:
            continue
        aux = insp.FORMATION_AUX_BASE + f.index * insp.FORMATION_AUX_SIZE
        own, mask = struct.unpack_from("<II", body, aux + 0x48)
        used.add(own & 0x3F)
        used.update(c for c in range(26) if mask >> c & 1)
    return used


def plan_groups(info: v2.BookInfo, wanted: list[str]) -> tuple[GroupPlan, list[str]]:
    """Place every wanted key ('11', '12', ..., 'Pistol', 'Kings Long', '13', 'P2'); returns the plan and the keys
    that did not fit.  Stock groups keep their record; twins and new personnel reuse a spare record or append."""
    plan = GroupPlan()
    stock = {}
    for pers, canon in oc.PERSONNEL_CODES.items():
        full = oc.LINE_CODES + canon
        for ci in info.book.categories:
            codes = tuple(lib.category_positions(info.body, ci.index))
            if codes[:6] == full[:6] and sorted(codes) == sorted(full):
                stock.setdefault(pers, (ci.index, codes, tuple(full.index(c) for c in codes)))
                break
    keep = retained_categories(info)
    used_stock = set()
    missing = []
    for key in wanted:
        if key in stock and key not in GROUP_NAMES:
            ci, codes, order = stock[key]
            plan.index[key], plan.codes[key], plan.order[key] = ci, codes, order
            used_stock.add(ci)
    count = len(info.book.categories)
    for key in wanted:
        if key in plan.index:
            continue
        base = "11" if key in ("Pistol", "Kings Long") else key
        if base not in oc.PERSONNEL_CODES:
            missing.append(key)
            continue
        if base in plan.codes:
            codes, order = plan.codes[base], plan.order[base]
        else:
            full = oc.LINE_CODES + oc.PERSONNEL_CODES[base]
            codes, order = tuple(full), tuple(range(11))
        spare = next((ci.index for ci in info.book.categories
                      if ci.index not in keep and ci.index not in used_stock and ci.index not in plan.edits
                      and lib.is_offense_category(lib.category_positions(info.body, ci.index))
                      and not any(ci.index == v[0] for k, v in stock.items() if k in wanted)), None)
        name = GROUP_NAMES.get(key) or STOCK_NAMES.get(key, key)
        if any(c.name == name for c in info.book.categories if c.index != spare) or \
                any(e[2] == name for e in plan.edits.values()):
            name = (name + " 2")[:20]
        code = GROUP_CODES.get(key, oc.PERSONNEL_CATEGORY_ID.get(base, 6))
        if spare is not None:
            ci = spare
        elif count < insp.CATEGORY_CAPACITY:
            ci = count
            count += 1
            plan.new.add(ci)
        else:
            missing.append(key)
            continue
        plan.index[key], plan.codes[key], plan.order[key] = ci, codes, order
        plan.edits[ci] = (codes, code, name)
        used_stock.add(ci)
    return plan, missing


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

@dataclass
class Cand:
    design: oc.PlayDesign
    fname: str
    family: str           # run | qb | quick | dropback | deep | pa | boot | rollout | screen | trick | must
    concept: str          # name without the featured-player letter (menu diversity)
    scheme: str
    primary_code: int | None
    screen_type: str | None
    routes: frozenset
    kinds: frozenset
    weight: float
    key: tuple = ()
    must: str = ""
    deep: bool = False    # featured route finishes 20+ yards downfield (coach profile deep class)
    lane: int | None = None   # native run lane of the handoff hole (nfl2k5_vip.HOLE_LANES)


def _views(spec: oc.FormationSpec, design: oc.PlayDesign, flags: int) -> lint.PlayView:
    chains = [list(codec.encode_chain(c)) for c in design.chains]
    return lint.PlayView(0, spec.name, 0, design.name, flags, [tuple(map(float, p)) for p in spec.positions_cm()],
                         list(spec.codes()), chains)


class Checker:
    """Validator + linter + native route check for (formation, design) pairs, cached."""

    def __init__(self, xbe: Path | None):
        from tools.b77 import p6s_route_check as rc
        self.rc = rc
        self.m = rc.machine(xbe) if xbe else None
        self.cache: dict = {}
        self.results: dict = {}

    def flags_for(self, info: v2.BookInfo, design: oc.PlayDesign) -> int:
        donor = info.header_donor(design.header)
        return v2.header_word(donor[2], design.preference)

    def ok(self, info, spec: oc.FormationSpec, design: oc.PlayDesign) -> tuple[bool, str]:
        key = (spec.name, v2.chain_key(design.chains), design.header)
        if key in self.results:
            return self.results[key]
        res = self._ok(info, spec, design)
        self.results[key] = res
        return res

    def _ok(self, info, spec, design):
        flags = self.flags_for(info, design)
        try:
            enc = [[n.to_bytes() for n in codec.encode_chain(c)] for c in design.chains]
        except Exception as exc:  # noqa: BLE001
            return False, f"encode: {exc}"
        if any(len(e) > 15 or not e for e in enc):
            return False, "chain length"
        asg = [(0, e) for e in enc]
        try:
            for i in range(11):
                asg[i] = (codec.build_descriptor(flags, asg, i, 0), asg[i][1])
            codec.validate_sync(asg)
            err = codec.validate_play(flags, asg)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
        if err:
            return False, "validator: " + err
        pos = [tuple(p) for p in spec.positions_cm()]
        codes = list(spec.codes())
        flats, repaired = lib.forward_back_flats(design.chains, pos, codes)
        if repaired:
            return False, "needs back-flat repair"
        fixed, _ = lint.normalize_offense_play(pos, codes, design.chains)
        if fixed is not None:
            return False, "needs execution repair"
        view = _views(spec, design, flags)
        found = lint.check_handoffs(view) + lint.check_pass_targets(view) + lint.check_screen(view)
        bad = [f for f in found if lint.SEVERITY.get(f.code) == "error" or f.code in ("BACKWARD_TARGET", "SCREEN_SIDE_CROSS", "SCREEN_NO_RELEASE")]
        if bad:
            return False, "lint: " + bad[0].code
        if self.m is not None and design.play_type in ("pass", "pa_pass") and "screen" not in design.tags:
            rows = self.rc.design_rows(spec, design)
            flagsn = [x for x in self.rc.check_rows(self.m, self.cache, rows) if not x[0].startswith("BEHIND")]
            if flagsn:
                return False, "route check: " + flagsn[0][0]
        return True, ""


def _concept_base(name: str) -> str:
    for pre in ("X ", "Z ", "Slot ", "Y ", "U ", "HB ", "RB2 ", "FB "):
        if name.startswith(pre):
            return name[len(pre):]
        if name.startswith("PA " + pre):
            return "PA " + name[3 + len(pre):]
    return name


def _route_names(design) -> set:
    out = set()
    for ch in design.chains:
        segs = tuple((int(n[1][0]), round(n[1][2] / oc.FT)) for n in ch if n[0] == 0x12)
        if not segs:
            continue
        for name, r in oc.ROUTES.items():
            try:
                built = tuple((int(s[1][0]), round(s[1][2] / oc.FT)) for s in r.build())
            except Exception:  # noqa: BLE001
                continue
            if tuple(k for k, _ in built) == tuple(k for k, _ in segs) and built[1:] == segs[1:]:
                out.add(name)
                break
    return out


def _kinds(design) -> set:
    return {int(n[1][0]) for ch in design.chains for n in ch if n[0] == 0x12}


def screen_type(design, spec) -> str | None:
    if "screen" not in design.tags:
        return None
    p = design.primary
    kind = spec.codes()[p] & 31 if p is not None else 0
    return {HB_: "back", FB_: "fullback"}.get(kind, "te" if kind == lib.TE else "wr") + (
        ":" + design.concept if kind == lib.WR else "")


HB_, FB_ = lib.HB, lib.FB


HOLE_LANES = (2, 4, 3, 3, 2, 2, 1, 1, 0)        # nfl2k5_vip.HOLE_LANES


def make_cand(spec, design, family, weight, must="") -> Cand:
    codes = spec.codes()
    passing = design.play_type in ("pass", "pa_pass")
    deep = False
    if passing and design.primary is not None and "screen" not in design.tags:
        ctx = spec.context()
        end = oc.route_end_depth_yd(ctx, design.primary, design.chains[design.primary])
        deep = end is not None and end >= 20.0
    lane = None
    if not passing:
        for ch in design.chains:
            for n in ch:
                if n[0] == 0x16:
                    lane = HOLE_LANES[int(n[1][2])]
    return Cand(design, spec.name, family, _concept_base(design.name), design.concept,
                codes[design.primary] if design.primary is not None and passing else None,
                screen_type(design, spec), frozenset(_route_names(design)), frozenset(_kinds(design)), weight,
                (spec.personnel, v2.chain_key(design.chains)), must, deep, lane)


def candidates(info, prof: Profile, fname: str, checker: Checker, rng: random.Random, sample: int = 220) -> list[Cand]:
    spec = oc.FORMATIONS[fname]
    ctx = spec.context()
    codes = spec.codes()
    out: list[Cand] = []
    seen = set()

    def add(design, family, weight, must=""):
        if design is None:
            return
        ok, why = checker.ok(info, spec, design)
        if not ok:
            return
        c = make_cand(spec, design, family, weight, must)
        if c.key in seen:
            return
        seen.add(c.key)
        out.append(c)

    # runs
    for scheme in om.RUN_SCHEMES:
        base_w = prof.run_w.get(scheme, 0.6)
        carriers = ["B"]
        if spec.personnel in ("21", "22", "23") and scheme in ("HB Dive", "HB Iso", "Inside Zone", "HB Off Tackle") \
                and ctx.slot("B2") is not None:
            carriers.append("B2")
        if spec.personnel == "P2" and ctx.slot("B2") is not None:
            carriers.append("B2")
        for carrier in carriers:
            for weak in (False, True):
                try:
                    d = om.run_design(ctx, scheme, weak=weak, carrier=carrier, codes=codes)
                except oc.ConceptUnavailable:
                    continue
                w = base_w * (0.7 if weak else 1.0) * (0.8 if carrier == "B2" else 1.0)
                add(d, "trick" if "gadget" in d.tags else "run", w)
    # QB runs and must-haves
    for fn, fam, w, must in ((oc.CONCEPTS["QB Sneak"].build, "qb", 1.0, "sneak"), (om.tush_push, "qb", 1.0, "tush"),
                             (om.qb_keep, "qb", 0.8, "keep"), (om.qb_power, "qb", 0.5, ""),
                             (oc.CONCEPTS["QB Draw"].build, "qb", 0.5, "")):
        try:
            d = fn(ctx, codes) if fn in (om.tush_push, om.qb_keep, om.qb_power) else fn(ctx)
        except oc.ConceptUnavailable:
            continue
        if must == "tush" and fname != "Goal Line Sneak":
            continue
        add(d, fam, w, must)
    # screens
    for label, weak in (("B", False), ("B", True), ("B2", False)):
        try:
            add(om.back_screen(ctx, label, weak, codes), "screen", 1.0)
        except oc.ConceptUnavailable:
            pass
    for name in ("Bubble Screen", "WR Slip Screen", "TE Screen"):
        try:
            d = oc.design(name, ctx)
        except oc.ConceptUnavailable:
            continue
        p = d.primary
        who = om.letter(codes[p]) if p is not None else ""
        d.name = f"{who} {name.replace('WR ', '').replace('TE ', '')}".strip()
        add(d, "screen", 1.0)
    # tricks
    for name in ("Flea Flicker", "End Around", "Reverse"):
        try:
            add(oc.design(name, ctx), "trick", 0.5)
        except oc.ConceptUnavailable:
            pass
    # named engine pass concepts
    for name, cd in oc.CONCEPTS.items():
        if cd.family in ("run", "trick", "screen") or name in ("QB Sneak", "QB Draw"):
            continue
        try:
            d = oc.design(name, ctx, {"depth_step": prof.depth_step} if prof.depth_step else None)
        except oc.ConceptUnavailable:
            continue
        p = d.primary
        fam = {"quick": "quick", "dropback": "dropback", "pa": "pa", "shot": "deep"}.get(cd.family, "dropback")
        if "rollout" in d.header:
            fam = "boot"
        who = om.letter(codes[p]) if p is not None else ""
        if who and not d.name.startswith(("PA", "Y ", "Mesh", "Four")):
            d.name = f"{who} {d.name}"[:40]
        add(d, fam, prof.pass_w.get(fam, 1.0) * 0.9)
    # combo calls (sampled by team weights)
    calls = om.combo_calls(ctx)
    heavy = spec.tag in ("goal", "short")
    if heavy:
        # goal-line and heavy sets: play action and boots off the run look, quick game, few dropbacks
        extra = []
        for c in calls:
            if c.drop == "quick":
                extra.append(om.ComboCall(c.strong, c.weak, ("fake", 0) if False else c.back, "pa", c.focus))
        calls = [c for c in calls if c.drop in ("pa", "quick", "max")] + extra
    if ctx.slot("B") is not None:
        calls += [om.ComboCall(c.strong, c.weak, ("check", "Back Flat", 1.0) if c.back[0] == "block" else c.back, "boot", c.focus)
                  for c in calls if c.drop in ("pa", "dropback") and c.focus != "back"][:4000]
        calls += [om.ComboCall(c.strong, c.weak, ("route", "Flat"), "rollout", c.focus)
                  for c in calls if c.drop == "dropback" and c.strong in ("Flood", "Smash", "Bench", "Curl Flat", "Spot", "Sail", "Snag")]
    if not calls:
        return out
    weights = []
    for c in calls:
        sc = om._find(om.STRONG_COMBOS, len(om._side_labels(ctx, "S")), c.strong)
        fam = {"pa": "pa", "boot": "boot", "rollout": "rollout"}.get(c.drop, sc.family)
        w = prof.pass_w.get(fam, 1.0)
        if c.focus == "back":
            w *= 0.35
        if c.focus == "weak":
            w *= 0.6
        weights.append(w)
    picked = set()
    tries = 0
    while len(picked) < min(sample, len(calls)) and tries < sample * 6:
        tries += 1
        i = rng.choices(range(len(calls)), weights)[0]
        if i in picked:
            continue
        picked.add(i)
        c = calls[i]
        try:
            d = om.combo_design(ctx, c, codes)
        except oc.ConceptUnavailable:
            continue
        sc = om._find(om.STRONG_COMBOS, len(om._side_labels(ctx, "S")), c.strong)
        fam = {"pa": "pa", "boot": "boot", "rollout": "rollout"}.get(c.drop, sc.family)
        if c.drop == "max":
            fam = "deep"
        add(d, fam, weights[i])
    return out


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

FAMILY_OF_MIX = {"run": "run", "qb": "qb", "quick": "quick", "dropback": "dropback", "deep": "deep", "pa": "pa",
                 "boot": "pa", "rollout": "dropback", "screen": "screen", "trick": "run"}


BOOK_FAMILY = {"run": "run", "trick": "run", "qb": "run", "quick": "quick", "screen": "screen", "dropback": "dropback",
               "rollout": "dropback", "deep": "deep", "pa": "pa", "boot": "pa"}
SHARE_CAP = {"run": 5, "quick": 3, "dropback": 3, "pa": 3, "deep": 2, "screen": 3}
BOOK_SHARES = {"run": 0.32, "quick": 0.18, "dropback": 0.22, "pa": 0.13, "deep": 0.08, "screen": 0.07}


def book_quota(prof: Profile, budget: int) -> dict:
    w = {}
    for fam, share in BOOK_SHARES.items():
        mod = {"quick": prof.pass_w["quick"], "dropback": prof.pass_w["dropback"], "deep": prof.pass_w["deep"],
               "pa": (prof.pass_w["pa"] + prof.pass_w["boot"]) / 2, "screen": prof.pass_w["screen"]}.get(fam, 1.0)
        w[fam] = share * (0.6 + 0.4 * mod)
    tot = sum(w.values())
    return {k: max(3, round(budget * v / tot)) for k, v in w.items()}


class Selector:
    def __init__(self, prof: Profile, league_routes: Counter, league_concepts: Counter, quota: dict | None = None):
        self.prof = prof
        self.quota = quota or {}
        self.taken = Counter()
        self.lanes = defaultdict(set)
        self.routes = Counter()
        self.kinds = Counter()
        self.concepts = Counter()
        self.schemes = Counter()
        self.primary = Counter()
        self.league_routes = league_routes
        self.league_concepts = league_concepts

    def score(self, c: Cand, menu: list[Cand], mix: dict, record: bool = True) -> float:
        s = c.weight
        if record and self.quota:
            bf = BOOK_FAMILY[c.family]
            q = self.quota.get(bf, 1)
            rem = q - self.taken[bf]
            s *= 0.06 if rem <= 0 else 0.5 + rem / q
        fam = FAMILY_OF_MIX[c.family]
        have = Counter(FAMILY_OF_MIX[m.family] for m in menu)
        target = mix.get(fam, 0.0) * max(len(menu) + 1, 8)
        s *= 1.6 if have[fam] < target else 0.35
        if any(m.concept == c.concept for m in menu):
            s *= 0.05
        s *= 1.0 / (1.0 + 0.8 * self.concepts[c.concept])
        if c.scheme in om.RUN_SCHEMES:
            s *= 1.0 / (1.0 + 0.5 * self.schemes[c.scheme])
        if c.lane is not None:
            lane = min(c.lane, 4 - c.lane)          # flipped rings mirror lanes 0<->4, 1<->3
            if c.scheme not in self.lanes[lane] and len(self.lanes[lane]) < 4:
                s *= 1.8
        new_routes = [r for r in c.routes if self.routes[r] == 0]
        s *= 1.0 + 0.12 * len(new_routes) + 0.08 * sum(1 for r in c.routes if self.league_routes[r] == 0)
        s *= 1.0 + 0.2 * sum(1 for k in c.kinds if self.kinds[k] == 0)
        s *= 1.0 / (1.0 + 0.25 * self.league_concepts[c.concept] / 8.0)
        if c.primary_code is not None:
            role = om.letter(c.primary_code) or "?"
            total = sum(self.primary.values()) + 1
            share = self.primary[role] / total
            ideal = {"X": 0.2, "Z": 0.2, "Slot": 0.2, "Y": 0.18, "U": 0.05, "HB": 0.12, "FB": 0.03, "RB2": 0.03}.get(role, 0.1)
            s *= 1.6 if share < ideal else 0.5
        if c.screen_type:
            if any(m.screen_type == c.screen_type for m in menu):
                s = 0.0
            if sum(1 for m in menu if m.screen_type) >= 2:
                s = 0.0
        return s

    def take(self, c: Cand):
        self.taken[BOOK_FAMILY[c.family]] += 1
        self.routes.update(c.routes)
        self.kinds.update(c.kinds)
        self.concepts[c.concept] += 1
        self.schemes[c.scheme] += 1
        if c.lane is not None:
            self.lanes[min(c.lane, 4 - c.lane)].add(c.scheme)
        if c.primary_code is not None:
            self.primary[om.letter(c.primary_code) or "?"] += 1


def choose_formations(info, prof: Profile, plan_n: int, rng: random.Random) -> list[str]:
    era = ERA_PROFILES[prof.era]["catalog_era"]
    have = set(info_groups_possible(info))
    pool = [n for n in oc.FORMATIONS if era in om.ERA.get(n, ("2020s", "2010s")) and oc.FORMATIONS[n].personnel in have
            and n not in ("Empty", "Singleback Spread", "Singleback Trips Open", "Split Backs Twins")]
    chosen = [n for n in MUST_FORMATIONS if n in pool]
    for s in prof.signature:
        for n in pool:
            if n == s and n not in chosen:
                chosen.append(n)
    # at least three pistol sets (Noah: Pistol is its own group) and one of each modern gun family
    for group in (("Pistol Bunch TE", "Pistol Y Off Trips", "Pistol Strong", "Pistol Deuce Close", "Pistol Ace",
                   "Pistol Strong Slot", "Pistol Wing", "Pistol Trey", "Pistol Doubles Y Off", "Pistol Full House"),):
        opts = [n for n in group if n in pool and n not in chosen]
        rng.shuffle(opts)
        opts.sort(key=lambda n: -formation_weight(prof, n))
        need = 3 + (1 if prof.fam_w["pistol"] > 1.2 else 0) + (1 if prof.fam_w["pistol"] > 2.0 else 0)
        chosen += opts[:max(0, need - sum(1 for n in chosen if oc.FORMATIONS[n].align == "pistol"))]
    rest = [n for n in pool if n not in chosen]
    while len(chosen) < plan_n and rest:
        ws = [formation_weight(prof, n) * (0.55 if _too_close(n, chosen) else 1.0) for n in rest]
        i = rng.choices(range(len(rest)), ws)[0]
        chosen.append(rest.pop(i))
    return chosen[:plan_n]


def _too_close(name: str, chosen: list[str]) -> bool:
    spec = oc.FORMATIONS[name]
    for n in chosen:
        o = oc.FORMATIONS[n]
        if o.personnel == spec.personnel and o.align == spec.align and \
                sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(o.skills, spec.skills)) < 6:
            return True
    return False


def info_groups_possible(info) -> list[str]:
    return list(oc.PERSONNEL_CODES)


def group_key(fname: str) -> str:
    spec = oc.FORMATIONS[fname]
    if spec.align == "pistol" and spec.personnel == "11":
        return "Pistol"
    return spec.personnel


def build_book(retail: bytes, team: str, *, era: str = "2020s", xbe: Path | None = None, checker: Checker | None = None,
               league_routes: Counter | None = None, league_concepts: Counter | None = None, menu_target: int = 12,
               menu_max: int = 18):
    prof = team_profile(team, era)
    rng = random.Random(prof.seed)
    info = v2.BookInfo(retail, team)
    cap = capacity(info, team)
    checker = checker or Checker(xbe)
    forms = choose_formations(info, prof, cap["formations"], rng)
    wanted = []
    for f in forms:
        k = group_key(f)
        if k not in wanted:
            wanted.append(k)
    if "11" in wanted and "Kings Long" not in wanted:
        wanted.append("Kings Long")
    plan, missing = plan_groups(info, wanted)
    if missing:
        forms = [f for f in forms if group_key(f) not in missing]
    # refill dropped formation slots from personnel that did place
    if len(forms) < cap["formations"]:
        extra = choose_formations(info, prof, cap["formations"] + 20, random.Random(prof.seed + 1))
        for f in extra:
            if len(forms) >= cap["formations"]:
                break
            if f not in forms and group_key(f) in plan.index:
                forms.append(f)
    # candidates
    cands = {f: candidates(info, prof, f, checker, random.Random(prof.seed ^ hash(f) & 0xFFFF)) for f in forms}
    budget = cap["plays"]
    sel = Selector(prof, league_routes or Counter(), league_concepts or Counter(), book_quota(prof, budget))
    chosen: dict = OrderedDict()           # key -> Cand (record)
    menus: dict = {f: [] for f in forms}

    def pick(f, c):
        if c.key not in chosen:
            chosen[c.key] = c
            sel.take(c)
        menus[f].append(chosen[c.key])

    # must-haves
    def first(f, pred):
        return next((c for c in cands.get(f, []) if pred(c)), None)
    musts = []
    for f in forms:
        if f == "Goal Line Sneak":
            musts += [(f, first(f, lambda c: c.must == "tush")), (f, first(f, lambda c: c.must == "sneak"))]
    for f in forms:
        if oc.FORMATIONS[f].tag in ("goal", "short") and f != "Goal Line Sneak":
            musts.append((f, first(f, lambda c: c.must == "sneak")))
            break
    for f in ("Empty Trey", "Singleback Doubles", "Singleback Ace"):
        if f in forms:
            musts.append((f, first(f, lambda c: c.must == "keep")))
            break
    for f in forms:
        if oc.FORMATIONS[f].align == "gun" and any(c.design.play_type == "direct_snap" for c in cands[f]):
            musts.append((f, first(f, lambda c: c.design.play_type == "direct_snap")))
            break
    for name in ("Flea Flicker", "End Around"):
        for f in forms:
            c = first(f, lambda c: c.design.concept == name)
            if c:
                musts.append((f, c))
                break
    for f in forms:
        if oc.FORMATIONS[f].tag in ("goal",):
            for fam in ("pa", "quick"):
                c = first(f, lambda c, fam=fam: c.family == fam)
                if c:
                    musts.append((f, c))
    for uc in (False, True):
        got = 0
        for f in sorted(forms, key=lambda f: -len(cands[f])):
            spec = oc.FORMATIONS[f]
            if (spec.align == "uc") != uc or got >= 3:
                continue
            c = max((c for c in cands[f] if c.deep), key=lambda c: c.weight, default=None)
            if c is not None:
                musts.append((f, c))
                got += 1
    # team plays from the team package (p6s / p6x signatures and named menu entries) where the set is in the book
    pkg = v2.load_package(team)
    named = [dict(formation=s_["formation"], concept=s_["concept"], name=s_["name"], overrides=s_.get("overrides", {}))
             for s_ in pkg.get("signature", [])]
    for fname, entries in (pkg.get("menus") or {}).items():
        for e in entries:
            if isinstance(e, dict) and e.get("name"):
                named.append(dict(formation=fname, concept=e["concept"], name=e["name"], overrides=e.get("overrides", {})))
    team_plays = 0
    for row in named:
        if team_plays >= 8 or row["formation"] not in forms or row["concept"] not in oc.CONCEPTS:
            continue
        spec = oc.FORMATIONS[row["formation"]]
        try:
            d = oc.design(row["concept"], spec.context(), dict(row["overrides"], name=row["name"]))
        except (oc.ConceptUnavailable, KeyError, ValueError, TypeError):
            continue
        if not checker.ok(info, spec, d)[0]:
            continue
        fam = {"quick": "quick", "dropback": "dropback", "pa": "pa", "shot": "deep", "screen": "screen", "run": "run",
               "trick": "trick"}.get(oc.CONCEPTS[row["concept"]].family, "dropback")
        c = make_cand(spec, d, fam, 2.0, must="team")
        if c.key not in {m.key for m in menus[row["formation"]]}:
            musts.append((row["formation"], c))
            team_plays += 1
    for f, c in musts:
        if c is not None and len(chosen) < budget and not any(m.key == c.key for m in menus[f]):
            pick(f, c)
    # greedy fill: each step serves the formation furthest below its own-record target; a set with no sister
    # formation (same personnel) cannot borrow plays, so it needs more of its own
    sisters = Counter(oc.FORMATIONS[f].personnel for f in forms)
    own_target = {f: {1: menu_target, 2: 7, 3: 5}.get(sisters[oc.FORMATIONS[f].personnel], 4) for f in forms}
    scale = (budget - len(chosen)) / max(1, sum(own_target.values()))
    if scale > 1:
        own_target = {f: max(1, round(v * scale)) for f, v in own_target.items()}
    own = Counter()
    for f in forms:
        own[f] = sum(1 for m in menus[f])
    stuck = set()
    while len(chosen) < budget:
        open_forms = [f for f in forms if f not in stuck and len(menus[f]) < menu_max]
        if not open_forms:
            break
        f = max(open_forms, key=lambda f: (own_target[f] - own[f], rng.random()))
        mix = MENU_MIX[oc.FORMATIONS[f].tag]
        best, best_s = None, 0.0
        for c in cands[f]:
            if c.key in chosen or any(m.design.name == c.design.name for m in menus[f]):
                continue
            s = sel.score(c, menus[f], mix) * (0.5 + rng.random())
            if s > best_s:
                best, best_s = c, s
        if best is None:
            stuck.add(f)
            continue
        pick(f, best)
        own[f] += 1
    # share records into sister formations (same personnel, same canonical slot order); a record is linked
    # in at most SHARE_CAP menus (runs more, QB runs only in sets of the same QB alignment)
    links = Counter()
    for f in forms:
        for m in menus[f]:
            links[m.key] += 1
    shared = 0
    for _round in range(menu_target):
        added_any = False
        for f in sorted(forms, key=lambda f: len(menus[f])):
            spec = oc.FORMATIONS[f]
            if len(menus[f]) >= menu_target:
                continue
            mix = MENU_MIX[spec.tag]
            options = []
            for key, c in chosen.items():
                if key[0] != spec.personnel or any(m.key == key for m in menus[f]) or c.must == "tush":
                    continue
                cap_links = SHARE_CAP.get(BOOK_FAMILY[c.family], 3)
                if links[key] >= cap_links:
                    continue
                home = oc.FORMATIONS[c.fname]
                if c.family == "qb" and (home.align == "uc") != (spec.align == "uc"):
                    continue
                if any(m.design.name == c.design.name or m.concept == c.concept for m in menus[f]):
                    continue
                if FAMILY_OF_MIX[c.family] not in mix:
                    continue
                s = sel.score(c, menus[f], mix, record=False) / (1.0 + 0.7 * links[key])
                if s > 0:
                    options.append((s, c))
            options.sort(key=lambda t: -t[0])
            for s_, c in options[:40]:
                ok, _ = checker.ok(info, spec, c.design)
                if ok:
                    menus[f].append(c)
                    links[c.key] += 1
                    shared += 1
                    added_any = True
                    break
        if not added_any:
            break
    # every menu a multiple of three links: a short last page repeats its last play on the empty buttons
    # (job pb2: Noah's three Bubble Screens).  Repair by sharing a sister record, dropping a shared link, adding or
    # dropping an own record; the record count is then refilled in steps that keep every menu a multiple of 3.
    def share_options(f, cap_extra=1):
        spec = oc.FORMATIONS[f]
        mix = MENU_MIX[spec.tag]
        out = []
        for key, c in chosen.items():
            if key[0] != spec.personnel or any(m.key == key for m in menus[f]) or c.must == "tush":
                continue
            if links[key] >= SHARE_CAP.get(BOOK_FAMILY[c.family], 3) + cap_extra:
                continue
            if c.family == "qb" and (oc.FORMATIONS[c.fname].align == "uc") != (spec.align == "uc"):
                continue
            if any(m.design.name == c.design.name for m in menus[f]):
                continue
            out.append((sel.score(c, menus[f], mix, record=False) / (1 + links[key]), c))
        out.sort(key=lambda t: -t[0])
        return [c for _s, c in out if checker.ok(info, spec, c.design)[0]][:5]

    def own_options(f):
        mix = MENU_MIX[oc.FORMATIONS[f].tag]
        opts = [(sel.score(c, menus[f], mix), c) for c in cands[f]
                if c.key not in chosen and not any(m.design.name == c.design.name for m in menus[f])]
        return [c for s_, c in sorted(opts, key=lambda t: -t[0]) if s_ > 0][:5]

    def drop_link(f, unique_ok):
        nonlocal shared
        for m in reversed(menus[f]):
            if m.must:
                continue
            if links[m.key] > 1:
                menus[f].remove(m)
                links[m.key] -= 1
                shared -= 1
                return True
        if unique_ok:
            for m in reversed(menus[f]):
                if not m.must and links[m.key] == 1:
                    menus[f].remove(m)
                    del links[m.key]
                    del chosen[m.key]
                    return True
        return False

    def add_shared(f, cap_extra=1):
        nonlocal shared
        if len(menus[f]) >= menu_max:
            return False
        opt = share_options(f, cap_extra)
        if not opt:
            return False
        menus[f].append(opt[0]); links[opt[0].key] += 1; shared += 1
        return True

    def add_own(f):
        if len(chosen) >= budget or len(menus[f]) >= menu_max:
            return False
        opt = own_options(f)
        if not opt:
            return False
        pick(f, opt[0]); links[opt[0].key] = 1
        return True

    for _it in range(400):
        bad = [f for f in forms if len(menus[f]) % 3]
        if not bad:
            break
        progress = False
        for f in bad:
            r = len(menus[f]) % 3
            if r == 2 and (add_shared(f) or add_own(f) or add_shared(f, 3)):
                progress = True
                continue
            if drop_link(f, unique_ok=False) or drop_link(f, unique_ok=True):
                progress = True
                continue
            if add_shared(f) or add_own(f) or add_shared(f, 3):
                progress = True
        if not progress:
            break
    # refill freed records in blocks that keep every menu a multiple of three: r own records plus 3 - r shared
    for _it in range(300):
        free = budget - len(chosen)
        if free <= 0:
            break
        n_own = 3 if free >= 3 else free
        grew = False
        for f in sorted(forms, key=lambda f: len(menus[f])):
            if len(menus[f]) + 3 > menu_max:
                continue
            opts = own_options(f)
            if len(opts) < n_own:
                continue
            shares = share_options(f, 3) if n_own < 3 else []
            shares = [c for c in shares if all(c.key != o.key for o in opts[:n_own])]
            if len(shares) < 3 - n_own:
                continue
            for c in opts[:n_own]:
                pick(f, c); links[c.key] = 1
            for c in shares[:3 - n_own]:
                menus[f].append(c); links[c.key] += 1; shared += 1
            grew = True
            break
        if not grew:
            break
    # remaining free records: swap a shared link for a new own record (menu size unchanged, one more record)
    for _it in range(300):
        if len(chosen) >= budget:
            break
        swapped = False
        for f in sorted(forms, key=lambda f: -len(menus[f])):
            shared_links = [m for m in menus[f] if links[m.key] > 1 and not m.must]
            opts = own_options(f)
            if not shared_links or not opts:
                continue
            m = shared_links[-1]
            menus[f].remove(m)
            links[m.key] -= 1
            shared -= 1
            pick(f, opts[0])
            links[opts[0].key] = 1
            swapped = True
            break
        if not swapped:
            break
    for f in forms:
        if len(menus[f]) % 3:
            raise ValueError(f"{team} {f}: menu of {len(menus[f])} links cannot reach a multiple of three")
    need = len(info.plays) - (1 if cap["special_mode"] == "replace" else 0)
    if len(chosen) < need:
        raise ValueError(f"{team}: only {len(chosen)} records for {need} ordinary plays after page repair")
    return dict(prof=prof, info=info, cap=cap, forms=forms, plan=plan, menus=menus, chosen=chosen, shared=shared,
                missing=missing, cands=cands)


# ---------------------------------------------------------------------------
# Pack assembly
# ---------------------------------------------------------------------------

def order_menu(fname: str, menu: list[Cand]) -> list[Cand]:
    """Base call first; the first three (default audibles) are a run, a quick throw and a shot / play action."""
    spec = oc.FORMATIONS[fname]
    runs = [c for c in menu if c.family in ("run", "qb")]
    quick = [c for c in menu if c.family in ("quick", "screen")]
    shot = [c for c in menu if c.family in ("pa", "boot", "deep", "dropback", "rollout")]
    head = []
    lead = runs if spec.tag in ("goal", "short", "base") else quick or shot
    for group in ((lead, runs, quick, shot) if spec.tag in ("goal", "short", "base") else (lead, shot, runs, quick)):
        for c in group:
            if c not in head:
                head.append(c)
                break
        if len(head) >= 3:
            break
    return head + [c for c in menu if c not in head]


NAME_POOL_UNITS = (0x13000 - insp.STRING_BASE) // 2     # coach_ai tags 0x13000-0x1337F: strings end before it
NAME_MARGIN = 24


def name_variants(c: Cand) -> list[str]:
    alts = list(getattr(c.design, "alt_names", None) or [c.design.name])
    if c.design.name not in alts:
        alts.insert(0, c.design.name)
    base = alts[-1]
    for a, b in (("PA Boot ", "Boot "), ("Sprint ", "Spr "), (" Screen", " Scrn"), ("Max ", "Mx ")):
        if a in base:
            alts.append(base.replace(a, b))
            base = alts[-1]
    return alts


def fit_names(result: dict, team: str) -> dict:
    """Shorten play names (combo backside tags first) until the whole pool fits before the coach_ai tail."""
    info: v2.BookInfo = result["info"]
    retained = {info.book.book_name}
    for f in info.book.formations:
        if f.index not in info.forms:
            retained.add(f.name)
    for p in info.book.plays:
        if p.index not in info.plays:
            retained.add(p.name)
    for c in info.book.categories:
        e = result["plan"].edits.get(c.index)
        retained.add(e[2] if e else c.name)
    for e in result["plan"].edits.values():
        retained.add(e[2])
    dpath = ROOT / "data" / "playbooks" / f"softdrink_{team.lower()}_defense.2k5book"
    defense_units = 0
    if dpath.exists():
        doc = json.loads(dpath.read_text(encoding="utf-8"))
        defense_units = sum(len(e["custom_name"]) + 1 for e in (*doc["formations"], *doc["plays"]))
    budget = NAME_POOL_UNITS - NAME_MARGIN - defense_units
    chosen, menus, forms = result["chosen"], result["menus"], result["forms"]
    variants = {k: name_variants(c) for k, c in chosen.items()}
    current = {k: 0 for k in chosen}
    special = ["Fake FG End Zone"]

    def units():
        names = retained | set(forms) | set(special) | {variants[k][current[k]][:40] for k in chosen}
        return sum(len(n) + 1 for n in names)

    def menu_ok(k, name):
        for f in forms:
            if any(m.key == k for m in menus[f]):
                if any(m.key != k and variants[m.key][current[m.key]] == name for m in menus[f]):
                    return False
        return True
    before = units()
    while units() > budget:
        opts = sorted((k for k in chosen if current[k] + 1 < len(variants[k])),
                      key=lambda k: -len(variants[k][current[k]]))
        moved = False
        for k in opts:
            nxt = variants[k][current[k] + 1]
            if menu_ok(k, nxt):
                current[k] += 1
                moved = True
                break
            current[k] += 1          # skip a variant that would duplicate a menu name
        if not moved and not opts:
            raise ValueError(f"{team}: play names need {units()} UTF-16 units, the pool before 0x13000 has {budget}")
    for k, c in chosen.items():
        c.design.name = variants[k][current[k]][:40]
    return dict(budget=budget, before=before, after=units(), defense_units=defense_units)


def assemble(result: dict, team: str):
    names = fit_names(result, team)
    info: v2.BookInfo = result["info"]
    plan: GroupPlan = result["plan"]
    forms, menus, chosen = result["forms"], result["menus"], result["chosen"]
    cap = result["cap"]
    body = info.body
    # indices: ordinary records first, then appended
    f_idx = list(info.forms) + [None] * max(0, len(forms) - len(info.forms))
    nlinks = Counter(m.key for f in forms for m in menus[f])
    # coach rings address plays 0..255 only: the most linked records and every must-have, deep shot and
    # distinct run take the lowest indices; appended records (indices past the retail count) come last
    keys = sorted(chosen, key=lambda k: (not chosen[k].must, not chosen[k].deep, -nlinks[k]))
    ordinary = sorted(info.plays)
    special_index = None
    if cap["special_mode"] == "replace":
        special_index = ordinary.pop()          # the highest ordinary index (coach rings stop at 255)
    p_idx = ordinary + [None] * max(0, len(keys) - len(ordinary))
    if len(keys) < len(ordinary):
        raise ValueError(f"{team}: {len(keys)} plays for {len(ordinary)} ordinary records")
    if len(forms) < len(info.forms):
        raise ValueError(f"{team}: {len(forms)} formations for {len(info.forms)} ordinary records")
    play_ids, plays_out, rows = {}, [], []
    for n, (k, pi) in enumerate(zip(keys, p_idx)):
        c = chosen[k]
        d = c.design
        spec = oc.FORMATIONS[c.fname]
        gk = group_key(c.fname)
        order = plan.order[gk]
        donor_index, donor_name, donor_flags, donor_sig = info.header_donor(d.header)
        flags = v2.header_word(donor_flags, d.preference)
        chains = v2.to_book_order(d.chains, order)
        pid = f"p{n:03d}"
        play_ids[k] = pid
        ptype = d.play_type if d.play_type in packs.PLAY_TYPES else "pass"
        plays_out.append(packs.PackPlay(
            pid, d.name[:40], ptype, tuple(tuple(ch) for ch in chains),
            packs.PackDonor(donor_index, donor_name, donor_flags, donor_sig), flags, pi,
            info.book.plays[pi].name.strip() if pi is not None else "", d.concept))
        rows.append(dict(play=pid, play_index=pi, name=d.name, concept=d.concept, family=c.family, header=d.header,
                         play_type=ptype, personnel=spec.personnel, home=c.fname, primary=om.letter(c.primary_code)
                         if c.primary_code is not None else None, screen=c.screen_type, must=c.must,
                         routes=sorted(c.routes), deep=c.deep, lane=c.lane, formations=[f for f in forms if any(m.key == k for m in menus[f])]))
    # special: PAT fake field goal into the retained FG formation
    fg = next((f for f in info.book.formations if lib.formation_record(body, f.index).type_code == 12), None)
    special = None
    if fg is not None:
        donor = next((info.book.plays[l.play_index] for l in fg.play_links
                      if "PASS" in info.book.plays[l.play_index].name.upper()), None)
        if donor is not None:
            rec = lib.formation_record(body, fg.index)
            pos = [(s.x[0], s.z[0]) for s in rec.slots]
            codes = lib.category_positions(body, lib.formation_category(body, fg.index))
            dflags, dch = lib.play_chains(body, donor.index)
            chains = om.fake_fg_deep(pos, codes, lib.decoded_chains(body, donor.index))
            special = packs.PackPlay("fgfake", "Fake FG End Zone", "special", tuple(tuple(c) for c in chains),
                                     packs.PackDonor(donor.index, donor.name.strip(), dflags, lib.qb_signature(dch[0][1])),
                                     dflags, special_index,
                                     info.book.plays[special_index].name.strip() if special_index is not None else "",
                                     "PAT Fake FG", fg.index, None)
    forms_out, menus_out, form_rows = [], [], []
    used = Counter()
    for n, (f, fi) in enumerate(zip(forms, f_idx)):
        spec = oc.FORMATIONS[f]
        gk = group_key(f)
        ci = plan.index[gk]
        codes = plan.codes[gk]
        order = plan.order[gk]
        donor = info.formation_donor(spec, used)
        used[donor["index"]] += 1
        canon = spec.positions_cm()
        positions = tuple(canon[s] for s in order)
        mask = [ci]
        if gk == "11" and "Kings Long" in plan.index:
            # b77 p6s design: third-and-long shotgun 11 sets are owned by the code-9 twin, every 11 set lists both
            kl = plan.index["Kings Long"]
            mask.append(kl)
            if spec.align == "gun" and any(w in f for w in LONG_SETS):
                ci = kl
        edit = plan.edits.get(ci)
        fid = f"f{n:02d}"
        forms_out.append(packs.PackFormation(
            fid, f, positions, codes, packs.PackDonor(donor["index"], donor["name"]), fi,
            info.book.formations[fi].name.strip() if fi is not None else "", ci,
            category_positions=tuple(edit[0]) if edit else None, situation=tuple(spec.situation),
            category_mask=tuple(sorted(set(mask))), category_code=edit[1] if edit else None,
            category_name=edit[2] if edit else None))
        menu = order_menu(f, menus[f])
        menus_out.append((fid, tuple(play_ids[c.key] for c in menu)))
        form_rows.append(dict(formation=f, index=fi, family=om.formation_family(f), personnel=spec.personnel,
                              group=edit[2] if edit else info.cat_names.get(ci), align=spec.align, tag=spec.tag,
                              menu=[c.design.name for c in menu]))
    # Kings Long twin needs at least one formation naming its edit values
    if "Kings Long" in plan.index:
        kl = plan.index["Kings Long"]
        edit = plan.edits.get(kl)
        if edit and not any(f.category_index == kl for f in forms_out):
            # values ride on the first 11-personnel formation that lists it in its mask
            pass
    notes = (f"DESIGN (b776 pb1 v3, era {result['prof'].era}): {result['prof'].family} tree; Madden 27 family and "
             "personnel shares (Civil.GG playbook database) x the team's 2025 tendencies; retail-template runs, "
             "combo pass concepts, every retail route kind. No pre-snap motion, no RPO, no read option. "
             "All gameplay unwitnessed.")
    all_plays = tuple(plays_out) + ((special,) if special else ())
    pack = packs.PlaybookPack(
        packs.PackBook(team, f"SOFTDRINK 2K28 {team} Offense", "SOFTDRINK / Claude (pb1)", VERSION, "CC0-1.0",
                       notes=notes[:2000]),
        packs.PackBase(packs.book_fingerprint(info.body), len(info.book.formations), len(info.book.plays),
                       info.book.node_count),
        tuple(forms_out), all_plays, packs.OFFENSE_SCHEMA, tuple(menus_out))
    catalog = dict(team=team, version=VERSION, era=result["prof"].era, family=result["prof"].family,
                   capacity=cap, formations=form_rows, plays=rows, shared_links=result["shared"],
                   groups={k: dict(index=v, name=(plan.edits.get(v) or (None, None, info.cat_names.get(v)))[2],
                                   appended=v in plan.new) for k, v in plan.index.items()},
                   missing_groups=result["missing"], name_pool=names)
    return pack, catalog


# ---------------------------------------------------------------------------
# League driver
# ---------------------------------------------------------------------------

def semantic_digest(pack) -> str:
    by_play = {p.id: p for p in pack.plays}
    rows = [(pack.formations_by_id[f].slot_positions, pack.formations_by_id[f].position_codes,
             [(by_play[p].concept, by_play[p].play_flags, by_play[p].assignments) for p in menu])
            for f, menu in pack.menus]
    rows.append([(p.custom_name, p.assignments) for p in pack.plays if p.play_type == "special"])
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=list).encode()).hexdigest()


def build_league(image: Path, teams, *, era: str = "2020s", xbe: Path | None = None, write: bool = False,
                 out_dir: Path | None = None, progress=print, fit_iters: int = 1500) -> list[dict]:
    """Build the teams in order; league-wide route and concept counters push later books away from earlier ones."""
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    checker = Checker(xbe)
    league_routes, league_concepts = Counter(), Counter()
    manifest = []
    (v2.V2 / "catalogs").mkdir(exist_ok=True)
    with OuterImage(image) as img:
        for team in teams:
            retail = img.read_entry(BOOK_ENTRIES[team])
            res = build_book(retail, team, era=era, checker=checker, league_routes=league_routes,
                             league_concepts=league_concepts)
            pack, catalog = assemble(res, team)
            if fit_iters:
                pack, fit = fit_cpu(res, pack, retail, team, iters=fit_iters, log=progress)
                catalog["cpu_fit"] = fit
                for row, f in zip(catalog["formations"], pack.formations):
                    row["cpu_situation"] = list(f.situation) if f.situation else None
            check = packs.check_pack(pack)
            if not check.ok:
                raise SystemExit(f"{team}: {check.text()}")
            for c in res["chosen"].values():
                league_routes.update(c.routes)
                league_concepts[c.concept] += 1
            row = dict(team=team, pack=str(v2.pack_path(team).relative_to(ROOT)), formations=len(pack.formations),
                       plays=len(pack.plays), links=sum(len(m) for _, m in pack.menus),
                       appended_formations=sum(1 for f in pack.formations if f.replace_index is None),
                       appended_plays=sum(1 for p in pack.plays if p.replace_index is None),
                       semantic_sha256=semantic_digest(pack))
            manifest.append(row)
            if write:
                packs.save_pack(pack, v2.pack_path(team))
                (v2.V2 / "catalogs" / f"{team}.json").write_text(json.dumps(catalog, indent=1) + "\n",
                                                                 encoding="utf-8", newline="\n")
            if out_dir is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
                packs.save_pack(pack, out_dir / v2.pack_path(team).name)
                (out_dir / f"{team}_catalog.json").write_text(json.dumps(catalog, indent=1) + "\n", encoding="utf-8",
                                                              newline="\n")
            progress(f"{team} {row['formations']} formations ({row['appended_formations']} appended), "
                     f"{row['plays']} plays ({row['appended_plays']} appended + PAT fake), {row['links']} links")
    return manifest


def write_manifests(manifest: list[dict], era: str) -> None:
    (v2.V2 / "manifest.json").write_text(json.dumps(dict(status="DESIGN on PROVED OFFLINE grammar",
                                                         runtime_witness=False, version=VERSION, era=era,
                                                         generator="pb/v2/generator.py (b776 pb1)", teams=manifest),
                                                    indent=1) + "\n", encoding="utf-8", newline="\n")
    rows = [dict(team=r["team"], pack=r["pack"], plays=r["plays"], formations=r["formations"],
                 semantic_sha256=r["semantic_sha256"]) for r in manifest]
    (ROOT / "pb" / "league_manifest.json").write_text(json.dumps(dict(
        status="PROVED OFFLINE", runtime_witness=False,
        generator="pb/v2/generator.py (b776 pb1 v3); pb/build_league.py is the v0.5 reference generator",
        teams=rows), indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", type=Path, required=True, help="retail ISO (read only)")
    ap.add_argument("--xbe", type=Path, help="retail default.xbe for the native route check (recommended)")
    ap.add_argument("--team", action="append")
    ap.add_argument("--era", default="2020s", choices=sorted(ERA_PROFILES))
    ap.add_argument("--write", action="store_true", help="write data/playbooks packs, pb/v2 catalogs and manifests")
    ap.add_argument("--out", type=Path, help="also write packs and catalogs to this folder")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--fit-iters", type=int, default=1500, help="CPU fit iterations per team (0 = no fit)")
    args = ap.parse_args(argv)
    teams = args.team or list(packs.TEAM_BOOKS)
    write = args.write and args.era == "2020s"
    if args.workers > 1 and len(teams) > 1:
        # independent chains (league novelty counters are per chain); the parent writes the manifests
        from concurrent.futures import ProcessPoolExecutor
        chains = [teams[i::args.workers] for i in range(args.workers)]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futs = [pool.submit(build_league, args.image, c, era=args.era, xbe=args.xbe, write=write,
                                out_dir=args.out, fit_iters=args.fit_iters) for c in chains if c]
            rows = {r["team"]: r for f in futs for r in f.result()}
        manifest = [rows[t] for t in teams]
    else:
        manifest = build_league(args.image, teams, era=args.era, xbe=args.xbe, write=write, out_dir=args.out,
                                fit_iters=args.fit_iters)
    if args.write and not args.team and args.era == "2020s":
        write_manifests(manifest, args.era)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# CPU personnel design (b77 p6s fit, re-aimed at the v3 books)
# ---------------------------------------------------------------------------

def fit_cpu(result: dict, pack, retail: bytes, team: str, *, iters: int = 2500, seed: int = 1, log=None):
    """Fit formation CPU ratings (flag bits 21-29) and group ownership/membership to the team's 2025 charting with
    ``pb/v2/fit_cpu.py``'s search on the analytic selector; pistol sets stay in the Pistol group, other sets never
    move into it.  Returns (new pack, fit receipt)."""
    from pb.v2 import fit_cpu as fc
    from pb.v2 import selection_model as sm
    plan: GroupPlan = result["plan"]
    compiled = full_compile(retail, pack, team)
    imap = {int(k): v for k, v in compiled.report["category_menus"]["index_map"].items()} \
        if compiled.report["category_menus"].get("index_map") else None
    nf0 = len(result["info"].book.formations)
    order, k = [], 0
    for f in pack.formations:
        if f.replace_index is None:
            order.append(nf0 + k)
            k += 1
        else:
            order.append(f.replace_index)
    to_new = (lambda c: imap.get(c, c)) if imap else (lambda c: c)
    inv = {v: k for k, v in imap.items()} if imap else {}
    to_old = (lambda c: inv.get(c, c))
    bk = sm.book_from(compiled.replacement)
    design = fc.Design(bk, set(order))
    design.tags = {fi: oc.FORMATIONS[f.custom_name].tag for fi, f in zip(order, pack.formations)}
    pistol = {to_new(plan.index["Pistol"])} if "Pistol" in plan.index else set()
    groups = {}
    for ci, c in bk.cats.items():
        if c["id"] <= 10 and c.get("personnel") and ci not in bk.special_cats:
            groups.setdefault(design.exact[ci], []).append(ci)
    state = {}
    for fi, f in zip(order, pack.formations):
        bf = bk.forms[fi]
        own = bf["own"]
        mask = [c for c in range(26) if bf["mask"] >> c & 1]
        state[fi] = (own, sorted(set(mask) | {own}),
                     fc.clamp(design.tags[fi], tuple((bf["flags"] >> s) & 7 for s in (21, 24, 27))))

    class Groups(dict):
        def __getitem__(self, key):
            return dict.__getitem__(self, key)
    opts = Groups()
    for exact, cis in groups.items():
        opts[exact] = cis
    # pistol sets: only the Pistol group; everything else: never the Pistol group
    pistol_fi = {fi for fi, (own, _m, _r) in state.items() if own in pistol}
    original_search_groups = {k: [c for c in v if c not in pistol] or v for k, v in opts.items()}

    def search_groups_for(fi):
        return [next(iter(pistol))] if fi in pistol_fi else original_search_groups

    cells, gun_bins = fc.targets(team)
    before = fc.objective(design, state, cells, gun_bins)
    rnd = random.Random(seed)
    best = before
    keys = list(state)
    import copy
    for it in range(iters):
        cand = copy.deepcopy(state)
        fi = rnd.choice(keys)
        own, mask, r = cand[fi]
        options = [next(iter(pistol))] if fi in pistol_fi else original_search_groups[design.exact[own]]
        move = rnd.random()
        if move < 0.65 or len(options) == 1:
            r = list(r)
            r[rnd.randrange(3)] = rnd.randrange(5)
            cand[fi] = (own, mask, fc.clamp(design.tags.get(fi, ""), r))
        elif move < 0.85:
            new = rnd.choice(options)
            cand[fi] = (new, sorted(set(mask) - {own} | {new}), r)
            if not any(o == own for o, _m, _r in cand.values()):
                continue
        else:
            c = rnd.choice(options)
            if c == own:
                continue
            cand[fi] = (own, sorted(set(mask) ^ {c}), r)
        value = fc.objective(design, cand, cells, gun_bins)
        if value[0] < best[0] - 1e-6:
            state, best = cand, value
    design.apply(state)
    _e, rows = fc.score(design, cells, best[1])
    # write back: ratings, owner (pre-compaction index) and mask, and the group's edit values on its owners
    forms = []
    for fi, f in zip(order, pack.formations):
        own, mask, ratings = state[fi]
        own_o = to_old(own)
        mask_o = tuple(sorted(to_old(c) for c in mask))
        edit = plan.edits.get(own_o)
        stock_codes = f.position_codes
        forms.append(replace(f, situation=tuple(int(x) for x in ratings), category_index=own_o, category_mask=mask_o,
                             category_positions=tuple(edit[0]) if edit else None,
                             category_code=edit[1] if edit else None, category_name=edit[2] if edit else None,
                             position_codes=tuple(edit[0]) if edit else stock_codes))
    new_pack = replace(pack, formations=tuple(forms))
    receipt = dict(objective_before=round(before[0], 1), objective_after=round(best[0], 1), shotgun_weight=best[1],
                   cells=rows, iterations=iters)
    if log:
        log(f"{team}: CPU fit objective {before[0]:.1f} -> {best[0]:.1f} (shotgun weight {best[1]})")
    return new_pack, receipt


def full_compile(retail: bytes, pack, team: str):
    return full.compile_offense(retail, pack, asset_id="book:" + team)


from dataclasses import replace  # noqa: E402
from mod_editor.core import nfl2k5_complete_offense as full  # noqa: E402
