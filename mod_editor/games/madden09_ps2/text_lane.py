"""The disc's ``TEXT`` members: counted, measured, and rewritten in place.

``TEXT`` is what ``identify_member`` calls a member whose decompressed bytes are
printable NUL-separated strings, and Madden 09's retail disc carries 14,748 of
them -- most of the story generator's templates, plus menu and front-end
banks [M].  This lane lists them: which container, which member, how many
strings, how long, and the member's digest.

What it edits
-------------

A **string slot**: one NUL-separated run of characters inside a member,
addressed by its byte offset in that member.  On the retail disc a bank is one
slot -- the members carry no NUL at all [M], so the whole member is one string
-- while the synthetic fixture carries three, and the same rule covers both.

A slot is a **fixed allocation**: the room between it and the next string,
which is what the budget quotes.  A shorter replacement is padded to it with the
format's terminator, ``\\x00``, so the string the game reads ends where the
replacement ends and every byte after it inside the slot is a NUL.  A longer
replacement is refused with the length it has to fit.  Nothing moves: the
member keeps its exact byte count, so the container does, so the ISO extent
does, and the destination image is the source's exact size.  Because the
allocation counts the padding a previous edit left behind, shortening a string
does not spend it: the next catalogue offers the same room again.

Three containers holding string banks stay read-only, and the disc says which:
``/DATA/GAME.QKL`` and ``/DATA/FE.QKL`` are preload caches that **name** 29 and
28 ``/DATA`` files and carry a copy of at least some of them, and
``GAMEDATA.DAT``, ``LOADDATA.DAT`` and ``STADATA.DAT`` are among the names [M].
Editing one copy and not the other would leave the game reading whichever it
reached first, so a container either cache names is refused --
:func:`containers.preload_names` reads that list off the user's own image
rather than trusting a table written down here.  The six story and
online-strings containers are named in neither [M], which is what makes them
safe to write.

The catalogue still carries no string
-------------------------------------

The contract's third rule is that a catalogue holds names, offsets, lengths and
digests and never payload, and a catalogue is a file that can be shipped.  So
the **document** is counts and digests, exactly as before, and the strings
themselves reach a screen only through the *targets* built from the user's own
image -- or through :meth:`TextLane.preview`, which re-reads them from the disc
on demand.  Nothing decoded is written to this repository by this lane.

**Nothing here has been seen in a running game.**  The evidence is offline: a
destination image, an independent verifier that re-reads it, and a conformance
harness that proves the whole path on a synthetic disc.  No emulator has booted
a rebuilt Madden 09 disc, and this module does not claim one has.

Run it without a window::

    python3 -m mod_editor.games.madden09_ps2.text_lane --source DISC.iso

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

CAPABILITY_ID = "madden09ps2.menus.text_members"
LANE_ID = "menus.text_members"
SCHEMA = "madden09_ps2_text_inventory/v1"
RECIPE_SCHEMA = "madden09_ps2_text_edit/v1"
RECEIPT_SCHEMA = "madden09_ps2_text_write/v1"

#: The containers holding ``TEXT`` members that the retail disc's preload
#: caches name [M].  The list a user's own image declares is read at catalogue
#: time by :func:`containers.preload_names` and takes precedence; this is the
#: measured floor, so an image whose caches this module cannot read still
#: refuses the three it is known to have to.
PRELOAD_COPIES: Mapping[str, Tuple[str, ...]] = {
    "GAMEDATA.DAT": ("GAME.QKL", "FE.QKL"),
    "LOADDATA.DAT": ("FE.QKL",),
    "STADATA.DAT": ("GAME.QKL", "FE.QKL"),
}


class TextLane(TextBankLane):
    """Every ``TEXT`` member on the disc, measured; six containers' worth editable."""

    discs = containers
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "menus"
    page = "menus"
    title = "Text banks"
    classification = "offline-writer-proved"
    game_title = "Madden NFL 09 (PlayStation 2)"
    schema = SCHEMA
    recipe_schema = RECIPE_SCHEMA
    receipt_schema = RECEIPT_SCHEMA
    preload_copies = PRELOAD_COPIES
    validators = (
        "tools/validate_madden09_ps2_text.sh",
        "tools/validate_madden09_ps2_text.bat",
    )


def verify_build(source: Path, destination: Path,
                 receipt_document: Mapping[str, Any]) -> dict:
    """Re-derive, from the two images alone, that the build did what it claimed.

    The check itself is :meth:`TextBankLane.verify_build`, shared with every
    other text-bank lane on this stack; this is the module-level spelling
    callers in this package have always used.
    """

    return TextLane().verify_build(Path(source), Path(destination), receipt_document)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.madden09_ps2.text_lane --source DISC.iso``.

    With ``--recipe`` and ``--destination`` it also does the write: it plans,
    builds a NEW image, and runs the independent verifier over the result.  The
    source is opened read-only either way.
    """

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.text_lane",
        description="Count and edit the TEXT banks on a Madden NFL 09 (PS2) disc.",
    )
    parser.add_argument("--source", required=True, help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--preview", metavar="CONTAINER:INDEX:OFFSET",
                        help="print the first strings of one member, read from your own disc")
    parser.add_argument("--recipe", help="a JSON recipe of string edits, as compose_recipe writes")
    parser.add_argument("--destination", help="the NEW image to write; it must not exist")
    parser.add_argument("--report", help="write the build receipt and verdict to this JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan the edits and print the byte ranges; write nothing")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = TextLane()
    source = Path(arguments.source)
    try:
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
        print("TEXT members=%d strings=%d bytes=%d listed=%d"
              % (document["text_members"], document["strings"], document["bytes"],
                 document["rows_listed"]))
        if not arguments.recipe:
            if arguments.destination:
                parser.error("--destination needs --recipe: there is nothing to write without one")
            return 0
        recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
        if arguments.dry_run or not arguments.destination:
            plan = lane.plan(source, recipe, catalogue)
            for item in plan.declared_ranges:
                print("would write %d byte(s) at %d (%s)"
                      % (item.length, item.start, item.reason))
            print("TEXT_PLAN targets=%d bytes=%d"
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
        print("TEXT_WRITE %s" % ("PASS" if verdict.passed else "FAIL"))
        return 0 if verdict.passed else 1
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = ["CAPABILITY_ID", "LANE_ID", "MAX_TARGETS", "PRELOAD_COPIES", "PREVIEW_STRINGS",
           "PREVIEW_WIDTH", "RECEIPT_SCHEMA", "RECIPE_SCHEMA", "SCHEMA", "SLOT_PREFIX",
           "TERMINATOR", "TEXT_ENCODING", "TextError", "TextLane", "encode_slot",
           "is_text_member", "measure", "parse_slot_key", "slot_key", "slots_in",
           "split_strings", "verify_build"]


if __name__ == "__main__":
    raise SystemExit(_main())
