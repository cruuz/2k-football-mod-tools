#!/usr/bin/env python3
"""Create a copied NFL 2K5 XISO applying a plan of fixed-size roster edits.

This generalizes the single-fixture ``nfl_player_roster_xiso_workflow.py``
proof (Joey Harrington #3 -> Noah CodexProof #42) to a plan of edits over BOTH
roster pools:

* ``jersey_number`` — the proved masked field (``+0x20`` bits 3..9).  Available
  for primary AND secondary players; unrelated word bits are preserved.
* ``first_name`` / ``last_name`` — a same-allocation UTF-16LE edit.  Available
  for primary players whose name is uniquely referenced.  The replacement must
  fit inside the current decoded name span (up to and including its NUL
  terminator); the remainder of that span is zero-filled.  Secondary-pool name
  allocations are zero-capacity (empty placeholder players) and are refused.

Every pointer, team roster slot/count, position, face/head ID, unrelated player
bit, XDVDFS extent, and ``default.xbe`` is preserved.  The retail source is
opened read-only and is never rewritten.  The output is created exclusively and
must differ from the source only at the planned byte offsets.
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

import nfl_team_identity_xiso_workflow as common

SCHEMA = "nfl2k5_player_roster_general_workflow/v1"
PLAN_SCHEMA = "nfl2k5_player_roster_general_plan/v1"
AUDIT_SCHEMA = "nfl2k5_player_roster_audit/v1"
SOURCE_SHA256 = common.SOURCE_SHA256
PACK0_SHA256 = common.PACK0_SHA256
XBE_SHA256 = common.XBE_SHA256
IMAGE_SIZE = common.IMAGE_SIZE
PACK0_SECTOR = common.PACK0_SECTOR
PACK0_SIZE = common.PACK0_SIZE
ROST_OUTER = common.ROST_OUTER_OFFSET
ROST_BODY = ROST_OUTER + common.ROST_WRAPPER_SIZE
ROST_BODY_SIZE = common.ROST_BODY_SIZE

PLAYER_STRIDE = 0x54
FIRST_POINTER_FIELD = 0x10
LAST_POINTER_FIELD = 0x14
JERSEY_WORD_FIELD = 0x20
JERSEY_MASK = 0x3F8
JERSEY_SHIFT = 3

POOL_LAYOUT = {
    "primary_players": {"offset": 44968, "count": 2479},
    "secondary_players": {"offset": 253204, "count": 68},
}
NAME_FIELDS = {"first_name": FIRST_POINTER_FIELD, "last_name": LAST_POINTER_FIELD}


class WorkflowError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowError(message)


def read_regular_json(path: Path, label: str) -> tuple[Path, bytes, tuple[int, int]]:
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode), f"{label} must not be a symlink")
    resolved = path.resolve(strict=True)
    fd = os.open(resolved, os.O_NOFOLLOW | os.O_RDONLY)
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


def load_audit(path: Path) -> tuple[dict[str, object], str, Path, tuple[int, int]]:
    resolved, raw, owned = read_regular_json(path, "audit report")
    value = json.loads(raw)
    require(value.get("schema") == AUDIT_SCHEMA, "player audit schema mismatch")
    require(value["layout"]["primary_players"] ==
            {"count": 2479, "offset": 44968, "stride": 84},
            "primary layout changed")
    require(value["layout"]["secondary_players"] ==
            {"count": 68, "offset": 253204, "stride": 84},
            "secondary layout changed")
    return value, hashlib.sha256(raw).hexdigest(), resolved, owned


def load_plan(path: Path) -> tuple[dict[str, object], Path, tuple[int, int]]:
    resolved, raw, owned = read_regular_json(path, "plan")
    value = json.loads(raw)
    require(value.get("schema") == PLAN_SCHEMA, "plan schema mismatch")
    require(value.get("source_sha256") == SOURCE_SHA256,
            "plan is not bound to the supported retail source")
    edits = value.get("edits")
    require(isinstance(edits, list) and edits, "plan has no edits")
    return value, resolved, owned


def player_record(audit: dict[str, object], pool: str, index: int) -> dict[str, object]:
    layout = POOL_LAYOUT.get(pool)
    require(layout is not None, f"unknown pool {pool!r}")
    require(isinstance(index, int) and 0 <= index < layout["count"],
            f"{pool} index {index} out of range")
    for row in audit["players"]:
        if row["pool"] == pool and row["index"] == index:
            return row
    raise WorkflowError(f"{pool} index {index} missing from audit")


def resolve_pointer(fd: int, body_absolute: int, record_relative: int, field: int) -> int:
    value = struct.unpack(
        "<i", common.pread_exact(fd, body_absolute + record_relative + field, 4)
    )[0]
    return record_relative + field + value - 1


def read_utf16z(fd: int, absolute: int, maximum: int = 256) -> bytes:
    """Read a NUL-terminated UTF-16LE string INCLUDING its terminator."""
    raw = common.pread_exact(fd, absolute, maximum)
    for end in range(2, len(raw) + 1, 2):
        if raw[end - 2:end] == b"\0\0":
            return raw[:end]
    raise WorkflowError("unterminated UTF-16 string in roster name span")


def prepare_jersey_edit(fd: int, body: int, record: dict[str, object],
                        value: object) -> dict[str, object]:
    require(isinstance(value, int) and 0 <= value <= 99,
            "jersey_number must be an integer 0..99")
    record_offset = record["record_body_offset"]
    absolute = body + record_offset + JERSEY_WORD_FIELD
    word = struct.unpack("<I", common.pread_exact(fd, absolute, 4))[0]
    new_word = (word & ~JERSEY_MASK) | ((value & 0x7F) << JERSEY_SHIFT)
    require((new_word & ~JERSEY_MASK) == (word & ~JERSEY_MASK),
            "jersey edit would change unrelated word bits")
    before = struct.pack("<I", word)
    after = struct.pack("<I", new_word)
    changed = [i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    return {
        "field": "jersey_number",
        "pool": record["pool"],
        "player_index": record["index"],
        "xiso_absolute_offset": absolute,
        "before": (word >> JERSEY_SHIFT) & 0x7F,
        "after": value,
        "before_word": f"0x{word:08x}",
        "after_word": f"0x{new_word:08x}",
        "payload": after,
        "changed_relative_bytes": [absolute + i for i in changed],
    }


def prepare_name_edit(fd: int, body: int, record: dict[str, object],
                      field: str, value: object) -> dict[str, object]:
    require(record["pool"] == "primary_players",
            "secondary-pool name allocations are zero-capacity and not writable")
    require(isinstance(value, str) and value, "name value must be a non-empty string")
    require("\0" not in value, "name value must not contain NUL")
    ref_key = f"{field}_known_pointer_reference_count"
    require(record.get(ref_key) == 1,
            f"{field} for {record['pool']} {record['index']} is not uniquely referenced")
    pointer_field = NAME_FIELDS[field]
    record_offset = record["record_body_offset"]
    target = resolve_pointer(fd, body, record_offset, pointer_field)
    require(target == record[f"{field}_body_offset"],
            f"{field} pointer target moved")
    absolute = body + target
    current = read_utf16z(fd, absolute)
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
        "pool": record["pool"],
        "player_index": record["index"],
        "xiso_absolute_offset": absolute,
        "before": current.decode("utf-16le").rstrip("\0"),
        "after": value,
        "allocation_bytes": len(current),
        "before_hex": current.hex(),
        "after_hex": payload.hex(),
        "payload": payload,
        "changed_relative_bytes": [absolute + i for i in changed],
    }


def prepare_edits(fd: int, body: int, audit: dict[str, object],
                  plan: dict[str, object]) -> tuple[list[dict[str, object]], set[int]]:
    prepared: list[dict[str, object]] = []
    allowed: set[int] = set()
    seen: set[tuple[str, int, str]] = set()
    for edit in plan["edits"]:
        pool = edit.get("pool")
        index = edit.get("player_index")
        field = edit.get("field")
        key = (pool, index, field)
        require(key not in seen, f"duplicate edit for {key}")
        seen.add(key)
        record = player_record(audit, pool, index)
        if field == "jersey_number":
            prepped = prepare_jersey_edit(fd, body, record, edit.get("value"))
        elif field in NAME_FIELDS:
            prepped = prepare_name_edit(fd, body, record, field, edit.get("value"))
        else:
            raise WorkflowError(f"unsupported field {field!r}")
        prepared.append(prepped)
        allowed.update(prepped["changed_relative_bytes"])
    require(len(allowed) > 0, "plan changes no bytes")
    return prepared, allowed


def run(source_path: Path, output_path: Path, plan_path: Path,
        audit_path: Path, manifest_path: Path) -> dict[str, object]:
    source, source_fd, source_identity = common.safe_source(source_path)
    output: Path | None = None
    output_fd: int | None = None
    output_identity: tuple[int, int] | None = None
    success = False
    try:
        audit, audit_sha, audit_resolved, audit_identity = load_audit(audit_path)
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
        body = pack.offset + ROST_BODY

        prepared, allowed = prepare_edits(source_fd, body, audit, plan)

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
        require((audit_resolved.stat().st_dev, audit_resolved.stat().st_ino) ==
                audit_identity, "audit pathname changed during workflow")

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
            "audit": {"path": str(audit_resolved), "sha256": audit_sha},
            "xdvdfs": {
                **directory, "tree_and_extents_identical": True,
                "pack0_sector": pack.sector, "pack0_size": pack.size,
                "default_xbe_sha256": XBE_SHA256,
            },
            "edits": serializable,
            "claims": {
                "edit_count": len(prepared),
                "allowed_changed_byte_count": len(allowed),
                "actual_changed_byte_offsets": sorted(differences),
                "all_other_xiso_bytes_identical": True,
                "layout_identical_copy_only_xiso": True,
                "roster_membership_changed": False,
                "position_changed": False,
                "face_id_changed": False,
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
        require(common.identity(source) == source_identity,
                "retail source pathname changed")
        require(common.identity(output) == output_identity,
                "output pathname changed at closeout")
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
    parser.add_argument(
        "--audit", type=Path,
        default=Path("reports/assets/nfl2k5_player_roster_audit.json"),
    )
    args = parser.parse_args(argv)
    try:
        result = run(args.source_xiso, args.output_xiso, args.plan,
                     args.audit, args.manifest)
    except (OSError, WorkflowError, common.WorkflowError, json.JSONDecodeError) as exc:
        print(f"nfl_player_roster_general_workflow: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_PLAYER_ROSTER_GENERAL_WORKFLOW_OK "
        f"edits={result['claims']['edit_count']} "
        f"changed={result['claims']['allowed_changed_byte_count']} "
        f"sha256={result['output']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
