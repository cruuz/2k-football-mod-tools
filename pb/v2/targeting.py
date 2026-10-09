"""Team target shares influence compatible reads, never receiving assignments.

The native 198E40 read setup and 199100 evaluation scheduler consume this
order. 1985E0 still chooses by viability, projected catch score, depth, cost,
attributes and attribute-based tie breaks. This policy is a tendency, not a
forced target.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import json
from pathlib import Path

from mod_editor.core import nfl2k5_offense_concepts as oc

DATA = Path(__file__).resolve().parents[1] / "research" / "targets_2026.json"
ROLE_KIND = {oc.WR: "WR", oc.TE: "TE", oc.HB: "RB", oc.FB: "FB"}


@lru_cache(maxsize=1)
def target_data():
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    if doc["season"] != 2026 or len(doc["teams"]) != 32 or not doc["coverage"]["weeks"]:
        raise ValueError("target policy requires a complete sourced 2026 league")
    return doc


def roles(spec):
    """Canonical formation slots are X, Z, slot, TE1/2/3 and RB1/FB1.

    PERSONNEL_CODES are the generator's depth-role convention, not left/right
    receiver labels S1/W1 (which change with formation strength).
    """
    return {s: f"{ROLE_KIND[c & 31]}{(c >> 5) + 1}"
            for s, c in enumerate(spec.codes()) if (c & 31) in ROLE_KIND}


def depth_band(depth):
    return 0 if depth < 8 else 1 if depth < 16 else 2


def resolve_roles(codes, chart):
    """Resolve native rank/side chain, starting row and duplicate-player skip.

    WR's variant low bit chooses side vs rank and its upper bits give the
    starting row. TE, RB and FB have one rank chain and use the whole ordinal.
    Return the selected player's rank role, rather than treating a side-chain
    ordinal as a guarantee about a roster identity.
    """
    selected, result = set(), {}
    for slot, code in enumerate(codes):
        prefix = ROLE_KIND.get(code & 31)
        if prefix is None:
            continue
        ordinal = code >> 5
        chain = "side" if prefix == "WR" and ordinal & 1 else "rank"
        start = ordinal >> 1 if prefix == "WR" else ordinal
        players = [(role, p) for role, p in chart.items() if role.startswith(prefix)]
        players.sort(key=lambda item: (item[1][chain], item[1]["rank"], item[1]["side"],
                                       int(item[0][len(prefix):])))
        available = [role for role, _ in players[start:] if role not in selected]
        if not available:
            # The runtime can substitute when a position pool is absent or
            # exhausted. Do not guess that player's identity or borrow a
            # starter's targets. This unresolved slot has no policy weight.
            result[slot] = f"unresolved_{prefix}{ordinal+1}"
            continue
        result[slot] = available[0]
        selected.add(available[0])
    return result


def direct_band(ctx, slot, chain):
    # Block/check-release, fake handoff, screen block and leak jobs retain
    # their authored order. A pure receiving chain is Start + route nodes.
    if any(n[0] not in (0x01, 0x12) for n in chain):
        return None
    if any(n[0] == 0x12 and int(n[1][0]) in (8, 9, 10) for n in chain):
        return None
    depth = oc.route_end_depth_yd(ctx, slot, chain)
    return None if depth is None else depth_band(depth)


def apply(design, spec, team, shares=None):
    """Permute existing direct reads within their original depth-band positions.

    Reads in each compatible band descend by observed share. Equal shares keep
    the concept's authored relative order. This gives the higher-target player
    priority whenever the concept permits the same receiving job depth.
    Screens, gadgets and moving-pocket concepts keep their intended target and
    side. No route, protection, delay, fake, receiving role or read membership
    changes. No prior-season fallback is permitted.
    """
    if (not design.reads or design.play_type not in ("pass", "pa_pass")
            or "screen" in design.tags or "gadget" in design.tags
            or any(n[0] == 0x06 and int(n[1][0]) != 0 for n in design.chains[0])
            or any(n[0] == 0x04 and int(n[1][0]) != 0 for n in design.chains[0])):
        return design
    row = target_data()["teams"][team]
    shares = row["role_shares"] if shares is None else shares
    ctx, slot_roles = spec.context(), resolve_roles(spec.codes(), row["depth_chart"])
    groups = {}
    for index, slot in enumerate(design.reads[:4]):
        band = direct_band(ctx, slot, design.chains[slot])
        if band is not None:
            groups.setdefault(band, []).append((index, slot))
    reads = list(design.reads)
    for candidates in groups.values():
        if len(candidates) < 2:
            continue
        ordered = sorted((s for _, s in candidates), key=lambda s: -shares.get(slot_roles[s], 0))
        for (index, _), slot in zip(candidates, ordered):
            reads[index] = slot
    if reads == design.reads:
        return design
    result = copy.deepcopy(design)
    result.reads, result.primary = reads, reads[0]
    for i, node in enumerate(result.chains[0]):
        if node[0] == 0x06:
            args = list(node[1])
            args[1:5] = [s - 5 for s in reads[:4]] + [0] * max(0, 4 - len(reads))
            result.chains[0][i] = (0x06, args)
    return result
