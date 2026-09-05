"""The disc's EA TDB databases: catalogued table by table, and now edited.

Madden 09's team, roster and tuning data does not live in one file.  It lives
in **EA TDB databases packed as members of ``TERF`` containers** -- 235 of them
in ``DB_TEAMS.DAT``, 15 in ``TEMPLATE.DAT`` and 104 in ``GAMEDATA.DAT`` [M] --
plus one bare database on the disc, ``/DATA/STRMDATA.DB``, which carries no
container around it at all [M].

This lane opens each of them through
:mod:`mod_editor.games._formats.ea_tdb` and says what is inside: the tables,
how many records each holds against its capacity, the record stride, and every
field's name, type and bit width.  For the databases it can also **edit**, it
goes one step further and lists the rows themselves.

What it edits
-------------

Only ``/DATA/DB_TEAMS.DAT``, and inside it only two tables:

* ``PLAY`` -- one row per player: first and last name, jersey number, age and
  twenty numeric ratings.  The exact list is :data:`PLAYER_FIELDS`; it is a
  list and not "whatever is numeric" on purpose, so what this page offers is
  something a reader can check rather than a shape that drifts.
* ``TEAM`` -- the nickname, city, abbreviation and short name a team is drawn
  under (:data:`TEAM_FIELDS`).

Everything else on the disc stays read-only, and each has a reason:

* ``TEMPLATE.DAT`` and ``GAMEDATA.DAT`` are **named in the preload caches**
  ``/DATA/FE.QKL`` and ``/DATA/GAME.QKL``, and the first 256 bytes of each
  appear verbatim inside the cache that names them [M].  Editing one copy and
  not the other would leave the game reading whichever it reached first, so
  this lane refuses both rather than writing half a change.  ``DB_TEAMS.DAT``
  is named in neither [M], which is what makes it safe to write -- and the
  catalogue re-reads that list off the user's own image
  (:func:`containers.preload_names`) rather than trusting a table written down
  here.
* ``STRMDATA.DB`` is a 5 MB bare database of league and presentation tables
  with no ``PLAY`` table at all [M]; it is outside what this page is for.

Why a record edit is a bounded write
------------------------------------

A TDB field owns a fixed run of bits inside a fixed-stride record, so writing
one **cannot change a length**: the database comes back the same size, the
container member it sits in comes back the same size, and the ISO extent it
came from is rewritten in place.  A rewrite that would change any of those is
refused rather than allowed to move bytes this lane cannot account for.

The four checksums EA stores in a TDB header are recomputed on every write
(``ea_tdb.recompute_crcs``) and re-derived from the destination's own bytes by
the verifier (``ea_tdb.verify_crcs``).  The algorithm is proved against 4,806
checksum slots on the owner's retail disc; see :mod:`ea_tdb`.

**Nothing here has been seen in a running game.**  The evidence is offline: a
destination image, an independent verifier that re-reads it, and a conformance
harness that proves the whole path on a synthetic disc.  No emulator has booted
a rebuilt Madden 09 disc, and this module does not claim one has.

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
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_tdb, ea_terf
from mod_editor.games.contract import (
    Catalogue,
    DeclaredRange,
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
RECIPE_SCHEMA = "madden09_ps2_team_database_edit/v1"
RECEIPT_SCHEMA = "madden09_ps2_team_database_write/v1"

#: The containers whose members are EA TDB databases [M].  Named rather than
#: discovered so a 415 MB speech container is never opened looking for one; the
#: inventory lane is where "what else is on this disc" is answered.
TDB_CONTAINERS = (
    containers.TEAM_DATABASE_CONTAINER,
    containers.TEMPLATE_CONTAINER,
    containers.GAME_DATA_CONTAINER,
)

#: The one container this lane writes to.  See the module docstring: the other
#: two are duplicated inside ``FE.QKL`` and editing them would leave a stale
#: copy behind.
WRITABLE_CONTAINER = containers.TEAM_DATABASE_CONTAINER

#: Which preload cache names each container this lane will not write [M].  The
#: list a user's own image declares is read at catalogue time by
#: :func:`containers.preload_names` and takes precedence; this is the measured
#: floor, so an image whose caches this module cannot read still refuses the
#: two it is known to have to.
PRELOAD_COPIES: Mapping[str, Tuple[str, ...]] = {
    containers.TEMPLATE_CONTAINER: ("FE.QKL",),
    containers.GAME_DATA_CONTAINER: ("GAME.QKL", "FE.QKL"),
}

#: How many database targets are listed.  A retail disc has 355 TDB members
#: [M], so the cap is generous; the document's totals are complete regardless.
MAX_TARGETS = 2000

#: How many editable rows are listed.  ``DB_TEAMS.DAT`` holds 235 databases of
#: roughly 53 players and one team each -- about 12,700 rows [M] -- and the cap
#: is above that so a retail disc lists every one.  The document says how many
#: were listed either way.
MAX_ROW_TARGETS = 20000

#: The tables whose rows become editable, in the order a page shows them.
EDITABLE_TABLES = ("TEAM", "PLAY")

#: What a number field is set to when the user means "leave this alone".  A
#: text box can be left blank and dropped, but a spinner always holds some
#: value, so the convention has to be named rather than inferred; it is the one
#: the sibling PS2 module already uses.
KEEP_NUMBER = -1

#: The scale Madden's numeric ratings are on [S].  The fields are seven bits
#: wide and would hold 127, but a rating above 99 is not a value the game's own
#: data ever carries, so the editor stops at 99 rather than at the bit width.
RATING_MAX = 99

#: The range an NFL jersey number covers [S].  ``PJEN`` is seven bits wide.
JERSEY_MAX = 99


def _rating(name: str, label: str) -> Tuple[str, str, str, Optional[int]]:
    return (name, label, f"{label} rating, 0 to {RATING_MAX}.", RATING_MAX)


#: The ``PLAY`` fields this lane offers, in the order a page draws them.  Each
#: is ``(field name, label, help, maximum)``; ``maximum`` of ``None`` means the
#: field's own bit width is the bound.  A field the table does not declare is
#: skipped, so a database with a different schema simply offers less.
PLAYER_FIELDS: Tuple[Tuple[str, str, str, Optional[int]], ...] = (
    ("PFNA", "First name", "The player's first name.", None),
    ("PLNA", "Last name", "The player's last name.", None),
    ("PJEN", "Jersey number", f"Squad number, 0 to {JERSEY_MAX}.", JERSEY_MAX),
    ("PAGE", "Age", "Age in years, as the six-bit field stores it.", None),
    _rating("POVR", "Overall"),
    _rating("PSPD", "Speed"),
    _rating("PACC", "Acceleration"),
    _rating("PAGI", "Agility"),
    _rating("PSTR", "Strength"),
    _rating("PAWR", "Awareness"),
    _rating("PCTH", "Catching"),
    _rating("PCAR", "Carrying"),
    _rating("PTHP", "Throwing power"),
    _rating("PTHA", "Throwing accuracy"),
    _rating("PJMP", "Jumping"),
    _rating("PTAK", "Tackling"),
    _rating("PBTK", "Broken tackles"),
    _rating("PPBK", "Pass blocking"),
    _rating("PRBK", "Run blocking"),
    _rating("PSTA", "Stamina"),
    _rating("PINJ", "Injury"),
    _rating("PKPR", "Kick power"),
    _rating("PKAC", "Kick accuracy"),
    _rating("PMOR", "Morale"),
)

#: The ``TEAM`` fields this lane offers.  What each holds was read off the
#: owner's own disc -- ``TDNA`` "Bears", ``TLNA`` "Chicago", ``TSNA`` "CHI",
#: ``TMNC`` "Brownies" for Cleveland -- so the labels are measured, not guessed
#: [M].  No value from that reading is stored here.
TEAM_FIELDS: Tuple[Tuple[str, str, str, Optional[int]], ...] = (
    ("TDNA", "Nickname", "The name the team is drawn under, e.g. its mascot.", None),
    ("TLNA", "City", "The city or region the team plays for.", None),
    ("TSNA", "Abbreviation", "The two-to-five letter short code.", None),
    ("TMNC", "Short name", "The familiar short form commentary uses.", None),
)

#: Both lists, keyed by the table they belong to.
EDITABLE_FIELDS: Mapping[str, Tuple[Tuple[str, str, str, Optional[int]], ...]] = {
    "PLAY": PLAYER_FIELDS,
    "TEAM": TEAM_FIELDS,
}

#: How a row target's key is spelled: ``row:<iso path>#<member>:<table>:<record>``.
ROW_PREFIX = "row:"


class TeamDataError(Refusal):
    """This lane could not do what was asked; the sentence says why."""


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------


def row_key(iso_path: str, member: int, table: str, record: int) -> str:
    """The target key for one record of one table of one container member."""

    return f"{ROW_PREFIX}{iso_path}#{member}:{table}:{record}"


def parse_row_key(key: str) -> Tuple[str, int, str, int]:
    """``row:/DATA/DB_TEAMS.DAT#12:PLAY:34`` back into its four parts."""

    if not key.startswith(ROW_PREFIX):
        raise TeamDataError(
            f"{key!r} is not an editable row; a row's key is spelled "
            f"{ROW_PREFIX}<container>#<member>:<table>:<record>, and the "
            f"database and table targets beside them are read-only."
        )
    rest = key[len(ROW_PREFIX):]
    try:
        head, table, record = rest.rsplit(":", 2)
        path, member = head.rsplit("#", 1)
        return path, int(member), table, int(record)
    except ValueError as exc:
        raise TeamDataError(
            f"{key!r} is not a row key this lane writes; it should read "
            f"{ROW_PREFIX}<container>#<member>:<table>:<record>."
        ) from exc


# --------------------------------------------------------------------------
# Fields
# --------------------------------------------------------------------------


def text_budget(field: ea_tdb.TdbField) -> int:
    """How many characters a ``STRING`` field takes, terminator excluded.

    The field is *n* bytes and a name that filled all *n* would leave the game
    reading past its own field for a terminator, so the budget is one less.
    """

    return max(0, field.bit_width // 8 - 1)


def number_bound(field: ea_tdb.TdbField, maximum: Optional[int]) -> int:
    """The largest value a numeric field takes: the smaller of scale and width."""

    width_bound = (1 << field.bit_width) - 1
    return width_bound if maximum is None else min(maximum, width_bound)


def fields_for(table: ea_tdb.TdbTable) -> Tuple[Field, ...]:
    """The editor controls one row of *table* offers, in list order.

    Built once per table schema and shared by every row of it: a retail disc
    has about 12,700 rows and each carrying its own copies of two dozen field
    descriptions is a quarter of a million objects for no information.
    """

    out: List[Field] = []
    for name, label, help_text, maximum in EDITABLE_FIELDS.get(table.name, ()):
        if name not in table:
            continue
        field = table.field(name)
        if field.type_id == ea_tdb.FIELD_STRING:
            budget = text_budget(field)
            out.append(Field(
                name, "text", label,
                f"{help_text} Up to {budget} characters -- the field is "
                f"{field.bit_width // 8} bytes and one is the terminator. "
                f"Leave it blank to keep what is there.",
                maximum=budget,
            ))
        elif field.type_id in (ea_tdb.FIELD_UINT, ea_tdb.FIELD_SINT):
            bound = number_bound(field, maximum)
            out.append(Field(
                name, "int", label,
                f"{help_text} {KEEP_NUMBER} keeps the value that is there.",
                minimum=KEEP_NUMBER, maximum=bound,
            ))
    return tuple(out)


def _shared_fields_cache() -> Dict[Tuple[Any, ...], Tuple[Field, ...]]:
    return {}


def row_values(database: ea_tdb.TdbDatabase, table: ea_tdb.TdbTable, index: int,
               shape: Sequence[Field]) -> Dict[str, Any]:
    """What the row holds today, for the fields this lane offers."""

    record = database.record_bytes(table, index)
    return {item.key: database.decode(table.field(item.key), record) for item in shape}


# --------------------------------------------------------------------------
# The lane
# --------------------------------------------------------------------------


class TeamDataLane:
    """Every EA TDB database on the disc, and the rows of the one it writes."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "players_rosters"
    page = "rosters"
    title = "Team and roster databases"
    classification = "offline-writer-proved"
    recipe_schema = RECIPE_SCHEMA
    validators = (
        "tools/validate_madden09_ps2_team_data.sh",
        "tools/validate_madden09_ps2_team_data.bat",
    )
    #: A record edit never changes a length, so the destination image is the
    #: source's exact size.
    fixed_allocation = True
    read_only = False

    #: Why a database outside ``DB_TEAMS.DAT`` offers no edit.
    @staticmethod
    def read_only_reason(container_name: str,
                         cached: Optional[Mapping[str, Sequence[str]]] = None) -> str:
        caches = (cached or {}).get(container_name.upper()) or PRELOAD_COPIES.get(
            container_name.upper())
        if caches:
            named = " and ".join(f"/DATA/{item}" for item in caches)
            return (
                f"{container_name} is named in {named}, the preload cache, which carries a "
                f"copy of at least some of what it names and which this lane does not "
                f"rewrite; editing one copy and not the other would leave the game reading "
                f"whichever it reached first."
            )
        return (
            f"{container_name} is outside what this page edits: it writes the per-team roster "
            f"databases in {WRITABLE_CONTAINER}."
        )

    # -- catalogue -----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        image = containers.open_disc(Path(source))
        files = {entry.name: entry for entry in containers.data_files(image)}
        cached = containers.preload_names(image)
        if WRITABLE_CONTAINER.upper() in cached:
            raise TeamDataError(
                f"{WRITABLE_CONTAINER} is named in "
                + " and ".join(cached[WRITABLE_CONTAINER.upper()])
                + " on this image, and a container a preload cache carries is not one this "
                  "lane rewrites; it edits nothing here."
            )
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        row_targets: List[Target] = []
        totals = {"databases": 0, "tables": 0, "records": 0, "fields": 0}
        skipped: Dict[str, str] = {}
        shapes: Dict[Tuple[Any, ...], Tuple[Field, ...]] = _shared_fields_cache()

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
            iso_path = f"{containers.DATA_DIRECTORY}/{name}"
            for index, payload in containers.members_of_format(
                    container, ea_terf.FORMAT_TDB, progress=progress):
                row = self._database_row(iso_path, index, payload)
                self._accumulate(totals, row)
                rows.append(row)
                if len(targets) < MAX_TARGETS:
                    targets.extend(self._targets_for(row))
                if name == WRITABLE_CONTAINER and len(row_targets) < MAX_ROW_TARGETS:
                    row_targets.extend(self._rows_of(iso_path, name, index, payload, shapes,
                                                     MAX_ROW_TARGETS - len(row_targets)))

        bare = files.get(containers.STREAM_DATABASE_FILE)
        if bare is None:
            skipped[containers.STREAM_DATABASE_FILE] = "not on this image"
        else:
            if progress is not None:
                progress(f"{containers.STREAM_DATABASE_FILE}…")
            try:
                payload = containers.read_file(image, bare, limit=None)
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
            "writable_container": WRITABLE_CONTAINER,
            "preload_cached": {name: list(caches) for name, caches in sorted(cached.items())},
            "bare_database": containers.STREAM_DATABASE_FILE,
            "databases": totals["databases"],
            "tables": totals["tables"],
            "records": totals["records"],
            "fields": totals["fields"],
            "rows_listed": len(rows),
            "targets_listed": len(targets),
            "editable_rows_listed": len(row_targets),
            "editable_rows_cap": MAX_ROW_TARGETS,
            "editable_tables": list(EDITABLE_TABLES),
            "skipped": skipped,
            "rows": rows,
            "note": "Schema for every database on the disc: table names, record counts, "
                    "strides and field names. The rows of DB_TEAMS.DAT are listed as "
                    "editable targets with the values they hold; those values are read "
                    "from your own image and are not part of this document.",
        }
        return Catalogue(SCHEMA, self.lane_id, str(source),
                         tuple(targets) + tuple(row_targets), document)

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
        the other 354, so the failure is recorded on the row and the walk
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
        row["checksum_sites_wrong"] = len(ea_tdb.verify_crcs(payload))
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
        """One target for the database, and one per table inside it.  Read-only."""

        key = self._database_key(row)
        name = str(row["path"]).rsplit("/", 1)[-1]
        note = row.get("note") or ""
        detail = [f"{row['bytes']:,} bytes"]
        if row.get("table_count") is not None:
            detail.append(f"{row['table_count']} tables")
            detail.append(f"v{row.get('version')}")
        if note:
            detail.append(note)
        budget = ("Its rows are listed below and can be edited."
                  if name == WRITABLE_CONTAINER
                  else "Read-only: " + self.read_only_reason(name))

        out = [Target(
            key=f"database:{key}",
            label=key,
            detail=" · ".join(detail),
            budget=budget,
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
                budget=budget,
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
                          "Every field's name, type and bit width.", read_only=True),
                ),
            ))
        return out

    def _rows_of(self, iso_path: str, container_name: str, member: int, payload: bytes,
                 shapes: Dict[Tuple[Any, ...], Tuple[Field, ...]],
                 remaining: int) -> List[Target]:
        """The editable rows of one database member: one target per record."""

        try:
            database = ea_tdb.parse_tdb(payload)
        except ea_tdb.TdbError:
            return []
        out: List[Target] = []
        for table_name in EDITABLE_TABLES:
            if table_name not in database.table_names:
                continue
            table = database.table(table_name)
            signature = (table_name, tuple(
                (item.name, item.type_id, item.bit_width) for item in table.fields))
            shape = shapes.get(signature)
            if shape is None:
                shape = fields_for(table)
                shapes[signature] = shape
            if not shape:
                continue
            for index in range(table.current_records):
                if len(out) >= remaining:
                    return out
                values = row_values(database, table, index, shape)
                out.append(Target(
                    key=row_key(iso_path, member, table_name, index),
                    label=self._row_label(table_name, member, index, values),
                    detail=self._row_detail(table_name, values),
                    budget="Every value is written where it already sits; nothing moves and "
                           "the image keeps its exact size.",
                    searchable=f"{container_name} {member} {table_name} {index} "
                               + " ".join(str(value) for value in values.values()),
                    raw={
                        "container": container_name,
                        "iso_path": iso_path,
                        "member": member,
                        "table": table_name,
                        "record": index,
                        "record_bytes": table.record_bytes,
                        "values": values,
                    },
                    fields=shape,
                ))
        return out

    @staticmethod
    def _row_label(table: str, member: int, index: int, values: Mapping[str, Any]) -> str:
        if table == "PLAY":
            name = " ".join(str(values.get(key, "")).strip()
                            for key in ("PFNA", "PLNA")).strip()
            return name or f"member {member} · player {index}"
        name = " ".join(str(values.get(key, "")).strip()
                        for key in ("TLNA", "TDNA")).strip()
        return name or f"member {member} · team {index}"

    @staticmethod
    def _row_detail(table: str, values: Mapping[str, Any]) -> str:
        if table == "PLAY":
            parts = []
            if "PJEN" in values:
                parts.append(f"#{values['PJEN']}")
            if "POVR" in values:
                parts.append(f"OVR {values['POVR']}")
            if "PAGE" in values:
                parts.append(f"age {values['PAGE']}")
            return " · ".join(parts)
        return " · ".join(str(values[key]) for key in ("TSNA",) if key in values)

    # -- editing -------------------------------------------------------

    @staticmethod
    def _shape(target: Target) -> Dict[str, Field]:
        return {item.key: item for item in target.fields if not item.read_only}

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        """One sentence saying why an edit does not fit, or ``None``."""

        if not target.key.startswith(ROW_PREFIX):
            return (
                f"{target.key} is a description of a database, not a row of one. Choose a "
                f"player or team row of {WRITABLE_CONTAINER} to edit."
            )
        shape = self._shape(target)
        unknown = sorted(set(values) - set(shape))
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not a field this lane writes; "
                    f"it writes " + ", ".join(sorted(shape)) + ".")
        current = dict(target.raw.get("values") or {})
        changing = 0
        for key, value in values.items():
            item = shape[key]
            if item.kind == "text":
                if not isinstance(value, str):
                    return f"{item.label} takes text and was handed {value!r}."
                if value == "":
                    continue
                if "\x00" in value:
                    return f"{item.label} may not contain a NUL character; remove it."
                try:
                    encoded = value.encode(ea_tdb.TEXT_ENCODING, "strict")
                except UnicodeEncodeError:
                    return (f"{item.label} cannot be written as {ea_tdb.TEXT_ENCODING}, which "
                            f"is the only encoding this format carries; use characters that "
                            f"encoding has.")
                budget = int(item.maximum or 0)
                if len(encoded) > budget:
                    return (f"{item.label} is {len(encoded)} characters and the field holds "
                            f"{budget}; shorten it to {budget}.")
                if value != current.get(key):
                    changing += 1
                continue
            if type(value) is not int:
                return f"{item.label} takes a whole number and was handed {value!r}."
            if value == KEEP_NUMBER:
                continue
            low = 0
            high = int(item.maximum if item.maximum is not None else 0)
            if not low <= value <= high:
                return (f"{item.label} takes {low} to {high} and {value} is outside that; "
                        f"{KEEP_NUMBER} leaves the value alone.")
            if value != current.get(key):
                changing += 1
        if not changing:
            return ("Nothing in this row would change. Type a new value, or leave the row "
                    "alone.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows: List[Dict[str, Any]] = []
        for edit in edits:
            values = {key: value for key, value in edit.values.items()
                      if not (value == "" or value == KEEP_NUMBER)}
            rows.append({"target": edit.target_key, "values": values})
        return {"schema": RECIPE_SCHEMA, "edits": rows}

    # -- plan / build / verify -----------------------------------------

    @staticmethod
    def _recipe_edits(recipe: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        if str(recipe.get("schema")) != RECIPE_SCHEMA:
            raise TeamDataError(
                f"this recipe says it is {recipe.get('schema')!r} and this lane writes "
                f"{RECIPE_SCHEMA}; hand it a recipe compose_recipe made."
            )
        rows = recipe.get("edits")
        if not isinstance(rows, list) or not rows:
            raise TeamDataError(
                "this recipe changes nothing: its 'edits' list is empty, and a build with "
                "nothing to write would be a plain copy."
            )
        return [dict(row) for row in rows]

    def _resolve(self, source: Path, recipe: Mapping[str, Any]) -> Dict[str, Any]:
        """Work out every changed byte, from the user's own image, writing nothing.

        Returns the rebuilt container bytes per ISO path, the per-edit record
        of what changed, and enough detail for the verifier to re-derive the
        claim without this code.
        """

        image = containers.open_disc(Path(source))
        files = {f"{containers.DATA_DIRECTORY}/{entry.name}": entry
                 for entry in containers.data_files(image)}
        cached = containers.preload_names(image)
        wanted: Dict[str, Dict[int, Dict[str, Dict[str, Any]]]] = {}
        order: List[Tuple[str, str, int, str, int]] = []
        for row in self._recipe_edits(recipe):
            key = str(row.get("target", ""))
            iso_path, member, table, record = parse_row_key(key)
            name = iso_path.rsplit("/", 1)[-1]
            if name != WRITABLE_CONTAINER or name.upper() in cached:
                raise TeamDataError(
                    f"{key} names {name}, and this lane writes only {WRITABLE_CONTAINER}: "
                    + self.read_only_reason(name, cached)
                )
            values = row.get("values")
            if not isinstance(values, Mapping) or not values:
                raise TeamDataError(
                    f"{key} names no value to write; every edit must carry at least one."
                )
            slot = wanted.setdefault(iso_path, {}).setdefault(member, {})
            merged = slot.setdefault(f"{table}:{record}", {"table": table, "record": record,
                                                           "values": {}})
            merged["values"].update(values)
            order.append((key, iso_path, member, table, record))

        rebuilt: Dict[str, bytes] = {}
        edits_report: List[Dict[str, Any]] = []
        members_report: List[Dict[str, Any]] = []
        for iso_path, members in sorted(wanted.items()):
            entry = files.get(iso_path)
            if entry is None:
                raise TeamDataError(
                    f"this image holds no {iso_path}; it is not a Madden NFL 09 "
                    f"PlayStation 2 disc, or the container has been removed."
                )
            original = containers.read_file(image, entry)
            if len(original) != entry.recorded_length:
                raise TeamDataError(
                    f"{iso_path} is {entry.recorded_length:,} bytes in this image's own "
                    f"directory and carries {len(original):,}; a rewrite would have to grow "
                    f"the file, which this lane will not do."
                )
            container = ea_terf.parse_terf(original, allow_size_mismatch=True)
            working = original
            for member, rows in sorted(members.items()):
                payload = container.member(member)
                database = ea_tdb.parse_tdb(payload)
                new_payload = payload
                for entry_key in sorted(rows):
                    change = rows[entry_key]
                    table = database.table(str(change["table"]))
                    index = int(change["record"])
                    before = {name: database.value(table, index, name)
                              for name in change["values"]}
                    working_db = ea_tdb.parse_tdb(new_payload)
                    new_payload = ea_tdb.write_records(
                        working_db, table.name, {index: dict(change["values"])})
                    after_db = ea_tdb.parse_tdb(new_payload)
                    spans = []
                    record_start = after_db.record_offset(table.name, index)
                    for name in sorted(change["values"]):
                        field = table.field(name)
                        first = record_start + field.bit_offset // 8
                        last = record_start + (field.bit_offset + field.bit_width + 7) // 8
                        spans.append({"field": name, "start": first, "length": last - first,
                                      "bit_offset": field.bit_offset,
                                      "bit_width": field.bit_width,
                                      "type": field.type_name})
                    edits_report.append({
                        "target": row_key(iso_path, member, table.name, index),
                        "iso_path": iso_path,
                        "member": member,
                        "table": table.name,
                        "record": index,
                        "record_offset": record_start,
                        "record_bytes": table.record_bytes,
                        "before": before,
                        "after": {name: after_db.value(table.name, index, name)
                                  for name in change["values"]},
                        "field_spans": spans,
                    })
                if len(new_payload) != len(payload):
                    raise TeamDataError(
                        f"editing member {member} of {iso_path} changed its length from "
                        f"{len(payload):,} to {len(new_payload):,}; a record edit cannot do "
                        f"that and the result is refused."
                    )
                stale = ea_tdb.verify_crcs(new_payload)
                if stale:
                    raise TeamDataError(
                        f"member {member} of {iso_path} came out with a checksum that does "
                        f"not match its own bytes: {stale[0]}"
                    )
                working = ea_terf.rewrite_member(working, member, new_payload)
                if len(working) != len(original):
                    raise TeamDataError(
                        f"rewriting member {member} changed {iso_path} from "
                        f"{len(original):,} to {len(working):,} bytes; this lane writes only "
                        f"inside the space a file already owns."
                    )
                members_report.append({
                    "iso_path": iso_path,
                    "member": member,
                    "bytes": len(new_payload),
                    "source_sha256": hashlib.sha256(payload).hexdigest(),
                    "destination_sha256": hashlib.sha256(new_payload).hexdigest(),
                })
            rebuilt[iso_path] = working
        return {
            "rebuilt": rebuilt,
            "edits": edits_report,
            "members": members_report,
            "target_keys": tuple(item[0] for item in order),
        }

    @staticmethod
    def _ranges(iso_report: Mapping[str, Any]) -> Tuple[DeclaredRange, ...]:
        out: List[DeclaredRange] = []
        for item in iso_report.get("declared_ranges", ()):
            row = item if isinstance(item, Mapping) else item.as_dict()
            out.append(DeclaredRange(int(row["start"]), int(row["length"]),
                                     str(row.get("reason", ""))))
        return tuple(out)

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        writer = _iso_writer()
        resolved = self._resolve(Path(source), recipe)
        try:
            report = writer.plan_report(Path(source), resolved["rebuilt"])
        except writer.IsoWriteError as exc:
            raise TeamDataError(str(exc)) from exc
        return Plan(
            lane_id=self.lane_id,
            target_keys=tuple(resolved["target_keys"]),
            declared_ranges=self._ranges(report),
            document={
                "schema": RECEIPT_SCHEMA,
                "edits": resolved["edits"],
                "members": resolved["members"],
                "files": sorted(resolved["rebuilt"]),
                "bytes_declared": int(report.get("bytes_declared", 0)),
            },
        )

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        if source.resolve() == destination.resolve():
            raise TeamDataError(
                "the destination is the source; this lane writes a new image and leaves "
                "yours untouched, so give it another name."
            )
        if destination.exists():
            raise TeamDataError(
                f"{destination} already exists and this lane never writes over an image; "
                f"choose a name that is not there yet."
            )
        writer = _iso_writer()
        resolved = self._resolve(source, recipe)
        try:
            report = writer.replace_files(source, destination, resolved["rebuilt"])
        except writer.IsoWriteError as exc:
            raise TeamDataError(str(exc)) from exc
        document = {
            "schema": RECEIPT_SCHEMA,
            "edits": resolved["edits"],
            "members": resolved["members"],
            "recipe": dict(recipe),
            "iso_write_report": writer.report_to_json(report),
        }
        return Receipt(
            schema=RECEIPT_SCHEMA,
            lane_id=self.lane_id,
            source=str(source),
            destination=str(destination),
            declared_ranges=self._ranges(report),
            document=document,
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        try:
            report = verify_build(Path(source), Path(destination), dict(receipt.document))
        except Refusal as exc:
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        return Verdict(
            True,
            f"team-data verifier: PASS · {report['edits_checked']} value(s) read back from "
            f"the destination · {report['members_checked']} database(s) re-parsed with "
            f"{report['checksum_sites']} checksum slot(s) all correct · "
            f"{report['undeclared_changed_bytes']} undeclared changed bytes.",
            report,
        )

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "madden09-ps2-teamdata-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc(tdb_member=synthetic_database()))
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        """One name, one number and one rating, on the synthetic disc's own rows."""

        player = team = None
        for target in catalogue.targets:
            if not target.key.startswith(ROW_PREFIX):
                continue
            _path, _member, table, _record = parse_row_key(target.key)
            if table == "PLAY" and player is None:
                player = target
            elif table == "TEAM" and team is None:
                team = target
        if player is None or team is None:
            raise Refusal(
                "the synthetic database carries no PLAY and TEAM rows to edit; rebuild the "
                "fixture from synthetic_database()."
            )
        return (
            Edit(player.key, {"PFNA": "Kit", "PJEN": 7, "POVR": 88}, note="conformance"),
            Edit(team.key, {"TDNA": "Testers"}, note="conformance"),
        )


# --------------------------------------------------------------------------
# The independent verifier
# --------------------------------------------------------------------------


def _iso_writer() -> Any:
    """The repository's bounded ISO writer, imported at call time.

    Inside a function because a game package may not reach outside the contract
    at module level, and because a lane that only ever catalogues should not
    pay for the import.
    """

    root = Path(__file__).resolve().parents[3]
    tools = root / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import ps2_iso9660_writer  # noqa: PLC0415

    return ps2_iso9660_writer


def _iso_verifier() -> Any:
    root = Path(__file__).resolve().parents[3]
    tools = root / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import ps2_iso9660_verify  # noqa: PLC0415

    return ps2_iso9660_verify


def _allowed_spans(edits: Sequence[Mapping[str, Any]], member: int,
                   iso_path: str) -> List[Tuple[int, int]]:
    """The byte runs inside one member an edit is entitled to have changed."""

    spans: List[Tuple[int, int]] = []
    for edit in edits:
        if int(edit["member"]) != member or str(edit["iso_path"]) != iso_path:
            continue
        for span in edit.get("field_spans", ()):
            spans.append((int(span["start"]), int(span["length"])))
    return spans


def verify_build(source: Path, destination: Path,
                 receipt_document: Mapping[str, Any]) -> Dict[str, Any]:
    """Re-derive, from the two images alone, that the build did what it claimed.

    **This function imports none of the writer.**  It uses the repository's
    independent ISO verifier for the container-level claim, this module's
    *reader* for the database, and ``ea_tdb.verify_crcs`` -- which recomputes
    every checksum from the destination's own bytes -- for the checksums.  What
    the receipt says is an input to be checked, never evidence.

    Four things are proved:

    1. outside the declared byte ranges the destination is the source, the two
       images are the same size, and no untouched file's extent moved
       (``ps2_iso9660_verify.verify_replacement``);
    2. every edited value **reads back** from the destination's own container,
       member, table, record and field;
    3. inside each edited database, every byte that differs from the source lies
       either in one of the declared field spans or in a checksum slot -- so a
       write that scribbled somewhere else is caught even though it is inside a
       declared ISO range;
    4. all four kinds of checksum in each edited database agree with the bytes
       that are there.

    Raises :class:`Refusal` naming the first violation; returns counts on pass.
    """

    verifier = _iso_verifier()
    iso_report = receipt_document.get("iso_write_report")
    if not isinstance(iso_report, Mapping):
        raise TeamDataError(
            "this receipt carries no ISO write report, so there is nothing to verify "
            "against; rebuild with this lane's build()."
        )
    try:
        iso_verdict = verifier.verify_replacement(source, destination, dict(iso_report))
    except verifier.IsoVerifyError as exc:
        raise TeamDataError(f"the destination image is not the source plus the declared "
                            f"edits: {exc}") from exc

    edits = [dict(item) for item in receipt_document.get("edits", ())]
    if not edits:
        raise TeamDataError("this receipt names no edit, so there is nothing to read back.")

    source_image = containers.open_disc(Path(source))
    destination_image = containers.open_disc(Path(destination))
    paths = sorted({str(edit["iso_path"]) for edit in edits})
    checked = 0
    members_checked = 0
    crc_sites = 0
    for iso_path in paths:
        name = iso_path.rsplit("/", 1)[-1]
        source_container = containers.load_container(source_image, name)
        destination_container = containers.load_container(destination_image, name)
        members = sorted({int(edit["member"]) for edit in edits
                          if str(edit["iso_path"]) == iso_path})
        for member in members:
            try:
                before = source_container.member(member)
                after = destination_container.member(member)
            except ea_terf.TerfError as exc:
                raise TeamDataError(
                    f"member {member} of {iso_path} could not be read back out of the "
                    f"destination: {exc}"
                ) from exc
            if len(before) != len(after):
                raise TeamDataError(
                    f"member {member} of {iso_path} is {len(before):,} bytes in the source "
                    f"and {len(after):,} in the destination; a record edit cannot change a "
                    f"length."
                )
            database = ea_tdb.parse_tdb(after)
            stale = ea_tdb.verify_crcs(after)
            if stale:
                raise TeamDataError(
                    f"member {member} of {iso_path} has a checksum that does not match its "
                    f"own bytes: {stale[0]}"
                )
            crc_sites += len(ea_tdb.crc_sites(after))
            members_checked += 1
            allowed = _allowed_spans(edits, member, iso_path)
            allowed.extend((site.offset, 4) for site in ea_tdb.crc_sites(after))
            for offset in range(len(before)):
                if before[offset] == after[offset]:
                    continue
                if not any(start <= offset < start + length for start, length in allowed):
                    raise TeamDataError(
                        f"byte {offset} of member {member} of {iso_path} changed and no "
                        f"declared field or checksum slot covers it; the write reached "
                        f"outside what it declared."
                    )
            for edit in edits:
                if int(edit["member"]) != member or str(edit["iso_path"]) != iso_path:
                    continue
                table = str(edit["table"])
                index = int(edit["record"])
                for field_name, expected in dict(edit["after"]).items():
                    found = database.value(table, index, field_name)
                    if found != expected:
                        raise TeamDataError(
                            f"{table} record {index} field {field_name} of member {member} "
                            f"reads {found!r} in the destination and the receipt says it "
                            f"should read {expected!r}."
                        )
                    checked += 1
    return {
        "schema": RECEIPT_SCHEMA,
        "source": str(source),
        "destination": str(destination),
        "verdict": "PASS",
        "edits_checked": checked,
        "members_checked": members_checked,
        "checksum_sites": crc_sites,
        "undeclared_changed_bytes": 0,
        "iso_bytes_compared": int(iso_verdict.get("unchanged_bytes_compared", 0)),
        "iso": {key: iso_verdict[key] for key in sorted(iso_verdict)
                if isinstance(iso_verdict.get(key), (int, str, bool))},
    }


# --------------------------------------------------------------------------
# The synthetic database
# --------------------------------------------------------------------------


def synthetic_database() -> bytes:
    """A small EA TDB built from the format's own rules, for the synthetic disc.

    Two tables named as the real ones are, carrying the fields this lane edits
    so the conformance harness exercises a name, a number and a rating, and
    with bit widths that deliberately straddle byte boundaries so a writer that
    mis-orders the bit packing is visibly wrong.  Nothing here comes from a
    game: the names are invented and the numbers are a counting ramp.

    The four checksums are written from the result's own bytes, so this fixture
    is a database that passes :func:`ea_tdb.verify_crcs` -- which is what makes
    it a fair test of a writer that has to keep them passing.
    """

    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        (
            "TEAM",
            (
                ("TGID", ea_tdb.FIELD_UINT, 11),
                ("TDNA", ea_tdb.FIELD_STRING, 17 * 8),
                ("TLNA", ea_tdb.FIELD_STRING, 18 * 8),
                ("TSNA", ea_tdb.FIELD_STRING, 7 * 8),
                ("TMNC", ea_tdb.FIELD_STRING, 17 * 8),
                ("TWIN", ea_tdb.FIELD_SINT, 5),
            ),
            (
                {"TGID": 1, "TDNA": "SYNTHETIC-A", "TLNA": "Nowhere",
                 "TSNA": "SYN", "TMNC": "Synths", "TWIN": 3},
                {"TGID": 900, "TDNA": "SYNTHETIC-B", "TLNA": "Elsewhere",
                 "TSNA": "SYB", "TMNC": "Others", "TWIN": -4},
            ),
        ),
        (
            "PLAY",
            (
                ("PGID", ea_tdb.FIELD_UINT, 15),
                ("PFNA", ea_tdb.FIELD_STRING, 11 * 8),
                ("PLNA", ea_tdb.FIELD_STRING, 13 * 8),
                ("PJEN", ea_tdb.FIELD_UINT, 7),
                ("PAGE", ea_tdb.FIELD_UINT, 6),
                ("POVR", ea_tdb.FIELD_UINT, 7),
                ("PSPD", ea_tdb.FIELD_UINT, 7),
                ("PAWR", ea_tdb.FIELD_UINT, 7),
                ("PWGT", ea_tdb.FIELD_UINT, 9),
            ),
            tuple({"PGID": 16384 + n, "PFNA": "Synth", "PLNA": f"Player{n}",
                   "PJEN": 10 + n, "PAGE": 22 + n, "POVR": 40 + n,
                   "PSPD": 50 + n, "PAWR": 60 + n, "PWGT": 180 + n}
                  for n in range(4)),
        ),
    )))


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.madden09_ps2.team_data --source DISC.iso``.

    With ``--recipe`` and ``--destination`` it also does the write: it plans,
    builds a NEW image, and runs the independent verifier over the result.  The
    source is opened read-only either way.
    """

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.team_data",
        description="List and edit the EA TDB databases on a Madden NFL 09 (PS2) disc.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--recipe", help="a JSON recipe of row edits, as compose_recipe writes")
    parser.add_argument("--destination", help="the NEW image to write; it must not exist")
    parser.add_argument("--report", help="write the build receipt and verdict to this JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan the edits and print the byte ranges; write nothing")
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
        document = dict(catalogue.document)
        if arguments.out:
            Path(arguments.out).write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n")
        print("TEAM_DATA databases=%d tables=%d records=%d fields=%d editable_rows=%d"
              % (document["databases"], document["tables"], document["records"],
                 document["fields"], document["editable_rows_listed"]))
        if not arguments.recipe:
            if arguments.destination:
                parser.error("--destination needs --recipe: there is nothing to write without one")
            return 0
        recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
        source = Path(arguments.source)
        if arguments.dry_run or not arguments.destination:
            plan = lane.plan(source, recipe, catalogue)
            for item in plan.declared_ranges:
                print("would write %d byte(s) at %d (%s)"
                      % (item.length, item.start, item.reason))
            print("TEAM_DATA_PLAN targets=%d bytes=%d"
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
        print("TEAM_DATA_WRITE %s" % ("PASS" if verdict.passed else "FAIL"))
        return 0 if verdict.passed else 1
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = ["CAPABILITY_ID", "EDITABLE_FIELDS", "EDITABLE_TABLES", "JERSEY_MAX",
           "KEEP_NUMBER", "LANE_ID", "MAX_ROW_TARGETS", "MAX_TARGETS", "PLAYER_FIELDS",
           "PRELOAD_COPIES", "RATING_MAX", "RECEIPT_SCHEMA", "RECIPE_SCHEMA", "ROW_PREFIX",
           "SCHEMA", "TDB_CONTAINERS", "TEAM_FIELDS", "TeamDataError", "TeamDataLane",
           "WRITABLE_CONTAINER", "fields_for", "number_bound", "parse_row_key", "row_key",
           "row_values", "synthetic_database", "text_budget", "verify_build"]


if __name__ == "__main__":
    raise SystemExit(_main())
