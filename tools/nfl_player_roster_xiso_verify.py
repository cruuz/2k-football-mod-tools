#!/usr/bin/env python3
"""Independently verify the fixed-size NFL 2K5 player proof XISO.

This verifier does not import the player writer.  It parses both XDVDFS trees,
scans both complete images, reconstructs the expected 14-byte difference set,
checks player/team pointers and fields directly, and audits the manifest.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

import nfl_team_identity_xiso_verify as base


SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
OUTPUT_SHA256 = "e1257a7fbdc8eb19ed7e56459dbea15ba13526b1a11a5bc3d76dd15195b91721"
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
AUDIT_SHA256 = "795336ad0092e6ba6c806e314bb7515ecc0e11103bd889557229f4f1a92451c2"
WORKFLOW_SCHEMA = "nfl2k5_player_roster_xiso_workflow/v1"
AUDIT_SCHEMA = "nfl2k5_player_roster_audit/v1"

IMAGE_SIZE = 6_300_499_968
PACK0_SECTOR = 796_479
PACK0_SIZE = 193_710_080
ROST_OUTER = 0x00392800
ROST_BODY = ROST_OUTER + 0x20
ROST_BODY_SIZE = 593_760
PLAYER_RECORD = 0x157A8
PLAYER_STRIDE = 0x54
FIRST_STRING = 0x7EFDA
LAST_STRING = 0x7EFE4
TEAM18_RECORD = 0x64F0
TEAM18_SLOT = 35
JERSEY_FIELD = 0x20
OLD_WORD = 0x00080818
NEW_WORD = 0x00080950

FIRST_BEFORE = ("Joey" + "\0").encode("utf-16le")
FIRST_AFTER = ("Noah" + "\0").encode("utf-16le")
LAST_BEFORE = ("Harrington" + "\0").encode("utf-16le")
LAST_AFTER = ("CodexProof" + "\0").encode("utf-16le")


class VerifyError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def pointer_target(fd: int, body: int, record: int, field: int) -> int:
    value = struct.unpack("<i", base.pread_exact(fd, body + record + field, 4))[0]
    return record + field + value - 1


def expected_offsets(pack_offset: int) -> tuple[list[dict[str, object]], set[int]]:
    body = pack_offset + ROST_BODY
    rows: list[dict[str, object]] = []
    allowed: set[int] = set()
    for field, relative, before, after in (
        ("first_name", FIRST_STRING, FIRST_BEFORE, FIRST_AFTER),
        ("last_name", LAST_STRING, LAST_BEFORE, LAST_AFTER),
    ):
        changed = [index for index, pair in enumerate(zip(before, after))
                   if pair[0] != pair[1]]
        absolute = body + relative
        allowed.update(absolute + index for index in changed)
        rows.append({"field": field, "absolute": absolute, "changed": changed})
    old = struct.pack("<I", OLD_WORD)
    new = struct.pack("<I", NEW_WORD)
    changed = [index for index, pair in enumerate(zip(old, new)) if pair[0] != pair[1]]
    absolute = body + PLAYER_RECORD + JERSEY_FIELD
    allowed.update(absolute + index for index in changed)
    rows.append({"field": "jersey_number", "absolute": absolute, "changed": changed})
    require(len(allowed) == 14, "expected changed-byte set changed")
    return rows, allowed


def scan_images(
    source_fd: int, output_fd: int, allowed: set[int]
) -> tuple[str, str, list[int]]:
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    differences: list[int] = []
    position = 0
    while position < IMAGE_SIZE:
        size = min(base.CHUNK, IMAGE_SIZE - position)
        before = base.pread_exact(source_fd, position, size)
        after = base.pread_exact(output_fd, position, size)
        source_hash.update(before)
        output_hash.update(after)
        if before != after:
            differences.extend(
                position + index
                for index, pair in enumerate(zip(before, after))
                if pair[0] != pair[1]
            )
            require(len(differences) <= len(allowed),
                    "more bytes changed than expected")
        position += size
    require(set(differences) == allowed, "complete-image difference set mismatch")
    return source_hash.hexdigest(), output_hash.hexdigest(), differences


def virtual_replacements(pack_offset: int) -> dict[int, int]:
    """Return the independently reconstructed proof bytes by absolute offset."""

    body = pack_offset + ROST_BODY
    replacements: dict[int, int] = {}
    for relative, before, after in (
        (FIRST_STRING, FIRST_BEFORE, FIRST_AFTER),
        (LAST_STRING, LAST_BEFORE, LAST_AFTER),
    ):
        require(len(before) == len(after), "fixed-size name proof changed")
        for index, (old, new) in enumerate(zip(before, after)):
            if old != new:
                replacements[body + relative + index] = new
    old_word = struct.pack("<I", OLD_WORD)
    new_word = struct.pack("<I", NEW_WORD)
    for index, (old, new) in enumerate(zip(old_word, new_word)):
        if old != new:
            replacements[body + PLAYER_RECORD + JERSEY_FIELD + index] = new
    require(len(replacements) == 14, "virtual proof byte count changed")
    return replacements


def scan_virtual_output(
    source_fd: int, replacements: dict[int, int], allowed: set[int]
) -> tuple[str, str, list[int]]:
    """Hash the complete logical output without creating a 6.3 GB copy."""

    require(set(replacements) == allowed, "virtual replacement ledger mismatch")
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    differences: list[int] = []
    position = 0
    ordered = sorted(replacements)
    replacement_index = 0
    while position < IMAGE_SIZE:
        size = min(base.CHUNK, IMAGE_SIZE - position)
        before = base.pread_exact(source_fd, position, size)
        source_hash.update(before)
        end = position + size
        chunk_offsets: list[int] = []
        while replacement_index < len(ordered) and ordered[replacement_index] < end:
            absolute = ordered[replacement_index]
            require(absolute >= position, "virtual replacement order changed")
            chunk_offsets.append(absolute)
            replacement_index += 1
        if chunk_offsets:
            after = bytearray(before)
            for absolute in chunk_offsets:
                relative = absolute - position
                require(
                    after[relative] != replacements[absolute],
                    "virtual replacement does not change its source byte",
                )
                after[relative] = replacements[absolute]
                differences.append(absolute)
            output_hash.update(after)
        else:
            output_hash.update(before)
        position = end
    require(replacement_index == len(ordered), "virtual replacement outside image")
    return source_hash.hexdigest(), output_hash.hexdigest(), differences


def virtual_reader(
    source_fd: int, replacements: dict[int, int]
) -> Callable[[int, int], bytes]:
    def read(offset: int, size: int) -> bytes:
        payload = bytearray(base.pread_exact(source_fd, offset, size))
        end = offset + size
        for absolute, value in replacements.items():
            if offset <= absolute < end:
                payload[absolute - offset] = value
        return bytes(payload)

    return read


def validate_audit(raw: bytes) -> str:
    require(hashlib.sha256(raw).hexdigest() == AUDIT_SHA256, "audit hash mismatch")
    value = json.loads(raw)
    require(value.get("schema") == AUDIT_SCHEMA, "audit schema mismatch")
    require(value["safe_fixed_size_proof"]["target"] ==
            "main disc ROST primary_players:512 / Detroit slot 35",
            "audit proof target changed")
    require(value["claims"]["jersey_number_bits_proved"] is True and
            value["claims"]["position_byte_and_enum_proved"] is True and
            value["claims"]["runtime_visibility_proved"] is False,
            "audit claim boundary changed")
    return AUDIT_SHA256


def validate_structures(
    source_fd: int, read_output: Callable[[int, int], bytes], pack: base.Entry
) -> None:
    require(base.hash_extent(source_fd, pack.offset, pack.size) == PACK0_SHA256,
            "retail pack 0 hash mismatch")
    body = pack.offset + ROST_BODY
    source_wrapper = base.pread_exact(source_fd, pack.offset + ROST_OUTER, 0x20)
    output_wrapper = read_output(pack.offset + ROST_OUTER, 0x20)
    require(source_wrapper == output_wrapper, "ROST wrapper changed")
    require(struct.unpack("<4s7I", source_wrapper) ==
            (b"ROST", ROST_BODY_SIZE, ROST_BODY_SIZE, 0, 0, 0, 0, 0),
            "ROST wrapper values changed")

    require(base.pread_exact(source_fd, body + FIRST_STRING, len(FIRST_BEFORE)) ==
            FIRST_BEFORE, "source first name mismatch")
    require(read_output(body + FIRST_STRING, len(FIRST_AFTER)) ==
            FIRST_AFTER, "output first name mismatch")
    require(base.pread_exact(source_fd, body + LAST_STRING, len(LAST_BEFORE)) ==
            LAST_BEFORE, "source last name mismatch")
    require(read_output(body + LAST_STRING, len(LAST_AFTER)) ==
            LAST_AFTER, "output last name mismatch")
    output_record = read_output(body + PLAYER_RECORD, PLAYER_STRIDE)
    output_first_pointer = struct.unpack_from("<i", output_record, 0x10)[0]
    output_last_pointer = struct.unpack_from("<i", output_record, 0x14)[0]
    require(pointer_target(source_fd, body, PLAYER_RECORD, 0x10) ==
            PLAYER_RECORD + 0x10 + output_first_pointer - 1 == FIRST_STRING,
            "first-name pointer changed")
    require(pointer_target(source_fd, body, PLAYER_RECORD, 0x14) ==
            PLAYER_RECORD + 0x14 + output_last_pointer - 1 == LAST_STRING,
            "last-name pointer changed")

    source_record = base.pread_exact(source_fd, body + PLAYER_RECORD, PLAYER_STRIDE)
    expected = bytearray(source_record)
    struct.pack_into("<I", expected, JERSEY_FIELD, NEW_WORD)
    require(output_record == bytes(expected), "player record has unrelated changes")
    require(struct.unpack_from("<I", source_record, JERSEY_FIELD)[0] == OLD_WORD and
            struct.unpack_from("<I", output_record, JERSEY_FIELD)[0] == NEW_WORD,
            "jersey word mismatch")
    require(((OLD_WORD >> 3) & 0x7F, (NEW_WORD >> 3) & 0x7F) == (3, 42),
            "jersey decode mismatch")
    require((OLD_WORD & ~0x3F8) == (NEW_WORD & ~0x3F8),
            "unrelated jersey-word bits changed")
    require(source_record[0x35] == output_record[0x35] == 0,
            "position code changed")
    require(source_record[0x06:0x08] == output_record[0x06:0x08] ==
            struct.pack("<H", 3593), "face ID changed")

    source_team = base.pread_exact(source_fd, body + TEAM18_RECORD, 0x1F4)
    output_team = read_output(body + TEAM18_RECORD, 0x1F4)
    require(source_team == output_team, "Detroit team record changed")
    require(source_team[0x11C] == 53, "Detroit roster count changed")
    output_team_pointer = struct.unpack_from("<i", output_team, TEAM18_SLOT * 4)[0]
    require(pointer_target(source_fd, body, TEAM18_RECORD, TEAM18_SLOT * 4) ==
            TEAM18_RECORD + TEAM18_SLOT * 4 + output_team_pointer - 1 == PLAYER_RECORD,
            "Detroit slot 35 changed")


def validate_manifest(
    raw: bytes, source: Path, output: Path, audit_sha: str,
    differences: list[int], rows: list[dict[str, object]],
) -> str:
    value = json.loads(raw)
    require(value.get("schema") == WORKFLOW_SCHEMA, "manifest schema mismatch")
    require(Path(value["source"]["path"]).resolve() == source and
            Path(value["output"]["path"]).resolve() == output,
            "manifest path mismatch")
    require(value["source"]["sha256_before"] == SOURCE_SHA256 and
            value["source"]["sha256_after"] == SOURCE_SHA256 and
            value["source"]["modified"] is False,
            "manifest source state mismatch")
    require(value["output"]["sha256"] == OUTPUT_SHA256,
            "manifest output hash mismatch")
    require(value["audit"]["sha256"] == audit_sha, "manifest audit hash mismatch")
    proof = value["proof"]
    require(proof["player_pool"] == "primary_players" and
            proof["player_index"] == 512 and
            proof["detroit_team_index"] == 18 and
            proof["detroit_roster_slot"] == 35 and
            proof["detroit_roster_count_before_after"] == 53,
            "manifest proof selection changed")
    require(proof["before_display"] == "Joey Harrington #3 QB" and
            proof["after_display"] == "Noah CodexProof #42 QB" and
            proof["face_id_before_after"] == 3593 and
            proof["position_code_before_after"] == 0,
            "manifest proof identity changed")
    require(proof["actual_changed_byte_count"] == 14 and
            proof["actual_changed_byte_offsets"] == differences and
            proof["allowed_changed_byte_offsets"] == differences,
            "manifest changed-byte ledger mismatch")
    require([item["xiso_absolute_offset"] for item in proof["edits"]] ==
            [item["absolute"] for item in rows], "manifest edit offsets changed")
    claims = value["claims"]
    require(claims == {
        "face_id_changed": False,
        "fixed_size_player_identity_and_number_edit_proved": True,
        "layout_identical_copy_only_xiso": True,
        "original_source_modified": False,
        "portme": "Boot this copied XISO with no loaded roster save, then capture roster UI and gameplay before claiming the disc-seed edit is visible at runtime.",
        "position_changed": False,
        "roster_membership_changed": False,
        "runtime_visibility_proved": False,
        "save_container_modified": False,
        "title_executed": False,
        "xemu_started": False,
    }, "manifest claim boundary changed")
    return hashlib.sha256(raw).hexdigest()


def run(
    source_path: Path, output_path: Path, manifest_path: Path, audit_path: Path,
    *, virtual_output: bool = False,
) -> dict[str, object]:
    audit_resolved, audit_raw, audit_identity = base.read_regular_bytes(
        audit_path, "audit"
    )
    manifest_resolved, manifest_raw, manifest_identity = base.read_regular_bytes(
        manifest_path, "manifest"
    )
    audit_sha = validate_audit(audit_raw)
    source, source_fd = base.open_regular(source_path)
    output_fd: int | None = None
    try:
        if virtual_output:
            require(
                not os.path.lexists(output_path),
                "virtual output path must be absent",
            )
            output = output_path.expanduser().resolve(strict=False)
        else:
            output, output_fd = base.open_regular(output_path)
        require(source != output, "source and output paths match")
        require(os.fstat(source_fd).st_size == IMAGE_SIZE, "source XISO size mismatch")
        if output_fd is not None:
            require(os.fstat(output_fd).st_size == IMAGE_SIZE, "output XISO size mismatch")
        source_entries, source_directory = base.parse_xdvdfs(source_fd)
        pack = source_entries.get("vc_53450030/0")
        xbe = source_entries.get("default.xbe")
        require(pack is not None and xbe is not None, "required XDVDFS file missing")
        require((pack.sector, pack.size) == (PACK0_SECTOR, PACK0_SIZE),
                "pack 0 extent mismatch")
        rows, allowed = expected_offsets(pack.offset)
        if output_fd is None:
            replacements = virtual_replacements(pack.offset)
            require(
                all(pack.offset <= absolute < pack.offset + pack.size for absolute in allowed),
                "virtual replacement escaped pack 0",
            )
            read_output = virtual_reader(source_fd, replacements)
            source_hash, output_hash, differences = scan_virtual_output(
                source_fd, replacements, allowed
            )
        else:
            output_entries, output_directory = base.parse_xdvdfs(output_fd)
            require(
                source_entries == output_entries and source_directory == output_directory,
                "XDVDFS trees differ",
            )
            read_output = lambda offset, size: base.pread_exact(
                output_fd, offset, size
            )
            source_hash, output_hash, differences = scan_images(
                source_fd, output_fd, allowed
            )
        require(base.hash_extent(source_fd, xbe.offset, xbe.size) == XBE_SHA256,
                "default.xbe has wrong hash")
        require(
            read_output(xbe.offset, xbe.size) == base.pread_exact(
                source_fd, xbe.offset, xbe.size
            ),
            "default.xbe differs",
        )
        require(source_hash == SOURCE_SHA256, "retail XISO hash mismatch")
        require(output_hash == OUTPUT_SHA256, "proof XISO hash mismatch")
        validate_structures(source_fd, read_output, pack)
        manifest_sha = validate_manifest(
            manifest_raw, source, output, audit_sha, differences, rows
        )
        require((audit_resolved.stat().st_dev, audit_resolved.stat().st_ino) ==
                audit_identity, "audit pathname changed during verification")
        require((manifest_resolved.stat().st_dev, manifest_resolved.stat().st_ino) ==
                manifest_identity, "manifest pathname changed during verification")
        return {
            "source_sha256": source_hash,
            "output_sha256": output_hash,
            "manifest_sha256": manifest_sha,
            "changed_bytes": len(differences),
            "xdvdfs_identical": True,
            "default_xbe_unchanged": True,
            "player": "Noah CodexProof",
            "jersey": 42,
            "runtime_visibility": False,
        }
    finally:
        os.close(source_fd)
        if output_fd is not None:
            os.close(output_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument(
        "--virtual-output", action="store_true",
        help="verify the absent historical output by independently overlaying its 14 bytes",
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--audit", type=Path,
        default=Path("reports/assets/nfl2k5_player_roster_audit.json"),
    )
    args = parser.parse_args(argv)
    try:
        result = run(
            args.source_xiso, args.output_xiso, args.manifest, args.audit,
            virtual_output=args.virtual_output,
        )
    except (OSError, VerifyError, base.VerifyError, json.JSONDecodeError) as exc:
        print(f"nfl_player_roster_xiso_verify: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_PLAYER_ROSTER_XISO_VERIFY_PASS "
        f"changed={result['changed_bytes']} "
        f"player={result['player'].replace(' ', '_')} "
        f"jersey={result['jersey']} "
        f"xdvdfs_identical={str(result['xdvdfs_identical']).lower()} "
        f"runtime={str(result['runtime_visibility']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
