#!/usr/bin/env python3
"""Create a diagnostic s42 XISO whose stadium time suffix is always ``n``.

The accepted inputs are the two pinned, independently verified s42-visible
dispatch images.  A complete layout-identical copy is made, the one-byte displacement
of the conditional jump at XBE VA 0x00062C60 is changed from ``+5`` to ``+0``,
and the owning ``.text`` section SHA-1 field is recomputed.  This is a global
but control-flow-preserving diagnostic
for the stadium outer-name path, not a production executable patch.
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

import nfl_stadium_group36_s42_visibility_unlock_xiso_verify as visibility_verify
import nfl_uniform_color_xiso_direct_patch as xiso


SCHEMA = "nfl2k5_group36_s42_force_n_xiso_patch/v1"
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
TEXT_SECTION_INDEX = 0
TEXT_SECTION_HEADER = 0x370
TEXT_SECTION_DIGEST = 0x394
TEXT_VA = 0x00011000
TEXT_VSIZE = 0x0040F114
TEXT_RAW = 0x00001000
TEXT_RAW_SIZE = 0x0040F114
TEXT_SOURCE_DIGEST = bytes.fromhex("72edb599858a06a0f88c6ae446907e3977f4fec6")
TEXT_OUTPUT_DIGEST = bytes.fromhex("a013179864b328a3bda23b60f4cee9b9ed7dcc9d")
XBE_SIGNED_HEADER_SOURCE_SHA1 = "85c32209d9479a93af52b03efc83ee92dec28d26"
XBE_SIGNED_HEADER_OUTPUT_SHA1 = "80c507386b62ac1dddb4dc21750355ee5861babc"
XBE_RSA_SIGNATURE_SHA256 = "4648f39dab19e1108e68daf993f72db693eed9f1db96d22bde7cdfcff661f107"

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
TIME_BRANCH_BEFORE = b"\x74\x05"       # JZ 0x00062C67
TIME_BRANCH_AFTER = b"\x74\x00"        # JZ 0x00062C62 (fall-through target)
TIME_DISPLACEMENT_XBE_OFFSET = TIME_BRANCH_XBE_OFFSET + 1
TIME_DISPLACEMENT_BEFORE = b"\x05"
TIME_DISPLACEMENT_AFTER = b"\x00"
TIME_CONTEXT_OFFSET = 0x00052C50
TIME_CONTEXT_BEFORE = bytes.fromhex(
    "85c07405bf61000000e8d204080085c07405bf6e000000668974240e66897c24"
)
TIME_CONTEXT_AFTER = bytearray(TIME_CONTEXT_BEFORE)
TIME_CONTEXT_AFTER[TIME_BRANCH_XBE_OFFSET - TIME_CONTEXT_OFFSET:
                   TIME_BRANCH_XBE_OFFSET - TIME_CONTEXT_OFFSET + 2] = TIME_BRANCH_AFTER
TIME_CONTEXT_AFTER = bytes(TIME_CONTEXT_AFTER)

DEFAULT_XBE_ABSOLUTE = DEFAULT_XBE_SECTOR * xiso.SECTOR_SIZE
DIGEST_ABSOLUTE = DEFAULT_XBE_ABSOLUTE + TEXT_SECTION_DIGEST
BRANCH_ABSOLUTE = DEFAULT_XBE_ABSOLUTE + TIME_BRANCH_XBE_OFFSET
DISPLACEMENT_ABSOLUTE = DEFAULT_XBE_ABSOLUTE + TIME_DISPLACEMENT_XBE_OFFSET
EXPECTED_CHANGED_ABSOLUTE = (
    list(range(DIGEST_ABSOLUTE, DIGEST_ABSOLUTE + len(TEXT_OUTPUT_DIGEST))) +
    [DISPLACEMENT_ABSOLUTE]
)
S42_ASSET_ABSOLUTE = 0x617A8142
S42_ASSET_BYTES = ("s42\0").encode("utf-16le")
MAX_JSON = 64 * 1024


class ForceNPatchError(ValueError):
    """The requested diagnostic violates the pinned global-force-n contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ForceNPatchError(message)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def regular(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ForceNPatchError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def xbe_sha1(payload: bytes) -> str:
    """Return the XBE length-framed SHA-1 used by section/header records."""

    return hashlib.sha1(struct.pack("<I", len(payload)) + payload).hexdigest()  # nosec B324


def cstring(payload: bytes, offset: int, maximum: int = 64) -> str:
    require(0 <= offset < len(payload), "XBE section name offset is outside file")
    end = payload.find(b"\0", offset, min(len(payload), offset + maximum))
    require(end >= 0, "XBE section name is unterminated")
    try:
        return payload[offset:end].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ForceNPatchError("XBE section name is not ASCII") from exc


def validate_xbe(payload: bytes, *, patched: bool) -> dict[str, object]:
    require(len(payload) == DEFAULT_XBE_SIZE and payload[:4] == b"XBEH",
            "default.xbe size or magic mismatch")
    image_base, headers_size = struct.unpack_from("<II", payload, 0x104)
    section_count, section_table_va = struct.unpack_from("<II", payload, 0x11C)
    require((image_base, headers_size, section_count, section_table_va) ==
            (XBE_IMAGE_BASE, XBE_HEADERS_SIZE, XBE_SECTION_COUNT,
             XBE_IMAGE_BASE + XBE_SECTION_TABLE),
            "default.xbe fixed header boundary mismatch")
    header_offset = section_table_va - image_base
    require(header_offset == TEXT_SECTION_HEADER and
            header_offset + XBE_SECTION_COUNT * XBE_SECTION_HEADER_SIZE <= headers_size,
            "default.xbe section table boundary mismatch")
    fields = struct.unpack_from("<9I20s", payload, header_offset)
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
    require(TEXT_VA + TIME_BRANCH_XBE_OFFSET - TEXT_RAW == TIME_BRANCH_VA,
            "XBE VA/file mapping arithmetic mismatch")
    expected_context = TIME_CONTEXT_AFTER if patched else TIME_CONTEXT_BEFORE
    expected_branch = TIME_BRANCH_AFTER if patched else TIME_BRANCH_BEFORE
    expected_digest = TEXT_OUTPUT_DIGEST if patched else TEXT_SOURCE_DIGEST
    expected_xbe_sha = DEFAULT_XBE_OUTPUT_SHA256 if patched else DEFAULT_XBE_SOURCE_SHA256
    expected_header_sha = (
        XBE_SIGNED_HEADER_OUTPUT_SHA1 if patched else XBE_SIGNED_HEADER_SOURCE_SHA1
    )
    require(payload[TIME_CONTEXT_OFFSET:TIME_CONTEXT_OFFSET + len(expected_context)] ==
            expected_context and
            payload.count(expected_context) == 1 and
            payload[TIME_BRANCH_XBE_OFFSET:TIME_BRANCH_XBE_OFFSET + 2] == expected_branch,
            "stadium time-suffix instruction context mismatch or is not unique")
    stored_digest = payload[TEXT_SECTION_DIGEST:TEXT_SECTION_DIGEST + 20]
    computed_digest = bytes.fromhex(xbe_sha1(payload[TEXT_RAW:TEXT_RAW + TEXT_RAW_SIZE]))
    require(stored_digest == computed_digest == expected_digest,
            "default.xbe .text stored/recomputed digest mismatch")
    require(xbe_sha1(payload[0x104:headers_size]) == expected_header_sha,
            "default.xbe signed-header digest mismatch")
    require(hashlib.sha256(payload[4:0x104]).hexdigest() == XBE_RSA_SIGNATURE_SHA256,
            "default.xbe RSA signature bytes changed")
    require(hashlib.sha256(payload).hexdigest() == expected_xbe_sha,
            "default.xbe complete SHA-256 mismatch")
    return {
        "section_index": TEXT_SECTION_INDEX,
        "section_name": name,
        "section_header_file_offset": header_offset,
        "section_virtual_address": TEXT_VA,
        "section_virtual_size": TEXT_VSIZE,
        "section_raw_file_offset": TEXT_RAW,
        "section_raw_size": TEXT_RAW_SIZE,
        "section_digest_file_offset": TEXT_SECTION_DIGEST,
        "section_digest": stored_digest.hex(),
        "time_branch_virtual_address": TIME_BRANCH_VA,
        "time_branch_file_offset": TIME_BRANCH_XBE_OFFSET,
        "time_branch_bytes": expected_branch.hex(),
        "signed_header_sha1": expected_header_sha,
        "rsa_signature_sha256": XBE_RSA_SIGNATURE_SHA256,
        "visibility_unlock_virtual_address": S42_UNLOCK_VA,
        "visibility_unlock_file_offset": S42_UNLOCK_XBE_OFFSET,
        "visibility_unlock_bytes": S42_UNLOCK_VISIBLE_BYTES.hex(),
        "data_section_digest": data_stored_digest.hex(),
        "xbe_sha256": expected_xbe_sha,
    }


def make_patched_xbe(source: bytes) -> tuple[bytes, dict[str, object]]:
    source_info = validate_xbe(source, patched=False)
    patched = bytearray(source)
    patched[TIME_DISPLACEMENT_XBE_OFFSET] = TIME_DISPLACEMENT_AFTER[0]
    digest = bytes.fromhex(xbe_sha1(bytes(patched[TEXT_RAW:TEXT_RAW + TEXT_RAW_SIZE])))
    require(digest == TEXT_OUTPUT_DIGEST and
            sum(a != b for a, b in zip(TEXT_SOURCE_DIGEST, digest)) == 20,
            "recomputed .text digest changed outside the pinned contract")
    patched[TEXT_SECTION_DIGEST:TEXT_SECTION_DIGEST + 20] = digest
    output = bytes(patched)
    output_info = validate_xbe(output, patched=True)
    differences = [index for index, pair in enumerate(zip(source, output))
                   if pair[0] != pair[1]]
    expected = list(range(TEXT_SECTION_DIGEST, TEXT_SECTION_DIGEST + 20)) + [
        TIME_DISPLACEMENT_XBE_OFFSET,
    ]
    require(differences == expected, "patched XBE difference set mismatch")
    return output, {"source": source_info, "output": output_info,
                    "changed_xbe_offsets": differences}


def write_manifest(owned: xiso.OwnedFile, value: dict[str, object]) -> None:
    payload = canonical_json(value)
    require(xiso.owned_path_matches(owned), "manifest pathname changed before write")
    position = 0
    while position < len(payload):
        written = os.pwrite(owned.descriptor, payload[position:], position)
        require(written > 0, "short manifest write")
        position += written
    os.ftruncate(owned.descriptor, len(payload))
    os.fsync(owned.descriptor)
    require(xiso.read_exact(owned.descriptor, 0, len(payload)) == payload,
            "manifest readback mismatch")


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
    source_visibility_manifest = regular(
        source_visibility_manifest_path, "source s42 visibility manifest"
    )
    visibility_base_xiso = regular(
        visibility_base_xiso_path, "visibility base s42 XISO"
    )
    manifest_raw = source_visibility_manifest.read_bytes()
    require(0 < len(manifest_raw) <= MAX_JSON and
            hashlib.sha256(manifest_raw).hexdigest() ==
            profile["visibility_manifest_sha256"],
            "source s42 visibility manifest size or SHA-256 mismatch")

    if source_profile == "s42_control":
        require(all(value is None for value in (
            source_geometry_manifest_path, retail_xiso_path, index_path,
            recipe_path, geometry_output_dir,
        )), "s42_control forbids expanded-wall proof arguments")
        verification = visibility_verify.verify(
            source_profile, visibility_base_xiso, source_dispatch_manifest_path,
            dispatch_base_xiso_path, source, source_visibility_manifest,
        )
    else:
        require(all(value is not None for value in (
            source_geometry_manifest_path, retail_xiso_path, index_path,
            recipe_path, geometry_output_dir,
        )), "s42_expanded_wall requires all geometry source-proof arguments")
        verification = visibility_verify.verify(
            source_profile, visibility_base_xiso, source_dispatch_manifest_path,
            dispatch_base_xiso_path, source, source_visibility_manifest,
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
        "visibility_base_xiso_path": str(visibility_base_xiso),
        "source_visibility_manifest_path": str(source_visibility_manifest),
        "source_visibility_manifest_sha256": profile["visibility_manifest_sha256"],
        "source_visibility_output_sha256": verification["output_xiso_sha256"],
        "source_visibility_changed_byte_count": verification["changed_byte_count"],
        "source_visibility_default_xbe_sha256":
            verification["default_xbe_output_sha256"],
        "source_visibility_selectability_runtime_proved": False,
        "source_visibility_target_outer_runtime_proved": False,
    })


def run(
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
    source = regular(source_xiso_path, "pinned s42 source XISO")
    (expected_source_sha, expected_output_sha, expected_pack9_sha,
     source_proof) = prepare_source_profile(
        source_profile, source, source_visibility_manifest_path,
        visibility_base_xiso_path, source_dispatch_manifest_path,
        dispatch_base_xiso_path, source_geometry_manifest_path, retail_xiso_path,
        index_path, recipe_path, geometry_output_dir,
    )
    output = xiso.canonical_new_path(output_xiso_path)
    manifest = xiso.canonical_new_path(manifest_path)
    require(not output.exists() and not manifest.exists(),
            "output XISO and manifest must both be new paths")
    require(len({source, output, manifest}) == 3,
            "source, output, and manifest paths must be distinct")

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    output_owned: xiso.OwnedFile | None = None
    manifest_owned: xiso.OwnedFile | None = None
    success = False
    try:
        source_info = os.fstat(source_fd)
        require(stat.S_ISREG(source_info.st_mode) and
                source_info.st_size == xiso.EXPECTED_XISO_SIZE,
                "source XISO size/type mismatch")
        source_identity = xiso.fd_identity(source_fd)
        require(xiso.path_identity(source) == source_identity,
                "source pathname changed after open")
        source_sha_before = xiso.sha256_fd(source_fd)
        require(source_sha_before == expected_source_sha,
                "source-profile s42 XISO SHA-256 mismatch")

        entries, directory = xiso.parse_xdvdfs(source_fd, source_info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        pack0 = entries.get(PACK0_PATH.casefold())
        pack9 = entries.get(PACK9_PATH.casefold())
        xbe_entry = entries.get("default.xbe")
        require(len(files) == FILE_COUNT and
                pack0 is not None and (pack0.sector, pack0.size) ==
                (PACK0_SECTOR, PACK0_SIZE) and
                pack9 is not None and (pack9.sector, pack9.size) ==
                (PACK9_SECTOR, PACK9_SIZE) and
                xbe_entry is not None and (xbe_entry.sector, xbe_entry.size) ==
                (DEFAULT_XBE_SECTOR, DEFAULT_XBE_SIZE),
                "source XDVDFS fixed extents mismatch")
        require(xbe_entry.byte_offset == DEFAULT_XBE_ABSOLUTE,
                "default.xbe absolute extent moved")
        source_pack0_sha = xiso.sha256_fd(source_fd, pack0.byte_offset, pack0.size)
        source_pack9_sha = xiso.sha256_fd(source_fd, pack9.byte_offset, pack9.size)
        require(source_pack0_sha == S42_PACK0_SHA256 and
                source_pack9_sha == expected_pack9_sha and
                xiso.read_exact(source_fd, S42_ASSET_ABSOLUTE, len(S42_ASSET_BYTES)) ==
                S42_ASSET_BYTES,
                "source s42 roster/geometry profile mismatch")
        source_xbe = xiso.read_exact(source_fd, xbe_entry.byte_offset, xbe_entry.size)
        patched_xbe, xbe_patch = make_patched_xbe(source_xbe)
        require(xbe_patch["changed_xbe_offsets"] ==
                [*range(TEXT_SECTION_DIGEST, TEXT_SECTION_DIGEST + 20),
                 TIME_DISPLACEMENT_XBE_OFFSET],
                "XBE changed-offset contract mismatch")

        allowed = set(EXPECTED_CHANGED_ABSOLUTE)
        require(len(allowed) == 21 and sorted(allowed) == EXPECTED_CHANGED_ABSOLUTE,
                "authorized complete-image offset set mismatch")
        output_owned = xiso.reserve_file(output)
        require(output_owned.identity != source_identity, "output aliases source inode")
        copy_method = xiso.copy_fd_exact(
            source_fd, output_owned.descriptor, source_info.st_size
        )
        require(xiso.owned_path_matches(output_owned),
                "output pathname changed during copy")
        require(os.pwrite(output_owned.descriptor, TEXT_OUTPUT_DIGEST,
                          DIGEST_ABSOLUTE) == 20,
                "short .text digest write")
        require(os.pwrite(output_owned.descriptor, TIME_DISPLACEMENT_AFTER,
                          DISPLACEMENT_ABSOLUTE) == 1,
                "short time-branch displacement write")
        os.fsync(output_owned.descriptor)
        require(xiso.read_exact(output_owned.descriptor, xbe_entry.byte_offset,
                                xbe_entry.size) == patched_xbe,
                "patched default.xbe readback mismatch")

        source_sha_after, output_sha, differences = xiso.compare_and_hash(
            source_fd, output_owned.descriptor, source_info.st_size, allowed
        )
        require(source_sha_after == source_sha_before,
                "source XISO changed during write")
        require(output_sha == expected_output_sha and
                differences == EXPECTED_CHANGED_ABSOLUTE,
                "complete-image 21-byte difference ledger mismatch")
        output_entries, output_directory = xiso.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size
        )
        require(output_entries == entries and output_directory == directory,
                "XDVDFS tree or extents changed")
        output_xbe = xiso.read_exact(
            output_owned.descriptor, xbe_entry.byte_offset, xbe_entry.size
        )
        output_xbe_info = validate_xbe(output_xbe, patched=True)
        require(xiso.sha256_fd(output_owned.descriptor, pack0.byte_offset, pack0.size) ==
                source_pack0_sha and
                xiso.sha256_fd(output_owned.descriptor, pack9.byte_offset, pack9.size) ==
                source_pack9_sha and
                xiso.read_exact(output_owned.descriptor, S42_ASSET_ABSOLUTE,
                                len(S42_ASSET_BYTES)) == S42_ASSET_BYTES,
                "roster or geometry pack changed")
        require(xiso.path_identity(source) == source_identity and
                xiso.owned_path_matches(output_owned),
                "an artifact pathname changed")

        result: dict[str, object] = {
            "schema": SCHEMA,
            "source_profile": source_profile,
            "source": {
                "path": str(source), "size": source_info.st_size,
                "sha256_before": source_sha_before,
                "sha256_after": source_sha_after,
                "opened_read_only": True, "modified": False,
                "exact_pinned_s42_visibility_artifact": True,
            },
            "source_proof": source_proof,
            "xdvdfs": {
                **directory, "file_count": len(files),
                "tree_identical_after_patch": True,
                "all_sector_extents_preserved": True,
                "default_xbe_sector": xbe_entry.sector,
                "default_xbe_size": xbe_entry.size,
                "pack0_sha256": source_pack0_sha,
                "pack9_sha256": source_pack9_sha,
            },
            "xbe": {
                "source": xbe_patch["source"],
                "output": output_xbe_info,
                "instruction_patch": {
                    "scope": "global stadium outer-name time suffix in FUN_00062be0",
                    "global_not_s42_conditional": True,
                    "virtual_address": f"0x{TIME_BRANCH_VA:08x}",
                    "file_offset": f"0x{TIME_BRANCH_XBE_OFFSET:08x}",
                    "instruction_absolute_xiso_offset": f"0x{BRANCH_ABSOLUTE:08x}",
                    "changed_byte_absolute_xiso_offset": f"0x{DISPLACEMENT_ABSOLUTE:08x}",
                    "before_hex": TIME_BRANCH_BEFORE.hex(),
                    "before_instruction": "JZ 0x00062c67",
                    "after_hex": TIME_BRANCH_AFTER.hex(),
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
                    "digest_absolute_xiso_offset": f"0x{DIGEST_ABSOLUTE:08x}",
                    "digest_changed_byte_count": 20,
                    "rsa_signature_bytes_changed": False,
                    "signed_header_changed": True,
                    "existing_retail_signature_attests_modified_header": False,
                },
            },
            "patch": {
                "purpose": "diagnostic global stadium-time suffix force-n only",
                "allowed_changed_byte_offsets": EXPECTED_CHANGED_ABSOLUTE,
                "actual_changed_byte_offsets": differences,
                "actual_changed_byte_count": len(differences),
                "semantic_code_byte_count": 1,
                "required_section_digest_byte_count": 20,
                "all_other_xiso_bytes_identical": True,
            },
            "output": {
                "path": str(output), "size": source_info.st_size,
                "sha256": output_sha, "copy_method": copy_method,
                "exclusively_created": True, "distinct_from_source_inode": True,
            },
            "claims": {
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
            },
        }
        manifest_owned = xiso.reserve_file(manifest)
        write_manifest(manifest_owned, result)
        require(xiso.path_identity(source) == source_identity and
                xiso.owned_path_matches(output_owned) and
                xiso.owned_path_matches(manifest_owned),
                "an artifact pathname changed during manifest publication")
        success = True
        return result
    finally:
        os.close(source_fd)
        if output_owned is not None:
            os.close(output_owned.descriptor)
        if manifest_owned is not None:
            os.close(manifest_owned.descriptor)
        if not success:
            xiso.unlink_if_owned(manifest_owned)
            xiso.unlink_if_owned(output_owned)


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
    try:
        result = run(
            args.source_profile, args.source_xiso,
            args.source_visibility_manifest, args.visibility_base_xiso,
            args.source_dispatch_manifest, args.dispatch_base_xiso,
            args.output_xiso, args.manifest,
            source_geometry_manifest_path=args.source_geometry_manifest,
            retail_xiso_path=args.retail_xiso, index_path=args.index,
            recipe_path=args.recipe, geometry_output_dir=args.geometry_output_dir,
        )
    except (OSError, ValueError, xiso.PatchError, KeyError,
            json.JSONDecodeError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_GROUP36_S42_FORCE_N_XISO_PATCH_COMPLETE "
        f"changed={result['patch']['actual_changed_byte_count']} "
        f"output_sha256={result['output']['sha256']} runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
