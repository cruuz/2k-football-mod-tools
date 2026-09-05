"""The disc's 102 playbooks: catalogued play by play, and now renamed.

Madden 09's playbooks are **EA TDB databases packed as ``LZH1`` members of
``/DATA/GAMEDATA.DAT``** [M].  The container holds 115 members; 104 of them are
databases; 102 of those carry the same nineteen tables -- ``ARTL FORM PBAI PBAU
PBFM PBPL PBST PLCM PLPD PLRD PLYL PLYS PSAL SETG SETL SETP SGF\\x00 SPKF
SPKG`` -- and are the shipped books [M].  The other two carry ``ARTL``,
``OPTM`` and ``PSAL`` only: they are the in-game route menus, not playbooks,
and this lane leaves them alone.

Until :func:`ea_tdb.decode_name` all 102 were unreadable here.  One of their
tables is named ``SGF`` followed by a **NUL byte**, and a reader that decoded a
name as strict printable ASCII refused the whole database before it reached a
row.  Nothing else stood in the way: with the name decoded and escaped, all 104
databases open and their **4,096 checksum slots all agree with their own
bytes** [M].

What this page edits
--------------------

**Names.**  Eight of the nineteen tables carry a ``STRING`` field called
``name``, and every one of them is offered (:data:`EDITABLE_FIELDS`): the
formation names, the set and set-group names, the play names, and the
special-teams formation names.  Renaming a play is what a playbook editor is
for, and a name is the one value in these tables whose meaning is not in doubt.

**Six numbers, each with a source.**  A numeric field is offered only where the
owner's research says what it means -- ``FORM.FTYP`` and its two siblings (the
six-valued formation type), the audible slot ``PBAU.PBAU``, and ``PLYL.risk``
and ``PLYL.motn``.  Everything else in these tables is a row id, a foreign key
or an undecoded number, and this page does not offer it: a renamed play is a
bounded change, a re-pointed foreign key is a dangling reference nobody has
booted.

**No rows are added or removed.**  Every table in every shipped book has
``record_count == max_records`` -- 1,944 of 1,944 [M] -- so there is not one
spare slot anywhere on the disc.  Adding a play means growing a table, which
means the editor caps in the executable, which is the **Gameplay** page's
separate route (:mod:`.code_patches`).  This page writes inside the rows that
are already there.

Why a member rewrite is safe here, and where the caches come in
---------------------------------------------------------------

``GAMEDATA.DAT`` is named in **both** preload caches, so the whole-container
refusal the sibling database lane uses would refuse every playbook.  The rule
here is finer, and it is read off the user's own image
(:func:`containers.preload_copies`) rather than written down:

* ``GAME.QKL`` carries byte copies of ``GAMEDATA.DAT`` members **103..112** and
  no copy of its directory [M].  Those are the UI screens at the end of the
  container -- **no playbook is cached**, which is what makes members 0..101
  writable at all.  A member that *is* cached is refused by name.
* ``FE.QKL`` carries **two copies of the container's directory** -- its first
  ``data_offset`` bytes -- and no members [M].  So a rewrite that changes the
  directory has to change both copies with it, or the game preloads a stale one.

A record edit never changes a database's length, so the only thing that can
move the directory is the **re-encoded member's stored size**.  This lane
therefore re-encodes under a byte budget equal to the size the member already
occupies and, when the stream fits, pads it to exactly that size and splices it
in place: the directory comes back byte-identical, both cache copies stay
correct untouched, and the image keeps its length.  On the retail disc that is
the ordinary case by a wide margin -- our encoder comes out about 5.5 % smaller
than EA's on every book sampled, so a book has 750 to 4,000 bytes of headroom
[M].  When a stream does not fit, the member is rewritten through
:func:`ea_terf.plan_member_rewrite` / :func:`ea_terf.rewrite_member`, the image
is allowed to grow, and both directory copies are rewritten with it.

**Nothing here has been seen in a running game.**  The evidence is offline: a
destination image, an independent verifier that re-reads it, and a conformance
harness that proves the whole path on a synthetic disc.  No emulator has booted
a rebuilt Madden 09 disc, and this module does not claim one has.
``docs/product/MADDEN09_PS2_PLAYBOOKS.md`` says what a boot would have to show.

Run it without a window::

    python3 -m mod_editor.games.madden09_ps2.playbooks_lane --source DISC.iso

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

CAPABILITY_ID = "madden09ps2.playbooks.databases"
LANE_ID = "playbooks.databases"
SCHEMA = "madden09_ps2_playbook_catalog/v1"
RECIPE_SCHEMA = "madden09_ps2_playbook_edit/v1"
RECEIPT_SCHEMA = "madden09_ps2_playbook_write/v1"

#: The one container that holds playbooks [M].
CONTAINER = containers.GAME_DATA_CONTAINER
CONTAINER_PATH = f"{containers.DATA_DIRECTORY}/{CONTAINER}"

#: The nineteen tables a shipped playbook carries, in alphabetical order [M].
#: ``SGF\x00`` is spelled as :func:`ea_tdb.decode_name` renders it: three
#: characters and the NUL byte the file actually stores.
PLAYBOOK_TABLES: Tuple[str, ...] = (
    "ARTL", "FORM", "PBAI", "PBAU", "PBFM", "PBPL", "PBST", "PLCM", "PLPD",
    "PLRD", "PLYL", "PLYS", "PSAL", "SETG", "SETL", "SETP", "SGF\\x00",
    "SPKF", "SPKG",
)

#: What makes a member a playbook rather than one of the two route-menu
#: databases beside them: the two tables the play graph is navigable through
#: [S -- the owner's ``tools/madden_play.py`` uses the same pair].  Tested
#: against the file's own table list, never against a member index.
PLAYBOOK_MARKERS: Tuple[str, ...] = ("PLYL", "PBPL")

#: The tables whose rows this lane offers, in the order a page shows them:
#: the book's shape first (formations, then sets, then plays), then the
#: special-teams and audible rows.
EDITABLE_TABLES: Tuple[str, ...] = (
    "FORM", "PBFM", "PBST", "SETL", "SGF\\x00", "PBPL", "PLYL", "SPKF", "PBAU",
)

#: What a number field is set to when the user means "leave this alone".  The
#: convention the sibling lanes already use: a text box can be left blank and
#: dropped, a spinner always holds some value.
KEEP_NUMBER = -1

#: ``FORM.FTYP``'s six values and what each is, read off the formation names of
#: all 102 shipped books [S -- the owner's ``madden09-iso-contents.md`` §6].
#: Quoted in a help string so a user changing one knows what they are choosing;
#: the field is written as a plain number, because a seventh value this table
#: does not list would otherwise be unrepresentable.
FORMATION_TYPES: Mapping[int, str] = {
    1: "offence",
    2: "kickoff",
    3: "safety kickoff",
    11: "defence",
    12: "kick return",
    13: "safety kick return",
}

_FTYP_HELP = (
    "Which side of the ball this formation is, as the file's own six values "
    "spell it: " + ", ".join(f"{value} = {label}"
                             for value, label in sorted(FORMATION_TYPES.items())) + "."
)

#: A ``name`` field, described once.  Every one of the eight is a ``STRING``
#: whose width the file declares, so the character budget is read from the
#: table rather than written down here.
_NAME = ("name", "Name", "The name this row is drawn under.", None)


#: The fields this lane offers, per table.  Each is
#: ``(field name, label, help, maximum)``; ``maximum`` of ``None`` means the
#: field's own width is the bound.  A field a table does not declare is
#: skipped, so a database with another schema simply offers less.
EDITABLE_FIELDS: Mapping[str, Tuple[Tuple[str, str, str, Optional[int]], ...]] = {
    "FORM": (
        ("name", "Formation name", "The formation's name, e.g. the shape the "
                                   "offence lines up in.", None),
        ("FTYP", "Formation type", _FTYP_HELP, None),
    ),
    "PBFM": (
        ("name", "Formation name", "This book's name for the formation.", None),
        ("FTYP", "Formation type", _FTYP_HELP, None),
    ),
    "PBST": (
        ("name", "Set name", "This book's name for the set.", None),
    ),
    "SETL": (
        ("name", "Set name", "The set's name -- the personnel and alignment "
                             "under a formation.", None),
    ),
    "SGF\\x00": (
        ("name", "Group name", "The short label this set group is drawn under.", None),
    ),
    "PBPL": (
        ("name", "Play name", "This book's name for the play.", None),
    ),
    "PLYL": (
        ("name", "Play name", "The play's name.", None),
        ("risk", "Risk", "The play's risk rating, as the file stores it "
                         "(the meaning of the scale is not decoded here).", None),
        ("motn", "Motion", "1 when the play sends a man in motion, 0 when it "
                           "does not.", None),
    ),
    "SPKF": (
        ("name", "Formation name", "The special-teams formation's name.", None),
    ),
    "PBAU": (
        ("PBAU", "Audible slot", "Which of the formation's audible slots this "
                                 "row fills.", None),
        ("FTYP", "Formation type", _FTYP_HELP, None),
    ),
}

#: How a row target's key is spelled: ``row:<iso path>#<member>:<table>:<record>``.
ROW_PREFIX = "row:"

#: How many read-only book and table targets are listed.  A retail disc's 102
#: books contribute one target each plus one per table -- 2,040 [M] -- so the
#: cap is generous; the document says how many were listed either way.
MAX_BOOK_TARGETS = 4096

#: How many editable rows are listed.  The 102 shipped books hold about 78,900
#: rows across the nine tables above [M], and the cap is above that so a retail
#: disc lists every one.
MAX_ROW_TARGETS = 120000

#: What a book target's detail quotes: the tables whose row counts say what
#: kind of book it is.
BOOK_COUNT_TABLES = ("PBFM", "PBST", "PBPL")


class PlaybookError(Refusal):
    """This lane could not do what was asked; the sentence says why."""


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------


def book_key(member: int) -> str:
    """The target key for one playbook."""

    return f"book:{CONTAINER_PATH}#{member}"


def table_key(member: int, table: str) -> str:
    """The target key for one table of one playbook."""

    return f"table:{CONTAINER_PATH}#{member}:{table}"


def row_key(member: int, table: str, record: int) -> str:
    """The target key for one record of one table of one playbook."""

    return f"{ROW_PREFIX}{CONTAINER_PATH}#{member}:{table}:{record}"


def parse_row_key(key: str) -> Tuple[str, int, str, int]:
    """``row:/DATA/GAMEDATA.DAT#67:SETL:3`` back into its four parts."""

    if not key.startswith(ROW_PREFIX):
        raise PlaybookError(
            f"{key!r} is not an editable row; a row's key is spelled "
            f"{ROW_PREFIX}<container>#<member>:<table>:<record>, and the book and "
            f"table targets beside them are read-only."
        )
    rest = key[len(ROW_PREFIX):]
    try:
        head, table, record = rest.rsplit(":", 2)
        path, member = head.rsplit("#", 1)
        return path, int(member), table, int(record)
    except ValueError as exc:
        raise PlaybookError(
            f"{key!r} is not a row key this lane writes; it should read "
            f"{ROW_PREFIX}<container>#<member>:<table>:<record>."
        ) from exc


# --------------------------------------------------------------------------
# Fields
# --------------------------------------------------------------------------


def text_budget(field: ea_tdb.TdbField) -> int:
    """How many characters a ``STRING`` field takes, terminator excluded."""

    return max(0, field.bit_width // 8 - 1)


def number_bound(field: ea_tdb.TdbField, maximum: Optional[int]) -> int:
    """The largest value a numeric field takes: the smaller of scale and width."""

    width_bound = (1 << field.bit_width) - 1
    return width_bound if maximum is None else min(maximum, width_bound)


def fields_for(table: ea_tdb.TdbTable) -> Tuple[Field, ...]:
    """The editor controls one row of *table* offers, in list order.

    Built once per table schema and shared by every row of it: the 102 books
    hold about 78,900 editable rows and each carrying its own copies of the
    field descriptions would be a quarter of a million objects for no
    information.

    A field the table does not declare is skipped, and so is a numeric field
    that is not ``UINT``: every number this page offers is unsigned on the disc
    [M], and a signed one would need a different bound than the width gives.
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
        elif field.type_id == ea_tdb.FIELD_UINT:
            bound = number_bound(field, maximum)
            out.append(Field(
                name, "int", label,
                f"{help_text} {KEEP_NUMBER} keeps the value that is there.",
                minimum=KEEP_NUMBER, maximum=bound,
            ))
    return tuple(out)


def row_values(database: ea_tdb.TdbDatabase, table: ea_tdb.TdbTable, index: int,
               shape: Sequence[Field]) -> Dict[str, Any]:
    """What the row holds today, for the fields this lane offers."""

    record = database.record_bytes(table, index)
    return {item.key: database.decode(table.field(item.key), record) for item in shape}


def is_playbook(database: ea_tdb.TdbDatabase) -> bool:
    """Does this database carry the play graph, rather than a route menu?"""

    names = set(database.table_names)
    return all(marker in names for marker in PLAYBOOK_MARKERS)


# --------------------------------------------------------------------------
# The lane
# --------------------------------------------------------------------------


class PlaybooksLane:
    """The 102 shipped playbooks, and the names inside them."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "scripts_config"
    page = "playbooks"
    title = "Playbook formation, set and play names"
    classification = "offline-writer-proved"
    recipe_schema = RECIPE_SCHEMA
    validators = (
        "tools/validate_madden09_ps2_playbooks.sh",
        "tools/validate_madden09_ps2_playbooks.bat",
    )
    #: The image keeps its length whenever the re-encoded member fits the size
    #: it already occupies, which is the ordinary case -- our ``LZH1`` streams
    #: come out about 5.5 % under EA's on every book sampled [M].  It is not
    #: guaranteed, so the honest answer is False and the receipt carries the
    #: number.
    fixed_allocation = False
    read_only = False

    NOT_BOOTED = (
        "No rebuilt Madden 09 disc has been booted. Every step here is proved against your "
        "own bytes offline -- the edited database re-parses out of the destination with the "
        "values you asked for, all four kinds of TDB checksum agree with the bytes that are "
        "there, both preload-cache copies of the container's directory still equal it, and "
        "every byte outside the declared ranges is unchanged -- but whether the game reads "
        "the renamed play is not something this tool can find out."
    )

    NO_BOOK_NAME = (
        "The disc gives a playbook no name of its own: no table in it carries a book-level "
        "name field and no string bank on the image lists the books, so a book is named here "
        "by the container member it is, and described by what it holds."
    )

    # -- catalogue -----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        image = containers.open_disc(Path(source))
        files = {entry.name: entry for entry in containers.data_files(image)}
        entry = files.get(CONTAINER)
        if entry is None:
            raise PlaybookError(
                f"this image holds no {CONTAINER_PATH}; it is not a Madden NFL 09 "
                f"PlayStation 2 disc, or the container has been removed."
            )
        preload = containers.preload_copies(image)
        cached = preload.get(CONTAINER.upper()) or preload.get(CONTAINER)
        blob = containers.read_file(image, entry)
        container = ea_terf.parse_terf(blob, allow_size_mismatch=True)

        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        row_targets: List[Target] = []
        shapes: Dict[Tuple[Any, ...], Tuple[Field, ...]] = {}
        totals = {"books": 0, "tables": 0, "records": 0, "fields": 0,
                  "checksum_sites": 0, "checksum_sites_wrong": 0}
        skipped: Dict[str, str] = {}

        for index in range(container.member_count):
            member = container.members[index]
            try:
                if container.member_format(index) != ea_terf.FORMAT_TDB:
                    continue
                payload = containers.member_uncached(container, index)
            except ea_terf.TerfError as exc:
                skipped[str(index)] = str(exc)
                continue
            try:
                database = ea_tdb.parse_tdb(payload)
            except ea_tdb.TdbError as exc:
                skipped[str(index)] = str(exc)
                continue
            if not is_playbook(database):
                skipped[str(index)] = (
                    "a database of " + ", ".join(database.table_names)
                    + "; it carries no play graph, so it is not a playbook."
                )
                continue
            if progress is not None and totals["books"] % 16 == 0:
                progress(f"{CONTAINER} member {index}…")
            row = self._book_row(index, member, payload, database)
            totals["books"] += 1
            totals["checksum_sites"] += row["checksum_sites"]
            totals["checksum_sites_wrong"] += row["checksum_sites_wrong"]
            for table in row["tables"]:
                totals["tables"] += 1
                totals["records"] += int(table["records"])
                totals["fields"] += int(table["field_count"])
            rows.append(row)
            writable = self._writable_reason(cached, index)
            if len(targets) < MAX_BOOK_TARGETS:
                targets.extend(self._targets_for(row, writable))
            if len(row_targets) < MAX_ROW_TARGETS:
                row_targets.extend(self._rows_of(index, database, shapes, writable,
                                                 MAX_ROW_TARGETS - len(row_targets)))

        document = {
            "schema": SCHEMA,
            "source": str(source),
            "container": CONTAINER_PATH,
            "container_bytes": len(blob),
            "container_members": container.member_count,
            "books": totals["books"],
            "tables": totals["tables"],
            "records": totals["records"],
            "fields": totals["fields"],
            "checksum_sites": totals["checksum_sites"],
            "checksum_sites_wrong": totals["checksum_sites_wrong"],
            "editable_tables": list(EDITABLE_TABLES),
            "editable_rows_listed": len(row_targets),
            "editable_rows_cap": MAX_ROW_TARGETS,
            "books_listed": len(rows),
            "targets_listed": len(targets) + len(row_targets),
            "preload": {
                "directory_copies": [copy.as_dict() for copy in (cached.header if cached else ())],
                "cached_members": sorted(cached.members) if cached else [],
            },
            "skipped": skipped,
            "book_names": self.NO_BOOK_NAME,
            "rows": rows,
            "note": "Every shipped playbook on the disc: its tables, how many records each "
                    "holds against its capacity, and every field's name, type and width. The "
                    "names inside them are read from your own image into the targets and are "
                    "not part of this document.",
        }
        return Catalogue(SCHEMA, self.lane_id, str(source),
                         tuple(targets) + tuple(row_targets), document)

    @staticmethod
    def _writable_reason(cached: Optional[containers.ContainerPreload],
                         member: int) -> Optional[str]:
        """Why this member may not be written, or ``None`` when it may.

        The rule is read off the user's own image: a member a preload cache
        carries a byte copy of cannot be rewritten at a new size without
        rewriting that copy too, and a cached copy is a fixed slot.  On the
        retail disc no playbook is cached [M], so this is a guard rather than a
        refusal anyone meets.
        """

        copies = cached.for_member(member) if cached is not None else ()
        if not copies:
            return None
        names = ", ".join(sorted({copy.cache for copy in copies}))
        return (
            f"{CONTAINER} member {member} is copied byte for byte into {names}, the preload "
            f"cache the game loads from, and a cached copy is a fixed slot; this lane will "
            f"not rewrite a member it cannot keep that copy in step with."
        )

    def _book_row(self, index: int, member: Any, payload: bytes,
                  database: ea_tdb.TdbDatabase) -> Dict[str, Any]:
        """One playbook as names, counts and digests -- never a value."""

        sites = ea_tdb.crc_sites(payload)
        row: Dict[str, Any] = {
            "member": index,
            "path": CONTAINER_PATH,
            "codec": member.codec,
            "codec_name": member.codec_name,
            "stored_bytes": member.stored_size,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "version": database.version,
            "table_count": database.table_count,
            "checksum_sites": len(sites),
            "checksum_sites_wrong": sum(1 for site in sites if not site.matches),
            "tables": [],
        }
        for table in database.tables:
            row["tables"].append({
                "name": table.name,
                "records": table.current_records,
                "capacity": table.max_records,
                "record_bytes": table.record_bytes,
                "field_count": table.field_count,
                "editable": table.name in EDITABLE_TABLES,
                "fields": [
                    {"name": item.name, "type": item.type_name,
                     "bit_offset": item.bit_offset, "bit_width": item.bit_width}
                    for item in table.fields
                ],
            })
        return row

    def _targets_for(self, row: Mapping[str, Any],
                     writable: Optional[str]) -> List[Target]:
        """One read-only target for the book, and one per table inside it."""

        member = int(row["member"])
        counts = {table["name"]: table["records"] for table in row["tables"]}
        detail = " · ".join(
            [f"{counts.get(name, 0):,} {label}"
             for name, label in (("PBFM", "formations"), ("PBST", "sets"),
                                 ("PBPL", "plays"))]
            + [f"{row['bytes']:,} bytes"]
        )
        budget = (writable or
                  "Its rows are listed below; a name is written where it already sits.")
        out = [Target(
            key=book_key(member),
            label=f"{CONTAINER} member {member}",
            detail=detail,
            budget=budget,
            searchable=f"{CONTAINER} playbook {member}",
            raw=dict(row, tables=[table["name"] for table in row["tables"]]),
            fields=(
                Field("member", "note", "Member",
                      "Which member of the container this book is. The disc gives a "
                      "playbook no name of its own.", read_only=True),
                Field("table_count", "note", "Tables", "How many tables it carries.",
                      read_only=True),
                Field("bytes", "note", "Bytes", "The decompressed database's length.",
                      read_only=True),
                Field("stored_bytes", "note", "Packed bytes",
                      "How many bytes it occupies in the container.", read_only=True),
                Field("checksum_sites", "note", "Checksum slots",
                      "How many CRC slots the database carries, and how many disagree "
                      "with their own bytes.", read_only=True),
                Field("sha256", "note", "Digest",
                      "SHA-256 of the decompressed database.", read_only=True),
            ),
        )]
        for table in row["tables"]:
            out.append(Target(
                key=table_key(member, str(table["name"])),
                label=f"{CONTAINER} member {member} · {table['name']}",
                detail=f"{table['records']:,} of {table['capacity']:,} records · "
                       f"{table['record_bytes']} bytes/record · "
                       f"{table['field_count']} fields",
                budget=("Its rows are listed below." if table["editable"] else
                        "Read-only: this page offers no field of this table, because "
                        "nothing it holds has a decoded meaning to offer."),
                searchable=f"{CONTAINER} {member} {table['name']} "
                           + " ".join(item["name"] for item in table["fields"]),
                raw=dict(table, member=member, path=CONTAINER_PATH),
                fields=(
                    Field("name", "note", "Table", "The table's four-character name, "
                                                   "as the file spells it.", read_only=True),
                    Field("records", "note", "Records", "How many records it holds.",
                          read_only=True),
                    Field("capacity", "note", "Capacity",
                          "How many records it has room for. Every shipped table is "
                          "exactly full, so no row can be added here.", read_only=True),
                    Field("record_bytes", "note", "Record stride",
                          "How many bytes one record occupies.", read_only=True),
                    Field("fields", "note", "Field names",
                          "Every field's name, type and bit width.", read_only=True),
                ),
            ))
        return out

    def _rows_of(self, member: int, database: ea_tdb.TdbDatabase,
                 shapes: Dict[Tuple[Any, ...], Tuple[Field, ...]],
                 writable: Optional[str], remaining: int) -> List[Target]:
        """The editable rows of one playbook: one target per record."""

        out: List[Target] = []
        budget = (writable or
                  "Written where it already sits: the record keeps its length, the "
                  "database keeps its length, and the member is re-packed to the size it "
                  "already occupies whenever the stream fits.")
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
                    key=row_key(member, table_name, index),
                    label=self._row_label(table_name, member, index, values),
                    detail=f"member {member} · {table_name} record {index}",
                    budget=budget,
                    searchable=f"{CONTAINER} {member} {table_name} {index} "
                               + " ".join(str(value) for value in values.values()),
                    raw={
                        "iso_path": CONTAINER_PATH,
                        "member": member,
                        "table": table_name,
                        "record": index,
                        "record_bytes": table.record_bytes,
                        "values": values,
                        "writable": writable is None,
                    },
                    fields=shape,
                ))
        return out

    @staticmethod
    def _row_label(table: str, member: int, index: int,
                   values: Mapping[str, Any]) -> str:
        name = str(values.get("name", "")).strip()
        return name or f"member {member} · {table} {index}"

    # -- editing -------------------------------------------------------

    @staticmethod
    def _shape(target: Target) -> Dict[str, Field]:
        return {item.key: item for item in target.fields if not item.read_only}

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        """One sentence saying why an edit does not fit, or ``None``."""

        if not target.key.startswith(ROW_PREFIX):
            return (
                f"{target.key} is a description of a playbook or one of its tables, not a "
                f"row of one. Choose a formation, set or play row to edit."
            )
        if not target.raw.get("writable", True):
            return self._writable_refusal(int(target.raw.get("member", -1)))
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
            high = int(item.maximum if item.maximum is not None else 0)
            if not 0 <= value <= high:
                return (f"{item.label} takes 0 to {high} and {value} is outside that; "
                        f"{KEEP_NUMBER} leaves the value alone.")
            if value != current.get(key):
                changing += 1
        if not changing:
            return ("Nothing in this row would change. Type a new value, or leave the row "
                    "alone.")
        return None

    @staticmethod
    def _writable_refusal(member: int) -> str:
        return (
            f"{CONTAINER} member {member} is carried byte for byte inside a preload cache, "
            f"and a cached copy is a fixed slot; this lane will not rewrite a member it "
            f"cannot keep that copy in step with."
        )

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows: List[Dict[str, Any]] = []
        for edit in edits:
            values = {key: value for key, value in edit.values.items()
                      if not (value == "" or value == KEEP_NUMBER)}
            row: Dict[str, Any] = {"target": edit.target_key, "values": values}
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": RECIPE_SCHEMA, "edits": rows}

    # -- plan / build / verify -----------------------------------------

    @staticmethod
    def _recipe_edits(recipe: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        if not isinstance(recipe, Mapping) or str(recipe.get("schema")) != RECIPE_SCHEMA:
            raise PlaybookError(
                f"this recipe says it is "
                f"{recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r} and "
                f"this lane writes {RECIPE_SCHEMA}; hand it a recipe compose_recipe made."
            )
        rows = recipe.get("edits")
        if not isinstance(rows, list) or not rows:
            raise PlaybookError(
                "this recipe changes nothing: its 'edits' list is empty, and a build with "
                "nothing to write would be a plain copy."
            )
        return [dict(row) for row in rows]

    def _resolve(self, source: Path, recipe: Mapping[str, Any],
                 catalogue: Optional[Catalogue]) -> Dict[str, Any]:
        """Work out every changed byte from the user's own image, writing nothing.

        Done in full by ``plan`` as well as by ``build``: whether the re-encoded
        member still fits the size it occupies is what decides whether the
        directory moves, and "it probably fits" is not a plan.
        """

        wanted: Dict[int, Dict[str, Dict[str, Any]]] = {}
        order: List[str] = []
        for row in self._recipe_edits(recipe):
            key = str(row.get("target", ""))
            if catalogue is not None:
                catalogue.target(key)               # the catalogue's own refusal
            iso_path, member, table, record = parse_row_key(key)
            if iso_path != CONTAINER_PATH:
                raise PlaybookError(
                    f"{key} names {iso_path}, and the playbooks live in {CONTAINER_PATH}; "
                    f"this lane writes nothing else."
                )
            if table not in EDITABLE_TABLES:
                raise PlaybookError(
                    f"{key} names the table {table}, and this page writes "
                    + ", ".join(EDITABLE_TABLES) + "."
                )
            values = row.get("values")
            if not isinstance(values, Mapping) or not values:
                raise PlaybookError(
                    f"{key} names no value to write; every edit must carry at least one."
                )
            slot = wanted.setdefault(member, {})
            merged = slot.setdefault(f"{table}:{record}",
                                     {"table": table, "record": record, "values": {}})
            merged["values"].update(values)
            if key not in order:
                order.append(key)

        image = containers.open_disc(Path(source))
        files = {entry.name: entry for entry in containers.data_files(image)}
        entry = files.get(CONTAINER)
        if entry is None:
            raise PlaybookError(
                f"this image holds no {CONTAINER_PATH}; it is not a Madden NFL 09 "
                f"PlayStation 2 disc, or the container has been removed."
            )
        preload = containers.preload_copies(image)
        cached = preload.get(CONTAINER.upper()) or preload.get(CONTAINER)

        original = containers.read_file(image, entry)
        blob = original
        edits_report: List[Dict[str, Any]] = []
        members_report: List[Dict[str, Any]] = []
        for member in sorted(wanted):
            refusal = self._writable_reason(cached, member)
            if refusal is not None:
                raise PlaybookError(refusal)
            container = ea_terf.parse_terf(blob, allow_size_mismatch=True)
            if not 0 <= member < container.member_count:
                raise PlaybookError(
                    f"{CONTAINER} has {container.member_count} member(s) and this recipe "
                    f"names member {member}; choose one the catalogue lists."
                )
            payload = containers.member_uncached(container, member)
            database = ea_tdb.parse_tdb(payload)
            if not is_playbook(database):
                raise PlaybookError(
                    f"{CONTAINER} member {member} carries no play graph, so it is not a "
                    f"playbook; this page writes the 102 that are."
                )
            new_payload = payload
            for entry_key in sorted(wanted[member]):
                change = wanted[member][entry_key]
                working = ea_tdb.parse_tdb(new_payload)
                table = working.table(str(change["table"]))
                index = int(change["record"])
                before = {name: working.value(table, index, name)
                          for name in change["values"]}
                new_payload = ea_tdb.write_records(
                    working, table.name, {index: dict(change["values"])})
                after = ea_tdb.parse_tdb(new_payload)
                record_start = after.record_offset(table.name, index)
                spans = []
                for name in sorted(change["values"]):
                    field = table.field(name)
                    first = record_start + field.bit_offset // 8
                    last = record_start + (field.bit_offset + field.bit_width + 7) // 8
                    spans.append({"field": name, "start": first, "length": last - first,
                                  "bit_offset": field.bit_offset,
                                  "bit_width": field.bit_width, "type": field.type_name})
                edits_report.append({
                    "target": row_key(member, table.name, index),
                    "iso_path": CONTAINER_PATH,
                    "member": member,
                    "table": table.name,
                    "record": index,
                    "record_offset": record_start,
                    "record_bytes": table.record_bytes,
                    "before": before,
                    "after": {name: after.value(table.name, index, name)
                              for name in change["values"]},
                    "field_spans": spans,
                })
            if len(new_payload) != len(payload):
                raise PlaybookError(
                    f"editing member {member} changed its length from {len(payload):,} to "
                    f"{len(new_payload):,}; a record edit cannot do that and the result is "
                    f"refused."
                )
            stale = ea_tdb.verify_crcs(new_payload)
            if stale:
                raise PlaybookError(
                    f"member {member} came out with a checksum that does not match its own "
                    f"bytes: {stale[0]}"
                )
            blob, note = self._repack(blob, member, new_payload)
            members_report.append(dict(
                note, member=member, payload_bytes=len(new_payload),
                source_sha256=hashlib.sha256(payload).hexdigest(),
                destination_sha256=hashlib.sha256(new_payload).hexdigest()))

        rebuilt = ea_terf.parse_terf(blob, allow_size_mismatch=True)
        violations = rebuilt.layout_violations()
        if violations:
            raise PlaybookError(
                f"the rebuilt {CONTAINER} broke the container's own layout rules "
                f"({violations[0]}); nothing was written."
            )
        caches, cache_notes = self._patch_preload(image, files, cached, original, blob)
        written: Dict[str, bytes] = {CONTAINER: blob}
        written.update(caches)
        paths = {name: files[name].path for name in written}
        grows = [name for name, payload in written.items()
                 if len(payload) > int(files[name].recorded_length)]
        return {
            "written": written,
            "paths": paths,
            "grows": grows,
            "edits": edits_report,
            "members": members_report,
            "cache_copies": cache_notes,
            "target_keys": tuple(order),
        }

    @staticmethod
    def _repack(blob: bytes, member: int, payload: bytes) -> Tuple[bytes, Dict[str, Any]]:
        """Put *payload* back into member *member*, smallest disturbance first.

        **The exact-size path.**  The member's ``LZH1`` stream is re-encoded
        under a budget equal to the bytes it already occupies and, when it
        fits, padded with NULs to exactly that size and spliced in place.  Every
        directory word -- the member's offset, its stored size, its codec and
        its decompressed size -- is then unchanged by construction, so no other
        member moves, the container keeps its length, and the two copies of the
        directory the preload cache carries stay correct without being touched.

        Padding is safe because a bounded decode never reads it: the decoder
        stops when it has produced the declared number of bytes, which happens
        at the end of the block and before the trailing NULs [M -- proved on
        the disc's own members, and by the round trip below on every write].

        **The growth path.**  When the stream does not fit -- or when the
        member is not an ``LZH1`` one to begin with, because the splice leaves
        the codec word alone and would then contradict it --
        :func:`ea_terf.plan_member_rewrite` chooses the codec and
        :func:`ea_terf.rewrite_member` lays the container out again.  Members
        after this one move, the directory changes, and the caller mirrors it
        into the caches.  Every TDB member of the retail disc's
        ``GAMEDATA.DAT`` is ``LZH1`` [M], so the splice is the ordinary case
        and the codec test is a guard against an image that is not this one.
        """

        parsed = ea_terf.parse_terf(blob, allow_size_mismatch=True)
        slot = parsed.members[member].stored_size
        directory_before = blob[:parsed.data_offset]
        # No ``budget=`` here on purpose: an overrun is a fact to act on, not a
        # refusal to swallow, and swallowing it would hide a real encoder
        # failure behind a silent fall-through to the growth path.
        stream, report = ea_terf.lzh1_compress_report(payload, reference_bytes=slot)
        if parsed.members[member].codec == ea_terf.CODEC_LZH1 and len(stream) <= slot:
            padded = stream + b"\x00" * (slot - len(stream))
            if ea_terf.decompress_member(padded, ea_terf.CODEC_LZH1, len(payload)) != payload:
                raise PlaybookError(                        # pragma: no cover - encoder defect
                    f"the re-encoded member {member} did not decode back to the database it "
                    f"was made from once padded to its slot; nothing was written."
                )
            start = parsed.data_offset + parsed.members[member].offset
            out = bytearray(blob)
            out[start:start + slot] = padded
            blob = bytes(out)
            after = ea_terf.parse_terf(blob, allow_size_mismatch=True)
            if after.stored(member) != padded or blob[:after.data_offset] != directory_before:
                raise PlaybookError(                        # pragma: no cover - splice defect
                    f"splicing member {member} back moved a byte outside its own slot; "
                    f"nothing was written."
                )
            return blob, {
                "path": "exact-size",
                "codec": ea_terf.CODEC_LZH1,
                "codec_name": ea_terf.CODEC_NAMES[ea_terf.CODEC_LZH1],
                "stored_bytes": slot,
                "previous_stored_size": slot,
                "stream_bytes": len(stream),
                "padding_bytes": slot - len(stream),
                "headroom": report.headroom,
                "directory_changed": False,
                "grows_container": False,
                "start": start,
                "length": slot,
                "note": (f"LZH1 in {len(stream)} byte(s), padded to the {slot} the member "
                         f"already occupies: the container directory is unchanged and no "
                         f"other member moves."),
            }
        plan = ea_terf.plan_member_rewrite(blob, member, payload)
        grown = ea_terf.rewrite_member(blob, member, payload, codec=plan.codec)
        after = ea_terf.parse_terf(grown, allow_size_mismatch=True)
        return grown, dict(
            plan.as_dict(),
            path="rewrite",
            directory_changed=grown[:after.data_offset] != directory_before,
            stream_bytes=len(plan.packed),
            padding_bytes=0,
            headroom=slot - len(plan.packed),
        )

    @staticmethod
    def _patch_preload(image: Any, files: Mapping[str, Any],
                       cached: Optional[containers.ContainerPreload],
                       before: bytes, after: bytes
                       ) -> Tuple[Dict[str, bytes], List[Dict[str, Any]]]:
        """Keep the caches' copies of this container's directory in step with it.

        ``FE.QKL`` carries two byte copies of ``GAMEDATA.DAT``'s first
        ``data_offset`` bytes [M].  A copy is a fixed slot, so a directory that
        changed *length* could not be mirrored -- that is refused by name --
        and one that changed *content* is written into both copies.  When the
        exact-size path was taken the directory did not change at all and this
        returns nothing to write, which is the point of that path.
        """

        notes: List[Dict[str, Any]] = []
        if cached is None or cached.empty:
            return {}, notes
        parsed_before = ea_terf.parse_terf(before, allow_size_mismatch=True)
        parsed_after = ea_terf.parse_terf(after, allow_size_mismatch=True)
        if before[:parsed_before.data_offset] == after[:parsed_after.data_offset]:
            return {}, notes
        if parsed_after.data_offset != parsed_before.data_offset:
            raise PlaybookError(
                f"the rebuilt {CONTAINER}'s directory is {parsed_after.data_offset} bytes "
                f"and the one the preload caches copy is {parsed_before.data_offset}; a "
                f"cached copy is a fixed slot and cannot grow. Nothing was written."
            )
        caches: Dict[str, bytearray] = {}
        for copy in cached.header:
            if copy.cache not in caches:
                if copy.cache not in files:
                    raise PlaybookError(
                        f"{copy.cache} carries a copy of {CONTAINER} and is not on this "
                        f"image; the two disagree and nothing was written."
                    )
                caches[copy.cache] = bytearray(
                    containers.read_file(image, files[copy.cache], limit=None))
            blob = caches[copy.cache]
            length = copy.length_in(parsed_after)
            end = copy.offset + length
            if end > len(blob):
                raise PlaybookError(
                    f"{copy.cache}'s copy of {CONTAINER}'s directory runs past the end of "
                    f"the cache; nothing was written."
                )
            blob[copy.offset:end] = after[:length]
            notes.append({**copy.as_dict(), "length": length,
                          "why": "the container's directory moved"})
        return {name: bytes(blob) for name, blob in caches.items()}, notes

    @staticmethod
    def _ranges(report: Mapping[str, Any]) -> Tuple[DeclaredRange, ...]:
        out: List[DeclaredRange] = []
        for item in report.get("declared_ranges", ()):
            row = item if isinstance(item, Mapping) else item.as_dict()
            out.append(DeclaredRange(int(row["start"]), int(row["length"]),
                                     str(row.get("reason", ""))))
        return tuple(out)

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        resolved = self._resolve(Path(source), recipe, catalogue)
        writer = _iso_writer()
        replacements = {resolved["paths"][name]: payload
                        for name, payload in resolved["written"].items()}
        try:
            report = writer.plan_report(Path(source), replacements,
                                        allow_growth=bool(resolved["grows"]))
        except writer.IsoWriteError as exc:
            raise PlaybookError(str(exc)) from exc
        ranges = self._ranges(writer.report_to_json(report))
        return Plan(
            lane_id=self.lane_id,
            target_keys=tuple(resolved["target_keys"]),
            declared_ranges=ranges,
            document={
                "schema": RECEIPT_SCHEMA,
                "edits": resolved["edits"],
                "members": resolved["members"],
                "preload_copies": resolved["cache_copies"],
                "files": sorted(resolved["written"]),
                "grows_the_image": bool(resolved["grows"]),
                "declared_bytes": sum(item.length for item in ranges),
                "runtime_note": self.NOT_BOOTED,
            },
        )

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        import os

        source, destination = Path(source), Path(destination)
        if source.resolve() == destination.resolve():
            raise PlaybookError(
                "the destination is the source; this lane writes a new image and leaves "
                "yours untouched, so give it another name."
            )
        if os.path.lexists(destination):
            raise PlaybookError(
                f"{destination} already exists and this lane never writes over an image; "
                f"choose a name that is not there yet."
            )
        resolved = self._resolve(source, recipe, catalogue)
        writer = _iso_writer()
        replacements = {resolved["paths"][name]: payload
                        for name, payload in resolved["written"].items()}
        try:
            report = writer.replace_files(source, destination, replacements,
                                          allow_growth=bool(resolved["grows"]))
        except writer.IsoWriteError as exc:
            raise PlaybookError(str(exc)) from exc
        json_report = writer.report_to_json(report)
        document = {
            "schema": RECEIPT_SCHEMA,
            "source": str(source),
            "destination": str(destination),
            "edits": resolved["edits"],
            "members": resolved["members"],
            "preload_copies": resolved["cache_copies"],
            "files": [
                {"name": name, "path": resolved["paths"][name], "bytes": len(payload),
                 "sha256": hashlib.sha256(payload).hexdigest(),
                 "kind": "preload-cache" if name != CONTAINER else "container"}
                for name, payload in sorted(resolved["written"].items())
            ],
            "grew_the_image": bool(json_report.get("growth")),
            "iso_write_report": json_report,
            "runtime_note": self.NOT_BOOTED,
        }
        return Receipt(
            schema=RECEIPT_SCHEMA,
            lane_id=self.lane_id,
            source=str(source),
            destination=str(destination),
            declared_ranges=self._ranges(json_report),
            document=document,
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        try:
            report = verify_build(Path(source), Path(destination), dict(receipt.document))
        except Refusal as exc:
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        return Verdict(
            True,
            f"playbook verifier: PASS · {report['edits_checked']} value(s) read back from "
            f"the destination · {report['members_checked']} playbook(s) re-parsed with "
            f"{report['checksum_sites']} checksum slot(s) all correct · "
            f"{report['untouched_members']} untouched member(s) byte-identical · "
            f"{report['preload_copies']} preload-cache copy/copies still equal what they "
            f"copy · {report['undeclared_changed_bytes']} undeclared changed bytes. "
            f"{PlaybooksLane.NOT_BOOTED}",
            report,
        )

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "madden09-ps2-playbooks-synthetic.iso"
        path.write_bytes(build_synthetic_playbook_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        """A formation name and a set name, on the synthetic disc's own rows."""

        formation = settle = None
        for target in catalogue.targets:
            if not target.key.startswith(ROW_PREFIX):
                continue
            _path, _member, table, _record = parse_row_key(target.key)
            if table == "FORM" and formation is None:
                formation = target
            elif table == "SETL" and settle is None:
                settle = target
            if formation is not None and settle is not None:
                break
        if formation is None or settle is None:
            raise Refusal(
                "the synthetic playbook carries no FORM and SETL rows to edit; rebuild the "
                "fixture from synthetic_playbook()."
            )
        return (
            Edit(formation.key, {"name": CONFORMANCE_FORMATION_NAME},
                 note="conformance: rename a formation"),
            Edit(settle.key, {"name": CONFORMANCE_SET_NAME},
                 note="conformance: rename a set"),
        )


# --------------------------------------------------------------------------
# The independent verifier
# --------------------------------------------------------------------------


def _iso_writer() -> Any:
    """The repository's bounded ISO writer, imported at call time."""

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


def _allowed_spans(edits: Sequence[Mapping[str, Any]], member: int) -> List[Tuple[int, int]]:
    """The byte runs inside one member an edit is entitled to have changed."""

    spans: List[Tuple[int, int]] = []
    for edit in edits:
        if int(edit["member"]) != member:
            continue
        for span in edit.get("field_spans", ()):
            spans.append((int(span["start"]), int(span["length"])))
    return spans


def verify_build(source: Path, destination: Path,
                 receipt_document: Mapping[str, Any]) -> Dict[str, Any]:
    """Re-derive, from the two images alone, that the build did what it claimed.

    **This function imports none of the writer.**  It uses the repository's
    independent ISO verifier for the image-level claim, this module's *reader*
    for the container and the database, and :func:`ea_tdb.verify_crcs` -- which
    recomputes every checksum from the destination's own bytes -- for the
    checksums.  What the receipt says is an input to be checked, never evidence.

    Six things are proved:

    1. outside the declared byte ranges the destination is the source, and no
       untouched file's extent moved (``ps2_iso9660_verify``);
    2. every edited value **reads back** from the destination's own container,
       member, table, record and field;
    3. inside each edited database, every byte that differs from the source lies
       either in a declared field span or in a checksum slot;
    4. all four kinds of checksum in each edited database agree with the bytes
       that are there;
    5. every member the recipe did not name is byte-identical, still packed;
    6. every copy a preload cache carries of this container -- its directory and
       any member -- equals what the destination now holds, re-read from the
       destination image rather than from the receipt.

    Raises :class:`Refusal` naming the first violation; returns counts on pass.
    """

    verifier = _iso_verifier()
    iso_report = receipt_document.get("iso_write_report")
    if not isinstance(iso_report, Mapping):
        raise PlaybookError(
            "this receipt carries no ISO write report, so there is nothing to verify "
            "against; rebuild with this lane's build()."
        )
    try:
        iso_verdict = verifier.verify_replacement(source, destination, dict(iso_report))
    except verifier.IsoVerifyError as exc:
        raise PlaybookError(f"the destination image is not the source plus the declared "
                            f"edits: {exc}") from exc
    if iso_verdict.get("result") != "PASS":
        raise PlaybookError(f"the image-level verifier did not pass: {iso_verdict}")

    edits = [dict(item) for item in receipt_document.get("edits", ())]
    if not edits:
        raise PlaybookError("this receipt names no edit, so there is nothing to read back.")

    source_image = containers.open_disc(Path(source))
    destination_image = containers.open_disc(Path(destination))
    before = containers.load_container(source_image, CONTAINER)
    after_files = {entry.name: entry for entry in containers.data_files(destination_image)}
    if CONTAINER not in after_files:
        raise PlaybookError(f"{CONTAINER} is not on the destination image.")
    after_blob = containers.read_file(destination_image, after_files[CONTAINER])
    after = ea_terf.parse_terf(after_blob, allow_size_mismatch=True)
    violations = after.layout_violations()
    if violations:
        raise PlaybookError(
            f"the rebuilt {CONTAINER} breaks the container's layout rules ({violations[0]})."
        )
    if after.member_count != before.member_count:
        raise PlaybookError(
            f"{CONTAINER} went from {before.member_count} member(s) to {after.member_count}."
        )

    touched = sorted({int(edit["member"]) for edit in edits})
    checked = 0
    crc_sites = 0
    for member in touched:
        was = before.member(member, max_output=before.members[member].decompressed_size)
        now = after.member(member, max_output=after.members[member].decompressed_size)
        if len(was) != len(now):
            raise PlaybookError(
                f"member {member} is {len(was):,} bytes in the source and {len(now):,} in "
                f"the destination; a record edit cannot change a length."
            )
        database = ea_tdb.parse_tdb(now)
        stale = ea_tdb.verify_crcs(now)
        if stale:
            raise PlaybookError(
                f"member {member} has a checksum that does not match its own bytes: "
                f"{stale[0]}"
            )
        sites = ea_tdb.crc_sites(now)
        crc_sites += len(sites)
        allowed = _allowed_spans(edits, member)
        allowed.extend((site.offset, 4) for site in sites)
        for offset in range(len(was)):
            if was[offset] == now[offset]:
                continue
            if not any(start <= offset < start + length for start, length in allowed):
                raise PlaybookError(
                    f"byte {offset} of member {member} changed and no declared field or "
                    f"checksum slot covers it; the write reached outside what it declared."
                )
        for edit in edits:
            if int(edit["member"]) != member:
                continue
            table = str(edit["table"])
            index = int(edit["record"])
            for field_name, expected in dict(edit["after"]).items():
                found = database.value(table, index, field_name)
                if found != expected:
                    raise PlaybookError(
                        f"{table} record {index} field {field_name} of member {member} "
                        f"reads {found!r} in the destination and the receipt says it should "
                        f"read {expected!r}."
                    )
                checked += 1

    untouched = 0
    for index in range(before.member_count):
        if index in touched:
            continue
        if before.stored(index) != after.stored(index):
            raise PlaybookError(
                f"{CONTAINER} member {index} changed and no edit named it."
            )
        untouched += 1

    copies = _verify_preload(destination_image, after_files, after_blob)
    return {
        "schema": RECEIPT_SCHEMA,
        "source": str(source),
        "destination": str(destination),
        "verdict": "PASS",
        "edits_checked": checked,
        "members_checked": len(touched),
        "untouched_members": untouched,
        "checksum_sites": crc_sites,
        "preload_copies": copies,
        "undeclared_changed_bytes": 0,
        "iso_bytes_compared": int(iso_verdict.get("unchanged_bytes_compared", 0)),
        "iso": {key: iso_verdict[key] for key in sorted(iso_verdict)
                if isinstance(iso_verdict.get(key), (int, str, bool))},
    }


def _verify_preload(image: Any, files: Mapping[str, Any], blob: bytes) -> int:
    """Every cached copy of this container still equals the container.

    Derived from the destination image alone -- the caches are re-parsed there
    and compared against the container as it now stands -- so a receipt that
    forgot a copy fails here rather than being believed.
    """

    preload = containers.preload_copies(image)
    row = preload.get(CONTAINER.upper()) or preload.get(CONTAINER)
    if row is None or row.empty:
        return 0
    parsed = ea_terf.parse_terf(blob, allow_size_mismatch=True)
    cache_bytes: Dict[str, bytes] = {}
    checked = 0
    for copy in list(row.header) + [item for items in row.members.values() for item in items]:
        if copy.cache not in cache_bytes:
            if copy.cache not in files:
                raise PlaybookError(
                    f"{copy.cache} carries a copy of {CONTAINER} and is not on the new image."
                )
            cache_bytes[copy.cache] = containers.read_file(
                image, files[copy.cache], limit=None)
        data = cache_bytes[copy.cache]
        length = copy.length_in(parsed)
        wanted = blob[:length] if copy.is_header else parsed.stored(int(copy.member))
        if data[copy.offset:copy.offset + length] != wanted:
            where = "directory" if copy.is_header else f"member {copy.member}"
            raise PlaybookError(
                f"{copy.cache}'s copy of {CONTAINER}'s {where} at byte 0x{copy.offset:x} is "
                f"not what the container now holds. The game preloads from that copy, so "
                f"the edit would be read against a stale directory."
            )
        checked += 1
    return checked


# --------------------------------------------------------------------------
# The synthetic disc
# --------------------------------------------------------------------------

#: What the conformance edit renames a formation and a set to.  Both are
#: invented and both are shorter than the fields they go in.
CONFORMANCE_FORMATION_NAME = "Synth Wide"
CONFORMANCE_SET_NAME = "Synth Set Two"

#: How many playbooks the synthetic container carries, and how many rows each
#: of the edited tables holds.  Small enough that CI packs them in well under a
#: second, large enough that the lane's own grouping is exercised.
SYNTHETIC_BOOKS = 3
SYNTHETIC_FORMATIONS = 4
SYNTHETIC_SETS = 6
SYNTHETIC_PLAYS = 12


def synthetic_playbook(seed: int = 0) -> bytes:
    """A nineteen-table playbook built from the format's own rules.

    Nothing here comes from a game: the names are invented, the numbers are a
    counting ramp, and the four checksums are written from the result's own
    bytes so the fixture is a database that passes :func:`ea_tdb.verify_crcs`.
    The table set is the real nineteen -- ``SGF\\x00`` included, spelled with
    the NUL byte the disc actually stores -- so a reader that cannot decode
    that name fails here rather than only on a disc CI does not have.

    The names repeat on purpose.  A playbook is re-packed under a budget equal
    to the bytes it already occupies, so a fixture whose every string is
    distinct would leave the encoder no headroom and CI would only ever see one
    of the two packing paths.
    """

    def name(prefix: str, index: int) -> str:
        # Deliberately few distinct strings: see the docstring.
        return f"{prefix} {index % 2}"

    tables: List[Tuple[Any, ...]] = [
        ("FORM",
         (("FORM", ea_tdb.FIELD_UINT, 7),
          ("FTYP", ea_tdb.FIELD_UINT, 4),
          ("name", ea_tdb.FIELD_STRING, 18 * 8)),
         tuple({"FORM": index + 1, "FTYP": 1 if index % 2 else 11,
                "name": name("Formation", index)}
               for index in range(SYNTHETIC_FORMATIONS))),
        ("PBFM",
         (("FAU1", ea_tdb.FIELD_UINT, 9), ("FAU2", ea_tdb.FIELD_UINT, 9),
          ("FAU3", ea_tdb.FIELD_UINT, 9), ("FAU4", ea_tdb.FIELD_UINT, 9),
          ("PBFM", ea_tdb.FIELD_UINT, 11), ("FTYP", ea_tdb.FIELD_UINT, 4),
          ("ord_", ea_tdb.FIELD_UINT, 4), ("grid", ea_tdb.FIELD_UINT, 1),
          ("name", ea_tdb.FIELD_STRING, 18 * 8)),
         tuple({"PBFM": index + 1, "FTYP": 1, "ord_": index, "grid": 0,
                "FAU1": index, "FAU2": index, "FAU3": index, "FAU4": index,
                "name": name("Formation", index)}
               for index in range(SYNTHETIC_FORMATIONS))),
        ("PBST",
         (("SETL", ea_tdb.FIELD_UINT, 9), ("PBFM", ea_tdb.FIELD_UINT, 11),
          ("PBST", ea_tdb.FIELD_UINT, 13), ("ord_", ea_tdb.FIELD_UINT, 6),
          ("name", ea_tdb.FIELD_STRING, 19 * 8)),
         tuple({"SETL": index + 1, "PBFM": 1 + index % SYNTHETIC_FORMATIONS,
                "PBST": index + 1, "ord_": index, "name": name("Set", index)}
               for index in range(SYNTHETIC_SETS))),
        ("SETL",
         (("SETL", ea_tdb.FIELD_UINT, 9), ("FORM", ea_tdb.FIELD_UINT, 7),
          ("MOTN", ea_tdb.FIELD_UINT, 1), ("SETT", ea_tdb.FIELD_UINT, 3),
          ("SITT", ea_tdb.FIELD_UINT, 2), ("SLF_", ea_tdb.FIELD_UINT, 1),
          ("name", ea_tdb.FIELD_STRING, 23 * 8), ("poso", ea_tdb.FIELD_UINT, 2)),
         tuple({"SETL": index + 1, "FORM": 1 + index % SYNTHETIC_FORMATIONS,
                "MOTN": 0, "SETT": 0, "SITT": 0, "SLF_": 0, "poso": 0,
                "name": name("Set", index)}
               for index in range(SYNTHETIC_SETS))),
        ("SGF\\x00",
         (("SETL", ea_tdb.FIELD_UINT, 9), ("SGF_", ea_tdb.FIELD_UINT, 12),
          ("name", ea_tdb.FIELD_STRING, 4 * 8), ("dflt", ea_tdb.FIELD_UINT, 1)),
         tuple({"SETL": 1 + index % SYNTHETIC_SETS, "SGF_": index + 1,
                "dflt": 0, "name": "G%d" % (index % 2)}
               for index in range(SYNTHETIC_SETS))),
        ("PBPL",
         (("PBPL", ea_tdb.FIELD_UINT, 15), ("PLYL", ea_tdb.FIELD_UINT, 13),
          ("PBST", ea_tdb.FIELD_UINT, 13), ("ord_", ea_tdb.FIELD_UINT, 6),
          ("name", ea_tdb.FIELD_STRING, 21 * 8), ("Flag", ea_tdb.FIELD_UINT, 5)),
         tuple({"PBPL": index + 1, "PLYL": index + 1,
                "PBST": 1 + index % SYNTHETIC_SETS, "ord_": index % 60,
                "Flag": 0, "name": name("Play", index)}
               for index in range(SYNTHETIC_PLAYS))),
        ("PLYL",
         (("SETL", ea_tdb.FIELD_UINT, 9), ("PLYL", ea_tdb.FIELD_UINT, 13),
          ("SITT", ea_tdb.FIELD_UINT, 2), ("PLYT", ea_tdb.FIELD_UINT, 6),
          ("PLF_", ea_tdb.FIELD_UINT, 14), ("name", ea_tdb.FIELD_STRING, 31 * 8),
          ("risk", ea_tdb.FIELD_UINT, 5), ("motn", ea_tdb.FIELD_UINT, 1),
          ("phlp", ea_tdb.FIELD_UINT, 3), ("vpos", ea_tdb.FIELD_UINT, 4)),
         tuple({"SETL": 1 + index % SYNTHETIC_SETS, "PLYL": index + 1,
                "SITT": 0, "PLYT": 0, "PLF_": 0, "risk": index % 32,
                "motn": index % 2, "phlp": 0, "vpos": 0,
                "name": name("Play", index)}
               for index in range(SYNTHETIC_PLAYS))),
        ("SPKF",
         (("SETL", ea_tdb.FIELD_UINT, 9), ("SPF_", ea_tdb.FIELD_UINT, 10),
          ("name", ea_tdb.FIELD_STRING, 16 * 8)),
         tuple({"SETL": index + 1, "SPF_": index + 1, "name": name("Kick", index)}
               for index in range(2))),
        ("PBAU",
         (("PBPL", ea_tdb.FIELD_UINT, 15), ("FTYP", ea_tdb.FIELD_UINT, 4),
          ("PBAU", ea_tdb.FIELD_UINT, 3)),
         tuple({"PBPL": index + 1, "FTYP": 1, "PBAU": index % 8}
               for index in range(4))),
        # The ten tables this page does not edit, present so the fixture is a
        # nineteen-table playbook rather than a convenient subset.
        ("ARTL", (("ARTL", ea_tdb.FIELD_UINT, 12), ("acnt", ea_tdb.FIELD_UINT, 4)),
         tuple({"ARTL": index + 1, "acnt": index % 12} for index in range(6))),
        ("PBAI", (("PBPL", ea_tdb.FIELD_UINT, 15), ("AIGR", ea_tdb.FIELD_UINT, 6),
                  ("prct", ea_tdb.FIELD_UINT, 7)),
         tuple({"PBPL": index + 1, "AIGR": index % 8, "prct": index}
               for index in range(SYNTHETIC_PLAYS))),
        ("PLCM", (("PLYL", ea_tdb.FIELD_UINT, 13), ("per1", ea_tdb.FIELD_UINT, 7)), ()),
        ("PLPD", (("PLYL", ea_tdb.FIELD_UINT, 13), ("per1", ea_tdb.FIELD_UINT, 7)), ()),
        ("PLRD", (("PLYL", ea_tdb.FIELD_UINT, 13), ("hole", ea_tdb.FIELD_UINT, 4)), ()),
        ("PLYS", (("PSAL", ea_tdb.FIELD_UINT, 11), ("ARTL", ea_tdb.FIELD_UINT, 12),
                  ("PLYL", ea_tdb.FIELD_UINT, 13), ("poso", ea_tdb.FIELD_UINT, 4)),
         tuple({"PSAL": index + 1, "ARTL": 1 + index % 6, "PLYL": 1 + index % SYNTHETIC_PLAYS,
                "poso": index % 11} for index in range(22))),
        ("PSAL", (("val1", ea_tdb.FIELD_UINT, 8), ("val2", ea_tdb.FIELD_UINT, 8),
                  ("val3", ea_tdb.FIELD_UINT, 8), ("PSAL", ea_tdb.FIELD_UINT, 11),
                  ("code", ea_tdb.FIELD_UINT, 8), ("step", ea_tdb.FIELD_UINT, 4)),
         tuple({"val1": index, "val2": index, "val3": index, "PSAL": 1 + index % 22,
                "code": index % 32, "step": index % 8} for index in range(22))),
        ("SETG", (("SETG", ea_tdb.FIELD_UINT, 13), ("SETP", ea_tdb.FIELD_UINT, 12),
                  ("SGF_", ea_tdb.FIELD_UINT, 12), ("x___", ea_tdb.FIELD_FLOAT, 32),
                  ("y___", ea_tdb.FIELD_FLOAT, 32)),
         tuple({"SETG": index + 1, "SETP": index + 1, "SGF_": 1 + index % SYNTHETIC_SETS,
                "x___": float(index), "y___": float(-index)} for index in range(11))),
        ("SETP", (("SETL", ea_tdb.FIELD_UINT, 9), ("SETP", ea_tdb.FIELD_UINT, 12),
                  ("poso", ea_tdb.FIELD_UINT, 4)),
         tuple({"SETL": 1 + index % SYNTHETIC_SETS, "SETP": index + 1, "poso": index % 11}
               for index in range(11))),
        ("SPKG", (("SPF_", ea_tdb.FIELD_UINT, 10), ("poso", ea_tdb.FIELD_UINT, 4),
                  ("DPos", ea_tdb.FIELD_UINT, 3), ("EPos", ea_tdb.FIELD_UINT, 5)),
         tuple({"SPF_": 1 + index % 2, "poso": index % 11, "DPos": 0, "EPos": index % 32}
               for index in range(4))),
    ]
    if seed:
        # One book differs from the next only in a number, so the three members
        # are distinct without any of them being a special case.
        tables = [(name_, fields, tuple({**row, **({"ord_": (row.get("ord_", 0) + seed) % 60}
                                                  if "ord_" in row else {})}
                                        for row in rows))
                  for name_, fields, rows in tables]
    return ea_tdb.recompute_crcs(ea_tdb.build_tdb(tuple(tables)))


def build_synthetic_playbook_disc(*, cached_books: Sequence[int] = ()) -> bytes:
    """A tiny ``SLUS-21770``-shaped image carrying a synthetic ``GAMEDATA.DAT``.

    The container is a ``COMP`` TERF whose playbook members are packed with
    :func:`ea_terf.lzh1_compress` -- the shape the retail disc ships for all 104
    of its databases [M] -- followed by one stored member that stands for the UI
    screens at the end of the real container.  Two preload caches are built
    beside it in the shape the disc has: ``FE.QKL`` carrying **two copies of the
    container's directory** and ``GAME.QKL`` carrying **a copy of that last
    member** [M].  So CI proves both halves of the coherence rule -- the
    directory copies a growing member moves, and the member-level refusal a
    cached member earns -- with no game data anywhere.

    *cached_books* names playbook members ``GAME.QKL`` should carry a copy of
    as well.  The retail disc caches none [M]; a test that wants the
    member-level refusal asks for one here rather than inventing a cache shape
    the disc does not have.
    """

    books = [synthetic_playbook(seed) for seed in range(SYNTHETIC_BOOKS)]
    trailing = containers.synthetic_text_member(containers.SYNTHETIC_TEXT_LINES)
    members = books + [trailing]
    codecs = [ea_terf.CODEC_LZH1] * len(books) + [ea_terf.CODEC_STORED]
    gamedata = ea_terf.build_terf(members, chunk="COMP", codecs=codecs)
    parsed = ea_terf.parse_terf(gamedata)
    directory = gamedata[:parsed.data_offset]
    game_cache = containers.build_synthetic_preload_cache(
        [(CONTAINER, containers.PRELOAD_KIND_MEMBER, len(books),
          parsed.stored(len(books)))]
        + [(CONTAINER, containers.PRELOAD_KIND_MEMBER, int(index),
            parsed.stored(int(index))) for index in cached_books])
    fe_cache = containers.build_synthetic_preload_cache([
        (CONTAINER, containers.PRELOAD_KIND_HEADER, None, directory),
        (CONTAINER, containers.PRELOAD_KIND_HEADER, None, directory),
    ])
    boot = (b"BOOT2 = cdrom0:\\%s;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"
            % containers.BOOT_FILE.encode("ascii"))
    return containers.iso_lib.build_synthetic_iso(
        files=[
            (b"SYSTEM.CNF;1", boot),
            (containers.BOOT_FILE.encode("ascii") + b";1", b"\x7fELF" + bytes(4092)),
        ],
        sub_name=b"DATA",
        sub_files=[
            (CONTAINER.encode("ascii") + b";1", gamedata),
            (containers.PRELOAD_CACHES[0].encode("ascii") + b";1", game_cache),
            (containers.PRELOAD_CACHES[1].encode("ascii") + b";1", fe_cache),
        ],
    )


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.madden09_ps2.playbooks_lane --source DISC.iso``.

    With ``--recipe`` and ``--destination`` it also does the write: it plans,
    builds a NEW image, and runs the independent verifier over the result.  The
    source is opened read-only either way.
    """

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.playbooks_lane",
        description="List and rename the playbooks on a Madden NFL 09 (PS2) disc.",
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
    lane = PlaybooksLane()
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
        print("PLAYBOOKS books=%d tables=%d records=%d fields=%d checksums=%d wrong=%d "
              "editable_rows=%d"
              % (document["books"], document["tables"], document["records"],
                 document["fields"], document["checksum_sites"],
                 document["checksum_sites_wrong"], document["editable_rows_listed"]))
        if not arguments.recipe:
            if arguments.destination:
                parser.error("--destination needs --recipe: there is nothing to write without one")
            return 0
        recipe = json.loads(Path(arguments.recipe).read_text(encoding="utf-8"))
        source = Path(arguments.source) if arguments.source else Path(catalogue.source)
        if arguments.dry_run or not arguments.destination:
            plan = lane.plan(source, recipe, catalogue)
            for item in plan.declared_ranges:
                print("would write %d byte(s) at %d (%s)"
                      % (item.length, item.start, item.reason))
            print("PLAYBOOKS_PLAN targets=%d bytes=%d"
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
        print("PLAYBOOKS_WRITE %s" % ("PASS" if verdict.passed else "FAIL"))
        return 0 if verdict.passed else 1
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = [
    "CAPABILITY_ID",
    "CONFORMANCE_FORMATION_NAME",
    "CONFORMANCE_SET_NAME",
    "CONTAINER",
    "CONTAINER_PATH",
    "EDITABLE_FIELDS",
    "EDITABLE_TABLES",
    "FORMATION_TYPES",
    "KEEP_NUMBER",
    "LANE_ID",
    "MAX_BOOK_TARGETS",
    "MAX_ROW_TARGETS",
    "PLAYBOOK_MARKERS",
    "PLAYBOOK_TABLES",
    "RECEIPT_SCHEMA",
    "RECIPE_SCHEMA",
    "ROW_PREFIX",
    "SCHEMA",
    "SYNTHETIC_BOOKS",
    "PlaybookError",
    "PlaybooksLane",
    "book_key",
    "build_synthetic_playbook_disc",
    "fields_for",
    "is_playbook",
    "number_bound",
    "parse_row_key",
    "row_key",
    "row_values",
    "synthetic_playbook",
    "table_key",
    "text_budget",
    "verify_build",
]


if __name__ == "__main__":
    raise SystemExit(_main())
