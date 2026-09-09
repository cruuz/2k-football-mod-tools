"""Offline, data-only CPU book clones in a new APF game folder.

An unused offensive label's existing name becomes its type. Only its type
pointer and the selected team's assignment pointer change; no string pool or
save capacity is guessed. A cloned IFF is appended to the LAST volume, and a
sorted directory row uses verified zero space before the first payload.

This finalization changes outer indices. Apply other Studio edits first, then
clone. Runtime loading of the expanded archive is UNWITNESSED. No XEX patch is
needed by the traced name-based resolver, and no executable bytes are changed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
from typing import Callable, Iterable

from .errors import ValidationError
from . import apf2k8_splb_writer as splb
from .apf2k8_book_identity import (
    book_identity_report, filename_id, parse_roster_identity, read_resource,
)
import apf_inner
import apf_outer
import apf_roster
import apf_texture_patch


PROVIDER_KIND = "splb_book_clone"
REPORT_SCHEMA = "apf2k8_book_clone/v1"
REQUEST_SCHEMA = "apf2k8_book_clone_requests/v1"
STATUS = "A_PROVEN offline clone/allocation/assignment; UNWITNESSED in game"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class CloneRequest:
    label_id: int
    team_index: int
    donor_type: str

    def __post_init__(self):
        if type(self.label_id) is not int or not 0 <= self.label_id < 69:
            raise ValidationError("Clone label ID must be 0..68")
        if type(self.team_index) is not int or not 0 <= self.team_index < 40:
            raise ValidationError("Clone team index must be 0..39")
        if not isinstance(self.donor_type, str) or self.donor_type not in {
                x for x in splb.STOCK_BOOKS.values() if x.startswith("O-")}:
            raise ValidationError("Choose one of the seven existing offensive CPU book donors")


def requests_from_json(data: bytes) -> tuple[CloneRequest, ...]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(f"Duplicate clone JSON key: {key}")
            result[key] = value
        return result
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != {"schema", "clones"} or value["schema"] != REQUEST_SCHEMA:
            raise ValidationError("Unknown book-clone recipe schema")
        rows = value["clones"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 36:
            raise ValidationError("Supply 1..36 book clone requests")
        result = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"label_id", "team_index", "donor_type"}:
                raise ValidationError("A clone request has unsupported fields")
            result.append(CloneRequest(**row))
        return tuple(result)
    except (UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(f"Invalid book-clone JSON: {exc}") from exc


def _requests(requests: Iterable[CloneRequest]) -> tuple[CloneRequest, ...]:
    rows = tuple(requests)
    if not rows or any(not isinstance(x, CloneRequest) for x in rows):
        raise ValidationError("Supply at least one CloneRequest")
    if len({x.label_id for x in rows}) != len(rows) or len({x.team_index for x in rows}) != len(rows):
        raise ValidationError("Clone requests must use distinct labels and teams")
    return tuple(sorted(rows, key=lambda x: x.label_id))


def bind_roster(body: bytes, requests: Iterable[CloneRequest], *, raw_save: bool = False) -> tuple[bytes, dict]:
    """Use existing UTF-16 strings as new types; preserve all other bytes."""
    rows = _requests(requests)
    before = parse_roster_identity(body, raw_save=raw_save)
    output = bytearray(body)
    fields = set()
    changes = []
    for request in rows:
        label = before.labels[request.label_id]
        team = before.teams[request.team_index]
        if label.side != "offense":
            raise ValidationError("Independent book clones currently require an offensive label")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 -]{0,26}", label.name):
            raise ValidationError("Clone label names must be 1..27 ASCII letters, digits, spaces or hyphens")
        if label.name in splb.STOCK_BOOKS.values() or label.name in ("UA", "UB"):
            raise ValidationError("Clone label name collides with a built-in or runtime book")
        peers = [x.index for x in before.teams if x.offense == label.index and x.index != team.index]
        if peers:
            raise ValidationError(f"Label {label.index} is already assigned to other teams: {peers}")
        if any(x.index != label.index and x.kind == label.name for x in before.labels):
            raise ValidationError("Another label already uses the proposed clone type")
        # A field-local relative pointer is one-based; the target string itself
        # is immutable and may safely have other readers (e.g. a defensive label).
        name_target = apf_roster.resolve_relative(body, label.offset, "clone label name")
        for field, target in ((label.offset + 4, name_target), (team.offense_field, label.offset)):
            struct.pack_into(">I", output, field, (target - field + 1) & 0xFFFFFFFF)
            fields.update(range(field, field + 4))
        changes.append({"team_index": team.index, "label_id": label.index, "label": label.name,
                        "before_type": label.kind, "after_type": label.name,
                        "type_pointer_offset": label.offset + 4,
                        "assignment_pointer_offset": team.offense_field})
    result = bytes(output)
    after = parse_roster_identity(result, raw_save=raw_save)
    changed = [i for i, (a, b) in enumerate(zip(body, result)) if a != b]
    if not set(changed) <= fields:
        raise ValidationError("Clone assignment escaped its two pointer fields")
    for request in rows:
        label = after.labels[request.label_id]
        if label.kind != label.name or after.teams[request.team_index].offense != label.index:
            raise ValidationError("Clone assignment did not survive reparse")
    return result, {"changes": changes, "changed_byte_count": len(changed),
                    "changed_offsets": changed, "all_string_bytes_preserved": True,
                    "resource_length_preserved": len(result) == len(body)}


def clone_body(donor: bytes, name: str) -> bytes:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 -]{0,26}", name):
        raise ValidationError("Clone name must fit the 28-unit NUL-terminated header")
    splb.parse_book(donor, 0)
    output = bytearray(donor)
    output[0x30:0x68] = (name.encode("utf-16-be") + b"\0\0").ljust(0x38, b"\0")
    result = bytes(output)
    verify_clone_body(donor, result, name)
    return result


def verify_clone_body(donor: bytes, clone: bytes, name: str) -> dict:
    before = splb.parse_book(donor, 0)
    after = splb.parse_book(clone, 0)
    expected_name = (name.encode("utf-16-be") + b"\0\0").ljust(0x38, b"\0")
    if (len(expected_name) != 0x38 or clone[0x30:0x68] != expected_name
            or donor[:0x30] != clone[:0x30] or donor[0x68:] != clone[0x68:]
            or before.records != after.records):
        raise ValidationError("Clone differs from donor outside its exact book-name allocation")
    return {"donor_sha256": _sha(donor), "clone_sha256": _sha(clone),
            "identical_except_name": True, "record_count": len(after.records),
            "populated_records": sum(x.populated for x in after.records)}


def rebuild_resource(source, replacement: bytes) -> tuple[bytes, dict]:
    """Rebuild one fixed IFF allocation, rejecting even round-tripping overlaps."""
    _archive, entry, record, body, decoded, original = source
    if len(body) != len(replacement):
        raise ValidationError("The replacement must preserve the decoded resource extent")
    part = record.files[0].parts[0]
    block = record.blocks[0]
    if not block.is_compressed or block.wrapper is None or part.block_index != 0:
        raise ValidationError("Expected a single H7A block")
    wanted = decoded[:part.offset] + replacement + decoded[part.offset + part.length:]
    stored = original[block.start_offset:block.start_offset + block.stored_length]
    encoded, transport = apf_inner.encode_h7a_preserving_tokens(stored[20:], decoded, wanted, block.wrapper.shift)
    tokens, _used = apf_inner._parse_h7a_tokens(encoded, len(wanted), block.wrapper.shift)
    if any(x.distance is not None and x.length > x.distance for x in tokens):
        raise ValidationError("H7A output contains a match longer than its distance")
    packed = struct.pack(">5I", apf_inner.H7A_MAGIC, len(wanted), len(encoded) + 20,
                         block.unknown_10, block.wrapper.shift) + encoded
    header = bytearray(original[:record.header_size])
    struct.pack_into(">8I", header, apf_inner.IFF_HEADER_SIZE,
                     block.name_hash, block.type_hash, block.unknown_08, len(wanted),
                     block.unknown_10, record.header_size, len(packed), block.indexed)
    struct.pack_into(">I", header, 8, record.header_size + len(packed))
    footer_end = record.file_length + 8 + record.footer.payload_size
    if any(original[footer_end:]):
        raise ValidationError("IFF allocation tail is not zero; refuse to consume it")
    active = bytes(header) + packed + original[record.file_length:footer_end]
    if len(active) > entry.size:
        raise ValidationError(f"Rebuilt IFF needs {len(active)} bytes; allocation is {entry.size}")
    output = active.ljust(entry.size, b"\0")
    reader = apf_texture_patch.BytesReader(output)
    reparsed = apf_inner.parse_iff(reader, entry)
    roundtrip = apf_inner.decode_block(reader, reparsed, 0, 16 * 1024 * 1024)
    if reparsed.warnings or roundtrip != wanted or reparsed.files != record.files:
        raise ValidationError("Rebuilt IFF failed independent reparse")
    return output, {"allocation_bytes": entry.size, "active_bytes": len(active),
                    "remaining_bytes": entry.size - len(active), "h7a_round_trip_exact": True,
                    "h7a_overlapping_matches": 0, "transport": transport}


@dataclass(frozen=True)
class CompiledClone:
    name: str
    donor_type: str
    name_id: int
    virtual_offset: int
    entry_bytes: bytes
    body: bytes


@dataclass(frozen=True)
class CompiledUnlock:
    source_index: Path
    requests: tuple[CloneRequest, ...]
    directory_before: bytes
    directory_after: bytes
    roster_source_sha256: str
    roster_entry: bytes
    roster_body: bytes
    clones: tuple[CompiledClone, ...]
    report: dict


def compile_unlock(index_path: Path, requests: Iterable[CloneRequest]) -> CompiledUnlock:
    requests = _requests(requests)
    index_path = Path(index_path).resolve()
    roster_source = read_resource(index_path, apf_roster.OUTER_NAME_ID, "roster", "ROST")
    archive, roster_entry, _record, roster_before, _decoded, _original = roster_source
    identity = parse_roster_identity(roster_before)
    roster_after, binding = bind_roster(roster_before, requests)
    roster_packed, roster_transport = rebuild_resource(roster_source, roster_after)
    entries = sorted(archive.entries, key=lambda x: x.virtual_offset)
    first = entries[0].virtual_offset
    if first < archive.table_end or first > 16 * 1024 * 1024:
        raise ValidationError("Archive directory/payload boundary is unsupported")
    previous = first
    for entry in entries:
        if entry.virtual_offset != previous:
            raise ValidationError("Archive has gaps or overlapping allocations")
        previous = entry.virtual_end
    if previous != archive.virtual_size:
        raise ValidationError("Archive tail is not fully accounted for")
    original_ids = [x.name_id for x in archive.entries]
    if original_ids != sorted(set(original_ids)):
        raise ValidationError("Archive filename directory is not strictly sorted and unique")
    with index_path.open("rb") as stream:
        directory_before = stream.read(first)
    if len(directory_before) != first:
        raise ValidationError("Truncated archive directory")
    directory = bytearray(directory_before)
    clones = []
    proofs = []
    position = archive.virtual_size
    ids = set(original_ids)
    for request in requests:
        label = identity.labels[request.label_id]
        donor = read_resource(index_path, filename_id(request.donor_type), "spb", "SPLB")
        if splb.parse_book(donor[3], donor[1].table_index).name != request.donor_type:
            raise ValidationError("Donor filename and SPLB header disagree")
        replacement = clone_body(donor[3], label.name)
        name_id = filename_id(label.name)
        if name_id in ids:
            if label.kind != label.name:
                raise ValidationError(f"Clone filename hash collides with an existing resource: {label.name}")
            existing = read_resource(index_path, name_id, "spb", "SPLB")
            verify_clone_body(donor[3], existing[3], label.name)
            proofs.append({"name": label.name, "already_applied": True})
            continue
        packed, transport = rebuild_resource(donor, replacement)
        clones.append(CompiledClone(label.name, request.donor_type, name_id, position, packed, replacement))
        ids.add(name_id)
        proofs.append({"name": label.name, "donor": request.donor_type, "name_id": f"0x{name_id:08X}",
                       "virtual_offset": position, **verify_clone_body(donor[3], replacement, label.name),
                       "transport": transport})
        position += len(packed)
    table = [(x.name_id, x.offset_blocks, x.size_blocks) for x in archive.entries]
    table.extend((x.name_id, x.virtual_offset // archive.alignment, len(x.entry_bytes) // archive.alignment)
                 for x in clones)
    table.sort()
    end = archive.table_start + len(table) * apf_outer.ENTRY_RECORD_SIZE
    if end > first or any(directory_before[archive.table_end:end]):
        raise ValidationError("No verified zero directory allocation for another book row")
    if any(len(x.entry_bytes) % archive.alignment for x in clones):
        raise ValidationError("Clone allocation does not align to the archive block size")
    struct.pack_into(">I", directory, 0x10, len(table))
    last_size = archive.packs[-1].size_blocks + (position - archive.virtual_size) // archive.alignment
    if last_size > 0xFFFFFFFF or position // archive.alignment > 0xFFFFFFFF:
        raise ValidationError("Expanded archive exceeds its 32-bit block fields")
    struct.pack_into(">I", directory, 0x18 + (len(archive.packs) - 1) * 16, last_size)
    for index, row in enumerate(table):
        struct.pack_into(">III", directory, archive.table_start + 12 * index, *row)
    new_indices = {row[0]: index for index, row in enumerate(table)}
    books = {}
    for label in parse_roster_identity(roster_after).labels:
        if label.kind in books:
            continue
        key = filename_id(label.kind)
        if key in new_indices:
            # A filename match alone is not a type proof. Reparse pre-existing
            # resources too before describing them as resolved in a receipt.
            if key in original_ids:
                resource = read_resource(index_path, key, "spb", "SPLB")
                if splb.parse_book(resource[3], resource[1].table_index).name != label.kind:
                    raise ValidationError("An assigned book has a mismatched header")
            books[label.kind] = new_indices[key]
    report = {"schema": REPORT_SCHEMA, "status": STATUS, "base_executable_patch_required": False,
              "title_update_compatibility": "UNKNOWN: TU executable not reconstructed or witnessed",
              "clones": proofs, "roster_binding": binding, "roster_transport": roster_transport,
              "directory": {"entries_before": len(archive.entries), "entries_after": len(table),
                            "table_end_before": archive.table_end, "table_end_after": end,
                            "first_payload_offset": first, "zero_directory_bytes_consumed": end - archive.table_end,
                            "append_pack": archive.packs[-1].name,
                            "append_bytes": position - archive.virtual_size,
                            "existing_payload_offsets_preserved": True,
                            "old_to_new_outer_indices": {str(x.table_index): new_indices[x.name_id]
                                                          for x in archive.entries}},
              "book_identity": book_identity_report(parse_roster_identity(roster_after), books),
              "follow_up": "Finalize after other Studio edits; numeric outer indices change. Test base XEX in game."}
    return CompiledUnlock(index_path, requests, directory_before, bytes(directory),
                          _sha(roster_source[5]), roster_packed, roster_after, tuple(clones), report)


def verify_unlock(plan: CompiledUnlock, output_index: Path) -> dict:
    """Reparse directory, ROST and each clone and compare every other pack byte."""
    before = apf_outer.parse_archive(plan.source_index)
    after = apf_outer.parse_archive(Path(output_index))
    old = {x.name_id: x for x in before.entries}
    new = {x.name_id: x for x in after.entries}
    if len(new) != len(after.entries) or set(new) != set(old) | {x.name_id for x in plan.clones}:
        raise ValidationError("Expanded archive directory has missing/extra/duplicate resources")
    if [x.name_id for x in after.entries] != sorted(new):
        raise ValidationError("Expanded archive directory is not sorted")
    for key, entry in old.items():
        actual = new[key]
        if (actual.virtual_offset, actual.size) != (entry.virtual_offset, entry.size):
            raise ValidationError("An existing resource moved or changed allocation")
    if len(before.packs) != len(after.packs) or [p.name for p in before.packs] != [p.name for p in after.packs]:
        raise ValidationError("Archive volume identity changed")
    for index, (a, b) in enumerate(zip(before.packs, after.packs)):
        extra = sum(len(x.entry_bytes) for x in plan.clones) if index == len(before.packs) - 1 else 0
        if b.declared_size != a.declared_size + extra:
            raise ValidationError("Expanded volume size disagrees with clone allocations")
    roster = read_resource(output_index, apf_roster.OUTER_NAME_ID, "roster", "ROST")
    source_roster = read_resource(plan.source_index, apf_roster.OUTER_NAME_ID, "roster", "ROST")
    if _sha(source_roster[5]) != plan.roster_source_sha256:
        raise ValidationError("Source roster allocation changed since compilation")
    expected_roster, _receipt = bind_roster(source_roster[3], plan.requests)
    if roster[3] != expected_roster or roster[5] != plan.roster_entry:
        raise ValidationError("Expanded archive has the wrong roster binding")
    for clone in plan.clones:
        resource = read_resource(output_index, clone.name_id, "spb", "SPLB")
        donor = read_resource(plan.source_index, filename_id(clone.donor_type), "spb", "SPLB")
        verify_clone_body(donor[3], resource[3], clone.name)
        if resource[1].virtual_offset != clone.virtual_offset or resource[5] != clone.entry_bytes:
            raise ValidationError("Clone allocation/transport does not match the compiled result")
    # Compare the whole copied archive, excluding only the two authorized spans.
    allowed = [(0, len(plan.directory_after))]
    re = old[apf_roster.OUTER_NAME_ID]
    allowed.append((re.virtual_offset, re.virtual_end))
    compared = compare_untouched_packs(before, after, allowed)
    with Path(output_index).open("rb") as stream:
        if stream.read(len(plan.directory_after)) != plan.directory_after:
            raise ValidationError("Directory bytes differ from the compiled allocation")
    # Reapplying the recipe must not append duplicate resources or flip pointers.
    repeated = compile_unlock(output_index, plan.requests)
    if repeated.clones or repeated.roster_body != roster[3] or repeated.directory_after != plan.directory_after:
        raise ValidationError("Book clone apply is not idempotent")
    executable = compare_executable(plan.source_index.parent, Path(output_index).parent)
    return {"directory_roster_clones_and_label_resources_reparsed": True,
            "untouched_pack_bytes_compared": compared, "executable": executable,
            "clone_count_added": len(plan.clones), "idempotent_reapply": True,
            "runtime_status": "UNWITNESSED"}


def compare_executable(source_root: Path, output_root: Path) -> dict:
    """Prove that the optional executable was copied without modification."""
    source, output = source_root / "default.xex", output_root / "default.xex"
    if not source.is_file():
        if output.exists():
            raise ValidationError("An executable was introduced into a packs-only build")
        return {"present": False}
    digest = hashlib.sha256()
    count = 0
    with source.open("rb") as a, output.open("rb") as b:
        while True:
            chunk = a.read(4 * 1024 * 1024)
            if b.read(len(chunk) if chunk else 1) != chunk:
                raise ValidationError("Copied executable differs from the source")
            if not chunk:
                break
            digest.update(chunk)
            count += len(chunk)
    return {"present": True, "byte_identical": True, "bytes_compared": count,
            "sha256": digest.hexdigest()}


def compare_untouched_packs(before, after, allowed: list[tuple[int, int]]) -> int:
    """Byte-compare original volume ranges outside explicitly owned edits."""
    if ([x.name for x in before.packs] != [x.name for x in after.packs]
            or any(a.virtual_start != b.virtual_start for a, b in zip(before.packs, after.packs))):
        raise ValidationError("Archive volume mapping changed")
    compared = 0
    for pack, output_pack in zip(before.packs, after.packs):
        boundaries = sorted({pack.virtual_start, pack.virtual_end,
                             *(max(pack.virtual_start, min(pack.virtual_end, p))
                               for pair in allowed for p in pair)})
        with pack.path.open("rb") as source, output_pack.path.open("rb") as output:
            for start, end in zip(boundaries, boundaries[1:]):
                if any(a <= start and end <= b for a, b in allowed):
                    continue
                source.seek(start - pack.virtual_start)
                output.seek(start - pack.virtual_start)
                remaining = end - start
                while remaining:
                    count = min(4 * 1024 * 1024, remaining)
                    a, b = source.read(count), output.read(count)
                    if len(a) != count or a != b:
                        raise ValidationError("A byte outside the clone/directory/roster allocations changed")
                    remaining -= count
                    compared += count
    return compared


def build_new_folder(plan: CompiledUnlock, destination: Path,
                     progress: Callable[[str], None] = lambda _message: None) -> dict:
    """Copy the user's packs and XEX to a new directory, apply, then verify.

    A failed build removes only the directory this call just created. Existing
    destinations are refused, including symlinks; retail inputs stay read-only.
    """
    if Path(destination).is_symlink():
        raise ValidationError("Output directory must not be a symlink")
    destination = Path(destination).resolve()
    source_root = plan.source_index.parent
    if destination == source_root or destination in source_root.parents or source_root in destination.parents:
        raise ValidationError("Choose a separate new output directory outside the source game")
    archive = apf_outer.parse_archive(plan.source_index)
    with plan.source_index.open("rb") as stream:
        if stream.read(len(plan.directory_before)) != plan.directory_before:
            raise ValidationError("Source directory changed since compilation")
    roster_source = read_resource(plan.source_index, apf_roster.OUTER_NAME_ID, "roster", "ROST")
    if _sha(roster_source[5]) != plan.roster_source_sha256:
        raise ValidationError("Source roster allocation changed since compilation; review it again")
    destination.mkdir(parents=False, exist_ok=False)
    try:
        for pack in archive.packs:
            progress(f"Copying {pack.name}")
            shutil.copyfile(pack.path, destination / pack.name)
        xex = source_root / "default.xex"
        if xex.is_file():
            shutil.copyfile(xex, destination / xex.name)
        roster_entry = next(x for x in archive.entries if x.name_id == apf_roster.OUTER_NAME_ID)
        cursor = 0
        for segment in roster_entry.segments:
            with (destination / segment.pack_name).open("r+b") as stream:
                stream.seek(segment.pack_offset)
                stream.write(plan.roster_entry[cursor:cursor + segment.size])
            cursor += segment.size
        with (destination / archive.packs[-1].name).open("ab") as stream:
            for clone in plan.clones:
                stream.write(clone.entry_bytes)
        with (destination / plan.source_index.name).open("r+b") as stream:
            stream.write(plan.directory_after)
        progress("Verifying all archive bytes and reparsing the clone assignments")
        verification = verify_unlock(plan, destination / plan.source_index.name)
        receipt = {**plan.report, "verification": verification}
        receipt_path = destination / "book-unlock-receipt.json"
        temporary = destination / "book-unlock-receipt.json.partial"
        temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, receipt_path)
        return receipt
    except BaseException:
        shutil.rmtree(destination)
        raise
