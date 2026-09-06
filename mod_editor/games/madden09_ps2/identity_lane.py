"""The thirty-two NFL teams' identity: what they are called, and their colours.

A Madden 09 team's identity is not one row.  The same nickname, city,
abbreviation, short name, city id and pair of colours are written into the
``TEAM`` table of **three** databases on the retail disc, and a rename that
reaches one and not the others leaves the game reading whichever it opened
first.  So this lane's unit of work is a *team*, not a record: one target per
NFL team, and one recipe that carries every copy the disc itself agrees on.

What the disc carries, measured
-------------------------------

For each of the 32 NFL teams, on the owner's retail SLUS-21770 image [M]:

* ``/DATA/DB_TEAMS.DAT`` member *n* (``n`` = 0..31), table ``TEAM``, record 0
  -- one row per member, 65 fields, a 116-byte record.  **Written.**
* ``/DATA/STRMDATA.DB``, table ``TEAM``, the record whose ``TGID`` is that
  team's -- the same 65-field schema, 234 of 234 records.  Its rows are *not*
  in ``TGID`` order, so the record is resolved by reading the field, never by
  arithmetic.  All 32 teams' identity fields are byte-identical to the
  ``DB_TEAMS.DAT`` copy [M].  **Written**, when the two agree.
* ``/DATA/TEMPLATE.DAT`` member 1, table ``TEAM`` -- 33 rows, ``TGID`` 1..32
  plus the free-agent pool, and all 32 teams' identity fields byte-identical to
  the two above [M].  **Not written**: ``TEMPLATE.DAT`` is named in the
  ``/DATA/FE.QKL`` preload cache, which carries a copy of at least some of what
  it names, and this module does not rewrite a cache.  The catalogue says so.

``TEMPLATE.DAT`` members 2, 3 and 4 also hold ``TEAM`` tables, but their
``TGID`` values run 33..1011 -- the historical squads, not the 32 NFL teams
[M] -- so they carry no copy of a target's identity at all.  The other 203
``DB_TEAMS.DAT`` members are those same historical squads and the free-agent
pool, and are outside what this page is for.

Team names also appear as **prose** in the disc's ``TEXT`` string banks: 543
of the 14,748 members carry at least one of the 32 teams' four identity
strings, 464 of them a string five characters or longer, across six containers
[M].  This lane does **not** touch them -- a renamed team leaves the story
generator saying the old name -- and the Menus & UI page's text lane is where
a string is edited.  The count is measured here so the gap is a number rather
than a shrug.

What it edits
-------------

:data:`TEXT_FIELDS` -- the four names -- :data:`COLOUR_FIELDS` -- the two
colours, each composed from three one-byte channels -- and :data:`NUMBER_FIELDS`
-- the city id.  :data:`MEASURED_NOT_EDITED` lists the fields of the same
record that were read and are deliberately **not** offered: their meaning is a
hypothesis, and a hypothesis does not belong in an editor.

Why a record edit is a bounded write
------------------------------------

A TDB field owns a fixed run of bits inside a fixed-stride record, so writing
one cannot change a length: the database comes back the same size, the
container member it sits in comes back the same size, and the ISO extent it
came from is rewritten in place.  The four checksums EA stores in a TDB header
are recomputed on every write (``ea_tdb.recompute_crcs``) and re-derived from
the destination's own bytes by the verifier (``ea_tdb.verify_crcs``).  The
writer is the sibling roster lane's -- ``ea_tdb.write_records``,
``ea_terf.rewrite_member`` and ``tools/ps2_iso9660_writer`` -- imported, not
copied, so the two pages cannot drift apart.

**Nothing here has been seen in a running game.**  The evidence is offline: a
destination image, an independent verifier that re-reads it, and a conformance
harness that proves the whole path on a synthetic disc.  No emulator has booted
a rebuilt Madden 09 disc, and this module does not claim one has.

Run it without a window::

    python3 -m mod_editor.games.madden09_ps2.identity_lane --source DISC.iso

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
from .team_data import text_budget

CAPABILITY_ID = "madden09ps2.identity.team_records"
LANE_ID = "colors.team_identity"
SCHEMA = "madden09_ps2_team_identity/v1"
RECIPE_SCHEMA = "madden09_ps2_team_identity_edit/v1"
RECEIPT_SCHEMA = "madden09_ps2_team_identity_write/v1"

#: The table every copy of a team's identity lives in.
TEAM_TABLE = "TEAM"

#: The container whose members hold one team each, and the one this lane
#: anchors a target on.
TEAM_CONTAINER = containers.TEAM_DATABASE_CONTAINER

#: The bare database beside it that carries the second copy [M].
STREAM_DATABASE = containers.STREAM_DATABASE_FILE

#: The field a ``TEAM`` row is matched across databases by.  Ten bits, so 1,024
#: teams is the format's ceiling and 234 the disc's [M].
TEAM_ID_FIELD = "TGID"

#: How many members of :data:`TEAM_CONTAINER` are the NFL teams.  Members 0..31
#: carry ``TGID`` 1..32 and the 21-table roster shape; members 32..234 are 202
#: historical squads and the free-agent pool [M], which this page does not
#: offer because renaming a 1985 squad is not what "Text & Team Identity" is.
NFL_TEAM_MEMBERS = 32

#: What a number field is set to when the user means "leave this alone", the
#: same convention the sibling roster page uses: a text box can be left blank
#: and dropped, but a spinner always holds some value.
KEEP_NUMBER = -1

#: The four name fields, as ``(field, label, help)``.  Which of them holds
#: which kind of name is the sibling roster lane's measurement, repeated here
#: rather than guessed: a nickname, a city, a short code and a familiar short
#: form [M].  No value from that reading is stored in this module.
TEXT_FIELDS: Tuple[Tuple[str, str, str], ...] = (
    ("TDNA", "Nickname", "The name the team is drawn under, e.g. its mascot."),
    ("TLNA", "City", "The city or region the team plays for."),
    ("TSNA", "Abbreviation", "The two-to-five letter short code."),
    ("TMNC", "Short name", "The familiar short form commentary uses."),
)

#: The two colours, as ``(key, label, (red, green, blue) fields, help)``.  Each
#: is three separate one-byte fields in the record, so the editor's single
#: colour control writes three spans, and a colour word's **alpha is ignored**:
#: the record has no alpha channel to put it in, and a lane that silently
#: dropped a quarter of what the user typed without saying so would be lying.
COLOUR_FIELDS: Tuple[Tuple[str, str, Tuple[str, str, str], str], ...] = (
    ("primary", "Primary colour", ("TBCR", "TBCG", "TBCB"),
     "The team's first colour."),
    ("secondary", "Secondary colour", ("TB2R", "TB2G", "TB2B"),
     "The team's second colour."),
)

#: The numeric fields, as ``(field, label, help, maximum)``; ``maximum`` of
#: ``None`` means the field's own bit width is the bound.
NUMBER_FIELDS: Tuple[Tuple[str, str, str, Optional[int]], ...] = (
    ("CYID", "City id", "Which city record the team points at. It is an index, "
                        "not a name: the city names themselves are in "
                        "TEMPLATE.DAT, which this lane does not write.", None),
)

#: Fields of the same record that were read on the retail disc and are
#: deliberately **not** offered, with what is and is not known about each [M].
#: ``TCDO``, ``TCRP``, ``TGPT`` and ``TCTX`` track ``TGID`` almost exactly
#: across the 32 teams, which is consistent with colour or logo indices and
#: consistent with several other things; the owner's research records them as a
#: hypothesis and a hypothesis does not belong in an editor.  The rest are
#: structural keys: changing them re-points a row rather than renaming it.
MEASURED_NOT_EDITED: Mapping[str, str] = {
    "TCDO": "hypothesis: a colour or logo index; tracks TGID on 32 of 32 teams",
    "TCRP": "hypothesis: a colour or logo index; tracks TGID-1 on 31 of 32 teams",
    "TGPT": "hypothesis: a colour or logo index; tracks TGID on 32 of 32 teams",
    "TCTX": "hypothesis: a colour or logo index; tracks TGID on 32 of 32 teams",
    "TGID": "the key every other copy of this row is matched by; changing it "
            "would re-point the row, not rename the team",
    "CGID": "conference id; a structural key, not an identity string",
    "DGID": "division id; a structural key, not an identity string",
    "LGID": "league id; a structural key, not an identity string",
    "TORD": "the order the team is listed in; not part of its identity",
    "DISN": "unestablished; read but not decoded",
}

#: How a target's key is spelled: ``team:<iso path>#<member>:<record>``.
TEAM_PREFIX = "team:"

#: How the two colour halves are spelled to and from a user.
COLOUR_DIGITS = 6
COLOUR_WITH_ALPHA_DIGITS = 8


class IdentityError(Refusal):
    """This lane could not do what was asked; the sentence says why."""


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------


def team_key(iso_path: str, member: int, record: int) -> str:
    """The target key for one team: a container member and a record in it."""

    return f"{TEAM_PREFIX}{iso_path}#{member}:{record}"


def parse_team_key(key: str) -> Tuple[str, int, int]:
    """``team:/DATA/DB_TEAMS.DAT#4:0`` back into its three parts."""

    if not key.startswith(TEAM_PREFIX):
        raise IdentityError(
            f"{key!r} is not a team this lane edits; a team's key is spelled "
            f"{TEAM_PREFIX}<container>#<member>:<record>."
        )
    rest = key[len(TEAM_PREFIX):]
    try:
        head, record = rest.rsplit(":", 1)
        path, member = head.rsplit("#", 1)
        return path, int(member), int(record)
    except ValueError as exc:
        raise IdentityError(
            f"{key!r} is not a team key this lane writes; it should read "
            f"{TEAM_PREFIX}<container>#<member>:<record>."
        ) from exc


# --------------------------------------------------------------------------
# Colours
# --------------------------------------------------------------------------


def format_colour(red: int, green: int, blue: int) -> str:
    """Three channel bytes as the hex line an editor shows and takes back."""

    return "#%02X%02X%02X" % (red & 0xFF, green & 0xFF, blue & 0xFF)


def parse_colour(text: str) -> Tuple[int, int, int]:
    """A hex line as three channel bytes.  **An alpha byte is discarded.**

    ``#RRGGBB``, ``RRGGBB``, ``#AARRGGBB`` and ``AARRGGBB`` are all taken,
    because a shell that offers a packed ARGB control will hand back eight
    digits and the record has nowhere to put the first two.  The refusal names
    the spelling rather than the character that failed.
    """

    raw = str(text).strip()
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) not in (COLOUR_DIGITS, COLOUR_WITH_ALPHA_DIGITS):
        raise IdentityError(
            f"{text!r} is not a colour this lane reads; write it as six hex "
            f"digits, #RRGGBB, or eight with an alpha this record has no room "
            f"for and drops, #AARRGGBB."
        )
    if len(raw) == COLOUR_WITH_ALPHA_DIGITS:
        raw = raw[2:]
    try:
        number = int(raw, 16)
    except ValueError as exc:
        raise IdentityError(
            f"{text!r} is not a colour this lane reads; every character after "
            f"the # must be a hex digit, as in #1B3A5F."
        ) from exc
    return (number >> 16) & 0xFF, (number >> 8) & 0xFF, number & 0xFF


# --------------------------------------------------------------------------
# Fields
# --------------------------------------------------------------------------


def number_bound(field: ea_tdb.TdbField, maximum: Optional[int]) -> int:
    """The largest value a numeric field takes: the smaller of scale and width."""

    width_bound = (1 << field.bit_width) - 1
    return width_bound if maximum is None else min(maximum, width_bound)


def fields_for(table: ea_tdb.TdbTable) -> Tuple[Field, ...]:
    """The editor controls one team offers, in list order.

    Built once per table schema and shared by every team of it: the shape is
    the same for all 32 and each carrying its own copies would be information
    nobody asked for.  A field the table does not declare is skipped, and a
    colour whose three channels are not all there is skipped whole rather than
    offered as a control that could only write part of itself.
    """

    out: List[Field] = []
    for name, label, help_text in TEXT_FIELDS:
        if name not in table:
            continue
        field = table.field(name)
        if field.type_id != ea_tdb.FIELD_STRING:
            continue
        budget = text_budget(field)
        out.append(Field(
            name, "text", label,
            f"{help_text} Up to {budget} characters -- the field is "
            f"{field.bit_width // 8} bytes and one is the terminator. "
            f"Leave it blank to keep what is there.",
            maximum=budget,
        ))
    for key, label, channels, help_text in COLOUR_FIELDS:
        if not all(name in table for name in channels):
            continue
        out.append(Field(
            key, "colour_argb", label,
            f"{help_text} Written as {', '.join(channels)}, three one-byte "
            f"channels. Give it as #RRGGBB; an alpha byte has nowhere to go in "
            f"this record and is dropped. Leave it blank to keep what is there.",
        ))
    for name, label, help_text, maximum in NUMBER_FIELDS:
        if name not in table:
            continue
        field = table.field(name)
        if field.type_id not in (ea_tdb.FIELD_UINT, ea_tdb.FIELD_SINT):
            continue
        out.append(Field(
            name, "int", label,
            f"{help_text} {KEEP_NUMBER} keeps the value that is there.",
            minimum=KEEP_NUMBER, maximum=number_bound(field, maximum),
        ))
    return tuple(out)


def team_values(database: ea_tdb.TdbDatabase, table: ea_tdb.TdbTable, index: int,
                shape: Sequence[Field]) -> Dict[str, Any]:
    """What one team's row holds today, in the shape the editor draws.

    The four names come back as text and the city id as a number, both as the
    record stores them; each colour comes back as one hex line composed from
    its three channel bytes, which is the only place the two representations
    meet.
    """

    record = database.record_bytes(table, index)
    channels = {key: names for key, _label, names, _help in COLOUR_FIELDS}
    out: Dict[str, Any] = {}
    for item in shape:
        if item.key in channels:
            red, green, blue = (database.decode(table.field(name), record)
                                for name in channels[item.key])
            out[item.key] = format_colour(int(red), int(green), int(blue))
        else:
            out[item.key] = database.decode(table.field(item.key), record)
    return out


def record_writes(values: Mapping[str, Any]) -> Dict[str, Any]:
    """The editor's values as the ``TEAM`` fields they are written into.

    A colour becomes its three channel bytes here and nowhere else, so the
    record of what a build changed names real fields of the real record and a
    verifier never has to know what a "primary colour" is.
    """

    channels = {key: names for key, _label, names, _help in COLOUR_FIELDS}
    out: Dict[str, Any] = {}
    for key, value in values.items():
        if key in channels:
            red, green, blue = parse_colour(str(value))
            names = channels[key]
            out[names[0]], out[names[1]], out[names[2]] = red, green, blue
        else:
            out[key] = value
    return out


# --------------------------------------------------------------------------
# The lane
# --------------------------------------------------------------------------


class IdentityLane:
    """The 32 NFL teams' names and colours, in every copy the disc agrees on."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "colors"
    page = "identity"
    title = "Team names and colours"
    classification = "offline-writer-proved"
    recipe_schema = RECIPE_SCHEMA
    validators = (
        "tools/validate_madden09_ps2_identity.sh",
        "tools/validate_madden09_ps2_identity.bat",
    )
    #: A record edit never changes a length, so the destination image is the
    #: source's exact size.
    fixed_allocation = True
    read_only = False

    # -- catalogue -----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        image = containers.open_disc(Path(source))
        files = {entry.name: entry for entry in containers.data_files(image)}
        cached = containers.preload_names(image)
        self._refuse_if_cached(TEAM_CONTAINER, cached)

        entry = files.get(TEAM_CONTAINER)
        if entry is None:
            raise IdentityError(
                f"this image holds no {containers.DATA_DIRECTORY}/{TEAM_CONTAINER}, so it "
                f"carries no team records; choose the {containers.SERIAL} image."
            )
        if progress is not None:
            progress(f"{TEAM_CONTAINER}…")
        container = containers.load_container(image, TEAM_CONTAINER)
        iso_path = f"{containers.DATA_DIRECTORY}/{TEAM_CONTAINER}"

        stream = self._stream_rows(image, files, cached, progress=progress)
        #: One shape per distinct table schema, shared by every team that has
        #: it.  All 235 members of a retail disc's container declare the same
        #: 65 fields [M], so this is one entry -- but a member that declares
        #: something else gets its own shape rather than the first member's,
        #: which is what stops a modified image from offering a control for a
        #: field that table has not got.
        shapes: Dict[Tuple[Any, ...], Tuple[Field, ...]] = {}
        targets: List[Target] = []
        rows: List[Dict[str, Any]] = []
        for member in range(min(len(container), NFL_TEAM_MEMBERS)):
            try:
                payload = containers.member_uncached(container, member)
                database = ea_tdb.parse_tdb(payload)
            except (ea_terf.TerfError, ea_tdb.TdbError) as exc:
                rows.append({"member": member, "note": str(exc)})
                continue
            if TEAM_TABLE not in database.table_names:
                rows.append({"member": member, "note": f"no {TEAM_TABLE} table"})
                continue
            table = database.table(TEAM_TABLE)
            signature = tuple((item.name, item.type_id, item.bit_width)
                              for item in table.fields)
            shape = shapes.get(signature)
            if shape is None:
                shape = shapes.setdefault(signature, fields_for(table))
            if not shape:
                rows.append({"member": member,
                             "note": f"{TEAM_TABLE} declares none of the identity fields"})
                continue
            for index in range(table.current_records):
                values = team_values(database, table, index, shape)
                team_id = self._team_id(database, table, index)
                copies = self._copies_for(team_id, stream, values, member, index)
                rows.append({
                    "member": member,
                    "record": index,
                    "team_id": team_id,
                    "fields": table.field_count,
                    "record_bytes": table.record_bytes,
                    "copies": [dict(item) for item in copies],
                })
                targets.append(Target(
                    key=team_key(iso_path, member, index),
                    label=self._label(values, member),
                    detail=self._detail(values, copies),
                    budget="Every value is written where it already sits: the names pad to "
                           "their own field's bytes, a colour is three of them, and the "
                           "image keeps its exact size.",
                    searchable=" ".join([TEAM_CONTAINER, str(member)]
                                        + [str(value) for value in values.values()]),
                    raw={
                        "iso_path": iso_path,
                        "member": member,
                        "record": index,
                        "team_id": team_id,
                        "values": values,
                        "copies": [dict(item) for item in copies],
                    },
                    fields=shape,
                ))

        written = sum(1 for row in rows for item in row.get("copies", ())
                      if item.get("written"))
        document = {
            "schema": SCHEMA,
            "source": str(source),
            "container": TEAM_CONTAINER,
            "stream_database": STREAM_DATABASE,
            "table": TEAM_TABLE,
            "members_read": min(len(container), NFL_TEAM_MEMBERS),
            "container_members": len(container),
            "teams_listed": len(targets),
            "copies_written_per_build": written,
            "stream_rows": stream.get("records", 0),
            "stream_present": bool(stream.get("present")),
            "stream_note": stream.get("note", ""),
            "preload_cached": {name: list(caches) for name, caches in sorted(cached.items())},
            "edited_fields": (
                [name for name, _label, _help in TEXT_FIELDS]
                + [name for _key, _label, names, _help in COLOUR_FIELDS for name in names]
                + [name for name, _label, _help, _max in NUMBER_FIELDS]
            ),
            "measured_not_edited": dict(MEASURED_NOT_EDITED),
            "rows": rows,
            "note": "One row per NFL team: which container member and record carry its "
                    "identity, which other databases carry a copy, and which of those "
                    "copies a build writes. The values themselves are read from your own "
                    "image into the targets and are not part of this document.",
        }
        return Catalogue(SCHEMA, self.lane_id, str(source), tuple(targets), document)

    @staticmethod
    def _refuse_if_cached(name: str, cached: Mapping[str, Sequence[str]]) -> None:
        """A container a preload cache names is not one this lane rewrites."""

        caches = cached.get(name.upper())
        if not caches:
            return
        raise IdentityError(
            f"{name} is named in " + " and ".join(caches) + " on this image, and a file a "
            f"preload cache carries a copy of is not one this lane rewrites; editing one "
            f"copy and not the other would leave the game reading whichever it reached "
            f"first, so it edits nothing here."
        )

    @staticmethod
    def _team_id(database: ea_tdb.TdbDatabase, table: ea_tdb.TdbTable,
                 index: int) -> Optional[int]:
        if TEAM_ID_FIELD not in table:
            return None
        return int(database.value(table, index, TEAM_ID_FIELD))

    def _stream_rows(self, image: Any, files: Mapping[str, Any],
                     cached: Mapping[str, Sequence[str]], *,
                     progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """The bare database's ``TEAM`` rows, keyed by team id, or why there are none.

        The rows are **not** in team-id order on the retail disc [M], so the
        index is built by reading the field off every record rather than by
        assuming a position.
        """

        entry = files.get(STREAM_DATABASE)
        if entry is None:
            return {"present": False, "note": f"{STREAM_DATABASE} is not on this image"}
        caches = cached.get(STREAM_DATABASE.upper())
        if caches:
            return {"present": False,
                    "note": f"{STREAM_DATABASE} is named in " + " and ".join(caches)
                            + ", so this lane does not write it"}
        if progress is not None:
            progress(f"{STREAM_DATABASE}…")
        try:
            payload = containers.read_file(image, entry, limit=None)
            database = ea_tdb.parse_tdb(payload)
        except (containers.DiscError, ea_tdb.TdbError) as exc:
            return {"present": False, "note": str(exc)}
        if TEAM_TABLE not in database.table_names:
            return {"present": False, "note": f"{STREAM_DATABASE} has no {TEAM_TABLE} table"}
        table = database.table(TEAM_TABLE)
        index: Dict[int, int] = {}
        for record in range(table.current_records):
            team_id = self._team_id(database, table, record)
            if team_id is not None and team_id not in index:
                index[team_id] = record
        return {"present": True, "records": table.current_records,
                "by_team_id": index, "database": database, "table": table,
                "note": ""}

    def _copies_for(self, team_id: Optional[int], stream: Mapping[str, Any],
                    values: Mapping[str, Any], member: int,
                    index: int) -> List[Dict[str, Any]]:
        """Every database on the disc that carries this team's identity.

        The anchor is always written.  A second copy is written **field by
        field**, and only where it agrees with the anchor today: a value that
        already says something else is not a copy of this team's, and writing
        it would be a guess dressed as consistency.  So a copy that differs in
        one name still takes a colour, and the row says which fields it will
        not take rather than reading as all or nothing.
        """

        out: List[Dict[str, Any]] = [{
            "file": TEAM_CONTAINER, "member": member, "record": index,
            "written": True, "fields_not_written": [],
            "reason": "the row this target names",
        }]
        if not stream.get("present") or team_id is None:
            if stream.get("note"):
                out.append({"file": STREAM_DATABASE, "member": None, "record": None,
                            "written": False, "fields_not_written": sorted(values),
                            "reason": stream.get("note", "")})
            return out
        record = stream.get("by_team_id", {}).get(team_id)
        if record is None:
            out.append({"file": STREAM_DATABASE, "member": None, "record": None,
                        "written": False, "fields_not_written": sorted(values),
                        "reason": f"no {TEAM_TABLE} row carries {TEAM_ID_FIELD} {team_id}"})
            return out
        other = team_values(stream["database"], stream["table"], record,
                            tuple(Field(key, "note", key) for key in values))
        differ = sorted(key for key in values if other.get(key) != values.get(key))
        if not differ:
            reason = "carries the same identity"
        elif len(differ) < len(values):
            reason = ("carries a different " + ", ".join(differ)
                      + "; those are left alone and the rest are written")
        else:
            reason = ("carries a different value in every field this page writes; a "
                      "build leaves it alone")
        out.append({
            "file": STREAM_DATABASE, "member": None, "record": record,
            "written": len(differ) < len(values), "fields_not_written": differ,
            "reason": reason,
        })
        return out

    @staticmethod
    def _label(values: Mapping[str, Any], member: int) -> str:
        name = " ".join(str(values.get(key, "")).strip()
                        for key in ("TLNA", "TDNA")).strip()
        return name or f"team in member {member}"

    @staticmethod
    def _detail(values: Mapping[str, Any], copies: Sequence[Mapping[str, Any]]) -> str:
        parts = [str(values[key]) for key in ("TSNA",) if key in values]
        parts.extend(str(values[key]) for key in ("primary", "secondary") if key in values)
        written = sum(1 for item in copies if item.get("written"))
        parts.append(f"{written} of {len(copies)} copies written")
        held = sorted({name for item in copies for name in item.get("fields_not_written", ())})
        if held:
            parts.append("another copy already differs in " + ", ".join(held)
                         + ", so those stay as they are")
        return " · ".join(parts)

    # -- editing -------------------------------------------------------

    @staticmethod
    def _shape(target: Target) -> Dict[str, Field]:
        return {item.key: item for item in target.fields if not item.read_only}

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        """One sentence saying why an edit does not fit, or ``None``."""

        if not target.key.startswith(TEAM_PREFIX):
            return (f"{target.key} is not a team this lane edits; choose one of the "
                    f"{NFL_TEAM_MEMBERS} teams in {TEAM_CONTAINER}.")
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
                problem = self._check_text(item, value)
                if problem:
                    return problem
                if value == "":
                    continue
            elif item.kind == "colour_argb":
                if not isinstance(value, str):
                    return f"{item.label} takes a hex colour and was handed {value!r}."
                if value.strip() == "":
                    continue
                try:
                    red, green, blue = parse_colour(value)
                except Refusal as exc:
                    return f"{item.label}: {exc}"
                value = format_colour(red, green, blue)
            else:
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
            return ("Nothing about this team would change. Type a new name or colour, or "
                    "leave the team alone.")
        return None

    @staticmethod
    def _check_text(item: Field, value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return f"{item.label} takes text and was handed {value!r}."
        if value == "":
            return None
        if "\x00" in value:
            return f"{item.label} may not contain a NUL character; remove it."
        try:
            encoded = value.encode(ea_tdb.TEXT_ENCODING, "strict")
        except UnicodeEncodeError:
            return (f"{item.label} cannot be written as {ea_tdb.TEXT_ENCODING}, which is "
                    f"the only encoding this format carries; use characters that encoding "
                    f"has.")
        budget = int(item.maximum or 0)
        if len(encoded) > budget:
            return (f"{item.label} is {len(encoded)} characters and the field holds "
                    f"{budget}; shorten it to {budget}.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows: List[Dict[str, Any]] = []
        for edit in edits:
            values = {key: value for key, value in edit.values.items()
                      if not (value == "" or value == KEEP_NUMBER
                              or (isinstance(value, str) and value.strip() == ""))}
            rows.append({"target": edit.target_key, "values": values})
        return {"schema": RECIPE_SCHEMA, "edits": rows}

    # -- plan / build / verify -----------------------------------------

    @staticmethod
    def _recipe_edits(recipe: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        if str(recipe.get("schema")) != RECIPE_SCHEMA:
            raise IdentityError(
                f"this recipe says it is {recipe.get('schema')!r} and this lane writes "
                f"{RECIPE_SCHEMA}; hand it a recipe compose_recipe made."
            )
        rows = recipe.get("edits")
        if not isinstance(rows, list) or not rows:
            raise IdentityError(
                "this recipe changes nothing: its 'edits' list is empty, and a build with "
                "nothing to write would be a plain copy."
            )
        return [dict(row) for row in rows]

    def _resolve(self, source: Path, recipe: Mapping[str, Any]) -> Dict[str, Any]:
        """Work out every changed byte, from the user's own image, writing nothing.

        Returns the rebuilt bytes per ISO path, the per-copy record of what
        changed, and enough detail for the verifier to re-derive the claim
        without this code.
        """

        image = containers.open_disc(Path(source))
        files = {entry.name: entry for entry in containers.data_files(image)}
        cached = containers.preload_names(image)
        self._refuse_if_cached(TEAM_CONTAINER, cached)

        wanted: Dict[int, Dict[int, Dict[str, Any]]] = {}
        order: List[str] = []
        for row in self._recipe_edits(recipe):
            key = str(row.get("target", ""))
            iso_path, member, record = parse_team_key(key)
            name = iso_path.rsplit("/", 1)[-1]
            if name != TEAM_CONTAINER:
                raise IdentityError(
                    f"{key} names {name}, and this lane anchors every team on "
                    f"{TEAM_CONTAINER}; choose a team from this page's catalogue."
                )
            if member >= NFL_TEAM_MEMBERS:
                raise IdentityError(
                    f"{key} names member {member}, and this page offers the "
                    f"{NFL_TEAM_MEMBERS} NFL teams in members 0..{NFL_TEAM_MEMBERS - 1}; "
                    f"the members past them are historical squads and the free-agent pool."
                )
            values = row.get("values")
            if not isinstance(values, Mapping) or not values:
                raise IdentityError(
                    f"{key} names no value to write; every edit must carry at least one."
                )
            slot = wanted.setdefault(member, {}).setdefault(
                record, {"record": record, "values": {}})
            slot["values"].update(values)
            order.append(key)

        entry = files.get(TEAM_CONTAINER)
        if entry is None:
            raise IdentityError(
                f"this image holds no {containers.DATA_DIRECTORY}/{TEAM_CONTAINER}; it is "
                f"not a Madden NFL 09 PlayStation 2 disc, or the container has been removed."
            )
        writable = containers.open_for_rewrite(image, entry)
        original = writable.data
        container = writable.parsed
        stream = self._stream_rows(image, files, cached)

        iso_path = f"{containers.DATA_DIRECTORY}/{TEAM_CONTAINER}"
        working = original
        edits_report: List[Dict[str, Any]] = []
        members_report: List[Dict[str, Any]] = []
        stream_writes: Dict[int, Dict[str, Any]] = {}
        stream_skipped: List[Dict[str, Any]] = []
        for member in sorted(wanted):
            writable.require_member_inside(member)
            payload = container.member(member)
            new_payload = payload
            for record in sorted(wanted[member]):
                values = dict(wanted[member][record]["values"])
                database = ea_tdb.parse_tdb(new_payload)
                table = database.table(TEAM_TABLE)
                if record >= table.current_records:
                    raise IdentityError(
                        f"member {member} of {TEAM_CONTAINER} holds {table.current_records} "
                        f"{TEAM_TABLE} record(s) and this edit names record {record}; "
                        f"rebuild the catalogue from this image."
                    )
                writes = record_writes(values)
                unknown = sorted(name for name in writes if name not in table)
                if unknown:
                    raise IdentityError(
                        f"{TEAM_TABLE} in member {member} declares no "
                        f"{', '.join(unknown)}; this database has a different schema from "
                        f"the one this page reads and it is left alone."
                    )
                before = {name: database.value(table, record, name) for name in writes}
                new_payload = ea_tdb.write_records(database, TEAM_TABLE, {record: writes})
                after = ea_tdb.parse_tdb(new_payload)
                edits_report.append(self._copy_report(
                    key=team_key(iso_path, member, record),
                    iso_path=iso_path, member=member, table=table,
                    record=record, writes=writes, before=before,
                    record_offset=after.record_offset(TEAM_TABLE, record),
                    after_values={name: after.value(TEAM_TABLE, record, name)
                                  for name in writes},
                ))
                team_id = self._team_id(after, after.table(TEAM_TABLE), record)
                self._stage_stream(stream, team_id, writes, before, stream_writes,
                                   stream_skipped)
            if len(new_payload) != len(payload):
                raise IdentityError(
                    f"editing member {member} of {TEAM_CONTAINER} changed its length from "
                    f"{len(payload):,} to {len(new_payload):,}; a record edit cannot do "
                    f"that and the result is refused."
                )
            stale = ea_tdb.verify_crcs(new_payload)
            if stale:
                raise IdentityError(
                    f"member {member} of {TEAM_CONTAINER} came out with a checksum that "
                    f"does not match its own bytes: {stale[0]}"
                )
            working = ea_terf.rewrite_member(
                working, member, new_payload,
                allow_short_tail=writable.recorded_short)
            if len(working) != len(original):
                raise IdentityError(
                    f"rewriting member {member} changed {iso_path} from {len(original):,} "
                    f"to {len(working):,} bytes; this lane writes only inside the space a "
                    f"file already owns."
                )
            members_report.append({
                "iso_path": iso_path, "member": member, "bytes": len(new_payload),
                "source_sha256": hashlib.sha256(payload).hexdigest(),
                "destination_sha256": hashlib.sha256(new_payload).hexdigest(),
            })

        rebuilt: Dict[str, bytes] = {iso_path: working}
        if stream_writes:
            rebuilt.update(self._rewrite_stream(image, files, stream_writes,
                                                edits_report, members_report))
        return {
            "rebuilt": rebuilt,
            "edits": edits_report,
            "members": members_report,
            "copies_not_written": stream_skipped,
            "target_keys": tuple(dict.fromkeys(order)),
        }

    @staticmethod
    def _copy_report(*, key: str, iso_path: str, member: Optional[int],
                     table: ea_tdb.TdbTable, record: int, writes: Mapping[str, Any],
                     before: Mapping[str, Any], record_offset: int,
                     after_values: Mapping[str, Any]) -> Dict[str, Any]:
        spans = []
        for name in sorted(writes):
            field = table.field(name)
            first = record_offset + field.bit_offset // 8
            last = record_offset + (field.bit_offset + field.bit_width + 7) // 8
            spans.append({"field": name, "start": first, "length": last - first,
                          "bit_offset": field.bit_offset, "bit_width": field.bit_width,
                          "type": field.type_name})
        return {
            "target": key, "iso_path": iso_path, "member": member,
            "table": table.name, "record": record, "record_offset": record_offset,
            "record_bytes": table.record_bytes,
            "before": dict(before), "after": dict(after_values), "field_spans": spans,
        }

    @staticmethod
    def _stage_stream(stream: Mapping[str, Any], team_id: Optional[int],
                      writes: Mapping[str, Any], before: Mapping[str, Any],
                      staged: Dict[int, Dict[str, Any]],
                      skipped: List[Dict[str, Any]]) -> None:
        """Queue the bare database's copy of this row, when it agrees today.

        Agreement is checked **field by field, on the values being written**:
        the second copy is written only where it says the same thing the anchor
        said before the edit, so a row that already differs is left alone and
        the receipt says which field made it differ.
        """

        if not stream.get("present"):
            if stream.get("note"):
                skipped.append({"file": STREAM_DATABASE, "team_id": team_id,
                                "reason": str(stream["note"])})
            return
        if team_id is None:
            skipped.append({"file": STREAM_DATABASE, "team_id": None,
                            "reason": f"this {TEAM_TABLE} row declares no {TEAM_ID_FIELD}, "
                                      f"so no second copy can be matched to it"})
            return
        record = stream.get("by_team_id", {}).get(team_id)
        if record is None:
            skipped.append({"file": STREAM_DATABASE, "team_id": team_id,
                            "reason": f"no {TEAM_TABLE} row carries {TEAM_ID_FIELD} "
                                      f"{team_id}"})
            return
        database, table = stream["database"], stream["table"]
        agree: Dict[str, Any] = {}
        differ: List[str] = []
        for name, value in writes.items():
            if name not in table:
                differ.append(name)
            elif database.value(table, record, name) == before.get(name):
                agree[name] = value
            else:
                differ.append(name)
        if differ:
            skipped.append({"file": STREAM_DATABASE, "team_id": team_id, "record": record,
                            "reason": "already carries a different "
                                      + ", ".join(sorted(differ))
                                      + "; it is not a copy of this row and is left alone"})
        if agree:
            staged.setdefault(record, {"record": record, "values": {}})["values"].update(agree)

    def _rewrite_stream(self, image: Any, files: Mapping[str, Any],
                        staged: Mapping[int, Dict[str, Any]],
                        edits_report: List[Dict[str, Any]],
                        members_report: List[Dict[str, Any]]) -> Dict[str, bytes]:
        """The bare database with the queued rows written, same size, checksums fresh."""

        entry = files[STREAM_DATABASE]
        original = containers.read_file(image, entry, limit=None)
        if len(original) != entry.recorded_length:
            raise IdentityError(
                f"{entry.path} is {entry.recorded_length:,} bytes in this image's own "
                f"directory and carries {len(original):,}; a rewrite would have to grow the "
                f"file, which this lane will not do."
            )
        working = original
        for record in sorted(staged):
            writes = dict(staged[record]["values"])
            database = ea_tdb.parse_tdb(working)
            table = database.table(TEAM_TABLE)
            before = {name: database.value(table, record, name) for name in writes}
            working = ea_tdb.write_records(database, TEAM_TABLE, {record: writes})
            after = ea_tdb.parse_tdb(working)
            edits_report.append(self._copy_report(
                key=f"{TEAM_PREFIX}{entry.path}:{record}", iso_path=entry.path,
                member=None, table=table, record=record, writes=writes, before=before,
                record_offset=after.record_offset(TEAM_TABLE, record),
                after_values={name: after.value(TEAM_TABLE, record, name) for name in writes},
            ))
        if len(working) != len(original):
            raise IdentityError(
                f"editing {entry.path} changed its length from {len(original):,} to "
                f"{len(working):,}; a record edit cannot do that and the result is refused."
            )
        stale = ea_tdb.verify_crcs(working)
        if stale:
            raise IdentityError(
                f"{entry.path} came out with a checksum that does not match its own bytes: "
                f"{stale[0]}"
            )
        members_report.append({
            "iso_path": entry.path, "member": None, "bytes": len(working),
            "source_sha256": hashlib.sha256(original).hexdigest(),
            "destination_sha256": hashlib.sha256(working).hexdigest(),
        })
        return {entry.path: working}

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
            raise IdentityError(str(exc)) from exc
        return Plan(
            lane_id=self.lane_id,
            target_keys=tuple(resolved["target_keys"]),
            declared_ranges=self._ranges(report),
            document={
                "schema": RECEIPT_SCHEMA,
                "edits": resolved["edits"],
                "members": resolved["members"],
                "copies_not_written": resolved["copies_not_written"],
                "files": sorted(resolved["rebuilt"]),
                "bytes_declared": int(report.get("bytes_declared", 0)),
            },
        )

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        if source.resolve() == destination.resolve():
            raise IdentityError(
                "the destination is the source; this lane writes a new image and leaves "
                "yours untouched, so give it another name."
            )
        if destination.exists():
            raise IdentityError(
                f"{destination} already exists and this lane never writes over an image; "
                f"choose a name that is not there yet."
            )
        writer = _iso_writer()
        resolved = self._resolve(source, recipe)
        try:
            report = writer.replace_files(source, destination, resolved["rebuilt"])
        except writer.IsoWriteError as exc:
            raise IdentityError(str(exc)) from exc
        document = {
            "schema": RECEIPT_SCHEMA,
            "edits": resolved["edits"],
            "members": resolved["members"],
            "copies_not_written": resolved["copies_not_written"],
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
            f"identity verifier: PASS · {report['values_checked']} value(s) read back from "
            f"the destination · {report['databases_checked']} database(s) re-parsed with "
            f"{report['checksum_sites']} checksum slot(s) all correct · "
            f"{report['undeclared_changed_bytes']} undeclared changed bytes.",
            report,
        )

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "madden09-ps2-identity-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc(
            tdb_members=[synthetic_team_database(team_id) for team_id in SYNTHETIC_TEAM_IDS],
            stream_database=synthetic_stream_database(),
        ))
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        """A name, a short name and a colour, on the synthetic disc's own teams."""

        teams = [target for target in catalogue.targets
                 if target.key.startswith(TEAM_PREFIX)]
        if not teams:
            raise Refusal(
                "the synthetic disc carries no team rows to edit; rebuild the fixture from "
                "synthetic_team_database()."
            )
        return (
            Edit(teams[0].key, {"TDNA": "Testers", "primary": "#123456"},
                 note="conformance"),
            Edit(teams[-1].key, {"TSNA": "TST"}, note="conformance"),
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


def _allowed_spans(edits: Sequence[Mapping[str, Any]], iso_path: str,
                   member: Optional[int]) -> List[Tuple[int, int]]:
    """The byte runs inside one database an edit is entitled to have changed."""

    spans: List[Tuple[int, int]] = []
    for edit in edits:
        if str(edit["iso_path"]) != iso_path or edit.get("member") != member:
            continue
        for span in edit.get("field_spans", ()):
            spans.append((int(span["start"]), int(span["length"])))
    return spans


def _check_database(before: bytes, after: bytes, edits: Sequence[Mapping[str, Any]],
                    iso_path: str, member: Optional[int], what: str) -> Tuple[int, int]:
    """One edited database, re-derived from the destination's own bytes.

    Returns ``(values checked, checksum slots checked)`` and raises on the
    first violation.  Nothing here calls the writer: the values are read back
    with the plain reader, the checksums are recomputed from the bytes that are
    there, and every differing byte has to fall inside a span the receipt
    declared or a checksum slot the format defines.
    """

    if len(before) != len(after):
        raise IdentityError(
            f"{what} is {len(before):,} bytes in the source and {len(after):,} in the "
            f"destination; a record edit cannot change a length."
        )
    database = ea_tdb.parse_tdb(after)
    stale = ea_tdb.verify_crcs(after)
    if stale:
        raise IdentityError(
            f"{what} has a checksum that does not match its own bytes: {stale[0]}"
        )
    sites = ea_tdb.crc_sites(after)
    allowed = _allowed_spans(edits, iso_path, member)
    allowed.extend((site.offset, 4) for site in sites)
    for offset in range(len(before)):
        if before[offset] == after[offset]:
            continue
        if not any(start <= offset < start + length for start, length in allowed):
            raise IdentityError(
                f"byte {offset} of {what} changed and no declared field or checksum slot "
                f"covers it; the write reached outside what it declared."
            )
    checked = 0
    for edit in edits:
        if str(edit["iso_path"]) != iso_path or edit.get("member") != member:
            continue
        table = str(edit["table"])
        record = int(edit["record"])
        for name, expected in dict(edit["after"]).items():
            found = database.value(table, record, name)
            if found != expected:
                raise IdentityError(
                    f"{table} record {record} field {name} of {what} reads {found!r} in the "
                    f"destination and the receipt says it should read {expected!r}."
                )
            checked += 1
    return checked, len(sites)


def verify_build(source: Path, destination: Path,
                 receipt_document: Mapping[str, Any]) -> Dict[str, Any]:
    """Re-derive, from the two images alone, that the build did what it claimed.

    **This function imports none of the writer.**  It uses the repository's
    independent ISO verifier for the container-level claim, this module's
    *reader* for the databases, and ``ea_tdb.verify_crcs`` -- which recomputes
    every checksum from the destination's own bytes -- for the checksums.  What
    the receipt says is an input to be checked, never evidence.

    Five things are proved:

    1. outside the declared byte ranges the destination is the source, the two
       images are the same size, and no untouched file's extent moved
       (``ps2_iso9660_verify.verify_replacement``);
    2. every edited value **reads back** from the destination's own container,
       member, table, record and field -- and from the bare database beside it,
       when a second copy was written;
    3. inside each edited database, every byte that differs from the source
       lies either in a declared field span or in a checksum slot, so a write
       that scribbled somewhere else is caught even though it is inside a
       declared ISO range;
    4. all four kinds of checksum in each edited database agree with the bytes
       that are there;
    5. every text field the receipt says was written is **NUL-padded to its own
       field's width** in the destination, which is the format's rule and not
       the encoder's opinion of it.

    Raises :class:`Refusal` naming the first violation; returns counts on pass.
    """

    verifier = _iso_verifier()
    iso_report = receipt_document.get("iso_write_report")
    if not isinstance(iso_report, Mapping):
        raise IdentityError(
            "this receipt carries no ISO write report, so there is nothing to verify "
            "against; rebuild with this lane's build()."
        )
    try:
        iso_verdict = verifier.verify_replacement(source, destination, dict(iso_report))
    except verifier.IsoVerifyError as exc:
        raise IdentityError(f"the destination image is not the source plus the declared "
                            f"edits: {exc}") from exc

    edits = [dict(item) for item in receipt_document.get("edits", ())]
    if not edits:
        raise IdentityError("this receipt names no edit, so there is nothing to read back.")

    source_image = containers.open_disc(Path(source))
    destination_image = containers.open_disc(Path(destination))
    source_files = {entry.name: entry for entry in containers.data_files(source_image)}
    destination_files = {entry.name: entry
                         for entry in containers.data_files(destination_image)}
    checked = 0
    databases = 0
    crc_sites = 0
    for iso_path in sorted({str(edit["iso_path"]) for edit in edits}):
        name = iso_path.rsplit("/", 1)[-1]
        members = sorted({edit.get("member") for edit in edits
                          if str(edit["iso_path"]) == iso_path},
                         key=lambda item: (item is not None, item))
        # Opened once per file, not once per member: a user who renames all 32
        # teams edits 32 members of one 2.5 MB container.
        source_container = destination_container = None
        if any(member is not None for member in members):
            source_container = containers.load_container(source_image, name)
            destination_container = containers.load_container(destination_image, name)
        for member in members:
            if member is None:
                if name not in source_files or name not in destination_files:
                    raise IdentityError(
                        f"{iso_path} is named by this receipt and is not on both images; "
                        f"the destination was not built from this source."
                    )
                before = containers.read_file(source_image, source_files[name], limit=None)
                after = containers.read_file(destination_image, destination_files[name],
                                             limit=None)
                what = iso_path
            else:
                try:
                    before = source_container.member(int(member))
                    after = destination_container.member(int(member))
                except ea_terf.TerfError as exc:
                    raise IdentityError(
                        f"member {member} of {iso_path} could not be read back out of the "
                        f"destination: {exc}"
                    ) from exc
                what = f"member {member} of {iso_path}"
            values, sites = _check_database(before, after, edits, iso_path, member, what)
            _check_padding(after, edits, iso_path, member, what)
            checked += values
            crc_sites += sites
            databases += 1
    return {
        "schema": RECEIPT_SCHEMA,
        "source": str(source),
        "destination": str(destination),
        "verdict": "PASS",
        "values_checked": checked,
        "databases_checked": databases,
        "checksum_sites": crc_sites,
        "undeclared_changed_bytes": 0,
        "copies_not_written": len(list(receipt_document.get("copies_not_written", ()))),
        "iso_bytes_compared": int(iso_verdict.get("unchanged_bytes_compared", 0)),
        "iso": {key: iso_verdict[key] for key in sorted(iso_verdict)
                if isinstance(iso_verdict.get(key), (int, str, bool))},
    }


def _check_padding(after: bytes, edits: Sequence[Mapping[str, Any]], iso_path: str,
                   member: Optional[int], what: str) -> None:
    """Every written name fills its field: the text, then NULs to the width.

    The rule is re-expressed here rather than borrowed from the encoder, so a
    writer that stopped padding -- and left the previous name's tail behind for
    the game to read -- fails this even though every value it wrote reads back.
    """

    database = ea_tdb.parse_tdb(after)
    for edit in edits:
        if str(edit["iso_path"]) != iso_path or edit.get("member") != member:
            continue
        table = database.table(str(edit["table"]))
        record = database.record_bytes(table, int(edit["record"]))
        for span in edit.get("field_spans", ()):
            if str(span.get("type")) != "STRING":
                continue
            field = table.field(str(span["field"]))
            start = field.bit_offset // 8
            raw = record[start:start + field.bit_width // 8]
            text = str(edit["after"].get(field.name, "")).encode(ea_tdb.TEXT_ENCODING)
            if raw[:len(text)] != text or raw[len(text):] != b"\x00" * (len(raw) - len(text)):
                raise IdentityError(
                    f"{field.name} of {table.name} record {edit['record']} in {what} is not "
                    f"the written text followed by NULs to the field's {len(raw)} bytes; a "
                    f"name that does not fill its field leaves the old one's tail behind."
                )


# --------------------------------------------------------------------------
# The synthetic databases
# --------------------------------------------------------------------------

#: The team ids the synthetic disc's databases carry.  Two, so a lane that
#: matched a second copy by position instead of by team id is visibly wrong:
#: the bare database below lists them in the opposite order.
SYNTHETIC_TEAM_IDS: Tuple[int, ...] = (11, 22)

#: The ``TEAM`` fields both synthetic databases declare, in order.  The widths
#: are the ones the real schema publishes for the fields this lane edits, so a
#: budget computed here is the budget a disc would give; the two fields around
#: them are narrow and odd on purpose, so a writer that mis-orders the bit
#: packing spoils a neighbour and is caught.
SYNTHETIC_TEAM_SCHEMA: Tuple[Tuple[str, int, int], ...] = (
    ("TGID", ea_tdb.FIELD_UINT, 10),
    ("TDNA", ea_tdb.FIELD_STRING, 17 * 8),
    ("TLNA", ea_tdb.FIELD_STRING, 18 * 8),
    ("TSNA", ea_tdb.FIELD_STRING, 7 * 8),
    ("TMNC", ea_tdb.FIELD_STRING, 17 * 8),
    ("CYID", ea_tdb.FIELD_UINT, 8),
    ("TBCR", ea_tdb.FIELD_UINT, 8),
    ("TBCG", ea_tdb.FIELD_UINT, 8),
    ("TBCB", ea_tdb.FIELD_UINT, 8),
    ("TB2R", ea_tdb.FIELD_UINT, 8),
    ("TB2G", ea_tdb.FIELD_UINT, 8),
    ("TB2B", ea_tdb.FIELD_UINT, 8),
    ("TCDO", ea_tdb.FIELD_UINT, 8),
    ("TORD", ea_tdb.FIELD_UINT, 10),
    ("TWIN", ea_tdb.FIELD_SINT, 5),
)


def synthetic_team_row(team_id: int) -> Dict[str, Any]:
    """One invented team.  Nothing here comes from a game.

    The names are the word SYNTHETIC and a number, and the colours are the team
    id arithmetic, so the fixture is recognisable as a fixture in any dump of
    it.
    """

    return {
        "TGID": team_id,
        "TDNA": f"SYNTHETICS-{team_id}",
        "TLNA": f"Nowhere-{team_id}",
        "TSNA": f"SY{team_id}",
        "TMNC": f"Synths-{team_id}",
        "CYID": team_id % 251,
        "TBCR": team_id, "TBCG": (team_id * 3) % 256, "TBCB": (team_id * 7) % 256,
        "TB2R": (team_id * 5) % 256, "TB2G": (team_id * 11) % 256, "TB2B": team_id,
        "TCDO": team_id, "TORD": team_id, "TWIN": -3,
    }


def synthetic_team_database(team_id: int) -> bytes:
    """One container member: a ``TEAM`` table of exactly one team, as the disc has it.

    The four checksums are written from the result's own bytes, so this fixture
    passes :func:`ea_tdb.verify_crcs` -- which is what makes it a fair test of a
    writer that has to keep them passing.
    """

    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        (TEAM_TABLE, SYNTHETIC_TEAM_SCHEMA, (synthetic_team_row(team_id),)),
    )))


def synthetic_stream_database() -> bytes:
    """The bare database's second copy of every synthetic team.

    The rows are in the **opposite** order to the container's members, which is
    what the retail disc does too -- its rows are not in team-id order [M] --
    so a lane that resolved the second copy by position would write the wrong
    team here and the verifier would say so.
    """

    return ea_tdb.recompute_crcs(ea_tdb.build_tdb((
        (TEAM_TABLE, SYNTHETIC_TEAM_SCHEMA,
         tuple(synthetic_team_row(team_id) for team_id in reversed(SYNTHETIC_TEAM_IDS))),
    )))


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.madden09_ps2.identity_lane --source DISC.iso``.

    With ``--recipe`` and ``--destination`` it also does the write: it plans,
    builds a NEW image, and runs the independent verifier over the result.  The
    source is opened read-only either way.
    """

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.identity_lane",
        description="List and edit the 32 NFL teams' names and colours on a Madden NFL 09 "
                    "(PS2) disc.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--recipe", help="a JSON recipe of team edits, as compose_recipe writes")
    parser.add_argument("--destination", help="the NEW image to write; it must not exist")
    parser.add_argument("--report", help="write the build receipt and verdict to this JSON file")
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
        print("IDENTITY teams=%d copies_per_build=%d stream_rows=%d"
              % (document["teams_listed"], document["copies_written_per_build"],
                 document["stream_rows"]))
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
            print("IDENTITY_PLAN targets=%d bytes=%d"
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
        print("IDENTITY_WRITE %s" % ("PASS" if verdict.passed else "FAIL"))
        return 0 if verdict.passed else 1
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = ["CAPABILITY_ID", "COLOUR_FIELDS", "IdentityError", "IdentityLane", "KEEP_NUMBER",
           "LANE_ID", "MEASURED_NOT_EDITED", "NFL_TEAM_MEMBERS", "NUMBER_FIELDS",
           "RECEIPT_SCHEMA", "RECIPE_SCHEMA", "SCHEMA", "STREAM_DATABASE",
           "SYNTHETIC_TEAM_IDS", "SYNTHETIC_TEAM_SCHEMA", "TEAM_CONTAINER", "TEAM_ID_FIELD",
           "TEAM_PREFIX", "TEAM_TABLE", "TEXT_FIELDS", "fields_for", "format_colour",
           "number_bound", "parse_colour", "parse_team_key", "record_writes",
           "synthetic_stream_database", "synthetic_team_database", "synthetic_team_row",
           "team_key", "team_values", "verify_build"]


if __name__ == "__main__":
    raise SystemExit(_main())
