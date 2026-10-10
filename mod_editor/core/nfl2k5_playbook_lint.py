"""Football-execution linter and repair rules for NFL 2K5 PLAY books.

The PLAY validator (port of the game's 0x1A9840) only proves that a play is
*callable*. This module checks whether its geometry can work the way the
game's runtime executes it, using envelopes measured on the 37 retail books
with the game's own code (beta 77 job p13, offline native evidence):

* Handoffs (P1). The giver's Handoff To (0x13) and the target's Take Handoff
  (0x16) initializers (0x300B00 / 0x2E41F0) plan a meeting point with the
  exchange planner 0x2FFDD0. Retail QB-direct reverses start at most 9.05 yd
  apart (HB-to-WR toss reverses 10.59); a native plan for those needs at most
  7.04 yd of giver travel and 6.26 yd of runner travel. A direct handoff to a
  receiver 18 yd wide asks the QB to leave the pocket ~10 yd and the runner to
  cross ~10 yd, and the exchange can fire with the runner far away.
* Pass targets (P3). The native target solver 0x2DA8E0 leads a short receiver
  by about 1.75-2.75 yd; the forward/backward ruling 0x236810 follows the
  ball's launch direction. A receiver whose first catchable spot is level with
  or behind the QB's release depth is only forward while the QB stays deep; a
  QB caught mid-drop or stepping up throws a backward pass, and an incomplete
  backward pass is a live ball (fumble). Retail back routes always gain depth
  first; retail screens keep the back 2-4.5 yd in front of a 10 yd drop.
* Screens (P2). Retail back screens drop the QB 10 yd, put the back in front of
  that release, send the screen to the back's own side (3 of 174 cross), and
  release three linemen.
* Formations (P5 and general). Overlapping slots, offensive legality from the
  codec, and defensive fronts that stand two off-ball defenders over the ball.

Repair rules (``normalize_offense_play``) recognise the exact SOFTDRINK
complete-offense templates (pb/build_giants.assignments), prove that the
template reproduces the play byte for byte, and only then rebuild it:
an infeasible End Around goes to the nearest receiver inside the envelope,
an RB screen runs to the back's side and drops deep enough to keep the back
2 yd in front of the QB's set point (whole feet, never exactly 10 yd), and a
back's lateral route gains depth before it turns. Unrecognised plays are
never rewritten. Nothing here is a gameplay witness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable, Iterable, Mapping, Sequence

from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib
from . import nfl2k5_playbook_inspector as insp

YD = codec.YD_CM
SCHEMA = "nfl2k5_playbook_lint/v1"

# Retail envelopes, measured with the native initializers on all 37 retail books
# (510 reverse links, 3,971 ordinary handoff links in the 32 team books).
RETAIL_QB_REVERSE_SEPARATION_YD = 9.05      # QB-direct Slot Reverse / Fake Toss Reverse / WB Sweep
RETAIL_BACK_REVERSE_SEPARATION_YD = 10.59   # HB-to-WR Toss Reverse
RETAIL_HANDOFF_SEPARATION_YD = 5.97         # every other retail handoff in the team books
RETAIL_REVERSE_GIVER_TRAVEL_YD = 7.04       # native plan, reverses
RETAIL_REVERSE_RUNNER_TRAVEL_YD = 6.26
RETAIL_HANDOFF_GIVER_TRAVEL_YD = 7.50       # native plan, other handoffs
RETAIL_HANDOFF_RUNNER_TRAVEL_YD = 8.58
# A QB-direct reverse is only authored inside this separation (retail 9.05 plus one yard).
END_AROUND_MAX_SEPARATION_YD = 10.0
PITCH_GATE_YD = 10.0                        # toss path 0x2FF7C0 exchanges inside 914.4 cm
FORWARD_MARGIN_YD = 1.0                     # a route must finish this far in front of the QB release (retail p98)
SCREEN_MARGIN_YD = 2.0                      # a screen back starts this far in front (retail 2-4.5 yd)
RETAIL_SCREEN_DROP_YD = 10.0                # retail team-book back screens (169 of 174)
APPROACH_DEPTH_YD = -1.5                    # where a back's depth leg ends (d2b's checkdown repair)
SLOT_OVERLAP_CM = 40.0
DEFENDER_STACK_CM = 91.44
MUG_HALF_WIDTH_YD = 2.0
MUG_DEPTH_YD = 1.5
STANCE_STANDING = 1
RETAIL_BACK_FIRST_READ_SHARE = 0.29         # retail team books: a back is the QB's first read on 10-29% of pass links

SEVERITY = {
    "HANDOFF_FAR": "error", "HANDOFF_PLAN_FAR": "error", "PITCH_FAR": "error",
    "CHECKDOWN_BACKWARD": "error", "BACKWARD_TARGET": "warning",
    "SCREEN_DEPTH_MARGIN": "error", "SCREEN_SIDE_CROSS": "warning",
    "SCREEN_NO_RELEASE": "warning",
    "FORMATION_OVERLAP": "error", "FORMATION_ILLEGAL": "warning",
    "DEF_STACK": "warning", "DEF_MIDDLE_MUG": "warning", "BACK_PRIMARY_SHARE": "warning",
}
GOAL_IDS = {
    "HANDOFF_FAR": "P1", "HANDOFF_PLAN_FAR": "P1", "PITCH_FAR": "P1",
    "CHECKDOWN_BACKWARD": "P3", "BACKWARD_TARGET": "P3",
    "SCREEN_DEPTH_MARGIN": "P2", "SCREEN_SIDE_CROSS": "P2", "SCREEN_NO_RELEASE": "P2",
    "FORMATION_OVERLAP": "P5", "FORMATION_ILLEGAL": "P5", "DEF_STACK": "P5", "DEF_MIDDLE_MUG": "P5",
    "BACK_PRIMARY_SHARE": "P3",
}
# Play-level execution defects the Studio repair rules remove (BACK_PRIMARY_SHARE is a book-level design warning).
EXECUTION_CODES = ("HANDOFF_FAR", "HANDOFF_PLAN_FAR", "PITCH_FAR", "CHECKDOWN_BACKWARD", "BACKWARD_TARGET",
                   "SCREEN_DEPTH_MARGIN", "SCREEN_SIDE_CROSS", "SCREEN_NO_RELEASE")
DL_KINDS = frozenset({lib.DE, lib.DT})
RECEIVER_KINDS = frozenset({lib.WR, lib.TE, lib.HB, lib.FB})


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    formation: int
    formation_name: str
    play: int | None = None
    play_name: str = ""
    slot: int | None = None
    data: Mapping[str, object] = field(default_factory=dict)

    @property
    def severity(self) -> str:
        return SEVERITY[self.code]

    def to_json(self) -> dict:
        return dict(code=self.code, goal=GOAL_IDS[self.code], severity=self.severity, message=self.message,
                    formation=self.formation, formation_name=self.formation_name, play=self.play,
                    play_name=self.play_name, slot=self.slot, data=dict(self.data))


@dataclass
class PlayView:
    """One formation x play pairing in offense-relative centimetres (unflipped)."""
    formation: int
    formation_name: str
    play: int
    play_name: str
    play_flags: int
    positions: list[tuple[float, float]]
    codes: list[int]
    chains: list[list[codec.Node]]
    formation_type: int = 1

    @property
    def kinds(self) -> list[int]:
        return [c & 31 for c in self.codes]


@dataclass
class LintReport:
    label: str
    findings: list[Finding] = field(default_factory=list)
    plays_checked: int = 0
    links_checked: int = 0
    formations_checked: int = 0

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.code] = out.get(f.code, 0) + 1
        return dict(sorted(out.items()))

    def to_json(self) -> dict:
        return dict(schema=SCHEMA, label=self.label, plays_checked=self.plays_checked,
                    links_checked=self.links_checked, formations_checked=self.formations_checked,
                    counts=self.counts(), findings=[f.to_json() for f in self.findings])


# ---------------------------------------------------------------------------
# Reading books
# ---------------------------------------------------------------------------

def _decode(raw: bytes) -> codec.Node:
    return codec.Node.from_bytes(bytes(raw))


def resource_views(resource: bytes) -> Iterable[PlayView]:
    """Every offensive formation-play link of a PLAY resource."""
    book = insp.parse_playbook_resource(resource)
    body = resource[insp.RESOURCE_HEADER_SIZE:]
    for formation in book.formations:
        fr = lib.formation_record(body, formation.index)
        if fr.type_code >= 4:
            continue
        codes = lib.category_positions(body, lib.formation_category(body, formation.index))
        positions = [(float(s.x[0]), float(s.z[0])) for s in fr.slots]
        for link in formation.play_links:
            play = book.plays[link.play_index]
            if play.family_id != 0:
                continue
            chains = [[_decode(bytes.fromhex(n.raw_hex)) for n in book.assignment_chain(a).nodes]
                      for a in play.assignments]
            yield PlayView(formation.index, formation.name.strip(), play.index, play.name.strip(),
                           play.flags_or_id, positions, codes, chains, fr.type_code)


def pack_views(pack) -> Iterable[PlayView]:
    """Every pairing a ``.2k5book`` pack itself resolves (authored chains, no retail bytes).

    Complete-offense packs (v4) pair plays through their menus. Other pack
    schemas pair a play with ``link_formation`` when that names one of the
    pack's own formations; plays linked to stock formations need the target
    book and are linted after a build (``lint_resource``).
    """
    plays = {p.id: p for p in pack.plays}
    forms = {f.id: f for f in pack.formations}
    pairs = list(pack.menus) if getattr(pack, "menus", None) else []
    if not pairs:
        grouped: dict[str, list[str]] = {}
        for p in pack.plays:
            if getattr(p, "link_formation", None) in forms:
                grouped.setdefault(p.link_formation, []).append(p.id)
        pairs = list(grouped.items())
    for fid, menu in pairs:
        f = forms[fid]
        positions = [(float(x), float(z)) for x, z in f.slot_positions]
        codes = list(f.position_codes)
        if not codes or (codes[0] & 31) != lib.QB and not any((c & 31) == lib.QB for c in codes):
            continue          # defensive or special-teams formation
        for pid in menu:
            p = plays[pid]
            if getattr(p, "play_type", "") == "defense":
                continue
            chains = [list(codec.encode_chain(chain)) for chain in p.assignments]
            yield PlayView(f.replace_index if f.replace_index is not None else -1, f.custom_name,
                           p.replace_index if p.replace_index is not None else -1, p.custom_name,
                           int(p.play_flags or 0), positions, codes, chains)


def pack_defense_findings(pack) -> list[Finding]:
    """Defensive formation geometry of a pack (stances are not stored in packs: mug uses position only)."""
    out = []
    for i, f in enumerate(pack.formations):
        codes = list(f.position_codes)
        if not codes or any((c & 31) in (lib.QB, lib.C) for c in codes):
            continue
        pts = [(float(x), float(z)) for x, z in f.slot_positions]
        index = f.replace_index if f.replace_index is not None else -1
        for a in range(11):
            for b in range(a + 1, 11):
                d = math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1])
                if d < DEFENDER_STACK_CM:
                    out.append(Finding("DEF_STACK", f"{codec.position_label(codes[a])} (slot {a}) and "
                                       f"{codec.position_label(codes[b])} (slot {b}) stand {d / YD:.1f} yd apart",
                                       index, f.custom_name, data=dict(slots=[a, b], distance_yd=round(d / YD, 2))))
        mug = [s for s in range(11) if codes[s] & 31 not in DL_KINDS
               and abs(pts[s][0]) <= MUG_HALF_WIDTH_YD * YD and pts[s][1] <= MUG_DEPTH_YD * YD]
        if len(mug) >= 2:
            out.append(Finding("DEF_MIDDLE_MUG", "two or more off-ball defenders over the center within "
                               f"{MUG_DEPTH_YD:.1f} yd of the line (pack has no stance data): " + ", ".join(
                                   f"{codec.position_label(codes[s])} at ({pts[s][0] / YD:+.1f}, {pts[s][1] / YD:+.1f}) yd"
                                   for s in mug), index, f.custom_name, data=dict(slots=mug)))
    return out


# ---------------------------------------------------------------------------
# Geometry helpers (native semantics, see module docstring)
# ---------------------------------------------------------------------------

def qb_slot(view: PlayView) -> int | None:
    return next((s for s, k in enumerate(view.kinds) if k == lib.QB), None)


def qb_release_depth(view: PlayView) -> float | None:
    """Native 0x2F3D10 clamp: an encoded drop is LOS-relative and never moves the QB forward."""
    q = qb_slot(view)
    if q is None:
        return None
    return min([view.positions[q][1]] + [n.operands[2] for n in view.chains[q] if n.op == 0x04])


def is_pass(view: PlayView) -> bool:
    q = qb_slot(view)
    return q is not None and any(n.op == 0x06 for n in view.chains[q])


def first_read_slot(view: PlayView) -> int | None:
    q = qb_slot(view)
    node = next((n for n in view.chains[q] if n.op == 0x06), None) if q is not None else None
    if node is None:
        return None
    read = int(node.operands[1])
    return read + 5 if 1 <= read <= 5 else None


def route_segments(chain: Sequence[codec.Node]) -> list[codec.Node]:
    return [n for n in chain if n.op == 0x12]


def route_end_depth(chain: Sequence[codec.Node], start_z: float) -> float | None:
    """Depth (cm) where a receiver's route finishes, or None when the chain has no route.

    Upfield legs add their downfield component; lateral legs (4/5) and chips (8)
    keep depth; comebacks (7/11) give back 4 ft. Kind 9 is a pass block (or a
    screen release judged separately) and returns None.
    """
    z, seen = start_z, False
    for n in chain:
        if n.op != 0x12:
            continue
        kind, dist = int(n.operands[0]), max(float(n.operands[2]), 0.0)
        seen = True
        if kind == 9:
            return None
        if kind in (0, 10):
            z += dist
        elif kind in codec.ROUTE_BREAK_DEGREES:
            z += dist * math.cos(math.radians(codec.ROUTE_BREAK_DEGREES[kind]))
        elif kind in (7, 11):
            z -= 4 * codec.FT_CM
    return z if seen else None


def handoff_pairs(view: PlayView) -> list[tuple[int, int, int, int]]:
    """(giver, target, kind k, take hole) for every real Handoff To with a matching Take Handoff."""
    pairs = []
    for g, chain in enumerate(view.chains):
        for n in chain:
            if n.op != 0x13:
                continue
            t = int(n.operands[0])
            take = next((m for m in view.chains[t] if m.op == 0x16), None) if 0 <= t < 11 else None
            if take is None:
                continue
            pairs.append((g, t, int(n.operands[1]), int(take.operands[2])))
    return pairs


def separation_yd(view: PlayView, a: int, b: int) -> float:
    (ax, az), (bx, bz) = view.positions[a], view.positions[b]
    return math.hypot(ax - bx, az - bz) / YD


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

NativePlan = Callable[[PlayView, int, int], Mapping[str, float] | None]


def _finding(view: PlayView, code: str, message: str, slot: int | None = None, **data) -> Finding:
    return Finding(code, message, view.formation, view.formation_name, view.play, view.play_name, slot, data)


def check_handoffs(view: PlayView, native_plan: NativePlan | None = None) -> list[Finding]:
    out = []
    for giver, target, k, hole in handoff_pairs(view):
        sep = separation_yd(view, giver, target)
        gk, tk = view.kinds[giver], view.kinds[target]
        reverse = k == 2 or tk in (lib.WR, lib.TE)
        if k in (1, 3):
            limit, what = PITCH_GATE_YD, "pitch"
        elif reverse and gk == lib.QB:
            limit, what = END_AROUND_MAX_SEPARATION_YD, "QB-direct reverse/end-around"
        elif reverse:
            limit, what = RETAIL_BACK_REVERSE_SEPARATION_YD + 0.05, "reverse"
        else:
            limit, what = RETAIL_HANDOFF_SEPARATION_YD + 0.5, "handoff"
        data = dict(giver=giver, target=target, k=k, hole=hole, separation_yd=round(sep, 2), limit_yd=limit)
        if sep > limit:
            code = "PITCH_FAR" if k in (1, 3) else "HANDOFF_FAR"
            out.append(_finding(
                view, code, f"{what}: {codec.position_label(view.codes[giver])} (slot {giver}) hands to "
                f"{codec.position_label(view.codes[target])} (slot {target}) {sep:.1f} yd away at the snap; "
                f"retail never authors more than {limit:.1f} yd, so the exchange can fire before the runner arrives",
                target, **data))
        if native_plan is not None:
            plan = native_plan(view, giver, target)
            if plan:
                gl, rl = ((RETAIL_REVERSE_GIVER_TRAVEL_YD, RETAIL_REVERSE_RUNNER_TRAVEL_YD) if reverse else
                          (RETAIL_HANDOFF_GIVER_TRAVEL_YD, RETAIL_HANDOFF_RUNNER_TRAVEL_YD))
                if plan["giver_travel_yd"] > gl + 0.005 or plan["target_travel_yd"] > rl + 0.005:
                    out.append(_finding(
                        view, "HANDOFF_PLAN_FAR",
                        f"native exchange plan sends the giver {plan['giver_travel_yd']:.1f} yd and the runner "
                        f"{plan['target_travel_yd']:.1f} yd to the meeting point (retail at most {gl:.2f} / {rl:.2f})",
                        target, **data, **{k2: v for k2, v in plan.items()}))
    return out


def check_pass_targets(view: PlayView) -> list[Finding]:
    """A route that finishes level with or behind the QB's release depth is a backward-pass setup."""
    if not is_pass(view):
        return []
    release = qb_release_depth(view)
    screen = screen_receiver(view)
    out = []
    for s, chain in enumerate(view.chains):
        kind = view.kinds[s]
        if kind not in RECEIVER_KINDS or s == screen:
            continue
        end = route_end_depth(chain, view.positions[s][1])
        if end is None:
            continue
        margin = (end - release) / YD
        if margin >= FORWARD_MARGIN_YD:
            continue
        back = kind in (lib.HB, lib.FB)
        code = "CHECKDOWN_BACKWARD" if back else "BACKWARD_TARGET"
        where = "behind" if margin < 0 else "level with" if margin == 0 else "only just in front of"
        out.append(_finding(
            view, code, f"{codec.position_label(view.codes[s])} (slot {s}) finishes his route at "
            f"{end / YD:+.1f} yd, {where} the QB's {release / YD:+.1f} yd release ({margin:+.1f} yd); a throw "
            f"from a QB caught mid-drop or stepping up goes backward, and a dropped backward pass is a fumble "
            f"(retail backs finish at least {FORWARD_MARGIN_YD:.0f} yd in front in 98% of routes)", s,
            end_depth_yd=round(end / YD, 2), qb_release_yd=round(release / YD, 2), margin_yd=round(margin, 2)))
    return out


def screen_receiver(view: PlayView) -> int | None:
    if not is_pass(view):
        return None
    read = first_read_slot(view)
    if read is None:
        return None
    if any(n.op == 0x12 and int(n.operands[0]) in (9, 10) for n in view.chains[read]):
        if any(any(n.op == 0x18 for n in view.chains[s]) for s in range(11) if view.kinds[s] in lib.OL_KINDS) \
                or "screen" in view.play_name.lower():
            return read
    return None


def check_screen(view: PlayView) -> list[Finding]:
    s = screen_receiver(view)
    if s is None:
        return []
    out = []
    release = qb_release_depth(view)
    x, z = view.positions[s]
    margin = (z - release) / YD
    common = dict(receiver=s, qb_release_yd=round(release / YD, 2), receiver_depth_yd=round(z / YD, 2))
    if margin < SCREEN_MARGIN_YD:
        out.append(_finding(
            view, "SCREEN_DEPTH_MARGIN", f"screen back starts {margin:+.1f} yd from the QB's {release / YD:+.1f} yd "
            f"drop; retail drops {RETAIL_SCREEN_DROP_YD:.0f} yd so the back is 2-4.5 yd in front of the throw", s,
            margin_yd=round(margin, 2), **common))
    seg = next(n for n in view.chains[s] if n.op == 0x12 and int(n.operands[0]) in (9, 10))
    if int(seg.operands[0]) == 9 and abs(x) > 0.5 * YD:
        side = 1 if seg.operands[2] > 0 else -1
        if side * x < 0:
            out.append(_finding(
                view, "SCREEN_SIDE_CROSS", f"screen goes {'right' if side > 0 else 'left'} but the back is aligned "
                f"{abs(x) / YD:.1f} yd to the {'left' if x < 0 else 'right'}; he crosses the QB's drop "
                f"(retail: 3 of 174 back screens)", s, side=side, **common))
        releases = [o for o in range(11) if view.kinds[o] in lib.OL_KINDS
                    and any(n.op == 0x18 and n.operands[1] * side > 0 for n in view.chains[o])]
        if not releases:
            out.append(_finding(view, "SCREEN_NO_RELEASE", "no lineman releases to the screen side", s, side=side, **common))
    return out


def check_offense_formation(view: PlayView) -> list[Finding]:
    slots = [codec.FormationSlot(0, codec.NO_MIRROR, 1, [x] * 3, [z] * 3) for x, z in view.positions]
    issues = codec.formation_legality(slots, view.codes, offense=True)
    out = []
    for issue in issues:
        code = "FORMATION_OVERLAP" if "overlap" in issue else "FORMATION_ILLEGAL"
        out.append(Finding(code, issue, view.formation, view.formation_name))
    return out


def defense_findings(resource: bytes) -> list[Finding]:
    book = insp.parse_playbook_resource(resource)
    body = resource[insp.RESOURCE_HEADER_SIZE:]
    out = []
    for formation in book.formations:
        fr = lib.formation_record(body, formation.index)
        if fr.type_code not in (4, 5, 7):
            continue
        codes = lib.category_positions(body, lib.formation_category(body, formation.index))
        name = formation.name.strip()
        pts = [(float(s.x[0]), float(s.z[0])) for s in fr.slots]
        for a in range(11):
            for b in range(a + 1, 11):
                d = math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1])
                if d < DEFENDER_STACK_CM:
                    out.append(Finding("DEF_STACK", f"{codec.position_label(codes[a])} (slot {a}) and "
                                       f"{codec.position_label(codes[b])} (slot {b}) stand {d / YD:.1f} yd apart",
                                       formation.index, name, data=dict(slots=[a, b], distance_yd=round(d / YD, 2))))
        mug = [s for s in range(11) if codes[s] & 31 not in DL_KINDS and fr.slots[s].stance == STANCE_STANDING
               and abs(pts[s][0]) <= MUG_HALF_WIDTH_YD * YD and pts[s][1] <= MUG_DEPTH_YD * YD]
        if len(mug) >= 2:
            out.append(Finding("DEF_MIDDLE_MUG", "two or more off-ball defenders stand over the center within "
                               f"{MUG_DEPTH_YD:.1f} yd of the line: " + ", ".join(
                                   f"{codec.position_label(codes[s])} at ({pts[s][0] / YD:+.1f}, {pts[s][1] / YD:+.1f}) yd"
                                   for s in mug), formation.index, name,
                               data=dict(slots=mug, positions_yd=[(round(pts[s][0] / YD, 2), round(pts[s][1] / YD, 2))
                                                                  for s in mug])))
    return out


def lint_views(views: Iterable[PlayView], label: str, native_plan: NativePlan | None = None) -> LintReport:
    report = LintReport(label)
    plays, formations = set(), {}
    passes = back_first = 0
    for view in views:
        report.links_checked += 1
        plays.add(view.play)
        if is_pass(view):
            passes += 1
            read = first_read_slot(view)
            back_first += read is not None and view.kinds[read] in lib.BACK_KINDS
        if view.formation not in formations:
            formations[view.formation] = view
            report.findings.extend(check_offense_formation(view))
        report.findings.extend(check_handoffs(view, native_plan))
        report.findings.extend(check_pass_targets(view))
        report.findings.extend(check_screen(view))
    if passes >= 20 and back_first / passes > RETAIL_BACK_FIRST_READ_SHARE:     # a whole book, not a sample
        report.findings.append(Finding(
            "BACK_PRIMARY_SHARE", f"a back is the QB's first read on {back_first} of {passes} pass links "
            f"({100 * back_first / passes:.0f}%; retail team books 10-29%): the CPU's passing game runs through "
            "the back, so every back target must be forward-safe", -1, "(book)",
            data=dict(pass_links=passes, back_first_read=back_first, share=round(back_first / passes, 3))))
    report.plays_checked = len(plays)
    report.formations_checked = len(formations)
    return report


def lint_resource(resource: bytes, label: str = "book", native_plan: NativePlan | None = None) -> LintReport:
    report = lint_views(resource_views(resource), label, native_plan)
    report.findings.extend(defense_findings(resource))
    return report


def as_built(view: PlayView) -> PlayView:
    """The play the Studio compiler writes: d2b's deep-flat rule, then this module's repair rules."""
    authored = _authored(view.chains)
    flats, _ = lib.forward_back_flats(authored, view.positions, view.codes)
    fixed, _ = normalize_offense_play(view.positions, view.codes, flats)
    chains = fixed if fixed is not None else flats
    return PlayView(view.formation, view.formation_name, view.play, view.play_name, view.play_flags,
                    view.positions, view.codes, [list(codec.encode_chain(c)) for c in chains], view.formation_type)


def lint_pack(pack, label: str | None = None, *, studio_rules: bool = False,
              native_plan: NativePlan | None = None) -> LintReport:
    """Lint a ``.2k5book``; ``studio_rules`` lints the plays as the Studio compiler will write them."""
    views = pack_views(pack)
    if studio_rules:
        views = (as_built(v) for v in views)
    report = lint_views(views, label or pack.book.name, native_plan)
    report.findings.extend(pack_defense_findings(pack))
    return report


# ---------------------------------------------------------------------------
# Repair rules for the SOFTDRINK complete-offense templates
# ---------------------------------------------------------------------------

Chain = list
FIX_SCHEMA = "nfl2k5_playbook_fixes/v1"


def _encode(chain) -> list[bytes]:
    return [n.to_bytes() for n in codec.encode_chain(chain)]


def _as_bytes(chains) -> list[list[bytes]]:
    out = []
    for chain in chains:
        if chain and isinstance(chain[0], codec.Node):
            out.append([n.to_bytes() for n in chain])
        elif chain and isinstance(chain[0], (bytes, bytearray)):
            out.append([bytes(n) for n in chain])
        else:
            out.append(_encode(chain))
    return out


def _slot_of_code(codes: Sequence[int], code: int) -> int | None:
    return next((s for s, c in enumerate(codes) if c == code), None)


def end_around_template(positions, codes, receiver: int) -> list[Chain]:
    """pb/build_giants.assignments('End Around') for an explicit runner, in final slot order."""
    kinds = [c & 31 for c in codes]
    side = -1 if positions[receiver][0] > 0 else 1
    hb = _slot_of_code(codes, lib.HB)
    out: list[Chain] = [None] * 11
    out[0] = lib.qb_handoff_chain(receiver, 2)
    for s in range(1, 6):
        leg = lib.leg(8, side, 1, turn=0 if side > 0 else 1, group=2)
        out[s] = [lib.start(2 if kinds[s] == lib.C else 3), *([(2, [0])] if kinds[s] == lib.C else []), leg]
    for s in range(6, 11):
        out[s] = lib.stalk_block_chain() if kinds[s] == lib.WR else lib.blocker_chain("straight", side, True)
    out[receiver] = lib.carrier_chain(lib.handoff_hole_for_x(side * 10 * YD), (0, side * 10, -4, 2))
    if hb is not None and hb != receiver:
        out[hb] = lib.lead_block_chain(side * 5, 1)
    return out


def _template_matches(template: Sequence[Chain], chains_bytes: Sequence[Sequence[bytes]]) -> bool:
    try:
        return all(_encode(t) == list(c) for t, c in zip(template, chains_bytes))
    except ValueError:
        return False


def _end_around_runner(chains_bytes, codes) -> int | None:
    kinds = [c & 31 for c in codes]
    if kinds[0] != lib.QB or [b[0] for b in chains_bytes[0]] != [0x01, 0x03, 0x13]:
        return None
    node = codec.Node.from_bytes(chains_bytes[0][2])
    if int(node.operands[1]) != 2:
        return None
    runner = int(node.operands[0])
    return runner if 6 <= runner <= 10 and kinds[runner] in (lib.WR, lib.TE) else None


def fix_end_around(positions, codes, chains) -> tuple[list[Chain] | None, dict | None]:
    """Retarget an End Around whose runner is too far for the native exchange."""
    chains_bytes = _as_bytes(chains)
    runner = _end_around_runner(chains_bytes, codes)
    if runner is None:
        return None, None
    if not _template_matches(end_around_template(positions, codes, runner), chains_bytes):
        return None, None
    qb = 0
    sep = math.hypot(positions[runner][0] - positions[qb][0], positions[runner][1] - positions[qb][1]) / YD
    if sep <= END_AROUND_MAX_SEPARATION_YD:
        return None, None
    kinds = [c & 31 for c in codes]
    options = []
    for s in range(6, 11):
        if kinds[s] not in (lib.WR, lib.TE) or s == runner:
            continue
        d = math.hypot(positions[s][0] - positions[qb][0], positions[s][1] - positions[qb][1]) / YD
        if d <= END_AROUND_MAX_SEPARATION_YD:
            options.append((0 if kinds[s] == lib.WR else 1, round(d, 6), s))
    if not options:
        return None, dict(rule="end_around", status="no_feasible_runner", runner=runner, separation_yd=round(sep, 2))
    _, d, new = min(options)
    return end_around_template(positions, codes, new), dict(
        rule="end_around", status="retargeted", old_runner=runner, new_runner=new,
        old_separation_yd=round(sep, 2), new_separation_yd=round(d, 2))


def rb_screen_template(positions, codes, side: int, drop_yd: float) -> list[Chain] | None:
    """pb/build_giants.assignments('RB Slip') in final slot order, for an explicit side and drop."""
    kinds = [c & 31 for c in codes]
    hb = _slot_of_code(codes, lib.HB)
    if hb is None or kinds[0] != lib.QB:
        return None
    settings = lib.ScreenPreset("HB", hb, side, 0.8, drop_yd, 0.6)
    out: list[Chain] = [None] * 11
    out[0] = lib.screen_qb_chain(settings)
    for s in range(1, 6):
        out[s] = lib.center_chain(0, "pass", False) if kinds[s] == lib.C else lib.blocker_chain("pass", 0, False)
    for s in range(6, 11):
        out[s] = lib.blocker_chain("pass", 0, False) if kinds[s] in (lib.TE, lib.FB) else [lib.start(3), lib.seg(0, 20)]
    out[hb] = lib.screen_receiver_chain(side)
    release = [s for s in range(1, 6) if kinds[s] == lib.C]
    for k in (lib.T, lib.G):
        pool = [s for s in range(1, 6) if kinds[s] == k]
        if not pool:
            return None
        release.append(max(pool, key=lambda s: side * positions[s][0]))
    for s in release:
        out[s] = lib.screen_blocker_chain(kinds[s], settings, 0)
    return out


def screen_drop_yd(back_depth_cm: float, authored_drop_yd: float) -> float:
    """QB drop that leaves the screen back SCREEN_MARGIN_YD in front of the set point.

    Keeps the authored drop when it already does (level D's 7 yd for a back at -5);
    otherwise deepens it to the whole foot that restores the margin (9 yd for a back
    at -7). Never exactly 10 yd, which screen timing level D treats as a retail drop.
    """
    needed = -back_depth_cm / YD + SCREEN_MARGIN_YD
    if authored_drop_yd + 1e-6 >= needed:
        return authored_drop_yd
    feet = math.ceil(needed * 3 - 1e-6)
    if feet == 30:
        feet = 31          # 10 yd exactly is the retail drop that level D rewrites to 7
    return feet / 3


def fix_rb_screen(positions, codes, chains) -> tuple[list[Chain] | None, dict | None]:
    """An RB screen keeps its back in front of the QB's set point and runs to the back's own side."""
    chains_bytes = _as_bytes(chains)
    hb = _slot_of_code(codes, lib.HB)
    if hb is None or [b[0] for b in chains_bytes[0]] != [0x01, 0x03, 0x04, 0x06]:
        return None, None
    seg = [codec.Node.from_bytes(b) for b in chains_bytes[hb]]
    if [n.op for n in seg] != [0x01, 0x12] or int(seg[1].operands[0]) != 9:
        return None, None
    side = 1 if seg[1].operands[2] > 0 else -1
    drop = round(-codec.Node.from_bytes(chains_bytes[0][2]).operands[2] / YD, 6)
    template = rb_screen_template(positions, codes, side, drop)
    if template is None or not _template_matches(template, chains_bytes):
        return None, None
    hb_x, hb_z = positions[hb]
    new_side = (1 if hb_x > 0 else -1) if abs(hb_x) > 0.5 * YD else side
    new_drop = screen_drop_yd(hb_z, drop)
    if new_side == side and abs(new_drop - drop) < 1e-6:
        return None, None
    fixed = rb_screen_template(positions, codes, new_side, new_drop)
    return fixed, dict(rule="rb_screen", status="rebuilt", old_side=side, new_side=new_side,
                       old_drop_yd=round(drop, 2), new_drop_yd=round(new_drop, 2),
                       back_depth_yd=round(hb_z / YD, 2))


def fix_back_routes(positions, codes, chains) -> tuple[list[Chain] | None, dict | None]:
    """A back's lateral route gains depth to -1.5 yd first when it would finish within 1 yd of the QB release."""
    chains_bytes = _as_bytes(chains)
    kinds = [c & 31 for c in codes]
    q = next((s for s, k in enumerate(kinds) if k == lib.QB), None)
    if q is None:
        return None, None
    qnodes = [codec.Node.from_bytes(b) for b in chains_bytes[q]]
    if not any(n.op == 0x06 for n in qnodes):
        return None, None
    release = min([positions[q][1]] + [n.operands[2] for n in qnodes if n.op == 0x04])
    out = _authored(chains_bytes)
    changed = []
    for s, kind in enumerate(kinds):
        if kind not in lib.BACK_KINDS:
            continue
        nodes = [codec.Node.from_bytes(b) for b in chains_bytes[s]]
        if [n.op for n in nodes] != [0x01, 0x12] or nodes[0].flags != 0 or nodes[1].flags != 6:
            continue
        if list(nodes[0].operands) != [1, 3, 0, 0.0, 0.0, 0.0]:
            continue
        rkind, rflag, dist, k = nodes[1].operands
        if int(rkind) not in (4, 5) or int(rflag) != 0 or int(k) != 15:
            continue
        depth = positions[s][1]
        if depth >= release + FORWARD_MARGIN_YD * YD:
            continue
        approach = (APPROACH_DEPTH_YD * YD - depth) / YD
        if approach <= 0:
            continue
        out[s] = [lib.start(3), lib.seg(0, approach), (0x12, [int(rkind), 0, dist, 15])]
        changed.append(dict(slot=s, kind=int(rkind), depth_yd=round(depth / YD, 2),
                            qb_release_yd=round(release / YD, 2), approach_yd=round(approach, 2)))
    if not changed:
        return None, None
    return out, dict(rule="back_routes", status="depth_first", slots=changed)


def _authored(chains) -> list[Chain]:
    """Exact (opcode, operands) pairs; byte identity is checked by the callers."""
    out = []
    for chain in _as_bytes(chains):
        out.append([(n.op, list(n.operands)) for n in (codec.Node.from_bytes(b) for b in chain)])
    return out


def normalize_offense_play(positions, codes, chains) -> tuple[list[Chain] | None, list[dict]]:
    """Apply every repair rule in order; return (all eleven authored chains or None, receipts).

    Idempotent: a repaired play no longer matches any rule's trigger. Callers
    compare encoded bytes per slot and write only the slots that changed.
    """
    receipts: list[dict] = []
    current, changed = chains, False
    for rule in (fix_end_around, fix_rb_screen, fix_back_routes):
        fixed, receipt = rule(positions, codes, current)
        if receipt is not None:
            receipts.append(receipt)
        if fixed is not None:
            current, changed = fixed, True
    return (_authored(current) if changed else None), receipts


def changed_slots(old_chains, new_chains) -> list[int]:
    old_b, new_b = _as_bytes(old_chains), _as_bytes(new_chains)
    return [s for s in range(len(old_b)) if old_b[s] != new_b[s]]


__all__ = [
    "Finding", "LintReport", "PlayView", "as_built", "EXECUTION_CODES", "SCHEMA", "FIX_SCHEMA", "SEVERITY", "GOAL_IDS",
    "defense_findings", "end_around_template", "screen_drop_yd", "fix_back_routes", "fix_end_around", "fix_rb_screen",
    "lint_pack", "lint_resource", "lint_views", "pack_defense_findings", "normalize_offense_play", "pack_views", "rb_screen_template",
    "resource_views", "changed_slots",
]
