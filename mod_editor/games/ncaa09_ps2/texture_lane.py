"""The kit, equipment and face ``MMAP`` textures — decoded, and written back.

NCAA Football 09's uniforms and equipment are ``MMAP`` textures inside ``TERF``
containers, exactly as Madden NFL 09's are.  The lane that reads them is the
shared :mod:`mod_editor.games._lanes.terf_art`; this file is what points it at
*this* disc.

**There is no kit table to pair the art with, and that is measured.**  Every
uniform-shaped table on this disc has **0 rows** -- ``CTTB`` (104 fields),
``CTCD`` (45), ``CTUN`` (28), ``USTG``, ``USLG``, ``USLE`` -- because they are
the create-a-school tables and nobody has created one.  Madden 09 by contrast
ships ``UNIF`` with 270 rows [M].  **A school's kit here *is* these textures and
nothing else**, which is why this page has art rows and no database row.

What is on the page, measured on the retail disc [M]:

=================  =========  ==================================================
container            members  what it is
=================  =========  ==================================================
``UNIFORM.DAT``        1,200  kit textures, ``LZH1``-packed, 127,942,528 bytes
``PLADATA.DAT``          888  player equipment, ``LZH1``
``UIS_GEAR.DAT``         396  gear icons, stored -- and named by no preload cache
=================  =========  ==================================================

Two rows, and they earn different rungs:

* :class:`TextureLane` -- ``extract-only``.  A PNG comes out; nothing is
  written to a disc image.
* :class:`UniformDiscArtWriteLane` -- ``offline-writer-proved``.  The edited
  PNG goes back into a NEW disc image.

**The preload caches decide what a write costs here.**  ``UNIFORM.DAT``'s
directory is copied four times and three of its members are copied [M];
``PLADATA.DAT``'s directory once and eight members; **``UIS_GEAR.DAT`` is named
by no cache at all** [M], which makes it the cheapest target on the disc and the
one a first edit should use.  Every copy an edit disturbs is rewritten from the
container's own new bytes, and a *carried* member whose stored size changed is
refused by name rather than written past the end of somebody else's copy.

**No PCSX2 texture dump has been paired with this disc.**  So every replacement
identity here is **derived** -- computed from the texture's own bytes through
:mod:`mod_editor.games._formats.pcsx2_texture_name`, the GS block image of each
mip chain and the image's own palette -- and none is confirmed.  The page says
which it is, and no pack built from these names has been loaded in an emulator.

Run it without a window::

    python3 -m mod_editor.games.ncaa09_ps2.texture_lane --source DISC.iso
    python3 -m mod_editor.games.ncaa09_ps2.texture_lane --source DISC.iso \\
        --export OUT/manifest.json --limit 24

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence, Tuple

from mod_editor.games._lanes.terf_art import (
    MAX_TARGETS,
    TerfArtLane,
    TerfArtWriteLane,
)
from mod_editor.games.contract import Edit, Refusal

from . import containers

CAPABILITY_ID = "ncaa09ps2.uniforms.texture_census"
LANE_ID = "uniforms.texture_census"
CATALOG_SCHEMA = "ncaa09_ps2_texture_census/v1"
RECIPE_SCHEMA = "ncaa09_ps2_uniform_art_recipe/v1"
WRITE_SCHEMA = "ncaa09_ps2_uniform_art_export/v1"

DISC_CAPABILITY_ID = "ncaa09ps2.uniforms.disc_art_writer"
DISC_LANE_ID = "uniforms.disc_art_writer"
DISC_RECIPE_SCHEMA = "ncaa09_ps2_uniform_disc_art_recipe/v1"
DISC_WRITE_SCHEMA = "ncaa09_ps2_uniform_disc_art_write/v1"

#: What a sentence calls this game.
GAME_TITLE = "NCAA Football 09 (PlayStation 2)"

#: The kit, equipment and gear containers, and what the disc itself says about
#: each.  Only the first column is a fact about *this* module; the rest is what
#: the containers reveal, with an honest label on each [M].
ART_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    (containers.UNIFORM_CONTAINERS[0], "Kits",
     "1,206 members, 1,200 of them LZH1-packed MMAP kit textures, in a 127,942,528-byte "
     "container. The file names none of them, so the member index is the only structure "
     "it offers and which school a member belongs to is not established here -- and no "
     "table on this disc says either, because every create-a-school kit table has 0 rows."),
    (containers.UNIFORM_CONTAINERS[1], "Equipment",
     "889 members, 888 of them LZH1-packed MMAP player-equipment textures."),
    (containers.UNIFORM_CONTAINERS[2], "Gear icons",
     "396 stored MMAP members. This container is named by none of the three preload "
     "caches, which makes a rewrite here the cheapest on the disc: no cached directory "
     "and no cached member has to move with it."),
)

#: What the page says where a Madden page offers a uniform record to edit.
NO_KIT_TABLE_NOTE = (
    "There is no kit table on this disc to pair these textures with. CTTB (104 fields), "
    "CTCD (45), CTUN (28), USTG, USLG and USLE all have 0 rows, because they are the "
    "create-a-school tables and nobody has created one; Madden 09 by contrast ships UNIF "
    "with 270 rows. A school's kit here is these textures and nothing else, which is why "
    "this page has art rows and no database row."
)


class TextureLane(TerfArtLane):
    """Every kit, equipment and gear texture: preview, export, checked import."""

    discs = containers
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "uniforms"
    page = "uniforms"
    title = "Kit, equipment and gear textures"
    classification = "extract-only"
    game_title = GAME_TITLE
    art_containers = ART_CONTAINERS
    #: No PCSX2 texture dump has been paired with SLUS-21752, so every name
    #: this lane offers is derived and none is confirmed.  The absence is the
    #: honest value: a document that does not exist is not a document to read.
    identity_document = None
    identity_tool = ""
    max_targets = MAX_TARGETS
    #: UNIFORM.DAT's 1,200 members carry about 15,600 images between them, so a
    #: flat cap spent on the first container leaves UIS_GEAR.DAT -- 396 gear
    #: icons, and the one container on this disc no preload cache names --
    #: unreachable [M]. Each container gets its own share instead.
    max_targets_per_container = 1500
    catalog_schema = CATALOG_SCHEMA
    recipe_schema = RECIPE_SCHEMA
    write_schema = WRITE_SCHEMA
    validators = (
        "tools/validate_ncaa09_ps2_textures.sh",
        "tools/validate_ncaa09_ps2_textures.bat",
    )

    def build_catalogue(self, source: Path, *, progress=None):
        """The base's catalogue, plus the sentence about the kit table that is not there."""

        catalogue = super().build_catalogue(source, progress=progress)
        document = dict(catalogue.document)
        document["no_kit_table"] = NO_KIT_TABLE_NOTE
        from mod_editor.games.contract import Catalogue

        return Catalogue(catalogue.schema, catalogue.lane_id, catalogue.source,
                         catalogue.targets, document)



class UniformDiscArtWriteLane(TerfArtWriteLane):
    """Edited PNGs, back into the kit, equipment and gear members of a NEW image."""

    discs = containers
    lane_id = DISC_LANE_ID
    capability_id = DISC_CAPABILITY_ID
    surface = "uniforms"
    page = "uniforms"
    title = "Write kit, equipment and gear textures back to a new disc image"
    classification = "offline-writer-proved"
    game_title = GAME_TITLE
    art_containers = ART_CONTAINERS
    identity_document = None
    identity_tool = ""
    max_targets = MAX_TARGETS
    max_targets_per_container = 1500
    catalog_schema = CATALOG_SCHEMA
    recipe_schema = DISC_RECIPE_SCHEMA
    write_schema = DISC_WRITE_SCHEMA
    validators = (
        "tools/validate_ncaa09_ps2_uniform_disc_art.sh",
        "tools/validate_ncaa09_ps2_uniform_disc_art.bat",
    )
    NOT_BOOTED = (
        "No rebuilt NCAA Football 09 container has been booted. Every step here is proved "
        "against your own bytes offline -- the member decodes back to the pixels you gave "
        "it, the container follows the layout rules the retail discs follow, every preload "
        "cache copy of the container is rewritten with it, and every byte outside the "
        "declared ranges is unchanged -- but whether the game loads the result is not "
        "something this tool can find out."
    )



def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.ncaa09_ps2.texture_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.ncaa09_ps2.texture_lane",
        description="Catalogue and export an NCAA Football 09 (PS2) disc's kit, equipment "
                    "and gear MMAP textures.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21752 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--export", metavar="MANIFEST.json",
                        help="write this NEW manifest and the PNGs in a folder beside it")
    parser.add_argument("--limit", type=int, default=12,
                        help="how many textures --export writes (default 12)")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = TextureLane()
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                source = lane.synthetic_source(Path(room))
                catalogue = lane.build_catalogue(source)
                edits = tuple(Edit(target.key, {}) for target in catalogue.targets[:3])
                manifest = Path(room) / "export" / "manifest.json"
                receipt = lane.build(source, manifest, lane.compose_recipe(edits), catalogue)
                verdict = lane.verify(source, manifest, receipt)
                print(f"EXPORT files={len(receipt.artifacts)} "
                      f"verify={'PASS' if verdict.passed else 'FAIL'}")
                if not verdict.passed:
                    return 1
        else:
            if not arguments.source:
                parser.error("give --source DISC.iso, or --selftest")
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
    print("NCAA09_TEXTURES members=%d images=%d decodable=%d listed=%d not_decodable=%d"
          % (document["members_read"], document["images_seen"], document["images_decodable"],
             document["targets_listed"], sum(document["not_decodable"].values())))
    return 0


__all__ = ["ART_CONTAINERS", "CAPABILITY_ID", "CATALOG_SCHEMA", "DISC_CAPABILITY_ID",
           "DISC_LANE_ID", "DISC_RECIPE_SCHEMA", "DISC_WRITE_SCHEMA", "GAME_TITLE",
           "LANE_ID", "NO_KIT_TABLE_NOTE", "RECIPE_SCHEMA", "TextureLane",
           "UniformDiscArtWriteLane", "WRITE_SCHEMA"]


if __name__ == "__main__":
    raise SystemExit(_main())
