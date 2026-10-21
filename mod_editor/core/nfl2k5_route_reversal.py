"""Route reversal model and repair for authored play chains (b777, job sc1).

Why this exists
---------------
The retail route initializer (0x229AE0, endpoint code 0x225BEB..0x225CF8, traced under Unicorn on the real
executable) does not treat route segment kinds 9 and 10 as ordinary legs:

* kind 9  (pass block, the screen back)   ends 1.5 yd BEHIND the line of scrimmage, laterally ``distance`` yards,
  whatever the previous point was (the lateral end is clamped to +-19.67 yd);
* kind 10 (straight then block inside)    ends 1.0 yd BEHIND the line of scrimmage, whatever the previous point was.

Retail only ever puts kind 10 after a short stem on a BACK that starts 5.5 to 8 yd deep (a back steps up to the line to
block), where "1 yd behind the line" is ahead of him.  b776's generator (pb1) used the same ``stem 18/27 ft + kind 10``
as a receiver "Stem Block" on every WR and TE of a screen: a receiver who starts on the line runs the stem 6 to 9 yd
UPFIELD and is then sent back to 1 yd behind the line, so the screen's decoys sprint out and run backwards.  The
engine's own arithmetic (``route_end_depth_yd``) also treated kind 10 as "straight on", so nothing flagged it.

This module holds the corrected model, a lint (``reversals``) and the repair used by the generator.  The numbers come
from the native trace (``tests/mod_editor/data/sc1_native_route_ends.json`` keeps the golden results); nothing here
needs the retail executable.
"""
from __future__ import annotations

import math
from typing import Sequence

from . import nfl2k5_play_codec as codec

FT = codec.FT_CM
YD = codec.YD_CM

#: Native end depth (yards from the line, + downfield) forced by route kinds 9 and 10.
KIND_END_DEPTH_YD = {9: -1.5, 10: -1.0}
#: A segment that moves a receiver this far back toward his own goal line is a reversal.
REVERSAL_TOLERANCE_YD = 1.0
#: Kinds whose retreat is the designed shape of the route (comebacks and hooks), never flagged.
DESIGNED_RETURN_KINDS = frozenset({7, 8, 11})


def segment_depths(start_z_yd: float, chain: Sequence) -> list[tuple[int, float, float]]:
    """(kind, depth before, depth after) in yards for each route segment of ``chain``.

    Kinds 9 and 10 land on the native depth; straight legs add their length; angled legs add length*cos(angle);
    lateral legs add nothing; comebacks settle ~1 yd back.  Distances below zero (screen side) never count as depth."""
    z = float(start_z_yd)
    out = []
    for node in chain:
        if node[0] != 0x12:
            continue
        kind = int(node[1][0])
        dist = abs(float(node[1][2])) / YD
        before = z
        if kind in KIND_END_DEPTH_YD:
            z = KIND_END_DEPTH_YD[kind]
        elif kind == 0:
            z += dist
        elif kind in codec.ROUTE_BREAK_DEGREES:
            z += dist * math.cos(math.radians(codec.ROUTE_BREAK_DEGREES[kind]))
        elif kind in (7, 11):
            z -= 4 * FT / YD
        out.append((kind, before, z))
    return out


def route_end_depth_yd(start_z_yd: float, chain: Sequence) -> float | None:
    """Where a route finishes (yards from the line); ``None`` without a route segment."""
    path = segment_depths(start_z_yd, chain)
    return path[-1][2] if path else None


def reversals(start_z_yd: float, chain: Sequence, tolerance_yd: float = REVERSAL_TOLERANCE_YD) -> list[tuple]:
    """Segments that send the player back toward his own goal line: ``(kind, from_depth, to_depth)``.

    Only kinds 9 and 10 can do this by their native endpoint; designed comebacks (7, 8, 11) are skipped."""
    return [(k, a, b) for k, a, b in segment_depths(start_z_yd, chain)
            if k in KIND_END_DEPTH_YD and b < a - tolerance_yd]


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------

def clamp_stem(start_z_yd: float, chain: Sequence) -> list:
    """Shorten a back's ``stem + kind 10`` so the stem ends at or before the native kind-10 endpoint.

    The stem keeps whole yards (identical chains intern across formations); a back already at or past the endpoint
    gets a plain pass set (no route segments)."""
    out = list(chain)
    z = float(start_z_yd)
    for i, node in enumerate(out):
        if node[0] != 0x12:
            continue
        kind = int(node[1][0])
        if kind == 10:
            return out
        dist = abs(float(node[1][2])) / YD
        room = KIND_END_DEPTH_YD[10] - z
        if kind == 0 and dist > room:
            yards = math.floor(room) if room >= 1.0 else 0
            if yards <= 0:
                return [n for n in out if n[0] != 0x12]
            out[i] = (0x12, [0, node[1][1], yards * 3 * FT, node[1][3]])
            return out
        if kind == 0:
            z += dist
    return out


def blocker_chain(oc, ctx, slot: int) -> list:
    """What a non-target WR or TE does on a screen: block, never reverse (retail receiver run block / TE pass set)."""
    player = ctx.player(slot)
    if player.kind == oc.TE and player.on_los:
        return oc.te_block_chain(ctx, slot)
    return oc.stalk_chain()


def repair_design(oc, ctx, design) -> int:
    """Repair every reversing chain of one design in place; returns how many chains changed.

    * a WR or TE whose chain reverses is turned into a blocker (see ``blocker_chain``);
    * a back (HB/FB) whose stem overshoots the kind-10 endpoint gets a shorter stem;
    * the screen target (``design.primary``) is never touched here: screens are authored with kind 9 on purpose."""
    changed = 0
    for p in ctx.players:
        if p.slot == design.primary:
            continue
        chain = design.chains[p.slot]
        if not chain or not reversals(p.z, chain):
            continue
        if p.kind in (oc.HB, oc.FB):
            fixed = clamp_stem(p.z, chain)
        elif p.kind in (oc.WR, oc.TE):
            fixed = blocker_chain(oc, ctx, p.slot)
        else:
            continue
        design.chains[p.slot] = fixed
        changed += 1
    return changed


def decoys_to_blockers(oc, ctx, design, verticals=(), posts=()) -> int:
    """Screen decoys: every non-target WR or TE that runs a plain vertical or a post (or the old Stem Block) blocks.

    This is the generator's screen rule (``screen_blockers``): decoy verticals made a screen read as a pass play, the
    old Stem Block reversed (see the module doc), so the receivers release and stalk instead.  ``verticals`` and
    ``posts`` are the generator's kind-tuple classes (pb/v2/variety.py)."""
    if "screen" not in design.tags:
        return 0
    changed = 0
    for p in ctx.players:
        if p.slot == design.primary or p.kind not in (oc.WR, oc.TE):
            continue
        chain = design.chains[p.slot] or []
        kinds = tuple(int(n[1][0]) for n in chain if n[0] == 0x12)
        stem_block = kinds == (0, 10) or kinds == (10,)
        if stem_block or kinds in verticals or kinds in posts:
            design.chains[p.slot] = blocker_chain(oc, ctx, p.slot)
            changed += 1
    return changed

