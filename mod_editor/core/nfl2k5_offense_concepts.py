"""Modern offense concept engine for NFL 2K5 PLAY books (beta 77, job p48o).

The engine turns football designs into assignment chains made only of the
grammar the retail 2004 books already execute.  It is shared by the SOFTDRINK
book generator (``pb/v2``) and by the Studio's Create a Play wizard, so every
route, concept, screen and trick play here is also a wizard option.

Ground truth (all offline, nothing here is a gameplay witness):

* Route segments (0x12) are written in feet, the unit the books store, and each
  route below names the retail chain it copies (``RETAIL``).  The native route
  initializer 0x229AE0 was traced with the real executable (job p48o): a
  non-terminal leg runs exactly its encoded length; a terminal straight, angle
  (types 1/2/3/6) or lateral (4/5) keeps running past its length; comebacks
  settle at their end: type 7 back toward the sideline at 45 degrees, type 11
  back inside at 45 degrees, type 8 back inside at 30 degrees.
* Protections, check-release backs, run blocking, screens, the flea flicker
  and the slot reverse copy retail operands (ATL, ARZ, NYG books).
* Inside / outside is resolved by the game from the receiver's side of the
  ball, so one chain serves both sides; plays are authored strong-right and
  the game mirrors them when flipped (the CPU also scores mirrored copies).
* A pass target must finish in front of the QB's release (job p13's
  ``CHECKDOWN_BACKWARD`` rule): every back route here gains depth first.
* There is no pre-snap motion in this engine (Start nodes sit at 0,0), so no
  jet motion is faked; an end around is a QB-direct exchange with a slot
  receiver inside the retail exchange envelope.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable, Iterable, Mapping, Sequence

from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib

FT = codec.FT_CM
YD = codec.YD_CM
QB, T, C, G, TE, WR, HB, FB = lib.QB, lib.T, lib.C, lib.G, lib.TE, lib.WR, lib.HB, lib.FB
EVIDENCE = "PROVED OFFLINE grammar; gameplay UNWITNESSED"

Chain = list


# ---------------------------------------------------------------------------
# Node helpers (feet, the books' own unit)
# ---------------------------------------------------------------------------

def start(role: int = 3) -> tuple:
    return lib.start(role)


def seg(kind: int, feet: float, flag: int = 0) -> tuple:
    """Route segment: ``kind`` 0..11, distance in whole feet (retail units)."""
    return (0x12, [int(kind), int(flag), float(feet) * FT, 15])


def legf(kind: int, dx_ft: float, dy_ft: float, *, turn: int = 2, end: int = 0, group: int = 0,
         t: float = 0.0, rel: int = 1) -> tuple:
    """Block leg (0x11) with offsets in feet."""
    return (0x11, [int(kind), float(t), int(rel), int(end), int(turn), dx_ft * FT, dy_ft * FT, int(group)])


def move(dx_ft: float, dy_ft: float, mode: int = 0) -> tuple:
    return (0x04, [int(mode), dx_ft * FT, dy_ft * FT, 0])


def pass_node(reads: Sequence[int], mode: int = 0, delay: float = 0.0) -> tuple:
    """Dropback / Pass: ``reads`` are slots 6..10 in read order (missing reads are 0)."""
    ordinals = [r - 5 for r in reads if 6 <= r <= 10][:4]
    ordinals += [0] * (4 - len(ordinals))
    return (0x06, [int(mode), *ordinals, float(delay)])


def path(mode: int, dx_ft: float, dy_ft: float, a: int = 2, follow: int = 0, c: int = 0) -> tuple:
    return (0x15, [int(mode), dx_ft * FT, dy_ft * FT, int(a), 15, int(follow), int(c)])


def release(dx_ft: float, dy_ft: float, a: int = 2, b: int = 15) -> tuple:
    return (0x18, [0, dx_ft * FT, dy_ft * FT, int(a), int(b), 0, 0])


def take(hole: int, a: int = 0, t: float = 0.0) -> tuple:
    if not 0 <= int(hole) <= 8:
        raise ValueError("handoff hole must be 0..8")
    return (0x16, [int(a), float(t), int(hole)])


def fake_take(hole: int, a: int = 0, t: float = 0.0) -> tuple:
    if not 0 <= int(hole) <= 8:
        raise ValueError("handoff hole must be 0..8")
    return (0x17, [int(a), float(t), int(hole)])


def hole_toward(side: int, lateral_yd: float) -> int:
    """Native take-handoff hole nearest ``side * lateral_yd`` (0 is the middle)."""
    return lib.handoff_hole_for_x(side * lateral_yd * YD)


# ---------------------------------------------------------------------------
# Formation context: who is where, receiver numbering, strength
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Player:
    slot: int
    kind: int
    x: float          # yards, + = offense's right
    z: float          # yards, - = behind the line

    @property
    def on_los(self) -> bool:
        return abs(self.z) <= 0.17

    @property
    def side(self) -> int:
        return 1 if self.x >= 0 else -1


@dataclass
class FormationContext:
    """Eleven players in one slot order (the generator's canonical order or a book's)."""
    players: list[Player]
    labels: dict[str, int] = field(default_factory=dict)
    strong: int = 1

    @classmethod
    def build(cls, positions_cm: Sequence[tuple[float, float]], codes: Sequence[int]) -> "FormationContext":
        players = [Player(s, codes[s] & 31, positions_cm[s][0] / YD, positions_cm[s][1] / YD) for s in range(11)]
        ctx = cls(players)
        ctx._label()
        return ctx

    # -- derived views ------------------------------------------------------
    @property
    def qb(self) -> Player:
        return next(p for p in self.players if p.kind == QB)

    @property
    def gun(self) -> bool:
        return self.qb.z * YD <= codec.SHOTGUN_DEPTH_THRESHOLD_CM

    @property
    def under_center(self) -> bool:
        return not self.gun

    def ol(self) -> list[Player]:
        return [p for p in self.players if p.kind in lib.OL_KINDS]

    def center(self) -> Player:
        return next(p for p in self.players if p.kind == C)

    def backs(self) -> list[Player]:
        """Backs in the backfield (HB first, then FB), not split out as receivers."""
        out = [p for p in self.players if p.kind in (HB, FB) and self._in_backfield(p)]
        return sorted(out, key=lambda p: (p.kind != HB, abs(p.x)))

    def receivers(self) -> list[Player]:
        return [p for p in self.players if p.kind in (WR, TE, HB, FB) and not self._in_backfield(p)]

    @staticmethod
    def _in_backfield(p: Player) -> bool:
        return p.kind in (HB, FB) and p.z <= -2.5 and abs(p.x) <= 4.5

    def _label(self) -> None:
        recs = self.receivers()
        right = sorted([p for p in recs if p.x >= 0], key=lambda p: -p.x)
        left = sorted([p for p in recs if p.x < 0], key=lambda p: p.x)
        if len(right) != len(left):
            self.strong = 1 if len(right) > len(left) else -1
        else:
            inline_te = [p for p in recs if p.kind == TE and p.on_los and abs(p.x) < 7]
            self.strong = (1 if inline_te[0].x > 0 else -1) if inline_te else 1
        strong, weak = (right, left) if self.strong > 0 else (left, right)
        for n, p in enumerate(strong, 1):
            self.labels[f"S{n}"] = p.slot
        for n, p in enumerate(weak, 1):
            self.labels[f"W{n}"] = p.slot
        backs = self.backs()
        if backs:
            self.labels["B"] = backs[0].slot
        if len(backs) > 1:
            self.labels["B2"] = backs[1].slot
        tes = sorted((p for p in recs if p.kind == TE), key=lambda p: (not p.on_los, abs(p.x)))
        if tes:
            self.labels["Y"] = tes[0].slot

    def slot(self, label: str) -> int | None:
        return self.labels.get(label)

    @property
    def run_strong(self) -> int:
        """Run strength: the attached tight end's side, else the offset fullback's, else ``strong``."""
        inline = [p for p in self.players if p.kind == TE and p.on_los and abs(p.x) < 7]
        if len(inline) == 1:
            return 1 if inline[0].x > 0 else -1
        wing = [p for p in self.players if p.kind == TE and not p.on_los and abs(p.x) < 8]
        if wing:
            return 1 if wing[0].x > 0 else -1
        fb = [p for p in self.backs() if p.kind == FB and abs(p.x) > 0.5]
        if fb:
            return 1 if fb[0].x > 0 else -1
        return self.strong

    def player(self, slot: int) -> Player:
        return self.players[slot]

    def count(self, side: str) -> int:
        return sum(1 for k in self.labels if k[0] == side and k[1:].isdigit())

    @property
    def shape(self) -> str:
        """'3x1', '2x2', '2x1', '3x2', '4x1', ... strong count x weak count."""
        return f"{self.count('S')}x{self.count('W')}"

    def bunch_side(self) -> bool:
        """Three strong receivers within 4 yards of each other (a bunch / stack)."""
        xs = sorted(abs(self.player(self.labels[k]).x) for k in ("S1", "S2", "S3") if k in self.labels)
        return len(xs) == 3 and xs[-1] - xs[0] <= 4.0


# ---------------------------------------------------------------------------
# Protection and blocking chains (retail operands)
# ---------------------------------------------------------------------------

PROTECTIONS = ("quick", "dropback", "pa", "max")


def ol_chain(ctx: FormationContext, slot: int, protection: str) -> Chain:
    """Retail 90 / 50 / PA line sets (census of all 32 retail books, job p48o)."""
    p = ctx.player(slot)
    qb = ctx.qb.slot
    left = p.x < 0
    if protection == "quick":
        body = {C: [legf(1, 0, -1, turn=2, end=1)], G: [legf(1, 0, -2, turn=2, end=1)],
                T: [legf(1, 0, -3, turn=0 if left else 1, end=1)]}[p.kind]
    elif protection in ("dropback", "max"):
        body = {C: [legf(1, 0, -2, turn=2, end=1)], G: [legf(1, 0, -3, turn=2, end=1)],
                T: [legf(1, 0, -9, turn=0 if left else 1, end=1)]}[p.kind]
    elif protection == "pa":
        fake = legf(0, 0, 0, turn=2, end=0, t=0.5)
        body = {C: [fake, legf(1, 0, -5, turn=2, end=1)],
                G: [fake, legf(1, 1 if left else -1, -6, turn=2, end=1)],
                T: [fake, legf(1, 1 if left else -1, -9, turn=0 if left else 1, end=1)]}[p.kind]
    else:
        raise ValueError(protection)
    if p.kind == C:
        return [start(2), (0x02, [qb]), *body]
    return [start(3), *body]


def te_block_chain(ctx: FormationContext, slot: int) -> Chain:
    """Retail tight end pass set (50 Streaks)."""
    left = ctx.player(slot).x < 0
    return [start(3), legf(1, 0, -9, turn=0 if left else 1, end=1)]


def back_block_chain(ctx: FormationContext, slot: int) -> Chain:
    """Retail back pass protection: leg 6, step to the edge and 3 yards deep."""
    side = 1 if ctx.player(slot).x > 0.5 else -1
    return [start(3), legf(6, side * 3, -9, turn=2, end=1, group=1, rel=0)]


def stalk_chain() -> Chain:
    """Retail receiver run block: release 5 yards and stalk."""
    return [start(3), legf(3, 0, 15, turn=2, group=1)]


def drive_chain(dx_ft: float = 0, turn: int = 2) -> Chain:
    return [start(3), legf(0, dx_ft, 3, turn=turn)]


# ---------------------------------------------------------------------------
# Route tree (retail-proven encodings, feet)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RouteSpec:
    name: str
    segments: Callable[[float], list]      # depth (yards) -> [(kind, feet[, flag])]
    default_depth: float
    retail: str                            # the retail chain it copies (type:feet ...)
    blurb: str
    family: str                            # quick | intermediate | deep | crosser | back | double | screen

    def build(self, depth: float | None = None) -> list:
        d = self.default_depth if depth is None else float(depth)
        return [seg(*s) for s in self.segments(d)]


def _ft(yards: float) -> int:
    return max(1, int(round(yards * 3)))


ROUTES: dict[str, RouteSpec] = {}


def _route(name, segments, depth, retail, blurb, family):
    ROUTES[name] = RouteSpec(name, segments, depth, retail, blurb, family)


# -- vertical / outside
_route("Go", lambda d: [(0, _ft(d))], 15, "0:45", "straight up the field and keep running", "deep")
_route("Seam", lambda d: [(0, _ft(d))], 15, "0:45", "inside receiver straight up the seam", "deep")
_route("Fade", lambda d: [(6, 6), (0, _ft(d))], 15, "6:6 0:45", "release outside, then up the sideline", "deep")
_route("Post", lambda d: [(0, _ft(d)), (2, 30)], 10, "0:30 2:30", "up, then 45 degrees to the goal posts", "deep")
_route("Skinny Post", lambda d: [(0, _ft(d)), (1, 30)], 10, "0:30 1:30", "up, then a 30 degree glance inside", "deep")
_route("Corner", lambda d: [(0, _ft(d)), (6, 30)], 10, "0:30 6:30", "up, then 45 degrees to the pylon", "deep")
_route("Flag", lambda d: [(0, _ft(d)), (6, 24)], 7, "0:24 6:24", "slot corner from a short stem", "intermediate")
_route("Out", lambda d: [(0, _ft(d)), (5, 30)], 10, "0:24 5:30", "up, then square to the sideline", "intermediate")
_route("Quick Out", lambda d: [(0, _ft(d)), (5, 30)], 5, "0:15 5:30", "five yards and out", "quick")
_route("Comeback", lambda d: [(0, _ft(d)), (7, 9)], 13, "0:30 7:9", "push deep, then come back to the sideline", "intermediate")
_route("Curl", lambda d: [(0, _ft(d)), (11, 6)], 10, "0:30 11:6", "up, then turn back inside to the QB", "intermediate")
_route("Hook", lambda d: [(0, _ft(d)), (8, 6)], 8, "0:15 8:6", "up, then settle inside at 30 degrees", "intermediate")
_route("Hitch", lambda d: [(0, _ft(d)), (11, 3)], 6, "0:18 11:3", "quick stop and turn to the QB", "quick")
_route("Stick", lambda d: [(0, _ft(d)), (8, 3)], 6, "0:18 8:3", "six yards and sit inside", "quick")
_route("Slant", lambda d: [(0, _ft(d)), (1, 9)], 3, "0:9 1:9", "three steps, then slant inside", "quick")
_route("Snag", lambda d: [(0, _ft(d)), (1, 6), (8, 3)], 4, "0:12 1:6 8:3", "short slant that sits in the window", "quick")
_route("Dig", lambda d: [(0, _ft(d)), (4, 36)], 12, "0:24 4:36", "up, then flat across the middle", "intermediate")
_route("In", lambda d: [(0, _ft(d)), (4, 36)], 6, "0:18 4:36", "short square in under the linebackers", "quick")
_route("Sail", lambda d: [(0, _ft(d)), (6, 9), (5, 30)], 10, "0:30 6:9 + 5:30", "corner stem that flattens to the sideline", "intermediate")
_route("Whip", lambda d: [(0, _ft(d)), (4, 3), (5, 30)], 4, "0:30 4:3 5:21", "push, step inside, whip back out", "quick")
_route("Pivot", lambda d: [(0, _ft(d)), (4, 3), (5, 30)], 3, "0:30 4:3 5:21", "tight end pivot: in, then back out", "quick")
_route("Arrow", lambda d: [(6, 9), (5, 30)], 0, "6:9 5:30", "angle to the flat gaining depth", "quick")
_route("Flat", lambda d: [(5, 30)], 0, "5:30", "straight to the flat", "quick")
# -- crossers
_route("Drag", lambda d: [(0, _ft(d)), (4, 36)], 2, "0:6 4:36", "two yards, then across under the linebackers", "crosser")
_route("Shallow", lambda d: [(0, _ft(d)), (4, 36)], 5, "0:12 4:36", "five yard shallow cross", "crosser")
_route("Over", lambda d: [(0, _ft(d)), (2, 15), (4, 36)], 9, "0:27 2:15 4:36", "deep crosser at 12-15 yards", "crosser")
_route("Deep Cross", lambda d: [(0, _ft(d)), (2, 15), (4, 36)], 12, "0:36 2:15 4:36", "deep crosser over the linebackers", "crosser")
# -- double moves (shots)
_route("Out and Up", lambda d: [(0, _ft(d)), (5, 3), (0, 30)], 7, "0:21 5:3 0:30", "sell the out, then go", "double")
_route("Slant and Go", lambda d: [(0, _ft(d)), (2, 15), (0, 30)], 1, "0:3 2:15 0:30", "sell the slant, then go (sluggo)", "double")
_route("Stop and Go", lambda d: [(0, _ft(d)), (11, 3), (0, 30)], 10, "0:30 11:3 0:30", "sell the curl, then go", "double")
_route("Hitch and Go", lambda d: [(0, _ft(d)), (8, 6), (0, 30)], 5, "0:15 8:6 0:30", "sell the hitch, then go", "double")
_route("Post Corner", lambda d: [(0, _ft(d)), (2, 9), (6, 24)], 8, "0:24 2:9 6:24", "sell the post, break to the corner", "double")
_route("Corner Post", lambda d: [(0, _ft(d)), (6, 9), (2, 30)], 10, "0:30 6:9 2:30", "sell the corner, break to the post", "double")
_route("Wheel", lambda d: [(0, _ft(d)), (5, 30), (0, 30)], 2, "0:6 5:30 0:30", "slot wheel: flat, then up the sideline", "double")

# -- back routes (start in the backfield; every one gains depth before it flattens)
_route("Back Flat", lambda d: [(6, 12), (5, 30)], 0, "6:9 5:30", "back angles out, gaining 3 yards, to the flat", "back")
_route("Swing", lambda d: [(6, 24), (5, 30)], 0, "6:24 5:30", "back swings wide and keeps gaining depth", "back")
_route("Back Wheel", lambda d: [(6, 6), (5, 24), (0, 30)], 0, "6:6 5:24 0:30", "back to the flat, then up the sideline", "back")
_route("Angle", lambda d: [(6, 9), (3, 30)], 0, "6:9 + 3:30", "Texas: out two steps, then hard back inside", "back")
_route("Back Seam", lambda d: [(0, 45)], 0, "0:45", "back straight up the middle", "back")


def route_names(family: str | None = None) -> list[str]:
    return [n for n, r in ROUTES.items() if family is None or r.family == family]


def route_chain(name: str, depth: float | None = None) -> Chain:
    return [start(3), *ROUTES[name].build(depth)]


def check_release_chain(ctx: FormationContext, slot: int, then: str, hold: float = 1.5) -> Chain:
    """Retail check-release: block for ``hold`` seconds, then run ``then`` (last leg flagged)."""
    side = 1 if ctx.player(slot).x > 0.5 else -1
    segs = ROUTES[then].build()
    last = segs[-1]
    segs[-1] = (last[0], [last[1][0], 1, last[1][2], last[1][3]])
    return [start(3), legf(6, side * 3, -9, turn=2, end=1, group=1, rel=0, t=hold), *segs]


def route_end_depth_yd(ctx: FormationContext, slot: int, chain: Chain) -> float | None:
    """Where a route finishes (yards), mirroring job p13's linter arithmetic."""
    z = ctx.player(slot).z
    seen = False
    for node in chain:
        if node[0] != 0x12:
            continue
        kind, dist = int(node[1][0]), max(float(node[1][2]), 0.0) / YD
        seen = True
        if kind == 9:
            return None
        if kind in (0, 10):
            z += dist
        elif kind in codec.ROUTE_BREAK_DEGREES:
            z += dist * math.cos(math.radians(codec.ROUTE_BREAK_DEGREES[kind]))
        elif kind in (7, 11):
            z -= 4 * FT / YD
    return z if seen else None


FORWARD_MARGIN_YD = 1.25   # job p13: targets must finish >= 1 yd in front of the QB release


def ensure_forward(ctx: FormationContext, slot: int, chain: Chain, release_yd: float,
                   margin_yd: float = FORWARD_MARGIN_YD) -> Chain:
    """Lengthen (or insert) the first straight stem so the route finishes in front of the QB.

    Whole-yard steps keep identical chains identical across formations (they intern).
    Screens (type 9) and chains without route segments are returned unchanged."""
    end = route_end_depth_yd(ctx, slot, chain)
    if end is None or end >= release_yd + margin_yd:
        return chain
    need_ft = int(math.ceil((release_yd + margin_yd - end) * 3.0 / 3.0)) * 3
    first = next(i for i, n in enumerate(chain) if n[0] == 0x12)
    out = list(chain)
    node = out[first]
    if int(node[1][0]) == 0:
        feet = round(node[1][2] / FT) + need_ft
        out[first] = (0x12, [0, node[1][1], feet * FT, node[1][3]])
    else:
        out.insert(first, seg(0, need_ft))
    return out


# ---------------------------------------------------------------------------
# Play designs
# ---------------------------------------------------------------------------

#: Header kinds: how the game must classify a play (class nibble, quick / PA bits).
HEADER_KINDS = ("quick", "dropback", "pa", "pa_rollout", "rollout", "screen", "quick_screen",
                "run", "run_toss", "draw", "qb_sneak", "qb_draw", "reverse", "flea")


@dataclass
class PlayDesign:
    concept: str
    name: str
    play_type: str                 # pass | pa_pass | run | flea | sneak | keeper | reverse
    header: str                    # one of HEADER_KINDS
    chains: list
    primary: int | None = None     # first read or ball carrier slot
    reads: list = field(default_factory=list)
    tags: tuple = ()
    preference: int = 1            # play flag bits 9-11 (0 most preferred .. 4 least)
    notes: str = ""


class ConceptUnavailable(ValueError):
    """The formation cannot run this concept (missing receiver, no back, ...)."""


@dataclass
class PassPlan:
    routes: dict                   # label -> spec tuple
    reads: list                    # labels, primary first
    drop: str = "dropback"         # quick | quick3 | dropback | deep | pa | boot | rollout | screen | quick_screen
    protection: str = "dropback"
    header: str = "dropback"
    tags: tuple = ()
    boot_side: int = 0             # for boot/rollout: +1 strong, -1 weak (relative to ctx.strong)
    fake_to: str | None = None     # back label for play action


def _resolve(ctx: FormationContext, label: str) -> int | None:
    if label.isdigit():
        return int(label)
    return ctx.slot(label)


def _qb_chain(ctx: FormationContext, plan: PassPlan, reads: list[int]) -> Chain:
    drop = plan.drop
    head = [start(4), (0x03, [0])]
    side = plan.boot_side * ctx.strong
    if drop == "quick":
        return head + [move(0, -15), pass_node(reads)]
    if drop == "quick3":
        return head + [move(0, -9), pass_node(reads)]
    if drop == "dropback":
        return head + [move(0, -21), pass_node(reads)]
    if drop == "deep":
        return head + [move(0, -24), pass_node(reads)]
    if drop == "rollout":
        return head + [move(side * 21, -21, mode=1), pass_node(reads)]
    if drop in ("pa", "boot"):
        back = _resolve(ctx, plan.fake_to or "B")
        if back is None:
            raise ConceptUnavailable("play action needs a back to fake to")
        body = [(0x14, [back, 0])]
        if drop == "boot":
            body.append(move(side * 21, -21, mode=1))
        return head + body + [pass_node(reads)]
    if drop == "screen":
        return head + [move(0, -27), pass_node(reads[:1], mode=5)]
    if drop == "quick_screen":
        return head + [move(0, -15), pass_node(reads[:2], mode=2)]
    raise ValueError(drop)


def qb_release_yd(ctx: FormationContext, chain: Chain) -> float:
    """LOS-relative drop clamp (native 0x2F3D10): the QB never moves forward."""
    return min([ctx.qb.z] + [n[1][2] / YD for n in chain if n[0] == 0x04])


def _spec_chain(ctx: FormationContext, slot: int, spec: tuple, plan: PassPlan) -> Chain:
    what = spec[0]
    if what == "route":
        return route_chain(spec[1], spec[2] if len(spec) > 2 else None)
    if what == "check":
        return check_release_chain(ctx, slot, spec[1], spec[2] if len(spec) > 2 else 1.5)
    if what == "block":
        if ctx.player(slot).kind in (HB, FB):
            return back_block_chain(ctx, slot)
        return te_block_chain(ctx, slot)
    if what == "leak":
        # Retail PA-RO FB: block, then release across (0:9 4:30) after ``hold`` seconds.
        side = 1 if ctx.player(slot).x > 0 else -1
        hold = spec[2] if len(spec) > 2 else 1.5
        return [start(3), legf(4, -side * 3, 0, turn=2, end=1, group=1, rel=0, t=hold),
                *ROUTES[spec[1]].build(spec[3] if len(spec) > 3 else None)]
    if what == "fake":
        # Play-action back: fake take, then block or run a route.
        hole = spec[1]
        rest = spec[2] if len(spec) > 2 else ("block",)
        if rest[0] == "block":
            side = 1 if ctx.player(slot).x > 0.5 else -1
            tail = [legf(6, side * 3, -6, turn=2, end=1, group=1, rel=0)]
        else:
            tail = ROUTES[rest[1]].build(rest[2] if len(rest) > 2 else None)
        return [start(3), fake_take(hole), *tail]
    if what == "stalk":
        return stalk_chain()
    if what == "chain":
        return list(spec[1])
    raise ValueError(f"unknown route spec {spec!r}")


def _default_spec(ctx: FormationContext, label: str, player: Player) -> tuple:
    if player.kind in (HB, FB) and label in ("B", "B2"):
        return ("check", "Back Flat") if label == "B" else ("block",)
    number = int(label[1:]) if label[1:].isdigit() else 1
    return ("route", "Go" if number == 1 else "Seam")


_DEPTH_FAMILIES = ("intermediate", "deep", "double", "crosser")


def _apply_overrides(plan: PassPlan) -> PassPlan:
    ov = active_overrides()
    if not ov:
        return plan
    routes = dict(plan.routes)
    step = float(ov.get("depth_step", 0) or 0)
    if step:
        for label, spec in list(routes.items()):
            if spec and spec[0] == "route" and ROUTES[spec[1]].family in _DEPTH_FAMILIES:
                depth = spec[2] if len(spec) > 2 else ROUTES[spec[1]].default_depth
                routes[label] = ("route", spec[1], depth + step)
    for label, spec in (ov.get("routes") or {}).items():
        routes[str(label)] = tuple(spec) if spec else None
    reads = list(ov.get("reads") or plan.reads)
    return PassPlan(routes, reads, ov.get("drop", plan.drop), ov.get("protection", plan.protection),
                    plan.header, plan.tags, plan.boot_side, plan.fake_to)


def build_pass(ctx: FormationContext, concept: str, name: str, plan: PassPlan,
               play_type: str | None = None) -> PlayDesign:
    plan = _apply_overrides(plan)
    chains: list = [None] * 11
    assigned: dict[int, tuple] = {}
    for label, spec in plan.routes.items():
        slot = _resolve(ctx, label)
        if slot is None or spec is None:
            continue
        assigned[slot] = spec
    labels_by_slot = {v: k for k, v in ctx.labels.items() if k not in ("Y",)}
    for p in ctx.players:
        if p.kind in (WR, TE, HB, FB) and p.slot not in assigned:
            label = labels_by_slot.get(p.slot, "S1")
            assigned[p.slot] = _default_spec(ctx, label, p)
    for slot, spec in assigned.items():
        chains[slot] = _spec_chain(ctx, slot, spec, plan)
    for p in ctx.ol():
        chains[p.slot] = ol_chain(ctx, p.slot, plan.protection)
    reads: list[int] = []
    for label in plan.reads:
        slot = _resolve(ctx, label)
        if slot is not None and slot not in reads and any(n[0] == 0x12 for n in chains[slot]):
            reads.append(slot)
    if not reads:
        raise ConceptUnavailable(f"{concept}: no primary receiver in this formation")
    for slot in sorted(assigned, key=lambda s: (route_end_depth_yd(ctx, s, chains[s]) or -99)):
        if len(reads) >= 4:
            break
        if slot not in reads and any(n[0] == 0x12 and n[1][0] != 9 for n in chains[slot]):
            reads.append(slot)
    chains[ctx.qb.slot] = _qb_chain(ctx, plan, reads)
    release_yd = qb_release_yd(ctx, chains[ctx.qb.slot])
    for slot in assigned:
        chains[slot] = ensure_forward(ctx, slot, chains[slot], release_yd)
    kind = play_type or ("pa_pass" if plan.drop in ("pa", "boot") else "pass")
    return PlayDesign(concept, name, kind, plan.header, chains, reads[0], reads, plan.tags)


# ---------------------------------------------------------------------------
# Concept catalog
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConceptDef:
    name: str
    family: str                    # quick | dropback | pa | shot | screen | run | trick
    build: Callable[[FormationContext], PlayDesign]
    blurb: str
    situations: tuple = ()         # base | short | goal | long | red | two_minute | shot | gadget
    preference: int = 1


CONCEPTS: dict[str, ConceptDef] = {}


def concept(name: str, family: str, blurb: str, situations: tuple = (), preference: int = 1):
    def wrap(fn):
        CONCEPTS[name] = ConceptDef(name, family, fn, blurb, situations, preference)
        return fn
    return wrap


def _has(ctx: FormationContext, *labels: str) -> bool:
    return all(ctx.slot(label) is not None for label in labels)


def _need(ctx: FormationContext, *labels: str) -> None:
    if not _has(ctx, *labels):
        raise ConceptUnavailable("formation lacks " + ", ".join(l for l in labels if ctx.slot(l) is None))


def _back(ctx: FormationContext, default: tuple = ("check", "Back Flat")) -> dict:
    out = {}
    if ctx.slot("B") is not None:
        out["B"] = default
    if ctx.slot("B2") is not None:
        out["B2"] = ("block",)
    return out


def _pass(ctx, concept_name, plan, display=None, play_type=None):
    d = build_pass(ctx, concept_name, display or concept_name, plan, play_type)
    d.preference = CONCEPTS[concept_name].preference if concept_name in CONCEPTS else 1
    return d


# -- quick game (90 series: quick class word, 3-step or catch-and-throw) -----------------

@concept("Slant Flat", "quick", "slants outside, flats underneath: beat the corner or the flat defender",
         ("base", "short", "red"))
def _slant_flat(ctx):
    _need(ctx, "S1")
    r = {"S1": ("route", "Slant", 3), "S2": ("route", "Arrow"), "S3": ("route", "Seam", 12),
         "W1": ("route", "Slant", 3), "W2": ("route", "Arrow"), **_back(ctx, ("block",))}
    return _pass(ctx, "Slant Flat", PassPlan(r, ["S1", "S2", "W1", "W2"], "quick", "quick", "quick"))


@concept("Stick", "quick", "stick at six with a flat and a clear-out: the money third-and-short throw",
         ("short", "base", "red"))
def _stick(ctx):
    _need(ctx, "S1", "S2")
    if _has(ctx, "S3"):
        r = {"S1": ("route", "Go", 15), "S2": ("route", "Arrow"), "S3": ("route", "Stick", 6)}
        reads = ["S3", "S2", "W1", "B"]
    else:
        r = {"S1": ("route", "Go", 15), "S2": ("route", "Stick", 6)}
        reads = ["S2", "B", "W1"]
    r.update({"W1": ("route", "Slant", 3), "W2": ("route", "Stick", 6), **_back(ctx)})
    return _pass(ctx, "Stick", PassPlan(r, reads, "quick", "quick", "quick"))


@concept("Snag", "quick", "snag sits in the window under a corner with a flat: triangle read",
         ("base", "short", "red"))
def _snag(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Snag", 4), "S2": ("route", "Flag", 6),
         "S3": ("route", "Arrow"), "W1": ("route", "Slant", 3), "W2": ("route", "Hitch", 6), **_back(ctx)}
    if not _has(ctx, "S3") and ctx.slot("B") is not None:
        r["B"] = ("check", "Back Flat", 0.6)
    return _pass(ctx, "Snag", PassPlan(r, ["S1", "S2", "S3", "B", "W1"], "quick", "quick", "quick"))


@concept("Spacing", "quick", "five underneath routes stretched across the field (hitches, sits and a flat)",
         ("base", "short", "two_minute"))
def _spacing(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Hitch", 6), "S2": ("route", "Stick", 5), "S3": ("route", "Flat"),
         "W1": ("route", "Hitch", 6), "W2": ("route", "Stick", 5), **_back(ctx)}
    return _pass(ctx, "Spacing", PassPlan(r, ["S2", "S3", "S1", "W1", "W2"], "quick", "quick", "quick"))


@concept("Hitch Seam", "quick", "hitches outside, seams inside: beats three-deep and two-high",
         ("base", "two_minute"))
def _hitch_seam(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Hitch", 6), "S2": ("route", "Seam", 15), "S3": ("route", "Flat"),
         "W1": ("route", "Hitch", 6), "W2": ("route", "Seam", 15), **_back(ctx, ("block",))}
    return _pass(ctx, "Hitch Seam", PassPlan(r, ["S1", "W1", "S2", "W2"], "quick", "quick", "quick"))


@concept("Quick Outs", "quick", "five-yard outs by the outside receivers, sticks inside: a sideline clock play",
         ("two_minute", "base"))
def _quick_outs(ctx):
    _need(ctx, "S1", "W1")
    r = {"S1": ("route", "Quick Out", 5), "W1": ("route", "Quick Out", 5), "S2": ("route", "Stick", 6),
         "W2": ("route", "Stick", 6), "S3": ("route", "Seam", 15), **_back(ctx, ("block",))}
    return _pass(ctx, "Quick Outs", PassPlan(r, ["S1", "W1", "S2", "W2"], "quick", "quick", "quick"))


@concept("Double Slants", "quick", "slants by #1 and #2 on the same side: a natural rub",
         ("short", "red", "base"))
def _double_slants(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Slant", 3), "S2": ("route", "Slant", 2), "S3": ("route", "Arrow"),
         "W1": ("route", "Hitch", 6), "W2": ("route", "Arrow"), **_back(ctx, ("block",))}
    if _has(ctx, "S3") and ctx.player(ctx.slot("S3")).kind == TE:
        # b77 p6s: an attached #3 tight end blocks; his arrow ran into the #2 slant (native trace, 0.7 yd)
        r["S3"] = ("block",)
    return _pass(ctx, "Double Slants", PassPlan(r, ["S2", "S1", "S3", "W1"], "quick", "quick", "quick"))


@concept("Fade Out", "quick", "red zone: fade by #1, quick out underneath, flat from the back",
         ("red", "goal"))
def _fade_out(ctx):
    _need(ctx, "S1")
    r = {"S1": ("route", "Fade", 12), "S2": ("route", "Quick Out", 4), "S3": ("route", "Flat"),
         "W1": ("route", "Fade", 12), "W2": ("route", "Slant", 2), **_back(ctx)}
    return _pass(ctx, "Fade Out", PassPlan(r, ["S1", "S2", "W1", "B"], "quick", "quick", "quick"))


# -- dropback (50 series: dropback class word, 5-step / gun rhythm) -----------------------

@concept("Mesh", "dropback", "two shallow crossers rub at the mesh point, corners over the top",
         ("base", "long", "two_minute"))
def _mesh(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Corner", 10)}
    if _has(ctx, "W2"):
        r.update({"S2": ("route", "Drag", 2), "W2": ("route", "Shallow", 5), "W1": ("route", "Corner", 10)})
        reads = ["S2", "W2", "S1", "B"]
    else:
        r.update({"S2": ("route", "Drag", 2), "W1": ("route", "Shallow", 5), "S3": ("route", "Seam", 14)})
        reads = ["S2", "W1", "S3", "B"]
    if ctx.slot("S3") is not None and "S3" not in r:
        r["S3"] = ("route", "Seam", 14)
    r.update(_back(ctx, ("check", "Swing")))
    if ctx.slot("B2") is not None:
        # b77 p6s: with two backs the swing ran into the drag (native trace, 0.73 yd): both backs protect
        r["B"] = ("block",)
    return _pass(ctx, "Mesh", PassPlan(r, reads, "dropback", "dropback", "dropback"))


@concept("Shallow Cross", "dropback", "shallow cross under a dig: high-low the linebackers",
         ("base", "long"))
def _shallow(ctx):
    _need(ctx, "S1", "S2", "W1")
    r = {"S1": ("route", "Go", 15), "S2": ("route", "Drag", 2), "W1": ("route", "Dig", 12),
         "W2": ("route", "Seam", 15), "S3": ("route", "Seam", 14), **_back(ctx)}
    return _pass(ctx, "Shallow Cross", PassPlan(r, ["S2", "W1", "B", "S1"], "dropback", "dropback", "dropback"))


@concept("Drive", "dropback", "drive: shallow by #2 with a dig behind it from #3 or the backside",
         ("base", "long"))
def _drive(ctx):
    _need(ctx, "S1", "S2")
    if _has(ctx, "S3"):
        r = {"S1": ("route", "Go", 15), "S2": ("route", "Dig", 12), "S3": ("route", "Drag", 2)}
        reads = ["S3", "S2", "B", "W1"]
    else:
        r = {"S1": ("route", "Go", 15), "S2": ("route", "Drag", 2), "W2": ("route", "Dig", 12)}
        reads = ["S2", "W2", "B", "W1"]
    r.setdefault("W1", ("route", "Comeback", 13))
    r.update(_back(ctx))
    return _pass(ctx, "Drive", PassPlan(r, reads, "dropback", "dropback", "dropback"))


@concept("Smash", "dropback", "hitch by #1, corner by #2: high-low the cornerback",
         ("base", "red", "long"))
def _smash(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Hitch", 5), "S2": ("route", "Corner", 10), "S3": ("route", "Flat"),
         "W1": ("route", "Hitch", 5), "W2": ("route", "Corner", 10), **_back(ctx)}
    if not _has(ctx, "W2"):
        r["W1"] = ("route", "Dig", 12)
    return _pass(ctx, "Smash", PassPlan(r, ["S2", "S1", "W2", "W1"], "dropback", "dropback", "dropback"))


@concept("Flood", "dropback", "three levels to one side: clear-out, sail at twelve, flat underneath",
         ("base", "long"))
def _flood(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Go", 15), "S2": ("route", "Sail", 10)}
    if _has(ctx, "S3"):
        r["S3"] = ("route", "Flat")
        reads = ["S2", "S3", "W1", "B"]
        r.update(_back(ctx))
    else:
        reads = ["S2", "B", "W1"]
        r.update(_back(ctx, ("check", "Back Flat", 0.6)))
    r.update({"W1": ("route", "Dig", 12), "W2": ("route", "Seam", 15)})
    return _pass(ctx, "Flood", PassPlan(r, reads, "dropback", "dropback", "dropback"))


@concept("Levels", "dropback", "two in-breakers at different depths from one side, seam clears",
         ("base", "long"))
def _levels(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Dig", 12), "S2": ("route", "In", 5), "S3": ("route", "Seam", 15),
         "W1": ("route", "Comeback", 13), "W2": ("route", "Seam", 15), **_back(ctx)}
    return _pass(ctx, "Levels", PassPlan(r, ["S2", "S1", "W1", "B"], "dropback", "dropback", "dropback"))


@concept("Y Cross", "dropback", "tight end deep cross under a post, comeback outside: Air Coryell staple",
         ("base", "long"))
def _y_cross(ctx):
    y = ctx.slot("Y")
    if y is None:
        y = ctx.slot("S3") or ctx.slot("S2")
    if y is None:
        raise ConceptUnavailable("no inside receiver for the cross")
    r = {"S1": ("route", "Post", 12), "W1": ("route", "Go", 15), str(y): ("route", "Over", 9),
         **_back(ctx)}
    for lab in ("S2", "S3", "W2"):
        if ctx.slot(lab) is not None and ctx.slot(lab) != y:
            r[lab] = ("route", "Flat") if lab != "W2" else ("route", "Curl", 10)
            break
    return _pass(ctx, "Y Cross", PassPlan(r, [str(y), "W1", "S2", "B"], "dropback", "dropback", "dropback"))


@concept("Dagger", "dropback", "seam clears the safety, dig comes in behind it",
         ("base", "long"))
def _dagger(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Dig", 15), "S2": ("route", "Seam", 15), "S3": ("route", "Flat"),
         "W1": ("route", "Curl", 10), "W2": ("route", "Hitch", 6), **_back(ctx)}
    return _pass(ctx, "Dagger", PassPlan(r, ["S1", "S2", "W1", "B"], "dropback", "dropback", "dropback"))


@concept("Curl Flat", "dropback", "curl at twelve with the flat underneath: the cover-two beater",
         ("base", "long"))
def _curl_flat(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Curl", 11), "S2": ("route", "Flat"), "S3": ("route", "Seam", 15),
         "W1": ("route", "Curl", 11), "W2": ("route", "Flat"), **_back(ctx, ("block",))}
    return _pass(ctx, "Curl Flat", PassPlan(r, ["S1", "S2", "W1", "W2"], "dropback", "dropback", "dropback"))


@concept("Four Verticals", "dropback", "everyone vertical: stretch the deep zones, check down underneath",
         ("long", "two_minute", "shot"))
def _four_verts(ctx):
    _need(ctx, "S1", "W1")
    r = {"S1": ("route", "Go", 15), "S2": ("route", "Seam", 15), "S3": ("route", "Seam", 15),
         "W1": ("route", "Go", 15), "W2": ("route", "Seam", 15), **_back(ctx, ("check", "Swing"))}
    return _pass(ctx, "Four Verticals", PassPlan(r, ["S2", "W2", "S1", "W1"], "deep", "dropback", "dropback"))


@concept("Mills", "dropback", "post over a dig from the same side: the post-dig shot",
         ("long", "base", "shot"))
def _mills(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Dig", 13), "S2": ("route", "Post", 12), "S3": ("route", "Flat"),
         "W1": ("route", "Comeback", 13), "W2": ("route", "Hitch", 6), **_back(ctx)}
    return _pass(ctx, "Mills", PassPlan(r, ["S2", "S1", "W1", "B"], "deep", "dropback", "dropback"))


@concept("Double Post", "dropback", "skinny post under a deep post: split the safeties",
         ("long", "shot"))
def _double_post(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Post", 14), "S2": ("route", "Skinny Post", 9), "S3": ("route", "Flat"),
         "W1": ("route", "Dig", 12), "W2": ("route", "Hitch", 6), **_back(ctx)}
    return _pass(ctx, "Double Post", PassPlan(r, ["S2", "S1", "W1", "B"], "deep", "dropback", "dropback"))


@concept("Hank", "dropback", "curls outside, hooks inside, back to the flat: a zone sit-down concept",
         ("base", "long"))
def _hank(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Curl", 10), "S2": ("route", "Hook", 8), "S3": ("route", "Flat"),
         "W1": ("route", "Curl", 10), "W2": ("route", "Hook", 8), **_back(ctx)}
    return _pass(ctx, "Hank", PassPlan(r, ["S2", "S1", "W2", "B"], "dropback", "dropback", "dropback"))


@concept("Bench", "dropback", "deep out by #1 over an arrow by #2: a two-level sideline stretch",
         ("long", "two_minute"))
def _bench(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Out", 12), "S2": ("route", "Arrow"), "S3": ("route", "Seam", 15),
         "W1": ("route", "Dig", 12), "W2": ("route", "Seam", 15), **_back(ctx)}
    return _pass(ctx, "Bench", PassPlan(r, ["S1", "S2", "W1", "B"], "dropback", "dropback", "dropback"))


@concept("Texas", "dropback", "back angle route against the linebacker, clear-outs above",
         ("base", "short"))
def _texas(ctx):
    _need(ctx, "S1", "B")
    r = {"B": ("route", "Angle"), "S1": ("route", "Go", 15), "S2": ("route", "Seam", 14),
         "S3": ("route", "Hook", 8), "W1": ("route", "Curl", 10), "W2": ("route", "Seam", 14)}
    if ctx.slot("B2") is not None:
        r["B2"] = ("block",)
    return _pass(ctx, "Texas", PassPlan(r, ["B", "S2", "W1", "S1"], "dropback", "dropback", "dropback"))


@concept("Sail", "dropback", "corner-flatten sail by #2 under a go, back to the flat",
         ("base", "long"))
def _sail(ctx):
    _need(ctx, "S1", "S2")
    r = {"S1": ("route", "Go", 15), "S2": ("route", "Sail", 12), "S3": ("route", "Whip", 4),
         "W1": ("route", "Post", 12), "W2": ("route", "In", 6), **_back(ctx)}
    return _pass(ctx, "Sail", PassPlan(r, ["S2", "S3", "B", "W1"], "dropback", "dropback", "dropback"))


@concept("Whip Seam", "quick", "whip by the inside receiver, seam above, slants away",
         ("short", "base"))
def _whip(ctx):
    inside = ctx.slot("S3") or ctx.slot("S2")
    if inside is None:
        raise ConceptUnavailable("no inside receiver")
    r = {str(inside): ("route", "Whip", 4), "S1": ("route", "Go", 15), "W1": ("route", "Slant", 3),
         "W2": ("route", "Arrow"), **_back(ctx)}
    if ctx.slot("S3") is not None:
        r["S2"] = ("route", "Seam", 15)
    return _pass(ctx, "Whip Seam", PassPlan(r, [str(inside), "W1", "S2", "B"], "quick", "quick", "quick"))


# -- play action and shots (PA class word, PA bit) -----------------------------------------

def _fake_hole(ctx: FormationContext, label: str = "B") -> int:
    return hole_toward(ctx.run_strong, 0.8)


@concept("PA Boot", "pa", "run fake one way, QB boots the other: drag to the flat, deep over, clear-out",
         ("base", "short", "red"))
def _pa_boot(ctx):
    _need(ctx, "B", "S1", "W1")
    y = ctx.slot("Y")
    drag = y if y is not None else ctx.slot("S2")
    r = {"B": ("fake", _fake_hole(ctx)), "S1": ("route", "Over", 9), "W1": ("route", "Corner", 12)}
    if drag is not None:
        r[str(drag)] = ("route", "Drag", 3)
    for lab in ("S2", "S3"):
        if ctx.slot(lab) is not None and ctx.slot(lab) != drag:
            r[lab] = ("route", "Seam", 14)
    if ctx.slot("W2") is not None and ctx.slot("W2") != drag:
        r["W2"] = ("route", "Flat")
    if ctx.slot("B2") is not None:
        r["B2"] = ("leak", "Shallow", 1.0, 1)
    reads = [str(drag) if drag is not None else "W2", "S1", "W1", "B2"]
    plan = PassPlan(r, reads, "boot", "pa", "pa_rollout", fake_to="B", boot_side=-1)
    return _pass(ctx, "PA Boot", plan)


@concept("PA Boot Leak", "pa", "boot with the tight end leaking back across behind the defense",
         ("short", "red", "goal"))
def _pa_leak(ctx):
    _need(ctx, "B", "S1")
    y = ctx.slot("Y")
    if y is None:
        raise ConceptUnavailable("leak needs a tight end")
    # QB boots weak (away from the run fake); the leak and the over come back to him
    r = {"B": ("fake", _fake_hole(ctx)), "S1": ("route", "Over", 9),
         str(y): ("leak", "Drag", 1.2, 2), "W1": ("route", "Corner", 12)}
    for lab in ("S2", "S3"):
        if ctx.slot(lab) is not None and ctx.slot(lab) != y:
            r[lab] = ("route", "Seam", 14)
    if ctx.slot("W2") is not None and ctx.slot("W2") != y:
        r["W2"] = ("route", "Flat")
    if ctx.slot("B2") is not None:
        r["B2"] = ("block",)
    plan = PassPlan(r, [str(y), "S1", "W1", "W2"], "boot", "pa", "pa_rollout", fake_to="B", boot_side=-1)
    return _pass(ctx, "PA Boot Leak", plan)


@concept("Yankee", "shot", "max-protect play action: deep crosser and a post off a hard run fake",
         ("shot", "base"))
def _yankee(ctx):
    _need(ctx, "B", "S1", "W1")
    r = {"B": ("fake", _fake_hole(ctx)), "S1": ("route", "Deep Cross", 12), "W1": ("route", "Post", 12)}
    for lab in ("S2", "S3", "W2"):
        if ctx.slot(lab) is not None:
            r[lab] = ("block",) if ctx.player(ctx.slot(lab)).kind in (TE, FB, HB) else ("route", "Curl", 10)
    if ctx.slot("B2") is not None:
        r["B2"] = ("block",)
    plan = PassPlan(r, ["S1", "W1"], "pa", "pa", "pa", ("shot",), fake_to="B")
    return _pass(ctx, "Yankee", plan)


@concept("PA Crossers", "pa", "play action with crossers at two depths and a clear-out",
         ("base",))
def _pa_crossers(ctx):
    _need(ctx, "B", "S1", "S2")
    r = {"B": ("fake", _fake_hole(ctx)), "S1": ("route", "Go", 15), "S2": ("route", "Deep Cross", 12),
         "W1": ("route", "Dig", 10), "W2": ("route", "Drag", 3), "S3": ("route", "Flat")}
    if ctx.slot("B2") is not None:
        r["B2"] = ("block",)
    return _pass(ctx, "PA Crossers", PassPlan(r, ["S2", "W1", "W2"], "pa", "pa", "pa", fake_to="B"))


@concept("PA Shot", "shot", "play-action double move: sluggo outside, seam inside",
         ("shot",))
def _pa_shot(ctx):
    _need(ctx, "B", "S1", "W1")
    r = {"B": ("fake", _fake_hole(ctx)), "S1": ("route", "Slant and Go", 1), "W1": ("route", "Post Corner", 8),
         "S2": ("route", "Seam", 15), "W2": ("route", "Curl", 10)}
    if ctx.slot("B2") is not None:
        r["B2"] = ("block",)
    plan = PassPlan(r, ["S1", "S2", "W1"], "pa", "pa", "pa", ("shot",), fake_to="B")
    return _pass(ctx, "PA Shot", plan)


@concept("PA Dagger", "pa", "play-action dagger: seam clears, dig behind off the run fake",
         ("base", "shot"))
def _pa_dagger(ctx):
    _need(ctx, "B", "S1", "S2")
    r = {"B": ("fake", _fake_hole(ctx)), "S1": ("route", "Dig", 15), "S2": ("route", "Seam", 15),
         "W1": ("route", "Post", 12), "W2": ("route", "Flat"), "S3": ("route", "Flat")}
    if ctx.slot("B2") is not None:
        r["B2"] = ("leak", "Shallow", 1.0, 1)
    return _pass(ctx, "PA Dagger", PassPlan(r, ["S1", "S2", "W1"], "pa", "pa", "pa", fake_to="B"))


@concept("Out and Up", "shot", "sell the quick out, then take the top off",
         ("shot", "two_minute"))
def _out_up(ctx):
    _need(ctx, "S1", "W1")
    r = {"S1": ("route", "Out and Up", 7), "W1": ("route", "Stop and Go", 10), "S2": ("route", "Hitch", 6),
         "W2": ("route", "Stick", 6), "S3": ("route", "Flat"), **_back(ctx, ("block",))}
    return _pass(ctx, "Out and Up", PassPlan(r, ["S1", "W1", "S2"], "deep", "max", "dropback", ("shot",)))


@concept("Post Corner", "shot", "post-corner by #1 with a dig underneath",
         ("shot", "red"))
def _post_corner(ctx):
    _need(ctx, "S1")
    r = {"S1": ("route", "Post Corner", 8), "S2": ("route", "Dig", 10), "S3": ("route", "Flat"),
         "W1": ("route", "Corner Post", 10), "W2": ("route", "Hitch", 6), **_back(ctx, ("block",))}
    return _pass(ctx, "Post Corner", PassPlan(r, ["S1", "W1", "S2"], "deep", "max", "dropback", ("shot",)))


# -- b77 p6s (GOAL P4): more modern concepts, every one built from retail-encoded routes --------
# Each was checked with the p13 linter and the native route initializer (0x229AE0) trace from every
# formation that offers it (no receivers colliding at the same moment, no stacked landmarks).

@concept("Scissors", "dropback", "post by #1 over a corner by #2: the two routes cross and split the deep defender",
         ("long", "shot", "base"))
def _scissors(ctx):
    _need(ctx, "S1", "S2")
    a, b = ctx.player(ctx.slot("S1")), ctx.player(ctx.slot("S2"))
    if a.kind != WR or abs(a.x - b.x) < 5.0:
        raise ConceptUnavailable("scissors needs a split #1 receiver (bunch and heavy sets cross too tight)")
    r = {"S1": ("route", "Post", 14), "S2": ("route", "Corner", 6), "S3": ("route", "Flat"),
         "W1": ("route", "Dig", 12), "W2": ("route", "Hitch", 6), **_back(ctx)}
    return _pass(ctx, "Scissors", PassPlan(r, ["S2", "S1", "W1", "B"], "deep", "dropback", "dropback"))


@concept("Post Wheel", "pa", "play action: #1 post clears, the slot wheels up the sideline under it, dig backside",
         ("shot", "base"))
def _post_wheel(ctx):
    _need(ctx, "B", "S1", "S2")
    r = {"B": ("fake", _fake_hole(ctx)), "S1": ("route", "Post", 12), "S2": ("route", "Wheel", 2),
         "W1": ("route", "Dig", 12), "W2": ("route", "Drag", 3), "S3": ("route", "Seam", 14)}
    if ctx.slot("B2") is not None:
        r["B2"] = ("block",)
    return _pass(ctx, "Post Wheel", PassPlan(r, ["S2", "S1", "W1", "W2"], "pa", "pa", "pa", ("shot",), fake_to="B"))


@concept("Comebacks", "dropback", "comebacks outside at fifteen, seams inside: the sideline timing throw",
         ("long", "two_minute", "base"))
def _comebacks(ctx):
    _need(ctx, "S1", "W1")
    r = {"S1": ("route", "Comeback", 14), "W1": ("route", "Comeback", 14), "S2": ("route", "Seam", 15),
         "W2": ("route", "Seam", 15), "S3": ("route", "Flat"), **_back(ctx)}
    return _pass(ctx, "Comebacks", PassPlan(r, ["S1", "W1", "S2", "B"], "deep", "dropback", "dropback"))


@concept("Stick Nod", "shot", "stick-and-go by the inside receiver off the stick look, flat and clear-out",
         ("shot", "two_minute"))
def _stick_nod(ctx):
    _need(ctx, "S1", "S2")
    inside = "S3" if _has(ctx, "S3") else "S2"
    r = {"S1": ("route", "Go", 15), inside: ("route", "Hitch and Go", 5),
         "W1": ("route", "Slant", 3), "W2": ("route", "Stick", 6), **_back(ctx)}
    if inside == "S3":
        r["S2"] = ("route", "Arrow")
    return _pass(ctx, "Stick Nod", PassPlan(r, [inside, "S1", "W1", "B"], "deep", "dropback", "dropback", ("shot",)))


@concept("Y Pivot", "quick", "tight end pivot (in, then back out) under a clear-out, flat and slants",
         ("short", "base", "red"))
def _y_pivot(ctx):
    y = ctx.slot("Y")
    if y is None:
        raise ConceptUnavailable("pivot needs an attached tight end")
    r = {str(y): ("route", "Pivot", 3), "S1": ("route", "Go", 15), "W1": ("route", "Slant", 3),
         "W2": ("route", "Hitch", 6), **_back(ctx)}
    for lab in ("S2", "S3"):
        if ctx.slot(lab) is not None and ctx.slot(lab) != y:
            # trips: the slot climbs the seam instead, so his arrow does not land on the pivot (native trace)
            r[lab] = ("route", "Seam", 12) if _has(ctx, "S3") else ("route", "Arrow")
            break
    return _pass(ctx, "Y Pivot", PassPlan(r, [str(y), "B", "W1", "S1"], "quick", "quick", "quick"))


@concept("Slot Fade", "quick", "red zone: the slot fades over a quick out by #1, slant backside",
         ("red", "goal"))
def _slot_fade(ctx):
    _need(ctx, "S1", "S2")
    if ctx.player(ctx.slot("S2")).kind != WR:
        raise ConceptUnavailable("slot fade needs a slot receiver")
    r = {"S2": ("route", "Fade", 10), "S1": ("route", "Quick Out", 5), "S3": ("route", "Flat"),
         "W1": ("route", "Slant", 3), "W2": ("route", "Stick", 5), **_back(ctx)}
    return _pass(ctx, "Slot Fade", PassPlan(r, ["S2", "S1", "W1", "B"], "quick", "quick", "quick"))


@concept("Mesh Wheel", "dropback", "mesh crossers with the back wheeling out of the backfield behind them",
         ("long", "two_minute"))
def _mesh_wheel(ctx):
    _need(ctx, "S1", "S2", "B")
    r = {"S1": ("route", "Corner", 10), "S2": ("route", "Drag", 2)}
    if _has(ctx, "W2"):
        r.update({"W2": ("route", "Shallow", 5), "W1": ("route", "Go", 15)})
        reads = ["S2", "W2", "B", "S1"]
    else:
        r.update({"W1": ("route", "Shallow", 5)})
        reads = ["S2", "W1", "B", "S1"]
    if ctx.slot("S3") is not None:
        r["S3"] = ("route", "Seam", 14)
    r["B"] = ("check", "Back Wheel", 0.6)
    if ctx.slot("B2") is not None:
        r["B2"] = ("block",)
    return _pass(ctx, "Mesh Wheel", PassPlan(r, reads, "dropback", "dropback", "dropback"))


# -- screens -------------------------------------------------------------------------------

_SCREEN_RELEASE_FT = {T: 42, C: 30, G: 36}    # retail 50 H Screen: 14 / 10 / 12 yards


def _screen_side(ctx: FormationContext, slot: int) -> int:
    p = ctx.player(slot)
    return (1 if p.x > 0 else -1) if abs(p.x) > 0.5 else ctx.strong


def _screen_line(ctx: FormationContext, side: int, hold: float = 0.5) -> dict[int, Chain]:
    """Retail back-screen line: the centre, guard and tackle on the screen side release."""
    out: dict[int, Chain] = {}
    for p in ctx.ol():
        playside = p.kind == C or (p.x > 0) == (side > 0)
        turn = 1 if side < 0 else 0
        head = [start(2), (0x02, [ctx.qb.slot])] if p.kind == C else [start(3)]
        if playside:
            out[p.slot] = head + [legf(1, side * 1, -3, turn=turn, end=2, t=hold),
                                  release(side * _SCREEN_RELEASE_FT[p.kind], -6),
                                  legf(3, 0, 6, turn=turn)]
        else:
            out[p.slot] = head + [legf(1, side * (2 if p.kind == T else 3), -9 if p.kind == T else -6,
                                       turn=turn, end=1)]
    return out


@concept("RB Screen", "screen", "line sells pass, three linemen release, the back slips out behind them",
         ("long", "base"), preference=2)
def _rb_screen(ctx):
    _need(ctx, "B")
    b = ctx.slot("B")
    side = _screen_side(ctx, b)
    out = [None] * 11
    for slot, ch in _screen_line(ctx, side).items():
        out[slot] = ch
    out[b] = [start(3), seg(9, side * 33)]
    clear = {"S1": "Go", "S2": "Post", "S3": "Seam", "W1": "Go", "W2": "Seam"}
    for lab, name in clear.items():
        s = ctx.slot(lab)
        if s is not None:
            out[s] = route_chain(name, 15 if name in ("Go", "Seam") else 10)
    if ctx.slot("B2") is not None:
        out[ctx.slot("B2")] = back_block_chain(ctx, ctx.slot("B2"))
    out[ctx.qb.slot] = [start(4), (0x03, [0]), move(0, -27), pass_node([b], mode=5)]
    d = PlayDesign("RB Screen", "RB Screen", "pass", "screen", out, b, [b], ("screen",), 2)
    return d


@concept("WR Slip Screen", "screen", "retail slip screen: the split end comes flat along the line, quick throw",
         ("long", "base"), preference=2)
def _wr_slip(ctx):
    target = None
    for lab in ("W1", "S1"):
        s = ctx.slot(lab)
        if s is not None and ctx.player(s).on_los and ctx.player(s).kind == WR:
            target = s
            break
    if target is None:
        raise ConceptUnavailable("slip screen needs a receiver on the line")
    out = [None] * 11
    for p in ctx.ol():
        out[p.slot] = ol_chain(ctx, p.slot, "quick")
    out[target] = [start(3), seg(4, 75)]
    for lab, name, depth in (("S1", "Go", 15), ("S2", "Post", 10), ("S3", "Seam", 15),
                             ("W1", "Go", 15), ("W2", "Seam", 15)):
        s = ctx.slot(lab)
        if s is not None and s != target:
            out[s] = route_chain(name, depth)
    for lab in ("B", "B2"):
        s = ctx.slot(lab)
        if s is not None:
            out[s] = back_block_chain(ctx, s)
    out[ctx.qb.slot] = [start(4), (0x03, [0]), move(0, -15), pass_node([target], mode=2)]
    return PlayDesign("WR Slip Screen", "WR Slip Screen", "pass", "quick_screen", out, target, [target],
                      ("screen",), 2)


@concept("Bubble Screen", "screen", "slot bubbles to the flat behind the outside receiver's block, quick throw",
         ("long", "base", "two_minute"), preference=2)
def _bubble(ctx):
    target = None
    for lab in ("S2", "S3", "W2"):
        s = ctx.slot(lab)
        if s is not None and not ctx.player(s).on_los and ctx.player(s).kind in (WR, TE):
            target = s
            outside = ctx.slot(lab[0] + "1")
            break
    if target is None:
        raise ConceptUnavailable("bubble needs an off-line slot")
    out = [None] * 11
    for p in ctx.ol():
        out[p.slot] = ol_chain(ctx, p.slot, "quick")
    out[target] = route_chain("Flat")
    if outside is not None and outside != target:
        out[outside] = stalk_chain()
    for lab, name, depth in (("S1", "Go", 15), ("S2", "Seam", 15), ("S3", "Seam", 15),
                             ("W1", "Slant", 3), ("W2", "Arrow", 0)):
        s = ctx.slot(lab)
        if s is not None and out[s] is None:
            out[s] = route_chain(name, depth)
    for lab in ("B", "B2"):
        s = ctx.slot(lab)
        if s is not None:
            out[s] = back_block_chain(ctx, s)
    out[ctx.qb.slot] = [start(4), (0x03, [0]), move(0, -15), pass_node([target], mode=2)]
    return PlayDesign("Bubble Screen", "Bubble Screen", "pass", "quick_screen", out, target, [target],
                      ("screen",), 2)


@concept("TE Screen", "screen", "tight end blocks, then slips to the flat behind three releasing linemen",
         ("long", "base"), preference=3)
def _te_screen(ctx):
    y = ctx.slot("Y")
    if y is None or not ctx.player(y).on_los:
        raise ConceptUnavailable("TE screen needs an attached tight end")
    side = 1 if ctx.player(y).x > 0 else -1
    out = [None] * 11
    for slot, ch in _screen_line(ctx, side, hold=0.8).items():
        out[slot] = ch
    out[y] = [start(3), legf(1, 0, -3, turn=0 if side < 0 else 1, end=2, t=1.0), seg(9, side * 33)]
    for lab, name, depth in (("S1", "Go", 15), ("S2", "Post", 10), ("S3", "Seam", 15),
                             ("W1", "Go", 15), ("W2", "Seam", 15)):
        s = ctx.slot(lab)
        if s is not None and out[s] is None:
            out[s] = route_chain(name, depth)
    for lab in ("B", "B2"):
        s = ctx.slot(lab)
        if s is not None:
            out[s] = back_block_chain(ctx, s)
    out[ctx.qb.slot] = [start(4), (0x03, [0]), move(0, -27), pass_node([y], mode=5)]
    return PlayDesign("TE Screen", "TE Screen", "pass", "screen", out, y, [y], ("screen",), 3)


# -- runs ----------------------------------------------------------------------------------

def _run_receivers(ctx: FormationContext, out: list, d: int, *, te_drive: bool = True) -> None:
    for p in ctx.players:
        if out[p.slot] is not None or p.kind not in (WR, TE, HB, FB):
            continue
        if p.kind == TE and p.on_los and abs(p.x) < 8 and te_drive:
            out[p.slot] = [start(3), legf(0, d * 2, 3, turn=0 if d > 0 else 1)]
        elif p.kind in (HB, FB):
            out[p.slot] = [start(3), legf(4, d * 6, 3, turn=2, group=1, rel=0)]
        else:
            out[p.slot] = stalk_chain()


def _qb_give(ctx: FormationContext, carrier: int, kind: int, draw: bool = False) -> Chain:
    body = [move(0, -15)] if draw else []
    return [start(4), (0x03, [0]), *body, (0x13, [carrier, kind])]


def _run_ol(ctx: FormationContext, scheme: str, d: int, puller: int | None = None) -> dict[int, Chain]:
    out = {}
    for p in ctx.ol():
        head = [start(2), (0x02, [ctx.qb.slot])] if p.kind == C else [start(3)]
        if p.slot == puller:
            dist = 18 if scheme == "power" else (13 if scheme == "counter" else 6)
            out[p.slot] = head + [legf(2, d * dist, 3, turn=2, group=1, rel=0)]
        elif scheme == "zone":
            out[p.slot] = head + [legf(8, d * 3, 3, turn=0 if d > 0 else 1, group=2)]
        elif scheme == "reach":
            out[p.slot] = head + [legf(0, d * 3, 3, turn=0 if d > 0 else 1)]
        elif scheme == "draw":
            set_ = legf(1, 0, -3 if p.kind == T else 0, turn=0 if p.x < 0 else 1, end=1, t=1.3 if p.kind == T else 0.1)
            out[p.slot] = head + [set_, legf(0, 0, 6 if p.kind == T else 3, turn=0 if p.x < 0 else 1)]
        else:  # drive / duo / power / counter / trap base blocks
            out[p.slot] = head + [legf(0, 0, 3, turn=2)]
    return out


def _carrier(ctx: FormationContext) -> int:
    b = ctx.slot("B")
    if b is None:
        raise ConceptUnavailable("run needs a back")
    return b


def _backside_guard(ctx: FormationContext, d: int) -> int:
    return next(p.slot for p in ctx.ol() if p.kind == G and (p.x > 0) != (d > 0))


def _run(ctx, concept_name, display, scheme, d, hole_yd, path_spec, *, handoff=0, take_a=0, take_t=0.0,
         puller=False, lead=False, header="run", tags=()):
    b = _carrier(ctx)
    if active_overrides().get("direction") == "weak":
        d = -d
    out = [None] * 11
    pull = _backside_guard(ctx, d) if puller else None
    for slot, ch in _run_ol(ctx, scheme, d, pull).items():
        out[slot] = ch
    fb = ctx.slot("B2")
    if lead and fb is not None:
        out[fb] = [start(3), legf(4, d * 7, 0, turn=2, group=1, rel=0)]
    hole = hole_toward(d, hole_yd)
    mode, dx, dy = path_spec
    follow = 0
    if mode == 2:
        follow = pull if pull is not None else (fb if fb is not None else 0)
        if not follow:
            mode, dx, dy = 1, 0, 9
    out[b] = [start(3), take(hole, take_a, take_t), path(mode, d * dx, dy, a=2, follow=follow, c=1 if mode == 2 else 0)]
    _run_receivers(ctx, out, d)
    out[ctx.qb.slot] = _qb_give(ctx, b, handoff, draw=scheme == "draw")
    return PlayDesign(concept_name, display, "run", header, out, b, [], tags,
                      CONCEPTS[concept_name].preference if concept_name in CONCEPTS else 1)


@concept("Inside Zone", "run", "zone steps, the back presses the guard and cuts", ("base", "short", "goal"))
def _iz(ctx):
    return _run(ctx, "Inside Zone", "Inside Zone", "zone", ctx.run_strong, 0.8, (1, 0, 9))


@concept("Inside Zone Weak", "run", "inside zone to the weak side", ("base", "short"))
def _iz_weak(ctx):
    return _run(ctx, "Inside Zone Weak", "Inside Zone Weak", "zone", -ctx.run_strong, 0.8, (1, 0, 9))


@concept("Outside Zone", "run", "everyone reaches, the back stretches to the edge", ("base",))
def _oz(ctx):
    # retail Strong Outside Zone: hole 5.8 yd wide, absolute aiming point 5 yd out, 3 yd deep
    return _run(ctx, "Outside Zone", "Outside Zone", "zone", ctx.run_strong, 5.8, (0, 15, -9))


@concept("Duo", "run", "double teams straight ahead, downhill between the guards", ("base", "short", "goal"))
def _duo(ctx):
    return _run(ctx, "Duo", "Duo", "drive", ctx.run_strong, 0.8, (1, 0, 9))


@concept("Power", "run", "backside guard pulls and kicks out, the back follows him off tackle", ("base", "short", "goal"))
def _power(ctx):
    # retail Strong Power: hole 5.8 yd, absolute aiming point 6.7 yd wide on the line
    return _run(ctx, "Power", "Power", "power", ctx.run_strong, 5.8, (0, 20, 0), puller=True, lead=True)


@concept("Counter", "run", "counter step, the guard pulls across, the back follows him", ("base",), preference=2)
def _counter(ctx):
    return _run(ctx, "Counter", "Counter", "counter", -ctx.run_strong, 0.8, (2, 3, 0), handoff=5, take_a=1,
                take_t=0.1, puller=True)


@concept("Trap", "run", "let the tackle through, trap him with the backside guard", ("base", "short"), preference=2)
def _trap(ctx):
    return _run(ctx, "Trap", "Trap", "trap", ctx.run_strong, 0.8, (2, 0, 0), puller=True)


@concept("Toss", "run", "pitch to the back running to the edge, line reaches", ("base",), preference=2)
def _toss(ctx):
    d = ctx.run_strong
    out_design = _run(ctx, "Toss", "Toss", "reach", d, 5.8, (0, 30, -3), handoff=1, header="run_toss")
    return out_design


@concept("Iso", "run", "fullback isolates the linebacker, the back reads his block", ("short", "goal"))
def _iso(ctx):
    if ctx.slot("B2") is None:
        raise ConceptUnavailable("iso needs a fullback")
    return _run(ctx, "Iso", "Iso", "drive", ctx.run_strong, 2.5, (2, 0, -3), take_a=1, lead=True)


@concept("Draw", "run", "line sets like a pass, QB drops, then hands it to the back", ("long", "base"), preference=2)
def _draw(ctx):
    return _run(ctx, "Draw", "Draw", "draw", ctx.run_strong, 0.8, (1, 0, 9), handoff=4, header="draw")


@concept("QB Sneak", "run", "QB follows the centre, everybody drives", ("short", "goal"))
def _qb_sneak(ctx):
    if ctx.gun:
        raise ConceptUnavailable("sneak needs the QB under centre")
    out = [None] * 11
    for p in ctx.ol():
        head = [start(2), (0x02, [ctx.qb.slot])] if p.kind == C else [start(3)]
        inward = 0 if p.kind == C else (-1 if p.x > 0 else 1)
        out[p.slot] = head + [legf(0, inward, 3, turn=2 if p.kind == C else (1 if p.x > 0 else 0))]
    for p in ctx.players:
        if p.kind in (WR, TE, HB, FB):
            out[p.slot] = [start(3), legf(3, 0, 15, turn=2, group=1)]
    out[ctx.qb.slot] = [start(4), (0x03, [0]), move(0, -3), path(1, 0, 3, a=2)]
    return PlayDesign("QB Sneak", "QB Sneak", "sneak", "qb_sneak", out, ctx.qb.slot, [], ("short", "goal"), 1)


@concept("QB Draw", "run", "QB sells the pass, then runs through the middle", ("long",), preference=3)
def _qb_draw(ctx):
    out = [None] * 11
    for slot, ch in _run_ol(ctx, "draw", ctx.strong).items():
        out[slot] = ch
    for lab, name, depth in (("S1", "Go", 15), ("S2", "Seam", 15), ("S3", "Seam", 15),
                             ("W1", "Go", 15), ("W2", "Seam", 15)):
        s = ctx.slot(lab)
        if s is not None:
            out[s] = route_chain(name, depth)
    for lab in ("B", "B2"):
        s = ctx.slot(lab)
        if s is not None:
            out[s] = [start(3), legf(4, 0, 9, turn=2, group=1, rel=0)]
    out[ctx.qb.slot] = [start(4), (0x03, [0]), move(0, -15), path(0, 6, -6, a=0)]
    return PlayDesign("QB Draw", "QB Draw", "keeper", "qb_draw", out, ctx.qb.slot, [], ("long",), 3)


# -- trick plays ---------------------------------------------------------------------------

def _behind_qb(ctx: FormationContext) -> int | None:
    b = ctx.slot("B")
    if b is None:
        return None
    p = ctx.player(b)
    return b if abs(p.x) <= 1.0 and p.z < ctx.qb.z else None


@concept("Flea Flicker", "trick", "hand off, the back runs up and pitches it back, QB throws deep",
         ("shot", "gadget"), preference=4)
def _flea(ctx):
    b = _behind_qb(ctx)
    if b is None:
        raise ConceptUnavailable("flea flicker needs the back directly behind the QB")
    hole = hole_toward(ctx.strong, 0.8)
    out = [None] * 11
    for p in ctx.ol():
        out[p.slot] = ol_chain(ctx, p.slot, "pa")
    out[b] = [start(3), take(hole), path(1, 0, 9, a=2), (0x13, [ctx.qb.slot, 1]),
              legf(6, 0, 6, turn=2, end=3, group=1)]
    deep = {"S1": ("Go", 15), "S2": ("Post", 10), "S3": ("Over", 8), "W1": ("Post Corner", 8), "W2": ("Seam", 15)}
    reads = []
    for lab, (name, depth) in deep.items():
        s = ctx.slot(lab)
        if s is not None:
            out[s] = route_chain(name, depth)
            reads.append(s)
    if ctx.slot("B2") is not None:
        out[ctx.slot("B2")] = back_block_chain(ctx, ctx.slot("B2"))
    if not reads:
        raise ConceptUnavailable("flea flicker needs receivers")
    order = sorted(reads, key=lambda s: -(route_end_depth_yd(ctx, s, out[s]) or 0))
    out[ctx.qb.slot] = [start(4), (0x03, [0]), (0x13, [b, 0]), take(hole), pass_node(order)]
    return PlayDesign("Flea Flicker", "Flea Flicker", "flea", "flea", out, order[0], order, ("shot", "gadget"), 4)


@concept("End Around", "trick", "QB hands straight to the slot coming the other way (retail slot reverse)",
         ("gadget", "base"), preference=4)
def _end_around(ctx):
    if ctx.gun:
        raise ConceptUnavailable("end around needs the QB under centre (retail exchange envelope)")
    runner = None
    for lab in ("S2", "S3", "W2"):
        s = ctx.slot(lab)
        if s is None:
            continue
        p = ctx.player(s)
        sep = math.hypot(p.x - ctx.qb.x, p.z - ctx.qb.z)
        if p.kind == WR and not p.on_los and sep <= 9.6:
            runner = s
            break
    if runner is None:
        raise ConceptUnavailable("end around needs an off-line slot within the retail 9 yard envelope")
    side = 1 if ctx.player(runner).x > 0 else -1
    out = [None] * 11
    for p in ctx.ol():
        head = [start(2), (0x02, [ctx.qb.slot])] if p.kind == C else [start(3)]
        out[p.slot] = head + [legf(8, 0, 3, turn=0, group=2)]
    out[runner] = [start(3), take(8 if side > 0 else 1), path(0, -side * 30, -12, a=2)]
    for p in ctx.players:
        if out[p.slot] is not None or p.kind not in (WR, TE, HB, FB):
            continue
        if p.kind == TE and p.on_los:
            out[p.slot] = [start(3), legf(8, 0, 3, turn=0, group=2)]
        elif p.kind in (HB, FB):
            out[p.slot] = [start(3), release(side * 5, 0, a=2, b=8), legf(0, side * 5, 0, turn=2, rel=0)]
        else:
            out[p.slot] = stalk_chain()
    out[ctx.qb.slot] = [start(4), (0x03, [0]), (0x13, [runner, 2])]
    return PlayDesign("End Around", "End Around", "reverse", "reverse", out, runner, [], ("gadget",), 4)


@concept("Reverse", "trick", "toss to the back, who hands to the receiver coming back (retail toss reverse)",
         ("gadget",), preference=4)
def _reverse(ctx):
    b = _behind_qb(ctx)
    if b is None or ctx.gun:
        raise ConceptUnavailable("reverse needs the back behind an under-centre QB")
    runner = None
    bp = ctx.player(b)
    for lab in ("W2", "W1"):
        s = ctx.slot(lab)
        if s is None:
            continue
        p = ctx.player(s)
        if p.kind == WR and not p.on_los and math.hypot(p.x - bp.x, p.z - bp.z) <= 10.5:
            runner = s
            break
    if runner is None:
        raise ConceptUnavailable("reverse needs an off-line receiver on the weak side")
    side = 1 if ctx.player(runner).x > 0 else -1          # runner's side; the toss goes the other way
    out = [None] * 11
    for p in ctx.ol():
        head = [start(2), (0x02, [ctx.qb.slot])] if p.kind == C else [start(3)]
        out[p.slot] = head + [legf(8, 0, 3, turn=1, group=2)]
    out[b] = [start(3), take(1 if side > 0 else 8), (0x13, [runner, 2]), legf(4, side * 9, 5, turn=2, group=1)]
    out[runner] = [start(3), take(8 if side > 0 else 1, a=1, t=0.1), path(0, -side * 30, -15, a=2)]
    for p in ctx.players:
        if out[p.slot] is None and p.kind in (WR, TE, HB, FB):
            out[p.slot] = stalk_chain() if p.kind == WR else [start(3), legf(8, 0, 3, turn=1, group=2)]
    out[ctx.qb.slot] = [start(4), (0x03, [0]), (0x13, [b, 1]), legf(4, -side * 36, -6, turn=2, group=1, rel=0)]
    return PlayDesign("Reverse", "Reverse", "reverse", "reverse", out, runner, [], ("gadget",), 4)


_OVERRIDES: list = []


def active_overrides() -> dict:
    return _OVERRIDES[-1] if _OVERRIDES else {}


def design(name: str, ctx: FormationContext, overrides: Mapping | None = None) -> PlayDesign:
    """Build concept ``name`` for formation ``ctx`` (raises ConceptUnavailable).

    ``overrides`` is the team-package extension point (all optional):
    ``routes``  {label: ["route", name, depth] | ["check", name] | ["block"] | ...} replaces roles,
    ``reads``   [labels] new read order, ``depth_step`` yards added to intermediate/deep stems,
    ``direction`` "weak" flips a run, ``name`` display name, ``preference`` 0-4."""
    ov = dict(overrides or {})
    _OVERRIDES.append(ov)
    try:
        d = CONCEPTS[name].build(ctx)
    finally:
        _OVERRIDES.pop()
    # Screens author their blocking and timing directly rather than through PassPlan.
    # Honor receiver route variants here without rebuilding their screen protection.
    if "screen" in d.tags and ov.get("routes"):
        plan = PassPlan({}, [])
        release_yd = qb_release_yd(ctx, d.chains[ctx.qb.slot])
        for label, spec in ov["routes"].items():
            slot = _resolve(ctx, str(label))
            if slot is None:
                raise ConceptUnavailable(f"{name}: screen override receiver {label} is absent")
            if ctx.player(slot).kind not in (WR, TE, HB, FB):
                raise ConceptUnavailable(f"{name}: screen override requires an eligible receiver")
            chain = _spec_chain(ctx, slot, tuple(spec), plan)
            d.chains[slot] = ensure_forward(ctx, slot, chain, release_yd)
    if ov.get("name"):
        d.name = str(ov["name"])[:40]
    if "preference" in ov:
        d.preference = int(ov["preference"])
    return d


def available(ctx: FormationContext, names: Iterable[str] | None = None) -> list[str]:
    out = []
    for name in (names or CONCEPTS):
        try:
            design(name, ctx)
        except ConceptUnavailable:
            continue
        out.append(name)
    return out


# ---------------------------------------------------------------------------
# Formation library (strong side right; the game mirrors when a play is flipped)
# ---------------------------------------------------------------------------

#: Canonical skill-slot codes per personnel group (slots 6-10).  X = WR (left outside),
#: Z = WR2 (right outside), WR3 = the inside slot: the order the depth-role pass assigns
#: from geometry, so the roster's WR1 lines up at X in every set of a group.
PERSONNEL_CODES: dict[str, tuple[int, ...]] = {
    "11": (8, 9, 41, 73, 10),          # Kings:  TE, WR, WR2, WR3, HB
    "12": (8, 9, 41, 40, 10),          # Ace:    TE, WR, WR2, TE2, HB
    "21": (8, 9, 41, 11, 10),          # Pro:    TE, WR, WR2, FB, HB
    "22": (8, 9, 40, 11, 10),          # Jokers: TE, WR, TE2, FB, HB
    "23": (8, 40, 72, 11, 10),         # Jacks:  TE, TE2, TE3, FB, HB
    "20": (9, 41, 73, 11, 10),         # Queens: WR, WR2, WR3, FB, HB
    "10": (9, 41, 73, 105, 10),        # Flush:  WR, WR2, WR3, WR4, HB
    "01": (8, 9, 41, 73, 105),         # Straight: TE, WR, WR2, WR3, WR4
    "00": (9, 41, 73, 105, 137),       # 5 Wide: WR, WR2, WR3, WR4, WR5
}
#: Native personnel category ids (u-ai map 2.4): the CPU's situational target scale.
PERSONNEL_CATEGORY_ID = {"23": 0, "22": 2, "12": 3, "21": 4, "11": 6, "20": 7, "01": 8, "10": 9, "00": 10}
LINE_CM = ((0, 0), (302, 0), (-302, 0), (0, 0), (155, 0), (-155, 0))
LINE_CODES = (0, 5, 37, 6, 7, 39)
QB_DEPTH_CM = {"uc": -185, "gun": -482, "pistol": -366}
GUN_HB = (-2.5, -5.27)


@dataclass(frozen=True)
class FormationSpec:
    name: str
    personnel: str
    align: str                     # uc | gun | pistol (pistol is gun-flagged: QB 4 yd deep)
    skills: tuple                  # five (x, z) yards in PERSONNEL_CODES order
    tag: str                       # goal | short | base | pass | spread | empty
    situation: tuple               # retail (short, medium, long) rating target, census of same-kind retail sets
    backs: int                     # backfield type: 0 empty, 1 single back, 2 two backs
    blurb: str = ""

    def positions_cm(self) -> list[tuple[int, int]]:
        pos = [(0, QB_DEPTH_CM[self.align])] + list(LINE_CM[1:])
        pos += [(round(x * YD), round(z * YD)) for x, z in self.skills]
        return pos

    def codes(self) -> tuple[int, ...]:
        return LINE_CODES + PERSONNEL_CODES[self.personnel]

    def context(self) -> FormationContext:
        return FormationContext.build(self.positions_cm(), self.codes())

    def template_players(self) -> list:
        kinds = [c & 31 for c in self.codes()]
        return [lib.TemplatePlayer(k, x / YD, z / YD) for k, (x, z) in zip(kinds, self.positions_cm())]


FORMATIONS: dict[str, FormationSpec] = {}


def _formation(name, personnel, align, skills, tag, situation, backs, blurb=""):
    FORMATIONS[name] = FormationSpec(name, personnel, align, tuple(skills), tag, tuple(situation), backs, blurb)


_UC_HB = (0, -7)
# 11 personnel
_formation("Singleback Doubles", "11", "uc", [(5, 0), (-17, 0), (16, -1.5), (-9, -1.5), _UC_HB], "base", (3, 2, 1), 1,
           "2x2: tight end and Z right, X and the slot left")
_formation("Singleback Trey", "11", "uc", [(5, 0), (-17, 0), (17, -1.5), (10, -1.5), _UC_HB], "base", (3, 2, 1), 1,
           "3x1 with the tight end attached as #3")
_formation("Singleback Bunch", "11", "uc", [(8, 0), (-17, 0), (10, -1.5), (6.5, -1.5), _UC_HB], "base", (3, 2, 1), 1,
           "three-man bunch right, tight end on the point")
_formation("Gun Doubles", "11", "gun", [(5, 0), (-17, 0), (16, -1.5), (-9, -1.5), GUN_HB], "pass", (4, 2, 1), 1,
           "shotgun 2x2 with the back offset")
_formation("Gun Trey", "11", "gun", [(5, 0), (-17, 0), (17, -1.5), (10, -1.5), GUN_HB], "pass", (4, 2, 1), 1,
           "shotgun 3x1, tight end attached as #3")
_formation("Gun Trips", "11", "gun", [(6, -1.5), (-17, 0), (17, 0), (11, -1.5), GUN_HB], "pass", (4, 3, 0), 1,
           "shotgun trips right, tight end off the ball as #3")
_formation("Gun Bunch", "11", "gun", [(8, 0), (-17, 0), (10, -1.5), (6.5, -1.5), GUN_HB], "pass", (4, 2, 1), 1,
           "shotgun bunch right")
_formation("Gun Empty Trey", "11", "gun", [(5, 0), (-17, 0), (17, -1.5), (-9, -1.5), (11, -1.5)], "empty", (4, 3, 0), 0,
           "empty 3x2: the back split out between the tight end and Z")
_formation("Pistol Doubles", "11", "pistol", [(5, 0), (-17, 0), (16, -1.5), (-9, -1.5), _UC_HB], "base", (3, 2, 1), 1,
           "pistol 2x2, the back directly behind the QB")
_formation("Gun Wing", "11", "gun", [(6.5, -1.0), (-17, 0), (17, 0), (-9, -1.5), GUN_HB], "pass", (4, 2, 1), 1,
           "shotgun with the tight end on the wing")
_formation("Pistol Wing", "11", "pistol", [(6.5, -1.0), (-17, 0), (17, 0), (-9, -1.5), _UC_HB], "base", (3, 2, 1), 1,
           "pistol with the tight end on the wing (b77 p6s)")
_formation("Singleback Wing", "11", "uc", [(6.5, -1.0), (-17, 0), (17, 0), (-9, -1.5), _UC_HB], "base", (3, 2, 1), 1,
           "under centre with the tight end on the wing (b77 p6s)")
# 12 personnel
_formation("Singleback Ace", "12", "uc", [(5, 0), (-16, -1.5), (16, -1.5), (-5, 0), _UC_HB], "base", (2, 1, 3), 1,
           "two tight ends attached, receivers off the ball")
_formation("Ace Wing", "12", "uc", [(5, 0), (-17, 0), (16, -1.5), (6.5, -1.2), _UC_HB], "base", (2, 1, 2), 1,
           "tight end attached right with the second on the wing")
_formation("Singleback Y Trips", "12", "uc", [(5, 0), (-17, 0), (17, -1.5), (10, -1.5), _UC_HB], "base", (3, 2, 1), 1,
           "3x1 with the second tight end flexed in the slot")
_formation("Gun Ace Wing", "12", "gun", [(5, 0), (-17, 0), (16, -1.5), (6.5, -1.2), GUN_HB], "pass", (4, 2, 1), 1,
           "shotgun 12 personnel with a wing")
_formation("Gun Y Trips", "12", "gun", [(5, 0), (-17, 0), (17, -1.5), (10, -1.5), GUN_HB], "pass", (4, 2, 1), 1,
           "shotgun 3x1 with two tight ends")
_formation("Pistol Ace", "12", "pistol", [(5, 0), (-16, -1.5), (16, -1.5), (-5, 0), _UC_HB], "base", (3, 1, 2), 1,
           "pistol with both tight ends attached")
_formation("Gun Ace", "12", "gun", [(5, 0), (-16, -1.5), (16, -1.5), (-5, 0), GUN_HB], "pass", (4, 2, 1), 1,
           "shotgun with both tight ends attached (b77 p6s)")
# 21 personnel
_formation("I-Form Pro", "21", "uc", [(5, 0), (-17, 0), (16, -1.5), (0, -4.5), (0, -7.0)], "base", (2, 0, 3), 2,
           "classic I: fullback, tailback, tight end right")
_formation("Strong I", "21", "uc", [(5, 0), (-17, 0), (16, -1.5), (1.7, -4.5), (0, -7.0)], "base", (2, 0, 3), 2,
           "fullback offset to the tight end")
_formation("Weak I", "21", "uc", [(5, 0), (-17, 0), (16, -1.5), (-1.7, -4.5), (0, -7.0)], "base", (2, 0, 3), 2,
           "fullback offset away from the tight end")
_formation("I-Form Twins", "21", "uc", [(5, 0), (-17, 0), (-10, -1.5), (0, -4.5), (0, -7.0)], "base", (3, 1, 2), 2,
           "both receivers left, tight end right")
_formation("Pistol Strong", "21", "pistol", [(5, 0), (-17, 0), (16, -1.5), (2.0, -4.3), _UC_HB], "base", (3, 1, 2), 2,
           "pistol with the fullback offset strong")
_formation("Split Backs", "21", "uc", [(5, 0), (-17, 0), (16, -1.5), (-2.5, -5.5), (2.5, -5.5)], "base", (3, 1, 2), 2,
           "pro set, backs split behind the tackles")
# 22 and 23 personnel (short yardage and goal line)
_formation("I-Form Tight", "22", "uc", [(5, 0), (-16, -1.5), (-5, 0), (0, -4.5), (0, -7.0)], "short", (0, 2, 4), 2,
           "two tight ends, fullback and tailback")
_formation("Heavy Wing", "22", "uc", [(5, 0), (-17, 0), (6.5, -1.2), (1.7, -4.5), (0, -7.0)], "short", (0, 3, 4), 2,
           "tight end and wing right, fullback offset")
_formation("Ace Jumbo", "22", "uc", [(5, 0), (-16, -1.5), (-5, 0), (6.5, -1.2), _UC_HB], "short", (0, 2, 4), 1,
           "13 look: two attached tight ends with the fullback on the wing, one back")
_formation("Goal Line", "23", "uc", [(5, 0), (-5, 0), (6.5, -1.0), (0, -4.0), (0, -6.5)], "goal", (0, 3, 4), 2,
           "three tight ends, fullback and tailback, tight splits")
# 20 personnel
_formation("Gun Split Backs", "20", "gun", [(-17, 0), (17, 0), (10, -1.5), (-2.5, -5.27), (2.5, -5.27)], "pass", (4, 2, 1), 2,
           "shotgun with a back on each side of the QB")
_formation("Split Backs Twins", "20", "uc", [(-17, 0), (17, 0), (10, -1.5), (-2.5, -5.5), (2.5, -5.5)], "base", (3, 1, 1), 2,
           "under centre, three receivers, split backs")
# 10 personnel
_formation("Gun Spread", "10", "gun", [(-17, 0), (17, 0), (9, -1.5), (-9, -1.5), GUN_HB], "spread", (4, 2, 0), 1,
           "four wide 2x2")
_formation("Gun Trips Open", "10", "gun", [(-17, 0), (17, 0), (7, -1.5), (12, -1.5), GUN_HB], "spread", (4, 3, 0), 1,
           "four wide, trips right")
_formation("Singleback Spread", "10", "uc", [(-17, 0), (17, 0), (9, -1.5), (-9, -1.5), _UC_HB], "spread", (3, 2, 1), 1,
           "four wide under centre")
_formation("Singleback Trips Open", "10", "uc", [(-17, 0), (17, 0), (7, -1.5), (12, -1.5), _UC_HB], "spread", (3, 2, 0), 1,
           "four wide trips right under centre")
# 01 and 00 personnel (empty)
_formation("Gun Empty Y", "01", "gun", [(5, 0), (-17, 0), (17, -1.5), (10, -1.5), (-9, -1.5)], "empty", (4, 3, 1), 0,
           "empty with the tight end attached")
_formation("Gun Empty", "00", "gun", [(-17, 0), (17, 0), (6, -1.5), (11, -1.5), (-9, -1.5)], "empty", (4, 3, 0), 0,
           "five wide 3x2")
_formation("Empty", "00", "uc", [(-17, 0), (17, 0), (6, -1.5), (11, -1.5), (-9, -1.5)], "empty", (4, 3, 1), 0,
           "five wide under centre")


# condensed and pistol variants (same receiver structure as their families, so they share plays)
_formation("Singleback Doubles Tight", "11", "uc", [(5, 0), (-10, 0), (10, -1.5), (-6.5, -1.5), _UC_HB], "base", (3, 2, 1), 1,
           "condensed 2x2: receivers inside the numbers for crossers and rubs")
_formation("Gun Doubles Tight", "11", "gun", [(5, 0), (-10, 0), (10, -1.5), (-6.5, -1.5), GUN_HB], "pass", (4, 2, 1), 1,
           "shotgun condensed 2x2")
_formation("Pistol Trey", "11", "pistol", [(5, 0), (-17, 0), (17, -1.5), (10, -1.5), _UC_HB], "base", (3, 2, 1), 1,
           "pistol 3x1, tight end attached as #3")
_formation("Pistol Bunch", "11", "pistol", [(8, 0), (-17, 0), (10, -1.5), (6.5, -1.5), _UC_HB], "base", (3, 2, 1), 1,
           "pistol bunch right")
_formation("Gun Split Pro", "21", "gun", [(5, 0), (-17, 0), (16, -1.5), (-2.5, -5.27), (2.5, -5.27)], "pass", (3, 2, 1), 2,
           "shotgun 21 personnel with a back on each side")
_formation("Strong I Twins", "21", "uc", [(5, 0), (-17, 0), (-10, -1.5), (1.7, -4.5), (0, -7.0)], "base", (3, 1, 2), 2,
           "fullback offset strong, both receivers left")
_formation("Gun Spread Tight", "10", "gun", [(-12, 0), (12, 0), (7, -1.5), (-7, -1.5), GUN_HB], "spread", (4, 2, 0), 1,
           "four wide condensed 2x2")
_formation("Gun Empty Bunch", "00", "gun", [(-17, 0), (8, 0), (6.5, -1.5), (10, -1.5), (-9, -1.5)], "empty", (4, 3, 0), 0,
           "five wide: bunch right, two left")


def formation_problems(spec: FormationSpec) -> list[str]:
    slots = [codec.FormationSlot(0, codec.NO_MIRROR, 1, [x] * 3, [z] * 3) for x, z in spec.positions_cm()]
    return codec.formation_legality(slots, spec.codes(), offense=True)


# ---------------------------------------------------------------------------
# Studio wizard catalog (Create a Play / Create a Formation)
# ---------------------------------------------------------------------------

MODERN_SUFFIX = " (modern)"
FORMATION_SUFFIX = " (2K28)"
_RUN_FAMILIES = ("run",)


def wizard_name(name: str, existing: Mapping) -> str:
    return name if name not in existing else name + MODERN_SUFFIX


def register_wizard_catalog() -> None:
    """Expose every engine route, concept, run and formation to the Create a Play wizard.

    Additive: entries already in the play library keep their names and behaviour; an
    engine entry whose name is taken gets the "(modern)" suffix.  Idempotent."""
    if getattr(lib, "_MODERN_CATALOG", False):
        return
    for name, r in ROUTES.items():
        if name in lib.ROUTES_BY_NAME:
            continue
        lib.ROUTE_LIBRARY.append(lib.RouteDef(name, lambda d, s, _n=name: ROUTES[_n].build(d), r.default_depth,
                                              f"{r.blurb} (retail {r.retail})"))
    lib.ROUTES_BY_NAME.clear()
    lib.ROUTES_BY_NAME.update({r.name: r for r in lib.ROUTE_LIBRARY})
    for name, cd in CONCEPTS.items():
        if cd.family in _RUN_FAMILIES or name in ("QB Sneak", "QB Draw", "End Around", "Reverse"):
            key = wizard_name(name, lib.RUN_SCHEMES)
            lib.RUN_SCHEMES[key] = {"kind": None, "dir": "right", "blurb": cd.blurb, "engine": name}
        elif cd.family == "trick":
            continue                      # the flea flicker is its own play type
        else:
            key = wizard_name(name, lib.PASS_CONCEPTS)
            lib.PASS_CONCEPTS[key] = {"blurb": cd.blurb, "engine": name, "outside": "Go", "inside": "Go",
                                      "te": "Go", "back": "Block (stay in)"}
    for name, spec in FORMATIONS.items():
        lib.FORMATION_TEMPLATES[name + FORMATION_SUFFIX] = (spec.blurb or name, spec.template_players())
    lib._MODERN_CATALOG = True


def engine_assignments(engine: str, positions_cm: Sequence, kinds: Sequence[int]) -> PlayDesign:
    """Engine design for a wizard PlaySpec (positions in cm, kinds per slot)."""
    return design(engine, FormationContext.build(positions_cm, list(kinds)))


register_wizard_catalog()
