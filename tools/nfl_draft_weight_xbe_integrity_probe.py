#!/usr/bin/env python3
"""Probe the exact NFL 2K5 draft-weight XBE integrity boundary in memory.

The probe pins the retail executable and the gameplay-tuning audit, verifies
the 17-float table and its owning XBE section, then evaluates one deterministic
hypothetical edit two ways.  It never creates or modifies an XBE.  The result
shows why changing only the table leaves a stale section digest, while updating
that digest changes bytes covered by the existing RSA-signed header.
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
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "nfl2k5_draft_weight_xbe_integrity_probe/v1"
XBE = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
AUDIT = ROOT / "reports/gameplay_tuning/gameplay_tuning_ai_draft_audit.json"
XBE_SIZE = 11_948_032
XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
AUDIT_SIZE = 53_996
AUDIT_SHA256 = "c53522ee0f4151291f154720a1d457ff7368fb256fbf5845561f4ad68289524b"
TABLE_VA = 0x00589588
TABLE_OFFSET = 0x0057EAA8
TABLE_SIZE = 17 * 4
TABLE_SHA256 = "bf53338927a98ffc13f5c591d8cdc216f16691975ef9f27144fdad98f282098e"
POSITIONS = (
    "QB", "K", "P", "WR", "CB", "FS", "SS", "RB", "FB",
    "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE",
)
EXPECTED_WEIGHTS = (
    2.0, 0.1, 0.2, 1.4, 1.0, 1.1, 1.1, 1.7, 1.0,
    1.2, 1.2, 0.7, 0.5, 1.1, 1.3, 1.4, 1.3,
)


class ProbeError(ValueError):
    """An input or invariant differs from the exact audited boundary."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeError(message)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def xbe_sha1(payload: bytes) -> str:
    """XBE section/header digest: LE byte length followed by the raw bytes."""

    framed = struct.pack("<I", len(payload)) + payload
    return hashlib.sha1(framed).hexdigest()  # nosec: required XBE SHA-1 field


def read_pinned(path: Path, size: int, digest: str, label: str) -> bytes:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode) and opened.st_size == size and
                (opened.st_dev, opened.st_ino) == (supplied.st_dev, supplied.st_ino),
                f"{label} identity or size changed")
        payload = bytearray()
        while len(payload) < size:
            chunk = os.read(descriptor, min(16 * 1024 * 1024, size - len(payload)))
            require(bool(chunk), f"{label} shortened while reading")
            payload.extend(chunk)
        require(not os.read(descriptor, 1), f"{label} grew while reading")
        require(sha256(payload) == digest, f"{label} SHA-256 differs")
        current = path.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                f"{label} pathname changed while reading")
        return bytes(payload)
    finally:
        os.close(descriptor)


def u32(payload: bytes, offset: int) -> int:
    require(0 <= offset <= len(payload) - 4, "XBE 32-bit field is outside input")
    return struct.unpack_from("<I", payload, offset)[0]


def cstring(payload: bytes, offset: int, maximum: int = 64) -> str:
    require(0 <= offset < len(payload), "XBE section name is outside input")
    end = payload.find(b"\0", offset, min(len(payload), offset + maximum))
    require(end >= 0, "XBE section name is not terminated")
    return payload[offset:end].decode("ascii")


def locate_rdata(payload: bytes) -> dict[str, int | str]:
    require(payload[:4] == b"XBEH", "retail input is not an XBE")
    image_base = u32(payload, 0x104)
    headers_size = u32(payload, 0x108)
    section_count = u32(payload, 0x11C)
    table_va = u32(payload, 0x120)
    require(image_base == 0x00010000 and headers_size == 0x00000CC4 and
            section_count == 22, "retail XBE header boundary changed")
    table_offset = table_va - image_base
    require(table_offset == 0x370 and table_offset + section_count * 56 <= headers_size,
            "retail XBE section table boundary changed")
    selected: dict[str, int | str] | None = None
    for index in range(section_count):
        header_offset = table_offset + index * 56
        fields = struct.unpack_from("<9I20s", payload, header_offset)
        name = cstring(payload, fields[5] - image_base)
        if name != ".rdata":
            continue
        require(selected is None, "retail XBE contains duplicate .rdata sections")
        selected = {
            "index": index,
            "name": name,
            "header_file_offset": header_offset,
            "virtual_address": fields[1],
            "virtual_size": fields[2],
            "raw_address": fields[3],
            "raw_size": fields[4],
            "digest_file_offset": header_offset + 36,
            "stored_digest": fields[9].hex(),
        }
    require(selected is not None, "retail XBE .rdata section is missing")
    require(selected == {
        "index": 12,
        "name": ".rdata",
        "header_file_offset": 0x610,
        "virtual_address": 0x004E3AE0,
        "virtual_size": 0x00585E89,
        "raw_address": 0x004D9000,
        "raw_size": 0x00585E88,
        "digest_file_offset": 0x634,
        "stored_digest": "167a8c5810298ff4af2e297359328ad79210fc9b",
    }, "retail XBE .rdata descriptor changed")
    mapped = (int(selected["raw_address"]) + TABLE_VA -
              int(selected["virtual_address"]))
    require(mapped == TABLE_OFFSET and
            TABLE_OFFSET + TABLE_SIZE <= int(selected["raw_address"]) +
            int(selected["raw_size"]),
            "draft table no longer maps into the pinned .rdata section")
    return selected


def load_audit(payload: bytes) -> dict[str, Any]:
    value = json.loads(payload)
    require(payload == canonical_json(value), "gameplay-tuning audit is not canonical JSON")
    table = value["nfl2k5"]["cpu_fantasy_draft"]["priority_table"]
    rows = table["rows"]
    require(
        value["schema"] == "vc_gameplay_tuning_ai_draft_audit/v1"
        and table["virtual_address"] == "0x00589588"
        and table["file_offset"] == "0x0057EAA8"
        and table["section"] == ".rdata"
        and [(row["position_code"], row["position"], row["weight"])
             for row in rows] ==
            [(index, POSITIONS[index], EXPECTED_WEIGHTS[index])
             for index in range(17)]
        and value["nfl2k5"]["cpu_fantasy_draft"]["classification"] ==
            "exact executable-patch candidate; runtime patch not performed"
        and value["executable_integrity_boundary"]["nfl_xbe"] == {
            "copy_only_asset_archive_edit_reaches_values": False,
            "section_sha1_digest_present": True,
            "slider_and_draft_data_inside_signed_default_xbe": True,
        },
        "gameplay-tuning audit draft/integrity contract changed",
    )
    return value


def generate() -> dict[str, Any]:
    xbe = read_pinned(XBE, XBE_SIZE, XBE_SHA256, "retail NFL 2K5 default.xbe")
    audit_payload = read_pinned(
        AUDIT, AUDIT_SIZE, AUDIT_SHA256, "canonical gameplay-tuning audit"
    )
    load_audit(audit_payload)
    section = locate_rdata(xbe)
    table = xbe[TABLE_OFFSET:TABLE_OFFSET + TABLE_SIZE]
    require(sha256(table) == TABLE_SHA256, "retail draft table SHA-256 changed")
    weights = struct.unpack("<17f", table)
    for actual, expected in zip(weights, EXPECTED_WEIGHTS):
        require(struct.pack("<f", actual) == struct.pack("<f", expected),
                "retail draft table float bytes changed")

    raw = int(section["raw_address"])
    raw_size = int(section["raw_size"])
    digest_offset = int(section["digest_file_offset"])
    headers_size = u32(xbe, 0x108)
    original_section_digest = xbe_sha1(xbe[raw:raw + raw_size])
    original_header_digest = xbe_sha1(xbe[0x104:headers_size])
    require(original_section_digest == section["stored_digest"],
            "retail .rdata digest does not match its stored field")

    stale = bytearray(xbe)
    old_qb = stale[TABLE_OFFSET:TABLE_OFFSET + 4]
    new_qb = struct.pack("<f", 2.25)
    stale[TABLE_OFFSET:TABLE_OFFSET + 4] = new_qb
    changed_table_bytes = sum(left != right for left, right in zip(old_qb, new_qb))
    require(changed_table_bytes == 1, "deterministic hypothetical edit changed unexpectedly")
    hypothetical_section_digest = xbe_sha1(bytes(stale[raw:raw + raw_size]))
    stale_header_digest = xbe_sha1(bytes(stale[0x104:headers_size]))
    require(hypothetical_section_digest != original_section_digest and
            stale_header_digest == original_header_digest,
            "stale-digest hypothetical branch did not isolate the section payload")

    updated = bytearray(stale)
    digest_bytes = bytes.fromhex(hypothetical_section_digest)
    original_digest_bytes = bytes.fromhex(original_section_digest)
    digest_changed_bytes = sum(
        left != right for left, right in zip(original_digest_bytes, digest_bytes)
    )
    updated[digest_offset:digest_offset + 20] = digest_bytes
    updated_header_digest = xbe_sha1(bytes(updated[0x104:headers_size]))
    require(digest_changed_bytes == 20 and updated_header_digest != original_header_digest,
            "updated-digest hypothetical branch did not change the signed header")
    require(updated[4:0x104] == xbe[4:0x104],
            "hypothetical branch unexpectedly changed the RSA signature bytes")

    rows = [
        {"position_code": index, "position": POSITIONS[index], "weight": weight}
        for index, weight in enumerate(EXPECTED_WEIGHTS)
    ]
    return {
        "schema": SCHEMA,
        "scope": {
            "operation": "read-only in-memory XBE integrity feasibility probe",
            "retail_xbe_opened_for_write": False,
            "copied_xbe_created": False,
            "emulator_launched": False,
            "runtime_patch_claimed": False,
        },
        "inputs": {
            "retail_xbe": {
                "path": XBE.relative_to(ROOT).as_posix(),
                "size": len(xbe),
                "sha256_before": sha256(xbe),
                "sha256_after": sha256(read_pinned(
                    XBE, XBE_SIZE, XBE_SHA256, "retail NFL 2K5 default.xbe recheck"
                )),
            },
            "gameplay_tuning_audit": {
                "path": AUDIT.relative_to(ROOT).as_posix(),
                "size": len(audit_payload),
                "sha256": sha256(audit_payload),
            },
        },
        "target": {
            "virtual_address": f"0x{TABLE_VA:08X}",
            "file_offset": f"0x{TABLE_OFFSET:08X}",
            "byte_size": TABLE_SIZE,
            "float_count": 17,
            "table_sha256": sha256(table),
            "rows": rows,
            "owner": "proved CPU fantasy-draft position-priority ranking path",
            "section": section,
        },
        "hypothetical_edit": {
            "purpose": "deterministic integrity experiment only; no output XBE is written",
            "position_code": 0,
            "position": "QB",
            "old_weight": 2.0,
            "new_weight": 2.25,
            "old_float_le_hex": old_qb.hex(),
            "new_float_le_hex": new_qb.hex(),
            "changed_table_byte_count": changed_table_bytes,
        },
        "integrity_branches": {
            "payload_only_stale_section_digest": {
                "hypothetical_xbe_sha256": sha256(stale),
                "stored_section_digest": original_section_digest,
                "recomputed_section_digest": hypothetical_section_digest,
                "section_digest_matches": False,
                "signed_header_digest_before": original_header_digest,
                "signed_header_digest_after": stale_header_digest,
                "signed_header_changed": False,
                "result": "section integrity fails",
            },
            "payload_plus_updated_section_digest": {
                "hypothetical_xbe_sha256": sha256(updated),
                "stored_section_digest": hypothetical_section_digest,
                "recomputed_section_digest": hypothetical_section_digest,
                "section_digest_matches": True,
                "section_digest_header_byte_changes": digest_changed_bytes,
                "section_digest_file_offset": f"0x{digest_offset:08X}",
                "signed_header_range": f"0x00000104..0x{headers_size - 1:08X}",
                "signed_header_digest_before": original_header_digest,
                "signed_header_digest_after": updated_header_digest,
                "signed_header_changed": True,
                "original_rsa_signature_bytes_reused": True,
                "result": "existing signature does not attest the modified signed-header digest",
            },
        },
        "conclusion": {
            "offline_float_bytes_are_mapped": True,
            "current_public_writer_safe": False,
            "reason": (
                "A payload-only edit breaks the .rdata digest; repairing that digest "
                "changes the RSA-signed header while leaving the original signature bytes."
            ),
            "required_next_proof": [
                "an explicitly authorized executable/security execution lane",
                "a copied-XBE or emulator patch mechanism with independent changed-byte verification",
                "boot acceptance plus deterministic fantasy-draft behavior tests",
                "separate original-Xbox hardware validation before any hardware claim",
            ],
        },
        "claims": {
            "retail_xbe_modified": False,
            "copied_xbe_written": False,
            "draft_weight_writer_proved": False,
            "retail_signed_xbe_patch_proved": False,
            "emulator_runtime_proved": False,
            "original_xbox_hardware_proved": False,
            "integrity_blocker_reproduced_in_memory": True,
        },
    }


def write_new(path: Path, value: object) -> Path:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    require(requested.suffix.lower() == ".json", "probe report must use .json")
    require(not os.path.lexists(requested), f"probe report already exists: {requested}")
    parent = requested.parent.lstat()
    require(stat.S_ISDIR(parent.st_mode) and not stat.S_ISLNK(parent.st_mode),
            "probe report parent must be an existing non-symlink directory")
    destination = requested.resolve(strict=False)
    require(destination not in {XBE.resolve(strict=True), AUDIT.resolve(strict=True)},
            "probe report cannot replace an evidence input")
    payload = canonical_json(value)
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(
            destination,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) |
            getattr(os, "O_CLOEXEC", 0),
            0o644,
        )
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode), "exclusive probe report is not regular")
        identity = (opened.st_dev, opened.st_ino)
        cursor = 0
        while cursor < len(payload):
            written = os.write(descriptor, payload[cursor:])
            require(written > 0, "short write while creating probe report")
            cursor += written
        os.fsync(descriptor)
        require(os.pread(descriptor, len(payload) + 1, 0) == payload,
                "probe report descriptor read-back differs")
        current = destination.stat(follow_symlinks=False)
        require(stat.S_ISREG(current.st_mode) and
                (current.st_dev, current.st_ino, current.st_size) ==
                (identity[0], identity[1], len(payload)),
                "probe report pathname changed while writing")
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        try:
            current = destination.stat(follow_symlinks=False)
            if identity is not None and stat.S_ISREG(current.st_mode) and \
                    (current.st_dev, current.st_ino) == identity:
                destination.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
    require(destination.read_bytes() == payload, "probe report read-back differs")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports/gameplay_tuning/nfl_draft_weight_xbe_integrity_probe.json",
    )
    args = parser.parse_args(argv)
    try:
        report = generate()
        path = write_new(args.output, report)
        print(
            "NFL_DRAFT_WEIGHT_XBE_INTEGRITY_PROBE_PASS "
            f"weights=17 stale_digest=true signed_header_changed=true "
            f"xbe_written=false output={path}"
        )
        return 0
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ProbeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
