"""NFL Street 3 (PlayStation 2)'s kit, skin and tattoo ``MMAP`` members — catalogued, and one in 16,259 decoded.

A baller's look on this disc **is** ``/DATA/PLATEX.DAT`` and nothing else.  There
is no uniform table to pair the art with: the kit tables this family usually
carries live in ``TEMPLATE.DAT``'s create-a-team set and describe a *created*
team, not the 32 shipped ones [M].

The measured result this page exists to state
---------------------------------------------

``PLATEX.DAT`` holds **16,259 ``MMAP`` members** in a 87,709,696-byte container,
16,231 of them ``LZH1``-packed, and every one carries exactly one image.  Of
those 16,259 images, **3 decode here.**  The other 16,256 declare
**pixel layout 5 (13,853 of them) or pixel layout 6 (2,403)**, and
:mod:`mod_editor.games._formats.mmap_art` reads two layouts: 0 (4-bit indexed)
and 1 (8-bit indexed).  Layouts 5 and 6 are direct-colour surfaces with no CLUT,
and nothing in this repository decodes them [M].

**The assumption that would make that wrong** is that a kit texture on this disc
is an indexed texture.  It is not: it is direct colour, which is also why every
one of the 807 names PCSX2 wrote for this disc declares **PSM 0
(PSMCT32)** and not one declares PSM 27 [M].  A decoder for layouts 5 and 6
would turn 16,256 refusals into targets in an afternoon and would change nothing
else on this page; that, and not a bigger cap or a longer walk, is what this
container is waiting on.

So this row is **``extract-only`` and there is no kit *writer***.  A write lane
here would offer 3 target(s) and refuse 16,256, which is a control that can
only refuse.  The disc's other 1,725 decodable textures -- portraits, logos,
field art, playfields, presentation and menus -- do have writers, on their own
pages (:mod:`.art_pages`).

**PCSX2 identities: 28 confirmed, the rest derived.**  Five frames have been captured on this disc, covering a loading screen carrying the Audibles tip card and gameplay; 1,569 PNGs across the two naming conventions deduplicate to 807 distinct textures.
Pairing that capture against the disc through
``tools/ps2_texture_identities.py --game nflstreet3_ps2`` named **28 disc
texture(s)** from 81 of the 807 dumped files; 693 dumped files pair with
nothing this module indexes, which is what a disc whose art is mostly
direct-colour looks like from the dump side.  None of the 807 declares PSM 27, so ``extra_psms`` stays empty here [M].  Every other texture's
name is **derived** from its own bytes and :meth:`identity_note` says which of
the two it is, on every one.  ``docs/product/NFLSTREET3_PS2_MODULE.md`` §5 lists the
screens a further capture should cover.

Run it without a window::

    python3 -m mod_editor.games.nflstreet3_ps2.texture_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence, Tuple

from mod_editor.games._lanes import terf_art
from mod_editor.games._lanes.terf_art import TerfArtLane
from mod_editor.games.contract import Edit, Refusal

from . import containers

CAPABILITY_ID = "nflstreet3ps2.uniforms.texture_census"
LANE_ID = "uniforms.texture_census"
CATALOG_SCHEMA = "nflstreet3_ps2_texture_census/v1"
RECIPE_SCHEMA = "nflstreet3_ps2_kit_art_recipe/v1"
WRITE_SCHEMA = "nflstreet3_ps2_kit_art_export/v1"

#: What a sentence calls this game.
GAME_TITLE = "NFL Street 3 (PlayStation 2)"

#: The schema ``tools/ps2_texture_identities.py``'s document declares for this
#: disc.  The lane is what reads the table, so it owns what the table must say.
IDENTITY_SCHEMA = "nflstreet3_ps2_pcsx2_texture_identities/v1"

#: The evidence document that tool writes: which texture on the disc PCSX2 saw,
#: and under what filename.  Counts, dimensions, filenames and member indexes;
#: no pixel.  Every art row in this module reads it, because one capture's
#: frames reach several pages at once.
IDENTITY_DOCUMENT = Path(
    "docs/product/measured/nflstreet3_ps2/pcsx2-texture-identities.json")

#: What a refusal names when it asks for another capture.
IDENTITY_TOOL = "tools/ps2_texture_identities.py --game nflstreet3_ps2"

#: How well the derivation reproduces the names the paired dump actually wrote,
#: **for this disc**.  Only 28 textures are named, so a derivation check over them would be a measurement of twenty-eight samples; it has not been run and the sentence below says so rather than quoting another disc's figure.
DERIVATION_EVIDENCE = (
    "the rule's accuracy on this disc is unmeasured: the capture paired with SLUS-21482 names 28 textures, too few to check a derivation rule against, so every derived name here is computed and unverified")

#: Whether the derivation also has to cover ``PSMT8H``, which PCSX2 hashes over
#: the plain linear stream rather than the block image.  Measured on this disc's
#: own capture: **every one of the 807 dumped names declares PSM 0
#: (PSMCT32)** and none declares PSM 27 [M], so this stays empty.  The base's
#: default is another disc's measurement, and quoting one disc's number on
#: another is what this attribute exists to stop.
EXTRA_PSMS: Tuple[int, ...] = ()

#: The kit container, and what the disc itself says about it [M].
ART_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    (containers.UNIFORM_CONTAINERS[0], "Kits, skins and tattoos",
     "16,259 MMAP members, 16,231 of them LZH1-packed, in an 87,709,696-byte container -- 9.4x the member count of NFL Street's PLATEX.DAT. Every member carries one image and 16,256 of those images declare pixel layout 5 or 6 -- direct colour, no CLUT -- which this decoder does not read [M]."),
)

#: What the page says where a Madden page offers a uniform record to edit.
NO_KIT_TABLE_NOTE = (
    "There is no kit table on this disc to pair these textures with. The create-a-team tables that would carry one -- UNIF, TUNI, GEAR, CRTM, FACE and the rest, 149 tables in all -- are in TEMPLATE.DAT and describe a created team, not one of the 32 shipped ones [M]. Street 3 also added a twenty-field PF* face block to PLAY and ships every column of it zero, so even the per-player face indices are unused on the retail disc."
)

#: Why this page has no writer, in the numbers that decide it.
NO_WRITER_NOTE = (
    "This page has no writer, and the number is why: 16,256 of PLATEX.DAT's 16,259 images declare pixel layout 5 or 6, which mmap_art does not read -- it reads layout 0 (4-bit indexed) and layout 1 (8-bit indexed) [M]. A write lane here would offer three targets and refuse 16,256. What would change that is a decoder for the two direct-colour layouts, not a bigger cap; the other art pages in this module do have writers, over the 1,725 textures on this disc that do decode."
)


def load_identities(path: Optional[Path] = None):
    """This disc's confirmed PCSX2 names, or an empty map when none is paired."""

    return terf_art.load_identities(IDENTITY_DOCUMENT if path is None else path,
                                    IDENTITY_SCHEMA)


class TextureLane(TerfArtLane):
    """Every kit member, catalogued; the 3 this decoder reads, exported."""

    discs = containers
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "uniforms"
    page = "uniforms"
    title = "Kit, skin and tattoo textures"
    classification = "extract-only"
    game_title = GAME_TITLE
    art_containers = ART_CONTAINERS
    identity_document = IDENTITY_DOCUMENT
    identity_schema = IDENTITY_SCHEMA
    identity_tool = IDENTITY_TOOL
    derivation_evidence = DERIVATION_EVIDENCE
    extra_psms = EXTRA_PSMS
    max_targets = 8000
    max_targets_per_container = 6000
    catalog_schema = CATALOG_SCHEMA
    recipe_schema = RECIPE_SCHEMA
    write_schema = WRITE_SCHEMA
    validators = (
        "tools/validate_nflstreet3_ps2_textures.sh",
        "tools/validate_nflstreet3_ps2_textures.bat",
    )

    def build_catalogue(self, source: Path, *, progress=None):
        """The base's catalogue, plus the two sentences the numbers make necessary."""

        catalogue = super().build_catalogue(source, progress=progress)
        document = dict(catalogue.document)
        document["no_kit_table"] = NO_KIT_TABLE_NOTE
        document["no_writer"] = NO_WRITER_NOTE
        from mod_editor.games.contract import Catalogue

        return Catalogue(catalogue.schema, catalogue.lane_id, catalogue.source,
                         catalogue.targets, document)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.nflstreet3_ps2.texture_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.nflstreet3_ps2.texture_lane",
        description="Catalogue and export a NFL Street 3 (PlayStation 2) disc's kit MMAP members.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21482 disc image")
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
                return 0 if verdict.passed else 1
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
                  f"verify={'PASS' if verdict.passed else 'FAIL'} \u2014 {verdict.summary}")
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    print("TEXTURES members=%d images=%d decodable=%d listed=%d not_decodable=%d"
          % (document["members_read"], document["images_seen"], document["images_decodable"],
             document["targets_listed"], sum(document["not_decodable"].values())))
    return 0


__all__ = ["ART_CONTAINERS", "CAPABILITY_ID", "CATALOG_SCHEMA", "DERIVATION_EVIDENCE",
           "EXTRA_PSMS", "GAME_TITLE", "IDENTITY_DOCUMENT", "IDENTITY_SCHEMA",
           "IDENTITY_TOOL", "LANE_ID", "NO_KIT_TABLE_NOTE", "NO_WRITER_NOTE",
           "RECIPE_SCHEMA", "TextureLane", "WRITE_SCHEMA", "load_identities"]


if __name__ == "__main__":
    raise SystemExit(_main())
