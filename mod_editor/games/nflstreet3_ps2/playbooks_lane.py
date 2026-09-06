"""NFL Street 3 (PlayStation 2)'s playbooks: the formations, set-ups, plays and the names they carry.

``/DATA/IGDATA.DAT`` holds 11 EA TDB database(s) and inside them the play library
this disc calls its playbook: **11 ``FORM`` formation row(s), 30 ``SETL``
set-ups, 176 ``PLYL`` plays, 91 ``PBST`` sets, 377 ``PBPL`` play
slots and 17 ``PBFM`` books** [M].

This lane catalogues them and edits **the names and the ordering**, which is the
part a user can change without knowing what a route number means.  The link
fields that wire a play to its set-up and a set-up to its formation are offered
too, with their measured ranges, and a value outside a field's own width is
refused by the width rather than by a guess.

**What is not offered, and why it is a measured decision.**
``PBST`` on this disc is **5 fields and 127 bits** against NFL
Street's 27 and 511: the eleven ``ax``/``ay`` route-point pairs are
gone entirely [M].  What Street 3 added instead is ``PBFM``'s four
``FAU1``..``FAU4`` audible slots and a ``name`` on ``PBPL``, and both
are offered here.  So this disc's playbook page can rename a play
slot directly, where NFL Street's has to rename the play it calls.

Why a record edit is a bounded write here
-----------------------------------------

The ``PBST``/``PBPL``/``PLYL``/``SETL``/``FORM``/``PBFM`` rows are fixed-stride
records in a TDB, so a name that fits its field changes no length.
``IGDATA.DAT``'s members are ````LZH1``-packed inside a ``COMP`` chunk``, and a re-pack that grew would move
the directory, so the lane prices the write first and refuses a member that
would not fit -- and rewrites every preload-cache copy the edit disturbs.

**Nothing here has been seen in a running game.**

Run it without a window::

    python3 -m mod_editor.games.nflstreet3_ps2.playbooks_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence, Tuple

from mod_editor.games._lanes.tdb_records import FieldSpec, TdbRecordLane
from mod_editor.games.contract import Refusal

from . import containers

CAPABILITY_ID = "nflstreet3ps2.playbooks.play_databases"
LANE_ID = "playbooks.play_databases"
SCHEMA = "nflstreet3_ps2_playbooks/v1"
RECIPE_SCHEMA = "nflstreet3_ps2_playbook_edit/v1"
RECEIPT_SCHEMA = "nflstreet3_ps2_playbook_write/v1"

#: How many rows are listed.  The disc holds 702 rows across the six tables [M].
MAX_ROW_TARGETS = 8000

#: The six play tables, in the order a page shows them: book, formation,
#: set-up, play, set, play slot.
PLAY_TABLES = ("PBFM", "FORM", "SETL", "PLYL", "PBST", "PBPL")

#: What the page says about the fields it does not offer.
UNOFFERED_NOTE = (
    "Every field the six play tables declare on this disc is offered except the internal PLF_ and SLF_ flag words, which are 18-bit and 1-bit link flags whose meaning nothing here has established [M]."
)

#: The editor controls each table's row offers.
PLAYBOOK_FIELDS = {
    "PBFM": (
        ("name", "Name",
         "What the play list calls this row.", None),
        ("FTYP", "Book type",
         "Which kind of book this is.", None),
        ("FAU1", "Audible 1",
         "The first audible this book offers; a field NFL Street's PBFM does not have [M].", None),
        ("FAU2", "Audible 2",
         "The second audible this book offers.", None),
        ("FAU3", "Audible 3",
         "The third audible this book offers.", None),
        ("FAU4", "Audible 4",
         "The fourth audible this book offers.", None),
        ("ord_", "Order",
         "Where it sits in the list.", None),
    ),
    "FORM": (
        ("name", "Name",
         "What the play list calls this row.", None),
        ("FTYP", "Formation type",
         "Which kind of formation this is.", None),
    ),
    "SETL": (
        ("name", "Name",
         "What the play list calls this row.", None),
        ("FORM", "Formation",
         "Which formation this set-up uses.", None),
        ("SETT", "Set-up type",
         "Which kind of set-up this is.", None),
        ("poso", "Position order",
         "The ordering the set-up draws with.", None),
    ),
    "PLYL": (
        ("name", "Name",
         "What the play list calls this row.", None),
        ("SETL", "Set-up",
         "Which set-up this play is called from.", None),
        ("PLYT", "Play type",
         "Which kind of play this is.", None),
        ("risk", "Risk",
         "The risk value the play carries.", None),
        ("vpos", "Vertical position",
         "Where the play sits in the call list.", None),
    ),
    "PBST": (
        ("name", "Name",
         "What the play list calls this row.", None),
        ("PBFM", "Book",
         "Which book this set belongs to.", None),
        ("SETL", "Set-up",
         "Which set-up this set uses.", None),
        ("ord_", "Order",
         "Where it sits in the list.", None),
    ),
    "PBPL": (
        ("name", "Name",
         "What the play list calls this row.", None),
        ("PBST", "Set",
         "Which set this slot belongs to.", None),
        ("PLYL", "Play",
         "Which play this slot calls.", None),
        ("ord_", "Order",
         "Where it sits in the set.", None),
    ),
}


class PlaybooksLane(TdbRecordLane):
    """The play library: formations, set-ups, plays, and the names they carry."""

    discs = containers
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "scripts_config"
    page = "playbooks"
    title = "Playbooks and play names"
    classification = "offline-writer-proved"
    schema = SCHEMA
    recipe_schema = RECIPE_SCHEMA
    receipt_schema = RECEIPT_SCHEMA
    tdb_containers = (containers.GAME_DATA_CONTAINER,)
    writable_containers = (containers.GAME_DATA_CONTAINER,)
    editable_tables = PLAY_TABLES
    editable_fields = PLAYBOOK_FIELDS
    max_targets = 400
    max_row_targets = MAX_ROW_TARGETS
    validators = (
        "tools/validate_nflstreet3_ps2_playbooks.sh",
        "tools/validate_nflstreet3_ps2_playbooks.bat",
    )

    def row_label(self, table: str, member: Optional[int], index: int,
                  values: Mapping[str, Any]) -> str:
        name = str(values.get("name") or "").strip()
        where = "bare" if member is None else f"member {member}"
        return (f"{where} · {table.lower()} · {name}" if name
                else f"{where} · {table.lower()} {index}")

    def build_catalogue(self, source: Path, *, progress=None):
        catalogue = super().build_catalogue(source, progress=progress)
        document = dict(catalogue.document)
        document["play_tables"] = list(PLAY_TABLES)
        document["unoffered_fields"] = UNOFFERED_NOTE
        from mod_editor.games.contract import Catalogue

        return Catalogue(catalogue.schema, catalogue.lane_id, catalogue.source,
                         catalogue.targets, document)

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "nflstreet3_ps2-playbooks-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue):
        from mod_editor.games.contract import Edit

        for target in catalogue.targets:
            if not target.key.startswith(self.row_prefix):
                continue
            shape = {item.key: item for item in target.fields}
            if "name" not in shape:
                continue
            budget = shape["name"].maximum or 8
            return (Edit(target.key, {"name": "CONFORM"[:max(1, int(budget))]}),)
        raise Refusal("this catalogue lists no editable play row, so there is no "
                      "write to prove.")



def verify_build(source: Path, destination: Path,
                 receipt_document: Mapping[str, Any]) -> dict:
    """Re-derive, from the two images alone, that the build did what it claimed."""

    return PlaybooksLane().verify_build(Path(source), Path(destination), receipt_document)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.nflstreet3_ps2.playbooks_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.nflstreet3_ps2.playbooks_lane",
        description="Catalogue and edit the playbooks on a NFL Street 3 (PlayStation 2) disc.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21482 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--recipe", help="a JSON recipe of record edits")
    parser.add_argument("--destination", help="the NEW image to write; it must not exist")
    parser.add_argument("--report", help="write the receipt and verdict to this JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan the edits and print the byte ranges; write nothing")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = PlaybooksLane()
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
                print(f"SELFTEST rows={len(catalogue.targets)} "
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
    print("PLAYBOOKS databases=%d tables=%d rows_listed=%d"
          % (document.get("databases", 0), document.get("tables", 0),
             document.get("row_targets_listed", 0)))
    return 0


__all__ = ["CAPABILITY_ID", "LANE_ID", "MAX_ROW_TARGETS", "PLAYBOOK_FIELDS",
           "PLAY_TABLES", "PlaybooksLane", "RECEIPT_SCHEMA", "RECIPE_SCHEMA",
           "SCHEMA", "UNOFFERED_NOTE", "verify_build"]


if __name__ == "__main__":
    raise SystemExit(_main())
