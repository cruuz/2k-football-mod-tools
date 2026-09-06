"""``CPTH`` camera paths, and the two container heads beside them that stay unread.

The disc carries 85 ``.cap`` members on the 2002 disc and 88 on the 2003 disc,
each beginning ``CPTH``.  The owner's scoping study names the family ``HTPC``,
which is that tag read as a little-endian word; the bytes are ``CPTH`` and this
module matches the bytes [M].  The header's own arithmetic is exact [M]::

    +0  char[4] "CPTH"     +8  u32 records      16 + records * 32 == the member
    +4  u32 (7 / 1 / 5 / 3) +12 u32 0            85 of 85 and 88 of 88

Word 1 takes four values across the discs -- 7 on 43 (46) members, 1 on 20, 5 on
19 and 3 on 3 -- and is reported unnamed [M].  A record is 32 bytes of what read
as IEEE floats; nothing here says which of them is a position and which a time,
so the lane lists a path's record count and stride and offers no editor.

The same page names the two container families beside it whose heads are all
that is read [M]: ``WIFF`` (190 and 209 members, a big-endian RIFF whose declared
size + 8 is the member on every one) and ``.dff`` (1,272 and 1,436 RenderWare
clump streams, whose top-level walk consumes the member on 1,043 of 1,272 and
1,167 of 1,436).  Reading a clump's geometry is a different reader and is not
done here.

The lane is :class:`mod_editor.games._lanes.blitz_zip_lanes.ContainerInventoryLane`;
this file is the row it takes on **this** disc.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from mod_editor.games._lanes import blitz_zip_lanes
from mod_editor.games._lanes.blitz_zip_lanes import (
    CONTAINER_INVENTORY_REFUSAL,
    ContainerInventoryLane,
    camera_lane_main,
    walk_clump,
)

from . import containers

SCHEMA = "nflblitz2003_ps2_camera_paths/v1"
GAME_ID = containers.GAME_ID
LANE_ID = "presentation.camera_paths"
CAPABILITY_ID = f"{GAME_ID.replace('_', '')}.{LANE_ID}"

REFUSAL = CONTAINER_INVENTORY_REFUSAL


def read_camera(payload: bytes, name: str) -> Dict[str, Any]:
    """This disc's ``CPTH`` header reader; the behaviour is shared."""

    return blitz_zip_lanes.read_camera(containers, payload, name)


def read_wiff(head: bytes, size: int, name: str) -> Dict[str, Any]:
    """This disc's ``WIFF`` head reader; the behaviour is shared."""

    return blitz_zip_lanes.read_wiff(containers, head, size, name)


LANE = ContainerInventoryLane(containers, SCHEMA, LANE_ID)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    return camera_lane_main(containers, LANE, "NFL Blitz 2003 (PS2)", argv)


__all__ = ["CAPABILITY_ID", "ContainerInventoryLane", "LANE", "LANE_ID", "REFUSAL", "SCHEMA",
           "read_camera", "read_wiff", "walk_clump"]


if __name__ == "__main__":
    raise SystemExit(_main())
