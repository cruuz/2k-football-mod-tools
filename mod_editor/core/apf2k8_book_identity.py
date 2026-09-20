"""Report the distinction between a team label, a disc book, and personnel.

Resolution here proves serialized identity, not a live CPU choice. The base
executable formats ``{type}-spb.iff``; UA/UB and mode-specific overrides can
select runtime buffers instead. See ASTRA_REPORT.md for the instruction proof.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import struct
import zlib
import hashlib
import re

from .errors import ValidationError
from . import apf2k8_splb_writer as splb

import apf_inner
import apf_outer
import apf_roster
import apf_save_playbook_assignments as save_writer


REPORT_SCHEMA = "apf2k8_book_identity/v1"
FORMATION_PERSONNEL_BOUNDARY = (
    "A team selects a label; its type selects a shared disc book. A book record "
    "selects formation geometry and a separate personnel category. The row "
    "fallback and the chosen stored play can select different records. CPU "
    "personnel policy and the O-Shotgun WR1/WR4 and WR2/WR3 depth flips remain UNKNOWN."
)


def filename_id(book_type: str) -> int:
    try:
        return zlib.crc32((book_type + "-spb.iff").encode("ascii").upper())
    except UnicodeEncodeError as exc:
        raise ValidationError("Book resource types must be ASCII") from exc


@dataclass(frozen=True)
class Label:
    index: int
    offset: int
    name: str
    kind: str
    side: str


@dataclass(frozen=True)
class Team:
    index: int
    name: str
    offense: int
    defense: int
    offense_field: int
    defense_field: int


@dataclass(frozen=True)
class RosterIdentity:
    labels: tuple[Label, ...]
    teams: tuple[Team, ...]
    layout: str


def parse_roster_identity(body: bytes, *, raw_save: bool = False) -> RosterIdentity:
    if raw_save:
        parsed = save_writer.parse_save(body)
        if parsed.layout.signed_container:
            raise ValidationError("Extract and verify the signed save before editing its raw payload")
        labels = tuple(Label(x.playbook_id, x.offset, x.name, x.kind, x.side_name)
                       for x in parsed.playbooks)
        teams = tuple(Team(x.team_index, f"Team slot {x.team_index:02d}",
                           x.offensive_playbook_id, x.defensive_playbook_id,
                           x.offense_field_offset, x.defense_field_offset)
                      for x in parsed.teams)
        return RosterIdentity(labels, teams, "raw_roster_save")
    tables, _root = apf_roster.parse_root(body)
    labels = []
    for index in range(tables[11].count):
        at = tables[11].offset + index * 12
        side = struct.unpack_from(">I", body, at + 8)[0]
        if side not in (0, 0x01000000):
            raise ValidationError(f"Label {index} has an unknown side")
        strings = [apf_roster.decode_utf16be_z(
            body, apf_roster.resolve_relative(body, at + delta, "book label"), "book label")
            for delta in (0, 4)]
        labels.append(Label(index, at, *strings, "offense" if side == 0 else "defense"))
    by_offset = {x.offset: x for x in labels}
    teams = []
    for index in range(tables[4].count):
        at = tables[4].offset + index * 384
        selected = []
        for delta, side in ((0xE0, "offense"), (0xE4, "defense")):
            target = apf_roster.resolve_relative(body, at + delta, "team book")
            label = by_offset.get(target)
            if label is None or label.side != side:
                raise ValidationError(f"Team {index} has an invalid {side} label pointer")
            selected.append(label.index)
        name = apf_roster.decode_utf16be_z(
            body, apf_roster.resolve_relative(body, at + 0xA8, "team name"), "team name")
        teams.append(Team(index, name, *selected, at + 0xE0, at + 0xE4))
    return RosterIdentity(tuple(labels), tuple(teams), "disc_ROST")


def rewrite_save_label_type(body: bytes, label_id: int, book_type: str) -> tuple[bytes, dict]:
    """Bind one raw roster label to an existing immutable string, as disc clones do.

    Never overwrite an interned type string: other labels may share it. Clone
    types are names already present in the roster's label/team string pool.
    Unsupported or missing names require a different source roster, not growth
    of an unproved save allocation.
    """
    from mod_editor.apf_studio import ps3_roster_convert as layout

    if not isinstance(body, bytes) or len(body) != layout.ROSTER_SIZE:
        raise ValidationError("Choose a raw 2,715,908-byte Xbox Roster.ROS; season saves are unsupported")
    if type(label_id) is not int or not 0 <= label_id < save_writer.PLAYBOOK_COUNT:
        raise ValidationError("Choose a roster label from 0 to 68")
    if not isinstance(book_type, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 -]{0,26}", book_type):
        raise ValidationError("Book types must be 1..27 ASCII letters, digits, spaces or hyphens")
    try:
        layout.verify_converted(body)
        structure = layout.inspect_structure(body)
        before = parse_roster_identity(body, raw_save=True)
        targets = sorted(t for t, a in structure.allocations.items()
                         if a.text == book_type and structure.pool_start <= t < layout.RUNTIME_BLOCK_OFFSET
                         and not a.odd and t not in structure.interior)
        if not targets:
            raise ValidationError("This book type is absent from the save's string pool. Choose a clone "
                                  "using an existing saved label or team name; string allocation is unsupported")
        label = before.labels[label_id]
        if label.kind == book_type:
            raise ValidationError("This label already uses the selected book type")
        field = label.offset + 4
        output = bytearray(body)
        struct.pack_into(">i", output, field, targets[0] - field + 1)
        result = bytes(output)
        after = parse_roster_identity(result, raw_save=True)
        strict = layout.verify_converted(result)
    except (layout.PS3RosterConvertError, save_writer.SaveError) as exc:
        raise ValidationError(f"Raw roster validation failed: {exc}") from exc
    if after.teams != before.teams or any(
            new != (Label(old.index, old.offset, old.name, book_type, old.side)
                    if old.index == label_id else old)
            for old, new in zip(before.labels, after.labels)):
        raise ValidationError("The label type did not reparse independently")
    changed = [i for i in range(field, field + 4) if body[i] != result[i]]
    if body[:field] != result[:field] or body[field + 4:] != result[field + 4:]:
        raise ValidationError("The label edit escaped its type pointer")
    return result, {
        "schema": "apf2k8_save_label_type/v1", "label_id": label_id, "label": label.name,
        "side": label.side, "before_type": label.kind, "after_type": book_type,
        "type_pointer_offset": field, "string_target_offset": targets[0],
        "filename": book_type + "-spb.iff", "filename_id": filename_id(book_type),
        "source_sha256": hashlib.sha256(body).hexdigest(),
        "output_sha256": hashlib.sha256(result).hexdigest(),
        "changed_offsets": changed, "changed_byte_count": len(changed),
        "affected_team_indices": [t.index for t in before.teams if getattr(t, label.side) == label_id],
        "team_assignments_unchanged": True, "all_string_bytes_preserved": True,
        "strict_readers": strict, "runtime_in_game_proved": False,
        "runtime_status": "UNWITNESSED: load this roster with the matching built game and check the team's plays",
    }


def verify_save_label_type(source: bytes, output: bytes, receipt: dict) -> dict:
    """Re-derive the permitted edit from the source, then compare every byte."""
    expected, derived = rewrite_save_label_type(source, receipt.get("label_id"), receipt.get("after_type"))
    if output != expected or any(receipt.get(key) != value for key, value in derived.items()):
        raise ValidationError("Written label type or receipt differs from the verified edit")
    return {"verified": True, "changed_byte_count": derived["changed_byte_count"]}


def read_resource(index_path: Path, name_id: int, name: str, type_name: str):
    """Read by filename hash so sorted-directory insertions cannot change ownership."""
    archive = apf_outer.parse_archive(Path(index_path))
    matches = [x for x in archive.entries if x.name_id == name_id]
    if len(matches) != 1:
        raise ValidationError(f"Expected one archive resource 0x{name_id:08X}, found {len(matches)}")
    entry = matches[0]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        if record.warnings or record.file_count != 1 or record.block_count != 1:
            raise ValidationError("Book/roster IFF ownership is not the proved single-resource layout")
        item = record.files[0]
        if item.name != name or item.type_name != type_name or len(item.parts) != 1:
            raise ValidationError("Book/roster inner resource identity changed")
        part = item.parts[0]
        decoded = apf_inner.decode_block(reader, record, part.block_index, 16 * 1024 * 1024)
        body = decoded[part.offset:part.offset + part.length]
        original_entry = reader.read(entry, 0, entry.size)
    return archive, entry, record, body, decoded, original_entry


def read_disc_roster(index_path: Path) -> bytes:
    return read_resource(index_path, apf_roster.OUTER_NAME_ID, "roster", "ROST")[3]


def book_identity_report(identity: RosterIdentity, books: dict[str, int | None] | None = None) -> dict:
    """Report all 80 assignments, including unresolved types and all other sharers.

    With no archive, known stock names are a reference map, not an inspection
    of the user's installed packs. Unknown types never become invented books.
    """
    observed = books is not None
    if books is None:
        books = {name: index for index, name in splb.STOCK_BOOKS.items()}
    labels = {x.index: x for x in identity.labels}
    sharing = defaultdict(list)
    for team in identity.teams:
        for side, label_id in (("offense", team.offense), ("defense", team.defense)):
            sharing[(side, labels[label_id].kind)].append(team.index)
    rows = []
    for team in identity.teams:
        for side, label_id in (("offense", team.offense), ("defense", team.defense)):
            label = labels[label_id]
            resolved = label.kind if label.kind in books else None
            peers = [x for x in sharing[(side, label.kind)] if x != team.index]
            rows.append({"team_index": team.index, "team_name": team.name, "side": side,
                         "label_id": label.index, "label": label.name, "type": label.kind,
                         "resolved_book": resolved,
                         "filename": label.kind + "-spb.iff", "outer_index": books.get(label.kind),
                         "shared": bool(peers), "shared_with_team_indices": peers,
                         "status": ("A_PROVEN: resource reparsed" if observed else
                                    "A_PROVEN: label type; stock resource reference only") if resolved else
                                   "UNKNOWN: resource missing or type not inspected"})
    return {"schema": REPORT_SCHEMA, "title": "Book Identity", "layout": identity.layout,
            "archive_inspected": observed, "assignments": rows,
            "distinct_label_types": {side: len({x.kind for x in identity.labels if x.side == side})
                                     for side in ("offense", "defense")},
            "formation_vs_book": FORMATION_PERSONNEL_BOUNDARY,
            "runtime_status": "UNWITNESSED: serialized sharing; mode/UA/UB overrides are not captured"}


def disc_book_identity_report(index_path: Path, roster_body: bytes | None = None) -> dict:
    identity = parse_roster_identity(read_disc_roster(index_path) if roster_body is None else roster_body)
    archive = apf_outer.parse_archive(Path(index_path))
    existing = {x.name_id for x in archive.entries}
    books = {}
    for kind in sorted({x.kind for x in identity.labels}):
        if filename_id(kind) not in existing:
            continue
        _, entry, _, body, _, _ = read_resource(index_path, filename_id(kind), "spb", "SPLB")
        book = splb.parse_book(body, entry.table_index)
        if book.name != kind:
            raise ValidationError(f"Book {kind!r} has a different SPLB header name")
        books[kind] = entry.table_index
    return book_identity_report(identity, books)
