"""MVP Baseball 2005 (PlayStation 2) on the game-module contract, working off the disc.

The first EA ``BIG`` title on the Game Studio shell: no ``TERF`` container, no
``TDB`` database, every asset inside one of 211 EA ``BIG`` archives and every
texture an ``SHPS`` bank [M].  The shared readers under
``mod_editor/games/_formats`` open all of it -- ``ea_big`` (with the RefPack
encoder and the bounded slot writer this module needed), ``ea_shps``,
``ea_schl`` and the new ``ea_csv_db`` -- and this package is the game-specific
half: which archive feeds which page, and the writers.

What is on the contract:

* **identity** -- ISO9660 volume, ``SYSTEM.CNF`` and the boot ELF digest,
  through :class:`~.disc_identity.Mvp05DiscIdentifier`.
* **three CSV table writers** (:mod:`.database_lane`) -- the 18 roster tables,
  the four team tables, the tuning archives -- each cell edit re-packed into
  the slot its entry already owns.
* **the UI strings writer** (:mod:`.loch_lane`) -- 7,977 ``LOCH`` strings,
  replaced inside their own span.
* **four art writers and three art inventories** (:mod:`.art_lane`) -- 8-bit
  images exported and written back with derived PCSX2 identities, including
  ``MODELS.BIG``'s 21,767 writable kit, lettering and equipment textures -- the
  art a player actually wears; the code-``0x0e`` archives (the uniform preview
  swatches, portraits, field art) listed with the measured reason nothing is
  drawn.
* **audio** (:mod:`.audio_lane`) -- every ``SCHl`` stream played and exported,
  the bare stream files replaced, MicroTalk refused by name; the two ``BNKl``
  banks exported.
* **the bank inventory** (:mod:`.inventory_lane`) -- every bank on the disc.

Every writer is ``offline-writer-proved`` and no more: no rebuilt image has
been booted.  ``docs/product/MVP05_PS2_MODULE.md`` carries both halves.
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
from .art_lane import (
    FACE_LANE, FIELD_ART_LANE, KIT_LANE, MENU_LANE, PRESENTATION_LANE, STADIUM_LANE, UNIFORM_LANE,
)
from .audio_lane import BANKS_LANE, STREAMS_LANE
from .database_lane import IDENTITY_LANE, ROSTER_LANE, TUNING_LANE
from .disc_identity import Mvp05DiscIdentifier
from .inventory_lane import LANE as INVENTORY_LANE
from .loch_lane import LANE as STRINGS_LANE

HERE = Path(__file__).resolve().parent
GAME_ID = "mvp05_ps2"
SERIAL = containers.SERIAL

IDENTITY = GameIdentity(
    game_id=GAME_ID,
    title="MVP Baseball 2005 (USA, PlayStation 2)",
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
        tooltip="Open the MVP Baseball 2005 (PlayStation 2) studio: every page, and the lanes "
                "this module has.",
        flag="mvp05-ps2-studio",
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


#: The module's own lane order, which is the order a staged build runs in:
#: tables and strings first, then art, then audio, then the inventories.
_CANDIDATES = (
    ROSTER_LANE,
    IDENTITY_LANE,
    TUNING_LANE,
    STRINGS_LANE,
    STADIUM_LANE,
    PRESENTATION_LANE,
    MENU_LANE,
    STREAMS_LANE,
    BANKS_LANE,
    KIT_LANE,
    UNIFORM_LANE,
    FACE_LANE,
    FIELD_ART_LANE,
    INVENTORY_LANE,
)
LANES = tuple(lane for lane in _CANDIDATES if _registered(lane.capability_id))

GAME = GameModule(
    contract=CONTRACT_SCHEMA,
    identity=IDENTITY,
    identifier=Mvp05DiscIdentifier(IDENTITY),
    lanes=LANES,
    windows=WINDOWS,
    manifest=load_manifest(HERE),
    package=__name__,
    studio_window="studio",
)

__all__ = ["GAME", "GAME_ID", "IDENTITY", "LANES", "SERIAL", "WINDOWS"]
