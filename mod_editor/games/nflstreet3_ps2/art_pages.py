"""NFL Street 3 (PlayStation 2)'s portrait, logo, field, playfield, presentation and menu art.

Six pages' worth of ``MMAP`` textures, one class each, every one an instance of
the shared :class:`mod_editor.games._lanes.terf_art.TerfArtWriteLane`.  What is
here is which containers each page is about and what the disc says about them;
the walking, the decode, the checked import, the PCSX2 identity, the export and
the write-back are the base's and are the same code all six run.

Every row is ``offline-writer-proved``: an edited PNG goes back into a NEW disc
image, every preload-cache copy the edit disturbs is rewritten from the
container's own new bytes, an independent verifier re-reads the result, and
**no rebuilt NFL Street 3 container has been booted**.

What each page is about, measured [M]
-------------------------------------

``UIS_PORT.DAT`` 693 portraits · ``UIS_TMLO.DAT`` 173 +
``UIS_BNRT.DAT`` 173 logos and banners · ``UIS_CRTM.DAT`` 56 + ``UIS_FSEL.DAT`` 24 +
``UIS_FOOT.DAT`` 51 + ``UIS_CMAP.DAT`` 9 field art · ``ENVRNMT.DAT`` 8 +
``OBJMODEL.DAT`` 26 + ``STATMOD.DAT`` 79 playfield · ``LOADDATA.DAT`` 68 +
``UIS_INGM.DAT`` 30 + ``UIS_POST.DAT`` 90 + ``UIS_MOVI.DAT`` 22 +
``UIS_ONRE.DAT`` 103 presentation · eight menu containers, 114 members between
them.  1,727 ``MMAP`` members in all, against 16,259 in the kit container the
Uniforms page owns [M].

**Identity coverage.**  Five frames have been captured on this disc -- a loading
screen carrying the Audibles tip card, and gameplay -- and pairing them against
the disc named **28 textures** in 6 of the 25 containers this module indexes [M],
with the number of frames that drew one beside each:

===================  =========  =======  ======================
container            indexed    named    frames that drew one
===================  =========  =======  ======================
``UIS_INGM.DAT``            29       16                       5
``STATMOD.DAT``             78        5                       3
``UIS_BNRT.DAT``           173        2                       5
``UIS_BUTT.DAT``            13        2                       4
``UIS_TMLO.DAT``           173        2                       4
``PLATEX.DAT``               3        1                       3
===================  =========  =======  ======================

The nineteen containers not in that table were drawn by **no captured frame**:
``UIS_PORT.DAT`` (693 indexed), ``UIS_ONRE.DAT`` (103), ``UIS_POST.DAT`` (90),
``LOADDATA.DAT`` (68), ``UIS_CRTM.DAT`` (56), ``UIS_FOOT.DAT`` (51),
``UIS_FRON.DAT`` (36), ``OBJMODEL.DAT`` (26), ``UIS_FSEL.DAT`` (24),
``UIS_MOVI.DAT`` (22), ``UIS_CHAL.DAT`` (19), ``UIS_COMN.DAT`` (17),
``MINIGAMP.DAT`` (11), ``UIS_MPIC.DAT`` (11), ``UIS_CMAP.DAT`` (9),
``ENVRNMT.DAT`` (8), ``IGDATA.DAT`` (8), ``UIS_CTRL.DAT`` (5) and
``CHNL_IMG.DAT`` (2) [M].  **That column is the capture list**: a frame of the
roster screen would reach ``UIS_PORT.DAT``'s 693 portraits, and a post-game
screen ``UIS_POST.DAT``'s 90 -- together the two largest unconfirmed blocks on
the disc.

Every texture not in the 28 is **derived**, and :meth:`identity_note` says which
of the two it is on each one.  693 of the 807 distinct dumped files pair with
nothing this module indexes, and 33 more pair on RGB but not on alpha -- the
class that is confirmable but never derivable, because the game pads their
palette at run time [A].  Five frames confirm 28 textures of 1,725; that is the
number rather than a claim of coverage.

Run one without a window::

    python3 -m mod_editor.games.nflstreet3_ps2.art_pages --lane logos --source DISC.iso

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
    "No rebuilt NFL Street 3 container has been booted. Every step here is proved against your "
    "own bytes offline -- the member decodes back to the pixels you gave it, the container "
    "follows the layout rules the retail discs follow, every preload cache copy of the "
    "container is rewritten with it, and every byte outside the declared ranges is "
    "unchanged -- but whether the game loads the result is not something this tool can "
    "find out."
)

PORTRAIT_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("UIS_PORT.DAT", "Player portraits",
     "693 stored MMAP members in a 3,861,824-byte container -- 144 more than NFL Street's 549. The file names none of them."),
)

LOGO_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("UIS_TMLO.DAT", "Team logos",
     "173 stored MMAP members, against NFL Street's 102 [M]."),
    ("UIS_BNRT.DAT", "Team banners",
     "173 stored MMAP members. A container NFL Street does not have; the member count matching UIS_TMLO.DAT's exactly is a fact worth noticing and not one this module has explained."),
)

FIELD_ART_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("UIS_CRTM.DAT", "Create-a-team art",
     "56 stored MMAP members -- the same count and the same 293,488-byte container length as NFL Street's [M]."),
    ("UIS_FSEL.DAT", "Field-select thumbnails",
     "24 stored MMAP members."),
    ("UIS_FOOT.DAT", "Field markings",
     "51 stored MMAP members."),
    ("UIS_CMAP.DAT", "Challenge map",
     "9 stored MMAP members."),
)

STADIUM_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("ENVRNMT.DAT", "Playfield environments",
     "117 members: 71 SMF and 18 DMF models this module does not read, 9 TEXT banks the Menus page owns, 8 MMAP textures this page reaches, and 11 unclassified."),
    ("OBJMODEL.DAT", "Props",
     "171 members: 72 DMF, 45 SMF, 28 SKL1 and 26 MMAP -- thirteen times NFL Street's two MMAP members [M]."),
    ("STATMOD.DAT", "Static models and their skins",
     "181 members: 79 MMAP, 13 SMF, 2 DMF and 87 the reader does not classify. One member declares no palette and pixel layout 4, and is named rather than decoded [M]."),
)

PRESENTATION_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("LOADDATA.DAT", "Load screens",
     "68 MMAP members, 67 of them LZH1-packed, in a 10,537,856-byte container -- 5.7x NFL Street's 12."),
    ("UIS_INGM.DAT", "In-game overlay",
     "30 stored MMAP members. One is a 139x11 4-bit surface whose unpacked length does not satisfy the stride rule, and the decoder refuses it by name [M]."),
    ("UIS_POST.DAT", "Post-game screens",
     "90 stored MMAP members in a 12,083,808-byte container. A page NFL Street does not have."),
    ("UIS_MOVI.DAT", "Movie frames",
     "22 stored MMAP members."),
    ("UIS_ONRE.DAT", "Online results screens",
     "103 stored MMAP members."),
)

MENU_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    ("UIS_FRON.DAT", "Front end",
     "36 stored MMAP members, against NFL Street's 11 [M]."),
    ("UIS_BUTT.DAT", "Buttons",
     "13 stored MMAP members."),
    ("UIS_COMN.DAT", "Common panels",
     "17 stored MMAP members."),
    ("UIS_CHAL.DAT", "Challenge screens",
     "19 stored MMAP members."),
    ("UIS_CTRL.DAT", "Controller diagrams",
     "5 stored MMAP members."),
    ("UIS_MPIC.DAT", "Mini-game pictures",
     "11 stored MMAP members."),
    ("MINIGAMP.DAT", "Mini-game panels",
     "11 stored MMAP members."),
    ("CHNL_IMG.DAT", "Channel images",
     "2 stored MMAP members."),
)

#: Every container on the disc whose members carry ``MMAP`` textures, for the
#: All Textures page's census.  These twenty-four containers hold 1,727 MMAP members between them, of which 1,725 decode here; the rest of the disc's 17,986 MMAP members; the other 16,259 are the kits, which have their own page [M].
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
    catalog_schema = "nflstreet3_ps2_art_census/v1"
    NOT_BOOTED = NOT_BOOTED


class PortraitArtLane(_StreetArtLane):
    """The player portraits the front end draws."""

    lane_id = "rosters.portrait_art"
    capability_id = "nflstreet3ps2.rosters.portrait_art"
    surface = "portraits_faces"
    page = "rosters"
    title = "Player portrait art"
    art_containers = PORTRAIT_CONTAINERS
    recipe_schema = "nflstreet3_ps2_portrait_art_recipe/v1"
    write_schema = "nflstreet3_ps2_portrait_art_write/v1"
    validators = ("tools/validate_nflstreet3_ps2_art_pages.sh",
                  "tools/validate_nflstreet3_ps2_art_pages.bat")


class LogoArtLane(_StreetArtLane):
    """The team logos the ``TEAM`` row's ``TLGL`` id names."""

    lane_id = "identity.logo_art"
    capability_id = "nflstreet3ps2.identity.logo_art"
    surface = "logos_cards"
    page = "identity"
    title = "Team logo art"
    art_containers = LOGO_CONTAINERS
    recipe_schema = "nflstreet3_ps2_logo_art_recipe/v1"
    write_schema = "nflstreet3_ps2_logo_art_write/v1"
    validators = ("tools/validate_nflstreet3_ps2_art_pages.sh",
                  "tools/validate_nflstreet3_ps2_art_pages.bat")


class FieldArtLane(_StreetArtLane):
    """The create-a-team art and the field-select thumbnails."""

    lane_id = "field_art.create_team_art"
    capability_id = "nflstreet3ps2.field_art.create_team_art"
    surface = "stadiums_fields"
    page = "field_art"
    title = "Field and create-team art"
    art_containers = FIELD_ART_CONTAINERS
    recipe_schema = "nflstreet3_ps2_field_art_recipe/v1"
    write_schema = "nflstreet3_ps2_field_art_write/v1"
    validators = ("tools/validate_nflstreet3_ps2_art_pages.sh",
                  "tools/validate_nflstreet3_ps2_art_pages.bat")


class PlayfieldArtLane(_StreetArtLane):
    """The street playfields and the props that stand on them.

    NFL Street has no stadiums: it has street courts, and their geometry is
    ``SMF``/``DMF`` models this module does not read.  What this page reaches is
    the textures those models are skinned with.
    """

    lane_id = "stadiums.playfield_art"
    capability_id = "nflstreet3ps2.stadiums.playfield_art"
    surface = "stadiums_fields"
    page = "stadiums"
    title = "Playfield and prop textures"
    art_containers = STADIUM_CONTAINERS
    recipe_schema = "nflstreet3_ps2_playfield_art_recipe/v1"
    write_schema = "nflstreet3_ps2_playfield_art_write/v1"
    validators = ("tools/validate_nflstreet3_ps2_art_pages.sh",
                  "tools/validate_nflstreet3_ps2_art_pages.bat")


class PresentationArtLane(_StreetArtLane):
    """The load screens, the in-game overlay and the results screens."""

    lane_id = "presentation.screen_art"
    capability_id = "nflstreet3ps2.presentation.screen_art"
    surface = "scorebug_presentation"
    page = "presentation"
    title = "Load screens and in-game overlay"
    art_containers = PRESENTATION_CONTAINERS
    recipe_schema = "nflstreet3_ps2_presentation_art_recipe/v1"
    write_schema = "nflstreet3_ps2_presentation_art_write/v1"
    validators = ("tools/validate_nflstreet3_ps2_art_pages.sh",
                  "tools/validate_nflstreet3_ps2_art_pages.bat")


class MenuArtLane(_StreetArtLane):
    """The front-end backgrounds, buttons and panels."""

    lane_id = "menus.front_end_art"
    capability_id = "nflstreet3ps2.menus.front_end_art"
    surface = "menus"
    page = "menus"
    title = "Front-end and menu art"
    art_containers = MENU_CONTAINERS
    recipe_schema = "nflstreet3_ps2_menu_art_recipe/v1"
    write_schema = "nflstreet3_ps2_menu_art_write/v1"
    validators = ("tools/validate_nflstreet3_ps2_art_pages.sh",
                  "tools/validate_nflstreet3_ps2_art_pages.bat")


class AllTextureLane(_StreetArtLane):
    """Every ``MMAP`` texture on the disc that is not a kit, in one census.

    The kit container has its own page; this is the catch-all the contract asks
    for, so a texture is reachable somewhere even when no page is about it.
    """

    lane_id = "textures.mmap_census"
    capability_id = "nflstreet3ps2.textures.mmap_census"
    surface = "textures"
    page = "textures"
    title = "Every other MMAP texture on the disc"
    art_containers = ALL_ART_CONTAINERS
    max_targets = 6000
    max_targets_per_container = 400
    recipe_schema = "nflstreet3_ps2_all_texture_recipe/v1"
    write_schema = "nflstreet3_ps2_all_texture_write/v1"
    validators = ("tools/validate_nflstreet3_ps2_art_pages.sh",
                  "tools/validate_nflstreet3_ps2_art_pages.bat")


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
    """``python -m mod_editor.games.nflstreet3_ps2.art_pages --lane logos --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.nflstreet3_ps2.art_pages",
        description="Catalogue and export one of this disc's art pages.",
    )
    parser.add_argument("--lane", default="logos", choices=sorted(LANES),
                        help="which art page to run")
    parser.add_argument("--source", help="the user's own SLUS-21482 disc image")
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
