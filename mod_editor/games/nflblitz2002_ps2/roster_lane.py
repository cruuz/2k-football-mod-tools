"""``roster.rst``: the one member on the disc whose name says roster, and its player names.

The file is a run of fixed blocks and nothing else [M]::

    block   u32 18, then 18 x 100-byte records          1,804 bytes
    record  char[32] first name, char[32] last name,    two NUL-terminated
            36 bytes of numbers                          ASCII fields, 0xCD-padded

===========================================================  ==========  ==========
identity                                                     2002        2003
===========================================================  ==========  ==========
member bytes                                                 73,964      75,768
``bytes % 1,804``                                            0           0
blocks (``bytes / 1,804``)                                   41          42
blocks whose header word is 18                               41 of 41    42 of 42
records whose two name fields are NUL-terminated ASCII       738 of 738  756 of 756
records whose byte +68 equals their block's ordinal          738 of 738  756 of 756
===========================================================  ==========  ==========

The lane is :class:`mod_editor.games._lanes.blitz_zip_lanes.RosterNameLane`; this
file is the row it takes on **this** disc.  The 36 numeric bytes are listed and
never written: two columns have exact identities (byte +68 is the block ordinal,
byte +72 takes exactly 18 distinct values 0..17) and looking like ratings is not
being ratings.
"""

from __future__ import annotations

from typing import Optional, Sequence

from mod_editor.games._lanes.blitz_zip_lanes import RosterNameLane, roster_lane_main

from . import containers

SCHEMA = "nflblitz2002_ps2_roster_names/v1"
GAME_ID = containers.GAME_ID
LANE_ID = "rosters.player_names"
CAPABILITY_ID = f"{GAME_ID.replace('_', '')}.{LANE_ID}"

LANE = RosterNameLane(containers, SCHEMA, LANE_ID)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    return roster_lane_main(containers, LANE, "NFL Blitz 2002 (PS2)", argv)


__all__ = ["CAPABILITY_ID", "LANE", "LANE_ID", "RosterNameLane", "SCHEMA"]


if __name__ == "__main__":
    raise SystemExit(_main())
