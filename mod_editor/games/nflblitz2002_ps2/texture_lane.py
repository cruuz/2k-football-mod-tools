"""The RenderWare texture dictionaries: one inventory and two export pages.

761 ``.rtd`` members on the 2002 disc and 840 on the 2003 disc, holding 10,420
and 11,828 PS2 native rasters [M].  :mod:`mod_editor.games._formats.rw_txd`
opens all of them and decodes the 8-bit and 32-bit ones; the 4-bit ones are
listed with the measured reason nothing is drawn, which the reader states once
and every row here quotes rather than restates.

===========================================================  ==========  ==========
                                                             2002        2003
===========================================================  ==========  ==========
dictionaries read                                            761 of 761  840 of 840
rasters read (equal to the count each dictionary declares)   10,420      11,828
rasters decoded to RGBA (8-bit and 32-bit)                   4,189       6,392
PCSX2 replacement identities derived (8-bit)                 4,166       6,365
rasters listed and not drawn (4-bit)                         6,231       5,436
refusals                                                     0           0
===========================================================  ==========  ==========

**Three rows.**  ``textures.dictionary_inventory`` walks every dictionary on the
disc and writes nothing.  ``uniforms.team_textures`` and ``menus.screen_textures``
are the same walker over two selections -- the 594 dictionaries whose name is
``<a team prefix>_...`` and the 167 that are not -- and each exports a decoded
raster as PNG (2,408 of 8,434 rasters and 1,781 of 1,986 respectively) [M].  The team prefixes are read
off the disc's own ``<two letters>_crowd.ini`` members, so the selection is a
measurement of the disc in hand and never a table to keep in step with it.
None of the three writes: putting a raster back means re-swizzling into the GS
memory image and rewriting the member at its own length, which this module can
do for 8-bit rasters and has **not** proved, so it is not offered
(``docs/product/RENDERWARE_TXD_FORMAT.md`` §8).

**Identities are derived, none confirmed.**  A name is what PCSX2's documented
rules compute from the raster's own bytes.  No texture dump of either Blitz disc
exists in this project, so nothing here says a replacement pack was found.

The lane is :class:`mod_editor.games._lanes.blitz_zip_lanes.TextureDictionaryLane`;
this file is the three rows it takes on **this** disc.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from mod_editor.games._lanes.blitz_zip_lanes import (
    INVENTORY_ONLY,
    NO_TEXTURE_WRITER,
    TextureDictionaryLane,
    texture_lane_main,
)

from . import containers

SCHEMA = "nflblitz2002_ps2_texture_dictionaries/v1"
GAME_ID = containers.GAME_ID

_NO_WRITER = NO_TEXTURE_WRITER
_INVENTORY_ONLY = INVENTORY_ONLY

INVENTORY_LANE = TextureDictionaryLane(
    containers, SCHEMA,
    "textures.dictionary_inventory", "textures", "textures",
    "Every RenderWare texture dictionary on the disc", "read-only-mapped",
    selection="all", refusal=_INVENTORY_ONLY, validator="textures", read_only=True)
TEAM_LANE = TextureDictionaryLane(
    containers, SCHEMA,
    "uniforms.team_textures", "uniforms", "uniforms",
    "The per-team texture dictionaries", "extract-only",
    selection="team", refusal=_NO_WRITER, validator="art", read_only=False)
SCREEN_LANE = TextureDictionaryLane(
    containers, SCHEMA,
    "menus.screen_textures", "menus", "menus",
    "Every texture dictionary that is not a team's", "extract-only",
    selection="other", refusal=_NO_WRITER, validator="art", read_only=False)

LANES = (INVENTORY_LANE, TEAM_LANE, SCREEN_LANE)
_BY_NAME: Dict[str, TextureDictionaryLane] = {"inventory": INVENTORY_LANE, "team": TEAM_LANE,
                                              "screens": SCREEN_LANE}


def _main(argv: Optional[Sequence[str]] = None) -> int:
    return texture_lane_main(containers, _BY_NAME, "NFL Blitz 2002 (PS2)", argv)


__all__ = ["INVENTORY_LANE", "LANES", "SCHEMA", "SCREEN_LANE", "TEAM_LANE",
           "TextureDictionaryLane"]


if __name__ == "__main__":
    raise SystemExit(_main())
