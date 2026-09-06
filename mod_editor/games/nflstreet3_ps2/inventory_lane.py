"""Every ``/DATA`` container on the user's NFL Street 3 (PlayStation 2) disc, listed and never written.

This is the module's first rung and the one every other lane stands on.  The
walk itself is the shared
:class:`mod_editor.games._lanes.container_inventory.ContainerInventoryLane`; this
file is what points it at *this* disc and what says, in this disc's own numbers,
what it will find: **80 ``TERF`` containers and 27,178 members**, every one
of which the shared reader opens [M].

**The member cap here is two bounds, not one.**  27,178 members against a
6,000-row page means a flat cap spent in disc order would list the first few
containers and nothing after them; on this disc 16,259 of the members are in one
container.  So each container gets at most 150 rows and the disc gets at most
6,000, and the document says both numbers beside the totals it kept in full.

It writes nothing.  ``plan``, ``build`` and ``verify`` refuse by contract rather
than quietly doing nothing, which is what ``read_only`` marks and what the
studio reads to draw this page as a table instead of an editor.

**Retail-free.**  Names, offsets, sizes, codecs and format labels.  No member
payload leaves the user's disc.

Run it without a window::

    python3 -m mod_editor.games.nflstreet3_ps2.inventory_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

from mod_editor.games._lanes.container_inventory import ContainerInventoryLane
from mod_editor.games.contract import Refusal

from . import containers

CAPABILITY_ID = "nflstreet3ps2.textures.container_inventory"
LANE_ID = "textures.container_inventory"
SCHEMA = "nflstreet3_ps2_container_inventory/v1"

#: How many member rows the page lists across the disc, and how many one
#: container may take of that.  See the module docstring for why the second
#: bound exists.
MAX_MEMBER_TARGETS = 6000
MAX_MEMBERS_PER_CONTAINER = 150


class InventoryLane(ContainerInventoryLane):
    """The disc's containers and their members, read-only."""

    discs = containers
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    recipe_schema = SCHEMA
    title = "Every /DATA container on the disc"
    max_member_targets = MAX_MEMBER_TARGETS
    max_members_per_container = MAX_MEMBERS_PER_CONTAINER
    synthetic_name = "nflstreet3_ps2-inventory-synthetic.iso"
    validators = (
        "tools/validate_nflstreet3_ps2_inventory.sh",
        "tools/validate_nflstreet3_ps2_inventory.bat",
    )

    REFUSAL = (
        "The container inventory only lists what is on your disc; it writes nothing, so "
        "there is nothing here to plan, build or verify. The pages that do write name "
        "their own containers -- see docs/product/NFLSTREET3_PS2_MODULE.md for which lane owns "
        "which container."
    )


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.nflstreet3_ps2.inventory_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.nflstreet3_ps2.inventory_lane",
        description="List every /DATA container on a NFL Street 3 (PlayStation 2) disc. Read-only.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21482 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    if not arguments.selftest and not arguments.source:
        parser.error("give --source a disc image, or --selftest")
    lane = InventoryLane()
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                catalogue = lane.build_catalogue(lane.synthetic_source(Path(room)))
        else:
            catalogue = lane.build_catalogue(
                Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    print("INVENTORY containers=%d members=%d listed=%d formats=%s"
          % (document["containers"], document["members"], document["member_rows_listed"],
             ",".join(f"{k}:{v}" for k, v in sorted(document["format_totals"].items()))))
    return 0


__all__ = ["CAPABILITY_ID", "InventoryLane", "LANE_ID", "MAX_MEMBERS_PER_CONTAINER",
           "MAX_MEMBER_TARGETS", "SCHEMA"]


if __name__ == "__main__":
    raise SystemExit(_main())
