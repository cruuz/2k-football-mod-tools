"""Every EA TDB database on the NCAA Football 09 disc, table by table, read-only.

NCAA 09 keeps its league in a shape Madden 09 does not: ``/DATA/LEAGUE.DAT`` is
a ``COMP`` container of 455 members whose 433 ``RLE1``-packed databases are one
league database plus **432 per-team roster databases**, each a ``PLAY`` and a
``DCHT`` table [M].  ``/DATA/GAMEDATA.DAT`` carries 137 more (one shared play
library and 136 playbooks), ``/DATA/TEMPLATE.DAT`` 11 fresh-dynasty templates,
and ``/DATA/STRMDATA.DB`` is a bare database with no container around it [M].

This lane catalogues all of them: the tables, their record stride, how many rows
they hold and how many they can, and every field's name, type, bit width and bit
offset.  **A field name is the schema and is identical on every disc; a record's
contents are the user's game data**, and no value is read out of a record here.

It writes nothing.  What a writer would need is in
``docs/product/NCAA09_PS2_SCHEMA.md``.

Run it without a window::

    python3 -m mod_editor.games.ncaa09_ps2.database_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_tdb, ea_terf
from mod_editor.games.contract import (
    Catalogue, Edit, Field, Plan, Receipt, Refusal, Target, Verdict,
)

from . import containers

CAPABILITY_ID = "ncaa09ps2.players.league_databases"
LANE_ID = "players.league_databases"
SCHEMA = "ncaa09_ps2_league_databases/v1"

#: The containers this lane opens, in the order a report lists them [M].
DATABASE_CONTAINERS = (
    containers.LEAGUE_CONTAINER,
    containers.GAME_DATA_CONTAINER,
    containers.TEMPLATE_CONTAINER,
)

#: How many database rows the page lists.  The disc holds 582 [M]; every one is
#: catalogued in the document, and the page's target list stops here so a table
#: stays a table.
MAX_DATABASE_TARGETS = 700


class DatabaseLane:
    """The disc's EA TDB databases and their schema, read-only."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "players_rosters"
    page = "rosters"
    title = "Every EA TDB database on the disc"
    classification = "read-only-mapped"
    recipe_schema = SCHEMA
    validators = (
        "tools/validate_ncaa09_ps2_databases.sh",
        "tools/validate_ncaa09_ps2_databases.bat",
    )
    fixed_allocation = False
    read_only = True

    REFUSAL = (
        "This lane catalogues the databases on your disc and writes nothing. NCAA "
        "Football 09's PLAY table has no PFNA or PLNA field, so the Madden 09 roster "
        "writer does not port to it; docs/product/NCAA09_PS2_SCHEMA.md names, field by "
        "field, what a writer for this disc would have to be given instead."
    )

    # -- catalogue -----------------------------------------------------

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        image = containers.open_disc(Path(source))
        rows: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        targets: List[Target] = []
        schemas: Dict[str, Dict[str, Any]] = {}
        crc_agree = crc_differ = 0
        tables = fields = 0

        for name in DATABASE_CONTAINERS:
            try:
                container = containers.load_container(image, name)
            except containers.DiscError as exc:
                refusals.append({"reader": "containers.load_container",
                                 "where": name, "sentence": str(exc)})
                continue
            for index in range(len(container)):
                if progress is not None and index % 64 == 0:
                    progress(f"{name} member {index} of {len(container)}…")
                try:
                    payload = containers.member_uncached(container, index)
                except ea_terf.TerfError as exc:
                    refusals.append({"reader": "ea_terf.member",
                                     "where": f"{name}:{index}", "sentence": str(exc)})
                    continue
                if ea_terf.identify_member(payload) != "TDB":
                    continue
                row, refused = self._describe(payload, name, index, schemas)
                if refused is not None:
                    refusals.append(refused)
                    continue
                crc_agree += row["crc_sites_agree"]
                crc_differ += row["crc_sites_differ"]
                tables += row["tables"]
                fields += row["fields"]
                rows.append(row)

        for entry in containers.data_files(image):
            if containers.classify(image, entry) != containers.KIND_TDB:
                continue
            try:
                payload = containers.read_file(image, entry)
            except containers.DiscError as exc:
                refusals.append({"reader": "containers.read_file",
                                 "where": entry.path, "sentence": str(exc)})
                continue
            row, refused = self._describe(payload, entry.name, None, schemas)
            if refused is not None:
                refusals.append(refused)
                continue
            crc_agree += row["crc_sites_agree"]
            crc_differ += row["crc_sites_differ"]
            tables += row["tables"]
            fields += row["fields"]
            rows.append(row)

        for row in rows[:MAX_DATABASE_TARGETS]:
            targets.append(self._database_target(row))

        document = {
            "schema": SCHEMA,
            "source": str(source),
            "containers": list(DATABASE_CONTAINERS),
            "databases": len(rows),
            "databases_refused": len(refusals),
            "database_rows_listed": min(len(rows), MAX_DATABASE_TARGETS),
            "database_rows_cap": MAX_DATABASE_TARGETS,
            "tables": tables,
            "field_definitions": fields,
            "crc_sites_agree": crc_agree,
            "crc_sites_differ": crc_differ,
            "distinct_schemas": len(schemas),
            "schemas": schemas,
            "rows": rows,
            "refusals": refusals,
        }
        return Catalogue(schema=SCHEMA, lane_id=self.lane_id, source=str(source),
                         targets=tuple(targets), document=document)

    @staticmethod
    def _describe(payload: bytes, where: str, member: Optional[int],
                  schemas: Dict[str, Dict[str, Any]]
                  ) -> Tuple[Dict[str, Any], Optional[Dict[str, str]]]:
        """One database's shape, or the reader's own sentence about why not.

        A database the reader refuses is **recorded**, not dropped: two of this
        disc's 582 carry a field type the shared reader does not name, and a
        catalogue that quietly omitted them would read as if they were not there.
        """

        try:
            database = ea_tdb.parse_tdb(payload)
        except ea_tdb.TdbError as exc:
            return {}, {"reader": "ea_tdb.parse_tdb",
                        "where": where if member is None else f"{where}:{member}",
                        "sentence": str(exc)}
        digest = _schema_digest(database)
        if digest not in schemas:
            schemas[digest] = {
                "digest": digest,
                "version": database.version,
                "tables": [_table_document(database.table(name))
                           for name in database.table_names],
            }
        agree = differ = 0
        crc_note = ""
        try:
            for site in ea_tdb.crc_sites(payload):
                if site.matches:
                    agree += 1
                else:
                    differ += 1
        except ea_tdb.TdbError as exc:
            crc_note = str(exc)
        return {
            "where": where,
            "member": member,
            "bytes": len(payload),
            "version": database.version,
            "schema": digest,
            "tables": len(database.table_names),
            "fields": sum(len(database.table(n).fields) for n in database.table_names),
            "records": sum(database.table(n).current_records for n in database.table_names),
            "table_rows": {n: database.table(n).current_records
                           for n in database.table_names},
            "crc_sites_agree": agree,
            "crc_sites_differ": differ,
            "crc_note": crc_note,
        }, None

    @staticmethod
    def _database_target(row: Mapping[str, Any]) -> Target:
        label = row["where"] if row["member"] is None \
            else f"{row['where']} member {row['member']}"
        detail = " · ".join([
            f"{row['tables']} table(s)",
            f"{row['records']:,} row(s)",
            f"{row['fields']} field definition(s)",
            f"schema {row['schema']}",
            f"{row['crc_sites_agree']} of {row['crc_sites_agree'] + row['crc_sites_differ']} "
            f"checksum slot(s) agree",
        ])
        return Target(
            key=f"database:{row['where']}:{row['member'] if row['member'] is not None else '-'}",
            label=label,
            detail=detail,
            budget="Read-only: this lane never writes to your disc.",
            searchable=f"{row['where']} {row['member']} {row['schema']} "
                       + " ".join(row["table_rows"]),
            raw=dict(row),
            fields=(
                Field("version", "note", "TDB version",
                      "The version word in this database's header.", read_only=True),
                Field("schema", "note", "Schema digest",
                      "Databases with the same digest have the same tables and fields.",
                      read_only=True),
                Field("tables", "note", "Tables",
                      "How many tables this database carries.", read_only=True),
                Field("table_rows", "note", "Rows per table",
                      "How many records each table currently holds.", read_only=True),
                Field("fields", "note", "Field definitions",
                      "How many field definitions across every table.", read_only=True),
                Field("crc_sites_agree", "note", "Checksums that agree",
                      "EA stores four CRC-32/MPEG-2 values per database; this is how many "
                      "hold the value they recompute to.", read_only=True),
            ),
        )

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
        path = Path(work_dir) / "ncaa09-ps2-databases-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc(
            stream_database=containers.synthetic_tdb(tables=1)))
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


def _table_document(table: ea_tdb.TdbTable) -> Dict[str, Any]:
    """One table's shape.  Names, widths, offsets and counts; never a record."""

    return {
        "table": table.name,
        "record_bytes": table.record_bytes,
        "record_bits": table.record_bits,
        "records": table.current_records,
        "max_records": table.max_records,
        "field_count": table.field_count,
        "index_count": table.index_count,
        "fields": [{"name": field.name, "type": field.type_id,
                    "type_name": field.type_name, "bits": field.bit_width,
                    "offset": field.bit_offset}
                   for field in table.fields],
    }


def _schema_digest(database: ea_tdb.TdbDatabase) -> str:
    """A stable 16-character name for one table/field shape.

    Two databases share a digest exactly when they share every table name,
    record stride, field name, field type, width and offset -- which is what
    lets 432 per-team rosters collapse to one row in a document [M].
    """

    import hashlib

    blob = json.dumps(
        [[name,
          database.table(name).record_bytes,
          [[f.name, f.type_id, f.bit_width, f.bit_offset]
           for f in database.table(name).fields]]
         for name in database.table_names],
        sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.ncaa09_ps2.database_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.ncaa09_ps2.database_lane",
        description="Catalogue every EA TDB database on an NCAA Football 09 (PS2) disc. "
                    "Read-only; field names and widths, never a record's contents.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21752 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    if not arguments.selftest and not arguments.source:
        parser.error("give --source a disc image, or --selftest")
    lane = DatabaseLane()
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                catalogue = lane.build_catalogue(lane.synthetic_source(Path(room)))
        else:
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
    print("DATABASES parsed=%d refused=%d tables=%d fields=%d schemas=%d crc=%d/%d"
          % (document["databases"], document["databases_refused"], document["tables"],
             document["field_definitions"], document["distinct_schemas"],
             document["crc_sites_agree"],
             document["crc_sites_agree"] + document["crc_sites_differ"]))
    return 0


__all__ = ["CAPABILITY_ID", "DATABASE_CONTAINERS", "DatabaseLane", "LANE_ID",
           "MAX_DATABASE_TARGETS", "SCHEMA"]


if __name__ == "__main__":
    raise SystemExit(_main())
