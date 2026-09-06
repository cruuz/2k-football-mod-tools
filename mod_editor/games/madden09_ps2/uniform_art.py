"""The disc's ``MMAP`` textures, decoded to PNG, and written back to a new image.

Madden 09's uniforms, player and coach faces, tattoos and field art are
``MMAP`` textures inside ``TERF`` containers.  The **lane** -- catalogue,
decode, checked import, PCSX2 identity, export with a receipt an independent
verifier re-derives, and the disc write -- now lives in
:mod:`mod_editor.games._lanes.terf_art`, because NCAA Football 09 puts its art
in exactly the same place and a second copy of an encoder is a second place for
it to be wrong.  This file is what points that lane at *this* disc: which
containers, which page, which schemas, and where the PCSX2 identity document
for ``SLUS-21770`` is.

Two rows, and they earn different rungs:

* :class:`UniformArtLane` -- ``extract-only``.  Nothing here writes to a disc
  image; a PNG comes out.
* :class:`UniformDiscArtWriteLane` -- ``offline-writer-proved``.  The edited
  PNG goes back into a NEW disc image, with every preload-cache copy the edit
  disturbed rewritten, and **no rebuilt Madden 09 container has been booted**.

The *Write PCSX2 pack* step is still not offered from either row:
:meth:`replacement_identity` answers with a name a texture dump has confirmed
where one exists and a derived name otherwise, and no pack built from those
names has been loaded in an emulator.

What *is* proved is the decode.  See :mod:`._formats.mmap_art` for the layout
and the evidence: 10,545 of 10,546 images across eight containers of the retail
disc decode cleanly, and the results are recognisable jersey sheets and human
faces rather than plausible-looking noise.

Run it without a window::

    python3 -m mod_editor.games.madden09_ps2.uniform_art --source DISC.iso
    python3 -m mod_editor.games.madden09_ps2.uniform_art --source DISC.iso \\
        --export OUT_DIR --limit 24

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence, Tuple

from mod_editor.games._lanes import terf_art
from mod_editor.games._lanes.terf_art import (
    _IDENTITY_CACHE,
    CATALOGUE_COST_NOTE,
    DERIVED_PREFIX,
    IDENTITY_CONVENTIONS,
    MAX_TARGETS,
    PNG_SIGNATURE,
    TerfArtLane,
    TerfArtWriteLane,
    _sha256,
    derive_texture_names,
    read_rgba_png,
    write_rgba_png,
)
from mod_editor.games.contract import Edit, Refusal

from . import containers

CAPABILITY_ID = "madden09ps2.uniforms.mmap_export"
LANE_ID = "uniforms.mmap_export"
CATALOG_SCHEMA = "madden09_ps2_uniform_art_catalog/v1"
RECIPE_SCHEMA = "madden09_ps2_uniform_art_recipe/v1"
WRITE_SCHEMA = "madden09_ps2_uniform_art_export/v1"

DISC_CAPABILITY_ID = "madden09ps2.uniforms.disc_art_writer"
DISC_LANE_ID = "uniforms.disc_art_writer"
DISC_RECIPE_SCHEMA = "madden09_ps2_uniform_disc_art_recipe/v1"
DISC_WRITE_SCHEMA = "madden09_ps2_uniform_disc_art_write/v1"

#: The schema ``tools/madden09_ps2_texture_identities.py``'s document declares.
#: The lane is what reads the table, so it owns what the table must say.
IDENTITY_SCHEMA = "madden09_ps2_pcsx2_texture_identities/v1"

#: The evidence document ``tools/madden09_ps2_texture_identities.py`` writes:
#: which texture on the disc PCSX2 saw, and under what filename.  Counts,
#: dimensions, filenames and member indexes; no pixel.
IDENTITY_DOCUMENT = Path("docs/product/measured/madden09_ps2/pcsx2-texture-identities.json")

#: The art containers, and what the disc itself says about how they are
#: organised.  Only the first column is a fact about *this* module; the rest is
#: what the containers reveal, with an honest label on each.
#:
#: ``group`` is what a page can sort by today.  ``UNIFORMS.DAT`` names nothing
#: -- every one of its 455 members carries 15 unnamed images -- so the member
#: index is the only structure it offers, and which team a member belongs to is
#: **not established here** [A].  ``PLYRFACE`` and ``COACFACE`` name their one
#: image ``FACE`` and ``TATTOOS`` names its own, so those groups are read from
#: the file [M].
ART_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    (containers.UNIFORM_CONTAINER, "Uniforms",
     "455 members, each carrying about fifteen unnamed images: jersey, trouser and "
     "kit sheets. The file names none of them, so the member index is the only "
     "structure it offers and which team a member belongs to is not established here."),
    (containers.PLAYER_FACE_CONTAINER, "Player faces",
     "532 members, one image each, named FACE by the file. The member index is a "
     "player face id; which player it belongs to is not established here."),
    (containers.COACH_FACE_CONTAINER, "Coach faces",
     "711 members, one image each. Same shape as the player faces."),
    (containers.TATTOO_CONTAINER, "Tattoos",
     "82 members, one image each, named by the file."),
)


def load_identities(path: Optional[Path] = None):
    """This disc's confirmed PCSX2 names, or an empty map when none is paired.

    The shared loader takes the document to read; this one supplies Madden 09's
    so a caller in this package keeps the call it always had.
    """

    return terf_art.load_identities(IDENTITY_DOCUMENT if path is None else path,
                                    IDENTITY_SCHEMA)


class UniformArtLane(TerfArtLane):
    """Every ``MMAP`` texture on the disc: preview, export, and a checked import."""

    discs = containers
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "uniforms"
    page = "uniforms"
    title = "Uniform, face and tattoo textures"
    classification = "extract-only"
    game_title = "Madden NFL 09 (PlayStation 2)"
    identity_tool = "tools/madden09_ps2_texture_identities.py"
    art_containers = ART_CONTAINERS
    identity_document = IDENTITY_DOCUMENT
    identity_schema = IDENTITY_SCHEMA
    max_targets = MAX_TARGETS
    catalog_schema = CATALOG_SCHEMA
    recipe_schema = RECIPE_SCHEMA
    write_schema = WRITE_SCHEMA
    validators = (
        "tools/validate_madden09_ps2_uniform_art.sh",
        "tools/validate_madden09_ps2_uniform_art.bat",
    )


class UniformDiscArtWriteLane(TerfArtWriteLane):
    """Edited PNGs, back into the ``MMAP`` members of a NEW disc image.

    The export lane above catalogues and decodes; this one is the other
    direction, and it is a separate row because it earns a different rung.  It
    shares the catalogue, the decoder and the PNG reader -- pointing two lanes
    at one decode is the whole reason the decoder is its own module -- and
    replaces the three steps that write.

    **What it does not claim.**  ``offline-writer-proved`` is the whole of it:
    every step is proved against the user's own bytes by a verifier that
    rebuilds the answer from the two images, and **no rebuilt Madden 09
    container has ever been booted**.
    """

    discs = containers
    lane_id = DISC_LANE_ID
    capability_id = DISC_CAPABILITY_ID
    surface = "uniforms"
    page = "uniforms"
    title = "Write uniform, face and tattoo textures back to a new disc image"
    classification = "offline-writer-proved"
    game_title = "Madden NFL 09 (PlayStation 2)"
    identity_tool = "tools/madden09_ps2_texture_identities.py"
    art_containers = ART_CONTAINERS
    identity_document = IDENTITY_DOCUMENT
    identity_schema = IDENTITY_SCHEMA
    max_targets = MAX_TARGETS
    catalog_schema = CATALOG_SCHEMA
    recipe_schema = DISC_RECIPE_SCHEMA
    write_schema = DISC_WRITE_SCHEMA
    validators = (
        "tools/validate_madden09_ps2_uniform_disc_art.sh",
        "tools/validate_madden09_ps2_uniform_disc_art.bat",
    )
    NOT_BOOTED = (
        "No rebuilt Madden 09 container has been booted. Every step here is proved against "
        "your own bytes offline -- the member decodes back to the pixels you gave it, the "
        "container follows the layout rules the retail discs follow, and every byte outside "
        "the declared ranges is unchanged -- but whether the game loads the result is not "
        "something this tool can find out."
    )


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.madden09_ps2.uniform_art --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.uniform_art",
        description="Catalogue and export a Madden NFL 09 (PS2) disc's MMAP textures.",
    )
    parser.add_argument("--source", required=True, help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--export", metavar="MANIFEST.json",
                        help="write this NEW manifest and the PNGs in a folder beside it")
    parser.add_argument("--limit", type=int, default=12,
                        help="how many textures --export writes (default 12)")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = UniformArtLane()
    try:
        catalogue = lane.build_catalogue(
            Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
        if arguments.export:
            edits = tuple(Edit(target.key, {}) for target in
                          catalogue.targets[:max(1, arguments.limit)])
            recipe = lane.compose_recipe(edits)
            manifest = Path(arguments.export)
            receipt = lane.build(Path(arguments.source), manifest, recipe, catalogue)
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
    print("UNIFORM_ART members=%d images=%d decodable=%d listed=%d not_decodable=%d"
          % (document["members_read"], document["images_seen"], document["images_decodable"],
             document["targets_listed"], sum(document["not_decodable"].values())))
    return 0


__all__ = ["ART_CONTAINERS", "CAPABILITY_ID", "CATALOGUE_COST_NOTE", "CATALOG_SCHEMA",
           "DERIVED_PREFIX",
           "IDENTITY_CONVENTIONS", "IDENTITY_DOCUMENT", "IDENTITY_SCHEMA", "load_identities",
           "DISC_CAPABILITY_ID", "DISC_LANE_ID", "DISC_RECIPE_SCHEMA", "DISC_WRITE_SCHEMA",
           "LANE_ID", "MAX_TARGETS",
           "PNG_SIGNATURE", "RECIPE_SCHEMA", "UniformArtLane", "UniformDiscArtWriteLane",
           "WRITE_SCHEMA", "derive_texture_names", "read_rgba_png", "write_rgba_png"]


if __name__ == "__main__":
    raise SystemExit(_main())
