"""NCAA Football 09 (PlayStation 2) on the game-module contract, working off the disc.

The third game on the Game Studio shell and the second written *for* it: there
is no window in this package at all.  ``studio_window`` points at the core shell,
which draws the same fourteen pages every studio has; a lane reaches its page by
being a lane, and a page with no lane says why in one sentence from
``game.json``'s ``page_notes``.

NCAA Football 09 is a Tiburon disc of the same generation as Madden NFL 09 and
shares every *container* format with it -- ``TERF`` containers, ``LZH1`` and
``RLE1`` codecs, EA ``TDB`` databases with four CRC-32/MPEG-2 slots each,
``MMAP`` textures, ``SCHl`` streams, ``BNKl`` banks, ``QL01`` preload caches --
which is why the shared readers under ``mod_editor/games/_formats`` open it with
nothing changed: **85 of 85 containers, 30,391 of 30,391 members, 580 of 582
databases, 8,564 of 8,564 checksum slots** [M].

It does **not** share Madden's *schema*.  Its ``PLAY`` table has 86 fields where
Madden 09's has 110, and only 37 names are common; there is no ``PFNA`` and no
``PLNA``, because NCAA's players have no names.  Its rosters are 432 separate
per-team databases inside one container, not one table.  So every reader ports
and no Madden writer does; ``docs/product/NCAA09_PS2_SCHEMA.md`` is the census
that says which, field by field.

What is on the contract today:

* **identity** -- ISO9660 volume, ``SYSTEM.CNF``'s boot file and the boot ELF
  digest, through :class:`~.disc_identity.Ncaa09DiscIdentifier`.  One image is
  named; anything else is listed as ``unknown edition`` and nothing is claimed
  about it.
* **inventory** (:mod:`.inventory_lane`, ``read-only-mapped``) -- every ``/DATA``
  container, its chunk chain, its members, their codecs and what their
  decompressed bytes hold.
* **databases** (:mod:`.database_lane`, ``read-only-mapped``) -- all 582 EA TDB
  databases, table by table, with every field's name, type, width and offset,
  and the two the shared reader refuses recorded by their own sentence.
* **text** (:mod:`.text_lane`, ``read-only-mapped``) -- the 1,247 ``TEXT`` string
  banks, measured; the strings are read from the user's own image on demand and
  never stored.
* **textures** (:mod:`.texture_lane`, ``read-only-mapped``) -- the kit, equipment
  and face ``MMAP`` members by their own headers.  Not an exporter: the ``MMAP``
  pixel decoder lives in the Madden 09 package and a game never imports another
  game.
* **audio** (:mod:`.audio_lane`) -- two ``extract-only`` lanes over 8,021 ``SCHl``
  streams and 728 ``BNKl`` banks.  412 streams and 1,213 bank sounds export as
  WAV; the other 7,609 streams are EA MicroTalk and are refused by name.

**No lane here writes.**  Nothing has been booted, no NCAA Football 09 container
has been rebuilt by this module, and every refusal above names what would lift
its row.  ``docs/product/NCAA09_PS2_MODULE.md`` carries both halves.

Retail-free: this package carries names, offsets, lengths, counts and digests.
No member payload, no decoded pixel and no string from the game is in it.
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
from .art_pages import FaceArtLane, FieldArtLane, PresentationArtLane, StadiumArtLane
from .audio_lane import AudioBanksLane, AudioStreamsLane
from .database_lane import DatabaseLane
from .disc_identity import Ncaa09DiscIdentifier
from .identity_lane import IdentityLane
from .inventory_lane import InventoryLane
from .playbooks_lane import PlaybooksLane
from .saves_lane import DraftClassLane
from .text_lane import TextLane
from .texture_lane import TextureLane, UniformDiscArtWriteLane

HERE = Path(__file__).resolve().parent
GAME_ID = "ncaa09_ps2"
SERIAL = containers.SERIAL

IDENTITY = GameIdentity(
    game_id=GAME_ID,
    title="NCAA Football 09 (USA, PlayStation 2)",
    platform="PlayStation 2",
    serials=(SERIAL,),
    executable_sha256=(containers.RETAIL_BOOT_ELF_SHA256,),
    content_sha256=(containers.RETAIL_IMAGE_SHA256,),
)


def _studio(parent: Any = None, **context: Any) -> Any:
    """This module's studio: the core shell, hosting the lanes above.

    Qt is imported inside the function, as the contract requires of a game
    package.  There is no hand-written window here and there does not need to
    be: the shell draws every page, and a lane reaches its page by being a lane.
    """

    from mod_editor.games.studio_qt import GameStudioDialog

    source = context.get("source")
    return GameStudioDialog(GAME, parent=parent,
                            initial_source=Path(source) if source else None)


WINDOWS = (
    WindowSpec(
        window_id="studio",
        menu_label="Studio…",
        tooltip="Open the NCAA Football 09 (PlayStation 2) studio: every page, and the "
                "lanes this module has so far.",
        flag="ncaa09-ps2-studio",
        factory=_studio,
    ),
)


def _registered(capability_id: str) -> bool:
    """Whether the registry fragment beside this file carries ``capability_id``.

    A lane joins ``GAME.lanes`` when its row exists, so a lane whose row is still
    a proposal is reachable by import and covered by its own tests without the
    module claiming it as a capability.
    """

    try:
        document = json.loads((HERE / "registry.fragment.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(row.get("id") == capability_id for row in document.get("capabilities", []))


_CANDIDATES = (
    InventoryLane(),
    TextureLane(),
    UniformDiscArtWriteLane(),
    DatabaseLane(),
    FaceArtLane(),
    IdentityLane(),
    FieldArtLane(),
    StadiumArtLane(),
    PresentationArtLane(),
    TextLane(),
    AudioStreamsLane(),
    AudioBanksLane(),
    PlaybooksLane(),
    DraftClassLane(),
)
LANES = tuple(lane for lane in _CANDIDATES if _registered(lane.capability_id))

GAME = GameModule(
    contract=CONTRACT_SCHEMA,
    identity=IDENTITY,
    identifier=Ncaa09DiscIdentifier(IDENTITY),
    lanes=LANES,
    windows=WINDOWS,
    manifest=load_manifest(HERE),
    package=__name__,
    studio_window="studio",
)

__all__ = ["GAME", "GAME_ID", "IDENTITY", "LANES", "SERIAL", "WINDOWS"]
