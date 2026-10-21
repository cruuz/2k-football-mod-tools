#!/usr/bin/env python3
"""Audit and repair route reversals in the shipped offense packs (b777 sc1).

The generator (``pb/v2/generator.py``, ``screen_blockers``) now builds screens and play-action backs that do not
reverse; this tool applies the same rules to packs that were generated before the fix, so a pack set can be
checked or patched without a full regeneration.  A rebuilt pack set (pb/v2/build.py) needs no patch: ``--audit`` on it
must report zero.

    python3 pb/v2/repair_reversals.py --audit                      # count reversing chains in data/playbooks
    python3 pb/v2/repair_reversals.py --apply --out /tmp/packs     # write repaired copies (never in place by default)

A repaired offense changes the book bytes: the defense packs (fingerprinted to the exact offense output) and the
screen timing pins must be regenerated after it (see pb/defense and pb/v2/pins.py).  Nothing here needs the retail
executable.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT)]

from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from mod_editor.core import nfl2k5_route_reversal as rr  # noqa: E402

PLAIN_VERTICAL = {(0,), (6, 0), (1, 0)}
POST_LIKE = {(0, 2), (0, 1), (2,), (1,)}
YD = 91.44


class _Design:
    """The three fields the repair reads."""

    def __init__(self, chains, primary, tags):
        self.chains, self.primary, self.tags = chains, primary, tags


def _chains(play: dict) -> list:
    return [[(int(n[0]), list(n[1])) for n in a] for a in play["assignments"]]


def _primary(play: dict):
    qb = next((n for n in play["assignments"][0] if int(n[0]) == 6), None)
    if qb is None:
        return None
    first = int(qb[1][1])
    return first + 5 if first else 7


def play_contexts(doc: dict, play_id: str) -> list:
    """Every formation whose menu lists the play, as ``(formation id, context)``: a linked play runs from all of them
    (a back starts 7 yd deep under centre and 5.3 yd deep in the gun, so a stem has to fit the shallowest start)."""
    out = []
    by_id = {f["id"]: f for f in doc["formations"]}
    for fid, ids in doc["menus"].items():
        if play_id in ids:
            f = by_id[fid]
            out.append((fid, oc.FormationContext.build([(float(x), float(z)) for x, z in f["slot_positions"]],
                                                       f["position_codes"])))
    return out


def _reversing_slots(contexts, chains, primary) -> set:
    return {p.slot for _fid, ctx in contexts for p in ctx.players
            if p.slot != primary and chains[p.slot] and rr.reversals(p.z, chains[p.slot])}


def repair_doc(doc: dict) -> Counter:
    """Repair ``doc`` (a pack's JSON) in place; returns counts by kind of fix."""
    stats: Counter = Counter()
    for play in doc["plays"]:
        if play.get("play_type") not in ("pass", "pa_pass"):
            continue
        contexts = play_contexts(doc, play["id"])
        if not contexts:
            continue
        chains = _chains(play)
        primary = _primary(play)           # the screen target keeps kind 9 / 10 by design
        bad = _reversing_slots(contexts, chains, primary)
        stats["chains_reversing"] += len(bad)
        if not bad:
            continue
        tags = ("screen",) if "creen" in play.get("concept", "") or "creen" in play.get("custom_name", "") else ()
        design = _Design(chains, primary, tags)
        for _fid, ctx in contexts:
            rr.decoys_to_blockers(oc, ctx, design, PLAIN_VERTICAL, POST_LIKE)
            rr.repair_design(oc, ctx, design)
        for slot in bad:
            stats["screen_blocker" if tags else "back_stem"] += 1
            play["assignments"][slot] = [[op, vals] for op, vals in design.chains[slot]]
        stats["plays_changed"] += 1
        stats["still_reversing"] += len(_reversing_slots(contexts, design.chains, primary))
    return stats


def audit_doc(doc: dict) -> Counter:
    stats: Counter = Counter()
    for play in doc["plays"]:
        if play.get("play_type") not in ("pass", "pa_pass"):
            continue
        contexts = play_contexts(doc, play["id"])
        bad = _reversing_slots(contexts, _chains(play), _primary(play)) if contexts else set()
        if bad:
            stats["plays"] += 1
            stats["chains"] += len(bad)
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--packs", type=Path, default=ROOT / "data/playbooks")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    total: Counter = Counter()
    for path in sorted(a.packs.glob("softdrink_*_modern.2k5book")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if a.apply:
            stats = repair_doc(doc)
            if a.out:
                a.out.mkdir(parents=True, exist_ok=True)
                pack = packs.pack_from_json(doc)
                packs.save_pack(pack, a.out / path.name)
        else:
            stats = audit_doc(doc)
        print(path.name, dict(stats))
        total.update(stats)
    print("TOTAL", dict(total))
    return 1 if (a.audit and total.get("chains")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
