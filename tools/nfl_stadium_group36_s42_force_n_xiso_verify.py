#!/usr/bin/env python3
"""Independently verify the diagnostic global s42 force-night XISO patch.

This verifier imports neither the force-night writer nor an XBE writer.  It
re-proves the selected s42 source artifact, parses the XBE and XDVDFS directly,
recomputes the XBE section/header digests, and compares every byte of both
6.3 GB images against the exact 21-byte authorization set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

import nfl_stadium_group36_s42_visibility_unlock_xiso_verify as visibility_verify
import nfl_uniform_color_xiso_direct_patch as xiso_format


VERIFY_SCHEMA = "nfl2k5_group36_s42_force_n_xiso_verify/v1"
MANIFEST_SCHEMA = "nfl2k5_group36_s42_force_n_xiso_patch/v1"
SOURCE_PROFILES = {
    "s42_control": {
        "source_sha256": "9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40",
        "output_sha256": "863ba00df855efdf54b85d568516b1ed0f7bbd33ddb77096ce3e16da4e702383",
        "visibility_manifest_sha256": "88b4e1e0a5911ba7c2fa6b92d61eaf5b7b47605d9a61d4208cffbbcb1eefbdbe",
        "pack9_sha256": "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
    },
    "s42_expanded_wall": {
        "source_sha256": "f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6",
        "output_sha256": "d41c44882919a00282c184fcc85b4ec139e17b48ee7681960808cc14947bab72",
        "visibility_manifest_sha256": "166ba6a28318e289446f0814edd9bcddb28360bd4ad16b13dfa22f82634429b7",
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
DEFAULT_XBE_SOURCE_SHA256 = "955ddffebbefe9f53d915d7728daf4e6224f946935b3549a1976615cff73dd6b"
DEFAULT_XBE_OUTPUT_SHA256 = "c6abdd77be89594ee19dbfd8dbfa300b592a5a2ed1af2276e5e132678e50cc27"

XBE_IMAGE_BASE = 0x00010000
XBE_HEADERS_SIZE = 0x00000CC4
XBE_SECTION_COUNT = 22
XBE_SECTION_TABLE = 0x370
XBE_SECTION_HEADER_SIZE = 56
TEXT_SECTION_DIGEST = 0x394
TEXT_VA = 0x00011000
TEXT_VSIZE = 0x0040F114
TEXT_RAW = 0x00001000
TEXT_RAW_SIZE = 0x0040F114
TEXT_SOURCE_DIGEST = bytes.fromhex("72edb599858a06a0f88c6ae446907e3977f4fec6")
TEXT_OUTPUT_DIGEST = bytes.fromhex("a013179864b328a3bda23b60f4cee9b9ed7dcc9d")
SIGNED_HEADER_SOURCE_SHA1 = "85c32209d9479a93af52b03efc83ee92dec28d26"
SIGNED_HEADER_OUTPUT_SHA1 = "80c507386b62ac1dddb4dc21750355ee5861babc"
RSA_SIGNATURE_SHA256 = "4648f39dab19e1108e68daf993f72db693eed9f1db96d22bde7cdfcff661f107"

DATA_SECTION_INDEX = 13
DATA_SECTION_HEADER = XBE_SECTION_TABLE + DATA_SECTION_INDEX * XBE_SECTION_HEADER_SIZE
DATA_SECTION_DIGEST = DATA_SECTION_HEADER + 36
DATA_VA = 0x00A69980
DATA_VSIZE = 0x003F6988
DATA_RAW = 0x00A5F000
DATA_RAW_SIZE = 0x0008F95C
DATA_VISIBILITY_DIGEST = bytes.fromhex("8011736208bf6320358ee1b1cdaf29d421f80c24")
S42_UNLOCK_VA = 0x00A9723C
S42_UNLOCK_XBE_OFFSET = 0x00A8C8BC
S42_UNLOCK_VISIBLE_BYTES = b"\0\0\0\0"

TIME_BRANCH_VA = 0x00062C60
TIME_BRANCH_XBE_OFFSET = 0x00052C60
TIME_DISPLACEMENT_XBE_OFFSET = 0x00052C61
TIME_CONTEXT_XBE_OFFSET = 0x00052C5E
TIME_CONTEXT_SOURCE = bytes.fromhex("85c07405bf6e000000668974240e66897c240c")
TIME_CONTEXT_OUTPUT = bytes.fromhex("85c07400bf6e000000668974240e66897c240c")
DEFAULT_XBE_ABSOLUTE = DEFAULT_XBE_SECTOR * xiso_format.SECTOR_SIZE
DIGEST_ABSOLUTE = DEFAULT_XBE_ABSOLUTE + TEXT_SECTION_DIGEST
TIME_DISPLACEMENT_ABSOLUTE = DEFAULT_XBE_ABSOLUTE + TIME_DISPLACEMENT_XBE_OFFSET
CHANGED_XBE_OFFSETS = list(range(TEXT_SECTION_DIGEST, TEXT_SECTION_DIGEST + 20)) + [
    TIME_DISPLACEMENT_XBE_OFFSET,
]
CHANGED_XISO_OFFSETS = list(range(DIGEST_ABSOLUTE, DIGEST_ABSOLUTE + 20)) + [
    TIME_DISPLACEMENT_ABSOLUTE,
]
S42_ASSET_ABSOLUTE = 0x617A8142
S42_ASSET_BYTES = ("s42\0").encode("utf-16le")
MAX_JSON = 64 * 1024


class ForceNVerifyError(ValueError):
    """A source, output, or manifest violates the independent contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ForceNVerifyError(message)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def open_regular(path: Path, label: str) -> tuple[Path, int, tuple[int, int]]:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ForceNVerifyError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    opened = os.fstat(descriptor)
    identity = xiso_format.fd_identity(descriptor)
    require(stat.S_ISREG(opened.st_mode) and
            xiso_format.path_identity(resolved) == identity,
            f"{label} pathname or descriptor changed")
    return resolved, descriptor, identity


def read_json(path: Path, label: str) -> tuple[Path, dict[str, object], str]:
    resolved, descriptor, identity = open_regular(path, label)
    try:
        size = os.fstat(descriptor).st_size
        require(0 < size <= MAX_JSON, f"{label} size is outside v1 limit")
        raw = xiso_format.read_exact(descriptor, 0, size)
        value = json.loads(raw)
        require(isinstance(value, dict) and raw == canonical_json(value),
                f"{label} is not canonical JSON")
        require(xiso_format.path_identity(resolved) == identity,
                f"{label} pathname changed during read")
        return resolved, value, hashlib.sha256(raw).hexdigest()
    finally:
        os.close(descriptor)


def xbe_sha1(payload: bytes) -> str:
    return hashlib.sha1(struct.pack("<I", len(payload)) + payload).hexdigest()  # nosec B324


def cstring(payload: bytes, offset: int, maximum: int = 64) -> str:
    require(0 <= offset < len(payload), "XBE section name offset outside file")
    end = payload.find(b"\0", offset, min(len(payload), offset + maximum))
    require(end >= 0, "XBE section name is unterminated")
    try:
        return payload[offset:end].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ForceNVerifyError("XBE section name is not ASCII") from exc


def parse_xbe(payload: bytes, *, patched: bool) -> dict[str, object]:
    require(len(payload) == DEFAULT_XBE_SIZE and payload[:4] == b"XBEH",
            "default.xbe size/magic mismatch")
    image_base, headers_size = struct.unpack_from("<II", payload, 0x104)
    section_count, section_table_va = struct.unpack_from("<II", payload, 0x11C)
    require((image_base, headers_size, section_count, section_table_va) ==
            (XBE_IMAGE_BASE, XBE_HEADERS_SIZE, XBE_SECTION_COUNT,
             XBE_IMAGE_BASE + XBE_SECTION_TABLE),
            "default.xbe header boundary mismatch")
    section_header = section_table_va - image_base
    require(section_header == XBE_SECTION_TABLE and
            section_header + section_count * XBE_SECTION_HEADER_SIZE <= headers_size,
            "default.xbe section table boundary mismatch")
    fields = struct.unpack_from("<9I20s", payload, section_header)
    name = cstring(payload, fields[5] - image_base)
    require(name == ".text" and fields[:5] ==
            (0x16, TEXT_VA, TEXT_VSIZE, TEXT_RAW, TEXT_RAW_SIZE),
            "default.xbe .text descriptor mismatch")
    data_fields = struct.unpack_from("<9I20s", payload, DATA_SECTION_HEADER)
    data_name = cstring(payload, data_fields[5] - image_base)
    require(data_name == ".data" and data_fields[:5] ==
            (0x07, DATA_VA, DATA_VSIZE, DATA_RAW, DATA_RAW_SIZE) and
            DATA_RAW + S42_UNLOCK_VA - DATA_VA == S42_UNLOCK_XBE_OFFSET,
            "default.xbe .data visibility descriptor mismatch")
    data_stored_digest = payload[DATA_SECTION_DIGEST:DATA_SECTION_DIGEST + 20]
    data_computed_digest = bytes.fromhex(
        xbe_sha1(payload[DATA_RAW:DATA_RAW + DATA_RAW_SIZE])
    )
    require(data_stored_digest == data_computed_digest == DATA_VISIBILITY_DIGEST and
            payload[S42_UNLOCK_XBE_OFFSET:S42_UNLOCK_XBE_OFFSET + 4] ==
            S42_UNLOCK_VISIBLE_BYTES,
            "s42 visibility-unlock source proof is absent or stale")
    require(TEXT_RAW + TIME_BRANCH_VA - TEXT_VA == TIME_BRANCH_XBE_OFFSET,
            "XBE virtual/file address mapping mismatch")

    expected_context = TIME_CONTEXT_OUTPUT if patched else TIME_CONTEXT_SOURCE
    expected_digest = TEXT_OUTPUT_DIGEST if patched else TEXT_SOURCE_DIGEST
    expected_header = SIGNED_HEADER_OUTPUT_SHA1 if patched else SIGNED_HEADER_SOURCE_SHA1
    expected_sha = DEFAULT_XBE_OUTPUT_SHA256 if patched else DEFAULT_XBE_SOURCE_SHA256
    require(payload[TIME_CONTEXT_XBE_OFFSET:
                    TIME_CONTEXT_XBE_OFFSET + len(expected_context)] == expected_context and
            payload.count(expected_context) == 1,
            "force-n instruction context mismatch or is not unique")
    stored_digest = payload[TEXT_SECTION_DIGEST:TEXT_SECTION_DIGEST + 20]
    recomputed_digest = bytes.fromhex(xbe_sha1(payload[TEXT_RAW:TEXT_RAW + TEXT_RAW_SIZE]))
    require(stored_digest == recomputed_digest == expected_digest,
            "default.xbe .text digest mismatch")
    require(xbe_sha1(payload[0x104:headers_size]) == expected_header,
            "default.xbe signed-header digest mismatch")
    require(hashlib.sha256(payload[4:0x104]).hexdigest() == RSA_SIGNATURE_SHA256,
            "default.xbe RSA signature bytes changed")
    require(hashlib.sha256(payload).hexdigest() == expected_sha,
            "default.xbe complete SHA-256 mismatch")
    return {
        "section_index": 0,
        "section_name": name,
        "section_header_file_offset": section_header,
        "section_virtual_address": TEXT_VA,
        "section_virtual_size": TEXT_VSIZE,
        "section_raw_file_offset": TEXT_RAW,
        "section_raw_size": TEXT_RAW_SIZE,
        "section_digest_file_offset": TEXT_SECTION_DIGEST,
        "section_digest": stored_digest.hex(),
        "time_branch_virtual_address": TIME_BRANCH_VA,
        "time_branch_file_offset": TIME_BRANCH_XBE_OFFSET,
        "time_branch_bytes": payload[TIME_BRANCH_XBE_OFFSET:
                                     TIME_BRANCH_XBE_OFFSET + 2].hex(),
        "signed_header_sha1": expected_header,
        "rsa_signature_sha256": RSA_SIGNATURE_SHA256,
        "visibility_unlock_virtual_address": S42_UNLOCK_VA,
        "visibility_unlock_file_offset": S42_UNLOCK_XBE_OFFSET,
        "visibility_unlock_bytes": S42_UNLOCK_VISIBLE_BYTES.hex(),
        "data_section_digest": data_stored_digest.hex(),
        "xbe_sha256": expected_sha,
    }


def independent_xbe_difference(source: bytes, output: bytes) -> list[int]:
    require(len(source) == len(output) == DEFAULT_XBE_SIZE,
            "XBE source/output sizes differ")
    differences = [index for index, pair in enumerate(zip(source, output))
                   if pair[0] != pair[1]]
    require(differences == CHANGED_XBE_OFFSETS,
            "default.xbe independent 21-byte ledger mismatch")
    require(source[TIME_DISPLACEMENT_XBE_OFFSET] == 0x05 and
            output[TIME_DISPLACEMENT_XBE_OFFSET] == 0x00,
            "force-n displacement edit mismatch")
    require(source[:TEXT_SECTION_DIGEST] == output[:TEXT_SECTION_DIGEST] and
            source[TEXT_SECTION_DIGEST + 20:TIME_DISPLACEMENT_XBE_OFFSET] ==
            output[TEXT_SECTION_DIGEST + 20:TIME_DISPLACEMENT_XBE_OFFSET] and
            source[TIME_DISPLACEMENT_XBE_OFFSET + 1:] ==
            output[TIME_DISPLACEMENT_XBE_OFFSET + 1:],
            "default.xbe changed outside digest/displacement bytes")
    return differences


def prepare_source_profile(
    source_profile: str,
    source: Path,
    source_visibility_manifest_path: Path,
    visibility_base_xiso_path: Path,
    source_dispatch_manifest_path: Path,
    dispatch_base_xiso_path: Path,
    source_geometry_manifest_path: Path | None,
    retail_xiso_path: Path | None,
    index_path: Path | None,
    recipe_path: Path | None,
    geometry_output_dir: Path | None,
) -> tuple[str, str, str, dict[str, object]]:
    require(source_profile in SOURCE_PROFILES, "unknown source profile")
    profile = SOURCE_PROFILES[source_profile]
    visibility_manifest, manifest_value, manifest_sha = read_json(
        source_visibility_manifest_path, "source s42 visibility manifest"
    )
    require(manifest_sha == profile["visibility_manifest_sha256"] and
            manifest_value.get("schema") ==
            "nfl2k5_group36_s42_visibility_unlock_xiso_patch/v1",
            "source s42 visibility manifest identity mismatch")
    visibility_base, visibility_base_fd, visibility_base_identity = open_regular(
        visibility_base_xiso_path, "visibility base s42 XISO"
    )
    os.close(visibility_base_fd)
    require(xiso_format.path_identity(visibility_base) == visibility_base_identity,
            "visibility base pathname changed")

    if source_profile == "s42_control":
        require(all(value is None for value in (
            source_geometry_manifest_path, retail_xiso_path, index_path,
            recipe_path, geometry_output_dir,
        )), "s42_control forbids expanded-wall proof arguments")
        verification = visibility_verify.verify(
            source_profile, visibility_base, source_dispatch_manifest_path,
            dispatch_base_xiso_path, source, visibility_manifest,
        )
    else:
        require(all(value is not None for value in (
            source_geometry_manifest_path, retail_xiso_path, index_path,
            recipe_path, geometry_output_dir,
        )), "s42_expanded_wall requires all geometry source-proof arguments")
        verification = visibility_verify.verify(
            source_profile, visibility_base, source_dispatch_manifest_path,
            dispatch_base_xiso_path, source, visibility_manifest,
            source_geometry_manifest_path=source_geometry_manifest_path,
            retail_xiso_path=retail_xiso_path,
            index_path=index_path,
            recipe_path=recipe_path,
            geometry_output_dir=geometry_output_dir,
        )
    require(verification["output_xiso_sha256"] == profile["source_sha256"] and
            verification["manifest_sha256"] == profile["visibility_manifest_sha256"] and
            verification["changed_byte_count"] == 22 and
            verification["default_xbe_output_sha256"] == DEFAULT_XBE_SOURCE_SHA256 and
            verification["xemu_stadium_selectability_proved"] is False and
            verification["xemu_target_outer_loaded_proved"] is False,
            "independent source s42 visibility proof mismatch")
    return (str(profile["source_sha256"]), str(profile["output_sha256"]),
            str(profile["pack9_sha256"]), {
        "kind": "pinned independently verified s42 visibility-unlock diagnostic image",
        "visibility_source_profile": source_profile,
        "visibility_base_xiso_path": str(visibility_base),
        "source_visibility_manifest_path": str(visibility_manifest),
        "source_visibility_manifest_sha256": profile["visibility_manifest_sha256"],
        "source_visibility_output_sha256": verification["output_xiso_sha256"],
        "source_visibility_changed_byte_count": verification["changed_byte_count"],
        "source_visibility_default_xbe_sha256":
            verification["default_xbe_output_sha256"],
        "source_visibility_selectability_runtime_proved": False,
        "source_visibility_target_outer_runtime_proved": False,
    })


def verify(
    source_profile: str,
    source_xiso_path: Path,
    source_visibility_manifest_path: Path,
    visibility_base_xiso_path: Path,
    source_dispatch_manifest_path: Path,
    dispatch_base_xiso_path: Path,
    output_xiso_path: Path,
    manifest_path: Path,
    *,
    source_geometry_manifest_path: Path | None = None,
    retail_xiso_path: Path | None = None,
    index_path: Path | None = None,
    recipe_path: Path | None = None,
    geometry_output_dir: Path | None = None,
) -> dict[str, object]:
    manifest_file, manifest, manifest_sha = read_json(
        manifest_path, "force-n writer manifest"
    )
    require(manifest.get("schema") == MANIFEST_SCHEMA and set(manifest) == {
        "schema", "source_profile", "source", "source_proof", "xdvdfs",
        "xbe", "patch", "output", "claims",
    }, "force-n manifest root/schema mismatch")
    require(manifest["source_profile"] == source_profile,
            "force-n manifest source profile mismatch")

    source, source_fd, source_identity = open_regular(
        source_xiso_path, "pinned s42 source XISO"
    )
    output, output_fd, output_identity = open_regular(
        output_xiso_path, "force-n output XISO"
    )
    try:
        (expected_source_sha, expected_output_sha, expected_pack9_sha,
         expected_source_proof) = (
            prepare_source_profile(
                source_profile, source, source_visibility_manifest_path,
                visibility_base_xiso_path, source_dispatch_manifest_path,
                dispatch_base_xiso_path, source_geometry_manifest_path,
                retail_xiso_path, index_path, recipe_path,
                geometry_output_dir,
            )
        )
        source_info = os.fstat(source_fd)
        output_info = os.fstat(output_fd)
        require(source_identity != output_identity and
                source_info.st_size == output_info.st_size ==
                xiso_format.EXPECTED_XISO_SIZE,
                "source/output identity or size mismatch")
        source_entries, source_directory = xiso_format.parse_xdvdfs(
            source_fd, source_info.st_size
        )
        output_entries, output_directory = xiso_format.parse_xdvdfs(
            output_fd, output_info.st_size
        )
        require(source_entries == output_entries and
                source_directory == output_directory,
                "XDVDFS tree or extents differ")
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

        source_sha, output_sha, differences = xiso_format.compare_and_hash(
            source_fd, output_fd, source_info.st_size, set(CHANGED_XISO_OFFSETS)
        )
        require(source_sha == expected_source_sha and
                output_sha == expected_output_sha and
                differences == CHANGED_XISO_OFFSETS,
                "complete-image source hash or 21-byte ledger mismatch")
        source_pack0_sha = xiso_format.sha256_fd(
            source_fd, pack0.byte_offset, pack0.size
        )
        output_pack0_sha = xiso_format.sha256_fd(
            output_fd, pack0.byte_offset, pack0.size
        )
        source_pack9_sha = xiso_format.sha256_fd(
            source_fd, pack9.byte_offset, pack9.size
        )
        output_pack9_sha = xiso_format.sha256_fd(
            output_fd, pack9.byte_offset, pack9.size
        )
        require(source_pack0_sha == output_pack0_sha == S42_PACK0_SHA256 and
                source_pack9_sha == output_pack9_sha == expected_pack9_sha and
                xiso_format.read_exact(source_fd, S42_ASSET_ABSOLUTE,
                                       len(S42_ASSET_BYTES)) ==
                xiso_format.read_exact(output_fd, S42_ASSET_ABSOLUTE,
                                       len(S42_ASSET_BYTES)) == S42_ASSET_BYTES,
                "s42 roster or geometry profile changed")
        source_xbe = xiso_format.read_exact(
            source_fd, xbe_entry.byte_offset, xbe_entry.size
        )
        output_xbe = xiso_format.read_exact(
            output_fd, xbe_entry.byte_offset, xbe_entry.size
        )
        source_xbe_record = parse_xbe(source_xbe, patched=False)
        output_xbe_record = parse_xbe(output_xbe, patched=True)
        xbe_differences = independent_xbe_difference(source_xbe, output_xbe)

        expected_source = {
            "path": str(source), "size": source_info.st_size,
            "sha256_before": source_sha, "sha256_after": source_sha,
            "opened_read_only": True, "modified": False,
            "exact_pinned_s42_visibility_artifact": True,
        }
        expected_xdvdfs = {
            **source_directory, "file_count": len(files),
            "tree_identical_after_patch": True,
            "all_sector_extents_preserved": True,
            "default_xbe_sector": xbe_entry.sector,
            "default_xbe_size": xbe_entry.size,
            "pack0_sha256": source_pack0_sha,
            "pack9_sha256": source_pack9_sha,
        }
        expected_xbe = {
            "source": source_xbe_record,
            "output": output_xbe_record,
            "instruction_patch": {
                "scope": "global stadium outer-name time suffix in FUN_00062be0",
                "global_not_s42_conditional": True,
                "virtual_address": "0x00062c60",
                "file_offset": "0x00052c60",
                "instruction_absolute_xiso_offset": "0x0029bc60",
                "changed_byte_absolute_xiso_offset": "0x0029bc61",
                "before_hex": "7405",
                "before_instruction": "JZ 0x00062c67",
                "after_hex": "7400",
                "after_instruction": "JZ 0x00062c62",
                "effect": "unconditionally execute MOV EDI,0x6e",
            },
            "dataflow": {
                "weather_register": "ESI",
                "time_register": "EDI",
                "weather_store": "0x00062c67 MOV word ptr [ESP+0x0e],SI",
                "time_store": "0x00062c6c MOV word ptr [ESP+0x0c],DI",
                "asset_code_load": "0x00062c76 MOV EDX,[EAX+0x0c]",
                "format_callsite": "0x00062c82",
                "format": "%s%c%c.iff",
                "s42_clear_result": "s42nd.iff",
            },
            "integrity": {
                "text_section_digest_recomputed": True,
                "digest_absolute_xiso_offset": "0x00249394",
                "digest_changed_byte_count": 20,
                "rsa_signature_bytes_changed": False,
                "signed_header_changed": True,
                "existing_retail_signature_attests_modified_header": False,
            },
        }
        expected_patch = {
            "purpose": "diagnostic global stadium-time suffix force-n only",
            "allowed_changed_byte_offsets": CHANGED_XISO_OFFSETS,
            "actual_changed_byte_offsets": differences,
            "actual_changed_byte_count": 21,
            "semantic_code_byte_count": 1,
            "required_section_digest_byte_count": 20,
            "all_other_xiso_bytes_identical": True,
        }
        claims = {
            "diagnostic_only": True,
            "offline_force_n_dataflow_proved": True,
            "weather_suffix_instruction_and_value_preserved": True,
            "s42_asset_code_preserved": True,
            "s42_visibility_unlock_preserved": True,
            "source_geometry_volume9_preserved": True,
            "internal_text_section_digest_valid": True,
            "internal_data_section_digest_valid": True,
            "retail_signed_executable_chain_preserved": False,
            "xemu_boot_acceptance_proved": False,
            "xemu_target_outer_loaded_proved": False,
            "xemu_geometry_visibility_proved": False,
            "original_xbox_hardware_proved": False,
            "production_ready": False,
            "public_editor_exposed": False,
        }
        require(manifest["source"] == expected_source,
                "manifest source record mismatch")
        require(manifest["source_proof"] == expected_source_proof,
                "manifest source-proof record mismatch")
        require(manifest["xdvdfs"] == expected_xdvdfs,
                "manifest XDVDFS record mismatch")
        require(manifest["xbe"] == expected_xbe,
                "manifest XBE record mismatch")
        require(manifest["patch"] == expected_patch,
                "manifest patch record mismatch")
        output_record = manifest["output"]
        require(output_record == {
            "path": str(output), "size": output_info.st_size,
            "sha256": output_sha,
            "copy_method": output_record.get("copy_method"),
            "exclusively_created": True, "distinct_from_source_inode": True,
        } and output_record.get("copy_method") in {"copy_file_range", "pread_pwrite"},
                "manifest output record mismatch")
        require(manifest["claims"] == claims, "manifest claim boundary mismatch")
        require(xbe_differences == CHANGED_XBE_OFFSETS and
                xiso_format.sha256_fd(source_fd) == expected_source_sha and
                xiso_format.path_identity(source) == source_identity and
                xiso_format.path_identity(output) == output_identity and
                xiso_format.path_identity(manifest_file) is not None,
                "an input changed during independent verification")
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
        "source_profile_volume9_sha256": source_pack9_sha,
        "source_default_xbe_sha256": source_xbe_record["xbe_sha256"],
        "output_default_xbe_sha256": output_xbe_record["xbe_sha256"],
        "text_section_digest_exact": True,
        "rsa_signed_header_chain_preserved": False,
        "weather_dataflow_preserved": True,
        "xdvdfs_tree_exact": True,
        "source_unchanged": True,
        "xemu_boot_acceptance_proved": False,
        "xemu_target_outer_loaded_proved": False,
        "xemu_geometry_visibility_proved": False,
        "hardware_proved": False,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-profile", required=True, choices=sorted(SOURCE_PROFILES))
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--source-visibility-manifest", required=True, type=Path)
    parser.add_argument("--visibility-base-xiso", required=True, type=Path)
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
        args.source_profile, args.source_xiso,
        args.source_visibility_manifest, args.visibility_base_xiso,
        args.source_dispatch_manifest, args.dispatch_base_xiso,
        args.output_xiso, args.manifest,
        source_geometry_manifest_path=args.source_geometry_manifest,
        retail_xiso_path=args.retail_xiso, index_path=args.index,
        recipe_path=args.recipe, geometry_output_dir=args.geometry_output_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, xiso_format.PatchError, KeyError,
            json.JSONDecodeError, struct.error, SyntaxError) as exc:
        raise SystemExit(f"error: {exc}") from exc
