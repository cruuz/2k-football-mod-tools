"""The disc's ``TEXT`` members: counted, measured, and rewritten in place.

``TEXT`` is what ``ea_terf.identify_member`` calls a member whose decompressed
bytes are printable NUL-separated strings.  NCAA Football 09's retail disc
carries **1,247 of them, 1,247 slots, 241,787 characters** [M] --
``EXAMS.DAT`` 1,238, ``JERSEY.DAT`` 7, ``OSDKSTRN.DAT`` 1 and ``GAMEDATA.DAT``
1.  The lane is the shared
:mod:`mod_editor.games._lanes.text_banks`; this file is what points it at this
disc and records what this disc's banks are shaped like.

Three measurements, and all three matter to a writer [M]
--------------------------------------------------------

* **Every one of the 1,247 members holds exactly one run.**  The slot histogram
  is ``{1: 1247}``, so no member on this disc is a multi-string bank.  Madden
  09's are a mix, and the same slot rule covers both.
* **Not one ends in a terminator**, where Madden 09's banks are a mix.
* **There is no padding anywhere** -- 0 spare bytes across all 1,247.

So a same-allocation writer for this disc has **no slack to start with**: a
replacement must be exactly the length it replaces, or shorter and pay for the
terminator it introduces.  Runs go from 15 to 50,519 bytes.  That is not a
limitation of this lane; it is what the disc is, and the budget on every target
says so before an edit is typed.  Shortening a string *creates* slack, and
because a slot's allocation counts the padding a previous edit left behind, the
next catalogue offers that room again.

Which containers are writable, and why
--------------------------------------

``EXAMS.DAT``, ``JERSEY.DAT`` and ``OSDKSTRN.DAT`` are named by **none** of the
three ``QL01`` preload caches [M], which is what makes them safe to write:
nothing carries a second copy of them for the game to read instead.
``GAMEDATA.DAT`` -- which holds one ``TEXT`` member beside its 137 playbook
databases -- **is** named, by ``FE.QKL`` and ``GAME.QKL``, and its directory is
copied twice and fifteen of its members once each [M]; editing one copy and not
the other would leave the game reading whichever it reached first, so this lane
refuses it and says which cache names it.  The list is read off the **user's own
image** by ``containers.preload_names`` rather than trusted from a table written
down here.

The catalogue still carries no string
-------------------------------------

A catalogue is a file that can be shipped, so the document is counts and
digests.  The strings themselves reach a screen only through the *targets*
built from the user's own image, or through :meth:`TextLane.preview`, which
re-reads them from the disc on demand.  A test asserts the point by searching
the serialised document for the synthetic fixture's own lines and failing if it
finds one.

``FONTS.DAT`` and ``UIS_FONT.DAT`` hold 17 ``FNTS`` fonts [M]; no font decoder
exists in this repository, so the glyphs a string is drawn with are out of
reach and this lane says so rather than implying the text is fully editable.

**Nothing here has been seen in a running game.**

Run it without a window::

    python3 -m mod_editor.games.ncaa09_ps2.text_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence, Tuple

from mod_editor.games._lanes.text_banks import (
    MAX_TARGETS,
    PREVIEW_STRINGS,
    PREVIEW_WIDTH,
    SLOT_PREFIX,
    TERMINATOR,
    TEXT_ENCODING,
    TextBankLane,
    TextError,
    encode_slot,
    is_text_member,
    measure,
    parse_slot_key,
    slot_key,
    slots_in,
    split_strings,
)
from mod_editor.games.contract import Refusal

from . import containers

CAPABILITY_ID = "ncaa09ps2.menus.text_members"
LANE_ID = "menus.text_members"
SCHEMA = "ncaa09_ps2_text_inventory/v1"
RECIPE_SCHEMA = "ncaa09_ps2_text_edit/v1"
RECEIPT_SCHEMA = "ncaa09_ps2_text_write/v1"

#: The containers holding ``TEXT`` members that this disc's preload caches name
#: [M].  Exactly one does: ``GAMEDATA.DAT``, in both ``FE.QKL`` and
#: ``GAME.QKL``.  The list a user's own image declares is read at catalogue time
#: by :func:`containers.preload_names` and takes precedence; this is the
#: measured floor, so an image whose caches this module cannot read still
#: refuses the one it is known to have to.
PRELOAD_COPIES: Mapping[str, Tuple[str, ...]] = {
    "GAMEDATA.DAT": ("FE.QKL", "GAME.QKL"),
}

#: The three containers that carry a writable ``TEXT`` member on this disc [M].
#: Named here for the document; the lane still discovers members by walking, so
#: an image with a bank somewhere else lists it rather than hiding it.
WRITABLE_TEXT_CONTAINERS = ("EXAMS.DAT", "JERSEY.DAT", "OSDKSTRN.DAT")

#: What the page says about the fonts it cannot reach.
FONT_NOTE = (
    "FONTS.DAT and UIS_FONT.DAT hold 17 FNTS font sets and no decoder for that format "
    "exists in this repository, so the glyphs a string is drawn with are out of reach "
    "here. A replacement is written in latin-1, the encoding EA stored these banks in; "
    "a character the shipped font has no glyph for will not draw, and this lane cannot "
    "tell you which those are."
)


class TextLane(TextBankLane):
    """Every ``TEXT`` member on the disc, measured; three containers' worth editable."""

    discs = containers
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "menus"
    page = "menus"
    title = "Text banks"
    classification = "offline-writer-proved"
    game_title = "NCAA Football 09 (PlayStation 2)"
    schema = SCHEMA
    recipe_schema = RECIPE_SCHEMA
    receipt_schema = RECEIPT_SCHEMA
    preload_copies = PRELOAD_COPIES
    validators = (
        "tools/validate_ncaa09_ps2_text.sh",
        "tools/validate_ncaa09_ps2_text.bat",
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
    """Re-derive, from the two images alone, that the build did what it claimed.

    The check itself is :meth:`TextBankLane.verify_build`, shared with Madden
    09's text lane; this is the module-level spelling a caller in this package
    uses.
    """

    return TextLane().verify_build(Path(source), Path(destination), receipt_document)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.ncaa09_ps2.text_lane --source DISC.iso``.

    With ``--recipe`` and ``--destination`` it also does the write: it plans,
    builds a NEW image, and runs the independent verifier over the result.  The
    source is opened read-only either way.
    """

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.ncaa09_ps2.text_lane",
        description="Count and edit the TEXT banks on an NCAA Football 09 (PS2) disc.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21752 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--preview", metavar="CONTAINER:INDEX:OFFSET",
                        help="print the first strings of one member, read from your own disc")
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
                destination = Path(room) / "written.iso"
                receipt = lane.build(source, destination, lane.compose_recipe(edits),
                                     catalogue)
                verdict = lane.verify(source, destination, receipt)
                print("NCAA09_TEXT_SELFTEST %s" % ("PASS" if verdict.passed else "FAIL"))
                if not verdict.passed:
                    print(verdict.summary, file=sys.stderr)
                    return 1
                document = dict(catalogue.document)
        else:
            if not arguments.source:
                parser.error("give --source DISC.iso, or --selftest")
            source = Path(arguments.source)
            catalogue = lane.build_catalogue(
                source, progress=lambda line: print(line, file=sys.stderr))
            if arguments.preview:
                wanted = arguments.preview
                target = catalogue.target(
                    wanted if wanted.startswith(SLOT_PREFIX) else SLOT_PREFIX + wanted)
                for line in lane.preview(source, target):
                    print(line)
            document = dict(catalogue.document)
        if arguments.out:
            Path(arguments.out).write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n")
        print("NCAA09_TEXT members=%d strings=%d bytes=%d listed=%d"
              % (document["text_members"], document["strings"], document["bytes"],
                 document["rows_listed"]))
        if arguments.selftest or not arguments.recipe:
            if arguments.destination and not arguments.selftest:
                parser.error("--destination needs --recipe")
            return 0
        recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
        if arguments.dry_run or not arguments.destination:
            plan = lane.plan(source, recipe, catalogue)
            for item in plan.declared_ranges:
                print("would write %d byte(s) at %d (%s)"
                      % (item.length, item.start, item.reason))
            print("NCAA09_TEXT_PLAN targets=%d bytes=%d"
                  % (len(plan.target_keys), plan.declared_bytes))
            return 0
        receipt = lane.build(source, Path(arguments.destination), recipe, catalogue)
        verdict = lane.verify(source, Path(arguments.destination), receipt)
        print(verdict.summary)
        if arguments.report:
            Path(arguments.report).write_text(
                json.dumps({"receipt": dict(receipt.document),
                            "verdict": {"passed": verdict.passed,
                                        "summary": verdict.summary,
                                        "document": dict(verdict.document)}},
                           indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8", newline="\n")
        print("NCAA09_TEXT_WRITE %s" % ("PASS" if verdict.passed else "FAIL"))
        return 0 if verdict.passed else 1
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = ["CAPABILITY_ID", "FONT_NOTE", "LANE_ID", "MAX_TARGETS", "PRELOAD_COPIES",
           "PREVIEW_STRINGS", "PREVIEW_WIDTH", "RECEIPT_SCHEMA", "RECIPE_SCHEMA", "SCHEMA",
           "SLOT_PREFIX", "TERMINATOR", "TEXT_ENCODING", "TextError", "TextLane",
           "WRITABLE_TEXT_CONTAINERS", "encode_slot", "is_text_member", "measure",
           "parse_slot_key", "slot_key", "slots_in", "split_strings", "verify_build"]


if __name__ == "__main__":
    raise SystemExit(_main())
