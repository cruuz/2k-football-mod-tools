"""NFL Street (PlayStation 2)'s portrait, logo, field, playfield, presentation and menu art.

Six pages' worth of ``MMAP`` textures, one class each, every one an instance of
the shared :class:`mod_editor.games._lanes.terf_art.TerfArtWriteLane`.  What is
here is which containers each page is about and what the disc says about them;
the walking, the decode, the checked import, the PCSX2 identity, the export and
the write-back are the base's and are the same code all six run.

Every row is ``offline-writer-proved``: an edited PNG goes back into a NEW disc
image, every preload-cache copy the edit disturbs is rewritten from the
container's own new bytes, an independent verifier re-reads the result, and
**no rebuilt NFL Street container has been booted**.

What each page is about, measured [M]
-------------------------------------

``UIS_PORT.DAT`` 549 portraits · ``UIS_TMLO.DAT`` 102 logos ·
``UIS_CRTM.DAT`` 56 + ``UIS_FSEL.DAT`` 41 field art · ``ENVRNMT.DAT`` 15 +
``OBJMODEL.DAT`` 2 + ``STATMOD.DAT`` 19 playfield · ``LOADDATA.DAT`` 12 +
``UIS_INGM.DAT`` 18 + ``UIS_MOVI.DAT`` 22 + ``UIS_ONRE.DAT`` 103 presentation ·
nine ``UIS_*`` menu containers, 103 members between them.  1,050 ``MMAP``
members in all, against 1,735 in the kit container the Uniforms page owns [M].

**Identity coverage.**  Six frames have been captured on this disc -- the Select
Field screen and five frames of gameplay -- and pairing them against the disc
named **33 textures** in 8 of the 22 containers this module indexes [M], with
the number of frames that drew one beside each:

===================  =========  =======  ======================
container            indexed    named    frames that drew one
===================  =========  =======  ======================
``UIS_INGM.DAT``            18       10                       4
``ENVRNMT.DAT``             15        5                       6
``IGDATA.DAT``               8        5                       1
``UIS_BUTT.DAT``            13        4                       3
``STATMOD.DAT``             18        3                       5
``UIS_COMN.DAT``            16        3                       5
``UIS_TMLO.DAT``           102        2                       3
``PLATEX.DAT``               1        1                       5
===================  =========  =======  ======================

The fourteen containers not in that table were drawn by **no captured frame**:
``UIS_PORT.DAT`` (549 indexed), ``UIS_ONRE.DAT`` (103), ``UIS_CRTM.DAT`` (56),
``UIS_FSEL.DAT`` (41), ``UIS_BGPL.DAT`` (25), ``UIS_MOVI.DAT`` (22),
``UIS_CHAL.DAT`` (19), ``LOADDATA.DAT`` (12), ``UIS_FRON.DAT`` (11),
``UIS_GABR.DAT`` (11), ``UIS_CTRL.DAT`` (4), ``UIS_BGMP.DAT`` (3),
``OBJMODEL.DAT`` (1) and ``UIS_CWIN.DAT`` (1) [M].  **That column is the capture
list**: a frame of the roster screen would reach ``UIS_PORT.DAT``'s 549
portraits, which is by far the largest unconfirmed block on the disc.

Every texture not in the 33 is **derived**, and :meth:`identity_note` says which
of the two it is on each one.  1,074 of the 1,170 distinct dumped files pair with
nothing this module indexes, and 9 more pair on RGB but not on alpha -- the class
that is confirmable but never derivable, because the game pads their palette at
run time [A].  The unmatched bulk is what a disc whose kit art is direct-colour
looks like from the dump side: see :mod:`.texture_lane` for the disc-side half of
the same fact.

Run one without a window::

    python3 -m mod_editor.games.nflstreet1_ps2.art_pages --lane logos --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Optional, Sequence, Tuple

from mod_editor.games._lanes.terf_art import TerfArtWriteLane
from mod_editor.games.contract import Edit, Refusal

from . import containers
from .texture_lane import (
    DERIVATION_EVIDENCE,
    EXTRA_PSMS,
    GAME_TITLE,
    IDENTITY_DOCUMENT,
    IDENTITY_SCHEMA,
    IDENTITY_TOOL,
)

#: The sentence every one of these rows carries about what has not been proved.
NOT_BOOTED = (
    "No rebuilt NFL Street container has been booted. Every step here is proved against your "
    "own bytes offline -- the member decodes back to the pixels you gave it, the container "
    "follows the layout rules the retail discs follow, every preload cache copy of the "
    "container is rewritten with it, and every byte outside the declared ranges is "
    "unchanged -- but whether the game loads the result is not something this tool can "
    "find out."
)

PORTRAIT_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("UIS_PORT.DAT", "Player portraits",
     "549 stored MMAP members in a 2,876,800-byte container. The file names none of them, so the member index is the only structure it offers."),
)

LOGO_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("UIS_TMLO.DAT", "Team logos",
     "102 stored MMAP members. TEAM.TLGL runs 1..32 across the 32 team rows [M], so there are about three members per team here and which is which is not established."),
)

FIELD_ART_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("UIS_CRTM.DAT", "Create-a-team art",
     "56 stored MMAP members."),
    ("UIS_FSEL.DAT", "Field-select thumbnails",
     "41 stored MMAP members in a 3,389,280-byte container -- the eight field thumbnails the Select Field screen draws, and the art around them."),
)

STADIUM_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("ENVRNMT.DAT", "Playfield environments",
     "112 members: 48 SMF and 18 DMF models this module does not read, 15 MMAP textures it does, 8 TEXT banks the Menus page owns, and 15 empty."),
    ("OBJMODEL.DAT", "Props",
     "92 members: 70 DMF, 17 SKL1, 3 SMF and 2 MMAP. One of the two MMAP members is a palette-only entry carrying 30 alternate CLUTs for the other, which the decoder names as such rather than counting as a failure [M]."),
    ("STATMOD.DAT", "Static models and their skins",
     "105 members: 19 MMAP, 9 SMF, 2 DMF and 75 the reader does not classify. One member declares no palette and pixel layout 4, and is named rather than decoded [M]."),
)

PRESENTATION_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("LOADDATA.DAT", "Load screens",
     "12 MMAP members, 11 of them LZH1-packed."),
    ("UIS_INGM.DAT", "In-game overlay",
     "18 stored MMAP members."),
    ("UIS_MOVI.DAT", "Movie frames",
     "22 stored MMAP members."),
    ("UIS_ONRE.DAT", "Online results screens",
     "103 stored MMAP members."),
)

MENU_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("UIS_FRON.DAT", "Front end",
     "11 stored MMAP members."),
    ("UIS_BUTT.DAT", "Buttons",
     "13 stored MMAP members."),
    ("UIS_COMN.DAT", "Common panels",
     "16 stored MMAP members."),
    ("UIS_BGPL.DAT", "Player backgrounds",
     "25 stored MMAP members in a 6,582,240-byte container."),
    ("UIS_BGMP.DAT", "Map backgrounds",
     "3 stored MMAP members."),
    ("UIS_CHAL.DAT", "Challenge screens",
     "19 stored MMAP members."),
    ("UIS_GABR.DAT", "Game-break panels",
     "11 stored MMAP members."),
    ("UIS_CTRL.DAT", "Controller diagrams",
     "4 stored MMAP members."),
    ("UIS_CWIN.DAT", "Create window",
     "1 stored MMAP member."),
)

#: Every container on the disc whose members carry ``MMAP`` textures, for the
#: All Textures page's census.  These twenty-one containers hold 1,050 MMAP members between them, of which 1,048 decode here; the rest of the disc's 2,785 MMAP members; the other 1,735 are the kits, which have their own page [M].
ALL_ART_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    PORTRAIT_CONTAINERS + LOGO_CONTAINERS + FIELD_ART_CONTAINERS
    + STADIUM_CONTAINERS + PRESENTATION_CONTAINERS + MENU_CONTAINERS)


class _StreetArtLane(TerfArtWriteLane):
    """What all six of this disc's art rows share."""

    discs = containers
    classification = "offline-writer-proved"
    game_title = GAME_TITLE
    identity_document = IDENTITY_DOCUMENT
    identity_schema = IDENTITY_SCHEMA
    identity_tool = IDENTITY_TOOL
    derivation_evidence = DERIVATION_EVIDENCE
    extra_psms = EXTRA_PSMS
    max_targets = 4000
    max_targets_per_container = 800
    catalog_schema = "nflstreet1_ps2_art_census/v1"
    NOT_BOOTED = NOT_BOOTED


class PortraitArtLane(_StreetArtLane):
    """The player portraits the front end draws."""

    lane_id = "rosters.portrait_art"
    capability_id = "nflstreet1ps2.rosters.portrait_art"
    surface = "portraits_faces"
    page = "rosters"
    title = "Player portrait art"
    art_containers = PORTRAIT_CONTAINERS
    recipe_schema = "nflstreet1_ps2_portrait_art_recipe/v1"
    write_schema = "nflstreet1_ps2_portrait_art_write/v1"
    validators = ("tools/validate_nflstreet1_ps2_art_pages.sh",
                  "tools/validate_nflstreet1_ps2_art_pages.bat")


class LogoArtLane(_StreetArtLane):
    """The team logos the ``TEAM`` row's ``TLGL`` id names."""

    lane_id = "identity.logo_art"
    capability_id = "nflstreet1ps2.identity.logo_art"
    surface = "logos_cards"
    page = "identity"
    title = "Team logo art"
    art_containers = LOGO_CONTAINERS
    recipe_schema = "nflstreet1_ps2_logo_art_recipe/v1"
    write_schema = "nflstreet1_ps2_logo_art_write/v1"
    validators = ("tools/validate_nflstreet1_ps2_art_pages.sh",
                  "tools/validate_nflstreet1_ps2_art_pages.bat")


class FieldArtLane(_StreetArtLane):
    """The create-a-team art and the field-select thumbnails."""

    lane_id = "field_art.create_team_art"
    capability_id = "nflstreet1ps2.field_art.create_team_art"
    surface = "stadiums_fields"
    page = "field_art"
    title = "Field and create-team art"
    art_containers = FIELD_ART_CONTAINERS
    recipe_schema = "nflstreet1_ps2_field_art_recipe/v1"
    write_schema = "nflstreet1_ps2_field_art_write/v1"
    validators = ("tools/validate_nflstreet1_ps2_art_pages.sh",
                  "tools/validate_nflstreet1_ps2_art_pages.bat")


class PlayfieldArtLane(_StreetArtLane):
    """The street playfields and the props that stand on them.

    NFL Street has no stadiums: it has street courts, and their geometry is
    ``SMF``/``DMF`` models this module does not read.  What this page reaches is
    the textures those models are skinned with.
    """

    lane_id = "stadiums.playfield_art"
    capability_id = "nflstreet1ps2.stadiums.playfield_art"
    surface = "stadiums_fields"
    page = "stadiums"
    title = "Playfield and prop textures"
    art_containers = STADIUM_CONTAINERS
    recipe_schema = "nflstreet1_ps2_playfield_art_recipe/v1"
    write_schema = "nflstreet1_ps2_playfield_art_write/v1"
    validators = ("tools/validate_nflstreet1_ps2_art_pages.sh",
                  "tools/validate_nflstreet1_ps2_art_pages.bat")


class PresentationArtLane(_StreetArtLane):
    """The load screens, the in-game overlay and the results screens."""

    lane_id = "presentation.screen_art"
    capability_id = "nflstreet1ps2.presentation.screen_art"
    surface = "scorebug_presentation"
    page = "presentation"
    title = "Load screens and in-game overlay"
    art_containers = PRESENTATION_CONTAINERS
    recipe_schema = "nflstreet1_ps2_presentation_art_recipe/v1"
    write_schema = "nflstreet1_ps2_presentation_art_write/v1"
    validators = ("tools/validate_nflstreet1_ps2_art_pages.sh",
                  "tools/validate_nflstreet1_ps2_art_pages.bat")


class MenuArtLane(_StreetArtLane):
    """The front-end backgrounds, buttons and panels."""

    lane_id = "menus.front_end_art"
    capability_id = "nflstreet1ps2.menus.front_end_art"
    surface = "menus"
    page = "menus"
    title = "Front-end and menu art"
    art_containers = MENU_CONTAINERS
    recipe_schema = "nflstreet1_ps2_menu_art_recipe/v1"
    write_schema = "nflstreet1_ps2_menu_art_write/v1"
    validators = ("tools/validate_nflstreet1_ps2_art_pages.sh",
                  "tools/validate_nflstreet1_ps2_art_pages.bat")


class AllTextureLane(_StreetArtLane):
    """Every ``MMAP`` texture on the disc that is not a kit, in one census.

    The kit container has its own page; this is the catch-all the contract asks
    for, so a texture is reachable somewhere even when no page is about it.
    """

    lane_id = "textures.mmap_census"
    capability_id = "nflstreet1ps2.textures.mmap_census"
    surface = "textures"
    page = "textures"
    title = "Every other MMAP texture on the disc"
    art_containers = ALL_ART_CONTAINERS
    max_targets = 4000
    max_targets_per_container = 400
    recipe_schema = "nflstreet1_ps2_all_texture_recipe/v1"
    write_schema = "nflstreet1_ps2_all_texture_write/v1"
    validators = ("tools/validate_nflstreet1_ps2_art_pages.sh",
                  "tools/validate_nflstreet1_ps2_art_pages.bat")


LANES = {
    "portraits": PortraitArtLane,
    "logos": LogoArtLane,
    "field": FieldArtLane,
    "playfields": PlayfieldArtLane,
    "presentation": PresentationArtLane,
    "menus": MenuArtLane,
    "textures": AllTextureLane,
}


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.nflstreet1_ps2.art_pages --lane logos --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.nflstreet1_ps2.art_pages",
        description="Catalogue and export one of this disc's art pages.",
    )
    parser.add_argument("--lane", default="logos", choices=sorted(LANES),
                        help="which art page to run")
    parser.add_argument("--source", help="the user's own SLUS-20841 disc image")
    parser.add_argument("--selftest", action="store_true",
                        help="run every art page on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if arguments.selftest:
            import tempfile

            failures = 0
            for name in sorted(LANES):
                lane = LANES[name]()
                with tempfile.TemporaryDirectory() as room:
                    source = lane.synthetic_source(Path(room))
                    catalogue = lane.build_catalogue(source)
                    edits = lane.conformance_edits(catalogue)
                    destination = Path(room) / "out.iso"
                    receipt = lane.build(source, destination,
                                         lane.compose_recipe(edits), catalogue)
                    verdict = lane.verify(source, destination, receipt)
                    print(f"  {name:12s} targets={len(catalogue.targets):5d} "
                          f"verify={'PASS' if verdict.passed else 'FAIL'}")
                    failures += 0 if verdict.passed else 1
            print(f"ART_PAGES lanes={len(LANES)} failures={failures}")
            return 0 if failures == 0 else 1
        if not arguments.source:
            parser.error("give --source DISC.iso, or --selftest")
        lane = LANES[arguments.lane]()
        catalogue = lane.build_catalogue(
            Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    print("ART lane=%s members=%d images=%d decodable=%d listed=%d"
          % (arguments.lane, document["members_read"], document["images_seen"],
             document["images_decodable"], document["targets_listed"]))
    return 0


__all__ = ["ALL_ART_CONTAINERS", "AllTextureLane", "FIELD_ART_CONTAINERS",
           "FieldArtLane", "LANES", "LOGO_CONTAINERS", "LogoArtLane",
           "MENU_CONTAINERS", "MenuArtLane", "NOT_BOOTED",
           "PORTRAIT_CONTAINERS", "PRESENTATION_CONTAINERS", "PlayfieldArtLane",
           "PortraitArtLane", "PresentationArtLane", "STADIUM_CONTAINERS"]


if __name__ == "__main__":
    raise SystemExit(_main())
