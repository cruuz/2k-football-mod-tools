"""Every ``TEXT`` string bank on the NFL Street (PlayStation 2) disc, measured and rewritten in place.

The disc carries **531 ``TEXT`` members** across four containers [M].  A
``TEXT`` member is NUL-separated latin-1 strings and nothing else -- no index,
no length table -- so a string is rewritten **inside the bytes it already
occupies** and a replacement longer than the slot is refused by name with both
lengths in the sentence.

Where they are, measured [M]
----------------------------

``OBJDEFS.DAT`` 393 · ``PLADYNCL.DAT`` 129 · ``ENVRNMT.DAT`` 8 ·
``IGDATA.DAT`` 1.  ``OBJDEFS.DAT`` is every member: 393 of 393 are ``TEXT`` [M].

The walk, the measurement, the in-place rewrite and the independent verifier are
the shared :class:`mod_editor.games._lanes.text_banks.TextBankLane`; this file
is what points it at this disc and what says which of its containers a preload
cache copies, because that is what a write here costs.

**None of the four ``TEXT`` containers is named by any of this disc's
nine ``QL01`` preload caches** [M], which makes a text edit the cheapest
write this module has: no cached directory and no cached member moves with it.

**Nothing here has been seen in a running game.**

Run it without a window::

    python3 -m mod_editor.games.nflstreet1_ps2.text_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence, Tuple

from mod_editor.games._lanes.text_banks import TextBankLane
from mod_editor.games.contract import Refusal

from . import containers

CAPABILITY_ID = "nflstreet1ps2.menus.text_members"
LANE_ID = "menus.text_members"
SCHEMA = "nflstreet1_ps2_text_inventory/v1"
RECIPE_SCHEMA = "nflstreet1_ps2_text_edit/v1"
RECEIPT_SCHEMA = "nflstreet1_ps2_text_write/v1"

#: Which containers this disc's preload caches carry a copy of, as the measured
#: floor.  The list a user's own image declares is read at catalogue time by
#: :func:`containers.preload_names` and takes precedence; this is what the disc
#: on this box declares, so an image whose caches cannot be walked still refuses
#: the one it is known to have to.
PRELOAD_COPIES: Mapping[str, Tuple[str, ...]] = {
    # Read from the user's own image at catalogue time; this map is
    # the measured floor and is deliberately empty because none of
    # this disc's four TEXT containers is named by any of its nine
    # QL01 caches [M] -- so a text write here disturbs no cached copy,
    # which makes it the cheapest write on the disc.
}

#: The containers that carry a ``TEXT`` member on this disc [M].  Named here for
#: the document; the lane still discovers members by walking, so an image with a
#: bank somewhere else lists it rather than hiding it.
WRITABLE_TEXT_CONTAINERS = ("OBJDEFS.DAT", "PLADYNCL.DAT", "ENVRNMT.DAT", "IGDATA.DAT")

#: What the page says about the fonts it cannot reach.
FONT_NOTE = (
    "UIS_FONT.DAT holds 4 FNTS font sets and no decoder for that format exists in this repository, so the glyphs a string is drawn with are out of reach here. A replacement is written in latin-1, the encoding EA stored these banks in; a character the shipped font has no glyph for will not draw, and this lane cannot tell you which those are."
)


class TextLane(TextBankLane):
    """Every ``TEXT`` member on the disc, measured; each one editable in place."""

    discs = containers
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "menus"
    page = "menus"
    title = "Text banks"
    classification = "offline-writer-proved"
    game_title = "NFL Street (PlayStation 2)"
    schema = SCHEMA
    recipe_schema = RECIPE_SCHEMA
    receipt_schema = RECEIPT_SCHEMA
    preload_copies = PRELOAD_COPIES
    validators = (
        "tools/validate_nflstreet1_ps2_text.sh",
        "tools/validate_nflstreet1_ps2_text.bat",
    )

    def build_catalogue(self, source: Path, *, progress=None):
        """The base's catalogue, plus what this disc's banks are shaped like."""

        catalogue = super().build_catalogue(source, progress=progress)
        document = dict(catalogue.document)
        document["fonts"] = FONT_NOTE
        document["writable_containers"] = list(WRITABLE_TEXT_CONTAINERS)
        from mod_editor.games.contract import Catalogue

        return Catalogue(catalogue.schema, catalogue.lane_id, catalogue.source,
                         catalogue.targets, document)


def verify_build(source: Path, destination: Path,
                 receipt_document: Mapping[str, Any]) -> dict:
    """Re-derive, from the two images alone, that the build did what it claimed."""

    return TextLane().verify_build(Path(source), Path(destination), receipt_document)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.nflstreet1_ps2.text_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.nflstreet1_ps2.text_lane",
        description="Count and edit the TEXT banks on a NFL Street (PlayStation 2) disc.",
    )
    parser.add_argument("--source", help="the user's own SLUS-20841 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--recipe", help="a JSON recipe of string edits")
    parser.add_argument("--destination", help="the NEW image to write; it must not exist")
    parser.add_argument("--report", help="write the receipt and verdict to this JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan the edits and print the byte ranges; write nothing")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = TextLane()
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                source = lane.synthetic_source(Path(room))
                catalogue = lane.build_catalogue(source)
                edits = lane.conformance_edits(catalogue)
                destination = Path(room) / "out.iso"
                receipt = lane.build(source, destination,
                                     lane.compose_recipe(edits), catalogue)
                verdict = lane.verify(source, destination, receipt)
                print(f"SELFTEST slots={len(catalogue.targets)} "
                      f"verify={'PASS' if verdict.passed else 'FAIL'} \u2014 "
                      f"{verdict.summary}")
                return 0 if verdict.passed else 1
        if not arguments.source:
            parser.error("give --source a disc image, or --selftest")
        catalogue = lane.build_catalogue(
            Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
        if arguments.recipe:
            recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
            if arguments.dry_run or not arguments.destination:
                planned = lane.plan(Path(arguments.source), recipe, catalogue)
                print("PLAN " + json.dumps(planned.document, sort_keys=True)[:400])
                return 0
            receipt = lane.build(Path(arguments.source), Path(arguments.destination),
                                 recipe, catalogue)
            verdict = lane.verify(Path(arguments.source), Path(arguments.destination),
                                  receipt)
            if arguments.report:
                Path(arguments.report).write_text(
                    json.dumps({"receipt": receipt.document,
                                "verdict": {"passed": verdict.passed,
                                            "summary": verdict.summary}},
                               indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")
            print(f"BUILD verify={'PASS' if verdict.passed else 'FAIL'} \u2014 "
                  f"{verdict.summary}")
            return 0 if verdict.passed else 1
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    print("TEXT members=%d slots=%d listed=%d"
          % (document.get("members", 0), document.get("slots", 0),
             document.get("targets_listed", 0)))
    return 0


__all__ = ["CAPABILITY_ID", "FONT_NOTE", "LANE_ID", "PRELOAD_COPIES",
           "RECEIPT_SCHEMA", "RECIPE_SCHEMA", "SCHEMA", "TextLane",
           "WRITABLE_TEXT_CONTAINERS", "verify_build"]


if __name__ == "__main__":
    raise SystemExit(_main())
