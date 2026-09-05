"""Play-design library for the NFL 2K5 "Create a Play" wizard.

Everything here composes retail opcodes (see :mod:`nfl2k5_play_codec`) into
football-level building blocks: modern formation templates, a route library,
pass concepts, run schemes with automatic blocking, special-teams templates,
personnel matching against a book's categories, and heuristics that suggest
which stock formations / plays are the most outdated candidates to replace.
"""

from __future__ import annotations

import math

import struct
from dataclasses import dataclass, field
from collections import Counter
from typing import Callable, Mapping, Sequence

from . import nfl2k5_play_codec as codec
from .nfl2k5_playbook_inspector import (
    CATEGORY_BASE, CATEGORY_SIZE, FORMATION_AUX_BASE, FORMATION_AUX_SIZE, FORMATION_BASE,
    FORMATION_SIZE, NODE_BASE, NODE_SIZE, PLAY_BASE, PLAY_SIZE, Nfl2k5Playbook,
)

YD = codec.YD_CM
QB, P, K, H, KR, T, C, G, TE, WR, HB, FB = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
DE, DT, OLB, MLB, CB, FS, SS = 12, 13, 14, 15, 16, 17, 18
OL_KINDS = {T, C, G}
BACK_KINDS = {HB, FB}
RECEIVER_KINDS = {WR, TE, HB, FB}


# ---------------------------------------------------------------------------
# Formation templates (yards; x + = offense's right, z − = behind the line)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TemplatePlayer:
    kind: int
    x: float
    z: float


def _line() -> list[TemplatePlayer]:
    return [TemplatePlayer(T, 3.3, 0), TemplatePlayer(T, -3.3, 0), TemplatePlayer(C, 0, 0),
            TemplatePlayer(G, 1.7, 0), TemplatePlayer(G, -1.7, 0)]


FORMATION_TEMPLATES: dict[str, tuple[str, list[TemplatePlayer]]] = {
    "Gun Trips Right": ("3 WR bunched right, TE left, RB offset — the modern spread staple",
        [TemplatePlayer(QB, 0, -5), *_line(), TemplatePlayer(TE, -5, 0), TemplatePlayer(WR, 18, 0),
         TemplatePlayer(WR, 12, -1.5), TemplatePlayer(WR, 8, -1), TemplatePlayer(HB, -2.5, -5)]),
    "Gun Bunch Right": ("Tight three-man bunch to the right for rubs and mesh",
        [TemplatePlayer(QB, 0, -5), *_line(), TemplatePlayer(TE, -5, 0), TemplatePlayer(WR, 9, 0),
         TemplatePlayer(WR, 7.5, -1.5), TemplatePlayer(WR, 6, -0.5), TemplatePlayer(HB, 2.5, -5)]),
    "Gun Doubles": ("2×2 spread, RB offset — balanced pass formation",
        [TemplatePlayer(QB, 0, -5), *_line(), TemplatePlayer(WR, -18, 0), TemplatePlayer(WR, -9, -1.5),
         TemplatePlayer(WR, 18, 0), TemplatePlayer(TE, 8, -1.5), TemplatePlayer(HB, -2.5, -5)]),
    "Gun Empty (5 wide)": ("Nobody in the backfield — quick game and RPO looks",
        [TemplatePlayer(QB, 0, -5), *_line(), TemplatePlayer(WR, -20, 0), TemplatePlayer(WR, -11, -1.5),
         TemplatePlayer(WR, 20, 0), TemplatePlayer(TE, 6, -1), TemplatePlayer(HB, 12, -1.5)]),
    "Pistol Ace": ("QB 4 yards deep with the back directly behind him",
        [TemplatePlayer(QB, 0, -4), *_line(), TemplatePlayer(TE, 5, 0), TemplatePlayer(WR, -15, -1),
         TemplatePlayer(WR, 15, -1), TemplatePlayer(WR, -8, 0), TemplatePlayer(HB, 0, -7)]),
    "Pistol Strong": ("Pistol with an offset fullback for lead runs and play action",
        [TemplatePlayer(QB, 0, -4), *_line(), TemplatePlayer(TE, 5, 0), TemplatePlayer(WR, -16, 0),
         TemplatePlayer(WR, 16, -1), TemplatePlayer(FB, 3.5, -4.5), TemplatePlayer(HB, 0, -7)]),
    "Singleback Ace": ("Under center, one back, two TEs — base personnel",
        [TemplatePlayer(QB, 0.05, -2), *_line(), TemplatePlayer(TE, 5, 0), TemplatePlayer(TE, -5, 0),
         TemplatePlayer(WR, -15, -1), TemplatePlayer(WR, 15, 0), TemplatePlayer(HB, 0, -7)]),
    "Singleback Trips": ("Under center with trips to the right",
        [TemplatePlayer(QB, 0.05, -2), *_line(), TemplatePlayer(TE, -5, 0), TemplatePlayer(WR, 17, 0),
         TemplatePlayer(WR, 11, -1.5), TemplatePlayer(WR, 7, -1), TemplatePlayer(HB, 0, -7)]),
    "I-Form Pro": ("Classic I with a fullback, TE right, split end left, flanker right",
        [TemplatePlayer(QB, 0.05, -2), *_line(), TemplatePlayer(TE, 5, 0), TemplatePlayer(WR, -15, 0),
         TemplatePlayer(WR, 15, -1), TemplatePlayer(FB, 0, -4.5), TemplatePlayer(HB, 0, -7.5)]),
    "Jumbo / Tush Push": ("QB under center with two backs stacked right behind him",
        [TemplatePlayer(QB, 0.05, -1.4), *_line(), TemplatePlayer(TE, 5, 0), TemplatePlayer(TE, -5, 0),
         TemplatePlayer(WR, -9, -1), TemplatePlayer(FB, -0.8, -3), TemplatePlayer(HB, 0.8, -3)]),
    "Wildcat": ("Back in the gun spot, QB flexed wide — pair with a direct-snap run play",
        [TemplatePlayer(QB, 16, -1), *_line(), TemplatePlayer(TE, 5, 0), TemplatePlayer(WR, -17, 0),
         TemplatePlayer(WR, -9, -1.5), TemplatePlayer(FB, 3, -5), TemplatePlayer(HB, 0, -5)]),
    "Gun Y-Trips (TE)": ("TE as the inside trips receiver, RB weak",
        [TemplatePlayer(QB, 0, -5), *_line(), TemplatePlayer(WR, -17, 0), TemplatePlayer(WR, 17, 0),
         TemplatePlayer(WR, 12, -1.5), TemplatePlayer(TE, 7, 0), TemplatePlayer(HB, -2.5, -5)]),
    "Gun Split Backs": ("Two backs beside the QB in the gun — screens and draws",
        [TemplatePlayer(QB, 0, -5), *_line(), TemplatePlayer(WR, -17, 0), TemplatePlayer(WR, 17, 0),
         TemplatePlayer(WR, 9, -1.5), TemplatePlayer(FB, -3.5, -5), TemplatePlayer(HB, 3.5, -5)]),
}


# ---------------------------------------------------------------------------
# Book access
# ---------------------------------------------------------------------------

def category_positions(body: bytes, category_index: int) -> list[int]:
    off = CATEGORY_BASE + category_index * CATEGORY_SIZE
    return list(body[off + 5:off + 16])


def formation_category(body: bytes, formation_index: int) -> int:
    aux = FORMATION_AUX_BASE + formation_index * FORMATION_AUX_SIZE
    return struct.unpack_from("<I", body, aux + 0x48)[0] & 0x3F


def formation_record(body: bytes, formation_index: int) -> codec.FormationRecord:
    off = FORMATION_BASE + formation_index * FORMATION_SIZE
    return codec.FormationRecord.from_bytes(body[off:off + FORMATION_SIZE])


def play_chains(body: bytes, play_index: int) -> tuple[int, list[tuple[int, list[bytes]]]]:
    off = PLAY_BASE + play_index * PLAY_SIZE
    flags = struct.unpack_from("<I", body, off + 4)[0]
    out = []
    for slot in range(11):
        desc = struct.unpack_from("<I", body, off + 8 + slot * 8)[0]
        ptr_field = off + 0x0C + slot * 8
        target = ptr_field - 1 + struct.unpack_from("<i", body, ptr_field)[0]
        out.append((desc, [body[target + k * NODE_SIZE: target + (k + 1) * NODE_SIZE] for k in range(desc & 0xF)]))
    return flags, out


def offense_formations(book: Nfl2k5Playbook, body: bytes) -> list[int]:
    return [f.index for f in book.formations if formation_record(body, f.index).type_code < 4]


def offense_plays(book: Nfl2k5Playbook) -> list[int]:
    return [p.index for p in book.plays if p.family_id == 0]


# ---------------------------------------------------------------------------
# Personnel matching: template players -> category slots
# ---------------------------------------------------------------------------

@dataclass
class FittedFormation:
    category_index: int
    donor_formation_index: int
    slot_positions: list[tuple[int, int]]      # cm, category slot order
    slot_kinds: list[int]
    labels: list[str]
    warnings: list[str] = field(default_factory=list)
    codes: list[int] = field(default_factory=list)          # eleven position codes (kind | rank << 5)
    category_positions: list[int] | None = None             # codes to write when no stock group has this mix
    note: str = ""


# ---------------------------------------------------------------------------
# Personnel (who lines up in each spot)
# ---------------------------------------------------------------------------

SKILL_SLOTS = (6, 7, 8, 9, 10)
SKILL_CHOICES: tuple[tuple[str, int], ...] = (("WR", WR), ("TE", TE), ("HB / RB", HB), ("FB", FB))
LINE_CODES = (T, T | 0x20, C, G, G | 0x20)     # slots 1-5 of every stock offensive group


def ranked_codes(kinds: Sequence[int], xs: Sequence[float]) -> list[int]:
    """Position codes for eleven kinds: slot 0 the QB, slots 1-5 the stock line codes,
    skill players ranked on the depth chart left→right (WR, WR2, WR3 …, HB, HB2)."""
    codes = [QB] + list(LINE_CODES) + [0] * (len(kinds) - 6)
    seen: dict[int, int] = {}
    for s in sorted(range(6, len(kinds)), key=lambda s: (xs[s], s)):
        k = kinds[s] & 0x1F
        rank = seen.get(k, 0)
        seen[k] = rank + 1
        codes[s] = k | (rank << 5)
    return codes


def is_offense_category(codes: Sequence[int]) -> bool:
    kinds = [c & 0x1F for c in codes]
    return len(kinds) == 11 and kinds[0] == QB and sorted(kinds[1:6]) == sorted([T, T, C, G, G])


def back_count(codes: Sequence[int]) -> int:
    return sum(1 for c in codes if (c & 0x1F) in BACK_KINDS)


@dataclass
class PersonnelPlan:
    category_index: int
    category_positions: list[int] | None       # None = a stock group already fields this mix
    slot_order: list[int]                      # new slot s takes the design's slot slot_order[s]
    codes: list[int]                           # codes in the new slot order
    note: str
    warnings: list[str] = field(default_factory=list)


def resolve_personnel(book: Nfl2k5Playbook, body: bytes, codes: Sequence[int],
                      claimed: Mapping[int, Sequence[int]] | None = None) -> PersonnelPlan:
    """Find the personnel group that fields ``codes`` (eleven position codes).

    A stock group with exactly this mix is reused (the skill slots are permuted
    into its order).  Otherwise the mix is written into an unused offensive
    group, or failing that the least-used one (with a warning naming the stock
    formations that change with it).  ``claimed`` maps groups already taken by
    other designs in this session to their codes: an identical mix shares the
    group, a different one avoids it."""
    codes = list(codes)
    if len(codes) != 11:
        raise ValueError("eleven position codes are needed")
    claimed = dict(claimed or {})

    def permuted(target_codes: Sequence[int]) -> list[int] | None:
        order = list(range(11))
        remaining = list(range(6, 11))
        for s in range(6, 11):
            pick = next((d for d in remaining if codes[d] == target_codes[s]), None)
            if pick is None:
                return None
            order[s] = pick
            remaining.remove(pick)
        return order

    for ci, taken in claimed.items():
        if sorted(taken) == sorted(codes):
            order = permuted(taken)
            if order is not None:
                return PersonnelPlan(ci, list(taken), order, [codes[order[s]] for s in range(11)],
                                     f"same mix as your earlier design → shares group “{book.categories[ci].name}”")
    for c in book.categories:
        if c.index in claimed:
            continue
        stock = category_positions(body, c.index)
        if sorted(stock) == sorted(codes) and list(stock[:6]) == codes[:6]:
            order = permuted(stock)
            if order is not None:
                return PersonnelPlan(c.index, None, order, [codes[order[s]] for s in range(11)],
                                     f"stock group “{c.name}”")
    usage = Counter(formation_category(body, f.index) for f in book.formations)
    candidates = []
    for c in book.categories:
        if c.index in claimed:
            continue
        if not is_offense_category(category_positions(body, c.index)):
            continue
        candidates.append((usage.get(c.index, 0), c.index))
    if not candidates:
        raise ValueError("this book has no free offensive personnel group to write")
    candidates.sort()
    used, target = candidates[0]
    name = book.categories[target].name
    warnings: list[str] = []
    if used:
        names = [f.name for f in book.formations if formation_category(body, f.index) == target]
        warnings.append(f"no stock group fields this mix, so “{name}” is rewritten — that also changes who lines up in "
                        + ", ".join(names))
        note = f"new mix → rewrites group “{name}”"
    else:
        note = f"new mix → written into the unused group “{name}”"
    return PersonnelPlan(target, codes, list(range(11)), codes, note, warnings)


def donor_for_personnel(book: Nfl2k5Playbook, body: bytes, plan: PersonnelPlan) -> int:
    """A stock offensive formation whose record can host the design (same group when
    the group is stock; otherwise a formation with the same number of backs)."""
    if plan.category_positions is None:
        same = [f.index for f in book.formations if formation_category(body, f.index) == plan.category_index]
        if same:
            return same[0]
    backs = min(back_count(plan.codes), 2)
    offense = offense_formations(book, body)
    for idx in offense:
        if formation_record(body, idx).type_code == backs:
            return idx
    return offense[0] if offense else 0


def fit_template(book: Nfl2k5Playbook, body: bytes, players: Sequence[TemplatePlayer],
                 claimed: Mapping[int, Sequence[int]] | None = None) -> FittedFormation:
    """Map eleven template players onto a personnel group (stock when one fields the mix)."""
    players = list(players)
    qbs = [p for p in players if p.kind == QB]
    tackles = sorted([p for p in players if p.kind == T], key=lambda p: -p.x)
    guards = sorted([p for p in players if p.kind == G], key=lambda p: -p.x)
    centers = [p for p in players if p.kind == C]
    skill = sorted([p for p in players if p.kind not in OL_KINDS and p.kind != QB], key=lambda p: (p.x, p.z))
    if len(qbs) != 1 or len(tackles) != 2 or len(guards) != 2 or len(centers) != 1 or len(skill) != 5:
        raise ValueError("a template needs one QB, two tackles, two guards, a center and five skill players")
    ordered = [qbs[0], tackles[0], tackles[1], centers[0], guards[0], guards[1], *skill]
    codes = ranked_codes([p.kind for p in ordered], [p.x for p in ordered])
    plan = resolve_personnel(book, body, codes, claimed)
    positions = [(int(round(ordered[plan.slot_order[s]].x * YD)), int(round(ordered[plan.slot_order[s]].z * YD)))
                 for s in range(11)]
    donor = donor_for_personnel(book, body, plan)
    labels = [codec.position_label(c) for c in plan.codes]
    return FittedFormation(plan.category_index, donor, positions, [c & 0x1F for c in plan.codes], labels,
                           list(plan.warnings), list(plan.codes), plan.category_positions, plan.note)


# ---------------------------------------------------------------------------
# Assignment building blocks
# ---------------------------------------------------------------------------

Chain = list[tuple[int, list[float]]]


def start(role: int = 3) -> tuple[int, list[float]]:
    return (0x01, [1, role, 0, 0.0, 0.0, 0.0])


def seg(kind: int, dist_yd: float, flag: int = 0) -> tuple[int, list[float]]:
    return (0x12, [kind, flag, dist_yd * YD, 15])


def leg(kind: int, dx_yd: float, dy_yd: float, turn: int = 2, end: int = 0, group: int = 0, t: float = 0.0, rel: int = 1) -> tuple[int, list[float]]:
    return (0x11, [kind, t, rel, end, turn, dx_yd * YD, dy_yd * YD, group])


@dataclass(frozen=True)
class RouteDef:
    name: str
    build: Callable[[float, int], list]   # (depth_yd, side) -> segments
    default_depth: float
    blurb: str


def _side_out(side: int) -> int:
    return 5   # lateral toward the sideline (the game resolves side from alignment)


ROUTE_LIBRARY: list[RouteDef] = [
    RouteDef("Go", lambda d, s: [seg(0, d)], 20, "straight down the field"),
    RouteDef("Post", lambda d, s: [seg(0, d), seg(2, 10)], 10, "up, then 45° toward the goal posts"),
    RouteDef("Corner", lambda d, s: [seg(0, d), seg(6, 10)], 10, "up, then 45° toward the corner"),
    RouteDef("Out", lambda d, s: [seg(0, d), seg(5, 8)], 8, "up, then hard to the sideline"),
    RouteDef("In / Dig", lambda d, s: [seg(0, d), seg(4, 8)], 10, "up, then across the middle"),
    RouteDef("Slant", lambda d, s: [seg(0, 3), seg(1, d)], 8, "three steps, then a 30° cut inside"),
    RouteDef("Curl", lambda d, s: [seg(0, d), seg(7, 2)], 10, "up, then turn back to the QB"),
    RouteDef("Comeback", lambda d, s: [seg(0, d), seg(11, 2)], 12, "up, then back toward the sideline"),
    RouteDef("Hitch", lambda d, s: [seg(0, 5), seg(7, 1)], 5, "quick five-yard stop"),
    RouteDef("Flat", lambda d, s: [seg(5, d)], 6, "straight to the flat"),
    RouteDef("Drag", lambda d, s: [seg(0, 2), seg(4, d)], 12, "shallow cross under the linebackers"),
    RouteDef("Wheel", lambda d, s: [seg(5, 5), seg(0, d)], 15, "to the flat, then turn up the sideline"),
    RouteDef("Screen", lambda d, s: [seg(8, 4), seg(5, d)], 5, "chip, then slip out for the screen"),
    RouteDef("Stick", lambda d, s: [seg(0, 6), seg(7, 1)], 6, "six yards and sit"),
    RouteDef("Block (stay in)", lambda d, s: [seg(9, 21 * (1 if s >= 0 else -1))], 0, "stay in and pass protect"),
]
ROUTES_BY_NAME = {r.name: r for r in ROUTE_LIBRARY}


def route_chain(name: str, depth_yd: float | None, side: int) -> Chain:
    r = ROUTES_BY_NAME[name]
    return [start(3), *r.build(depth_yd if depth_yd is not None else r.default_depth, side)]


def blocker_chain(style: str, side: int, run: bool) -> Chain:
    """style: 'straight' | 'left' | 'right' | 'pull-left' | 'pull-right' | 'pass'"""
    if not run or style == "pass":
        return [start(3), leg(1, 0, -1, turn=2, end=1)]
    if style == "left":
        return [start(3), leg(0, -1, 1, turn=1)]
    if style == "right":
        return [start(3), leg(0, 1, 1, turn=0)]
    if style == "pull-left":
        return [start(3), leg(2, -8, 1, turn=2, group=1, rel=0)]
    if style == "pull-right":
        return [start(3), leg(2, 8, 1, turn=2, group=1, rel=0)]
    return [start(3), leg(0, 0, 1, turn=2)]


def center_chain(qb_slot: int, style: str, run: bool) -> Chain:
    body = blocker_chain(style, 0, run)
    return [start(2), (0x02, [qb_slot]), *body[1:]]


def stalk_block_chain() -> Chain:
    return [start(3), leg(3, 0, 5, turn=2, group=1)]


def lead_block_chain(dx_yd: float, dy_yd: float) -> Chain:
    return [start(3), leg(4, dx_yd, dy_yd, turn=2, group=1, rel=0)]


def qb_pass_chain(shotgun: bool, drop_yd: float = 5.0) -> Chain:
    return [start(4), (0x03, [0]), (0x04, [0, 0.0, (-1.0 if shotgun else -drop_yd) * YD, 0]), (0x06, [0, 1, 4, 2, 3, 0.0])]


def qb_handoff_chain(carrier_slot: int, kind: int, draw: bool = False, shotgun: bool = False) -> Chain:
    """kind: 0 dive/iso handoff, 1 toss, 2 reverse-style, 4 draw handoff."""
    chain: Chain = [start(4), (0x03, [0])]
    if draw:
        chain.append((0x04, [0, 0.0, (-1.0 if shotgun else -5.0) * YD, 0]))
    chain.append((0x13, [carrier_slot, kind]))
    return chain


def qb_fake_then_pass(carrier_slot: int, shotgun: bool) -> Chain:
    return [start(4), (0x03, [0]), (0x14, [carrier_slot, 0]), (0x06, [0, 2, 1, 3, 5, 0.0])]


def qb_sneak_chain() -> Chain:
    return [start(4), (0x03, [0]), (0x04, [0, 0.0, -1.0 * YD, 0]), (0x15, [1, 0.0, 1.0 * YD, 2, 15, 0, 0])]


def qb_keeper_chain(dx_yd: float, dy_yd: float, shotgun: bool) -> Chain:
    return [start(4), (0x03, [0]), (0x04, [0, 0.0, (-1.0 if shotgun else -3.0) * YD, 0]), (0x15, [0, dx_yd * YD, dy_yd * YD, 2, 15, 0, 0])]


def carrier_chain(lane: int, path: tuple[int, float, float, int] | None, follow_slot: int | None = None, take_kind: int = 0) -> Chain:
    """lane 0-15 aim lane; path = (mode, dx_yd, dy_yd, a) or None; follow_slot for lead-follow runs."""
    chain: Chain = [start(3), (0x16, [take_kind, 0.0, lane])]
    if follow_slot is not None:
        chain.append((0x15, [2, -0.3 * YD, 0.0, 0, 15, follow_slot, 1]))
    elif path is not None:
        mode, dx, dy, a = path
        chain.append((0x15, [mode, dx * YD, dy * YD, a, 15, 0, 0]))
    return chain


def fake_carrier_chain(lane: int, after: Chain) -> Chain:
    return [start(3), (0x17, [0, 0.0, lane]), *after[1:]]


def reverse_first_back(lane: int, wr_slot: int) -> Chain:
    return [start(3), (0x16, [1, 0.0, lane]), (0x13, [wr_slot, 2]), leg(4, 3, 1.7, turn=2, group=1, rel=1)]


def reverse_receiver(side: int) -> Chain:
    return [start(3), (0x16, [0, 0.1, 8]), (0x15, [0, -10 * YD * side, -5 * YD, 2, 15, 0, 0])]


# ---------------------------------------------------------------------------
# Whole-play generation
# ---------------------------------------------------------------------------

@dataclass
class PlayerAssignment:
    kind: str                     # "route" | "block" | "carry" | "lead" | "stalk" | "qb" | "custom" | "fake_carry"
    route: str | None = None
    depth: float | None = None
    block_style: str = "straight"
    custom: Chain | None = None


@dataclass
class ScreenPreset:
    """Coordinated native grammar; WR/TE adaptations are unwitnessed hypotheses."""
    variant: str = "HB"
    receiver_slot: int | None = None
    side: int = -1
    hold_seconds: float = 0.8
    drop_yards: float = 7.0
    pass_delay: float = 0.6


SCREEN_CONCEPTS = {"HB Screen": "HB", "WR Screen": "WR", "TE Screen": "TE"}


def screen_preset(variant: str, receiver_slot: int | None = None,
                  side: int = -1, level: str = "D") -> ScreenPreset:
    if variant not in ("HB", "WR", "TE") or level not in ("Retail", "A", "B", "C", "D"):
        raise ValueError("Choose an HB, WR or TE screen and Retail/A/B/C/D timing.")
    return ScreenPreset(variant, receiver_slot, side,
                        0.8 if level in ("A", "D") else 0.5,
                        7.0 if level in ("B", "D") else 10.0,
                        0.6 if level in ("C", "D") else 0.0)


def screen_receiver_chain(side: int) -> Chain:
    # ATL:178 HB, not the old chip/flat sequence. Type 9 ends 1.5 yd behind LOS;
    # its signed distance is not an ordinary downfield route depth.
    return [start(3), seg(9, 11 * side)]


def screen_endpoint(incoming_x_cm: float, actor_x_cm: float, route_type: int = 9,
                    direction: int = 1, line_cm: float = 0.0) -> tuple[float, float]:
    """Proved endpoint adjustment (0x225BEB), not travel or catch prediction.

    incoming_x_cm is the movement solver's lateral endpoint, not encoded depth.
    """
    if route_type not in (9, 10) or direction not in (-1, 1):
        raise ValueError("Screen endpoint needs route type 9/10 and direction -1/1.")
    bound = 1798.32
    x = incoming_x_cm
    if route_type == 9:
        x = actor_x_cm if abs(actor_x_cm) >= bound else max(-bound, min(bound, x))
    return x, line_cm - direction * (1.5 if route_type == 9 else 1.0) * YD


def screen_blocker_chain(kind: int, settings: ScreenPreset, qb_slot: int) -> Chain:
    side = settings.side
    turn = 1 if side < 0 else 0
    chain = [start(2 if kind == C else 3)]
    if kind == C:
        chain.append((0x02, [qb_slot]))
    chain.extend([
        leg(1, side / 3, -1, turn=turn, end=2, t=settings.hold_seconds),
        (0x18, [0, side * {T: 14, C: 10, G: 12}[kind] * YD, -2 * YD, 2, 15, 0, 0]),
        leg(3, 0, 2, turn=turn),
    ])
    return chain


def screen_qb_chain(settings: ScreenPreset) -> Chain:
    if settings.receiver_slot is None or not 6 <= settings.receiver_slot <= 10:
        raise ValueError("The intended screen receiver must be in assignment slot 6 through 10.")
    return [start(4), (0x03, [0]), (0x04, [0, 0.0, -settings.drop_yards * YD, 0]),
            (0x06, [5, settings.receiver_slot - 5, 0, 0, 0, settings.pass_delay])]


def _screen_assignments(spec: "PlaySpec", variant: str) -> None:
    settings = spec.screen or screen_preset(variant)
    settings.variant = variant
    kind = {"HB": HB, "WR": WR, "TE": TE}[variant]
    candidates = [s for s in range(6, 11) if spec.kinds[s] == kind]
    if settings.receiver_slot is None:
        settings.receiver_slot = next(iter(candidates), None)
    if settings.receiver_slot not in candidates:
        raise ValueError(f"This screen needs a {variant} in assignment slot 6 through 10.")
    if settings.side not in (-1, 1):
        raise ValueError("Choose left or right for the screen.")
    if (not math.isfinite(settings.hold_seconds) or not 0.1 <= settings.hold_seconds <= 6.3
            or not math.isfinite(settings.drop_yards) or not 0 <= settings.drop_yards <= 20
            or not math.isfinite(settings.pass_delay) or not 0 <= settings.pass_delay <= 6.3):
        raise ValueError("Screen timing is outside the supported range; releasing blockers need a finite hold.")
    spec.screen = settings
    # Keep two protectors. The center and the tackle/guard on the chosen side release.
    for k in (C, T, G):
        slots = [s for s in range(1, 6) if spec.kinds[s] == k]
        if not slots:
            raise ValueError("The native screen needs a center, tackles and guards in slots 1 through 5.")
        slot = max(slots, key=lambda s: settings.side * spec.positions[s][0])
        spec.assignments[slot] = PlayerAssignment("screen_release")
    for s in range(6, 11):
        if s == settings.receiver_slot:
            spec.assignments[s] = PlayerAssignment("screen_receiver")
        elif spec.kinds[s] in (HB, FB, TE):
            spec.assignments[s] = PlayerAssignment("block", block_style="pass")


@dataclass
class PlaySpec:
    name: str
    play_type: str                  # "pass" | "run" | "pa_pass" | "sneak" | "keeper" | "reverse"
    positions: list[tuple[int, int]]  # cm, slot order
    kinds: list[int]                # position kinds per slot
    assignments: dict[int, PlayerAssignment]
    carrier_slot: int | None = None
    handoff_kind: int = 0           # 0 handoff, 1 toss, 4 draw
    run_direction: str = "middle"   # left | middle | right
    reverse_slot: int | None = None
    shotgun: bool | None = None
    direct_snap: bool = False       # wildcat: the ball is snapped straight to the carrier
    screen: ScreenPreset | None = None


RUN_SCHEMES: dict[str, dict] = {
    "Inside Zone": {"kind": 0, "dir": "middle", "lane": (8, 6, 10), "path": (1, 0, 3, 0), "blurb": "straight-ahead zone blocking, back reads the hole"},
    "Dive / Iso": {"kind": 0, "dir": "middle", "lane": (8, 7, 9), "path": (1, 0, 3, 0), "lead": True, "blurb": "fullback leads through the hole"},
    "Power": {"kind": 0, "dir": "right", "lane": (8, 4, 12), "path": (0, 2, 2, 2), "pull": True, "lead": True, "blurb": "backside guard pulls, FB kicks out"},
    "Counter": {"kind": 0, "dir": "left", "lane": (8, 12, 4), "path": (0, -3, 2, 2), "pull": True, "blurb": "back fakes one way, guard pulls the other"},
    "Outside Zone / Stretch": {"kind": 0, "dir": "right", "lane": (8, 3, 13), "path": (0, 7, 1, 2), "blurb": "everybody reaches to the play side"},
    "Toss": {"kind": 1, "dir": "right", "lane": (8, 3, 13), "path": (0, 10, -1, 2), "blurb": "QB pitches to the back going wide"},
    "Sweep": {"kind": 0, "dir": "right", "lane": (8, 3, 13), "path": (0, 9, 0, 2), "pull": True, "blurb": "handoff wide with a pulling guard"},
    "Draw": {"kind": 4, "dir": "middle", "lane": (8, 6, 10), "path": (1, 0, 3, 0), "draw": True, "blurb": "QB drops like a pass, then hands off"},
    "QB Sneak / Tush Push": {"kind": None, "dir": "middle", "blurb": "QB takes it right behind the center; backs push"},
    "QB Keeper": {"kind": None, "dir": "right", "blurb": "QB runs it himself around the edge"},
    "Reverse": {"kind": 2, "dir": "left", "blurb": "handoff to the back, who hands to a receiver coming back the other way"},
}

PASS_CONCEPTS: dict[str, dict] = {
    "4 Verts": {"blurb": "every receiver runs a go", "outside": "Go", "inside": "Go", "te": "Go", "back": "Block (stay in)"},
    "Mesh": {"blurb": "two shallow crossers under, corner and go over the top", "outside": "Corner", "inside": "Drag", "te": "Drag", "back": "Flat"},
    "Smash": {"blurb": "hitch outside, corner from the slot", "outside": "Hitch", "inside": "Corner", "te": "Curl", "back": "Flat"},
    "Flood": {"blurb": "go, out and flat stacked to one side", "outside": "Go", "inside": "Out", "te": "Flat", "back": "Block (stay in)"},
    "Levels": {"blurb": "dig over a drag", "outside": "In / Dig", "inside": "Drag", "te": "Go", "back": "Flat"},
    "Stick": {"blurb": "quick stick and flat with a go outside", "outside": "Go", "inside": "Stick", "te": "Stick", "back": "Flat"},
    "Slant-Flat": {"blurb": "slants with the back to the flat", "outside": "Slant", "inside": "Slant", "te": "Slant", "back": "Flat"},
    "Drive": {"blurb": "drag and dig from the same side", "outside": "Drag", "inside": "In / Dig", "te": "Curl", "back": "Block (stay in)"},
    "Dagger": {"blurb": "go clears, dig comes in behind", "outside": "In / Dig", "inside": "Go", "te": "Curl", "back": "Block (stay in)"},
    "Curl-Flat": {"blurb": "curls outside, backs to the flat", "outside": "Curl", "inside": "Curl", "te": "Out", "back": "Flat"},
    "Y-Cross": {"blurb": "the tight end crosses on a dig under a post, comeback outside", "outside": "Comeback", "inside": "Post", "te": "In / Dig", "back": "Flat"},
    "Snag": {"blurb": "slant inside, corner over the top of it, back to the flat", "outside": "Slant", "inside": "Corner", "te": "Stick", "back": "Flat"},
    "HB Screen": {"blurb": "EXPERIMENTAL / UNWITNESSED: back with releasing blockers", "outside": "Go", "inside": "Go", "te": "Block (stay in)", "back": "Screen"},
    "WR Screen": {"blurb": "EXPERIMENTAL / UNWITNESSED: receiver with releasing blockers", "outside": "Go", "inside": "Go", "te": "Block (stay in)", "back": "Screen"},
    "TE Screen": {"blurb": "EXPERIMENTAL / UNWITNESSED: tight end with releasing blockers", "outside": "Go", "inside": "Go", "te": "Block (stay in)", "back": "Screen"},
    "Wheel": {"blurb": "back wheels up the sideline", "outside": "Post", "inside": "Drag", "te": "Out", "back": "Wheel"},
}


def default_assignments(spec: PlaySpec, concept: str | None = None, scheme: str | None = None) -> None:
    """Fill spec.assignments with sensible defaults for the play type."""
    kinds = spec.kinds
    xs = [x for x, _ in spec.positions]
    spec.assignments.clear()
    if concept not in SCREEN_CONCEPTS or spec.play_type != "pass":
        spec.screen = None
    receivers = [s for s in range(11) if kinds[s] in (WR, TE)]
    backs = [s for s in range(11) if kinds[s] in (HB, FB)]
    outer = sorted(receivers, key=lambda s: -abs(xs[s]))
    if spec.play_type in ("pass", "pa_pass"):
        con = PASS_CONCEPTS.get(concept or "4 Verts", PASS_CONCEPTS["4 Verts"])
        for s in range(11):
            k = kinds[s]
            if k in OL_KINDS:
                spec.assignments[s] = PlayerAssignment("block", block_style="pass")
            elif k == QB:
                spec.assignments[s] = PlayerAssignment("qb")
            elif k == TE:
                spec.assignments[s] = PlayerAssignment("route", route=con["te"])
            elif k == WR:
                spec.assignments[s] = PlayerAssignment("route", route=con["outside"] if s in outer[:2] else con["inside"])
            else:
                spec.assignments[s] = PlayerAssignment("route", route=con["back"])
        if concept in SCREEN_CONCEPTS:
            if spec.play_type != "pass":
                raise ValueError("The experimental screen preset requires the Pass play type.")
            _screen_assignments(spec, SCREEN_CONCEPTS[concept])
    else:
        sch = RUN_SCHEMES.get(scheme or "Inside Zone", RUN_SCHEMES["Inside Zone"])
        dir_sign = {"left": -1, "middle": 0, "right": 1}[spec.run_direction]
        for s in range(11):
            k = kinds[s]
            if k == QB:
                spec.assignments[s] = PlayerAssignment("qb")
            elif k in OL_KINDS:
                style = "straight"
                if sch.get("pull") and k == G and (xs[s] < 0) == (dir_sign > 0):
                    style = "pull-right" if dir_sign > 0 else "pull-left"
                elif dir_sign:
                    style = "right" if dir_sign > 0 else "left"
                spec.assignments[s] = PlayerAssignment("block", block_style=style)
            elif s == spec.carrier_slot and spec.play_type in ("run", "reverse"):
                spec.assignments[s] = PlayerAssignment("carry")
            elif k in BACK_KINDS and spec.play_type in ("sneak", "keeper"):
                spec.assignments[s] = PlayerAssignment("lead")
            elif k == FB and sch.get("lead"):
                spec.assignments[s] = PlayerAssignment("lead")
            elif k in (WR, TE):
                spec.assignments[s] = PlayerAssignment("stalk")
            else:
                spec.assignments[s] = PlayerAssignment("block", block_style="pass" if spec.play_type == "pa_pass" else "straight")


def build_chains(spec: PlaySpec, scheme: str | None = None) -> list[Chain]:
    """Turn a PlaySpec into eleven node chains."""
    kinds = spec.kinds
    xs = [x for x, _ in spec.positions]
    qb_slot = next(s for s in range(11) if kinds[s] == QB)
    snapper = next((s for s in range(11) if kinds[s] == C), 3)
    shotgun = spec.shotgun if spec.shotgun is not None else spec.positions[qb_slot][1] <= codec.SHOTGUN_DEPTH_THRESHOLD_CM
    run = spec.play_type in ("run", "sneak", "keeper", "reverse")
    sch = RUN_SCHEMES.get(scheme or "", {})
    dir_sign = {"left": -1, "middle": 0, "right": 1}[spec.run_direction]
    lane = 8
    if sch.get("lane"):
        lane = sch["lane"][{-1: 1, 0: 0, 1: 2}[dir_sign]]
    fb_slot = next((s for s in range(11) if kinds[s] == FB), None)
    direct = spec.direct_snap and spec.carrier_slot is not None and run
    snap_target = spec.carrier_slot if direct else qb_slot
    chains: list[Chain] = []
    for s in range(11):
        a = spec.assignments.get(s) or PlayerAssignment("block", block_style="pass" if not run else "straight")
        side = 1 if xs[s] >= 0 else -1
        k = kinds[s]
        if spec.screen is not None:
            if a.kind == "screen_release":
                chains.append(screen_blocker_chain(k, spec.screen, qb_slot)); continue
            if a.kind == "screen_receiver":
                chains.append(screen_receiver_chain(spec.screen.side)); continue
            if k == QB and a.kind == "qb":
                chains.append(screen_qb_chain(spec.screen)); continue
        if a.kind == "custom" and a.custom:
            chains.append(list(a.custom)); continue
        if s == snapper:
            style = a.block_style if a.kind == "block" else ("straight" if run else "pass")
            chains.append(center_chain(snap_target, style, run)); continue
        if direct and s == spec.carrier_slot:
            path = sch.get("path", (1, 0, 3, 0))
            if dir_sign < 0 and path:
                path = (path[0], -abs(path[1]), path[2], path[3])
            mode, dx, dy, aa = path
            chains.append([start(4), (0x03, [0]), (0x15, [mode, dx * YD, dy * YD, aa, 15, 0, 0])]); continue
        if direct and k == QB:
            chains.append(route_chain("Go", 12, side) if a.kind == "route" else stalk_block_chain()); continue
        if k == QB or a.kind == "qb":
            if spec.play_type == "pass":
                chains.append(qb_pass_chain(shotgun))
            elif spec.play_type == "pa_pass":
                chains.append(qb_fake_then_pass(spec.carrier_slot if spec.carrier_slot is not None else next(b for b in range(11) if kinds[b] in BACK_KINDS), shotgun))
            elif spec.play_type == "sneak":
                chains.append(qb_sneak_chain())
            elif spec.play_type == "keeper":
                chains.append(qb_keeper_chain(6 * (dir_sign or 1), 3, shotgun))
            else:
                carrier = spec.carrier_slot if spec.carrier_slot is not None else next(b for b in range(11) if kinds[b] in BACK_KINDS)
                chains.append(qb_handoff_chain(carrier, 1 if spec.handoff_kind == 1 else (4 if spec.handoff_kind == 4 else 0), draw=spec.handoff_kind == 4, shotgun=shotgun))
            continue
        if a.kind == "carry":
            if spec.play_type == "reverse" and spec.reverse_slot is not None:
                chains.append(reverse_first_back(lane, spec.reverse_slot)); continue
            path = sch.get("path", (1, 0, 3, 0))
            if dir_sign < 0 and path:
                path = (path[0], -abs(path[1]), path[2], path[3])
            follow = fb_slot if (sch.get("lead") and fb_slot is not None and fb_slot != s) else None
            chains.append(carrier_chain(lane, tuple(path), follow_slot=follow)); continue
        if a.kind == "fake_carry":
            chains.append(fake_carrier_chain(lane, blocker_chain("pass", side, False))); continue
        if spec.play_type == "reverse" and s == spec.reverse_slot:
            chains.append(reverse_receiver(side)); continue
        if a.kind == "route":
            chains.append(route_chain(a.route or "Go", a.depth, side)); continue
        if a.kind == "lead":
            if spec.play_type == "sneak":
                chains.append(lead_block_chain(0, 1)); continue
            chains.append(lead_block_chain(2 * (dir_sign or 1), 1)); continue
        if a.kind == "stalk":
            chains.append(stalk_block_chain()); continue
        chains.append(blocker_chain(a.block_style, side, run))
    return chains


def validate_chains(play_flags: int, donor_chains: list[tuple[int, list[bytes]]], chains: list[Chain]) -> str | None:
    assignments = []
    for s in range(11):
        nodes = [codec.Node(op, 0, list(vals)) for op, vals in chains[s]]
        codec.assign_node_flags(nodes)
        assignments.append((donor_chains[s][0], [n.to_bytes() for n in nodes]))
    for s in range(11):
        desc = codec.build_descriptor(play_flags, assignments, s, donor_chains[s][0] >> 24)
        assignments[s] = (desc, assignments[s][1])
    return codec.validate_play(play_flags, assignments)


# ---------------------------------------------------------------------------
# Hand-drawn routes → the game's route segments
# ---------------------------------------------------------------------------

ROUTE_MAX_NODES = 3          # stock receiver chains carry at most three route segments


def _simplify(points: Sequence[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Douglas–Peucker line simplification."""
    pts = [tuple(p) for p in points]
    if len(pts) < 3:
        return pts

    def dist(p, a, b):
        (px, py), (ax, ay), (bx, by) = p, a, b
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    def rec(lo, hi):
        best, idx = 0.0, -1
        for i in range(lo + 1, hi):
            d = dist(pts[i], pts[lo], pts[hi])
            if d > best:
                best, idx = d, i
        if best > tolerance:
            return rec(lo, idx)[:-1] + rec(idx, hi)
        return [pts[lo], pts[hi]]

    return rec(0, len(pts) - 1)


def quantize_drawn_route(points_cm: Sequence[tuple[float, float]], side: int,
                         max_nodes: int = ROUTE_MAX_NODES) -> tuple[Chain, str]:
    """Turn a polyline drawn from a receiver (cm, +z downfield, first point = his spot)
    into a route chain the game runs: straight stems, 30/45/60° breaks in, a 45°
    break out, laterals in/out, comebacks.  Returns the chain and a plain description."""
    pts = [(float(x), float(z)) for x, z in points_cm]
    if len(pts) < 2:
        raise ValueError("draw a line from the player first")
    tol = 0.9 * YD
    legs: list[tuple[float, float]] = []
    for _ in range(6):
        simple = _simplify(pts, tol)
        legs = []
        for (ax, az), (bx, bz) in zip(simple, simple[1:]):
            dx, dz = bx - ax, bz - az
            length = math.hypot(dx, dz)
            if length < 0.5 * YD:
                continue
            inward = -side * dx
            angle = math.degrees(math.atan2(inward, dz))      # 0 = downfield, + = toward the middle
            if legs and abs(angle - legs[-1][1]) < 12:
                legs[-1] = (legs[-1][0] + length, (legs[-1][1] * legs[-1][0] + angle * length) / (legs[-1][0] + length))
            else:
                legs.append((length, angle))
        if len(legs) <= max_nodes + 1:
            break
        tol *= 1.6
    if not legs:
        raise ValueError("that line is too short to be a route")
    nodes: Chain = []
    words: list[str] = []
    stem = 0.0

    def flush_stem() -> None:
        nonlocal stem
        if stem > 0:
            yards = max(1.0, min(40.0, round(stem / YD)))
            nodes.append(seg(0, yards))
            words.append(f"{yards:.0f} yd up")
            stem = 0.0

    for length, angle in legs:
        aa = abs(angle)
        inward = angle > 0
        if aa < 20:
            stem += length
        elif aa < 75:
            yards = max(1.0, min(40.0, round(stem / YD))) if stem > 0 else 1.0
            if inward:
                t = 1 if aa < 37 else (2 if aa < 55 else 3)
                deg = {1: 30, 2: 45, 3: 60}[t]
                words.append(f"{yards:.0f} yd up, then {deg}° in" + (" (post)" if t == 2 else ""))
            else:
                t = 6
                words.append(f"{yards:.0f} yd up, then 45° out (corner)")
            nodes.append(seg(t, yards))
            stem = 0.0
        elif aa < 115:
            flush_stem()
            yards = max(1.0, min(30.0, round(length / YD)))
            nodes.append(seg(4 if inward else 5, yards))
            words.append(f"{yards:.0f} yd across the middle" if inward else f"{yards:.0f} yd to the sideline")
        else:
            flush_stem()
            nodes.append(seg(7 if inward else 11, 2))
            words.append("comeback inside" if inward else "comeback toward the sideline")
    flush_stem()
    trimmed = ""
    if len(nodes) > max_nodes:
        nodes = nodes[:max_nodes]
        words = words[:max_nodes]
        trimmed = " (kept the first three moves — the game runs at most three)"
    return [start(3), *nodes], ", ".join(words) + trimmed


def lane_for_x(x_cm: float) -> int:
    """The rush-lane index nearest an x position (cm)."""
    return min(range(len(codec.LANE_TABLE_CM)), key=lambda i: abs(codec.LANE_TABLE_CM[i] - x_cm))


def drawn_run_path(points_cm: Sequence[tuple[float, float]], side: int) -> tuple[int, tuple[int, float, float, int], str]:
    """A hand-drawn ball-carrier path → (aim lane, run-path operand, description)."""
    pts = [(float(x), float(z)) for x, z in points_cm]
    if len(pts) < 2:
        raise ValueError("draw the path from the ball carrier first")
    x0, z0 = pts[0]
    xe, ze = pts[-1]
    cross = next(((x, z) for (x, z) in pts if z >= 0), (xe, ze))
    lane = lane_for_x(cross[0])
    dx_yd = (xe - x0) * side / YD
    dz_yd = (ze - z0) / YD
    where = "left" if xe < x0 - YD else ("right" if xe > x0 + YD else "straight ahead")
    return lane, (0, round(dx_yd, 1), round(dz_yd, 1), 2), f"runs {where} to {dz_yd:+.0f} yd"


# ---------------------------------------------------------------------------
# "Outdated" suggestions
# ---------------------------------------------------------------------------

OLD_FORMATION_WORDS = ("split", "weak i", "strong i", "i pro", "i twins", "i spread", "i jokers", "wishbone", "flip", "clock", "straight")
OLD_PLAY_WORDS = ("dive", "iso", "weak", "strong", "blast", "trap", "counter", "sweep", "dump", "stops")


def suggest_formations_to_replace(book: Nfl2k5Playbook, body: bytes, category_index: int | None = None) -> list[tuple[int, str]]:
    """Ranked (formation_index, reason) among offensive formations, most outdated first."""
    scored = []
    for f in book.formations:
        rec = formation_record(body, f.index)
        if rec.type_code >= 4:
            continue
        name = f.name.lower()
        score = 0
        reasons = []
        for w in OLD_FORMATION_WORDS:
            if w in name:
                score += 3
                reasons.append(f"“{w}” looks dated")
                break
        if category_index is not None and formation_category(body, f.index) == category_index:
            score += 2
            reasons.append("same personnel group as your design")
        if len(f.play_links) < 12:
            score += 1
            reasons.append(f"only {len(f.play_links)} plays listed")
        scored.append((score, f.index, ", ".join(reasons) or "stock formation"))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [(idx, reason) for _s, idx, reason in scored]


def suggest_plays_to_replace(book: Nfl2k5Playbook, formation_index: int) -> list[tuple[int, str]]:
    """Ranked (play_index, reason) among the plays listed in a formation."""
    links = book.formations[formation_index].play_links
    usage = {}
    for f in book.formations:
        for l in f.play_links:
            usage[l.play_index] = usage.get(l.play_index, 0) + 1
    scored = []
    for l in links:
        p = book.plays[l.play_index]
        name = p.name.lower()
        score = 0
        reasons = []
        if usage.get(p.index, 0) == 1:
            score += 3
            reasons.append("only listed here (nothing else loses it)")
        for w in OLD_PLAY_WORDS:
            if w in name:
                score += 1
                reasons.append(f"“{w}”")
                break
        scored.append((score, p.index, ", ".join(reasons) or f"listed in {usage.get(p.index, 0)} formations"))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [(idx, reason) for _s, idx, reason in scored]



# ---------------------------------------------------------------------------
# Play header flags: the class the game plays a play as
# ---------------------------------------------------------------------------
# Bits 0-5 are the type code and 6-8 the family (both checked by the validator).
# Bits 12-15 are the play class, read by the game itself rather than inferred from the
# QB's chain: every stock dropback / play-action pass ('50', 'RO', 'PA') carries 0x6000,
# the '90' quick game 0x2000 (+ bit 26), handoffs / draws / QB runs 0x8000 (ATL corpus,
# 139 offensive plays, no exceptions).  Bit 21 marks play-action fakes (and the bootleg /
# naked QB runs), bit 27 the specials (Take Knee, Spike, fakes, Hail Mary).  A pass chain
# under a run-class header is played as a RUN: the receiver icons flash and vanish at the
# snap, the QB becomes a ball carrier and cannot throw.  That is exactly what happened to
# the first wizard pass play (donor = the book's first offensive play, a run).
PLAY_CLASS_MASK = 0xF000
PLAY_CLASS_PASS = 0x6000
PLAY_CLASS_QUICK = 0x2000
PLAY_CLASS_RUN = 0x8000
PLAY_FLAG_PLAY_ACTION = 0x200000
PLAY_FLAG_QUICK = 0x4000000
PLAY_FLAG_SPECIAL = 0x8000000
PLAY_FLAGS_KEEP_MASK = 0x1FF          # type code + family: must stay the donor's

WANTED_SIGNATURE = {"pass": "pass", "pa_pass": "pa_pass", "run": "run", "sneak": "qb_run",
                    "keeper": "qb_run", "reverse": "run"}


def qb_signature(qb_chain: Sequence) -> str:
    """Shape of a QB chain from its opcodes: 'pass' (dropback), 'pa_pass' (fake then throw),
    'run' (handoff), 'draw' (drop then handoff), 'qb_run' (sneak / keeper / bootleg / QB draw)
    or 'other'.  Accepts raw 8-byte nodes or (opcode, operands) tuples."""
    ops = {(n[0] if isinstance(n, (bytes, bytearray)) else int(n[0])) for n in qb_chain}
    if 0x13 in ops:
        return "draw" if 0x04 in ops else "run"
    if 0x06 in ops:
        return "pa_pass" if 0x14 in ops else "pass"
    if 0x15 in ops or 0x09 in ops:
        return "qb_run"
    return "other"


def play_class_label(flags: int) -> str:
    """'pass' | 'run' | 'other' from a play header's class bits."""
    if flags & PLAY_CLASS_RUN:
        return "run"
    if flags & 0x6000:
        return "pass"
    return "other"


def class_flags_for(play_type: str, flags: int) -> int:
    """Force ``flags`` into the class the wizard play type needs (type code / family kept)."""
    want_pass = play_type in ("pass", "pa_pass")
    ok = play_class_label(flags) == ("pass" if want_pass else "run")
    if ok:
        return flags
    out = flags & ~(PLAY_CLASS_MASK | PLAY_FLAG_QUICK | PLAY_FLAG_SPECIAL)
    out |= PLAY_CLASS_PASS if want_pass else PLAY_CLASS_RUN
    if play_type != "pa_pass":
        out &= ~PLAY_FLAG_PLAY_ACTION
    return out


def reference_play_for(book: Nfl2k5Playbook, body: bytes, play_type: str, scheme: str | None = None) -> tuple[int, int]:
    """(donor play index, header flags) for a wizard play: the stock offensive play of this
    book whose QB chain has the same shape and whose header carries the class the game must
    play it as (the most common flags word in that group).  Falls back to any offensive
    play with the class bits forced, so a pass is never staged under a run header."""
    wanted = WANTED_SIGNATURE.get(play_type, "pass")
    if play_type == "run" and scheme == "Draw":
        wanted = "draw"
    cands: list[tuple[int, int, str]] = []
    for p in book.plays:
        if p.family_id != 0:
            continue
        flags, chains = play_chains(body, p.index)
        cands.append((p.index, flags, qb_signature(chains[0][1])))
    plain = lambda f: not f & (PLAY_FLAG_PLAY_ACTION | PLAY_FLAG_QUICK | PLAY_FLAG_SPECIAL)  # noqa: E731
    not_special = lambda f: not f & PLAY_FLAG_SPECIAL  # noqa: E731
    is_pa = lambda f: bool(f & PLAY_FLAG_PLAY_ACTION) and not f & PLAY_FLAG_SPECIAL  # noqa: E731
    is_run = lambda f: bool(f & PLAY_CLASS_RUN) and not f & PLAY_FLAG_SPECIAL  # noqa: E731
    is_pass = lambda f: play_class_label(f) == "pass" and not f & PLAY_FLAG_SPECIAL  # noqa: E731
    order = {
        "pass": [("pass", lambda f: is_pass(f) and plain(f)), ("pass", is_pass), ("pa_pass", is_pass)],
        "pa_pass": [("pa_pass", is_pa), ("pa_pass", is_pass), ("pass", lambda f: is_pass(f) and plain(f))],
        "run": [("run", is_run), ("draw", is_run), ("qb_run", is_run), ("run", not_special)],
        "draw": [("draw", is_run), ("run", is_run), ("qb_run", is_run), ("draw", not_special)],
        "qb_run": [("qb_run", is_run), ("draw", is_run), ("run", is_run), ("qb_run", not_special)],
    }[wanted]
    for sig, ok in order:
        group = [(i, f) for i, f, s in cands if s == sig and ok(f)]
        if group:
            common = Counter(f for _, f in group).most_common(1)[0][0]
            index = next(i for i, f in group if f == common)
            return index, class_flags_for(play_type, common)
    if cands:
        index, flags, _ = cands[0]
        return index, class_flags_for(play_type, flags)
    return 0, class_flags_for(play_type, play_chains(body, 0)[0])


__all__ = [
    "PLAY_CLASS_MASK", "PLAY_CLASS_PASS", "PLAY_CLASS_QUICK", "PLAY_CLASS_RUN", "PLAY_FLAG_PLAY_ACTION",
    "PLAY_FLAG_QUICK", "PLAY_FLAG_SPECIAL", "PLAY_FLAGS_KEEP_MASK", "qb_signature", "play_class_label",
    "class_flags_for", "reference_play_for",
    "FORMATION_TEMPLATES", "PASS_CONCEPTS", "RUN_SCHEMES", "ROUTE_LIBRARY", "ROUTES_BY_NAME",
    "FittedFormation", "PlaySpec", "PlayerAssignment", "TemplatePlayer", "build_chains",
    "default_assignments", "fit_template", "formation_category", "formation_record",
    "offense_formations", "offense_plays", "play_chains", "suggest_formations_to_replace",
    "suggest_plays_to_replace", "validate_chains", "category_positions",
    "PersonnelPlan", "SKILL_CHOICES", "SKILL_SLOTS", "ranked_codes", "resolve_personnel", "donor_for_personnel",
    "is_offense_category", "back_count", "quantize_drawn_route", "drawn_run_path", "lane_for_x",
]
