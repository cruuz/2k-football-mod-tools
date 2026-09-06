"""Editing one record of one EA ``TDB`` table inside a ``TERF`` container member.

Three lanes on two discs are the same lane with a different field map:
Madden 09's team-and-roster databases, NCAA 09's 432 per-team roster databases,
and NCAA 09's league identity tables.  What differs between them is **which
fields an editor offers**, and that is exactly the half that never ports: the
two discs share 37 ``PLAY`` field names out of 110 and 86, and NCAA's ratings
are five bits where Madden's are seven [M].  What does not differ is everything
else -- walking the containers, listing a database's schema, turning a row into
editor controls, resolving a recipe against the user's own image, keeping the
preload caches in step, and re-deriving the result from the destination's own
bytes with none of the writer imported.

So the base is that everything else, and a game hands it:

* ``discs`` -- its own ``containers`` module (:class:`.._lanes.Discs`);
* the lane's identity and three schema strings;
* ``tdb_containers`` / ``writable_containers`` / ``bare_databases``;
* ``editable_tables`` and ``editable_fields`` -- the field map.

Why a record edit is a bounded write
------------------------------------

A TDB field owns a fixed run of bits inside a fixed-stride record, so writing
one **cannot change a length**: the database comes back the same size.  What
can change is the member's *stored* size, when the member is compressed and the
new payload packs differently -- so the base re-packs under the member's own
codec, refuses a container that would change length, and rewrites every preload
cache copy the edit disturbed
(:mod:`mod_editor.games._lanes.preload_coherence`).

The four checksums EA stores in a TDB header are recomputed on every write
(``ea_tdb.recompute_crcs``) and re-derived from the destination's own bytes by
the verifier (``ea_tdb.verify_crcs``).

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import (Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple)

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

from . import iso_tools, preload_coherence

#: What a number field is set to when the user means "leave this alone".  A
#: text box can be left blank and dropped, but a spinner always holds some
#: value, so the convention has to be named rather than inferred.
KEEP_NUMBER = -1

#: One editor control: ``(field name, label, help, maximum)``.  ``maximum`` of
#: ``None`` means the field's own bit width is the bound -- which is the honest
#: answer whenever the scale a value is drawn on has not been established.
FieldSpec = Tuple[str, str, str, Optional[int]]


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


def editor_fields(table: ea_tdb.TdbTable, specs: Sequence[FieldSpec]) -> Tuple[Field, ...]:
    """The editor controls one row of *table* offers, in *specs* order.

    Built once per table **schema** and shared by every row of it: a disc with
    24,717 player rows, each carrying its own copies of two dozen field
    descriptions, is half a million objects for no information.

    A field the table does not declare is skipped, so a database with a
    different schema simply offers less rather than refusing.
    """

    out: List[Field] = []
    for name, label, help_text, maximum in specs:
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


def row_values(database: ea_tdb.TdbDatabase, table: ea_tdb.TdbTable, index: int,
               shape: Sequence[Field]) -> Dict[str, Any]:
    """What the row holds today, for the fields this lane offers."""

    record = database.record_bytes(table, index)
    return {item.key: database.decode(table.field(item.key), record) for item in shape}


class TdbRecordLane:
    """A lane whose targets are records of EA ``TDB`` tables on a PS2 disc.

    A subclass sets the class attributes below and, when it writes, supplies
    ``synthetic_source`` and ``conformance_edits``.  Everything else is here.
    """

    # -- what a subclass must set -------------------------------------

    #: The game's own ``containers`` module.
    discs: Any = None

    lane_id: str = ""
    capability_id: str = ""
    surface: str = ""
    page: str = ""
    title: str = ""
    classification: str = "read-only-mapped"
    schema: str = ""
    recipe_schema: str = ""
    receipt_schema: str = ""
    validators: Tuple[str, ...] = ()

    #: Containers whose members are EA TDB databases.  Named rather than
    #: discovered so a 600 MB speech container is never opened looking for one.
    tdb_containers: Tuple[str, ...] = ()
    #: The subset this lane writes.  Empty means the lane is read-only.
    writable_containers: Tuple[str, ...] = ()
    #: ``/DATA`` files that are a bare database with no container around them.
    bare_databases: Tuple[str, ...] = ()

    #: The tables whose rows become editable, in the order a page shows them.
    editable_tables: Tuple[str, ...] = ()
    #: ``{table name: (FieldSpec, …)}`` -- the field map, the half that never
    #: ports between two games on the same stack.
    editable_fields: Mapping[str, Sequence[FieldSpec]] = {}

    #: How many database and row targets are listed.  A document's totals stay
    #: complete however many rows the table shows.
    max_targets: int = 2000
    max_row_targets: int = 20000

    #: How a row target's key is spelled.
    row_prefix: str = "row:"

    #: A record edit never changes a length, so the destination is the source's
    #: exact size.
    fixed_allocation: bool = True

    #: Whether a preload cache's copy of an edited member may come back
    #: shorter.  A record edit keeps the *decompressed* payload's length and
    #: can still change the *stored* one, because the bytes it packs changed;
    #: measured on NCAA 09's ``LEAGUE.DAT`` member 0, a name edit moves the
    #: RLE1 encoding by -13 to +1 bytes [M].  A shorter copy is read through
    #: the directory copy this lane rewrites beside it, so the bytes past it
    #: are never read; a longer one is refused either way.
    cached_member_may_shrink: bool = True

    @property
    def read_only(self) -> bool:
        return not self.writable_containers

    # -- refusal ------------------------------------------------------

    @property
    def error(self) -> type:
        """The refusal this lane raises: the game's own, so it reads as its."""

        return self.discs.DiscError

    def refuse(self, sentence: str) -> Refusal:
        return self.error(sentence)

    # -- keys ---------------------------------------------------------

    def row_key(self, iso_path: str, member: Optional[int], table: str, record: int) -> str:
        """``row:<iso path>#<member>:<table>:<record>``; ``#-`` for a bare database."""

        return (f"{self.row_prefix}{iso_path}#"
                f"{'-' if member is None else member}:{table}:{record}")

    def parse_row_key(self, key: str) -> Tuple[str, Optional[int], str, int]:
        """One row key back into its four parts, or one sentence saying why not."""

        if not key.startswith(self.row_prefix):
            raise self.refuse(
                f"{key!r} is not an editable row; a row's key is spelled "
                f"{self.row_prefix}<container>#<member>:<table>:<record>, and the "
                f"database and table targets beside them are read-only."
            )
        rest = key[len(self.row_prefix):]
        try:
            head, table, record = rest.rsplit(":", 2)
            path, member = head.rsplit("#", 1)
            return path, (None if member == "-" else int(member)), table, int(record)
        except ValueError as exc:
            raise self.refuse(
                f"{key!r} is not a row key this lane writes; it should read "
                f"{self.row_prefix}<container>#<member>:<table>:<record>."
            ) from exc

    # -- hooks a subclass may override --------------------------------

    def row_label(self, table: str, member: Optional[int], index: int,
                  values: Mapping[str, Any]) -> str:
        """What a row is called in a list.  The default is its position."""

        where = "bare" if member is None else f"member {member}"
        return f"{where} · {table.lower()} {index}"

    def row_detail(self, table: str, values: Mapping[str, Any]) -> str:
        """The second line under a row's label.  The default is nothing."""

        return ""

    def member_is_editable(self, container_name: str, member: Optional[int],
                           database: ea_tdb.TdbDatabase) -> bool:
        """Whether this member's rows are offered.  The default is all of them."""

        return True

    def read_only_reason(self, container_name: str,
                         cached: Optional[Mapping[str, Sequence[str]]] = None) -> str:
        """Why a container outside :attr:`writable_containers` offers no edit."""

        writable = ", ".join(self.writable_containers) or "nothing on this disc"
        return (f"{container_name} is outside what this page edits: it writes "
                f"{writable}.")

    def row_budget(self, container_name: str) -> str:
        """The sentence a row target carries about what its edit costs."""

        return ("Every value is written where it already sits; nothing moves and the "
                "image keeps its exact size.")

    # -- catalogue ----------------------------------------------------

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        discs = self.discs
        image = discs.open_disc(Path(source))
        files = {entry.name.upper(): entry for entry in discs.data_files(image)}
        cached = discs.preload_names(image)
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        row_targets: List[Target] = []
        totals = {"databases": 0, "tables": 0, "records": 0, "fields": 0}
        skipped: Dict[str, str] = {}
        shapes: Dict[Tuple[Any, ...], Tuple[Field, ...]] = {}

        for name in self.tdb_containers:
            entry = files.get(name.upper())
            if entry is None:
                skipped[name] = "not on this image"
                continue
            if progress is not None:
                progress(f"{name}…")
            container = discs.load_container(image, name)
            if container is None:
                skipped[name] = "could not be opened as a TERF container"
                continue
            iso_path = f"{discs.DATA_DIRECTORY}/{entry.name}"
            for index in range(container.member_count):
                try:
                    payload = discs.member_uncached(container, index)
                except Refusal:
                    continue
                if not payload[:2] == ea_tdb.TDB_MAGIC and not payload[4:6] == ea_tdb.TDB_MAGIC:
                    continue
                row = self._database_row(iso_path, index, payload)
                self._accumulate(totals, row)
                rows.append(row)
                if len(targets) < self.max_targets:
                    targets.extend(self._targets_for(row, name, cached))
                if (name in self.writable_containers
                        and len(row_targets) < self.max_row_targets):
                    row_targets.extend(self._rows_of(
                        iso_path, name, index, payload, shapes,
                        self.max_row_targets - len(row_targets)))

        for name in self.bare_databases:
            entry = files.get(name.upper())
            if entry is None:
                skipped[name] = "not on this image"
                continue
            if progress is not None:
                progress(f"{name}…")
            try:
                payload = discs.read_file(image, entry, limit=None)
            except Refusal as exc:
                skipped[name] = str(exc)
                continue
            row = self._database_row(entry.path, None, payload)
            self._accumulate(totals, row)
            rows.append(row)
            if len(targets) < self.max_targets:
                targets.extend(self._targets_for(row, name, cached))
            if name in self.writable_containers and len(row_targets) < self.max_row_targets:
                row_targets.extend(self._rows_of(
                    entry.path, name, None, payload, shapes,
                    self.max_row_targets - len(row_targets)))

        document = {
            "schema": self.schema,
            "source": str(source),
            "containers": list(self.tdb_containers),
            "writable_containers": list(self.writable_containers),
            "bare_databases": list(self.bare_databases),
            "preload_cached": {name: list(caches) for name, caches in sorted(cached.items())},
            "databases": totals["databases"],
            "tables": totals["tables"],
            "records": totals["records"],
            "fields": totals["fields"],
            "rows_listed": len(rows),
            "targets_listed": len(targets),
            "editable_rows_listed": len(row_targets),
            "editable_rows_cap": self.max_row_targets,
            "editable_tables": list(self.editable_tables),
            "skipped": skipped,
            "rows": rows,
            "note": "Schema for every database this lane walks: table names, record "
                    "counts, strides and field names. Editable rows are listed as targets "
                    "with the values they hold; those values are read from your own image "
                    "and are not part of this document.",
        }
        return Catalogue(self.schema, self.lane_id, str(source),
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
        the rest, so the failure is recorded on the row and the walk continues.
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

    def _targets_for(self, row: Mapping[str, Any], container_name: str,
                     cached: Mapping[str, Sequence[str]]) -> List[Target]:
        """One target for the database, and one per table inside it.  Read-only."""

        key = self._database_key(row)
        note = row.get("note") or ""
        detail = [f"{row['bytes']:,} bytes"]
        if row.get("table_count") is not None:
            detail.append(f"{row['table_count']} tables")
            detail.append(f"v{row.get('version')}")
        if note:
            detail.append(note)
        budget = ("Its rows are listed below and can be edited."
                  if container_name in self.writable_containers
                  else "Read-only: " + self.read_only_reason(container_name, cached))

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

    def _rows_of(self, iso_path: str, container_name: str, member: Optional[int],
                 payload: bytes, shapes: Dict[Tuple[Any, ...], Tuple[Field, ...]],
                 remaining: int) -> List[Target]:
        """The editable rows of one database: one target per record."""

        try:
            database = ea_tdb.parse_tdb(payload)
        except ea_tdb.TdbError:
            return []
        if not self.member_is_editable(container_name, member, database):
            return []
        out: List[Target] = []
        for table_name in self.editable_tables:
            if table_name not in database.table_names:
                continue
            table = database.table(table_name)
            signature = (table_name, tuple(
                (item.name, item.type_id, item.bit_width) for item in table.fields))
            shape = shapes.get(signature)
            if shape is None:
                shape = editor_fields(table, self.editable_fields.get(table_name, ()))
                shapes[signature] = shape
            if not shape:
                continue
            for index in range(table.current_records):
                if len(out) >= remaining:
                    return out
                values = row_values(database, table, index, shape)
                out.append(Target(
                    key=self.row_key(iso_path, member, table_name, index),
                    label=self.row_label(table_name, member, index, values),
                    detail=self.row_detail(table_name, values),
                    budget=self.row_budget(container_name),
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

    # -- editing ------------------------------------------------------

    @staticmethod
    def _shape(target: Target) -> Dict[str, Field]:
        return {item.key: item for item in target.fields if not item.read_only}

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        """One sentence saying why an edit does not fit, or ``None``."""

        if not target.key.startswith(self.row_prefix):
            writable = ", ".join(self.writable_containers) or "nothing on this disc"
            return (f"{target.key} is a description of a database, not a row of one. "
                    f"Choose a row of {writable} to edit.")
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
                    return (f"{item.label} cannot be written as {ea_tdb.TEXT_ENCODING}, "
                            f"which is the only encoding this format carries; use "
                            f"characters that encoding has.")
                budget = int(item.maximum or 0)
                if len(encoded) > budget:
                    return (f"{item.label} is {len(encoded)} characters and the field "
                            f"holds {budget}; shorten it to {budget}.")
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
        return {"schema": self.recipe_schema, "edits": rows}

    # -- plan / build / verify ----------------------------------------

    def _recipe_edits(self, recipe: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        if str(recipe.get("schema")) != self.recipe_schema:
            raise self.refuse(
                f"this recipe says it is {recipe.get('schema')!r} and this lane writes "
                f"{self.recipe_schema}; hand it a recipe compose_recipe made."
            )
        rows = recipe.get("edits")
        if not isinstance(rows, list) or not rows:
            raise self.refuse(
                "this recipe changes nothing: its 'edits' list is empty, and a build "
                "with nothing to write would be a plain copy."
            )
        return [dict(row) for row in rows]

    def _resolve(self, source: Path, recipe: Mapping[str, Any]) -> Dict[str, Any]:
        """Work out every changed byte, from the user's own image, writing nothing.

        Returns the rebuilt file bytes per ISO path -- containers and any
        preload cache the edit disturbed -- the per-edit record of what
        changed, and enough detail for the verifier to re-derive the claim
        without this code.
        """

        discs = self.discs
        image = discs.open_disc(Path(source))
        entries = {entry.name.upper(): entry for entry in discs.data_files(image)}
        files = {f"{discs.DATA_DIRECTORY}/{entry.name}": entry
                 for entry in discs.data_files(image)}
        cached = discs.preload_names(image)
        wanted: Dict[str, Dict[Optional[int], Dict[str, Dict[str, Any]]]] = {}
        order: List[str] = []
        for row in self._recipe_edits(recipe):
            key = str(row.get("target", ""))
            iso_path, member, table, record = self.parse_row_key(key)
            name = iso_path.rsplit("/", 1)[-1]
            if name not in self.writable_containers:
                raise self.refuse(
                    f"{key} names {name}, and this lane writes only "
                    + (", ".join(self.writable_containers) or "nothing on this disc")
                    + ": " + self.read_only_reason(name, cached)
                )
            values = row.get("values")
            if not isinstance(values, Mapping) or not values:
                raise self.refuse(
                    f"{key} names no value to write; every edit must carry at least one."
                )
            slot = wanted.setdefault(iso_path, {}).setdefault(member, {})
            merged = slot.setdefault(f"{table}:{record}",
                                     {"table": table, "record": record, "values": {}})
            merged["values"].update(values)
            order.append(key)

        rebuilt: Dict[str, bytes] = {}
        edits_report: List[Dict[str, Any]] = []
        members_report: List[Dict[str, Any]] = []
        caches: Dict[str, bytearray] = {}
        cache_notes: List[Dict[str, Any]] = []
        preload = discs.preload_copies(image)
        for iso_path, members in sorted(wanted.items(), key=lambda item: item[0]):
            entry = files.get(iso_path)
            if entry is None:
                raise self.refuse(
                    f"this image holds no {iso_path}; it is not the disc this module "
                    f"reads, or the file has been removed."
                )
            if list(members) == [None]:
                rebuilt[iso_path] = self._rewrite_bare(
                    discs, image, entry, iso_path, members[None], edits_report,
                    members_report)
                continue
            writable = discs.open_for_rewrite(image, entry)
            original = writable.data
            container = writable.parsed
            working = original
            touched: List[int] = []
            for member, rows in sorted(members.items(),
                                       key=lambda item: -1 if item[0] is None else item[0]):
                if member is None:
                    raise self.refuse(
                        f"{iso_path} is a container and an edit named it without a member; "
                        f"a row key inside a container reads "
                        f"{self.row_prefix}<container>#<member>:<table>:<record>."
                    )
                writable.require_member_inside(member)
                payload = discs.member_uncached(container, member)
                new_payload = self._rewrite_records(
                    iso_path, member, payload, rows, edits_report)
                codec = container.members[member].codec
                priced = ea_terf.plan_member_rewrite(
                    working, member, new_payload, codecs=(codec,),
                    allow_short_tail=writable.recorded_short)
                # ``fits_slot`` is the stronger claim -- nothing after this
                # member moves at all -- and it is not the bound a
                # fixed-allocation writer has.  A member that packs SMALLER
                # than its slot shifts the members after it up and the
                # container gets shorter, which the ISO writer handles inside
                # the extent the file already owns; a member that packs bigger
                # than the whole container's spare alignment is the one case
                # that really would have to grow the file.
                if priced.grows_container:
                    raise self.refuse(
                        f"the rewritten member {member} of {iso_path} packs to "
                        f"{len(priced.packed):,} byte(s) under {priced.codec_name}, which "
                        f"would grow the container from {priced.previous_length:,} to "
                        f"{priced.new_length:,} bytes -- past the space the disc gives it. "
                        f"Make the replacement text shorter, or write fewer rows in one "
                        f"recipe."
                    )
                working = ea_terf.rewrite_member(
                    working, member, new_payload, codec=codec,
                    allow_short_tail=writable.recorded_short)
                if len(working) > len(original):
                    raise self.refuse(
                        f"rewriting member {member} grew {iso_path} from "
                        f"{len(original):,} to {len(working):,} bytes; this lane writes "
                        f"only inside the space a file already owns."
                    )
                touched.append(member)
                members_report.append({
                    "iso_path": iso_path,
                    "member": member,
                    "bytes": len(new_payload),
                    "codec": codec,
                    "source_sha256": hashlib.sha256(payload).hexdigest(),
                    "destination_sha256": hashlib.sha256(new_payload).hexdigest(),
                })
            preload_coherence.patch_caches(
                discs, image, entries, preload, caches, cache_notes,
                entry.name, original, working, touched,
                allow_shorter=self.cached_member_may_shrink)
            rebuilt[iso_path] = working
        for name, blob in caches.items():
            cache_entry = entries.get(name.upper())
            if cache_entry is None:
                raise self.refuse(
                    f"{name} carries a copy of a container this edit rewrote and is not "
                    f"on this image; the two disagree and nothing was written."
                )
            rebuilt[cache_entry.path] = bytes(blob)
        return {
            "rebuilt": rebuilt,
            "edits": edits_report,
            "members": members_report,
            "cache_copies": cache_notes,
            "caches": sorted(caches),
            "target_keys": tuple(order),
        }

    def _rewrite_bare(self, discs: Any, image: Any, entry: Any, iso_path: str,
                      rows: Mapping[str, Dict[str, Any]],
                      edits_report: List[Dict[str, Any]],
                      members_report: List[Dict[str, Any]]) -> bytes:
        """A ``/DATA`` file that *is* a database, with no container around it."""

        payload = discs.read_file(image, entry, limit=None)
        new_payload = self._rewrite_records(iso_path, None, payload, rows, edits_report)
        if len(new_payload) != len(payload):
            raise self.refuse(
                f"editing {iso_path} changed its length from {len(payload):,} to "
                f"{len(new_payload):,}; a record edit cannot do that and the result is "
                f"refused."
            )
        members_report.append({
            "iso_path": iso_path,
            "member": None,
            "bytes": len(new_payload),
            "codec": None,
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "destination_sha256": hashlib.sha256(new_payload).hexdigest(),
        })
        return new_payload

    def _rewrite_records(self, iso_path: str, member: Optional[int], payload: bytes,
                         rows: Mapping[str, Dict[str, Any]],
                         edits_report: List[Dict[str, Any]]) -> bytes:
        """Every record edit for one database, and the spans they are entitled to."""

        database = ea_tdb.parse_tdb(payload)
        new_payload = payload
        for entry_key in sorted(rows):
            change = rows[entry_key]
            table = database.table(str(change["table"]))
            index = int(change["record"])
            before = {name: database.value(table, index, name) for name in change["values"]}
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
                              "bit_offset": field.bit_offset, "bit_width": field.bit_width,
                              "type": field.type_name})
            edits_report.append({
                "target": self.row_key(iso_path, member, table.name, index),
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
            raise self.refuse(
                f"editing {'member %d of ' % member if member is not None else ''}"
                f"{iso_path} changed its length from {len(payload):,} to "
                f"{len(new_payload):,}; a record edit cannot do that and the result is "
                f"refused."
            )
        stale = ea_tdb.verify_crcs(new_payload)
        if stale:
            raise self.refuse(
                f"{'member %d of ' % member if member is not None else ''}{iso_path} came "
                f"out with a checksum that does not match its own bytes: {stale[0]}"
            )
        return new_payload

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        writer = iso_tools.iso_writer()
        resolved = self._resolve(Path(source), recipe)
        try:
            report = writer.plan_report(Path(source), resolved["rebuilt"])
        except writer.IsoWriteError as exc:
            raise self.refuse(str(exc)) from exc
        return Plan(
            lane_id=self.lane_id,
            target_keys=tuple(resolved["target_keys"]),
            declared_ranges=iso_tools.declared_ranges(report),
            document={
                "schema": self.receipt_schema,
                "edits": resolved["edits"],
                "members": resolved["members"],
                "cache_copies": resolved["cache_copies"],
                "files": sorted(resolved["rebuilt"]),
                "bytes_declared": int(report.get("bytes_declared", 0)),
            },
        )

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        if source.resolve() == destination.resolve():
            raise self.refuse(
                "the destination is the source; this lane writes a new image and leaves "
                "yours untouched, so give it another name."
            )
        if destination.exists():
            raise self.refuse(
                f"{destination} already exists and this lane never writes over an image; "
                f"choose a name that is not there yet."
            )
        writer = iso_tools.iso_writer()
        resolved = self._resolve(source, recipe)
        try:
            report = writer.replace_files(source, destination, resolved["rebuilt"])
        except writer.IsoWriteError as exc:
            raise self.refuse(str(exc)) from exc
        document = {
            "schema": self.receipt_schema,
            "edits": resolved["edits"],
            "members": resolved["members"],
            "cache_copies": resolved["cache_copies"],
            "caches": resolved["caches"],
            "recipe": dict(recipe),
            "iso_write_report": writer.report_to_json(report),
        }
        return Receipt(
            schema=self.receipt_schema,
            lane_id=self.lane_id,
            source=str(source),
            destination=str(destination),
            declared_ranges=iso_tools.declared_ranges(report),
            document=document,
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        try:
            report = self.verify_build(Path(source), Path(destination),
                                       dict(receipt.document))
        except Refusal as exc:
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        return Verdict(
            True,
            f"{self.lane_id} verifier: PASS · {report['edits_checked']} value(s) read back "
            f"from the destination · {report['members_checked']} database(s) re-parsed with "
            f"{report['checksum_sites']} checksum slot(s) all correct · "
            f"{report['preload_copies']} preload-cache copy/copies still equal what they "
            f"copy · {report['undeclared_changed_bytes']} undeclared changed bytes.",
            report,
        )

    # -- the independent verifier -------------------------------------

    def verify_build(self, source: Path, destination: Path,
                     receipt_document: Mapping[str, Any]) -> Dict[str, Any]:
        """Re-derive, from the two images alone, that the build did what it claimed.

        **This imports none of the writer.**  It uses the repository's
        independent ISO verifier for the container-level claim, this game's
        *reader* for the databases, ``ea_tdb.verify_crcs`` -- which recomputes
        every checksum from the destination's own bytes -- for the checksums,
        and :func:`preload_coherence.check_caches` for the caches.  What the
        receipt says is an input to be checked, never evidence.

        Five things are proved:

        1. outside the declared byte ranges the destination is the source, the
           two images are the same size, and no untouched file's extent moved;
        2. every edited value **reads back** from the destination's own
           container, member, table, record and field;
        3. inside each edited database, every byte that differs from the source
           lies either in one of the declared field spans or in a checksum
           slot -- so a write that scribbled somewhere else is caught even
           though it is inside a declared ISO range;
        4. all four kinds of checksum in each edited database agree with the
           bytes that are there;
        5. every preload-cache copy of every rewritten container still equals
           what it copies, re-read off the **destination**.
        """

        discs = self.discs
        verifier = iso_tools.iso_verifier()
        iso_report = receipt_document.get("iso_write_report")
        if not isinstance(iso_report, Mapping):
            raise self.refuse(
                "this receipt carries no ISO write report, so there is nothing to verify "
                "against; rebuild with this lane's build()."
            )
        try:
            iso_verdict = verifier.verify_replacement(source, destination, dict(iso_report))
        except verifier.IsoVerifyError as exc:
            raise self.refuse(f"the destination image is not the source plus the declared "
                              f"edits: {exc}") from exc

        edits = [dict(item) for item in receipt_document.get("edits", ())]
        if not edits:
            raise self.refuse("this receipt names no edit, so there is nothing to read back.")

        source_image = discs.open_disc(Path(source))
        destination_image = discs.open_disc(Path(destination))
        destination_files = {entry.name.upper(): entry
                             for entry in discs.data_files(destination_image)}
        paths = sorted({str(edit["iso_path"]) for edit in edits})
        checked = 0
        members_checked = 0
        crc_sites = 0
        copies_checked = 0
        for iso_path in paths:
            name = iso_path.rsplit("/", 1)[-1]
            members = sorted({-1 if edit["member"] is None else int(edit["member"])
                              for edit in edits if str(edit["iso_path"]) == iso_path})
            if members == [-1]:
                entry = destination_files.get(name.upper())
                source_entry = {e.name.upper(): e
                                for e in discs.data_files(source_image)}.get(name.upper())
                if entry is None or source_entry is None:
                    raise self.refuse(f"{iso_path} is not on both images.")
                before = discs.read_file(source_image, source_entry, limit=None)
                after = discs.read_file(destination_image, entry, limit=None)
                database, sites = self._check_database(before, after, edits, iso_path, None)
                crc_sites += sites
                members_checked += 1
                checked += self._read_back(database, edits, iso_path, None)
                continue
            source_container = discs.load_container(source_image, name)
            destination_container = discs.load_container(destination_image, name)
            for member in members:
                try:
                    before = discs.member_uncached(source_container, member)
                    after = discs.member_uncached(destination_container, member)
                except ea_terf.TerfError as exc:
                    raise self.refuse(
                        f"member {member} of {iso_path} could not be read back out of the "
                        f"destination: {exc}"
                    ) from exc
                database, sites = self._check_database(before, after, edits, iso_path, member)
                crc_sites += sites
                members_checked += 1
                checked += self._read_back(database, edits, iso_path, member)
            blob = discs.read_file(destination_image, destination_files[name.upper()],
                                   limit=None)
            sentence, copies = preload_coherence.check_caches(
                discs, destination_image, destination_files, blob, name)
            if sentence is not None:
                raise self.refuse(sentence)
            copies_checked += copies
        return {
            "schema": self.receipt_schema,
            "source": str(source),
            "destination": str(destination),
            "verdict": "PASS",
            "edits_checked": checked,
            "members_checked": members_checked,
            "checksum_sites": crc_sites,
            "preload_copies": copies_checked,
            "undeclared_changed_bytes": 0,
            "iso_bytes_compared": int(iso_verdict.get("unchanged_bytes_compared", 0)),
            "iso": {key: iso_verdict[key] for key in sorted(iso_verdict)
                    if isinstance(iso_verdict.get(key), (int, str, bool))},
        }

    def _check_database(self, before: bytes, after: bytes,
                        edits: Sequence[Mapping[str, Any]], iso_path: str,
                        member: Optional[int]) -> Tuple[ea_tdb.TdbDatabase, int]:
        where = (f"member {member} of {iso_path}" if member is not None else iso_path)
        if len(before) != len(after):
            raise self.refuse(
                f"{where} is {len(before):,} bytes in the source and {len(after):,} in "
                f"the destination; a record edit cannot change a length."
            )
        database = ea_tdb.parse_tdb(after)
        stale = ea_tdb.verify_crcs(after)
        if stale:
            raise self.refuse(
                f"{where} has a checksum that does not match its own bytes: {stale[0]}"
            )
        sites = ea_tdb.crc_sites(after)
        allowed: List[Tuple[int, int]] = [(site.offset, 4) for site in sites]
        for edit in edits:
            if str(edit["iso_path"]) != iso_path:
                continue
            edit_member = edit["member"]
            if (None if edit_member is None else int(edit_member)) != member:
                continue
            for span in edit.get("field_spans", ()):
                allowed.append((int(span["start"]), int(span["length"])))
        offset = iso_tools.first_undeclared(before, after, allowed)
        if offset >= 0:
            raise self.refuse(
                f"byte {offset} of {where} changed and no declared field or checksum slot "
                f"covers it; the write reached outside what it declared."
            )
        return database, len(sites)

    def _read_back(self, database: ea_tdb.TdbDatabase,
                   edits: Sequence[Mapping[str, Any]], iso_path: str,
                   member: Optional[int]) -> int:
        checked = 0
        for edit in edits:
            if str(edit["iso_path"]) != iso_path:
                continue
            edit_member = edit["member"]
            if (None if edit_member is None else int(edit_member)) != member:
                continue
            table = str(edit["table"])
            index = int(edit["record"])
            for field_name, expected in dict(edit["after"]).items():
                found = database.value(table, index, field_name)
                if found != expected:
                    where = (f"member {member} of {iso_path}" if member is not None
                             else iso_path)
                    raise self.refuse(
                        f"{table} record {index} field {field_name} of {where} reads "
                        f"{found!r} in the destination and the receipt says it should "
                        f"read {expected!r}."
                    )
                checked += 1
        return checked


__all__ = [
    "FieldSpec",
    "KEEP_NUMBER",
    "TdbRecordLane",
    "editor_fields",
    "number_bound",
    "row_values",
    "text_budget",
]
