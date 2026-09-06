"""NFL Blitz 2002 (PlayStation 2) on the game-module contract, working off the disc.

The first Midway title on the Game Studio shell, and the first whose whole game
is one ZIP: ``/DATA/BASSETS.ZIP`` holds 2,426 stored members and
``/DATA/BASSETS.ZIH`` is Midway's pre-built index of them, carrying the same
names, sizes, offsets and CRC-32s [M].  Two shared readers open all of it --
:mod:`mod_editor.games._formats.blitz_zip` for the pair and
:mod:`~mod_editor.games._formats.rw_txd` for the 761 RenderWare texture
dictionaries inside it -- and this package is the game-specific half: which
member feeds which page, and the writers.

What is on the contract:

* **identity** -- ISO9660 volume, ``SYSTEM.CNF`` and the boot ELF digest,
  through the shared PS2 identifier.
* **four writers** -- the crowd tables, ``field.tab``, the trivia banks
  (:mod:`.text_lane`) and the roster's player names (:mod:`.roster_lane`), each
  a line or a name field rewritten inside the span it already owns, the member
  put back where it lies, and its CRC-32 rewritten in **all three** places the
  disc keeps it: the local file header, the central directory and the ``.ZIH``
  index.
* **two export lanes** (:mod:`.texture_lane`) -- the team dictionaries and every
  other dictionary, 8-bit and 32-bit rasters decoded to PNG with derived PCSX2
  identities; the 4-bit ones listed with the measured reason nothing is drawn.
* **two inventories** -- every texture dictionary on the disc
  (:mod:`.texture_lane`), and the camera paths, ``WIFF`` containers and
  RenderWare clumps (:mod:`.camera_lane`).

Every writer is ``offline-writer-proved`` and no more: no rebuilt image has been
booted.  ``docs/product/NFLBLITZ2002_PS2_MODULE.md`` carries both halves.
Retail-free: names, offsets, lengths, counts and digests only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mod_editor.games.contract import (
    CONTRACT_SCHEMA,
    GameIdentity,
    GameModule,
    WindowSpec,
    load_manifest,
)

from . import containers
from .camera_lane import LANE as CONTAINER_LANE
from .disc_identity import Ps2DiscIdentifier
from .roster_lane import LANE as ROSTER_LANE
from .text_lane import CROWD_LANE, FIELD_LANE, TRIVIA_LANE
from .texture_lane import INVENTORY_LANE, SCREEN_LANE, TEAM_LANE

HERE = Path(__file__).resolve().parent
GAME_ID = containers.GAME_ID
SERIAL = containers.SERIAL

IDENTITY = GameIdentity(
    game_id=GAME_ID,
    title=containers.TITLE,
    platform="PlayStation 2",
    serials=(SERIAL,),
    executable_sha256=(containers.RETAIL_BOOT_ELF_SHA256,),
    content_sha256=(containers.RETAIL_IMAGE_SHA256,),
)


def _studio(parent: Any = None, **context: Any) -> Any:
    """This module's studio: the core shell, hosting the lanes above."""

    from mod_editor.games.studio_qt import GameStudioDialog

    source = context.get("source")
    return GameStudioDialog(GAME, parent=parent,
                            initial_source=Path(source) if source else None)


WINDOWS = (
    WindowSpec(
        window_id="studio",
        menu_label="Studio…",
        tooltip="Open the NFL Blitz 2002 (PlayStation 2) studio: every page, and the lanes "
                "this module has.",
        flag="nflblitz2002-ps2-studio",
        factory=_studio,
    ),
)


def _registered(capability_id: str) -> bool:
    """Whether the registry fragment beside this file carries ``capability_id``."""

    try:
        document = json.loads((HERE / "registry.fragment.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(row.get("id") == capability_id for row in document.get("capabilities", []))


#: The module's own lane order, which is the order a staged build runs in: the
#: text and roster writers first, then the art exports, then the inventories.
_CANDIDATES = (
    ROSTER_LANE,
    CROWD_LANE,
    FIELD_LANE,
    TRIVIA_LANE,
    TEAM_LANE,
    SCREEN_LANE,
    CONTAINER_LANE,
    INVENTORY_LANE,
)
LANES = tuple(lane for lane in _CANDIDATES if _registered(lane.capability_id))

GAME = GameModule(
    contract=CONTRACT_SCHEMA,
    identity=IDENTITY,
    identifier=Ps2DiscIdentifier(IDENTITY),
    lanes=LANES,
    windows=WINDOWS,
    manifest=load_manifest(HERE),
    package=__name__,
    studio_window="studio",
)

__all__ = ["GAME", "GAME_ID", "IDENTITY", "LANES", "SERIAL", "WINDOWS"]
