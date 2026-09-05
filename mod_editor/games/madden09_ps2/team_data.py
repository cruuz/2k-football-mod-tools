"""The disc's EA TDB databases: tables, record counts and field names. Readers only.

Madden 09's team, roster and tuning data does not live in one file.  It lives
in **EA TDB databases packed as members of ``TERF`` containers** -- 235 of them
in ``DB_TEAMS.DAT``, 15 in ``TEMPLATE.DAT`` and 104 in ``GAMEDATA.DAT`` [M] --
plus one bare database on the disc, ``/DATA/STRMDATA.DB``, which carries no
container around it at all [M].

This lane opens each of them through
:mod:`mod_editor.games._formats.ea_tdb` and says what is inside: the tables,
how many records each holds against its capacity, the record stride, and every
field's name, type and bit width.  **Field names, not field values.**  A field
name is the schema and is the same on every disc; a record's contents are the
game's data and stay on the user's image.

**No writer, and none is claimed.**  Writing a row back would mean rewriting
the member, which means rebuilding its container; that path exists in
:func:`ea_terf.rewrite_member` but has never been proved by rebuilding a disc
and booting it, and a rewritten member cannot be re-packed to its original size
because no ``LZH1`` encoder exists anywhere public [S].  Until a rebuilt disc
boots, a TDB writer here would be a claim with no evidence, so ``plan``,
``build`` and ``verify`` refuse.

The CRC fields EA stores in a TDB header are reported, never checked and never
recomputed: this lane only reads.

Run it without a window::

    python3 -m mod_editor.games.madden09_ps2.team_data --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from mod_editor.games._formats import ea_tdb, ea_terf
from mod_editor.games.contract import (
    Catalogue,
    Edit,
    Field,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
)

from . import containers

CAPABILITY_ID = "madden09ps2.players.team_databases"
LANE_ID = "players_rosters.team_databases"
SCHEMA = "madden09_ps2_team_database_inventory/v1"

#: The containers whose members are EA TDB databases [M].  Named rather than
#: discovered so a 415 MB speech container is never opened looking for one; the
#: inventory lane is where "what else is on this disc" is answered.
TDB_CONTAINERS = (
    containers.TEAM_DATABASE_CONTAINER,
    containers.TEMPLATE_CONTAINER,
    containers.GAME_DATA_CONTAINER,
)

#: How many database targets are listed.  A retail disc has 354 TDB members
#: [M], so the cap is generous; the document's totals are complete regardless.
MAX_TARGETS = 2000


class TeamDataLane:
    """Every EA TDB database on the disc, table by table, read-only."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "players_rosters"
    page = "rosters"
    title = "Team and roster databases (read-only)"
    classification = "read-only-mapped"
    recipe_schema = SCHEMA
    validators = (
        "tools/validate_madden09_ps2_team_data.sh",
        "tools/validate_madden09_ps2_team_data.bat",
    )
    fixed_allocation = False
    read_only = True

    REFUSAL = (
        "This lane reads your disc's EA TDB databases and writes nothing. A writer would have "
        "to rebuild the TERF container the database sits in, and no rebuilt Madden 09 container "
        "has been booted in an emulator yet -- nor can an edited member be re-packed to its "
        "original size, because no LZH1 encoder exists publicly. Until that is proved, this "
        "page lists and does not edit."
    )

    # -- catalogue -----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        image = containers.open_disc(Path(source))
        files = {entry.name: entry for entry in containers.data_files(image)}
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        totals = {"databases": 0, "tables": 0, "records": 0, "fields": 0}
        skipped: Dict[str, str] = {}

        for name in TDB_CONTAINERS:
            entry = files.get(name)
            if entry is None:
                skipped[name] = "not on this image"
                continue
            if progress is not None:
                progress(f"{name}…")
            _report, container = containers.describe_container(image, entry, with_formats=False)
            if container is None:
                skipped[name] = "could not be opened as a TERF container"
                continue
            for index, payload in containers.members_of_format(
                    container, ea_terf.FORMAT_TDB, progress=progress):
                row = self._database_row(f"{containers.DATA_DIRECTORY}/{name}", index, payload)
                self._accumulate(totals, row)
                rows.append(row)
                if len(targets) < MAX_TARGETS:
                    targets.extend(self._targets_for(row))

        bare = files.get(containers.STREAM_DATABASE_FILE)
        if bare is None:
            skipped[containers.STREAM_DATABASE_FILE] = "not on this image"
        else:
            if progress is not None:
                progress(f"{containers.STREAM_DATABASE_FILE}…")
            try:
                payload = containers.read_file(image, bare)
            except containers.DiscError as exc:
                skipped[containers.STREAM_DATABASE_FILE] = str(exc)
            else:
                row = self._database_row(bare.path, None, payload)
                self._accumulate(totals, row)
                rows.append(row)
                if len(targets) < MAX_TARGETS:
                    targets.extend(self._targets_for(row))

        document = {
            "schema": SCHEMA,
            "source": str(source),
            "containers": list(TDB_CONTAINERS),
            "bare_database": containers.STREAM_DATABASE_FILE,
            "databases": totals["databases"],
            "tables": totals["tables"],
            "records": totals["records"],
            "fields": totals["fields"],
            "rows_listed": len(rows),
            "targets_listed": len(targets),
            "skipped": skipped,
            "rows": rows,
            "note": "Schema only: table names, record counts, strides and field names. No "
                    "record's contents are read or stored.",
        }
        return Catalogue(SCHEMA, self.lane_id, str(source), tuple(targets), document)

    @staticmethod
    def _accumulate(totals: Dict[str, int], row: Mapping[str, Any]) -> None:
        totals["databases"] += 1
        for table in row.get("tables", ()):
            totals["tables"] += 1
            totals["records"] += int(table.get("records", 0))
            totals["fields"] += int(table.get("field_count", 0))

    @staticmethod
    def _database_row(path: str, index: Optional[int], payload: bytes) -> Dict[str, Any]:
        """One database as numbers and names.  A refusal becomes a ``note``.

        One database this reader cannot open must not empty the catalogue of
        the other 353, so the failure is recorded on the row and the walk
        continues.
        """

        row: Dict[str, Any] = {
            "path": path,
            "member": index,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "tables": [],
            "note": "",
        }
        try:
            database = ea_tdb.parse_tdb(payload)
        except ea_tdb.TdbError as exc:
            row["note"] = str(exc)
            return row
        row["version"] = database.version
        row["preamble_bytes"] = database.preamble_bytes
        row["checksum"] = database.checksum
        row["table_count"] = database.table_count
        for table in database.tables:
            row["tables"].append({
                "name": table.name,
                "records": table.current_records,
                "capacity": table.max_records,
                "record_bytes": table.record_bytes,
                "record_bits": table.record_bits,
                "field_count": table.field_count,
                "index_count": table.index_count,
                "prior_crc": table.prior_crc,
                "header_crc": table.header_crc,
                "fields": [
                    {"name": item.name, "type": item.type_name,
                     "bit_offset": item.bit_offset, "bit_width": item.bit_width}
                    for item in table.fields
                ],
            })
        return row

    @staticmethod
    def _database_key(row: Mapping[str, Any]) -> str:
        return (f"{row['path']}#{row['member']}" if row.get("member") is not None
                else str(row["path"]))

    def _targets_for(self, row: Mapping[str, Any]) -> List[Target]:
        """One target for the database, and one per table inside it."""

        key = self._database_key(row)
        note = row.get("note") or ""
        detail = [f"{row['bytes']:,} bytes"]
        if row.get("table_count") is not None:
            detail.append(f"{row['table_count']} tables")
            detail.append(f"v{row.get('version')}")
        if note:
            detail.append(note)
        out = [Target(
            key=f"database:{key}",
            label=key,
            detail=" · ".join(detail),
            budget="Read-only: this lane never writes to your disc.",
            searchable=f"{key} tdb database",
            raw=dict(row, tables=[table["name"] for table in row.get("tables", ())]),
            fields=(
                Field("path", "note", "Container", "Which /DATA file holds this database.",
                      read_only=True),
                Field("member", "note", "Member",
                      "Its index inside that container; blank for a bare database.",
                      read_only=True),
                Field("version", "note", "TDB version", "The version its header declares.",
                      read_only=True),
                Field("table_count", "note", "Tables", "How many tables it carries.",
                      read_only=True),
                Field("bytes", "note", "Bytes", "The decompressed database's length.",
                      read_only=True),
                Field("sha256", "note", "Digest", "SHA-256 of the decompressed database.",
                      read_only=True),
            ),
        )]
        for table in row.get("tables", ()):
            out.append(Target(
                key=f"table:{key}:{table['name']}",
                label=f"{key} · {table['name']}",
                detail=f"{table['records']:,} of {table['capacity']:,} records · "
                       f"{table['record_bytes']} bytes/record · {table['field_count']} fields",
                budget="Read-only: this lane never writes to your disc.",
                searchable=f"{key} {table['name']} "
                           + " ".join(item["name"] for item in table["fields"]),
                raw=dict(table, path=row["path"], member=row.get("member")),
                fields=(
                    Field("name", "note", "Table", "The table's four-character name.",
                          read_only=True),
                    Field("records", "note", "Records",
                          "How many records it holds right now.", read_only=True),
                    Field("capacity", "note", "Capacity",
                          "How many records it has room for.", read_only=True),
                    Field("record_bytes", "note", "Record stride",
                          "How many bytes one record occupies.", read_only=True),
                    Field("field_count", "note", "Fields",
                          "How many fields each record carries.", read_only=True),
                    Field("fields", "note", "Field names",
                          "Every field's name, type and bit width. Names are the schema; "
                          "the values stay on your disc.", read_only=True),
                ),
            ))
        return out

    # -- the three refusals --------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        return self.REFUSAL

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": self.recipe_schema, "edits": []}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        raise Refusal(self.REFUSAL)

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        raise Refusal(self.REFUSAL)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        raise Refusal(self.REFUSAL)

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "madden09-ps2-teamdata-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc(tdb_member=synthetic_database()))
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


def synthetic_database() -> bytes:
    """A small EA TDB built from the format's own rules, for the synthetic disc.

    Two tables with fields whose bit widths deliberately straddle byte
    boundaries, so a reader that mis-orders the bit packing is visibly wrong.
    Nothing here comes from a game: the table names are made up and the values
    are a counting ramp.
    """

    return ea_tdb.build_tdb((
        (
            "TEAM",
            (
                ("TGID", ea_tdb.FIELD_UINT, 11),
                ("TDNA", ea_tdb.FIELD_STRING, 16 * 8),
                ("TWIN", ea_tdb.FIELD_SINT, 5),
            ),
            (
                {"TGID": 1, "TDNA": "SYNTHETIC-A", "TWIN": 3},
                {"TGID": 900, "TDNA": "SYNTHETIC-B", "TWIN": -4},
            ),
        ),
        (
            "PLAY",
            (
                ("PGID", ea_tdb.FIELD_UINT, 15),
                ("POVR", ea_tdb.FIELD_UINT, 7),
                ("PWGT", ea_tdb.FIELD_UINT, 9),
            ),
            tuple({"PGID": 16384 + n, "POVR": 40 + n, "PWGT": 180 + n} for n in range(4)),
        ),
    ))


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.madden09_ps2.team_data --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.team_data",
        description="List the EA TDB databases on a Madden NFL 09 (PS2) disc. Read-only.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = TeamDataLane()
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
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    print("TEAM_DATA databases=%d tables=%d records=%d fields=%d"
          % (document["databases"], document["tables"], document["records"], document["fields"]))
    return 0


__all__ = ["CAPABILITY_ID", "LANE_ID", "MAX_TARGETS", "SCHEMA", "TDB_CONTAINERS",
           "TeamDataLane", "synthetic_database"]


if __name__ == "__main__":
    raise SystemExit(_main())
