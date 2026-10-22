"""SOFTDRINK 2K28 modern offense catalog (b776 job pb1): every retail route, modern formations, combo pass
concepts, a retail-sourced run-blocking library and the must-have short-yardage and special plays.

This module extends ``nfl2k5_offense_concepts`` (it registers into ``ROUTES``, ``FORMATIONS`` and
``CONCEPTS``), so the Studio's Create a Play wizard and the book generator share it.  Ground truth is
the same as the base engine: every chain uses grammar the retail 2004 books already execute.

* Routes: the retail team books hold 164 distinct route-segment patterns over receivers (job pb1 census
  of all 32 books); every pattern used 7 or more times is named here or in the base engine, each with
  the retail chain it copies (``retail``).  A few marked ``invented`` combine retail segment kinds in an
  order retail does not use; they pass the validator and the native route initializer like the rest.
* Run blocking: each scheme copies one retail team-book play's line, back and receiver legs (named in
  ``RUN_SCHEMES``) and is re-aimed for the formation's strength.
* Pass concepts are combinations: a strong-side combo, a backside combo, a back job and a drop.  The
  generator (``pb/v2``) picks which combinations a team carries; each is a normal registered concept.
* No pre-snap motion, no RPO, no read option.  Nothing here is a gameplay witness.
"""
from __future__ import annotations

import re

from dataclasses import dataclass, field
import itertools
import math
from typing import Callable, Mapping, Sequence

from . import nfl2k5_offense_concepts as oc
from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib

FT, YD = oc.FT, oc.YD
QB, T, C, G, TE, WR, HB, FB = oc.QB, oc.T, oc.C, oc.G, oc.TE, oc.WR, oc.HB, oc.FB
seg, legf, move, pass_node, path, release, take, fake_take, start = (
    oc.seg, oc.legf, oc.move, oc.pass_node, oc.path, oc.release, oc.take, oc.fake_take, oc.start)
PlayDesign, PassPlan, ConceptUnavailable = oc.PlayDesign, oc.PassPlan, oc.ConceptUnavailable

#: concepts registered here that are generator combinations (kept out of the wizard's lists)
GENERATED: set[str] = set()
#: concept name -> extra metadata (family detail, key label, run scheme, screen type, must-have tag)
META: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Routes: the rest of the retail route tree (feet, retail counts from the pb1 census)
# ---------------------------------------------------------------------------

def _r(name, segments, depth, retail, blurb, family):
    if name in oc.ROUTES:
        raise ValueError(f"route {name} already exists")
    oc._route(name, segments, depth, retail, blurb, family)


_ft = oc._ft
_r("Deep Hook", lambda d: [(0, _ft(d)), (8, 30)], 10, "0:30 8:30 (594)", "ten yards, then settle back inside", "intermediate")
_r("Crossing Dig", lambda d: [(0, _ft(d)), (3, 45)], 8, "0:24 3:45 (297)", "eight yards, then a steep cut across the field", "crosser")
_r("Steep In", lambda d: [(0, _ft(d)), (3, 30)], 10, "0:30 3:30 (108)", "ten yards, then a sixty degree cut inside", "intermediate")
_r("Quick Angle", lambda d: [(0, _ft(d)), (3, 15)], 4, "0:12 3:15 (37)", "four yards, then a sharp cut under the linebackers", "quick")
_r("Bender", lambda d: [(1, 9), (0, _ft(d))], 12, "1:9 0:36 (266)", "inside release, then straight up the seam", "deep")
_r("Bend In", lambda d: [(1, 6), (0, _ft(d)), (4, 7)], 6, "1:6 0:18 4:7 (218)", "short inside release, up six, then flat across", "quick")
_r("Angle Cross", lambda d: [(2, _ft(d)), (4, 36)], 6, "2:18 4:36 (61)", "forty-five degrees inside, then across", "crosser")
_r("Slant Under", lambda d: [(1, _ft(d)), (4, 36)], 3, "1:9 4:36 (36)", "slant, then flatten under the linebackers", "crosser")
_r("Bang", lambda d: [(1, _ft(d))], 6, "1:18 (65)", "straight thirty degree glance inside off the release", "quick")
_r("Bang Post", lambda d: [(2, _ft(d))], 10, "2:30 (35)", "a post straight off the line", "deep")
_r("Release Out", lambda d: [(6, 6), (0, _ft(d)), (5, 24)], 4, "6:6 0:12 5:24 (12)", "outside release, up, then out", "quick")
_r("Angle Drag", lambda d: [(3, 6), (4, 75)], 0, "3:6 4:75 (13)", "two steps at sixty degrees, then flat across the formation", "crosser")
_r("Post Go", lambda d: [(0, _ft(d)), (2, 15), (0, 30)], 7, "0:21 2:15 0:30 (32)", "sell the post, then go", "double")
_r("Corner Go", lambda d: [(0, _ft(d)), (6, 15), (0, 30)], 7, "0:21 6:15 0:30 (32)", "sell the corner, then go", "double")
# b778 pb5: the sit is kind 7 (settle outside); kind 8 settled 0.9 yd inside and the slide out crossed the stem (a loop)
_r("Spot Out", lambda d: [(0, _ft(d)), (7, 3), (5, 15)], 5, "0:15 7:3 5:15 (29)", "five yards, sit, then slide out", "quick")
_r("Fade Stop", lambda d: [(6, 15), (0, _ft(d)), (8, 15)], 4, "6:15 0:12 8:15 (12)", "outside release, up, then settle", "intermediate")
_r("Fade Curl", lambda d: [(6, 6), (0, _ft(d)), (11, 6)], 6, "6:6 0:18 11:6 (6)", "outside release, then a curl back inside", "intermediate")
_r("Zig", lambda d: [(1, _ft(d)), (5, 24)], 14, "1:42 5:24 (15)", "long inside stem, then back out", "intermediate")
_r("Arrow Corner", lambda d: [(5, 6), (6, _ft(d))], 5, "5:6 6:15 (10)", "step out, then up to the corner", "quick")
_r("Steep Slant", lambda d: [(3, _ft(d))], 8, "3:24 (10)", "a sixty degree slant straight off the line", "quick")
_r("Comeback Go", lambda d: [(0, _ft(d)), (7, 3), (0, 24)], 10, "0:30 7:3 0:24 (6)", "sell the comeback, then go", "double")
_r("Return", lambda d: [(0, _ft(d)), (5, 3), (4, 24)], 8, "0:24 5:3 4:24 (10)", "sell the out, then come back inside", "intermediate")
_r("Slant Wheel", lambda d: [(1, _ft(d)), (5, 15), (0, 45)], 9, "1:27 5:15 0:45 (10)", "inside stem, out, then up the sideline", "double")
_r("Corner Curl", lambda d: [(0, _ft(d)), (6, 12), (11, 15)], 10, "0:30 6:12 11:15 (2)", "corner stem, then back inside", "intermediate")
_r("Post Dig", lambda d: [(0, _ft(d)), (2, 6), (4, 18), (1, 9), (0, 15)], 8, "0:24 2:6 4:18 1:9 0:15 (6)",
   "post stem, under, then up again", "crosser")
_r("Seam Out", lambda d: [(0, _ft(d)), (1, 9), (5, 24)], 9, "invented: 0 1 5", "seam stem, a glance inside, then out", "intermediate")
_r("Whip In", lambda d: [(0, _ft(d)), (5, 3), (4, 30)], 4, "invented: 0 5 4", "fake the out, whip back inside", "quick")
_r("Angle Out", lambda d: [(0, 3), (3, 9), (5, 30)], 0, "invented: 0 3 5", "back gains a yard, cuts inside, then breaks out", "back")
_r("Hook Corner", lambda d: [(0, _ft(d)), (8, 3), (6, 24)], 8, "invented: 0 8 6", "sell the hook, then break to the corner", "double")
_r("Release Block", lambda d: [(10, _ft(d))], 3, "10:9 (12)", "release straight up, then block downfield", "screen")
_r("Stem Block", lambda d: [(0, _ft(d)), (10, 3)], 9, "0:27 10:3 (171)", "run off the corner, then block", "screen")
_r("Back Out", lambda d: [(6, 15), (5, 30)], 0, "6:15 5:30 (197, check release)", "back angles out three steps, then flat", "back")
_r("Back In", lambda d: [(0, 15), (4, 30)], 0, "0:15 4:30 (20, check release)", "back up five, then in", "back")
_r("Back Cross", lambda d: [(0, 6), (2, 15), (4, 30)], 0, "0:6 then 2:15 4:30 (retail 36, check release)", "back gains two yards, angles inside, then across", "back")
_r("Back Hook", lambda d: [(0, 15), (8, 15)], 0, "0:15 8:15 (10, check release)", "back up five and settle", "back")
_r("Back Corner", lambda d: [(0, 24), (6, 24)], 0, "0:24 6:24 (19, check release)", "back up eight, then to the corner", "back")

# routes a back (in the backfield) can run cleanly from either side
BACK_ROUTES = ("Back Flat", "Swing", "Back Wheel", "Angle", "Back Seam", "Back Out", "Back In", "Back Cross",
               "Back Hook", "Back Corner", "Angle Out", "Texas")


# ---------------------------------------------------------------------------
# Formations (strong right; yards; personnel order oc.PERSONNEL_CODES)
# ---------------------------------------------------------------------------

#: b776 pb1: Pony personnel (two halfbacks, three receivers) for the backup-back package.
oc.PERSONNEL_CODES.setdefault("P2", (9, 41, 73, 42, 10))      # WR, WR2, WR3, HB2, HB
oc.PERSONNEL_CATEGORY_ID.setdefault("P2", 7)

#: formation name -> play-call family (the generator's formation-group axis)
FAMILY: dict[str, str] = {}
ERA: dict[str, tuple[str, ...]] = {}


def _family_of(name: str) -> str:
    for prefix, fam in (("Gun Wildcat", "Wildcat"), ("Gun Empty", "Empty"), ("Gun", "Gun"), ("Pistol", "Pistol"),
                        ("Singleback", "Singleback"), ("Ace", "Singleback"), ("I-Form", "I-Form"),
                        ("Strong Jumbo", "Goal Line"), ("Strong", "Strong"), ("Weak", "Weak"), ("Split Backs", "Split Backs"),
                        ("Full House", "Full House"), ("Wing T", "Wing T"), ("Goal Line", "Goal Line"),
                        ("Heavy", "Heavy"), ("Empty", "Empty")):
        if name.startswith(prefix):
            return fam
    return "Other"


def _wr_convention(personnel, skills):
    """Depth roles (nfl2k5_depth_roles) expect WR1 = X on the left outside, WR2 = Z on the right outside and WR3
    inside them: swap which receiver code stands on which spot (the geometry is unchanged)."""
    codes = oc.PERSONNEL_CODES[personnel]
    wr = [i for i, c in enumerate(codes) if c & 31 == WR]
    if len(wr) < 3:
        return skills
    spots = [skills[i] for i in wr]
    left = [p for p in spots if p[0] < 0]
    right = [p for p in spots if p[0] > 0]
    x = min(left, key=lambda p: p[0]) if left else max(spots, key=lambda p: abs(p[0]))
    rest = [p for p in spots if p is not x]
    z = max((p for p in rest if p[0] > 0), key=lambda p: p[0], default=None) or max(rest, key=lambda p: abs(p[0]))
    rest = [p for p in rest if p is not z]
    rest.sort(key=lambda p: abs(p[0]))                 # WR3 is the innermost of the rest
    out = list(skills)
    for i, p in zip(wr, [x, z] + rest):
        out[i] = p
    return out


def _f(name, personnel, align, skills, tag, situation, backs, blurb="", eras=("2020s", "2010s")):
    skills = _wr_convention(personnel, skills)
    oc._formation(name, personnel, align, skills, tag, situation, backs, blurb)
    FAMILY[name] = _family_of(name)
    ERA[name] = tuple(eras)


GUN_HB_R = (2.5, -5.27)
UC_HB = (0, -7)
PISTOL_HB = (0, -7)

# Names follow Madden NFL 27 where a set exists there (pb/research/m27_formations.md, from the Civil.GG playbook
# database: alignment read from its diagrams); the rest are CFB 27 sets or SOFTDRINK names.  Madden diagrams
# drawn left-strong are mirrored here (authored strong right; the game mirrors when a play is flipped).
# Alignment words -> yards: inline/attached (5, 0); tight split (8, 0); wide (17, 0); wing (6.5, -1.0);
# H-back / Y-off (4.5, -1.2); slot (9-11, -1.5); flanker (15-16, -1.5).

# --- 11 personnel: TE, X, Z, slot, HB --------------------------------------------------------------
_f("Gun Spread Y-Slot", "11", "gun", [(9, -1.5), (-17, 0), (17, 0), (-9, -1.5), GUN_HB_R], "pass", (4, 2, 1), 1,
   "Madden 27: 2x2 with the tight end in the right slot")
_f("Gun Bunch TE", "11", "gun", [(-5, 0), (8, 0), (10.5, -1.5), (6.5, -1.5), GUN_HB_R], "pass", (4, 2, 1), 1,
   "Madden 27 (17 books): receiver bunch right, tight end attached left")
_f("Gun Bunch X Nasty", "11", "gun", [(6.5, -1.2), (-8, 0), (5, 0), (8.5, -1.5), (-2.5, -5.27)], "pass", (4, 2, 1), 1,
   "Madden 27 (17 books): bunch with a receiver attached, X in a tight split")
_f("Gun Doubles Clamp Stack", "11", "gun", [(6, -1.2), (-8, 0), (8, 0), (-10, -1.5), GUN_HB_R], "pass", (4, 2, 1), 1,
   "Madden 27 (18 books): tight splits with a stacked receiver and a wing tight end")
_f("Gun Tight Y Off", "11", "gun", [(6.5, -1.0), (-8, 0), (17, 0), (-15, -1.5), GUN_HB_R], "pass", (4, 2, 1), 1,
   "Madden 27 (18 books): X tight with a flanker outside him, tight end on the wing")
_f("Gun Trips TE", "11", "gun", [(-5, 0), (17, 0), (13, -1.5), (9, -1.5), (-2.5, -5.27)], "pass", (4, 2, 1), 1,
   "Madden 27 (17 books): three receivers right, tight end attached left")
_f("Gun Trey Y-Flex", "11", "gun", [(-5, 0), (8, 0), (15, -1.5), (11, -1.5), (-2.5, -5.27)], "pass", (4, 2, 1), 1,
   "Madden 27 (16 books): trips right with the inside man in a tight split")
_f("Gun Y Off Trio Close", "11", "gun", [(6, -1.2), (-8, 0), (8.5, 0), (11.5, -1.5), GUN_HB_R], "pass", (4, 2, 1), 1,
   "Madden 27 (16 books): condensed 3x1 with the tight end off the ball")
_f("Gun Normal Y Off Close", "11", "gun", [(6.5, -1.0), (-17, 0), (12, 0), (-9, -1.5), GUN_HB_R], "pass", (4, 2, 1), 1,
   "Madden 27 (15 books): 2x2 with a wing tight end, Z inside the numbers")
_f("Gun Tight Open", "11", "gun", [(8, 0), (-8, 0), (15, -1.5), (-15, -1.5), GUN_HB_R], "pass", (4, 2, 1), 1,
   "Madden 27 (15 books): two tight splits (X and the tight end) with flankers outside")
_f("Gun Trey Open", "11", "gun", [(8, 0), (-17, 0), (15, -1.5), (11, -1.5), (-2.5, -5.27)], "pass", (4, 2, 1), 1,
   "Madden 27 (15 books): 3x1 with the tight end detached in a tight split")
_f("Gun Tight Slots", "11", "gun", [(6.5, -1.0), (-8, 0), (8, 0), (-6.5, -1.0), GUN_HB_R], "pass", (4, 2, 1), 1,
   "Madden 27: tight splits both sides with wings inside them")
_f("Gun Y Off Trips", "11", "gun", [(4.5, -1.2), (-17, 0), (17, 0), (10, -1.5), (-2.5, -5.27)], "pass", (4, 2, 1), 1,
   "Madden 27: 3x1 with the tight end off the ball beside the tackle")
_f("Gun Wing Trio", "11", "gun", [(6.5, -1.0), (-17, 0), (17, 0), (11, -1.5), (-2.5, -5.27)], "pass", (4, 2, 1), 1,
   "wing tight end with the slot and Z outside him")
_f("Gun Wildcat", "11", "gun", [(5, 0), (-17, 0), (16, -1.5), (-9, -1.5), (2.0, -5.3)], "base", (3, 2, 1), 1,
   "Madden 27 Wildcat idea in the gun: the back beside the QB takes direct snaps")
_f("Pistol Bunch TE", "11", "pistol", [(-5, 0), (8, 0), (10.5, -1.5), (6.5, -1.5), PISTOL_HB], "base", (3, 2, 1), 1,
   "Madden 27 (11 books): pistol bunch right, tight end attached left")
_f("Pistol Y Off Trips", "11", "pistol", [(6, -1.5), (-17, 0), (17, 0), (11, -1.5), PISTOL_HB], "base", (3, 2, 1), 1,
   "Madden 27: pistol trips with the tight end off the ball as #3")
_f("Pistol Doubles Y Off", "11", "pistol", [(4.5, -1.2), (-17, 0), (17, 0), (-9, -1.5), PISTOL_HB], "base", (3, 2, 1), 1,
   "Madden 27: pistol 2x2 with the tight end as an H-back")
_f("Pistol Trips", "11", "pistol", [(-5, 0), (17, 0), (13, -1.5), (9, -1.5), PISTOL_HB], "base", (3, 2, 1), 1,
   "Madden 27: pistol trips right, tight end attached left")
_f("Singleback Bunch X Nasty", "11", "uc", [(6.5, -1.2), (-8, 0), (5, 0), (8.5, -1.5), UC_HB], "base", (3, 2, 1), 1,
   "Madden 27 (18 books): bunch with a receiver attached, X in a tight split")
_f("Singleback Tight Y Off", "11", "uc", [(6.5, -1.0), (-8, 0), (8, 0), (-6.5, -1.0), UC_HB], "base", (3, 2, 1), 1,
   "Madden 27 (21 books): tight splits both sides with wings inside them")
_f("Singleback Bunch TE", "11", "uc", [(-5, 0), (8, 0), (10.5, -1.5), (6.5, -1.5), UC_HB], "base", (3, 2, 1), 1,
   "Madden 27 (10 books): bunch right, tight end attached left")
_f("Singleback Trips", "11", "uc", [(-5, 0), (17, 0), (13, -1.5), (9, -1.5), UC_HB], "base", (3, 2, 1), 1,
   "Madden 27: three receivers right, tight end attached left")
_f("Singleback Y Off Trey", "11", "uc", [(4.5, -1.2), (-17, 0), (17, 0), (10, -1.5), UC_HB], "base", (3, 2, 1), 1,
   "3x1 under centre with the tight end as an H-back")
_f("Empty Trey", "11", "uc", [(5, 0), (-17, 0), (17, -1.5), (-9, -1.5), (11, -1.5)], "empty", (4, 3, 1), 0,
   "under centre empty: the back split out (QB keep and quick game)")

# --- 12 personnel: TE, X, Z, TE2, HB -----------------------------------------------------------------
_f("Singleback Deuce Close", "12", "uc", [(6.5, -1.0), (-8, 0), (8, 0), (-6.5, -1.0), UC_HB], "base", (2, 1, 2), 1,
   "Madden 27 (25 books): tight splits with a wing tight end inside each")
_f("Gun Deuce Close", "12", "gun", [(6.5, -1.0), (-8, 0), (8, 0), (-6.5, -1.0), GUN_HB_R], "pass", (3, 2, 1), 1,
   "Madden 27 (22 books): shotgun with two wing tight ends and tight splits")
_f("Pistol Deuce Close", "12", "pistol", [(6.5, -1.0), (-8, 0), (8, 0), (-6.5, -1.0), PISTOL_HB], "base", (3, 1, 2), 1,
   "Madden 27 (13 books): pistol with two wing tight ends")
_f("Gun Wing Slot Offset", "12", "gun", [(5, 0), (-17, 0), (-9, -1.5), (8.5, -1.5), GUN_HB_R], "pass", (4, 2, 1), 1,
   "Madden 27 (24 books): receivers left, two tight ends right (attached and slot)")
_f("Singleback Wing Slot", "12", "uc", [(5, 0), (-17, 0), (-9, -1.5), (6.5, -1.2), UC_HB], "base", (2, 1, 2), 1,
   "Madden 27 (13 books): X and the slot left, tight end and wing right")
_f("Singleback Ace Close", "12", "uc", [(5, 0), (-9, -1.5), (9, -1.5), (-5, 0), UC_HB], "base", (2, 1, 3), 1,
   "Madden 27: two attached tight ends with both receivers in tight")
_f("Singleback Ace Slot", "12", "uc", [(5, 0), (15, -1.5), (10, -1.5), (-5, 0), UC_HB], "base", (2, 1, 2), 1,
   "Madden 27: two attached tight ends, both receivers right")
_f("Singleback H Back", "12", "uc", [(5, 0), (-17, 0), (16, -1.5), (-4, -1.2), UC_HB], "base", (2, 1, 2), 1,
   "tight end attached, the second as an H-back on the other side")
_f("Singleback Ace Bunch", "12", "uc", [(8, 0), (-17, 0), (10, -1.5), (6.5, -1.5), UC_HB], "base", (2, 2, 2), 1,
   "Madden 27 Singleback Bunch Ace: bunch with two tight ends")
_f("Gun Ace Flex", "12", "gun", [(5, 0), (-17, 0), (17, -1.5), (-9, -1.5), (2.5, -5.27)], "pass", (4, 2, 1), 1,
   "2x2 with the second tight end flexed into the slot")
_f("Gun Wing Stack", "12", "gun", [(5, 0), (-17, 0), (-14, -1.5), (8.5, -1.5), GUN_HB_R], "pass", (4, 2, 1), 1,
   "Madden 27: stacked receivers left, two tight ends right")
_f("Pistol Ace Wing", "12", "pistol", [(5, 0), (-17, 0), (16, -1.5), (6.5, -1.2), PISTOL_HB], "base", (3, 1, 2), 1,
   "pistol, tight end attached with the second on the wing")
_f("Pistol Y Trips", "12", "pistol", [(5, 0), (-17, 0), (17, -1.5), (10, -1.5), PISTOL_HB], "base", (3, 1, 2), 1,
   "pistol 3x1 with the second tight end in the slot")

# --- 13 personnel: TE, X, TE2, TE3, HB (a SOFTDRINK group: retail books have none) -------------------
oc.PERSONNEL_CODES.setdefault("13", (8, 9, 40, 72, 10))
oc.PERSONNEL_CATEGORY_ID.setdefault("13", 1)
_f("Singleback Wing Pair", "13", "uc", [(5, 0), (-17, 0), (6.5, -1.0), (9, -1.5), UC_HB], "short", (1, 2, 4), 1,
   "Madden 27 (21 books): three tight ends right (attached, wing, slot), X left")
_f("Singleback Wing Tight", "13", "uc", [(5, 0), (-15, -1.5), (6.5, -1.0), (-5, 0), UC_HB], "short", (1, 2, 4), 1,
   "Madden 27 (11 books): two attached tight ends with a wing, flanker left")
_f("Singleback Wing Tight Nasty", "13", "uc", [(5, 0), (-8, 0), (6.5, -1.0), (-6.5, -1.0), UC_HB], "short", (1, 2, 4), 1,
   "Madden 27 (10 books): wings both sides, X in a tight split")
_f("Pistol Wing Pair", "13", "pistol", [(5, 0), (-17, 0), (6.5, -1.0), (9, -1.5), PISTOL_HB], "short", (1, 2, 4), 1,
   "pistol with three tight ends right")

# --- 21 personnel: TE, X, Z, FB, HB ------------------------------------------------------------------
_f("I-Form Y Off Close", "21", "uc", [(6.5, -1.0), (-8, 0), (8, 0), (0, -4.5), (0, -7.0)], "base", (2, 1, 2), 2,
   "Madden 27 (23 books): tight splits, wing tight end, fullback and tailback")
_f("I-Form Slot", "21", "uc", [(5, 0), (-17, 0), (10, -1.5), (0, -4.5), (0, -7.0)], "base", (2, 1, 2), 2,
   "Madden 27: I-form with the flanker in the slot")
_f("I-Form Close", "21", "uc", [(5, 0), (-9, 0), (9, -1.5), (0, -4.5), (0, -7.0)], "base", (1, 1, 3), 2,
   "Madden 27 (12 books): I-form with both receivers in tight: crack toss and play action")
_f("Strong Close", "21", "uc", [(5, 0), (-9, 0), (9, -1.5), (1.7, -4.5), (0, -7.0)], "base", (1, 1, 3), 2,
   "Madden 27 (11 books): fullback offset strong, tight receiver splits")
_f("Strong Wing", "21", "uc", [(-5, 0), (17, 0), (9, -1.5), (-1.7, -4.5), (0, -7.0)], "base", (2, 1, 2), 2,
   "Madden 27 (12 books): both receivers right, tight end left with the fullback offset to him")
_f("Weak Close", "21", "uc", [(5, 0), (-9, 0), (9, -1.5), (-1.7, -4.5), (0, -7.0)], "base", (1, 1, 3), 2,
   "Madden 27: fullback offset weak, tight receiver splits")
_f("Weak I Twins", "21", "uc", [(5, 0), (-17, 0), (-10, -1.5), (-1.7, -4.5), (0, -7.0)], "base", (2, 1, 2), 2,
   "fullback offset weak, both receivers left")
_f("Pistol Weak", "21", "pistol", [(5, 0), (-17, 0), (16, -1.5), (-2.0, -4.3), PISTOL_HB], "base", (3, 1, 2), 2,
   "pistol with the fullback offset weak")
_f("Pistol Strong Y Off Close", "21", "pistol", [(6.5, -1.0), (-8, 0), (8, 0), (2.0, -4.3), PISTOL_HB], "base", (3, 1, 2), 2,
   "Madden 27: pistol, tight splits, wing tight end, fullback offset strong")
_f("Singleback FB Wing", "21", "uc", [(5, 0), (-17, 0), (16, -1.5), (-4.5, -1.2), UC_HB], "base", (2, 1, 2), 1,
   "one back with the fullback as a wing on the weak side")
_f("Wing T", "21", "uc", [(5, 0), (-17, 0), (6.5, -1.0), (0, -4.5), (-2.5, -5.0)], "short", (1, 2, 4), 2,
   "CFB wing-T: flanker on the wing, fullback behind the QB, halfback offset")
_f("Gun Split Y Off", "21", "gun", [(6.5, -1.0), (-9, 0), (9, 0), (-2.5, -5.27), (2.5, -5.27)], "pass", (3, 2, 1), 2,
   "shotgun 21 with tight splits, a wing tight end and a back each side")

# --- 22 personnel: TE, X, TE2, FB, HB ----------------------------------------------------------------
_f("Full House", "22", "uc", [(5, 0), (-17, 0), (2.0, -4.5), (-2.0, -4.5), (0, -7.0)], "short", (1, 2, 4), 2,
   "Madden 27 Full House: the H and the fullback side by side, tailback behind")
_f("Pistol Full House", "22", "pistol", [(5, 0), (-17, 0), (2.2, -4.0), (-2.2, -4.0), PISTOL_HB], "short", (1, 2, 4), 2,
   "Madden 27 (5 books): pistol with the H and the fullback beside the QB")
_f("I-Form Wing", "22", "uc", [(5, 0), (-17, 0), (6.5, -1.2), (0, -4.5), (0, -7.0)], "short", (1, 2, 4), 2,
   "Madden 27 (22 books): both tight ends right (attached and wing), fullback and tailback")
_f("Strong H Tight Close", "22", "uc", [(5, 0), (9, -1.5), (-5, 0), (1.7, -4.5), (0, -7.0)], "short", (0, 2, 4), 2,
   "Madden 27: two attached tight ends, receiver in the slot, fullback offset strong")
_f("Weak Wing", "22", "uc", [(5, 0), (-17, 0), (6.5, -1.2), (-1.7, -4.5), (0, -7.0)], "short", (1, 2, 4), 2,
   "Madden 27: tight end and wing right, fullback offset weak")
_f("Pistol Jumbo", "22", "pistol", [(5, 0), (-16, -1.5), (-5, 0), (2.0, -4.3), PISTOL_HB], "short", (1, 2, 4), 2,
   "pistol with two attached tight ends and the fullback offset")

# --- 23 personnel: TE, TE2, TE3, FB, HB (goal line) ------------------------------------------------
_f("Goal Line Sneak", "23", "uc", [(5, 0), (-5, 0), (0, -6.5), (1.1, -4.6), (-1.1, -4.6)], "goal", (0, 4, 5), 2,
   "Madden 27 tush-push set (7 books): three blockers stacked behind the QB at retail spacing (b777 tp1: the "
   "backs stood 1.3 yd from the QB and 1.4 yd apart, closer than any retail set (QB to back 2.7 yd, back to back "
   "2.1 yd); the QB's one-yard step back landed between them and the game lagged)")
_f("Strong Jumbo", "23", "uc", [(5, 0), (-5, 0), (6.5, -1.0), (1.5, -4.0), (0, -6.5)], "goal", (0, 3, 4), 2,
   "Madden 27: three tight ends (wing strong), fullback offset strong")
_f("Singleback Ace Double Wing", "23", "uc", [(5, 0), (-5, 0), (6.5, -1.0), (-6.5, -1.0), UC_HB], "goal", (0, 3, 4), 1,
   "Madden 27 (6 books): two attached tight ends with a wing on each side, one back")

# --- 20 personnel: WR, WR2, WR3, FB, HB --------------------------------------------------------------
_f("Pistol Strong Slot", "20", "pistol", [(-17, 0), (17, 0), (9, -1.5), (2.0, -4.3), PISTOL_HB], "base", (3, 2, 1), 2,
   "Madden 27: pistol with three receivers and the fullback offset strong")
_f("I-Form Slot Flex", "20", "uc", [(-17, 0), (17, 0), (10, -1.5), (0, -4.5), (0, -7.0)], "base", (2, 2, 2), 2,
   "I-form with three receivers")

# --- Pony (HB2 + HB, three receivers): the backup-back package ------------------------------------------
_f("Gun Split Close", "P2", "gun", [(-8, 0), (8, 0), (11, -1.5), (-2.5, -5.27), (2.3, -5.27)], "pass", (3, 2, 1), 2,
   "Madden 27 (12 books): two halfbacks beside the QB, receivers tight: the second back's package")
_f("Pistol Pony", "P2", "pistol", [(-17, 0), (17, 0), (-9, -1.5), (2.0, -4.3), PISTOL_HB], "base", (3, 2, 1), 2,
   "pistol with the second halfback offset: his runs and routes")

# --- 10 / 00 personnel ---------------------------------------------------------------------------------
_f("Pistol Spread", "10", "pistol", [(-17, 0), (17, 0), (9, -1.5), (-9, -1.5), PISTOL_HB], "spread", (3, 2, 1), 1,
   "Madden 27: pistol four wide 2x2")

# family for the base engine's formations too
for _name in oc.FORMATIONS:
    FAMILY.setdefault(_name, _family_of(_name))
    ERA.setdefault(_name, ("2020s", "2010s"))
for _name in ("Heavy Wing", "Ace Jumbo", "I-Form Tight"):
    FAMILY[_name] = "Heavy"
FAMILY["Empty"] = "Empty"


def formation_family(name: str) -> str:
    return FAMILY.get(name) or _family_of(name)


# ---------------------------------------------------------------------------
# Combo pass concepts: a call-side combo + a backside combo + a back job + a drop
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SideCombo:
    """Routes for the receivers on one side, #1 (outside) to #n (inside)."""
    name: str
    routes: tuple                 # spec per position: ("route", name, depth) | ("block",) ...
    key: int                      # index of the featured route (the call's primary when this side is read first)
    order: tuple                  # read order within the side (indices)
    family: str                   # quick | dropback | deep
    tags: tuple = ()

    @property
    def n(self) -> int:
        return len(self.routes)


def _sc(name, routes, key, order=None, family="dropback", tags=()):
    order = tuple(order) if order else (key,) + tuple(i for i in range(len(routes)) if i != key)
    return SideCombo(name, tuple(("route",) + tuple(r) if isinstance(r, tuple) else ("route", r) for r in routes),
                     key, order, family, tuple(tags))


#: call-side combos by receiver count (Madden 27 concept names where one exists; research section 3)
STRONG_COMBOS: dict[int, list[SideCombo]] = {
    3: [
        _sc("Flood", [("Go", 15), ("Sail", 10), ("Flat",)], 1, (1, 2, 0)),
        _sc("Deep Flood", [("Post", 14), ("Sail", 12), ("Flat",)], 1, (1, 2, 0), "deep"),
        _sc("Levels", [("Dig", 12), ("In", 5), ("Seam", 15)], 1, (1, 0, 2)),
        _sc("Snag", [("Snag", 4), ("Flag", 6), ("Arrow",)], 0, (0, 1, 2), "quick"),
        _sc("Spot", [("Corner", 10), ("Snag", 4), ("Flat",)], 1, (1, 2, 0), "quick"),
        _sc("Stick", [("Go", 15), ("Arrow",), ("Stick", 6)], 2, (2, 1, 0), "quick"),
        _sc("Spacing", [("Hitch", 6), ("Stick", 5), ("Flat",)], 1, (1, 2, 0), "quick"),
        _sc("Verticals", [("Go", 15), ("Seam", 15), ("Bender", 12)], 1, (1, 2, 0), "deep"),
        _sc("Smash", [("Hitch", 5), ("Corner", 10), ("Flat",)], 1, (1, 0, 2)),
        _sc("Drive", [("Go", 15), ("Dig", 12), ("Drag", 2)], 2, (2, 1, 0)),
        _sc("Bench", [("Out", 12), ("Arrow",), ("Seam", 15)], 0, (0, 1, 2)),
        _sc("Dagger", [("Dig", 15), ("Seam", 15), ("Flat",)], 0, (0, 1, 2)),
        _sc("Mills", [("Dig", 13), ("Post", 12), ("Flat",)], 1, (1, 0, 2), "deep"),
        _sc("Choice", [("Go", 15), ("Whip", 4), ("Seam", 15)], 1, (1, 2, 0), "quick"),
        _sc("Sail", [("Go", 15), ("Sail", 12), ("Whip", 4)], 1, (1, 2, 0)),
        _sc("Curls", [("Curl", 11), ("Hook", 8), ("Flat",)], 1, (1, 0, 2)),
        _sc("Curl Combo", [("Curl", 11), ("Seam", 15), ("Flat",)], 0, (0, 2, 1)),
        _sc("Slants", [("Slant", 3), ("Slant", 2), ("Arrow",)], 1, (1, 0, 2), "quick"),
        _sc("Corner Strike", [("Comeback", 13), ("Corner", 10), ("Flat",)], 1, (1, 0, 2)),
        _sc("Cross Dig", [("Go", 15), ("Crossing Dig", 8), ("Flat",)], 1, (1, 2, 0)),
        _sc("Return Flood", [("Go", 15), ("Return", 8), ("Flat",)], 1, (1, 2, 0)),
        _sc("Seam Levels", [("Comeback", 14), ("Seam Out", 9), ("In", 5)], 1, (1, 2, 0)),
        _sc("Deep Hooks", [("Deep Hook", 10), ("Steep In", 10), ("Arrow",)], 0, (0, 1, 2)),
        _sc("Zig Flat", [("Go", 15), ("Zig", 12), ("Flat",)], 1, (1, 2, 0)),
        _sc("Post Wheel", [("Post", 12), ("Wheel", 2), ("Seam", 14)], 1, (1, 0, 2), "deep", ("shot",)),
        _sc("Sluggo Seam", [("Slant and Go", 1), ("Seam", 15), ("Flat",)], 0, (0, 1, 2), "deep", ("shot",)),
        _sc("Stick Nod", [("Go", 15), ("Arrow",), ("Hitch and Go", 5)], 2, (2, 1, 0), "deep", ("shot",)),
        _sc("Scat", [("Quick Out", 5), ("Spot Out", 5), ("Bang", 6)], 1, (1, 2, 0), "quick"),
        _sc("Y Trail", [("Go", 15), ("Drag", 3), ("Over", 9)], 2, (2, 1, 0)),
        _sc("Cluster Wheel", [("Slant Wheel", 9), ("Quick Angle", 4), ("Arrow Corner", 5)], 0, (0, 1, 2), "dropback"),
        # deep shots: the featured route finishes 20+ yards down (the coach profile's deep class)
        _sc("Deep Post", [("Post", 18), ("Seam", 15), ("Flat",)], 0, (0, 1, 2), "deep", ("shot",)),
        _sc("Go Shot", [("Go", 22), ("Dig", 12), ("Flat",)], 0, (0, 1, 2), "deep", ("shot",)),
        _sc("Seam Shot", [("Comeback", 13), ("Seam", 22), ("Flat",)], 1, (1, 0, 2), "deep", ("shot",)),
        _sc("Deep Over", [("Go", 15), ("Post", 12), ("Deep Cross", 17)], 2, (2, 1, 0), "deep", ("shot",)),
        _sc("Skinny Shot", [("Skinny Post", 17), ("Out", 10), ("Arrow",)], 0, (0, 1, 2), "deep", ("shot",)),
    ],
    2: [
        _sc("Smash", [("Hitch", 5), ("Corner", 10)], 1, (1, 0)),
        _sc("Slant Flat", [("Slant", 3), ("Arrow",)], 0, (0, 1), "quick"),
        _sc("Stick", [("Go", 15), ("Stick", 6)], 1, (1, 0), "quick"),
        _sc("Curl Flat", [("Curl", 11), ("Flat",)], 0, (0, 1)),
        _sc("Hitch Seam", [("Hitch", 6), ("Seam", 15)], 0, (0, 1), "quick"),
        _sc("Double Slants", [("Slant", 3), ("Slant", 2)], 1, (1, 0), "quick"),
        _sc("Scissors", [("Post", 14), ("Corner", 6)], 1, (1, 0), "deep"),
        _sc("Mills", [("Dig", 13), ("Post", 12)], 1, (1, 0), "deep"),
        _sc("Dagger", [("Dig", 15), ("Seam", 15)], 0, (0, 1)),
        _sc("Verticals", [("Go", 15), ("Seam", 15)], 1, (1, 0), "deep"),
        _sc("Sail", [("Go", 15), ("Sail", 12)], 1, (1, 0)),
        _sc("Bench", [("Out", 12), ("Arrow",)], 0, (0, 1)),
        _sc("Levels", [("Dig", 12), ("In", 5)], 1, (1, 0)),
        _sc("Post Wheel", [("Post", 12), ("Wheel", 2)], 1, (1, 0), "deep", ("shot",)),
        _sc("Out and Up", [("Out and Up", 7), ("Hitch", 6)], 0, (0, 1), "deep", ("shot",)),
        _sc("China", [("Go", 15), ("Pivot", 3)], 1, (1, 0), "quick"),
        _sc("Whip", [("Go", 15), ("Whip", 4)], 1, (1, 0), "quick"),
        _sc("Slot Fade", [("Quick Out", 5), ("Fade", 10)], 1, (1, 0), "quick", ("red",)),
        _sc("Switch", [("Bender", 12), ("Fade", 12)], 1, (1, 0), "deep"),
        _sc("Bang Hitch", [("Hitch", 6), ("Bang Post", 10)], 1, (1, 0)),
        _sc("Comeback Seam", [("Comeback", 14), ("Seam", 15)], 0, (0, 1)),
        _sc("Quick Outs", [("Quick Out", 5), ("Stick", 6)], 0, (0, 1), "quick"),
        _sc("Spot Out", [("Hitch", 6), ("Spot Out", 5)], 1, (1, 0), "quick"),
        _sc("Steep In Seam", [("Steep In", 10), ("Seam", 15)], 0, (0, 1)),
        _sc("Out Seam", [("Out", 10), ("Seam", 15)], 0, (0, 1)),
        _sc("Snag", [("Snag", 4), ("Arrow Corner", 5)], 0, (0, 1), "quick"),
        _sc("Hook Corner", [("Hook Corner", 8), ("Flat",)], 0, (0, 1), "deep", ("shot",)),
        _sc("Corner Post", [("Corner Post", 10), ("Drag", 3)], 0, (0, 1), "deep", ("shot",)),
        _sc("Post Go", [("Post Go", 7), ("Quick Angle", 4)], 0, (0, 1), "deep", ("shot",)),
        _sc("Fade Curl", [("Fade Curl", 6), ("Release Out", 4)], 0, (0, 1)),
        _sc("Deep Post", [("Post", 18), ("Flat",)], 0, (0, 1), "deep", ("shot",)),
        _sc("Go Shot", [("Go", 22), ("Hitch", 6)], 0, (0, 1), "deep", ("shot",)),
        _sc("Seam Shot", [("Hitch", 6), ("Seam", 22)], 1, (1, 0), "deep", ("shot",)),
        _sc("Post Corner Shot", [("Post Corner", 16), ("Drag", 3)], 0, (0, 1), "deep", ("shot",)),
        _sc("Double Move", [("Out and Up", 7), ("Seam", 15)], 0, (0, 1), "deep", ("shot",)),
    ],
    4: [
        _sc("Quads Flood", [("Go", 15), ("Seam", 15), ("Sail", 10), ("Flat",)], 2, (2, 3, 1, 0)),
        _sc("Quads Stick", [("Go", 15), ("Hitch", 6), ("Arrow",), ("Stick", 6)], 3, (3, 2, 1, 0), "quick"),
        _sc("Quads Verts", [("Go", 15), ("Seam", 15), ("Bender", 12), ("Seam", 14)], 1, (1, 2, 3, 0), "deep"),
    ],
}
STRONG_COMBOS[1] = []          # a lone call-side receiver uses the backside list (iso routes)

#: backside combos: one receiver (an isolation route) or two
WEAK_COMBOS: dict[int, list[SideCombo]] = {
    1: [_sc(n, [r], 0, family=f) for n, r, f in (
        ("Dig", ("Dig", 12), "dropback"), ("Post", ("Post", 12), "deep"), ("Flag", ("Flag", 12), "dropback"),
        ("Curl", ("Curl", 10), "dropback"), ("Comeback", ("Comeback", 13), "dropback"), ("Out", ("Out", 10), "dropback"),
        ("Slant", ("Slant", 3), "quick"), ("Hitch", ("Hitch", 6), "quick"), ("Fade", ("Fade", 12), "deep"),
        ("Skinny Post", ("Skinny Post", 10), "deep"), ("Corner", ("Corner", 10), "dropback"),
        ("Deep Hook", ("Deep Hook", 10), "dropback"), ("Crossing Dig", ("Crossing Dig", 8), "dropback"),
        ("Steep In", ("Steep In", 10), "dropback"), ("Zig", ("Zig", 14), "dropback"), ("Return", ("Return", 8), "dropback"),
        ("Stop and Go", ("Stop and Go", 10), "deep"), ("Sluggo", ("Slant and Go", 1), "deep"),
        ("Post Corner", ("Post Corner", 8), "deep"), ("Comeback Go", ("Comeback Go", 10), "deep"),
        ("Quick Out", ("Quick Out", 5), "quick"), ("Bang", ("Bang", 6), "quick"), ("Steep Slant", ("Steep Slant", 8), "quick"),
        ("Fade Stop", ("Fade Stop", 4), "dropback"), ("Corner Curl", ("Corner Curl", 10), "dropback"),
        ("Whip In", ("Whip In", 4), "quick"), ("Over", ("Over", 9), "dropback"), ("Hitch and Go", ("Hitch and Go", 5), "deep"),
        ("Deep Go", ("Go", 22), "deep"), ("Deep Fade", ("Fade", 20), "deep"), ("Bomb Post", ("Post", 18), "deep"),
    )],
    2: [_sc(n, rs, k, family=f) for n, rs, k, f in (
        ("Slants", [("Slant", 3), ("Slant", 2)], 1, "quick"), ("Smash", [("Hitch", 5), ("Corner", 10)], 1, "dropback"),
        ("Stick", [("Comeback", 13), ("Stick", 6)], 1, "quick"), ("Curls", [("Curl", 10), ("Flat",)], 0, "dropback"),
        ("Seams", [("Hitch", 6), ("Seam", 15)], 1, "quick"), ("Corner Smash", [("Corner", 12), ("Hitch", 5)], 0, "dropback"),
        ("Outs", [("Quick Out", 5), ("Stick", 6)], 0, "quick"), ("Dagger", [("Dig", 15), ("Seam", 15)], 0, "dropback"),
        ("Levels", [("Dig", 12), ("In", 5)], 1, "dropback"), ("Slant Flat", [("Slant", 3), ("Arrow",)], 0, "quick"),
        ("Comebacks", [("Comeback", 14), ("Seam", 14)], 0, "dropback"), ("Whip", [("Curl", 12), ("Whip", 4)], 1, "quick"),
        ("Post Dig", [("Post", 12), ("Dig", 10)], 0, "deep"), ("Hitches", [("Hitch", 6), ("Hitch", 5)], 0, "quick"),
        ("Bench", [("Out", 12), ("Arrow",)], 0, "dropback"), ("Out Drag", [("Seam Out", 9), ("Drag", 3)], 0, "dropback"),
    )],
    0: [SideCombo("", (), 0, (), "dropback")],
}

#: back jobs: ("check", route, hold) releases after blocking; ("route", name) free release; ("block",)
BACK_JOBS = {
    "quick": [("block",), ("check", "Back Flat", 0.6), ("route", "Flat"), ("check", "Angle", 0.6), ("route", "Swing")],
    "dropback": [("check", "Back Flat", 1.5), ("check", "Swing", 1.2), ("check", "Back Out", 1.5),
                 ("check", "Back In", 1.5), ("check", "Back Hook", 1.5), ("route", "Back Wheel"), ("route", "Angle"),
                 ("check", "Back Cross", 1.5), ("block",)],
    "deep": [("block",), ("check", "Back Flat", 1.8), ("check", "Back Hook", 1.8), ("route", "Back Seam"),
             ("check", "Back Corner", 1.5), ("route", "Back Wheel")],
}
DROPS = {"quick": ("quick", "quick", "quick"), "quick3": ("quick3", "quick", "quick"),
         "dropback": ("dropback", "dropback", "dropback"), "deep": ("deep", "dropback", "dropback"),
         "max": ("deep", "max", "dropback"), "rollout": ("rollout", "dropback", "rollout"),
         "pa": ("pa", "pa", "pa"), "boot": ("boot", "pa", "pa_rollout")}
LETTER = {(WR, 0): "X", (WR, 1): "Z", (WR, 2): "Slot", (WR, 3): "Slot", (WR, 4): "Slot",
          (TE, 0): "Y", (TE, 1): "U", (TE, 2): "U", (HB, 0): "HB", (HB, 1): "RB2", (FB, 0): "FB"}


def letter(code: int) -> str:
    return LETTER.get((code & 31, code >> 5), "")


def _side_labels(ctx: oc.FormationContext, side: str) -> list[str]:
    return [f"{side}{i}" for i in range(1, 6) if ctx.slot(f"{side}{i}") is not None]


@dataclass(frozen=True)
class ComboCall:
    strong: str                    # STRONG_COMBOS name ("" when the call side has one receiver)
    weak: str                      # WEAK_COMBOS name ("" for none)
    back: tuple                    # back job
    drop: str                      # DROPS key
    focus: str = "strong"          # strong | weak | back
    b2: tuple = ("block",)         # second back's job
    flip: bool = False             # read the backside combo as the call side (iso concepts)
    variant: int = 0               # b776 pb1: which breaking route replaces each plain vertical filler (0 = as drawn)

    def key(self) -> tuple:
        return (self.strong, self.weak, self.back, self.drop, self.focus, self.b2, self.variant)


def _find(table, n, name):
    for c in table.get(n, ()):
        if c.name == name:
            return c
    raise ConceptUnavailable(f"no {n}-receiver combo {name!r}")


def combo_design(ctx: oc.FormationContext, call: ComboCall, codes=None) -> PlayDesign:
    """Build a combo call in ``ctx``; raises ConceptUnavailable when the shape does not fit."""
    s_labels, w_labels = _side_labels(ctx, "S"), _side_labels(ctx, "W")
    if len(s_labels) == 1 and len(w_labels) == 1:
        # 1x1 (heavy sets): treat the tight end side as the call side with an iso route
        pass
    strong = _find(STRONG_COMBOS, len(s_labels), call.strong) if call.strong else None
    if strong is None and len(s_labels) > 1:
        raise ConceptUnavailable("call side needs a combo")
    weak = _find(WEAK_COMBOS, len(w_labels), call.weak) if len(w_labels) else None
    if strong is None:
        # the lone call-side receiver runs a backside-style iso route named in ``strong`` slot via weak table
        raise ConceptUnavailable("one-receiver call sides use iso calls")
    routes, reads_s, reads_w = {}, [], []
    for i, spec in enumerate(strong.routes):
        routes[s_labels[i]] = spec
    reads_s = [s_labels[i] for i in strong.order]
    if weak is not None:
        for i, spec in enumerate(weak.routes):
            routes[w_labels[i]] = spec
        reads_w = [w_labels[i] for i in weak.order]
    subs = []
    if call.variant and strong.name not in VERTS_FAMILY:
        routes, subs = vary_verticals(routes, call.variant, keep={s_labels[strong.key]} |
                                      ({w_labels[weak.key]} if weak is not None and weak.routes else set()))
    b, b2 = ctx.slot("B"), ctx.slot("B2")
    if b is not None:
        routes["B"] = call.back
    if b2 is not None:
        routes["B2"] = call.b2
    if call.focus == "weak" and reads_w:
        reads = reads_w[:1] + reads_s[:2] + reads_w[1:] + reads_s[2:]
    elif call.focus == "back" and b is not None and call.back[0] != "block":
        reads = ["B"] + reads_s[:2] + reads_w[:1]
    else:
        reads = reads_s[:2] + reads_w[:1] + reads_s[2:] + reads_w[1:]
    if b is not None and call.back[0] != "block" and "B" not in reads:
        reads.append("B")
    drop, protection, header = DROPS[call.drop]
    fake = None
    if call.drop in ("pa", "boot"):
        if b is None:
            raise ConceptUnavailable("play action needs a back")
        fake = "B"
        # retail PA backs: fake, release six yards, then block (0x17 + 0:18 10:3, 225 retail uses), or a pass set
        tail = ("route", "Stem Block", 6) if (len(s_labels) + len(w_labels)) % 2 == 0 else ("block",)
        routes["B"] = ("fake", oc._fake_hole(ctx), tail)
        if call.back[0] == "route":
            routes["B"] = ("fake", oc._fake_hole(ctx), call.back)
        reads = [r for r in reads if r != "B"] + (["B"] if call.back[0] == "route" else [])
    plan = PassPlan(routes, reads, drop, protection, header, tuple(strong.tags), boot_side=(-1 if call.drop == "boot" else 1 if call.drop == "rollout" else 0), fake_to=fake)
    name = call_name(ctx, call, plan, codes, subs)
    d = oc.build_pass(ctx, name, name, plan)
    short = call_name(ctx, ComboCall(call.strong, "", call.back, call.drop, call.focus, call.b2), plan, codes, subs)
    d.alt_names = [name] + ([short] if short != name else [])      # shorter fallbacks for the name pool budget
    if subs:
        bare = call_name(ctx, ComboCall(call.strong, "", call.back, call.drop, call.focus, call.b2), plan, codes)
        if bare not in d.alt_names:
            d.alt_names.append(bare)                                   # the variant tag goes last
    d.preference = 2 if "shot" in strong.tags else 1
    d.tags = tuple(set(d.tags) | {"combo", strong.family})
    return d


#: concepts whose verticals are the point (four verticals, seam / go shots): never varied, capped per book
VERTS_FAMILY = {"Verticals", "Quads Verts", "Seam Shot", "Go Shot", "Sluggo Seam", "Switch", "Four Verticals"}
PLAIN_VERTICALS = {"Go", "Seam", "Fade", "Bender"}
#: breaking replacements for a plain vertical filler: outside (#1) and inside receivers, high-low depths mixed
OUTSIDE_BREAKS = (("Comeback", 14), ("Flag", 12), ("Curl", 12), ("Out", 14), ("Post Corner", 10), ("Dig", 12),
                  ("Out and Up", 7), ("Corner Curl", 10), ("Fade Stop", 4), ("Skinny Post", 12), ("Zig", 12),
                  ("Deep Hook", 10), ("Return", 8), ("Hitch", 6), ("Stop and Go", 10))
INSIDE_BREAKS = (("Corner", 10), ("Curl", 10), ("Whip", 4), ("Stick", 6), ("Dig", 10), ("Pivot", 3),
                 ("Crossing Dig", 8), ("Steep In", 10), ("Spot Out", 5), ("Hook Corner", 8), ("Bend In", 6),
                 ("Seam Out", 9), ("Snag", 4), ("Corner Post", 10), ("Angle Cross", 6))


def vary_verticals(routes: dict, variant: int, keep: set) -> tuple[dict, list]:
    """Replace plain-vertical fillers (go / seam / fade / bender) with breaking routes from the variant's slice of the
    outside and inside pools; the call side's featured route is kept."""
    out, subs = dict(routes), []
    for n, (label, spec) in enumerate(sorted(routes.items())):
        if label in keep or not spec or spec[0] != "route" or spec[1] not in PLAIN_VERTICALS:
            continue
        outside = label.endswith("1")
        pool = OUTSIDE_BREAKS if outside else INSIDE_BREAKS
        name, depth = pool[(variant * 3 + n * 5) % len(pool)]
        out[label] = ("route", name, depth)
        subs.append(name)
    return out, subs


def call_name(ctx, call: ComboCall, plan, codes=None, subs=()) -> str:
    """Madden-style call name: the featured receiver's letter, the call-side concept, the backside tag."""
    first = oc._resolve(ctx, plan.reads[0]) if plan.reads else None
    lead = ""
    if codes is not None and first is not None:
        lead = letter(codes[first])
    pre = {"pa": "PA ", "boot": "PA Boot ", "rollout": "Sprint "}.get(call.drop, "")
    if call.drop == "max" and ctx.slot("B") is not None:
        pre = "Max "                    # max protection only when a back stays in
    parts = [p for p in (pre.strip(), lead, call.strong, subs[0] if subs else "", call.weak) if p]
    name = " ".join(parts)
    return name[:40]


def combo_calls(ctx: oc.FormationContext) -> list[ComboCall]:
    """Every combo call this formation's shape can host (before team selection)."""
    s_n, w_n = len(_side_labels(ctx, "S")), len(_side_labels(ctx, "W"))
    strong_list = STRONG_COMBOS.get(s_n, [])
    weak_list = WEAK_COMBOS.get(w_n, [])
    has_b = ctx.slot("B") is not None
    out = []
    for sc in strong_list:
        for wc in weak_list:
            fam = sc.family
            drops = {"quick": ("quick",), "dropback": ("dropback",), "deep": ("deep", "max")}[fam]
            if fam != "quick" and has_b:
                drops = drops + ("pa",)
            for drop in drops:
                jobs = BACK_JOBS["quick" if drop == "quick" else "deep" if drop in ("deep", "max") else "dropback"] if has_b else [("block",)]
                if drop == "max":
                    jobs = [("block",)]          # max protection: the backs stay in
                for job in jobs:
                    has_vert = sc.name not in VERTS_FAMILY and any(
                        r[0] == "route" and r[1] in PLAIN_VERTICALS for r in (*sc.routes, *wc.routes))
                    for focus in ("strong", "weak", "back"):
                        if focus == "weak" and not wc.name:
                            continue
                        if focus == "back" and (not has_b or job[0] == "block" or drop in ("pa",)):
                            continue
                        for variant in ((1, 2, 3, 4) if has_vert else (0,)):
                            out.append(ComboCall(sc.name, wc.name, job, drop, focus, variant=variant))
    return out


# ---------------------------------------------------------------------------
# Run blocking library: each template copies one named retail team-book play (operands only, playside-relative:
# dx > 0 points to the play side; turn ps / bs / st). Extracted by the pb1 census (tools/b77/pb1_run_templates.py).
# ---------------------------------------------------------------------------

RUN_TEMPLATES = {'Inside Zone': {'source': 'ARZ Ace / Weak Zone Cutback',
                 'handoff': 0,
                 'take': (1, 0.0, 0.83),
                 'path': (1, -6, 0, 0, None, 0),
                 'ol': {'PT': [(8, 0.0, 1, 0, 'ps', 3, 3, 2)],
                        'BT': [(8, 0.0, 1, 0, 'ps', 3, 3, 2)],
                        'C': [(8, 0.0, 1, 0, 'ps', 3, 3, 2)],
                        'PG': [(8, 0.0, 1, 0, 'ps', 3, 3, 2)],
                        'BG': [(8, 0.0, 1, 0, 'ps', 3, 3, 2)]},
                 'qb': [],
                 'others': {'TE@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                            'WR2@off:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                            'WR@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                            'TE2@los:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1), (4, 0.0, 0, 0, 'st', -11, 0, 1)]}},
 'Outside Zone': {'source': 'ARZ Ace / Strong Outside Zone',
                  'handoff': 0,
                  'take': (0, 0.0, 5.83),
                  'path': (0, 15, -9, 2, None, 0),
                  'ol': {'BT': [(8, 0.0, 1, 0, 'bs', 3, 3, 2)],
                         'PT': [(8, 0.0, 1, 0, 'bs', 3, 3, 2)],
                         'C': [(8, 0.0, 1, 0, 'bs', 3, 3, 2)],
                         'BG': [(8, 0.0, 1, 0, 'bs', 3, 3, 2)],
                         'PG': [(8, 0.0, 1, 0, 'bs', 3, 3, 2)]},
                  'qb': [],
                  'others': {'TE@los:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                             'WR2@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                             'WR@off:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                             'TE2@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1), (4, 0.0, 0, 0, 'st', 21, 0, 1)]}},
 'Stretch': {'source': 'ARZ I Wing Jokers / Weak Stretch',
             'handoff': 8,
             'take': (1, 0.0, 5.83),
             'path': (0, 27, -3, 2, None, 0),
             'ol': {'PT': [(5, 0.0, 1, 0, 'bs', 3, 3, 2)],
                    'BT': [(5, 0.0, 1, 0, 'bs', 3, 3, 2)],
                    'C': [(5, 0.0, 1, 0, 'bs', 3, 3, 2)],
                    'PG': [(5, 0.0, 1, 0, 'bs', 3, 3, 2)],
                    'BG': [(5, 0.0, 1, 0, 'bs', 3, 3, 2)]},
             'qb': [],
             'others': {'TE2@los:bs': [(5, 0.0, 1, 0, 'bs', 3, 3, 2)],
                        'WR@off:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                        'TE@los:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                        'FB@back:mid': [(5, 0.0, 1, 0, 'bs', 3, 3, 2), (4, 0.0, 1, 0, 'bs', 12, 18, 1)]}},
 'Dive': {'source': 'ARZ Ace / Strong Dive',
          'handoff': 0,
          'take': (0, 0.0, 0.83),
          'path': (2, -1, 0, 0, 'PG', 1),
          'ol': {'BT': [(0, 0.0, 1, 0, 'bs', 0, 3, 0)],
                 'PT': [(0, 0.0, 1, 0, 'ps', 0, 3, 0)],
                 'C': [(0, 0.0, 1, 0, 'bs', 0, 3, 0)],
                 'BG': [(0, 0.0, 1, 0, 'bs', 0, 3, 0)],
                 'PG': [(0, 0.0, 1, 0, 'ps', 0, 3, 0)]},
          'qb': [],
          'others': {'TE@los:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                     'WR2@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                     'WR@off:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                     'TE2@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)]}},
 'Iso': {'source': 'ARZ I Spread / Strong Iso',
         'handoff': 0,
         'take': (0, 0.0, 2.5),
         'path': (2, 0, -3, 0, 'B2', 1),
         'ol': {'BT': [(0, 0.0, 1, 0, 'st', 0, 3, 0)],
                'PT': [(0, 0.0, 1, 0, 'ps', 0, 3, 0)],
                'C': [(0, 0.0, 1, 0, 'st', 0, 3, 0)],
                'BG': [(0, 0.0, 1, 0, 'st', 0, 3, 0)],
                'PG': [(0, 0.0, 1, 0, 'bs', 0, 3, 0)]},
         'qb': [],
         'others': {'WR2@los:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                    'WR3@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                    'WR@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                    'FB@back:mid': [(4, 0.0, 0, 0, 'st', 7, 0, 1)]}},
 'Fan Iso': {'source': 'BUF Split Pro / Strong Fan Iso',
             'handoff': 0,
             'take': (0, 0.0, 2.5),
             'path': (2, 0, -3, 0, 'B2', 1),
             'ol': {'BT': [(0, 0.0, 1, 0, 'st', 0, 3, 0)],
                    'PT': [(0, 0.0, 1, 0, 'bs', -1, 3, 0)],
                    'C': [(0, 0.0, 1, 0, 'st', 0, 3, 0)],
                    'BG': [(0, 0.0, 1, 0, 'st', 0, 3, 0)],
                    'PG': [(0, 0.0, 1, 0, 'bs', -1, 3, 0)]},
             'qb': [],
             'others': {'TE@los:ps': [(0, 0.0, 1, 0, 'ps', 0, 3, 0)],
                        'WR2@off:ps': [(3, 0.0, 0, 0, 'st', 27, 6, 0)],
                        'WR@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                        'FB@back:ps': [(4, 0.0, 0, 0, 'st', 12, 0, 1)]}},
 'Power O': {'source': 'ARZ Triple / Strong Power',
             'handoff': 0,
             'take': (0, 0.0, 5.83),
             'path': (0, 20, 0, 0, None, 0),
             'ol': {'BT': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                    'PT': [(0, 0.0, 1, 0, 'bs', -2, 3, 0)],
                    'C': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                    'BG': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                    'PG': [(2, 0.0, 0, 0, 'st', 18, 3, 1)]},
             'qb': [],
             'others': {'TE@los:ps': [(0, 0.0, 1, 0, 'bs', -2, 3, 0)],
                        'WR3@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                        'WR@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                        'WR2@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1), (4, 0.0, 0, 0, 'st', 15, 0, 1)]}},
 'Belly': {'source': 'ATL I Twins / Weak Belly',
           'handoff': 0,
           'take': (1, 0.0, 2.5),
           'path': (2, 1, 0, 0, 'PT', 1),
           'ol': {'PT': [(0, 0.0, 1, 0, 'bs', -4, 3, 0)],
                  'BT': [(0, 0.0, 1, 0, 'bs', 0, 3, 0)],
                  'C': [(0, 0.0, 1, 0, 'bs', 0, 3, 0)],
                  'PG': [(2, 0.0, 0, 0, 'ps', 12, 3, 1)],
                  'BG': [(0, 0.0, 1, 0, 'bs', 0, 3, 0)]},
           'qb': [],
           'others': {'TE@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                      'WR@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                      'WR2@los:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                      'FB@back:mid': [(4, 0.0, 0, 0, 'st', 12, 6, 1)]}},
 'Counter': {'source': 'ARZ I Pro / Strong Counter',
             'handoff': 5,
             'take': (0, 0.1, 4.17),
             'path': (2, 3, 0, 2, 'PT', 1),
             'ol': {'BT': [(0, 0.0, 1, 3, 'st', 3, 3, 0)],
                    'PT': [(0, 0.0, 1, 0, 'st', -3, 3, 0)],
                    'C': [(0, 0.0, 1, 0, 'st', -3, 3, 0)],
                    'BG': [(2, 0.0, 0, 0, 'bs', 12, 3, 1)],
                    'PG': [(0, 0.0, 1, 0, 'st', -3, 3, 0)]},
             'qb': [],
             'others': {'TE@los:ps': [(0, 0.0, 1, 0, 'st', -3, 3, 0)],
                        'WR2@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                        'WR@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                        'FB@back:mid': [(3, 0.0, 1, 0, 'st', 0, 15, 1), (4, 0.0, 0, 0, 'st', 15, 0, 1)]}},
 'Counter Trey': {'source': 'BAL I Wing Jokers / Strong Counter Trap',
                  'handoff': 5,
                  'take': (0, 0.1, 4.17),
                  'path': (2, 3, 0, 2, 'PT', 1),
                  'ol': {'BT': [(2, 0.0, 0, 0, 'bs', 12, 3, 1)],
                         'PT': [(0, 0.0, 1, 0, 'st', -3, 3, 0)],
                         'C': [(0, 0.0, 1, 0, 'st', -3, 3, 0)],
                         'BG': [(2, 0.0, 0, 0, 'ps', 18, 3, 1)],
                         'PG': [(0, 0.0, 1, 0, 'st', -3, 3, 0)]},
                  'qb': [],
                  'others': {'TE2@los:ps': [(0, 0.0, 1, 0, 'st', -3, 3, 0)],
                             'WR@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                             'TE@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                             'FB@back:mid': [(4, 0.6, 0, 0, 'ps', -6, -6, 1)]}},
 'Trap': {'source': 'CAR Pro F Flex / Strong Trap',
          'handoff': 0,
          'take': (0, 0.0, 0.83),
          'path': (1, 0, 6, 0, None, 0),
          'ol': {'BT': [(0, 0.0, 1, 0, 'bs', 1, 3, 0)],
                 'PT': [(0, 0.0, 1, 0, 'ps', 0, 3, 0)],
                 'C': [(0, 0.0, 1, 0, 'st', -4, 3, 0)],
                 'BG': [(2, 0.0, 0, 0, 'ps', 3, 3, 0)],
                 'PG': [(0, 0.0, 1, 0, 'st', -6, 3, 1)]},
          'qb': [],
          'others': {'TE@los:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                     'WR2@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                     'WR@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                     'FB@off:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)]}},
 'Sweep': {'source': 'ARZ Split Pro / Strong Sweep',
           'handoff': 0,
           'take': (0, 0.0, 5.83),
           'path': (2, 15, 0, 0, 'PG', 0),
           'ol': {'BT': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                  'PT': [(0, 0.0, 1, 0, 'bs', 0, 3, 0)],
                  'C': [(5, 0.0, 0, 0, 'bs', 6, 3, 0)],
                  'BG': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                  'PG': [(2, 0.0, 0, 0, 'st', 24, 3, 1)]},
           'qb': [],
           'others': {'TE@los:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                      'WR2@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                      'WR@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                      'FB@back:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1), (4, 0.0, 0, 0, 'st', 27, 0, 1)]}},
 'Pin Pull Sweep': {'source': 'ATL Split Jokers / Strong Split Sweep',
                    'handoff': 0,
                    'take': (0, 0.0, 5.83),
                    'path': (0, 30, -8, 2, None, 0),
                    'ol': {'BT': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                           'PT': [(0, 0.0, 1, 0, 'bs', -3, 3, 0)],
                           'C': [(2, 0.0, 0, 0, 'st', 18, 3, 1)],
                           'BG': [(0, 0.0, 1, 3, 'st', 3, 3, 0)],
                           'PG': [(2, 0.0, 0, 0, 'st', 21, 3, 1)]},
                    'qb': [],
                    'others': {'TE@los:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                               'WR@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                               'TE2@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                               'FB@back:ps': [(4, 0.0, 0, 0, 'st', 24, 0, 1)]}},
 'Lead Stretch': {'source': 'CHI Triple Bunch / Strong Lead Stretch',
                  'handoff': 8,
                  'take': (0, 0.0, 5.83),
                  'path': (2, -3, 0, 0, 'PG', 1),
                  'ol': {'BT': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                         'PT': [(2, 0.0, 0, 0, 'bs', 21, 3, 1)],
                         'C': [(0, 0.0, 1, 3, 'st', 3, 3, 0)],
                         'BG': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                         'PG': [(2, 0.0, 0, 0, 'ps', 27, 0, 1)]},
                  'qb': [],
                  'others': {'TE@los:ps': [(0, 0.0, 1, 0, 'bs', -9, 3, 0)],
                             'WR2@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                             'WR3@off:ps': [(0, 0.0, 1, 0, 'bs', -3, 6, 0)],
                             'WR@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)]}},
 'Toss': {'source': 'ARZ Ace / Strong Toss',
          'handoff': 1,
          'take': (0, 0.0, 5.83),
          'path': (0, 30, -3, 2, None, 0),
          'ol': {'BT': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                 'PT': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                 'C': [(0, 0.0, 1, 0, 'st', 3, 3, 0)],
                 'BG': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                 'PG': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)]},
          'qb': [],
          'others': {'TE@los:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                     'WR2@off:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                     'WR@off:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                     'TE2@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1), (4, 0.0, 0, 0, 'st', 21, 0, 1)]}},
 'Draw': {'source': 'ARZ Ace / Strong Draw',
          'handoff': 4,
          'take': (0, 0.0, 0.83),
          'path': (1, 0, 9, 0, None, 0),
          'ol': {'BT': [(1, 1.3, 1, 1, 'bs', 0, -3, 0), (0, 0.0, 1, 0, 'bs', 0, 6, 0)],
                 'PT': [(1, 1.3, 1, 1, 'ps', 0, -3, 0), (0, 0.0, 1, 0, 'ps', 0, 6, 0)],
                 'C': [(1, 0.1, 1, 1, 'bs', 0, 0, 0), (0, 0.0, 1, 0, 'bs', -1, 4, 0)],
                 'BG': [(1, 0.1, 1, 1, 'bs', 0, 0, 0), (0, 0.0, 1, 0, 'bs', 0, 3, 0)],
                 'PG': [(1, 0.1, 1, 1, 'ps', 0, 0, 0), (0, 0.0, 1, 0, 'ps', 1, 3, 0)]},
          'qb': [(4, [0, 0.0, -15, 0])],
          'others': {'TE@los:ps': [], 'WR2@off:ps': [], 'WR@off:bs': [], 'TE2@los:bs': []}},
 'Lead Draw': {'source': 'OAK I Jokers / Strong Lead Draw',
               'handoff': 4,
               'take': (0, 0.0, 0.83),
               'path': (1, 0, 9, 0, None, 0),
               'ol': {'BT': [],
                      'PT': [],
                      'C': [(1, 0.1, 1, 1, 'bs', 0, 0, 0), (0, 0.0, 1, 0, 'bs', -1, 4, 0)],
                      'BG': [(1, 0.1, 1, 1, 'bs', 0, 0, 0), (0, 0.0, 1, 0, 'bs', 0, 3, 0)],
                      'PG': [(1, 0.1, 1, 1, 'ps', 0, 0, 0), (0, 0.0, 1, 0, 'ps', 1, 3, 0)]},
               'qb': [(4, [0, 0.0, -15, 0])],
               'others': {'TE@off:ps': [], 'FB@back:mid': [(6, 0.6, 0, 1, 'st', 3, -9, 1), (4, 0.0, 0, 0, 'st', 3, 3, 1)]}},
 'G Iso': {'source': 'ARZ I Spread / Weak G-Iso',
           'handoff': 0,
           'take': (1, 0.0, 2.5),
           'path': (2, 0, -3, 0, 'B2', 1),
           'ol': {'PT': [(0, 0.0, 1, 0, 'ps', 0, 3, 0)],
                  'BT': [(0, 0.0, 1, 0, 'bs', 0, 3, 0)],
                  'C': [(0, 0.0, 1, 0, 'bs', -3, 3, 0)],
                  'PG': [(0, 0.0, 1, 0, 'bs', 0, 3, 0)],
                  'BG': [(2, 0.0, 0, 0, 'bs', 7, 3, 1)]},
           'qb': [],
           'others': {'WR2@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                      'WR3@off:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                      'WR@los:ps': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                      'FB@back:mid': [(4, 0.0, 0, 0, 'st', 8, 0, 1)]}},
 'Inside Trap': {'source': 'ATL Split Twins / Strong Inside Trap',
                 'handoff': 0,
                 'take': (0, 0.0, 0.83),
                 'path': (0, 3, -3, 0, None, 0),
                 'ol': {'BT': [(0, 0.0, 1, 0, 'bs', 1, 3, 0)],
                        'PT': [(0, 0.0, 1, 0, 'ps', 0, 3, 0)],
                        'C': [(0, 0.0, 1, 0, 'st', -4, 3, 0)],
                        'BG': [(2, 0.0, 0, 0, 'ps', 6, 3, 1)],
                        'PG': [(0, 0.0, 1, 0, 'st', 0, 1, 0)]},
                 'qb': [],
                 'others': {'TE@los:ps': [(0, 0.0, 1, 0, 'ps', 0, 3, 0)],
                            'WR@off:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                            'WR2@los:bs': [(3, 0.0, 1, 0, 'st', 0, 15, 1)],
                            'FB@back:ps': [(0, 0.0, 0, 0, 'st', 15, 0, 0)]}},
 'WB Sweep': {'source': 'ARZ I Wing Jokers / Weak WB Sweep',
              'handoff': 2,
              'take': (1, 0.0, 5.83),
              'path': (2, 21, 0, 0, 'PT', 1),
              'ol': {'PT': [(0, 0.0, 1, 0, 'bs', -3, 3, 0)],
                     'BT': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                     'C': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                     'PG': [(2, 0.0, 0, 0, 'ps', 18, 3, 1)],
                     'BG': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)]},
              'qb': [],
              'others': {'TE2@los:bs': [(0, 0.0, 1, 0, 'bs', 3, 3, 0)],
                         'TE@los:ps': [(0, 0.0, 1, 0, 'bs', -3, 3, 0)],
                         'FB@back:mid': [(4, 0.0, 0, 0, 'st', 21, 6, 1)],
                         'HB@back:mid': [(4, 0.0, 0, 0, 'st', 21, 0, 1)]}},
 'Direct Snap': {'source': 'BUF Gun: Trey Right / H Direct Snap',
                 'handoff': None,
                 'take': None,
                 'path': (2, 1, -3, 2, 'BG', 1),
                 'ol': {'BT': [(0, 0.0, 1, 0, 'bs', 1, 3, 0)],
                        'PT': [(0, 0.0, 1, 0, 'st', 3, 3, 0)],
                        'C': [(0, 0.0, 1, 0, 'st', -4, 3, 0)],
                        'BG': [(2, 0.0, 0, 0, 'st', 1, 6, 1)],
                        'PG': [(0, 0.0, 1, 0, 'st', 3, 3, 0)]},
                 'qb': [(24, [1, -9, -9, 2, 11, 0, 0])],
                 'others': {'WR@off:ps': [], 'WR3@los:ps': [], 'WR4@los:bs': [], 'WR2@off:ps': [(4, 0.0, 0, 0, 'st', 3, 0, 1)]}}}


@dataclass(frozen=True)
class RunScheme:
    name: str                     # Madden 27 style call name (carrier prefix added when not the HB)
    template: str                 # RUN_TEMPLATES key
    tags: tuple = ()
    needs: tuple = ()             # labels the formation must have ("B2" fullback / second back, "UC", "GUN", "WING")
    header: str = "run"           # run | run_toss | draw
    crack: bool = False           # playside receivers crack inside instead of stalking
    zone_toss: bool = False


RUN_SCHEMES: dict[str, RunScheme] = {s.name: s for s in (
    RunScheme("Inside Zone", "Inside Zone", ("base", "short")),
    RunScheme("Inside Zone Split", "Inside Zone", ("base",), ("SPLIT",)),
    RunScheme("Outside Zone", "Outside Zone", ("base",)),
    RunScheme("HB Stretch", "Stretch", ("base",)),
    RunScheme("HB Dive", "Dive", ("short", "goal")),
    RunScheme("HB Slam", "Fan Iso", ("short", "goal"), ("B2",)),
    RunScheme("HB Iso", "Iso", ("short", "goal"), ("B2",)),
    RunScheme("Guard Iso", "G Iso", ("short",), ("B2",)),
    RunScheme("Power G", "Power O", ("base", "short")),
    RunScheme("HB Off Tackle", "Belly", ("base",), ("B2",)),
    RunScheme("HB Counter", "Counter", ("base",)),
    RunScheme("Counter GT", "Counter Trey", ("base",)),
    RunScheme("01 Trap", "Trap", ("base",)),
    RunScheme("Inside Trap", "Inside Trap", ("base", "short")),
    RunScheme("HB Sweep", "Sweep", ("base",)),
    RunScheme("Pin Pull Sweep", "Pin Pull Sweep", ("base",)),
    RunScheme("Lead Stretch", "Lead Stretch", ("base",)),
    RunScheme("HB Toss", "Toss", ("base",), header="run_toss"),
    RunScheme("Crack Toss", "Toss", ("base",), header="run_toss", crack=True),
    RunScheme("Zone Toss", "Toss", ("base",), header="run_toss", zone_toss=True),
    RunScheme("HB Draw", "Draw", ("long", "base"), header="draw"),
    RunScheme("HB Lead Draw", "Lead Draw", ("long",), ("B2",), header="draw"),
    RunScheme("WB Sweep", "WB Sweep", ("gadget", "base"), ("WING", "UC")),
    RunScheme("Direct Snap Power", "Direct Snap", ("short", "gadget"), ("GUN",)),
)}


def _role_slots(ctx: oc.FormationContext, d: int) -> dict[str, int]:
    out = {}
    for p in ctx.ol():
        if p.kind == C:
            out["C"] = p.slot
        else:
            side = "P" if p.x * d > 0 else "B"
            out[side + ("T" if p.kind == T else "G")] = p.slot
    return out


def _leg_from(t, d: int) -> tuple:
    kind, tt, rel, end, turn, dx, dy, g = t
    turn_code = 2 if turn == "st" else (1 if (turn == "ps") == (d > 0) else 0)
    return legf(kind, dx * d, dy, turn=turn_code, end=end, group=g, t=tt, rel=rel)


def _where(p: oc.Player) -> str:
    if p.z <= -2.5 and abs(p.x) <= 4.5:
        return "back"
    return "los" if p.on_los else "off"


def _other_legs(tpl: dict, p: oc.Player, d: int):
    kind_label = {TE: "TE", WR: "WR", HB: "HB", FB: "FB"}[p.kind]
    side = "ps" if p.x * d > 0.3 else "bs" if p.x * d < -0.3 else "mid"
    where = _where(p)
    cands = [(k, v) for k, v in tpl["others"].items() if v]
    def parse(k):
        pos, rest = k.split("@")
        w, s = rest.split(":")
        return pos.rstrip("0123456789"), w, s
    for want in ((kind_label, where, side), (kind_label, where, None), (None, where, side)):
        for k, v in cands:
            pk, w, s = parse(k)
            if (want[0] is None or pk == want[0]) and w == want[1] and (want[2] is None or s == want[2]):
                return v
    return None


def run_design(ctx: oc.FormationContext, scheme: str, *, weak: bool = False, carrier: str = "B",
               codes=None) -> PlayDesign:
    """A retail-template run re-aimed for this formation (raises ConceptUnavailable)."""
    rs = RUN_SCHEMES[scheme]
    tpl = RUN_TEMPLATES[rs.template]
    if "GUN" in rs.needs and not ctx.gun:
        raise ConceptUnavailable("direct snap needs a shotgun set")
    if "UC" in rs.needs and ctx.gun:
        raise ConceptUnavailable("needs the QB under centre")
    if "B2" in rs.needs and ctx.slot("B2") is None:
        raise ConceptUnavailable("needs a lead back")
    d = ctx.run_strong * (-1 if weak else 1)
    roles = _role_slots(ctx, d)
    out: list = [None] * 11
    wing = None
    if rs.template == "WB Sweep":
        wing = next((p.slot for p in ctx.players if p.kind in (WR, TE) and not p.on_los and abs(p.x) < 8.5
                     and p.x * d < 0 and -1.6 <= p.z <= -0.5), None)
        if wing is None:
            raise ConceptUnavailable("wingback sweep needs a wing on the far side")
        car = wing
    else:
        car = ctx.slot(carrier)
        if car is None:
            raise ConceptUnavailable("no carrier")
    if rs.template == "Direct Snap":
        pc = ctx.player(car)
        if math.hypot(pc.x - ctx.qb.x, pc.z - ctx.qb.z) > 3.0 or pc.z > -4.5:
            raise ConceptUnavailable("direct snap needs the back beside the QB in the gun")
    for role, slot in roles.items():
        legs = tpl["ol"].get(role) or tpl["ol"].get(role[0] + ("G" if role.endswith("T") else "T")) or [(0, 0.0, 1, 0, "st", 0, 3, 0)]
        head = [start(2), (0x02, [car if rs.template == "Direct Snap" else ctx.qb.slot])] if role == "C" else [start(3)]
        out[slot] = head + [_leg_from(l, d) for l in legs]
    k = tpl["handoff"]
    take_a, take_t, lat = tpl["take"] if tpl["take"] else (0, 0.0, 0.8)
    hole = oc.hole_toward(d, lat) if lat > 0.1 else lib.handoff_hole_for_x(0.0)
    mode, dx, dy, a, follow_role, cflag = tpl["path"]
    follow = 0
    if mode == 2:
        follow = roles.get(follow_role) if follow_role in roles else ctx.slot("B2") if follow_role == "B2" else None
        if follow is None or follow == car or follow > car:
            # a follower's descriptor is computed from its leader's: the leader must come first (slot order)
            mode, dx, dy, follow, cflag = 1, 0, 9, 0, 0
    path_node = path(mode, d * dx, dy, a=a, follow=follow, c=cflag)
    if rs.template == "Direct Snap":
        out[car] = [start(3), start(7), path_node]
    else:
        out[car] = [start(3), take(hole, take_a, take_t), path_node]
    for p in ctx.players:
        if out[p.slot] is not None or p.kind not in (WR, TE, HB, FB):
            continue
        legs = _other_legs(tpl, p, d)
        if rs.crack and p.kind == WR and p.x * d > 0 and not legs:
            legs = [(0, 0.0, 1, 0, "st", -9, 3, 0)]
        if rs.crack and p.kind == WR and p.x * d > 0:
            legs = [(0, 0.0, 1, 0, "st", -9, 3, 0)]                 # crack inside on the safety / backer
        if "SPLIT" in rs.needs and p.kind in (TE, FB, HB) and not p.on_los and p.x * d > 0:
            legs = [(4, 0.0, 0, 0, "st", -(abs(p.x) * 3 + 9), 0, 1)]   # split zone: kick back across
        if legs is None:
            if p.kind in (HB, FB):
                legs = [(4, 0.0, 0, 0, "st", 6, 3, 1)]
            elif p.kind == TE and p.on_los:
                legs = [(0, 0.0, 1, 0, "st", 0, 3, 0)]
            else:
                legs = [(3, 0.0, 1, 0, "st", 0, 15, 1)]
        out[p.slot] = [start(3), *[_leg_from(l, d) for l in legs]]
    if "SPLIT" in rs.needs and not any(p.kind in (TE, FB, HB) and not p.on_los and p.x * d > 0 and p.slot != car
                                        for p in ctx.players):
        raise ConceptUnavailable("split zone needs an H-back or wing on the play side")
    qb = ctx.qb.slot
    if rs.template == "Direct Snap":
        out[qb] = [start(4), (0x03, [0]), (0x01, [0, 0, 0, 0.6, 0.0, 0.0]),
                   # b778 pb5: mode 1 (offset from the QB himself), as retail's "H Direct Snap" decoy does; mode 0
                   # aims at a point measured from the ball, which the play art draws as a backward arrow
                   (0x18, [1, -9 * d * FT, -9 * FT, 2, 11, 0, 0])]
    else:
        pre = []
        for op, vals in tpl["qb"]:
            if op == 0x04:
                pre.append(move(0, vals[2]))
        if rs.zone_toss:
            for role, slot in roles.items():
                out[slot] = out[slot][:2 if role == "C" else 1] + [legf(8, d * 3, 3, turn=1 if d > 0 else 0, group=2)]
        out[qb] = [start(4), (0x03, [0]), *pre, (0x13, [car, k])]
    who = letter(codes[car]) if codes is not None else ""
    base = rs.name
    if who and who != "HB" and base.startswith("HB "):
        base = who + base[2:]
    elif who and who not in ("HB",) and rs.template != "WB Sweep":
        base = f"{who} {base}"
    name = (base + (" Wk" if weak else ""))[:40]
    pref = 2 if "gadget" in rs.tags else 1
    play_type = "direct_snap" if rs.template == "Direct Snap" else ("reverse" if rs.template == "WB Sweep" else "run")
    header = "reverse" if rs.template == "WB Sweep" else rs.header
    return PlayDesign(scheme, name, play_type, header, out, car, [], rs.tags, pref)


# ---------------------------------------------------------------------------
# Must-haves: tush push, QB keep, QB power, more screens, the PAT fake field goal
# ---------------------------------------------------------------------------

def _drive_line(ctx, inward: bool = True) -> dict[int, list]:
    out = {}
    for p in ctx.ol():
        head = [start(2), (0x02, [ctx.qb.slot])] if p.kind == C else [start(3)]
        dx = 0 if p.kind == C or not inward else (-1 if p.x > 0 else 1)
        out[p.slot] = head + [legf(0, dx, 3, turn=2 if p.kind == C else (1 if p.x > 0 else 0))]
    return out


_HB_WORD = re.compile(r"\bHB\b")
_HALFBACK_WORD = re.compile(r"\bHalfback\b")


def rb_name(name: str) -> str:
    """Play-name spelling of the ball-carrier position (Noah 10/20: "rename halfback to running back (RB)
    everywhere"): RB, never HB; "H-Back" is a different position and stays.  Same length, so name budgets hold."""
    return _HALFBACK_WORD.sub("Running Back", _HB_WORD.sub("RB", name))


#: Tush push stack: backs up to this deep behind the QB count as pushers (the Goal Line Sneak set puts them
#: 2.6 and 4.5 yd behind him); each drives this far straight ahead.
TUSH_STACK_DEPTH_YD = 4.6
TUSH_DRIVE_FT = 9


def tush_push(ctx: oc.FormationContext, codes=None) -> PlayDesign:
    """QB sneak with every back stacked behind him driving into his back (retail QB Sneak operands for the QB and
    line).  2K5 has no push animation (none is known in the engine): the stacked players run lead blocks straight
    up the QB's path and drive whoever stands in that gap; that is the closest honest version."""
    if ctx.gun:
        raise ConceptUnavailable("tush push needs the QB under centre")
    stack = [p for p in ctx.players if p.kind in (HB, FB, TE) and ctx.qb.z - TUSH_STACK_DEPTH_YD <= p.z < ctx.qb.z
             and abs(p.x - ctx.qb.x) <= 1.2]
    if len(stack) < 2:
        raise ConceptUnavailable("tush push needs two or more players stacked behind the QB")
    out = [None] * 11
    for slot, ch in _drive_line(ctx).items():
        out[slot] = ch
    for p in stack:
        # b777 tp1: each pusher drives straight up his own lane (the retail QB Sneak back leg, kind 3, relative,
        # shorter).  The b776 leg sent every pusher to the QB's x (absolute, kind 4): two of them aimed at the
        # same spot inside the QB, and the pile thrashed (Noah 10/20: a few frames every 10 s, replay glitchy).
        out[p.slot] = [start(3), legf(3, 0, TUSH_DRIVE_FT, turn=2, group=1)]
    for p in ctx.players:
        if out[p.slot] is None and p.kind in (WR, TE, HB, FB):
            out[p.slot] = [start(3), legf(0, 0, 3, turn=2)] if p.on_los else [start(3), legf(3, 0, 15, turn=2, group=1)]
    out[ctx.qb.slot] = [start(4), (0x03, [0]), move(0, -3), path(1, 0, 3, a=2)]
    return PlayDesign("Tush Push", "Tush Push", "sneak", "qb_sneak", out, ctx.qb.slot, [], ("short", "goal", "must"), 1)


def qb_keep(ctx: oc.FormationContext, codes=None) -> PlayDesign:
    """Under-centre QB keep straight ahead behind drive blocks (retail QB keeper shape: a one-yard drop, then a
    straight path)."""
    if ctx.gun:
        raise ConceptUnavailable("the QB keep is an under-centre call")
    out = [None] * 11
    for p in ctx.ol():
        head = [start(2), (0x02, [ctx.qb.slot])] if p.kind == C else [start(3)]
        out[p.slot] = head + [legf(0, 0, 3, turn=2)]
    for p in ctx.players:
        if out[p.slot] is not None or p.kind not in (WR, TE, HB, FB):
            continue
        if p.kind in (HB, FB) and p.z <= -2.5:
            out[p.slot] = [start(3), legf(4, (ctx.qb.x - p.x) * 3 + 3, 6, turn=2, group=1, rel=0)]
        elif p.kind == TE and p.on_los:
            out[p.slot] = [start(3), legf(0, 0, 3, turn=2)]
        else:
            out[p.slot] = oc.stalk_chain()
    out[ctx.qb.slot] = [start(4), (0x03, [0]), move(0, -3), path(1, 0, 18, a=2)]
    return PlayDesign("QB Keep", "QB Keep", "keeper", "qb_sneak", out, ctx.qb.slot, [], ("short", "must"), 2)


def qb_power(ctx: oc.FormationContext, codes=None) -> PlayDesign:
    """Designed QB run from the gun: the backside guard pulls, the QB follows him (Madden 27 QB POWER); no read."""
    if not ctx.gun:
        raise ConceptUnavailable("QB power is a shotgun call")
    d = ctx.run_strong
    out = [None] * 11
    pull = oc._backside_guard(ctx, d)
    for slot, ch in oc._run_ol(ctx, "power", d, pull).items():
        out[slot] = ch
    oc._run_receivers(ctx, out, d)
    b = ctx.slot("B")
    if b is not None:
        out[b] = [start(3), legf(4, d * 9, 3, turn=2, group=1, rel=0)]
    # the QB cannot follow the puller (a follower's descriptor needs its leader earlier in slot order and the QB is
    # slot 0): he runs to the guard's kick-out point instead, a retail QB Draw style absolute path
    out[ctx.qb.slot] = [start(4), (0x03, [0]), move(0, -3), path(0, d * 9, 6, a=0)]
    return PlayDesign("QB Power", "QB Power", "keeper", "qb_draw", out, ctx.qb.slot, [], ("short", "base"), 2)


def back_screen(ctx: oc.FormationContext, label: str = "B", weak: bool = False, codes=None) -> PlayDesign:
    """RB screen to either side (HB Slip Screen) or to the fullback; the engine's retail back-screen line."""
    b = ctx.slot(label)
    if b is None:
        raise ConceptUnavailable("screen needs that back")
    side = oc._screen_side(ctx, b) * (-1 if weak else 1)
    p = ctx.player(b)
    if abs(p.x) > 0.5 and (p.x > 0) != (side > 0):
        raise ConceptUnavailable("a back screens to his own side")
    out = [None] * 11
    for slot, ch in oc._screen_line(ctx, side).items():
        out[slot] = ch
    out[b] = [start(3), seg(9, side * 33)]
    for lab, name in (("S1", "Go"), ("S2", "Post"), ("S3", "Seam"), ("W1", "Go"), ("W2", "Seam")):
        s = ctx.slot(lab)
        if s is not None:
            out[s] = oc.route_chain(name, 15 if name in ("Go", "Seam") else 10)
    for lab in ("B", "B2"):
        s = ctx.slot(lab)
        if s is not None and out[s] is None:
            out[s] = oc.back_block_chain(ctx, s)
    out[ctx.qb.slot] = [start(4), (0x03, [0]), move(0, -27), pass_node([b], mode=5)]
    who = letter(codes[b]) if codes is not None else "HB"
    name = f"{who} Slip Screen" + (" Wk" if weak else "") if label == "B" else f"{who} Screen"
    return PlayDesign(name, name, "pass", "screen", out, b, [b], ("screen",), 2)


def fake_fg_deep(positions, codes, donor_chains) -> list:
    """PAT / field-goal fake whose routes reach the end zone from the 15 (the try line).

    ``donor_chains`` are the book's retail FG Pass chains (decoded); the line, kicker and holder keep them.  The two
    right-side ends (on the line and on the wing) run a corner and a post past 15 yards, the left wing runs a deep
    corner; the holder reads post, corner, left corner."""
    chains = [list(c) for c in donor_chains]
    kinds = [c & 31 for c in codes]
    holder = next(s for s, k in enumerate(kinds) if k == lib.H)
    eligible = [s for s, k in enumerate(kinds) if k in (TE, FB, HB, WR)]
    if len(eligible) < 2:
        raise ConceptUnavailable("fake field goal needs two eligible ends")
    right = sorted((s for s in eligible if positions[s][0] > 0), key=lambda s: positions[s][1], reverse=True)
    left = [s for s in eligible if positions[s][0] < 0]
    jobs = {}
    if right:
        jobs[right[0]] = oc.route_chain("Corner", 13)            # end on the line: 13-yard stem, then the pylon
    if len(right) > 1:
        jobs[right[1]] = oc.route_chain("Post", 15)              # wing: 15 yards, then the post
    if left:
        jobs[left[0]] = oc.route_chain("Corner", 14)
    for s, ch in jobs.items():
        chains[s] = ch
    order = ([right[1]] if len(right) > 1 else []) + ([right[0]] if right else []) + (left[:1])
    head = [n for n in chains[holder] if n[0] == 0x01]
    chains[holder] = head + [pass_node(order[:4])]          # retail FG Pass holder: two Start nodes, then the throw
    return chains


# ---------------------------------------------------------------------------
# Studio wizard: the new runs and must-haves become named concepts (the combos stay generator-only)
# ---------------------------------------------------------------------------

def _register_concepts() -> None:
    for name, rs in RUN_SCHEMES.items():
        if name in oc.CONCEPTS:
            continue

        def build(ctx, _n=name):
            return run_design(ctx, _n)
        oc.CONCEPTS[name] = oc.ConceptDef(name, "run", build, f"retail-template run ({RUN_TEMPLATES[rs.template]['source']})",
                                          rs.tags, 2 if "gadget" in rs.tags else 1)
    for name, fn, fam, blurb in (
            ("Tush Push", tush_push, "run", "QB sneak with the backs stacked behind him driving into the pile"),
            ("QB Keep", qb_keep, "run", "under-centre QB keep straight ahead behind drive blocks"),
            ("QB Power", qb_power, "run", "shotgun QB run behind the pulling guard (no read)"),
            ("HB Slip Screen", lambda ctx: back_screen(ctx, "B", True), "screen", "back screen to the weak side")):
        if name not in oc.CONCEPTS:
            oc.CONCEPTS[name] = oc.ConceptDef(name, fam, fn, blurb, ("short",), 1)


_register_concepts()


def _wizard_late_register() -> None:
    """When this module is imported before the base engine finished, add its entries to an already-built wizard
    catalog (the base registration is idempotent by a flag, so it would otherwise skip them)."""
    if not getattr(lib, "_MODERN_CATALOG", False):
        return
    engines = {v.get("engine") for v in lib.RUN_SCHEMES.values()} | {v.get("engine") for v in lib.PASS_CONCEPTS.values()}
    for name, r in oc.ROUTES.items():
        if name not in lib.ROUTES_BY_NAME:
            lib.ROUTE_LIBRARY.append(lib.RouteDef(name, lambda d, s, _n=name: oc.ROUTES[_n].build(d), r.default_depth,
                                                  f"{r.blurb} (retail {r.retail})"))
            lib.ROUTES_BY_NAME[name] = lib.ROUTE_LIBRARY[-1]
    for name, cd in oc.CONCEPTS.items():
        if name in engines:
            continue
        if cd.family == "run" or name in ("QB Sneak", "QB Draw", "End Around", "Reverse"):
            lib.RUN_SCHEMES[oc.wizard_name(name, lib.RUN_SCHEMES)] = {"kind": None, "dir": "right", "blurb": cd.blurb,
                                                                      "engine": name}
        elif cd.family != "trick":
            lib.PASS_CONCEPTS[oc.wizard_name(name, lib.PASS_CONCEPTS)] = {
                "blurb": cd.blurb, "engine": name, "outside": "Go", "inside": "Go", "te": "Go", "back": "Block (stay in)"}
    for name, spec in oc.FORMATIONS.items():
        lib.FORMATION_TEMPLATES.setdefault(name + oc.FORMATION_SUFFIX, (spec.blurb or name, spec.template_players()))


_wizard_late_register()
