#!/usr/bin/env python3
"""Catalog the 37 ``PLAY`` playbooks on a PS2 ESPN NFL 2K5 disc.

Emits ``reports/gameplay_tuning/nfl2k5_ps2_playbook_catalog.v1.json``: per book
its content-id hash, book name, on-disc location and size, the formation / play
/ category / node counts, and the capacity headroom that decides whether a book
can take a new formation or play at all.

**Counts and names only.**  No playbook bytes, no play or formation names from
inside a book, no payload of any kind is read out into the catalog -- so the
result is a map of where the editable capacity is, not a copy of the game's
playbooks.  It is derived from the user's own disc and is safe to commit.

The headroom columns are the useful part.  Eight of the 37 books ship at the
270-play capacity, so a recipe that *adds* a play cannot target them; the same
eight are at capacity on the Xbox disc.  ``play_headroom`` is the number of
plays a book can still gain, ``formation_headroom`` the same for formations,
and ``node_headroom`` the remaining slots in the 3,500-node pool.

Usage::

    nfl2k5_ps2_playbook_target_catalog.py --iso SRC.iso \\
        [--output reports/gameplay_tuning/nfl2k5_ps2_playbook_catalog.v1.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _entry in (_ROOT, _HERE):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import nfl2k5_ps2_playbook_patch as patcher  # noqa: E402

SCHEMA = "nfl2k5_ps2_playbook_catalog/v1"
DEFAULT_OUTPUT = ("reports/gameplay_tuning/"
                  "nfl2k5_ps2_playbook_catalog.v1.json")

_KEEP = (
    "book_id", "book_name", "entry_index", "pack", "pack_iso_path",
    "pack_offset", "absolute_offset", "resource_size", "body_size",
    "compressed", "formations", "plays", "categories", "nodes", "chains",
    "formation_headroom", "play_headroom", "node_headroom",
    "at_play_capacity", "sha256",
)


def build(iso_path):
    rows = [{key: row[key] for key in _KEEP} for row in patcher.summarize(iso_path)]
    rows.sort(key=lambda row: row["absolute_offset"])
    totals = {
        "books": len(rows),
        "formations": sum(r["formations"] for r in rows),
        "plays": sum(r["plays"] for r in rows),
        "categories": sum(r["categories"] for r in rows),
        "nodes": sum(r["nodes"] for r in rows),
        "chains": sum(r["chains"] for r in rows),
        "formation_headroom": sum(r["formation_headroom"] for r in rows),
        "play_headroom": sum(r["play_headroom"] for r in rows),
        "node_headroom": sum(r["node_headroom"] for r in rows),
        "books_at_play_capacity": sum(1 for r in rows if r["at_play_capacity"]),
    }
    return {
        "schema": SCHEMA,
        "game": "ESPN NFL 2K5 (PS2, SLUS-20919)",
        "resource_kind": "PLAY",
        "capacities": {"formations": 50, "plays": 270, "nodes": 3500,
                       "categories": 26, "links_per_formation": 36},
        "resource_size": patcher.PLAY_RESOURCE_SIZE,
        "body_size": patcher.BODY_SIZE,
        "totals": totals,
        "books": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iso", required=True)
    parser.add_argument("--output", default=str(_ROOT / DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    try:
        catalog = build(args.iso)
    except patcher.PlaybookPatchError as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 1

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    totals = catalog["totals"]
    print("%d books -> %s" % (totals["books"], destination))
    print("  %d formations, %d plays, %d nodes"
          % (totals["formations"], totals["plays"], totals["nodes"]))
    print("  headroom: %d formations, %d plays, %d nodes; %d books at the play cap"
          % (totals["formation_headroom"], totals["play_headroom"],
             totals["node_headroom"], totals["books_at_play_capacity"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
