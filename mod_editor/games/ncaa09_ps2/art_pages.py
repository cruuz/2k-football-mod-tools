"""The other four texture pages: stadiums, field art, presentation and faces.

``UNIFORM.DAT`` was never the only ``MMAP`` container on this disc.  The same
decoder, the same encoder and the same disc writer reach the stadium art, the
field and school-logo art, every menu and presentation texture, and the player
and coach faces -- and this file is what points them there.  Nothing here
re-implements the lane: each row is
:class:`mod_editor.games._lanes.terf_art.TerfArtWriteLane` with a different set
of containers, a different page and its own schemas, so a fix to the encoder is
a fix to every row at once, on this disc and on Madden 09's.

Four rows, on four pages:

=========================================  =============  ============================
row                                        page           containers
=========================================  =============  ============================
``ncaa09ps2.stadiums.textures``            stadiums       ``STADATA``, ``UIS_STAD``
``ncaa09ps2.field_art.textures``           field_art      ``FLDDATA``, ``UIS_TMLO``
``ncaa09ps2.presentation.ui_textures``     presentation   ``FANDATA``, ``MSCTDATA``,
                                                          ``LOADDATA``
``ncaa09ps2.rosters.face_textures``        rosters        ``PLYRFACE``, ``COACFACE``
=========================================  =============  ============================

**One lane per row, not two.**  The uniforms page carries two rows because its
exporter is the row NCAA 09 shipped first and earns a lower rung than the
writer beside it.  These four ship with both halves at once, and one lane
already *is* both: the shell draws preview, Export PNG and a checked Import PNG
out of ``decode_png`` and ``encode``, and Build writes the edited texture into a
NEW disc image.

**What is not a texture is listed, not hidden.**  Every one of these containers
carries members this lane cannot open.  ``STADIUMS.DAT``'s 2,914 members are
1,880 ``SMF`` geometry and 1,034 empty, and ``STADATA.DAT`` adds 45 ``SMF`` and
4 ``DMF``; ``MSCTDATA.DAT`` carries 400 ``DMF``; ``MOVIEDAT.DAT`` is 12 ``MPCh``
movie streams [M].  **No ``SMF``, ``DMF`` or ``MPCh`` decoder is built anywhere
in this repository and no layout for any of them is documented here**, so the
catalogue counts them by format per container and leaves them alone.  Two of
those containers are not even on a page's list: ``STADIUMS.DAT`` is 197 MB, past
this module's 144 MB read limit, and ``MOVIEDAT.DAT`` is 333 MB and carries no
texture at all.  Both are listed by the All Textures page with their size.

**The preload caches are what a write costs here** [M].  ``STADATA.DAT``'s
directory is copied twice and 45 of its members; ``FLDDATA.DAT``'s once and 21;
``LOADDATA.DAT``'s three times and 27; ``PLYRFACE.DAT``'s twice and 54;
``MSCTDATA.DAT``'s once and 12; ``UIS_TMLO.DAT``'s once and 8.  Only
``UIS_STAD.DAT`` (a directory copy and no member) and ``FANDATA.DAT`` (the
same) are nearly free.  Every copy an edit disturbs is rewritten from the
container's own new bytes; a *carried* member whose stored size changed is
refused by name, because a cached copy is a fixed slot.

**Classification: ``offline-writer-proved``, and never more.**  Every step is
proved against the user's own bytes offline.  **No rebuilt NCAA Football 09
container has been booted**, so no row here says the game loads the result.

**No PCSX2 texture dump has been paired with ``SLUS-21752``**, so every
replacement identity on these pages is derived from the texture's own bytes and
none is confirmed.  The page says which.

Run one without a window::

    python3 -m mod_editor.games.ncaa09_ps2.art_pages --page stadiums \\
        --source DISC.iso [--out catalogue.json] [--export DIR/manifest.json]

**Evidence tags.**  **[M]** measured on the retail SLUS-21752 disc;
**[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence, Tuple

from mod_editor.games._lanes.terf_art import TerfArtWriteLane
from mod_editor.games.contract import Edit, Refusal

from . import containers
from .texture_lane import GAME_TITLE

#: A container a lane here points at: ``(file name, group, structure)``.  The
#: third column is what the container itself says, measured on the retail disc
#: by ``member_format`` over every member and ``mmap_art.parse`` over every
#: texture -- counts and sizes, never a pixel [M].
ContainerSpec = Tuple[str, str, str]

STADIUM_CONTAINERS: Tuple[ContainerSpec, ...] = (
    (containers.STADIUM_CONTAINERS[0], "Stadium art",
     "1,289 members: 1,195 MMAP textures, 45 SMF static geometry and 4 DMF animated "
     "models. The geometry is left alone -- no SMF or DMF decoder exists anywhere in "
     "this repository. Its directory is copied twice and 45 of its members are copied "
     "into the preload caches, so an edit to one of those 45 must keep its stored size."),
    (containers.STADIUM_CONTAINERS[1], "Stadium UI",
     "245 stored members. Its directory is copied once into a preload cache and none "
     "of its members is, which makes a rewrite here cheap."),
)

FIELD_ART_CONTAINERS: Tuple[ContainerSpec, ...] = (
    (containers.FIELD_ART_CONTAINERS[0], "Field art",
     "1,422 members, 1,391 of them LZH1-packed. This is the painted field surface and "
     "the end-zone art; which field a member belongs to is not established here."),
    (containers.FIELD_ART_CONTAINERS[1], "School logos",
     "399 LZH1-packed MMAP members: the school marks the menus and the fields draw. "
     "Which school a member belongs to is not established here -- the container names "
     "nothing, and no table on this disc joins a TEAM row to a texture."),
)

PRESENTATION_CONTAINERS: Tuple[ContainerSpec, ...] = (
    (containers.PRESENTATION_CONTAINERS[0], "Crowd",
     "257 stored members. Its directory is copied once into a preload cache and none "
     "of its members is."),
    (containers.PRESENTATION_CONTAINERS[1], "Mascots and trophies",
     "641 members: 240 MMAP textures and 400 DMF animated models. The models are left "
     "alone; no DMF decoder exists here."),
    (containers.PRESENTATION_CONTAINERS[2], "Load screens",
     "46 members, 30 of them 854x480 -- the shape a full-screen load image takes."),
)

FACE_CONTAINERS: Tuple[ContainerSpec, ...] = (
    (containers.FACE_CONTAINERS[0], "Player faces",
     "80 stored members, 64 of them carrying an MMAP wrapper header. The member index "
     "is a face id; which player it belongs to is not established here, and could not "
     "be: this disc's PLAY table carries no name to join it to."),
    (containers.FACE_CONTAINERS[1], "Coach faces",
     "18 stored members. The coaches DO have names on this disc -- COCH.CLFN and "
     "COCH.CLLN -- but nothing joins a coach row to a face member, so which coach a "
     "member is remains unestablished."),
)


class ArtPageLane(TerfArtWriteLane):
    """One art page: catalogue, preview, export, checked import, disc write-back.

    The whole of it is inherited from the shared base.  What a subclass sets is
    *where it points* -- the containers, the page, the surface, the ids and the
    schemas.  Overriding anything else would be a fork of the writer, which is
    the thing this file exists not to be.
    """

    discs = containers
    classification = "offline-writer-proved"
    game_title = GAME_TITLE
    #: No PCSX2 texture dump has been paired with this disc, so every name is
    #: derived and none is confirmed.
    identity_document = None
    identity_tool = ""
    #: Every texture in the lane's containers is addressable.  These pages hold
    #: between 300 and 1,600 images and a writer that could only reach the first
    #: few thousand would refuse the rest for no reason a user can see.
    max_targets = 12000
    validators = (
        "tools/validate_ncaa09_ps2_art_pages.sh",
        "tools/validate_ncaa09_ps2_art_pages.bat",
    )
    #: The page's own sentence about what it does not edit.  Rendered beside
    #: the lane, and repeated in the catalogue.
    page_scope = ""

    def build_catalogue(self, source: Path, *, progress=None):
        catalogue = super().build_catalogue(source, progress=progress)
        document = dict(catalogue.document)
        document["page_scope"] = self.page_scope
        from mod_editor.games.contract import Catalogue

        return Catalogue(catalogue.schema, catalogue.lane_id, catalogue.source,
                         catalogue.targets, document)


class StadiumArtLane(ArtPageLane):
    """``STADATA.DAT`` and ``UIS_STAD.DAT``, on the Stadiums page.

    The disc also ships a real stadium **table** -- ``LEAGUE.DAT``'s ``STAD``,
    242 rows of 56 fields -- and its names are edited by the Text & Team
    Identity page's lane.  This row is the art: 1,195 ``MMAP`` textures in
    ``STADATA.DAT`` and 245 stored members in ``UIS_STAD.DAT`` [M].
    """

    lane_id = "stadiums.textures"
    capability_id = "ncaa09ps2.stadiums.textures"
    surface = "stadiums_fields"
    page = "stadiums"
    title = "Stadium textures"
    art_containers = STADIUM_CONTAINERS
    catalog_schema = "ncaa09_ps2_stadium_art_catalog/v1"
    recipe_schema = "ncaa09_ps2_stadium_art_recipe/v1"
    write_schema = "ncaa09_ps2_stadium_art_write/v1"
    page_scope = (
        "Edits the MMAP textures of STADATA.DAT and UIS_STAD.DAT. It does not touch the 45 "
        "SMF geometry members and 4 DMF models in STADATA.DAT -- no decoder for either is "
        "built anywhere in this repository -- and it does not open STADIUMS.DAT at all: at "
        "197 MB that container is past this module's 144 MB read limit, and its 2,914 "
        "members are 1,880 SMF and 1,034 empty, so there is no texture in it to edit. The "
        "stadium NAMES are on the Text & Team Identity page, in LEAGUE.DAT's STAD table."
    )


class FieldArtLane(ArtPageLane):
    """``FLDDATA.DAT`` and ``UIS_TMLO.DAT``, on the Field Art & Create-Team Art page."""

    lane_id = "field_art.textures"
    capability_id = "ncaa09ps2.field_art.textures"
    surface = "stadiums_fields"
    page = "field_art"
    title = "Field and school-logo textures"
    art_containers = FIELD_ART_CONTAINERS
    catalog_schema = "ncaa09_ps2_field_art_catalog/v1"
    recipe_schema = "ncaa09_ps2_field_art_recipe/v1"
    write_schema = "ncaa09_ps2_field_art_write/v1"
    page_scope = (
        "Edits the MMAP textures of FLDDATA.DAT (1,422 members) and UIS_TMLO.DAT (399 "
        "school logos). It does not create a team: the create-a-school tables this page is "
        "half named for -- CTTB, CTCD, CTUN, USTG, USLG, USLE -- all have 0 rows on this "
        "disc, because a created school is user data and lives in a memory-card save this "
        "studio does not read. Which field or which school a member is remains "
        "unestablished: neither container names its members."
    )


class PresentationArtLane(ArtPageLane):
    """The crowd, the mascots and trophies, and the load screens."""

    lane_id = "presentation.ui_textures"
    capability_id = "ncaa09ps2.presentation.ui_textures"
    surface = "scorebug_presentation"
    page = "presentation"
    title = "Crowd, mascot, trophy and load-screen textures"
    art_containers = PRESENTATION_CONTAINERS
    catalog_schema = "ncaa09_ps2_ui_art_catalog/v1"
    recipe_schema = "ncaa09_ps2_ui_art_recipe/v1"
    write_schema = "ncaa09_ps2_ui_art_write/v1"
    page_scope = (
        "Edits the MMAP textures of FANDATA.DAT (crowd), MSCTDATA.DAT (mascots and "
        "trophies) and LOADDATA.DAT (load screens, 30 of them 854x480). It does not touch "
        "MSCTDATA.DAT's 400 DMF animated models -- no DMF decoder is built here -- and it "
        "does not open MOVIEDAT.DAT: 333 MB of 12 MPCh movie streams, for which this "
        "repository has no decoder and claims none. The scorebug itself is drawn by the "
        "executable and nothing on this disc has been mapped to it."
    )


class FaceArtLane(ArtPageLane):
    """Player and coach faces, on the Names, Numbers & Faces page."""

    lane_id = "rosters.face_textures"
    capability_id = "ncaa09ps2.rosters.face_textures"
    surface = "portraits_faces"
    page = "rosters"
    title = "Player and coach face textures"
    art_containers = FACE_CONTAINERS
    catalog_schema = "ncaa09_ps2_face_art_catalog/v1"
    recipe_schema = "ncaa09_ps2_face_art_recipe/v1"
    write_schema = "ncaa09_ps2_face_art_write/v1"
    page_scope = (
        "Edits the 64 player-face and 18 coach-face MMAP textures of PLYRFACE.DAT and "
        "COACFACE.DAT. It does not know which player or coach a face belongs to: this "
        "disc's PLAY table carries no name to join a face to, and although COCH does carry "
        "CLFN and CLLN, nothing joins a coach row to a face member. PLYRFACE.DAT's "
        "directory is copied twice into the preload caches and 54 of its members are, so "
        "an edit to one of those 54 must keep its stored size or is refused by name."
    )


#: The four rows this file adds, in page order.
ART_PAGE_LANES: Tuple[type, ...] = (
    FaceArtLane, FieldArtLane, PresentationArtLane, StadiumArtLane,
)

#: ``--page`` on the command line, and the lane it names.
LANES_BY_PAGE = {lane.page: lane for lane in ART_PAGE_LANES}


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.ncaa09_ps2.art_pages --page stadiums --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.ncaa09_ps2.art_pages",
        description="Catalogue, export and write back one of NCAA Football 09 (PS2)'s "
                    "four other texture pages.",
    )
    parser.add_argument("--page", choices=sorted(LANES_BY_PAGE),
                        help="which page's lane to run")
    parser.add_argument("--source", help="the user's own SLUS-21752 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--export", metavar="MANIFEST.json",
                        help="write this NEW manifest and the PNGs in a folder beside it")
    parser.add_argument("--limit", type=int, default=8,
                        help="how many textures --export writes (default 8)")
    parser.add_argument("--selftest", action="store_true",
                        help="run every page's lane on its synthetic disc")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if arguments.selftest:
            import tempfile

            for lane_class in ART_PAGE_LANES:
                lane = lane_class()
                with tempfile.TemporaryDirectory() as room:
                    source = lane.synthetic_source(Path(room))
                    catalogue = lane.build_catalogue(source)
                    edits = lane.conformance_edits(catalogue)
                    destination = Path(room) / "written.iso"
                    receipt = lane.build(source, destination, lane.compose_recipe(edits),
                                         catalogue)
                    verdict = lane.verify(source, destination, receipt)
                    print("NCAA09_ART_PAGE %-22s targets=%-5d write=%s"
                          % (lane.page, len(catalogue.targets),
                             "PASS" if verdict.passed else "FAIL"))
                    if not verdict.passed:
                        print(verdict.summary, file=sys.stderr)
                        return 1
            return 0
        if not arguments.page or not arguments.source:
            parser.error("give --page and --source DISC.iso, or --selftest")
        lane = LANES_BY_PAGE[arguments.page]()
        catalogue = lane.build_catalogue(
            Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
        if arguments.export:
            edits = tuple(Edit(target.key, {}) for target in
                          catalogue.targets[:max(1, arguments.limit)])
            manifest = Path(arguments.export)
            receipt = lane.build(Path(arguments.source), manifest,
                                 lane.compose_recipe(edits), catalogue)
            verdict = lane.verify(Path(arguments.source), manifest, receipt)
            print(f"EXPORT files={len(receipt.artifacts)} "
                  f"verify={'PASS' if verdict.passed else 'FAIL'} — {verdict.summary}")
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    print("NCAA09_ART_PAGE %s members=%d images=%d decodable=%d listed=%d"
          % (arguments.page, document["members_read"], document["images_seen"],
             document["images_decodable"], document["targets_listed"]))
    return 0


__all__ = ["ART_PAGE_LANES", "ArtPageLane", "ContainerSpec", "FACE_CONTAINERS",
           "FIELD_ART_CONTAINERS", "FaceArtLane", "FieldArtLane", "LANES_BY_PAGE",
           "PRESENTATION_CONTAINERS", "PresentationArtLane", "STADIUM_CONTAINERS",
           "StadiumArtLane"]


if __name__ == "__main__":
    raise SystemExit(_main())
