#!/usr/bin/env python3
"""Independently verify the NFL ``s42`` stadium-visibility diagnostic XISO.

This module imports neither the visibility writer nor another XBE patcher.  It
re-verifies the source dispatch artifact, parses both complete XISOs, derives
the exact 22-byte difference ledger, recomputes the modified ``.data`` digest,
and checks the fail-closed diagnostic claim boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

import nfl_stadium_group36_s42_dispatch_xiso_verify as dispatch_verify
import nfl_uniform_color_xiso_direct_patch as xiso


VERIFY_SCHEMA = "nfl2k5_group36_s42_visibility_unlock_xiso_verify/v1"
MANIFEST_SCHEMA = "nfl2k5_group36_s42_visibility_unlock_xiso_patch/v1"
SOURCE_PROFILES = {
    "s42_control": {
        "source_sha256": "32a4f45e5d3d53f1ee1780165d9ffdaa36995a154a62e39c313e0e467b63b9a5",
        "output_sha256": "9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40",
        "dispatch_manifest_sha256": "e619cf3fa5eae3eea4a09e97f681db96df968041c6746dda68a013dd6ddbef89",
        "dispatch_profile": "retail_control",
        "pack9_sha256": "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
    },
    "s42_expanded_wall": {
        "source_sha256": "3c2917114ec7005e21c24c7fdf971adfdd54c051e89ecf2c4f93beb64a73dc16",
        "output_sha256": "f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6",
        "dispatch_manifest_sha256": "4fd1d53323c39cef94d7b5ac2a17a4c7d8669abff126f83a5eeda8a451b3e5c0",
        "dispatch_profile": "expanded_wall",
        "pack9_sha256": "c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad",
    },
}

FILE_COUNT = 19
PACK0_PATH = "vc_53450030/0"
PACK0_SECTOR = 796_479
PACK0_SIZE = 193_710_080
S42_PACK0_SHA256 = "57d5ea1703e952cfca9b0f5175b5c9f9bc0bda3eb6676db9f8b6b0e074bddae9"
PACK9_PATH = "vc_53450030/9"
PACK9_SECTOR = 35_531
PACK9_SIZE = 634_941_440
DEFAULT_XBE_SECTOR = 1_170
DEFAULT_XBE_SIZE = 11_948_032
DEFAULT_XBE_SOURCE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
DEFAULT_XBE_OUTPUT_SHA256 = "955ddffebbefe9f53d915d7728daf4e6224f946935b3549a1976615cff73dd6b"

IMAGE_BASE = 0x00010000
HEADERS_SIZE = 0x00000CC4
SECTION_COUNT = 22
SECTION_TABLE = 0x370
SECTION_HEADER_SIZE = 56
DATA_INDEX = 13
DATA_HEADER = 0x648
DATA_DIGEST = 0x66C
DATA_VA = 0x00A69980
DATA_VSIZE = 0x003F6988
DATA_RAW = 0x00A5F000
DATA_RAW_SIZE = 0x0008F95C
DATA_SOURCE_DIGEST = bytes.fromhex("8c86ae03ba27ffd03d09a3b8ca21d61e74a9337c")
DATA_OUTPUT_DIGEST = bytes.fromhex("8011736208bf6320358ee1b1cdaf29d421f80c24")
SIGNED_HEADER_SOURCE_SHA1 = "5c1dfe46aea5959344a7b0a112dc7000343f0df6"
SIGNED_HEADER_OUTPUT_SHA1 = "85c32209d9479a93af52b03efc83ee92dec28d26"
RSA_SIGNATURE_SHA256 = "4648f39dab19e1108e68daf993f72db693eed9f1db96d22bde7cdfcff661f107"

TABLE_VA = 0x00A97218
TABLE_OFFSET = 0x00A8C898
ROW_COUNT = 9
ROW_SIZE = 8
S42_ROW = 4
S42_STRING_VA = 0x00E70D28
S42_UNLOCK_VA = 0x00A9723C
S42_UNLOCK_OFFSET = 0x00A8C8BC
S42_BEFORE = bytes.fromhex("4b010000")
S42_AFTER = bytes.fromhex("00000000")
TABLE_SOURCE = bytes.fromhex(
    "080de70047010000100de70048010000180de70049010000200de7004a010000"
    "280de7004b010000300de7004c010000380de7004d010000400de7004e010000"
    "480de7004f010000"
)
TABLE_OUTPUT_BUFFER = bytearray(TABLE_SOURCE)
TABLE_OUTPUT_BUFFER[S42_ROW * ROW_SIZE + 4:S42_ROW * ROW_SIZE + 8] = S42_AFTER
TABLE_OUTPUT = bytes(TABLE_OUTPUT_BUFFER)

XBE_ABSOLUTE = DEFAULT_XBE_SECTOR * xiso.SECTOR_SIZE
DIGEST_ABSOLUTE = XBE_ABSOLUTE + DATA_DIGEST
UNLOCK_ABSOLUTE = XBE_ABSOLUTE + S42_UNLOCK_OFFSET
CHANGED_ABSOLUTE = (
    list(range(DIGEST_ABSOLUTE, DIGEST_ABSOLUTE + 20)) +
    [UNLOCK_ABSOLUTE, UNLOCK_ABSOLUTE + 1]
)
S42_ASSET_ABSOLUTE = 0x617A8142
S42_ASSET_BYTES = ("s42\0").encode("utf-16le")
MAX_JSON = 64 * 1024


class VisibilityVerifyError(ValueError):
    """The copied XISO violates the independent visibility contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VisibilityVerifyError(message)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def open_regular(path: Path, label: str) -> tuple[Path, int, tuple[int, int]]:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise VisibilityVerifyError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    opened = os.fstat(descriptor)
    require(stat.S_ISREG(opened.st_mode), f"{label} descriptor is not regular")
    identity = xiso.fd_identity(descriptor)
    require(xiso.path_identity(resolved) == identity,
            f"{label} pathname changed after open")
    return resolved, descriptor, identity


def read_json(path: Path, label: str, expected_sha: str | None = None) -> tuple[Path, dict[str, object], str]:
    resolved, fd, identity = open_regular(path, label)
    try:
        size = os.fstat(fd).st_size
        require(0 < size <= MAX_JSON, f"{label} size is outside the v1 limit")
        raw = xiso.read_exact(fd, 0, size)
        digest = hashlib.sha256(raw).hexdigest()
        if expected_sha is not None:
            require(digest == expected_sha, f"{label} SHA-256 mismatch")
        value = json.loads(raw)
        require(raw == canonical_json(value), f"{label} is not canonical JSON")
        require(xiso.path_identity(resolved) == identity,
                f"{label} pathname changed during read")
        return resolved, value, digest
    finally:
        os.close(fd)


def xbe_sha1(payload: bytes) -> str:
    return hashlib.sha1(struct.pack("<I", len(payload)) + payload).hexdigest()  # nosec B324


def cstring(payload: bytes, offset: int) -> str:
    require(0 <= offset < len(payload), "section name address outside XBE")
    end = payload.find(b"\0", offset, min(len(payload), offset + 64))
    require(end >= 0, "section name is unterminated")
    try:
        return payload[offset:end].decode("ascii")
    except UnicodeDecodeError as exc:
        raise VisibilityVerifyError("section name is not ASCII") from exc


def validate_xbe(payload: bytes, *, patched: bool) -> dict[str, object]:
    require(len(payload) == DEFAULT_XBE_SIZE and payload[:4] == b"XBEH",
            "default.xbe size or magic mismatch")
    image_base, headers_size = struct.unpack_from("<II", payload, 0x104)
    section_count, section_table_va = struct.unpack_from("<II", payload, 0x11C)
    require((image_base, headers_size, section_count, section_table_va) ==
            (IMAGE_BASE, HEADERS_SIZE, SECTION_COUNT, IMAGE_BASE + SECTION_TABLE),
            "XBE fixed header mismatch")
    header = section_table_va - image_base + DATA_INDEX * SECTION_HEADER_SIZE
    require(header == DATA_HEADER and header + SECTION_HEADER_SIZE <= headers_size,
            "XBE .data section-header boundary mismatch")
    fields = struct.unpack_from("<9I20s", payload, header)
    name = cstring(payload, fields[5] - image_base)
    require(name == ".data" and fields[:5] ==
            (0x7, DATA_VA, DATA_VSIZE, DATA_RAW, DATA_RAW_SIZE),
            "XBE .data descriptor mismatch")
    require(DATA_RAW + S42_UNLOCK_VA - DATA_VA == S42_UNLOCK_OFFSET and
            TABLE_OFFSET + S42_ROW * ROW_SIZE + 4 == S42_UNLOCK_OFFSET,
            "XBE visibility-row mapping arithmetic mismatch")
    table = TABLE_OUTPUT if patched else TABLE_SOURCE
    word = S42_AFTER if patched else S42_BEFORE
    digest = DATA_OUTPUT_DIGEST if patched else DATA_SOURCE_DIGEST
    xbe_digest = DEFAULT_XBE_OUTPUT_SHA256 if patched else DEFAULT_XBE_SOURCE_SHA256
    header_digest = SIGNED_HEADER_OUTPUT_SHA1 if patched else SIGNED_HEADER_SOURCE_SHA1
    require(payload[TABLE_OFFSET:TABLE_OFFSET + ROW_COUNT * ROW_SIZE] == table,
            "XBE availability table mismatch")
    require(payload[S42_UNLOCK_OFFSET:S42_UNLOCK_OFFSET + 4] == word,
            "XBE s42 unlock word mismatch")
    stored = payload[DATA_DIGEST:DATA_DIGEST + 20]
    computed = bytes.fromhex(xbe_sha1(payload[DATA_RAW:DATA_RAW + DATA_RAW_SIZE]))
    require(stored == computed == digest,
            "XBE .data stored/recomputed digest mismatch")
    require(xbe_sha1(payload[0x104:headers_size]) == header_digest,
            "XBE signed-header digest mismatch")
    require(hashlib.sha256(payload[4:0x104]).hexdigest() == RSA_SIGNATURE_SHA256,
            "XBE RSA signature bytes changed")
    require(hashlib.sha256(payload).hexdigest() == xbe_digest,
            "complete default.xbe SHA-256 mismatch")
    return {
        "section_index": DATA_INDEX,
        "section_name": name,
        "section_header_file_offset": header,
        "section_virtual_address": DATA_VA,
        "section_virtual_size": DATA_VSIZE,
        "section_raw_file_offset": DATA_RAW,
        "section_raw_size": DATA_RAW_SIZE,
        "section_digest_file_offset": DATA_DIGEST,
        "section_digest": stored.hex(),
        "availability_table_virtual_address": TABLE_VA,
        "availability_table_file_offset": TABLE_OFFSET,
        "s42_unlock_virtual_address": S42_UNLOCK_VA,
        "s42_unlock_file_offset": S42_UNLOCK_OFFSET,
        "s42_unlock_id": struct.unpack("<I", word)[0],
        "signed_header_sha1": header_digest,
        "rsa_signature_sha256": RSA_SIGNATURE_SHA256,
        "xbe_sha256": xbe_digest,
    }


def prepare_source(
    source_profile: str,
    source: Path,
    source_dispatch_manifest_path: Path,
    dispatch_base_xiso_path: Path,
    source_geometry_manifest_path: Path | None,
    retail_xiso_path: Path | None,
    index_path: Path | None,
    recipe_path: Path | None,
    geometry_output_dir: Path | None,
) -> tuple[dict[str, object], dict[str, object]]:
    require(source_profile in SOURCE_PROFILES, "unknown source profile")
    profile = SOURCE_PROFILES[source_profile]
    source_dispatch_manifest, _, manifest_sha = read_json(
        source_dispatch_manifest_path, "source dispatch manifest",
        str(profile["dispatch_manifest_sha256"]),
    )
    dispatch_base_xiso, base_fd, _ = open_regular(
        dispatch_base_xiso_path, "dispatch base XISO"
    )
    os.close(base_fd)
    if source_profile == "s42_control":
        require(all(value is None for value in (
            source_geometry_manifest_path, retail_xiso_path, index_path,
            recipe_path, geometry_output_dir,
        )), "s42_control forbids expanded-wall proof arguments")
        verification = dispatch_verify.verify(
            "retail_control", dispatch_base_xiso, source, source_dispatch_manifest
        )
    else:
        require(all(value is not None for value in (
            source_geometry_manifest_path, retail_xiso_path, index_path,
            recipe_path, geometry_output_dir,
        )), "s42_expanded_wall requires all geometry source-proof arguments")
        verification = dispatch_verify.verify(
            "expanded_wall", dispatch_base_xiso, source, source_dispatch_manifest,
            source_geometry_manifest_path=source_geometry_manifest_path,
            retail_xiso_path=retail_xiso_path, index_path=index_path,
            recipe_path=recipe_path, geometry_output_dir=geometry_output_dir,
        )
    require(verification["output_xiso_sha256"] == profile["source_sha256"] and
            verification["manifest_sha256"] == manifest_sha and
            verification["changed_byte_count"] == 2 and
            verification["default_xbe_exact"] is True and
            verification["xemu_target_outer_loaded_proved"] is False,
            "independent source dispatch verification mismatch")
    proof = {
        "kind": "pinned independently verified s42 diagnostic dispatch image",
        "dispatch_source_profile": profile["dispatch_profile"],
        "dispatch_base_xiso_path": str(dispatch_base_xiso),
        "source_dispatch_manifest_path": str(source_dispatch_manifest),
        "source_dispatch_manifest_sha256": manifest_sha,
        "source_dispatch_output_sha256": verification["output_xiso_sha256"],
        "source_dispatch_changed_byte_count": verification["changed_byte_count"],
        "source_dispatch_default_xbe_exact": verification["default_xbe_exact"],
        "source_dispatch_runtime_proved": False,
    }
    return profile, proof


def verify(
    source_profile: str,
    source_xiso_path: Path,
    source_dispatch_manifest_path: Path,
    dispatch_base_xiso_path: Path,
    output_xiso_path: Path,
    output_manifest_path: Path,
    *,
    source_geometry_manifest_path: Path | None = None,
    retail_xiso_path: Path | None = None,
    index_path: Path | None = None,
    recipe_path: Path | None = None,
    geometry_output_dir: Path | None = None,
) -> dict[str, object]:
    source, source_fd, source_identity = open_regular(source_xiso_path, "source s42 XISO")
    output, output_fd, output_identity = open_regular(output_xiso_path, "output XISO")
    require(source_identity != output_identity, "source and output alias one inode")
    output_manifest, manifest, manifest_sha = read_json(
        output_manifest_path, "visibility output manifest"
    )
    profile, source_proof = prepare_source(
        source_profile, source, source_dispatch_manifest_path, dispatch_base_xiso_path,
        source_geometry_manifest_path, retail_xiso_path, index_path, recipe_path,
        geometry_output_dir,
    )
    try:
        source_info = os.fstat(source_fd)
        output_info = os.fstat(output_fd)
        require(source_info.st_size == output_info.st_size == xiso.EXPECTED_XISO_SIZE,
                "complete XISO size mismatch")
        source_entries, source_directory = xiso.parse_xdvdfs(
            source_fd, source_info.st_size
        )
        output_entries, output_directory = xiso.parse_xdvdfs(
            output_fd, output_info.st_size
        )
        require(source_entries == output_entries and
                source_directory == output_directory,
                "XDVDFS tree or extents changed")
        files = [entry for entry in source_entries.values()
                 if not (entry.attributes & 0x10)]
        pack0 = source_entries.get(PACK0_PATH.casefold())
        pack9 = source_entries.get(PACK9_PATH.casefold())
        xbe_entry = source_entries.get("default.xbe")
        require(len(files) == FILE_COUNT and
                pack0 is not None and (pack0.sector, pack0.size) ==
                (PACK0_SECTOR, PACK0_SIZE) and
                pack9 is not None and (pack9.sector, pack9.size) ==
                (PACK9_SECTOR, PACK9_SIZE) and
                xbe_entry is not None and (xbe_entry.sector, xbe_entry.size) ==
                (DEFAULT_XBE_SECTOR, DEFAULT_XBE_SIZE),
                "fixed XDVDFS extent contract mismatch")
        source_sha, output_sha, differences = xiso.compare_and_hash(
            source_fd, output_fd, source_info.st_size, set(CHANGED_ABSOLUTE)
        )
        require(source_sha == profile["source_sha256"] and
                output_sha == profile["output_sha256"],
                "source/output XISO SHA-256 mismatch")
        require(differences == CHANGED_ABSOLUTE,
                "complete-image 22-byte difference ledger mismatch")
        source_pack0_sha = xiso.sha256_fd(source_fd, pack0.byte_offset, pack0.size)
        output_pack0_sha = xiso.sha256_fd(output_fd, pack0.byte_offset, pack0.size)
        source_pack9_sha = xiso.sha256_fd(source_fd, pack9.byte_offset, pack9.size)
        output_pack9_sha = xiso.sha256_fd(output_fd, pack9.byte_offset, pack9.size)
        require(source_pack0_sha == output_pack0_sha == S42_PACK0_SHA256 and
                source_pack9_sha == output_pack9_sha == profile["pack9_sha256"],
                "roster or geometry volume changed")
        require(xiso.read_exact(source_fd, S42_ASSET_ABSOLUTE, len(S42_ASSET_BYTES)) ==
                xiso.read_exact(output_fd, S42_ASSET_ABSOLUTE, len(S42_ASSET_BYTES)) ==
                S42_ASSET_BYTES,
                "s42 roster dispatch allocation changed")
        source_xbe = xiso.read_exact(source_fd, xbe_entry.byte_offset, xbe_entry.size)
        output_xbe = xiso.read_exact(output_fd, xbe_entry.byte_offset, xbe_entry.size)
        source_xbe_info = validate_xbe(source_xbe, patched=False)
        output_xbe_info = validate_xbe(output_xbe, patched=True)

        require(manifest.get("schema") == MANIFEST_SCHEMA and
                manifest.get("source_profile") == source_profile,
                "manifest schema or source profile mismatch")
        require(manifest.get("source") == {
            "path": str(source), "size": source_info.st_size,
            "sha256_before": source_sha, "sha256_after": source_sha,
            "opened_read_only": True, "modified": False,
            "exact_pinned_s42_dispatch_artifact": True,
        }, "manifest source record mismatch")
        require(manifest.get("source_proof") == source_proof,
                "manifest source-proof record mismatch")
        require(manifest.get("xdvdfs") == {
            **source_directory, "file_count": len(files),
            "tree_identical_after_patch": True,
            "all_sector_extents_preserved": True,
            "default_xbe_sector": xbe_entry.sector,
            "default_xbe_size": xbe_entry.size,
            "pack0_sha256": source_pack0_sha,
            "pack9_sha256": source_pack9_sha,
        }, "manifest XDVDFS record mismatch")
        expected_classification = {
            "quick_game_next_function": "0x002c15d0",
            "quick_game_previous_function": "0x002c1600",
            "skip_predicate_function": "0x002c0c20",
            "availability_lookup_function": "0x0010e920",
            "unlock_test_function": "0x0010e8f0",
            "classification_key": "exact UTF-16 asset-code string",
            "s42_row_index": S42_ROW,
            "s42_string_virtual_address": f"0x{S42_STRING_VA:08x}",
            "source_unlock_id": 0x14B,
            "output_unlock_id": 0,
            "zero_id_semantics": "FUN_0010e8f0 returns visible before profile lookup",
            "s32_mode_exception_applies": False,
        }
        require(manifest.get("xbe") == {
            "source": source_xbe_info,
            "output": output_xbe_info,
            "visibility_classification": expected_classification,
            "integrity": {
                "data_section_digest_recomputed": True,
                "digest_absolute_xiso_offset": f"0x{DIGEST_ABSOLUTE:08x}",
                "digest_changed_byte_count": 20,
                "rsa_signature_bytes_changed": False,
                "signed_header_changed": True,
                "existing_retail_signature_attests_modified_header": False,
            },
        }, "manifest XBE record mismatch")
        require(manifest.get("patch") == {
            "purpose": "diagnostic global s42 stadium visibility/unlock classification",
            "scope": "all stadium records whose exact asset code is s42",
            "unlock_word_absolute_xiso_offset": f"0x{UNLOCK_ABSOLUTE:08x}",
            "unlock_word_before_hex": S42_BEFORE.hex(),
            "unlock_word_after_hex": S42_AFTER.hex(),
            "allowed_changed_byte_offsets": CHANGED_ABSOLUTE,
            "actual_changed_byte_offsets": differences,
            "actual_changed_byte_count": len(differences),
            "semantic_data_byte_count": 2,
            "required_section_digest_byte_count": 20,
            "all_other_xiso_bytes_identical": True,
        }, "manifest patch record mismatch")
        output_record = manifest.get("output")
        require(isinstance(output_record, dict) and output_record == {
            "path": str(output), "size": output_info.st_size,
            "sha256": output_sha, "copy_method": output_record.get("copy_method"),
            "exclusively_created": True, "distinct_from_source_inode": True,
        } and output_record.get("copy_method") in {"copy_file_range", "pread_pwrite"},
                "manifest output record mismatch")
        claims = {
            "diagnostic_only": True,
            "offline_visibility_predicate_proved": True,
            "offline_zero_unlock_id_path_proved": True,
            "s42_asset_code_preserved": True,
            "source_geometry_volume9_preserved": True,
            "internal_data_section_digest_valid": True,
            "retail_signed_executable_chain_preserved": False,
            "xemu_boot_acceptance_proved": False,
            "xemu_stadium_selectability_proved": False,
            "xemu_target_outer_loaded_proved": False,
            "xemu_geometry_visibility_proved": False,
            "original_xbox_hardware_proved": False,
            "production_ready": False,
            "distribution_ready": False,
            "public_editor_exposed": False,
        }
        require(manifest.get("claims") == claims,
                "manifest claim boundary mismatch")
        require(xiso.sha256_fd(source_fd) == profile["source_sha256"] and
                xiso.path_identity(source) == source_identity and
                xiso.path_identity(output) == output_identity and
                xiso.path_identity(output_manifest) is not None,
                "an input artifact changed during verification")
    finally:
        os.close(source_fd)
        os.close(output_fd)

    return {
        "schema": VERIFY_SCHEMA,
        "source_profile": source_profile,
        "manifest_sha256": manifest_sha,
        "source_xiso_sha256": source_sha,
        "output_xiso_sha256": output_sha,
        "changed_byte_offsets": differences,
        "changed_byte_count": len(differences),
        "source_pack0_sha256": source_pack0_sha,
        "output_pack0_sha256": output_pack0_sha,
        "source_pack9_sha256": source_pack9_sha,
        "output_pack9_sha256": output_pack9_sha,
        "default_xbe_source_sha256": DEFAULT_XBE_SOURCE_SHA256,
        "default_xbe_output_sha256": DEFAULT_XBE_OUTPUT_SHA256,
        "xdvdfs_tree_exact": True,
        "s42_asset_code_exact": True,
        "source_unchanged": True,
        "xemu_boot_acceptance_proved": False,
        "xemu_stadium_selectability_proved": False,
        "xemu_target_outer_loaded_proved": False,
        "xemu_geometry_visibility_proved": False,
        "hardware_proved": False,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-profile", required=True, choices=sorted(SOURCE_PROFILES))
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--source-dispatch-manifest", required=True, type=Path)
    parser.add_argument("--dispatch-base-xiso", required=True, type=Path)
    parser.add_argument("--source-geometry-manifest", type=Path)
    parser.add_argument("--retail-xiso", type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--recipe", type=Path)
    parser.add_argument("--geometry-output-dir", type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    result = verify(
        args.source_profile, args.source_xiso, args.source_dispatch_manifest,
        args.dispatch_base_xiso, args.output_xiso, args.manifest,
        source_geometry_manifest_path=args.source_geometry_manifest,
        retail_xiso_path=args.retail_xiso, index_path=args.index,
        recipe_path=args.recipe, geometry_output_dir=args.geometry_output_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, xiso.PatchError, KeyError,
            json.JSONDecodeError, struct.error) as exc:
        raise SystemExit(f"error: {exc}") from exc
