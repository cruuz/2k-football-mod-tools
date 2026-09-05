"""Madden NFL 09 (PlayStation 2) on the game-module contract, working off the disc.

The second game on the Game Studio shell, and the first one written *for* it:
there is no window in this package at all.  ``studio_window`` points at the
core shell, which draws the same fourteen pages every studio has; a lane
reaches its page by being a lane, and a page with no lane says why in one
sentence from ``game.json``'s ``page_notes``.

What is on the contract today, and what each rung rests on:

* **identity** -- ISO9660 volume, ``SYSTEM.CNF``'s boot file, and the boot ELF
  digest, through :class:`~.disc_identity.Madden09DiscIdentifier`.  Two images
  are named: the retail USA disc and the community's *Deluxe* rebuild.  A disc
  that boots another serial is refused with a sentence.
* **inventory** (:mod:`.inventory_lane`, ``read-only-mapped``) -- every
  ``/DATA`` container, its chunk chain, its members, their codecs, and what
  their decompressed bytes hold.  This is the rung every other lane stands on,
  and it is finished: the container format is fully decoded
  (``docs/product/EA_TERF_FORMAT.md``).
* **uniform art** (:mod:`.uniform_art`) -- the ``MMAP`` textures of
  ``UNIFORMS.DAT``, ``PLYRFACE.DAT``, ``COACFACE.DAT`` and ``TATTOOS.DAT``.
  Two rows, because they earn two different rungs: an ``extract-only``
  exporter, and an ``offline-writer-proved`` writer that puts an edited PNG
  back into a **new** disc image.
* **team data** (:mod:`.team_data`, ``read-only-mapped``) -- the EA TDB
  databases inside ``DB_TEAMS.DAT``, ``TEMPLATE.DAT`` and ``GAMEDATA.DAT``,
  and the bare ``STRMDATA.DB``, catalogued table by table.  **Readers only.**
* **text** (:mod:`.text_lane`, ``read-only-mapped``) -- the disc's ``TEXT``
  banks, counted and measured; the strings are read from the user's own image
  on demand and never stored.
* **team identity** (:mod:`.identity_lane`) -- the 32 NFL teams' names,
  abbreviations and two colours, written into every copy of the ``TEAM`` row
  the disc's own databases agree on: the ``DB_TEAMS.DAT`` member and the
  matching row of the bare ``STRMDATA.DB``.
* **audio** (:mod:`.audio_lane`) -- two lanes over the disc's 34,034 ``SCHl``
  streams and 301 ``BNKl`` banks.  The streams lane is the module's **first
  writer**: 295 of the streams are EA-XA ADPCM and a replacement WAV is
  re-encoded into the bytes the sound already occupies, with the preload
  caches' copies kept in step and an independent verifier that re-decodes the
  result.  ``offline-writer-proved``: nothing has been booted.  The banks lane
  is ``extract-only``.
* **executable patches** (:mod:`.code_patches`, ``unknown``) -- the whole
  pnach pipeline, proved on a synthetic ELF, with **no translation mapped**.
  The studio draws no editor for it; its page states the classification and
  the registry's reason.

**One writer, and what it does not claim.**  The uniform-art writer produces a
new disc image and is filed ``offline-writer-proved``: the member decodes back
to the pixels it was given, the container keeps the layout rules the retail
discs follow, every untouched member is byte-identical, and an independent
verifier re-derives every changed byte of the image from the two files.  **No
rebuilt Madden 09 container has ever been booted**, so nothing here says the
game loads the result, and no other lane in this module writes anything at all.
``docs/product/MADDEN09_PS2_MODULE.md`` carries both halves.
**One writer, and it has not been booted.**  The audio streams lane writes a
new disc image; every other lane here reads.  Its rung is
``offline-writer-proved`` and stops there on purpose: a destination is built,
an independent verifier re-parses it, and no rebuilt Madden 09 image has ever
been run in an emulator or on hardware.  The art and text lanes still write
nothing at all, because the container writer cannot shrink an ``LZH1`` member
back down -- no encoder for that codec exists anywhere public -- and the audio
containers are the ones that store their members uncompressed.  Both facts are
in ``docs/product/MADDEN09_PS2_MODULE.md`` and
``docs/product/MADDEN09_PS2_AUDIO.md``, and neither is worked around here.

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
from .audio_lane import AudioBanksLane, AudioStreamsLane
from .code_patches import Madden09CodePatchLane
from .disc_identity import Madden09DiscIdentifier
from .identity_lane import IdentityLane
from .inventory_lane import InventoryLane
from .team_data import TeamDataLane
from .text_lane import TextLane
from .uniform_art import UniformArtLane, UniformDiscArtWriteLane

HERE = Path(__file__).resolve().parent
GAME_ID = "madden09_ps2"
SERIAL = containers.SERIAL

IDENTITY = GameIdentity(
    game_id=GAME_ID,
    title="Madden NFL 09 (USA, PlayStation 2)",
    platform="PlayStation 2",
    serials=(SERIAL,),
    # Both boot ELFs this module recognises: the retail executable and the
    # community Deluxe disc's patched one.  Digests only.
    executable_sha256=(
        containers.RETAIL_BOOT_ELF_SHA256,
        containers.DELUXE_BOOT_ELF_SHA256,
    ),
    content_sha256=(
        containers.RETAIL_IMAGE_SHA256,
        containers.DELUXE_IMAGE_SHA256,
    ),
)


def _studio(parent: Any = None, **context: Any) -> Any:
    """This module's studio: the core shell, hosting the lanes above.

    Qt is imported inside the function, as the contract requires of a game
    package.  There is no hand-written window here and there does not need to
    be: the shell draws every page, and a lane reaches its page by being a
    lane.
    """

    from mod_editor.games.studio_qt import GameStudioDialog

    source = context.get("source")
    return GameStudioDialog(GAME, parent=parent, initial_source=Path(source) if source else None)


WINDOWS = (
    WindowSpec(
        window_id="studio",
        menu_label="Studio…",
        tooltip="Open the Madden NFL 09 (PlayStation 2) studio: every page, and the lanes "
                "this module has so far.",
        flag="madden09-ps2-studio",
        factory=_studio,
    ),
)


def _registered(capability_id: str) -> bool:
    """Whether the registry fragment beside this file carries ``capability_id``.

    A lane joins ``GAME.lanes`` when its row exists, so a lane whose row is
    still a proposal is reachable by import and covered by its own tests
    without the module claiming it as a capability.
    """

    try:
        document = json.loads((HERE / "registry.fragment.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(row.get("id") == capability_id for row in document.get("capabilities", []))


_CANDIDATES = (
    InventoryLane(),
    UniformArtLane(),
    UniformDiscArtWriteLane(),
    TeamDataLane(),
    TextLane(),
    IdentityLane(),
    AudioStreamsLane(),
    AudioBanksLane(),
    Madden09CodePatchLane(IDENTITY),
)
LANES = tuple(lane for lane in _CANDIDATES if _registered(lane.capability_id))

GAME = GameModule(
    contract=CONTRACT_SCHEMA,
    identity=IDENTITY,
    identifier=Madden09DiscIdentifier(IDENTITY),
    lanes=LANES,
    windows=WINDOWS,
    manifest=load_manifest(HERE),
    package=__name__,
    studio_window="studio",
)

__all__ = ["GAME", "GAME_ID", "IDENTITY", "LANES", "SERIAL", "WINDOWS"]
