"""NFL Street 3 (USA, PlayStation 2) on the game-module contract, working off the disc.

The eighth game on the Game Studio shell, and the second written entirely out of
shared lane bases: there is no window in this package and no lane shape in it
either.  ``studio_window`` points at the core shell, which draws the same
fourteen pages every studio has; a lane reaches its page by being a lane, and a
page with no lane says why in one sentence from ``game.json``'s ``page_notes``.

NFL Street 3 is the same EA container family as NFL Street, three years
later, and **not a re-skin of it**.  Every container format is shared and
every shared reader opens both with nothing changed -- **80 of 80
containers, 27,178 of 27,178 members, 47 of 47 databases plus one bare
database, 1,038 of 1,038 checksum slots** [M] -- and no record schema
survives except one.  ``PLAY`` goes from 65 fields / 671 bits to **84 /
831**, with 64 names in common and **none at the same bit offset**;
``TEAM`` goes from 41 / 575 to **22 / 447**; ``DCHT`` -- 4 fields, 63
bits, same names, same widths, same offsets -- is the only table that
ports byte for byte [M].  ``docs/product/NFLSTREET3_PS2_MODULE.md`` §2 is
the census.

What is on the contract today:

* **identity** -- ISO9660 volume, ``SYSTEM.CNF``'s boot file and the boot ELF
  digest, through :class:`~.disc_identity.NflStreet3DiscIdentifier`.  One image is named;
  anything else is listed as ``unknown edition`` and nothing is claimed about it.
* **inventory** (:mod:`.inventory_lane`, ``read-only-mapped``) -- every ``/DATA``
  container, its chunk chain, its members, their codecs and what their
  decompressed bytes hold.
* **rosters** (:mod:`.database_lane`, ``offline-writer-proved``) -- the 449
  player rows in the 32 per-team databases inside ``DB_TEAMS.DAT``.
* **team identity** (:mod:`.identity_lane`, ``offline-writer-proved``) -- the 32
  ``TEAM`` rows: names, palette slots and logo id.
* **playbooks** (:mod:`.playbooks_lane`, ``offline-writer-proved``) -- the play
  library in ``IGDATA.DAT``.
* **text** (:mod:`.text_lane`, ``offline-writer-proved``) -- the 813 ``TEXT``
  string banks, rewritten in place.
* **kit textures** (:mod:`.texture_lane`, ``extract-only``) -- ``PLATEX.DAT``'s
  16,259 members catalogued and the 3 this decoder reads exported.  The
  other 16,256 declare pixel layout 5 or 6, direct colour with no CLUT, and
  nothing in this repository decodes them [M]; there is no kit writer for that
  reason and the page says so.
* **six art pages** (:mod:`.art_pages`, all ``offline-writer-proved``) --
  portraits, logos, field art, playfields, presentation and menus, plus the
  All Textures catch-all: 1,725 decodable ``MMAP`` surfaces between them [M].
* **audio** (:mod:`.audio_lane`) -- two ``extract-only`` lanes over 920 ``SCHl``
  streams and 197 ``BNKl`` banks.  27 streams and 691 bank sounds export;
  the other 893 streams are EA MicroTalk and are refused by name.

**Nothing here has been booted.**  Every writer is proved offline -- a
destination image, an independent verifier that re-reads it, and a conformance
harness that runs the whole path on a synthetic disc -- and no rebuilt
NFL Street 3 (PlayStation 2) container has been loaded in an emulator or on hardware.
``docs/product/NFLSTREET3_PS2_MODULE.md`` carries both halves.

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
from .art_pages import (
    AllTextureLane,
    FieldArtLane,
    LogoArtLane,
    MenuArtLane,
    PlayfieldArtLane,
    PortraitArtLane,
    PresentationArtLane,
)
from .audio_lane import AudioBanksLane, AudioStreamsLane
from .database_lane import DatabaseLane
from .disc_identity import NflStreet3DiscIdentifier
from .identity_lane import IdentityLane
from .inventory_lane import InventoryLane
from .playbooks_lane import PlaybooksLane
from .text_lane import TextLane
from .texture_lane import TextureLane

HERE = Path(__file__).resolve().parent
GAME_ID = "nflstreet3_ps2"
SERIAL = containers.SERIAL

IDENTITY = GameIdentity(
    game_id=GAME_ID,
    title="NFL Street 3 (USA, PlayStation 2)",
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
        tooltip="Open the NFL Street 3 (PlayStation 2) studio: every page, and the lanes this module "
                "has so far.",
        flag="nflstreet3-ps2-studio",
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
    DatabaseLane(),
    IdentityLane(),
    PlaybooksLane(),
    TextLane(),
    TextureLane(),
    PortraitArtLane(),
    LogoArtLane(),
    FieldArtLane(),
    PlayfieldArtLane(),
    PresentationArtLane(),
    MenuArtLane(),
    AllTextureLane(),
    AudioStreamsLane(),
    AudioBanksLane(),
)
LANES = tuple(lane for lane in _CANDIDATES if _registered(lane.capability_id))

GAME = GameModule(
    contract=CONTRACT_SCHEMA,
    identity=IDENTITY,
    identifier=NflStreet3DiscIdentifier(IDENTITY),
    lanes=LANES,
    windows=WINDOWS,
    manifest=load_manifest(HERE),
    package=__name__,
    studio_window="studio",
)

__all__ = ["GAME", "GAME_ID", "IDENTITY", "LANES", "SERIAL", "WINDOWS"]
