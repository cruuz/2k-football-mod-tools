"""NFL Street (PlayStation 2)'s per-team rosters — catalogued, and edited.

``/DATA/DB_TEAMS.DAT`` is not one league database: it is **32 separate EA TDB
databases, one per team**, each carrying a ``PLAY`` table, a ``TEAM`` table and
a ``DCHT`` depth chart [M].  A player's team here **is which of the 32
databases he is in**; there is no league-wide roster table to sort.

This lane catalogues all 32 and edits their ``PLAY`` rows.  The ``TEAM`` row
beside them belongs to the Text & Team Identity page's lane, so one page owns
one set of bytes.

What the disc actually holds [M]
--------------------------------

* **402 player rows** across the 32 databases -- NFL Street fields seven a
  side, so a squad here is a fraction of a Madden roster's.
* **415 depth-chart rows**, 4 fields and 63 bits each.
* ``PLAY`` is **65 fields and 671 bits**; NFL Street 3's is 84 fields and 831 bits, and
  64 field names are common to the two with **none at the same bit offset** [M].

**The ratings are seven bits and the scale tops out at 100.**  Reading every
row off the disc settles what that means rather than assuming Madden's 0..99:
the highest value any attribute field carries on this disc is **100**, and the
field would hold 127 [M].  So the spinner's bound is 100, the disc's own, and
the document records the measurement it came from.

**There is no age.**  ``PAGE`` is 6 bits and **0 on every one of the 402
rows** [M] -- a street baller has no listed age -- so this lane does not offer
it.  The same measurement is why ``PLTO``, ``PRLT``, ``PUCL``, ``PRTY`` and ``PLIG`` are not offered either: each is 0 on every row [M].

Why a record edit is a bounded write here
-----------------------------------------

A TDB field owns a fixed run of bits in a fixed-stride record, so the
*decompressed* database comes back the same size.  ``DB_TEAMS.DAT``'s members
are **stored, not packed** [M], so the stored size cannot move either and the
container's directory stays exactly where it is.  The lane does not rely on
that: it prices the write before making it, refuses a member that would grow
past the slot it owns, and rewrites every preload-cache copy the edit disturbs
(:mod:`mod_editor.games._lanes.preload_coherence`).

The four checksums EA stores in each database are recomputed on every write and
re-derived from the destination's own bytes by the verifier -- which is a check
with teeth before the writer existed, because all **570** checksum slots on
this disc already hold the value they recompute to [M].

**Nothing here has been seen in a running game.**  The evidence is offline: a
destination image, an independent verifier that re-reads it, and a conformance
harness that proves the whole path on a synthetic disc.

Run it without a window::

    python3 -m mod_editor.games.nflstreet1_ps2.database_lane --source DISC.iso

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

CAPABILITY_ID = "nflstreet1ps2.players.team_databases"
LANE_ID = "players.team_databases"
SCHEMA = "nflstreet1_ps2_team_databases/v1"
RECIPE_SCHEMA = "nflstreet1_ps2_team_database_edit/v1"
RECEIPT_SCHEMA = "nflstreet1_ps2_team_database_write/v1"

#: The containers this lane opens, in the order a report lists them [M].
DATABASE_CONTAINERS = (
    containers.TEAM_DATABASE_CONTAINER,
    containers.GAME_DATA_CONTAINER,
    containers.TEMPLATE_CONTAINER,
)

#: The one container this lane writes.
WRITABLE_CONTAINER = containers.TEAM_DATABASE_CONTAINER

#: The highest value any attribute field carries on this disc [M].  The fields
#: are 7 bits and would hold 127; the disc's own ceiling is what the editor
#: uses, and it is not Madden's 99.
RATING_MAX = 100

#: The highest jersey number on the disc [M].
JERSEY_MAX = 99

#: How many database rows the page lists.  The disc holds 38 [M].
MAX_DATABASE_TARGETS = 400

#: How many player rows are listed as editable targets.  The disc holds 402
#: [M] and the cap is far above that, so a retail disc lists every one.
MAX_ROW_TARGETS = 20000

#: The editor controls one ``PLAY`` row offers: ``(field, label, help, max)``.
#: ``max`` of ``None`` means the field's own bit width is the bound, which is
#: the honest answer wherever the scale has not been established.  A field the
#: table does not declare is skipped, so this list is safe to share across the
#: disc's three ``PLAY`` schemas.
PLAYER_FIELDS: Tuple[FieldSpec, ...] = (
    ("PFNA", "First name",
     "The player's first name, as the game draws it.", None),
    ("PLNA", "Last name",
     "The player's last name.", None),
    ("PNKN", "Nickname",
     "The street name the commentary and the HUD use.", None),
    ("PJEN", "Jersey number",
     "The number on the shirt.", JERSEY_MAX),
    ("PPOS", "Position",
     "The position code this disc stores; 0..18 are in use [M].", None),
    ("POVR", "Overall",
     "The headline rating.", RATING_MAX),
    ("PSPD", "Speed",
     "How fast he runs.", RATING_MAX),
    ("PAGI", "Agility",
     "How sharply he changes direction.", RATING_MAX),
    ("PAWR", "Awareness",
     "How well he reads the play.", RATING_MAX),
    ("PCTH", "Catching",
     "How reliably he catches.", RATING_MAX),
    ("PTAK", "Tackling",
     "How reliably he tackles.", RATING_MAX),
    ("PBLK", "Blocking",
     "How well he blocks.", RATING_MAX),
    ("PBTK", "Break tackle",
     "How well he breaks a tackle.", RATING_MAX),
    ("PCOV", "Coverage",
     "How well he covers a receiver.", RATING_MAX),
    ("PCEL", "Style",
     "The style meter this disc keeps beside the ratings.", None),
    ("PPSS", "Passing",
     "How well he throws.", RATING_MAX),
    ("PDFT", "Trick handling",
     "The trick rating the disc stores for him.", RATING_MAX),
    ("PHGT", "Height",
     "Stored height, in the units the disc uses.", None),
    ("PWGT", "Weight",
     "Stored weight, in the units the disc uses.", None),
    ("PSKI", "Skin tone",
     "Which skin index the model uses.", None),
    ("PHAR", "Hair",
     "Which hair asset the model uses.", None),
    ("PHAT", "Headwear",
     "Which head asset the model wears.", None),
    ("PSHO", "Shoes",
     "Which shoe asset the model wears.", None),
    ("PGID", "Player id",
     "The id every other table joins on; change it and the depth chart stops pointing at him.", None),
)

#: What the page says about the fields it does not offer.
UNOFFERED_NOTE = (
    "PAGE is 0 on all 402 rows and PRFC is 63 on all 402 -- the field's own ceiling -- so neither is offered; a spinner over a column that never varies is a control that can only break something. PLTO, PRLT, PUCL, PRTY and PLIG are constant 0 as well [M]."
)


class DatabaseLane(TdbRecordLane):
    """Every EA TDB on the disc, catalogued; the 32 team rosters, editable."""

    discs = containers
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "players_rosters"
    page = "rosters"
    title = "Team rosters"
    classification = "offline-writer-proved"
    schema = SCHEMA
    recipe_schema = RECIPE_SCHEMA
    receipt_schema = RECEIPT_SCHEMA
    tdb_containers = DATABASE_CONTAINERS
    writable_containers = (WRITABLE_CONTAINER,)
    editable_tables = ("PLAY",)
    editable_fields = {"PLAY": PLAYER_FIELDS}
    max_targets = MAX_DATABASE_TARGETS
    max_row_targets = MAX_ROW_TARGETS
    validators = (
        "tools/validate_nflstreet1_ps2_databases.sh",
        "tools/validate_nflstreet1_ps2_databases.bat",
    )

    def row_label(self, table: str, member: Optional[int], index: int,
                  values: Mapping[str, Any]) -> str:
        """A player by the name the row carries, or by his slot when it is blank."""

        first = str(values.get("PFNA") or "").strip()
        last = str(values.get("PLNA") or "").strip()
        name = " ".join(part for part in (first, last) if part)
        where = "bare" if member is None else f"team {member}"
        return f"{where} · {name}" if name else f"{where} · play {index}"

    def row_detail(self, table: str, values: Mapping[str, Any]) -> str:
        bits = []
        if values.get("PJEN") is not None:
            bits.append(f"#{values['PJEN']}")
        if values.get("POVR") is not None:
            bits.append(f"overall {values['POVR']}")
        nick = str(values.get("PNKN") or "").strip()
        if nick:
            bits.append(f"\u201c{nick}\u201d")
        return " \u00b7 ".join(bits)

    def read_only_reason(self, container_name: str,
                         cached: Optional[Mapping[str, Sequence[str]]] = None) -> str:
        if container_name == containers.GAME_DATA_CONTAINER:
            return (f"{container_name} holds the playbooks; the Playbooks & Plays page "
                    f"owns those bytes, so this page lists them and does not write them.")
        if container_name == containers.TEMPLATE_CONTAINER:
            return (f"{container_name} holds the fresh-profile templates -- a save's "
                    f"starting state rather than the league -- so this page lists them "
                    f"and does not write them.")
        return super().read_only_reason(container_name, cached)

    def build_catalogue(self, source: Path, *, progress=None):
        """The base's catalogue, plus what this disc's ``PLAY`` rows are shaped like."""

        catalogue = super().build_catalogue(source, progress=progress)
        document = dict(catalogue.document)
        document["rating_maximum"] = RATING_MAX
        document["rating_maximum_note"] = (
            f"measured: the highest value any attribute field carries on this disc is "
            f"{RATING_MAX}, against the 127 the 7-bit field would hold")
        document["unoffered_fields"] = UNOFFERED_NOTE
        from mod_editor.games.contract import Catalogue

        return Catalogue(catalogue.schema, catalogue.lane_id, catalogue.source,
                         catalogue.targets, document)

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "nflstreet1_ps2-rosters-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue):
        from mod_editor.games.contract import Edit

        for target in catalogue.targets:
            if not target.key.startswith(self.row_prefix):
                continue
            if containers.TEAM_DATABASE_CONTAINER not in target.key:
                continue
            shape = {item.key: item for item in target.fields}
            values = {}
            if "PJEN" in shape:
                values["PJEN"] = 17
            if "POVR" in shape:
                values["POVR"] = 84
            if "PNKN" in shape:
                values["PNKN"] = "CONFORM"
            if values:
                return (Edit(target.key, values),)
        raise Refusal("this catalogue lists no editable player row, so there is no "
                      "write to prove.")


def verify_build(source: Path, destination: Path,
                 receipt_document: Mapping[str, Any]) -> dict:
    """Re-derive, from the two images alone, that the build did what it claimed."""

    return DatabaseLane().verify_build(Path(source), Path(destination), receipt_document)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.nflstreet1_ps2.database_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.nflstreet1_ps2.database_lane",
        description="Catalogue and edit the team rosters on a NFL Street (PlayStation 2) disc.",
    )
    parser.add_argument("--source", help="the user's own SLUS-20841 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--recipe", help="a JSON recipe of record edits")
    parser.add_argument("--destination", help="the NEW image to write; it must not exist")
    parser.add_argument("--report", help="write the receipt and verdict to this JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan the edits and print the byte ranges; write nothing")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = DatabaseLane()
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
    print("DATABASES databases=%d tables=%d rows_listed=%d"
          % (document.get("databases", 0), document.get("tables", 0),
             document.get("row_targets_listed", 0)))
    return 0


__all__ = ["CAPABILITY_ID", "DATABASE_CONTAINERS", "DatabaseLane", "JERSEY_MAX",
           "LANE_ID", "MAX_DATABASE_TARGETS", "MAX_ROW_TARGETS", "PLAYER_FIELDS",
           "RATING_MAX", "RECEIPT_SCHEMA", "RECIPE_SCHEMA", "SCHEMA",
           "UNOFFERED_NOTE", "WRITABLE_CONTAINER", "verify_build"]


if __name__ == "__main__":
    raise SystemExit(_main())
