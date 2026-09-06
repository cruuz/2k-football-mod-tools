"""The 432 schools' names, their conferences, their stadiums and their coaches.

Every one of them lives in **one** database: ``/DATA/LEAGUE.DAT`` member 0, the
league database, whose 25 tables carry the whole competition [M].  This lane
edits the names in five of them:

===========  ======  =========================================================
table          rows  what this lane writes
===========  ======  =========================================================
``TEAM``        432  ``TDNA`` (22 bytes), ``TMNA`` (18), ``TSNA`` (7)
``CONF``         25  ``CNAM`` (20 bytes)
``DIVI``         10  ``DNAM`` (20)
``STAD``        242  ``SNAM`` (30), ``STNN`` (18), ``SCIT`` (21), ``SSTA`` (15),
                     and ``SCAP``, a 17-bit capacity
``COCH``        315  ``CLFN`` (10 bytes), ``CLLN`` (13)
===========  ======  =========================================================

What is **not** here, and why it is a measurement rather than a gap
------------------------------------------------------------------

Madden 09's identity writer writes ``TDNA``, ``TLNA``, ``TSNA``, ``TMNC`` and
six colour bytes.  On this disc [M]:

* **``TLNA`` and ``TMNC`` do not exist.**  NCAA's ``TEAM`` has 74 fields, 29 of
  them shared with Madden's 65, and neither of those two is among them.  What
  is here instead is ``TMNA``, an 18-byte name Madden has no field for.
* **No colour field exists at all.**  ``TBCR``/``TBCG``/``TBCB`` and
  ``TB2R``/``TB2G``/``TB2B`` are all absent.  A 64-row ``PACL`` palette
  (``CRED``, ``CGRN``, ``CBLU`` per ``PCID``) *is* on the disc, and so are the
  create-a-school ``CTCD`` and ``CTUN`` tables with their packed 32-bit colour
  words -- **with 0 rows**, because a created school is user data.  Which
  ``TEAM`` field selects a school's palette entry is **not established**:
  ``TPID`` is 7 bits wide and ``PACL`` has 64 rows, which fits and is not proof
  [A].  So this lane reads ``PACL`` into the catalogue, offers **no colour
  control**, and says so rather than drawing a colour picker over a guess.

The coaches, by contrast, *do* have names on this disc even though the players
do not [M] -- ``CLFN`` and ``CLLN`` in ``COCH`` -- which is why the Names,
Numbers & Faces page has no name editor and this one has.

How the write is bounded
------------------------

A TDB field owns a fixed run of bits in a fixed-stride record, so the
decompressed database comes back its exact size.  ``LEAGUE.DAT`` member 0 is
``RLE1``-packed, so the *stored* size can move: measured on the retail disc, a
name edit moves the encoding by **-13 to +1 bytes** [M], and the slot member 0
owns is one byte larger than the bytes EA put in it.  The lane prices the
re-pack before writing and refuses, by name and by the number of bytes over,
anything that would not fit the slot -- because growing it would move all 454
members after it.

Member 0 is also **copied into ``PL.QKL``**, once as a member and twice (with
``FE.QKL``) as a container directory [M].  Every copy the edit disturbs is
rewritten from the container's own new bytes, and the verifier re-reads them
off the **destination** rather than believing the receipt.

**Nothing here has been seen in a running game.**

Run it without a window::

    python3 -m mod_editor.games.ncaa09_ps2.identity_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_tdb
from mod_editor.games._lanes.tdb_records import FieldSpec, TdbRecordLane
from mod_editor.games.contract import Catalogue, Edit, Refusal

from . import containers

CAPABILITY_ID = "ncaa09ps2.identity.league_records"
LANE_ID = "identity.league_records"
SCHEMA = "ncaa09_ps2_identity_inventory/v1"
RECIPE_SCHEMA = "ncaa09_ps2_identity_edit/v1"
RECEIPT_SCHEMA = "ncaa09_ps2_identity_write/v1"

#: The one container, and the one member inside it, this lane writes [M].
WRITABLE_CONTAINER = containers.LEAGUE_CONTAINER
LEAGUE_MEMBER = 0

#: How many rows are listed as editable targets.  The five tables hold
#: 432 + 25 + 10 + 242 + 315 = 1,024 rows on the retail disc [M].
MAX_ROW_TARGETS = 4000

#: How many capacity a stadium declares.  ``SCAP`` is 17 bits, so the field's
#: own ceiling is 131,071 -- above every stadium there has ever been, which is
#: why the bound is the field's and not a number invented here.
STADIUM_CAPACITY_MAX = None

TEAM_FIELDS: Tuple[FieldSpec, ...] = (
    ("TDNA", "School name",
     "The name the school is drawn under. NCAA 09's field is 22 bytes where "
     "Madden 09's TDNA is 17.", None),
    ("TMNA", "Long name",
     "The 18-byte name this disc carries and Madden 09 has no field for.", None),
    ("TSNA", "Abbreviation", "The two-to-six letter short code.", None),
)

CONFERENCE_FIELDS: Tuple[FieldSpec, ...] = (
    ("CNAM", "Conference name", "What the conference is called.", None),
)

DIVISION_FIELDS: Tuple[FieldSpec, ...] = (
    ("DNAM", "Division name", "What the division is called.", None),
)

STADIUM_FIELDS: Tuple[FieldSpec, ...] = (
    ("SNAM", "Stadium name", "The stadium's full name.", None),
    ("STNN", "Short name", "The short form a scoreboard has room for.", None),
    ("SCIT", "City", "The city the stadium is in.", None),
    ("SSTA", "State", "The state or region.", None),
    ("SCAP", "Capacity",
     "Seats, as the seventeen-bit field stores them. The bound is the field's own "
     "and not a number invented here.", STADIUM_CAPACITY_MAX),
)

COACH_FIELDS: Tuple[FieldSpec, ...] = (
    ("CLFN", "First name", "The coach's first name. The field is 10 bytes.", None),
    ("CLLN", "Last name", "The coach's last name. The field is 13 bytes.", None),
)

EDITABLE_FIELDS: Mapping[str, Tuple[FieldSpec, ...]] = {
    "TEAM": TEAM_FIELDS,
    "CONF": CONFERENCE_FIELDS,
    "DIVI": DIVISION_FIELDS,
    "STAD": STADIUM_FIELDS,
    "COCH": COACH_FIELDS,
}

#: What the page says where Madden 09 draws two colour pickers.  Repeated in
#: the registry row and in the module document, because a control that is
#: absent for a measured reason has to say the reason somewhere the user reads.
NO_COLOUR_NOTE = (
    "This disc's TEAM table carries no colour field: Madden 09's TBCR/TBCG/TBCB and "
    "TB2R/TB2G/TB2B are all absent, and so are TLNA and TMNC. A 64-row PACL palette "
    "is here and the create-a-school CTCD and CTUN colour tables are here with 0 rows, "
    "but which TEAM field selects a school's palette entry is not established, so this "
    "page offers names and no colour rather than a picker over a guess."
)


class IdentityLane(TdbRecordLane):
    """The league database's names: schools, conferences, stadiums, coaches."""

    discs = containers

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "colors"
    page = "identity"
    title = "School, conference, stadium and coach names"
    classification = "offline-writer-proved"
    schema = SCHEMA
    recipe_schema = RECIPE_SCHEMA
    receipt_schema = RECEIPT_SCHEMA
    validators = (
        "tools/validate_ncaa09_ps2_identity.sh",
        "tools/validate_ncaa09_ps2_identity.bat",
    )

    tdb_containers = (WRITABLE_CONTAINER,)
    writable_containers = (WRITABLE_CONTAINER,)
    editable_tables = ("TEAM", "CONF", "DIVI", "STAD", "COCH")
    editable_fields = EDITABLE_FIELDS
    max_targets = 600
    max_row_targets = MAX_ROW_TARGETS

    def member_is_editable(self, container_name: str, member: Optional[int],
                           database: ea_tdb.TdbDatabase) -> bool:
        """Only member 0.  Members 1..432 are the rosters, and another page's."""

        return member == LEAGUE_MEMBER

    def read_only_reason(self, container_name: str,
                         cached: Optional[Mapping[str, Sequence[str]]] = None) -> str:
        return (f"{container_name} members 1 to 432 are the per-team rosters and belong "
                f"to the Names, Numbers & Faces page's lane; this page writes the league "
                f"database, member {LEAGUE_MEMBER}.")

    def row_label(self, table: str, member: Optional[int], index: int,
                  values: Mapping[str, Any]) -> str:
        if table == "TEAM":
            return str(values.get("TDNA") or "").strip() or f"school {index}"
        if table == "CONF":
            return str(values.get("CNAM") or "").strip() or f"conference {index}"
        if table == "DIVI":
            return str(values.get("DNAM") or "").strip() or f"division {index}"
        if table == "STAD":
            return str(values.get("SNAM") or "").strip() or f"stadium {index}"
        name = " ".join(str(values.get(key, "")).strip()
                        for key in ("CLFN", "CLLN")).strip()
        return name or f"coach {index}"

    def row_detail(self, table: str, values: Mapping[str, Any]) -> str:
        if table == "TEAM":
            return " · ".join(str(values[key]) for key in ("TSNA", "TMNA")
                              if key in values and str(values[key]).strip())
        if table == "STAD":
            parts = [str(values[key]) for key in ("SCIT", "SSTA")
                     if key in values and str(values[key]).strip()]
            if "SCAP" in values:
                parts.append(f"{int(values['SCAP']):,} seats")
            return " · ".join(parts)
        return ""

    def row_budget(self, container_name: str) -> str:
        return ("Every name is written into the field it already occupies and padded out "
                "with the terminator. The league database keeps its exact size; its "
                "RLE1-packed member is re-packed and must fit the slot it owns, and the "
                "three copies the preload caches carry are rewritten with it.")

    def build_catalogue(self, source: Path, *, progress=None) -> Catalogue:
        """The base's catalogue, plus the palette the page reads and does not write."""

        catalogue = super().build_catalogue(source, progress=progress)
        document = dict(catalogue.document)
        document["colour_note"] = NO_COLOUR_NOTE
        document["palette"] = self._palette_shape(document)
        return Catalogue(catalogue.schema, catalogue.lane_id, catalogue.source,
                         catalogue.targets, document)

    @staticmethod
    def _palette_shape(document: Mapping[str, Any]) -> Mapping[str, Any]:
        """``PACL``'s shape, from the catalogue's own rows.  Counts, never colours."""

        for row in document.get("rows", ()):
            if row.get("member") != LEAGUE_MEMBER:
                continue
            for table in row.get("tables", ()):
                if table.get("name") == "PACL":
                    return {"rows": table.get("records", 0),
                            "fields": [item["name"] for item in table.get("fields", ())],
                            "note": NO_COLOUR_NOTE}
        return {"rows": 0, "fields": [], "note": NO_COLOUR_NOTE}

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "ncaa09-ps2-identity-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        """One school name, one conference name and one stadium capacity."""

        wanted = {"TEAM": None, "CONF": None, "STAD": None}
        for target in catalogue.targets:
            if not target.key.startswith(self.row_prefix):
                continue
            _path, _member, table, _record = self.parse_row_key(target.key)
            if table in wanted and wanted[table] is None:
                wanted[table] = target
        if wanted["TEAM"] is None:
            raise Refusal(
                "the synthetic league database carries no TEAM row to edit; rebuild the "
                "fixture from containers.synthetic_league_database()."
            )
        edits = [Edit(wanted["TEAM"].key, {"TSNA": "ZZ", "TDNA": "Renamed"},
                      note="conformance")]
        if wanted["CONF"] is not None:
            edits.append(Edit(wanted["CONF"].key, {"CNAM": "Renamed Conf"},
                              note="conformance"))
        if wanted["STAD"] is not None:
            edits.append(Edit(wanted["STAD"].key, {"SCAP": 51234}, note="conformance"))
        return tuple(edits)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.ncaa09_ps2.identity_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.ncaa09_ps2.identity_lane",
        description="List and edit the school, conference, stadium and coach names on "
                    "an NCAA Football 09 (PS2) disc.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21752 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--recipe", help="a JSON recipe of row edits")
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
                catalogue = lane.build_catalogue(lane.synthetic_source(Path(room)))
        else:
            if not arguments.source:
                parser.error("give --source DISC.iso, or --selftest")
            catalogue = lane.build_catalogue(
                Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
        document = dict(catalogue.document)
        if arguments.out:
            Path(arguments.out).write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n")
        print("NCAA09_IDENTITY rows=%d palette_rows=%d"
              % (document["editable_rows_listed"], document["palette"]["rows"]))
        if not arguments.recipe:
            if arguments.destination:
                parser.error("--destination needs --recipe")
            return 0
        recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
        source = Path(arguments.source)
        if arguments.dry_run or not arguments.destination:
            plan = lane.plan(source, recipe, catalogue)
            for item in plan.declared_ranges:
                print("would write %d byte(s) at %d (%s)"
                      % (item.length, item.start, item.reason))
            print("NCAA09_IDENTITY_PLAN targets=%d bytes=%d"
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
        print("NCAA09_IDENTITY_WRITE %s" % ("PASS" if verdict.passed else "FAIL"))
        return 0 if verdict.passed else 1
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = ["CAPABILITY_ID", "COACH_FIELDS", "CONFERENCE_FIELDS", "DIVISION_FIELDS",
           "EDITABLE_FIELDS", "IdentityLane", "LANE_ID", "LEAGUE_MEMBER",
           "MAX_ROW_TARGETS", "NO_COLOUR_NOTE", "RECEIPT_SCHEMA", "RECIPE_SCHEMA",
           "SCHEMA", "STADIUM_FIELDS", "TEAM_FIELDS", "WRITABLE_CONTAINER"]


if __name__ == "__main__":
    raise SystemExit(_main())
