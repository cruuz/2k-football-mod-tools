#!/usr/bin/env python3
"""Create a copied NFL 2K5 XISO applying fixed-size coach name edits.

This applies the proved same-allocation name contract of
``nfl_player_roster_general_workflow.py`` to the ROST coach table of the main
disc roster.  Every coach record carries pointer-referenced UTF-16LE
``first_name`` (+0x00) and ``last_name`` (+0x04) strings; each edit must fit
inside the current decoded name span (up to and including its NUL terminator),
and the remainder of that span is zero-filled.  A replacement that needs more
bytes than the existing span is refused; longer names need the full-allocation
writer, which does not exist.

Per-field ownership mirrors the player writer's check: a name is writable only
when its allocation is referenced by EXACTLY ONE known decoded ROST pointer.
The reference census covers the same pointer domains the player audit counts
(team/stadium/coach/college/player text fields, team labels, generated names,
historic descriptors, and the structural resource label), re-derived live from
the pinned retail body instead of trusting a separate audit file.

Every pointer, coach record scalar, team coach reference, XDVDFS extent, and
``default.xbe`` is preserved.  The retail source is opened read-only and is
never rewritten.  The output is created exclusively and must differ from the
source only at the planned byte offsets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling import below fails there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import nfl_team_identity_xiso_workflow as common

SCHEMA = "nfl2k5_coach_roster_name_workflow/v1"
PLAN_SCHEMA = "nfl2k5_coach_roster_name_plan/v1"
SOURCE_SHA256 = common.SOURCE_SHA256
PACK0_SHA256 = common.PACK0_SHA256
XBE_SHA256 = common.XBE_SHA256
IMAGE_SIZE = common.IMAGE_SIZE
PACK0_SECTOR = common.PACK0_SECTOR
PACK0_SIZE = common.PACK0_SIZE
ROST_OUTER = common.ROST_OUTER_OFFSET
ROST_BODY = ROST_OUTER + common.ROST_WRAPPER_SIZE
ROST_BODY_SIZE = common.ROST_BODY_SIZE
ROST_BODY_SHA256 = "b1164eeed262988dc97d840ba59f6274c1f5d4505249474e4cafd4e322d9f7ae"

ROST_ROOT_OFFSET = 0x40
ROST_ROOT_SIZE = 0x70
STRUCTURAL_LABEL_OFFSET = 0x20
MAX_UTF16_BYTES = 4096

COACH_STRIDE = 0xA8
COACH_TABLE_OFFSET = 0x2AD0
COACH_TABLE_COUNT = 35
TEAM_STRIDE = 0x1F4
TEAM_COACH_POINTER_FIELD = 0x14C
NAME_FIELDS = {"first_name": 0x00, "last_name": 0x04}

TABLE_SPECS = (
    ("primary_players", 0x00, 0x04, 0x54),
    ("secondary_players", 0x08, 0x0C, 0x54),
    ("stadiums", 0x10, 0x14, 0x80),
    ("teams", 0x18, 0x1C, TEAM_STRIDE),
    ("colleges", 0x20, 0x24, 0x08),
    ("coaches", 0x30, 0x34, COACH_STRIDE),
    ("player_pointer_vector", 0x38, 0x3C, 0x04),
    ("team_labels", 0x48, 0x4C, 0x08),
    ("generated_names", 0x50, 0x54, 0x08),
    ("historic_descriptors", 0x58, 0x5C, 0x10),
)

REFERENCE_DOMAINS = (
    ("teams", (0x104, 0x108, 0x10C, 0x138, 0x13C)),
    ("stadiums", (0x00, 0x08, 0x0C, 0x10, 0x14)),
    ("coaches", (0x00, 0x04, 0x08, 0x0C, 0x10)),
    ("colleges", (0x00,)),
    ("primary_players", (0x10, 0x14)),
    ("secondary_players", (0x10, 0x14)),
    ("team_labels", (0x00, 0x04)),
    ("generated_names", (0x00, 0x04)),
    ("historic_descriptors", (0x0C,)),
)


class WorkflowError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowError(message)


def read_regular_json(path: Path, label: str) -> tuple[Path, bytes, tuple[int, int]]:
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode), f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    fd = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        require(stat.S_ISREG(opened.st_mode), f"{label} is not a regular file")
        owned = (opened.st_dev, opened.st_ino)
        require(owned == (resolved.stat().st_dev, resolved.stat().st_ino),
                f"{label} pathname changed after open")
        raw = common.pread_exact(fd, 0, opened.st_size)
    finally:
        os.close(fd)
    return resolved, raw, owned


def load_plan(path: Path) -> tuple[dict[str, object], Path, tuple[int, int]]:
    resolved, raw, owned = read_regular_json(path, "plan")
    value = json.loads(raw)
    require(value.get("schema") == PLAN_SCHEMA, "plan schema mismatch")
    require(value.get("source_sha256") == SOURCE_SHA256,
            "plan is not bound to the supported retail source")
    edits = value.get("edits")
    require(isinstance(edits, list) and edits, "plan has no edits")
    return value, resolved, owned


def relative_target(body: bytes, field: int, label: str) -> int | None:
    """Resolve Visual Concepts' field-local biased signed relative pointer."""

    require(0 <= field <= len(body) - 4, f"{label} pointer field is out of bounds")
    value = struct.unpack_from("<i", body, field)[0]
    if value == 0:
        return None
    target = field + value - 1
    require(0 <= target < len(body),
            f"{label} pointer resolves outside body at 0x{target:x}")
    return target


def utf16z(body: bytes, offset: int, label: str) -> str:
    require(offset % 2 == 0, f"{label} UTF-16 pointer 0x{offset:x} is not aligned")
    limit = min(len(body), offset + MAX_UTF16_BYTES)
    end = offset
    while end + 1 < limit and body[end:end + 2] != b"\0\0":
        end += 2
    require(end + 1 < limit and body[end:end + 2] == b"\0\0",
            f"{label} has no UTF-16 terminator within {MAX_UTF16_BYTES} bytes")
    try:
        value = body[offset:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise WorkflowError(f"{label} is invalid UTF-16LE at 0x{offset:x}") from exc
    require(all(character.isprintable() or character in "\t\r\n"
                for character in value),
            f"{label} contains non-printable UTF-16 text")
    return value


def read_utf16z_span(body: bytes, offset: int, label: str) -> bytes:
    """Return the NUL-terminated UTF-16LE span INCLUDING its terminator."""

    require(offset % 2 == 0, f"{label} span 0x{offset:x} is not aligned")
    limit = min(len(body), offset + MAX_UTF16_BYTES)
    end = offset
    while end + 1 < limit and body[end:end + 2] != b"\0\0":
        end += 2
    require(end + 1 < limit and body[end:end + 2] == b"\0\0",
            f"{label} span is not NUL-terminated")
    return body[offset:end + 2]


def parse_roster_body(body: bytes) -> dict[str, dict[str, int]]:
    """Validate the pinned main ROST preamble/root and resolve every table."""

    require(len(body) == ROST_BODY_SIZE, "main ROST body size changed")
    require(body[:0x0C] == bytes(0x0C) and body[0x0C:0x10] == b"ROST",
            "main ROST inner magic changed")
    require(struct.unpack_from("<I", body, 0x10)[0] == 17,
            "main ROST inner version changed")
    root = relative_target(body, 0x14, "main ROST root")
    require(root == ROST_ROOT_OFFSET, "main ROST root moved")
    require(body[0x18:0x20] == bytes(8), "main ROST reserved preamble changed")
    require(utf16z(body, STRUCTURAL_LABEL_OFFSET, "main ROST label") == "roster",
            "main ROST is not the retail 'roster' resource")
    tables: dict[str, dict[str, int]] = {}
    for name, count_offset, pointer_offset, stride in TABLE_SPECS:
        count = struct.unpack_from("<I", body, root + count_offset)[0]
        pointer = relative_target(body, root + pointer_offset, f"{name} table")
        require(pointer is not None, f"{name} table pointer is null")
        require(pointer + count * stride <= len(body),
                f"{name} table exceeds the ROST body")
        tables[name] = {"offset": pointer, "count": count, "stride": stride,
                        "end": pointer + count * stride}
    coaches = tables["coaches"]
    require((coaches["offset"], coaches["count"], coaches["stride"]) ==
            (COACH_TABLE_OFFSET, COACH_TABLE_COUNT, COACH_STRIDE),
            "main ROST coach table layout changed")
    return tables


def known_string_pointer_references(
    body: bytes, tables: dict[str, dict[str, int]]
) -> dict[int, int]:
    """Count every decoded ROST UTF-16 pointer domain for alias safety.

    Mirrors the domains counted by ``nfl_player_roster_audit`` and the text
    catalog's ``roster_text_reference_counts``: the structural label plus all
    known decoded string pointer fields, resolved live from the body.
    """

    counts: dict[int, int] = {STRUCTURAL_LABEL_OFFSET: 1}
    for table_name, fields in REFERENCE_DOMAINS:
        table = tables[table_name]
        for index in range(table["count"]):
            record = table["offset"] + index * table["stride"]
            for relative in fields:
                target = relative_target(
                    body, record + relative,
                    f"{table_name} {index} +0x{relative:x}",
                )
                if target is not None:
                    counts[target] = counts.get(target, 0) + 1
    return counts


def coach_team_refs(
    body: bytes, tables: dict[str, dict[str, int]]
) -> dict[int, list[int]]:
    refs: dict[int, list[int]] = {}
    teams = tables["teams"]
    coaches = tables["coaches"]
    for index in range(teams["count"]):
        record = teams["offset"] + index * TEAM_STRIDE
        target = relative_target(body, record + TEAM_COACH_POINTER_FIELD,
                                 f"team {index} coach")
        if target is None:
            continue
        require(coaches["offset"] <= target < coaches["end"] and
                (target - coaches["offset"]) % COACH_STRIDE == 0,
                f"team {index} coach pointer is not a coach record")
        refs.setdefault((target - coaches["offset"]) // COACH_STRIDE, []).append(index)
    return refs


def parse_coach_records(
    body: bytes,
    tables: dict[str, dict[str, int]],
    references: dict[int, int],
) -> list[dict[str, object]]:
    table = tables["coaches"]
    records: list[dict[str, object]] = []
    for index in range(table["count"]):
        record_offset = table["offset"] + index * COACH_STRIDE
        record: dict[str, object] = {
            "index": index,
            "record_body_offset": record_offset,
            "identity_code_u16_40": struct.unpack_from(
                "<H", body, record_offset + 0x40)[0],
            "team_indices": [],
        }
        for field, pointer_field in NAME_FIELDS.items():
            target = relative_target(
                body, record_offset + pointer_field, f"coach {index} {field}")
            require(target is not None, f"coach {index} {field} pointer is null")
            record[field] = utf16z(body, target, f"coach {index} {field}")
            record[f"{field}_body_offset"] = target
            record[f"{field}_known_pointer_reference_count"] = references.get(target, 0)
        records.append(record)
    return records


def prepare_name_edit(body: bytes, record: dict[str, object],
                      field: str, value: object) -> dict[str, object]:
    require(field in NAME_FIELDS, f"unsupported field {field!r}")
    require(isinstance(value, str) and value, "name value must be a non-empty string")
    require("\0" not in value, "name value must not contain NUL")
    ref_key = f"{field}_known_pointer_reference_count"
    require(record.get(ref_key) == 1,
            f"{field} for coach {record['index']} is not uniquely referenced")
    pointer_field = NAME_FIELDS[field]
    target = relative_target(
        body, int(record["record_body_offset"]) + pointer_field,
        f"coach {record['index']} {field}")
    require(target == record[f"{field}_body_offset"],
            f"{field} pointer target moved")
    current = read_utf16z_span(body, target, f"coach {record['index']} {field}")
    require(len(current) >= 2 and current[-2:] == b"\0\0",
            f"{field} current span is not NUL-terminated")
    encoded = value.encode("utf-16le") + b"\0\0"
    require(len(encoded) <= len(current),
            f"{field} replacement needs {len(encoded)} bytes but the current "
            f"decoded name span is {len(current)} bytes; longer names need the "
            f"full-allocation writer")
    payload = encoded + b"\0" * (len(current) - len(encoded))
    require(len(payload) == len(current), "name payload must preserve span length")
    changed = [i for i, pair in enumerate(zip(current, payload)) if pair[0] != pair[1]]
    return {
        "field": field,
        "coach_index": record["index"],
        "record_body_offset": record["record_body_offset"],
        "body_string_offset": target,
        "before": current.decode("utf-16le").rstrip("\0"),
        "after": value,
        "allocation_bytes": len(current),
        "before_hex": current.hex(),
        "after_hex": payload.hex(),
        "known_pointer_reference_count": record[ref_key],
        "identity_code_u16_40": record["identity_code_u16_40"],
        "team_indices": record["team_indices"],
        "payload": payload,
        "changed_relative_bytes": changed,
    }


def prepare_edits(
    body_absolute: int,
    body: bytes,
    records: list[dict[str, object]],
    plan: dict[str, object],
) -> tuple[list[dict[str, object]], set[int]]:
    prepared: list[dict[str, object]] = []
    allowed: set[int] = set()
    seen: set[tuple[int, str]] = set()
    for edit in plan["edits"]:
        index = edit.get("coach_index")
        field = edit.get("field")
        require(type(index) is int and 0 <= index < len(records),
                f"coach_index {index!r} is outside the main roster coach table")
        require(field in NAME_FIELDS, f"unsupported field {field!r}")
        key = (index, field)
        require(key not in seen, f"duplicate edit for coach {index} {field}")
        seen.add(key)
        prepped = prepare_name_edit(body, records[index], field, edit.get("value"))
        prepped["xiso_absolute_offset"] = (
            body_absolute + int(prepped["body_string_offset"]))
        prepared.append(prepped)
        allowed.update(prepped["xiso_absolute_offset"] + i
                       for i in prepped["changed_relative_bytes"])
    require(len(allowed) > 0, "plan changes no bytes")
    return prepared, allowed


def run(source_path: Path, output_path: Path, plan_path: Path,
        manifest_path: Path) -> dict[str, object]:
    source, source_fd, source_identity = common.safe_source(source_path)
    output: Path | None = None
    output_fd: int | None = None
    output_identity: tuple[int, int] | None = None
    success = False
    try:
        plan, plan_resolved, plan_identity = load_plan(plan_path)
        source_sha = common.hash_extent(source_fd, 0, IMAGE_SIZE)
        require(source_sha == SOURCE_SHA256, "retail XISO hash changed")
        entries, directory = common.parse_xdvdfs(source_fd, IMAGE_SIZE)
        pack = entries.get("vc_53450030/0")
        xbe = entries.get("default.xbe")
        require(pack is not None and xbe is not None, "required XDVDFS file missing")
        require((pack.sector, pack.size) == (PACK0_SECTOR, PACK0_SIZE),
                "pack 0 extent changed")
        require(common.hash_extent(source_fd, pack.offset, pack.size) == PACK0_SHA256,
                "retail pack 0 hash changed")
        require(common.hash_extent(source_fd, xbe.offset, xbe.size) == XBE_SHA256,
                "retail default.xbe hash changed")
        wrapper = common.pread_exact(source_fd, pack.offset + ROST_OUTER, 0x20)
        require(struct.unpack("<4s7I", wrapper) ==
                (b"ROST", ROST_BODY_SIZE, ROST_BODY_SIZE, 0, 0, 0, 0, 0),
                "main ROST wrapper changed")
        body = common.pread_exact(
            source_fd, pack.offset + ROST_BODY, ROST_BODY_SIZE)
        require(hashlib.sha256(body).hexdigest() == ROST_BODY_SHA256,
                "retail main ROST body hash changed")

        tables = parse_roster_body(body)
        references = known_string_pointer_references(body, tables)
        records = parse_coach_records(body, tables, references)
        team_refs = coach_team_refs(body, tables)
        for index, teams in team_refs.items():
            require(0 <= index < len(records), "team coach reference left the table")
            records[index]["team_indices"] = sorted(teams)

        body_absolute = pack.offset + ROST_BODY
        prepared, allowed = prepare_edits(body_absolute, body, records, plan)

        output, output_fd, output_identity = common.reserve(output_path)
        require(output != source and output_identity != source_identity,
                "output aliases retail source")
        copy_method = common.copy_image(source_fd, output_fd, IMAGE_SIZE)
        for edit in prepared:
            common.pwrite_exact(output_fd, edit["xiso_absolute_offset"], edit["payload"])
        os.fsync(output_fd)
        require(common.identity(output) == output_identity, "output pathname changed")

        source_after, output_sha, differences = common.compare_images(
            source_fd, output_fd, IMAGE_SIZE, allowed
        )
        require(source_after == SOURCE_SHA256, "retail source changed during workflow")
        output_entries, output_directory = common.parse_xdvdfs(output_fd, IMAGE_SIZE)
        require(output_entries == entries and output_directory == directory,
                "XDVDFS tree or extents changed")
        require(common.hash_extent(output_fd, xbe.offset, xbe.size) == XBE_SHA256,
                "default.xbe changed")
        require(set(differences) == allowed,
                "output differs from source at unplanned offsets")
        for edit in prepared:
            readback = common.pread_exact(
                output_fd, edit["xiso_absolute_offset"], len(edit["payload"]))
            require(readback == edit["payload"],
                    f"{edit['field']} patch readback failed")
        require(common.identity(source) == source_identity,
                "retail source pathname changed")
        require(common.identity(output) == output_identity,
                "output pathname changed at closeout")

        serializable = [
            {k: v for k, v in edit.items() if k != "payload"} for edit in prepared
        ]
        result: dict[str, object] = {
            "schema": SCHEMA,
            "source": {
                "path": str(source), "size": IMAGE_SIZE,
                "sha256_before": source_sha, "sha256_after": source_after,
                "opened_read_only": True, "modified": False,
            },
            "output": {
                "path": str(output), "size": os.fstat(output_fd).st_size,
                "sha256": output_sha, "copy_method": copy_method,
                "exclusively_created": True, "distinct_from_source_inode": True,
            },
            "plan": {"path": str(plan_resolved),
                     "sha256": hashlib.sha256(
                         plan_resolved.read_bytes()).hexdigest()},
            "xdvdfs": {
                **directory, "tree_and_extents_identical": True,
                "pack0_sector": pack.sector, "pack0_size": pack.size,
                "default_xbe_sha256": XBE_SHA256,
            },
            "coach_table": {
                "offset": COACH_TABLE_OFFSET, "count": COACH_TABLE_COUNT,
                "stride": COACH_STRIDE,
            },
            "edits": serializable,
            "claims": {
                "edit_count": len(prepared),
                "allowed_changed_byte_count": len(allowed),
                "actual_changed_byte_offsets": sorted(differences),
                "all_other_xiso_bytes_identical": True,
                "layout_identical_copy_only_xiso": True,
                "ownership_contract": (
                    "each edited string allocation is referenced by exactly one "
                    "known decoded ROST pointer"
                ),
                "same_allocation_rule": (
                    "new string plus NUL terminator fits the existing decoded "
                    "span; the remainder is zero-filled"
                ),
                "coach_membership_changed": False,
                "serialized_pointer_modified": False,
                "runtime_visibility_proved": False,
                "xemu_started": False,
                "original_source_modified": False,
                "portme": (
                    "Boot this copied XISO with no loaded roster save, then capture "
                    "roster UI and gameplay before claiming a disc-seed edit is "
                    "visible at runtime. A loaded roster/franchise save may override "
                    "the disc seed."
                ),
            },
        }
        require(not manifest_path.exists(), "manifest already exists")
        common.write_json_exclusive(manifest_path, result)
        success = True
        return result
    finally:
        os.close(source_fd)
        if output_fd is not None:
            os.close(output_fd)
        if (not success and output is not None and output_identity is not None and
                common.identity(output) == output_identity):
            output.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = run(args.source_xiso, args.output_xiso, args.plan, args.manifest)
    except (OSError, WorkflowError, common.WorkflowError, json.JSONDecodeError,
            UnicodeDecodeError) as exc:
        print(f"nfl_coach_roster_name_workflow: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_COACH_ROSTER_NAME_WORKFLOW_OK "
        f"edits={result['claims']['edit_count']} "
        f"changed={result['claims']['allowed_changed_byte_count']} "
        f"sha256={result['output']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
