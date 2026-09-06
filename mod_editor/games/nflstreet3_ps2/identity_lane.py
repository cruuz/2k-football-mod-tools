"""NFL Street 3 (PlayStation 2)'s team identity: the names, the colour slots and the logo id.

The 32 team databases in ``/DATA/DB_TEAMS.DAT`` each carry one ``TEAM`` row,
and that row is the whole of a team's identity on this disc: its display name,
its long name, its three-letter short name, the three palette slots the kit is
drawn from, and the id of the logo the front end draws.  This lane writes that
row; the ``PLAY`` rows beside it belong to the Names, Numbers & Faces page, so
one page owns one set of bytes.

What the disc actually holds [M]
--------------------------------

* **32 ``TEAM`` rows**, one per database, 22 fields and 447 bits each.
* ``TDNA`` is 136 bits, ``TLNA`` 120, ``TSNA`` 56 -- **17, 15 and 7 bytes**, so the
  budgets are 16, 14 and 6 characters with one byte for the terminator.  These
  three widths are the **only** part of ``TEAM`` that is identical on both NFL
  Street discs [M].
* ``TMC1``, ``TMC2`` and ``TMC3`` are 7-bit values in 9..126, 2..127 and 10..127 across the 32
  rows [M].  Seven bits is not a colour: they are **indices into the palette
  table** (``CPAL``, 128 rows, in ``TEMPLATE.DAT`` [M]), so this page offers the
  slot number and does not pretend to offer a colour picker.
* ``TLGL`` runs 1..32 [M] -- one logo per team -- and the art it names is in
  ``UIS_TMLO.DAT``, which this module's logo-art lane writes.
* Three **team rating** fields survive from NFL Street's eleven:
  ``TROF``, ``TRDE`` and ``TROV``, running 63..83 across the 32
  rows [M].  ``TRQB``, ``TRRB``, ``TROL``, ``TRDL``, ``TRLB``,
  ``TRDB``, ``TRST`` and ``TWRR`` are gone, along with ``LGID``,
  ``SGID``, ``TMSA``, ``TLSA``, ``TLGS``, ``TGPT``, ``TGRP``,
  ``TDPB``, ``TOPB``, ``TFTL``, ``TRDL``, ``TVQS`` and ``TAss``
  -- twenty fields in all [M].  ``CTDL`` is the one field Street 3
  added, and it is 1 on all 32 rows.

**The colour is not on this page and the reason is measured.**  A control
labelled "primary colour" over a 7-bit index would either be a lie or would
need the palette read back and rendered; the palette is 128 rows in a container
this lane does not open.  What is offered is the index, with its range, and the
page says where the palette lives.

Why a record edit is a bounded write here
-----------------------------------------

Exactly as the roster lane's: a TDB field owns a fixed run of bits, the
container's members are stored rather than packed [M], every preload-cache copy
the edit disturbs is rewritten, and all **1,038** checksum slots on this disc
already verify before anything is written [M].

**Nothing here has been seen in a running game.**

Run it without a window::

    python3 -m mod_editor.games.nflstreet3_ps2.identity_lane --source DISC.iso

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

CAPABILITY_ID = "nflstreet3ps2.identity.team_records"
LANE_ID = "identity.team_records"
SCHEMA = "nflstreet3_ps2_team_identity/v1"
RECIPE_SCHEMA = "nflstreet3_ps2_team_identity_edit/v1"
RECEIPT_SCHEMA = "nflstreet3_ps2_team_identity_write/v1"

#: The highest value a team rating carries on this disc [M].
RATING_MAX = 100

#: How many rows are listed.  32 teams; the cap is above that so every one shows.
MAX_ROW_TARGETS = 400

#: Where the palette the three colour slots index into lives [M].
PALETTE_NOTE = (
    "TMC1, TMC2 and TMC3 are 7-bit indices, not colours: the palette they index is "
    "CPAL in TEMPLATE.DAT, 128 rows of 13 fields [M]. This page offers the index and "
    "its measured range; it does not draw a colour it has not read."
)

#: The editor controls one ``TEAM`` row offers.
TEAM_FIELDS: Tuple[FieldSpec, ...] = (
    ("TDNA", "Display name",
     "The name the front end draws for this team.", None),
    ("TLNA", "Long name",
     "The longer form the disc keeps beside it.", None),
    ("TSNA", "Short name",
     "The three-letter form the scoreboard uses.", None),
    ("TLGL", "Logo id",
     "Which logo this team draws; 1..32 on this disc, in an 8-bit field where NFL Street's is 7 [M].", None),
    ("TMC1", "Palette slot 1",
     "Index into CPAL, not a colour; 9..126 on this disc [M].", None),
    ("TMC2", "Palette slot 2",
     "Index into CPAL; 2..127 on this disc [M].", None),
    ("TMC3", "Palette slot 3",
     "Index into CPAL; 10..127 on this disc [M].", None),
    ("TROF", "Offence rating",
     "The team rating the front end shows; 70..83 here [M].", RATING_MAX),
    ("TRDE", "Defence rating",
     "The team rating the front end shows; 63..81 here [M].", RATING_MAX),
    ("TROV", "Overall rating",
     "The team rating the front end shows; 71..80 here [M].", RATING_MAX),
    ("CGID", "Conference id",
     "Which conference the team is filed under.", None),
    ("DGID", "Division id",
     "Which division the team is filed under.", None),
    ("TGID", "Team id",
     "The id every other table joins on; change it and the roster stops pointing at this team.", None),
)


class IdentityLane(TdbRecordLane):
    """The 32 ``TEAM`` rows: names, colour slots and logo id."""

    discs = containers
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "colors"
    page = "identity"
    title = "Team names, colour slots and logo ids"
    classification = "offline-writer-proved"
    schema = SCHEMA
    recipe_schema = RECIPE_SCHEMA
    receipt_schema = RECEIPT_SCHEMA
    tdb_containers = (containers.TEAM_DATABASE_CONTAINER,)
    writable_containers = (containers.TEAM_DATABASE_CONTAINER,)
    editable_tables = ("TEAM",)
    editable_fields = {"TEAM": TEAM_FIELDS}
    max_targets = 400
    max_row_targets = MAX_ROW_TARGETS
    validators = (
        "tools/validate_nflstreet3_ps2_identity.sh",
        "tools/validate_nflstreet3_ps2_identity.bat",
    )

    def row_label(self, table: str, member: Optional[int], index: int,
                  values: Mapping[str, Any]) -> str:
        name = str(values.get("TDNA") or "").strip()
        where = "bare" if member is None else f"team {member}"
        return f"{where} · {name}" if name else f"{where} · team row {index}"

    def row_detail(self, table: str, values: Mapping[str, Any]) -> str:
        bits = []
        short = str(values.get("TSNA") or "").strip()
        if short:
            bits.append(short)
        if values.get("TLGL") is not None:
            bits.append(f"logo {values['TLGL']}")
        slots = [values.get(key) for key in ("TMC1", "TMC2", "TMC3")]
        if any(slot is not None for slot in slots):
            bits.append("palette " + "/".join(str(slot) for slot in slots
                                              if slot is not None))
        return " \u00b7 ".join(bits)

    def build_catalogue(self, source: Path, *, progress=None):
        catalogue = super().build_catalogue(source, progress=progress)
        document = dict(catalogue.document)
        document["palette"] = PALETTE_NOTE
        document["logo_art_container"] = "UIS_TMLO.DAT"
        from mod_editor.games.contract import Catalogue

        return Catalogue(catalogue.schema, catalogue.lane_id, catalogue.source,
                         catalogue.targets, document)

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "nflstreet3_ps2-identity-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue):
        from mod_editor.games.contract import Edit

        for target in catalogue.targets:
            if not target.key.startswith(self.row_prefix) or ":TEAM:" not in target.key:
                continue
            shape = {item.key: item for item in target.fields}
            values = {}
            if "TSNA" in shape:
                values["TSNA"] = "CNF"
            if "TMC1" in shape:
                values["TMC1"] = 42
            if values:
                return (Edit(target.key, values),)
        raise Refusal("this catalogue lists no editable team row, so there is no "
                      "write to prove.")



def verify_build(source: Path, destination: Path,
                 receipt_document: Mapping[str, Any]) -> dict:
    """Re-derive, from the two images alone, that the build did what it claimed."""

    return IdentityLane().verify_build(Path(source), Path(destination), receipt_document)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.nflstreet3_ps2.identity_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.nflstreet3_ps2.identity_lane",
        description="Catalogue and edit the team identity rows on a NFL Street 3 (PlayStation 2) disc.",
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
    lane = IdentityLane()
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
    print("IDENTITY databases=%d tables=%d rows_listed=%d"
          % (document.get("databases", 0), document.get("tables", 0),
             document.get("row_targets_listed", 0)))
    return 0


__all__ = ["CAPABILITY_ID", "IdentityLane", "LANE_ID", "MAX_ROW_TARGETS",
           "PALETTE_NOTE", "RATING_MAX", "RECEIPT_SCHEMA", "RECIPE_SCHEMA",
           "SCHEMA", "TEAM_FIELDS", "verify_build"]


if __name__ == "__main__":
    raise SystemExit(_main())
