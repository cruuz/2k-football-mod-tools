#!/usr/bin/env python3
"""Create a copied NFL 2K5 XISO with one fixed-size player proof edit.

The pinned proof changes main-disc player ``Joey Harrington #3`` to
``Noah CodexProof #42``.  It preserves every pointer, team roster slot/count,
position, face/head ID, unrelated player bit, XDVDFS extent, and ``default.xbe``.
The retail source is opened read-only and is never rewritten.
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


SCHEMA = "nfl2k5_player_roster_xiso_workflow/v1"
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

PLAYER_RECORD = 0x157A8
PLAYER_STRIDE = 0x54
FIRST_POINTER_FIELD = 0x10
LAST_POINTER_FIELD = 0x14
FIRST_STRING = 0x7EFDA
LAST_STRING = 0x7EFE4
JERSEY_WORD_FIELD = 0x20
JERSEY_MASK = 0x3F8
JERSEY_SHIFT = 3
OLD_JERSEY = 3
NEW_JERSEY = 42
OLD_JERSEY_WORD = 0x00080818
NEW_JERSEY_WORD = 0x00080950
TEAM18_RECORD = 0x64F0
TEAM18_SLOT = 35
TEAM18_COUNT_FIELD = 0x11C


class WorkflowError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowError(message)


def utf16(value: str) -> bytes:
    return (value + "\0").encode("utf-16le")


FIRST_BEFORE = utf16("Joey")
FIRST_AFTER = utf16("Noah")
LAST_BEFORE = utf16("Harrington")
LAST_AFTER = utf16("CodexProof")


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


def validate_audit(path: Path) -> tuple[str, Path, tuple[int, int]]:
    resolved, raw, owned = read_regular_json(path, "audit report")
    value = json.loads(raw)
    require(value.get("schema") == AUDIT_SCHEMA, "player audit schema mismatch")
    require(value["summary"] == {
        "player_count": 2547,
        "position_count": 17,
        "primary_player_count": 2479,
        "promoted_stable_rating_count": 3,
        "proof_jersey": "3 -> 42",
        "proof_player": "Joey Harrington -> Noah CodexProof",
        "rating_ui_binding_count": 204,
        "secondary_player_count": 68,
        "team_count": 52,
    }, "player audit summary changed")
    proof = value["safe_fixed_size_proof"]
    require(proof["record_body_offset"] == PLAYER_RECORD and
            proof["first_name_body_offset"] == FIRST_STRING and
            proof["last_name_body_offset"] == LAST_STRING,
            "player audit proof offsets changed")
    require(proof["before"] == {
        "face_id": 3593, "first_name": "Joey", "jersey_number": 3,
        "last_name": "Harrington", "position": "QB", "team_indices": [18],
    }, "player audit before-state changed")
    require(proof["after"] == {
        "face_id": 3593, "first_name": "Noah", "jersey_number": 42,
        "last_name": "CodexProof", "position": "QB", "team_indices": [18],
    }, "player audit after-state changed")
    require(value["claims"]["runtime_visibility_proved"] is False and
            value["claims"]["originals_modified"] is False,
            "player audit claim boundary changed")
    return hashlib.sha256(raw).hexdigest(), resolved, owned


def resolve_pointer(fd: int, body_absolute: int, record_relative: int, field: int) -> int:
    value = struct.unpack(
        "<i", common.pread_exact(fd, body_absolute + record_relative + field, 4)
    )[0]
    return record_relative + field + value - 1


def expected_edits(body_absolute: int) -> tuple[list[dict[str, object]], set[int]]:
    rows: list[dict[str, object]] = []
    allowed: set[int] = set()
    for field, body_offset, before, after in (
        ("first_name", FIRST_STRING, FIRST_BEFORE, FIRST_AFTER),
        ("last_name", LAST_STRING, LAST_BEFORE, LAST_AFTER),
    ):
        require(len(before) == len(after), f"{field} allocation size changed")
        changed = [index for index, pair in enumerate(zip(before, after))
                   if pair[0] != pair[1]]
        absolute = body_absolute + body_offset
        allowed.update(absolute + index for index in changed)
        rows.append({
            "field": field,
            "body_offset": body_offset,
            "xiso_absolute_offset": absolute,
            "before": "Joey" if field == "first_name" else "Harrington",
            "after": "Noah" if field == "first_name" else "CodexProof",
            "allocation_bytes": len(before),
            "before_hex": before.hex(),
            "after_hex": after.hex(),
            "changed_relative_bytes": changed,
        })
    before_word = struct.pack("<I", OLD_JERSEY_WORD)
    after_word = struct.pack("<I", NEW_JERSEY_WORD)
    changed = [index for index, pair in enumerate(zip(before_word, after_word))
               if pair[0] != pair[1]]
    absolute = body_absolute + PLAYER_RECORD + JERSEY_WORD_FIELD
    allowed.update(absolute + index for index in changed)
    rows.append({
        "field": "jersey_number",
        "body_offset": PLAYER_RECORD + JERSEY_WORD_FIELD,
        "xiso_absolute_offset": absolute,
        "before": OLD_JERSEY,
        "after": NEW_JERSEY,
        "before_word": f"0x{OLD_JERSEY_WORD:08x}",
        "after_word": f"0x{NEW_JERSEY_WORD:08x}",
        "mask": "0x000003f8",
        "changed_relative_bytes": changed,
    })
    require(len(allowed) == 14, "proof changed-byte count changed")
    return rows, allowed


def validate_source(
    fd: int, pack: common.Entry
) -> tuple[int, list[dict[str, object]], set[int], bytes, bytes]:
    require((pack.sector, pack.size) == (PACK0_SECTOR, PACK0_SIZE),
            "pack 0 extent changed")
    require(common.hash_extent(fd, pack.offset, pack.size) == PACK0_SHA256,
            "retail pack 0 hash changed")
    wrapper = common.pread_exact(fd, pack.offset + ROST_OUTER, 0x20)
    require(struct.unpack("<4s7I", wrapper) ==
            (b"ROST", ROST_BODY_SIZE, ROST_BODY_SIZE, 0, 0, 0, 0, 0),
            "main ROST wrapper changed")
    body = pack.offset + ROST_BODY
    record = body + PLAYER_RECORD
    before_record = common.pread_exact(fd, record, PLAYER_STRIDE)
    require(resolve_pointer(fd, body, PLAYER_RECORD, FIRST_POINTER_FIELD) == FIRST_STRING,
            "first-name pointer target changed")
    require(resolve_pointer(fd, body, PLAYER_RECORD, LAST_POINTER_FIELD) == LAST_STRING,
            "last-name pointer target changed")
    require(common.pread_exact(fd, body + FIRST_STRING, len(FIRST_BEFORE)) == FIRST_BEFORE,
            "retail proof first name changed")
    require(common.pread_exact(fd, body + LAST_STRING, len(LAST_BEFORE)) == LAST_BEFORE,
            "retail proof last name changed")
    word = struct.unpack_from("<I", before_record, JERSEY_WORD_FIELD)[0]
    require(word == OLD_JERSEY_WORD and ((word >> JERSEY_SHIFT) & 0x7F) == OLD_JERSEY,
            "retail proof jersey word changed")
    computed = (word & ~JERSEY_MASK) | ((NEW_JERSEY & 0x7F) << JERSEY_SHIFT)
    require(computed == NEW_JERSEY_WORD and
            (computed & ~JERSEY_MASK) == (word & ~JERSEY_MASK),
            "jersey masked edit does not preserve unrelated bits")
    require(struct.unpack_from("<H", before_record, 0x06)[0] == 3593,
            "proof face ID changed")
    require(before_record[0x35] == 0, "proof position changed")

    team = body + TEAM18_RECORD
    before_team = common.pread_exact(fd, team, common.ROST_TEAM_STRIDE)
    require(before_team[TEAM18_COUNT_FIELD] == 53, "Detroit roster count changed")
    target = resolve_pointer(fd, body, TEAM18_RECORD, TEAM18_SLOT * 4)
    require(target == PLAYER_RECORD, "Detroit slot 35 no longer selects proof player")
    edits, allowed = expected_edits(body)
    return body, edits, allowed, before_record, before_team


def run(
    source_path: Path, output_path: Path, manifest_path: Path, audit_path: Path
) -> dict[str, object]:
    source, source_fd, source_identity = common.safe_source(source_path)
    output: Path | None = None
    output_fd: int | None = None
    output_identity: tuple[int, int] | None = None
    success = False
    try:
        audit_sha, audit_resolved, audit_identity = validate_audit(audit_path)
        source_sha = common.hash_extent(source_fd, 0, IMAGE_SIZE)
        require(source_sha == SOURCE_SHA256, "retail XISO hash changed")
        entries, directory = common.parse_xdvdfs(source_fd, IMAGE_SIZE)
        pack = entries.get("vc_53450030/0")
        xbe = entries.get("default.xbe")
        require(pack is not None and xbe is not None, "required XDVDFS file missing")
        require(common.hash_extent(source_fd, xbe.offset, xbe.size) == XBE_SHA256,
                "retail default.xbe hash changed")
        body, edits, allowed, before_record, before_team = validate_source(source_fd, pack)

        output, output_fd, output_identity = common.reserve(output_path)
        require(output != source and output_identity != source_identity,
                "output aliases retail source")
        copy_method = common.copy_image(source_fd, output_fd, IMAGE_SIZE)
        common.pwrite_exact(output_fd, body + FIRST_STRING, FIRST_AFTER)
        common.pwrite_exact(output_fd, body + LAST_STRING, LAST_AFTER)
        common.pwrite_exact(
            output_fd, body + PLAYER_RECORD + JERSEY_WORD_FIELD,
            struct.pack("<I", NEW_JERSEY_WORD),
        )
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
        require(common.pread_exact(output_fd, pack.offset + ROST_OUTER, 0x20) ==
                common.pread_exact(source_fd, pack.offset + ROST_OUTER, 0x20),
                "ROST wrapper changed")
        require(common.pread_exact(output_fd, body + FIRST_STRING, len(FIRST_AFTER)) ==
                FIRST_AFTER, "first-name patch readback failed")
        require(common.pread_exact(output_fd, body + LAST_STRING, len(LAST_AFTER)) ==
                LAST_AFTER, "last-name patch readback failed")
        after_record = common.pread_exact(output_fd, body + PLAYER_RECORD, PLAYER_STRIDE)
        expected_record = bytearray(before_record)
        struct.pack_into("<I", expected_record, JERSEY_WORD_FIELD, NEW_JERSEY_WORD)
        require(after_record == bytes(expected_record),
                "proof player record contains an unrelated change")
        require(after_record[0x35] == before_record[0x35] == 0 and
                after_record[0x06:0x08] == before_record[0x06:0x08],
                "position or face ID changed")
        require(common.pread_exact(output_fd, body + TEAM18_RECORD, common.ROST_TEAM_STRIDE) ==
                before_team, "Detroit team pointers/count/scalars changed")
        require(resolve_pointer(output_fd, body, TEAM18_RECORD, TEAM18_SLOT * 4) ==
                PLAYER_RECORD, "output Detroit slot 35 changed")
        require((audit_resolved.stat().st_dev, audit_resolved.stat().st_ino) ==
                audit_identity, "audit pathname changed during workflow")

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
            "audit": {"path": str(audit_resolved), "sha256": audit_sha},
            "xdvdfs": {
                **directory, "tree_and_extents_identical": True,
                "pack0_sector": pack.sector, "pack0_size": pack.size,
                "default_xbe_sha256": XBE_SHA256,
            },
            "proof": {
                "player_pool": "primary_players", "player_index": 512,
                "player_record_body_offset": PLAYER_RECORD,
                "detroit_team_index": 18, "detroit_roster_slot": TEAM18_SLOT,
                "detroit_roster_count_before_after": 53,
                "before_display": "Joey Harrington #3 QB",
                "after_display": "Noah CodexProof #42 QB",
                "face_id_before_after": 3593,
                "position_code_before_after": 0,
                "edits": edits,
                "all_serialized_pointers_unchanged": True,
                "allowed_changed_byte_offsets": sorted(allowed),
                "actual_changed_byte_offsets": differences,
                "actual_changed_byte_count": len(differences),
                "all_other_xiso_bytes_identical": True,
            },
            "claims": {
                "fixed_size_player_identity_and_number_edit_proved": True,
                "layout_identical_copy_only_xiso": True,
                "roster_membership_changed": False,
                "position_changed": False,
                "face_id_changed": False,
                "runtime_visibility_proved": False,
                "xemu_started": False,
                "title_executed": False,
                "save_container_modified": False,
                "original_source_modified": False,
                "portme": (
                    "Boot this copied XISO with no loaded roster save, then capture roster UI "
                    "and gameplay before claiming the disc-seed edit is visible at runtime."
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
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--audit", type=Path,
        default=Path("reports/assets/nfl2k5_player_roster_audit.json"),
    )
    args = parser.parse_args(argv)
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest, args.audit)
    except (OSError, WorkflowError, common.WorkflowError, json.JSONDecodeError) as exc:
        print(f"nfl_player_roster_xiso_workflow: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_PLAYER_ROSTER_XISO_WORKFLOW_OK "
        f"changed={result['proof']['actual_changed_byte_count']} "
        f"sha256={result['output']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
