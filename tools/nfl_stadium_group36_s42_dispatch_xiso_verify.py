#!/usr/bin/env python3
"""Independently verify the diagnostic NFL group36 ``s18`` -> ``s42`` shim.

This verifier imports neither the shim writer nor a roster writer.  It parses
both complete XISOs, re-derives the two-byte image difference set, validates
the ROST relative pointer and allocation directly, and proves that the chosen
pinned source-profile volume 9 remains byte-exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

import nfl_stadium_group36_geometry_xiso_verify as geometry_transport_verify
import nfl_uniform_color_xiso_direct_patch as xiso_format


VERIFY_SCHEMA = "nfl2k5_group36_s42_dispatch_xiso_verify/v1"
MANIFEST_SCHEMA = "nfl2k5_group36_s42_dispatch_xiso_patch/v1"
GEOMETRY_MANIFEST_SCHEMA = "nfl2k5_group36_geometry_xiso_patch/v1"
RETAIL_XISO_SHA256 = xiso_format.EXPECTED_XISO_SHA256
RETAIL_VOLUME9_SHA256 = "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a"
EXPANDED_WALL_XISO_SHA256 = "a17ce0bd1f37d3c361245334586346a5f43b5a9374ffe05fe5e41b101a10137c"
EXPANDED_WALL_MANIFEST_SHA256 = "80a5361c8b514f7215683d7ae7afdf91a365f4ac64d1736ba76ba349c9d69f95"
EXPANDED_WALL_VOLUME9_SHA256 = "c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad"
EXPANDED_WALL_RECIPE_SHA256 = "3ee45f7b36fae28e51814e7695dc9bbd20d3ea4ac3a722ca53e9bf1264639625"
EXPANDED_WALL_NATIVE_MANIFEST_SHA256 = "8d5454101129b8fc626cb42ac238ca49c6b39a4c0bdd52649fb1eba0a62d6417"
SOURCE_PROFILES = {
    "retail_control": {
        "source_sha256": RETAIL_XISO_SHA256,
        "volume9_sha256": RETAIL_VOLUME9_SHA256,
    },
    "expanded_wall": {
        "source_sha256": EXPANDED_WALL_XISO_SHA256,
        "volume9_sha256": EXPANDED_WALL_VOLUME9_SHA256,
    },
}
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
PACK0_PATH = "vc_53450030/0"
PACK0_SECTOR = 796_479
PACK0_SIZE = 193_710_080
PACK9_PATH = "vc_53450030/9"
PACK9_SECTOR = 35_531
PACK9_SIZE = 634_941_440
FILE_COUNT = 19

ROST_OUTER = 0x00392800
ROST_WRAPPER_SIZE = 0x20
ROST_BODY_SIZE = 593_760
ROST_ROOT = 0x40
STADIUM_COUNT = 82
STADIUM_TABLE = 0xB0
STADIUM_STRIDE = 0x80
STADIUM_INDEX = 18
STADIUM_RECORD = 0x9B0
ASSET_POINTER_FIELD = 0x9BC
ASSET_STRING = 0x76122
ASSET_BEFORE = ("s18\0").encode("utf-16le")
ASSET_AFTER = ("s42\0").encode("utf-16le")
CHANGED_RELATIVE = [2, 4]
BODY_ABSOLUTE = 0x61732020
STRING_ABSOLUTE = 0x617A8142
CHANGED_ABSOLUTE = [0x617A8144, 0x617A8146]
MAX_JSON = 64 * 1024


class DispatchVerifyError(ValueError):
    """The diagnostic copied XISO violates the independent v1 contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DispatchVerifyError(message)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def open_regular(path: Path, label: str) -> tuple[Path, int, tuple[int, int]]:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise DispatchVerifyError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    opened = os.fstat(descriptor)
    require(stat.S_ISREG(opened.st_mode), f"{label} descriptor is not regular")
    identity = xiso_format.fd_identity(descriptor)
    require(xiso_format.path_identity(resolved) == identity,
            f"{label} pathname changed after open")
    return resolved, descriptor, identity


def read_json(path: Path, label: str, expected_hash: str | None = None) -> tuple[Path, dict[str, object], str]:
    resolved, descriptor, identity = open_regular(path, label)
    try:
        size = os.fstat(descriptor).st_size
        require(0 < size <= MAX_JSON, f"{label} size is outside the v1 limit")
        raw = xiso_format.read_exact(descriptor, 0, size)
        digest = hashlib.sha256(raw).hexdigest()
        if expected_hash is not None:
            require(digest == expected_hash, f"{label} SHA-256 mismatch")
        value = json.loads(raw)
        require(raw == canonical_json(value), f"{label} is not canonical JSON")
        require(xiso_format.path_identity(resolved) == identity,
                f"{label} pathname changed during read")
        return resolved, value, digest
    finally:
        os.close(descriptor)


def resolve_pointer(body: bytes, field: int, label: str) -> int:
    require(0 <= field <= len(body) - 4, f"{label} pointer field outside body")
    value = struct.unpack_from("<i", body, field)[0]
    require(value != 0, f"{label} pointer is null")
    target = field + value - 1
    require(0 <= target < len(body), f"{label} pointer resolves outside body")
    return target


def validate_roster(fd: int, pack0_offset: int, expected_asset: bytes) -> dict[str, object]:
    wrapper_absolute = pack0_offset + ROST_OUTER
    wrapper = xiso_format.read_exact(fd, wrapper_absolute, ROST_WRAPPER_SIZE)
    require(struct.unpack("<4s7I", wrapper) ==
            (b"ROST", ROST_BODY_SIZE, ROST_BODY_SIZE, 0, 0, 0, 0, 0),
            "main ROST wrapper mismatch")
    body_absolute = wrapper_absolute + ROST_WRAPPER_SIZE
    require(body_absolute == BODY_ABSOLUTE, "ROST body absolute offset changed")
    body = xiso_format.read_exact(fd, body_absolute, ROST_BODY_SIZE)
    require(body[:12] == b"\0" * 12 and body[0x0C:0x10] == b"ROST" and
            struct.unpack_from("<I", body, 0x10)[0] == 17,
            "main ROST fixed header mismatch")
    require(resolve_pointer(body, 0x14, "root") == ROST_ROOT,
            "main ROST root offset mismatch")
    require(struct.unpack_from("<I", body, ROST_ROOT + 0x10)[0] == STADIUM_COUNT,
            "main ROST stadium count mismatch")
    require(resolve_pointer(body, ROST_ROOT + 0x14, "stadium table") == STADIUM_TABLE,
            "main ROST stadium table offset mismatch")
    require(STADIUM_RECORD == STADIUM_TABLE + STADIUM_INDEX * STADIUM_STRIDE and
            STADIUM_TABLE + STADIUM_COUNT * STADIUM_STRIDE <= len(body),
            "stadium table arithmetic mismatch")
    require(resolve_pointer(body, ASSET_POINTER_FIELD, "stadium 18 asset code") == ASSET_STRING,
            "stadium 18 asset-code pointer target mismatch")
    require(body[ASSET_STRING:ASSET_STRING + len(expected_asset)] == expected_asset,
            "stadium 18 asset-code bytes mismatch")
    references = []
    for field in range(0, len(body) - 3, 4):
        value = struct.unpack_from("<i", body, field)[0]
        if value and field + value - 1 == ASSET_STRING:
            references.append(field)
    require(references == [ASSET_POINTER_FIELD],
            "stadium 18 asset-code target is not uniquely referenced")
    require(body_absolute + ASSET_STRING == STRING_ABSOLUTE,
            "stadium 18 asset-code absolute offset mismatch")
    return {
        "wrapper_absolute_offset": wrapper_absolute,
        "wrapper_size": ROST_WRAPPER_SIZE,
        "body_absolute_offset": body_absolute,
        "body_size": ROST_BODY_SIZE,
        "root_offset": ROST_ROOT,
        "stadium_count": STADIUM_COUNT,
        "stadium_table_offset": STADIUM_TABLE,
        "stadium_stride": STADIUM_STRIDE,
        "stadium_index": STADIUM_INDEX,
        "stadium_record_offset": STADIUM_RECORD,
        "asset_pointer_field_offset": ASSET_POINTER_FIELD,
        "asset_string_body_offset": ASSET_STRING,
        "asset_string_absolute_offset": STRING_ABSOLUTE,
        "unique_aligned_relative_pointer_fields": references,
        "asset_code": expected_asset[:-2].decode("utf-16le"),
    }


def prepare_source_profile(
    source_profile: str,
    source: Path,
    source_geometry_manifest_path: Path | None,
    retail_xiso_path: Path | None,
    index_path: Path | None,
    recipe_path: Path | None,
    geometry_output_dir: Path | None,
) -> tuple[str, str, dict[str, object], Path | None]:
    require(source_profile in SOURCE_PROFILES, "unknown source profile")
    profile = SOURCE_PROFILES[source_profile]
    if source_profile == "retail_control":
        require(all(value is None for value in (
            source_geometry_manifest_path, retail_xiso_path, index_path,
            recipe_path, geometry_output_dir,
        )), "retail_control forbids geometry-proof arguments")
        return str(profile["source_sha256"]), str(profile["volume9_sha256"]), {
            "kind": "pinned retail dispatch-only control",
            "independent_geometry_xiso_verifier_ran": False,
            "retail_xiso_sha256": RETAIL_XISO_SHA256,
            "source_volume9_sha256": RETAIL_VOLUME9_SHA256,
        }, None

    require(all(value is not None for value in (
        source_geometry_manifest_path, retail_xiso_path, index_path,
        recipe_path, geometry_output_dir,
    )), "expanded_wall requires manifest, retail XISO, index, recipe, and geometry output")
    assert source_geometry_manifest_path is not None
    assert retail_xiso_path is not None
    assert index_path is not None
    assert recipe_path is not None
    assert geometry_output_dir is not None
    geometry_manifest, geometry_proof, geometry_manifest_sha = read_json(
        source_geometry_manifest_path, "expanded-wall geometry XISO manifest",
        EXPANDED_WALL_MANIFEST_SHA256,
    )
    require(geometry_proof.get("schema") == GEOMETRY_MANIFEST_SCHEMA and
            Path(geometry_proof["output"]["path"]).resolve(strict=True) == source and
            geometry_proof["output"]["sha256"] == EXPANDED_WALL_XISO_SHA256 and
            geometry_proof["native_geometry_proof"]["changed_volume_sha256"] ==
            EXPANDED_WALL_VOLUME9_SHA256 and
            geometry_proof["native_geometry_proof"]["recipe_sha256"] ==
            EXPANDED_WALL_RECIPE_SHA256 and
            geometry_proof["native_geometry_proof"]["geometry_manifest_sha256"] ==
            EXPANDED_WALL_NATIVE_MANIFEST_SHA256,
            "expanded-wall geometry manifest proof mismatch")
    verification = geometry_transport_verify.verify(
        retail_xiso_path, index_path, recipe_path, geometry_output_dir,
        source, geometry_manifest,
    )
    require(verification["output_xiso_sha256"] == EXPANDED_WALL_XISO_SHA256 and
            verification["changed_volume_sha256"] == EXPANDED_WALL_VOLUME9_SHA256 and
            verification["xemu_geometry_visibility_proved"] is False,
            "independent expanded-wall XISO verification result mismatch")
    retail = open_regular(retail_xiso_path, "retail proof XISO")
    os.close(retail[1])
    return str(profile["source_sha256"]), str(profile["volume9_sha256"]), {
        "kind": "pinned independently verified expanded-wall geometry diagnostic",
        "independent_geometry_xiso_verifier_ran": True,
        "independent_verifier_schema": verification["schema"],
        "geometry_xiso_manifest_path": str(geometry_manifest),
        "geometry_xiso_manifest_sha256": geometry_manifest_sha,
        "geometry_xiso_manifest_schema": GEOMETRY_MANIFEST_SCHEMA,
        "retail_xiso_path": str(retail[0]),
        "retail_xiso_sha256": RETAIL_XISO_SHA256,
        "native_geometry_volume9_sha256": EXPANDED_WALL_VOLUME9_SHA256,
        "recipe_sha256": EXPANDED_WALL_RECIPE_SHA256,
        "native_geometry_manifest_sha256": EXPANDED_WALL_NATIVE_MANIFEST_SHA256,
        "geometry_transport_changed_byte_count": verification["changed_byte_count"],
        "geometry_transport_changed_run_count": verification["changed_run_count"],
    }, geometry_manifest


def verify(
    source_profile: str,
    source_xiso_path: Path,
    output_xiso_path: Path,
    manifest_path: Path,
    *,
    source_geometry_manifest_path: Path | None = None,
    retail_xiso_path: Path | None = None,
    index_path: Path | None = None,
    recipe_path: Path | None = None,
    geometry_output_dir: Path | None = None,
) -> dict[str, object]:
    output_manifest, manifest, manifest_sha = read_json(
        manifest_path, "dispatch writer manifest"
    )
    require(manifest.get("schema") == MANIFEST_SCHEMA and set(manifest) == {
        "schema", "source_profile", "source", "source_proof", "xdvdfs",
        "roster", "patch", "output", "claims",
    }, "dispatch manifest root/schema mismatch")
    require(manifest["source_profile"] == source_profile,
            "dispatch manifest source profile mismatch")

    source, source_fd, source_identity = open_regular(source_xiso_path, "pinned source XISO")
    output, output_fd, output_identity = open_regular(output_xiso_path, "dispatch output XISO")
    try:
        expected_source_sha, expected_volume9_sha, expected_source_proof, proof_manifest = (
            prepare_source_profile(
                source_profile, source, source_geometry_manifest_path,
                retail_xiso_path, index_path, recipe_path, geometry_output_dir,
            )
        )
        source_info = os.fstat(source_fd)
        output_info = os.fstat(output_fd)
        require(source_identity != output_identity, "source and output alias an inode")
        require(source_info.st_size == output_info.st_size == xiso_format.EXPECTED_XISO_SIZE,
                "source/output XISO size mismatch")

        source_entries, source_directory = xiso_format.parse_xdvdfs(source_fd, source_info.st_size)
        output_entries, output_directory = xiso_format.parse_xdvdfs(output_fd, output_info.st_size)
        require(output_directory == source_directory and output_entries == source_entries,
                "XDVDFS tree or extents differ")
        files = [entry for entry in source_entries.values() if not (entry.attributes & 0x10)]
        require(len(files) == FILE_COUNT, "XDVDFS file count mismatch")
        pack0 = source_entries.get(PACK0_PATH.casefold())
        pack9 = source_entries.get(PACK9_PATH.casefold())
        xbe = source_entries.get("default.xbe")
        require(pack0 is not None and (pack0.sector, pack0.size) ==
                (PACK0_SECTOR, PACK0_SIZE), "volume 0 extent mismatch")
        require(pack9 is not None and (pack9.sector, pack9.size) ==
                (PACK9_SECTOR, PACK9_SIZE), "volume 9 extent mismatch")
        require(xbe is not None and xbe.size == xiso_format.EXPECTED_XBE_SIZE,
                "default.xbe extent mismatch")

        source_roster = validate_roster(source_fd, pack0.byte_offset, ASSET_BEFORE)
        output_roster = validate_roster(output_fd, pack0.byte_offset, ASSET_AFTER)
        require({**source_roster, "asset_code": "s42"} == output_roster,
                "ROST structure changed outside the asset string")
        source_sha, output_sha, differences = xiso_format.compare_and_hash(
            source_fd, output_fd, source_info.st_size, set(CHANGED_ABSOLUTE)
        )
        require(source_sha == expected_source_sha,
                "source-profile XISO SHA-256 mismatch")
        require(differences == CHANGED_ABSOLUTE,
                "complete-image two-byte difference ledger mismatch")
        source_pack0_sha = xiso_format.sha256_fd(source_fd, pack0.byte_offset, pack0.size)
        output_pack0_sha = xiso_format.sha256_fd(output_fd, pack0.byte_offset, pack0.size)
        require(source_pack0_sha == PACK0_SHA256 and output_pack0_sha != source_pack0_sha,
                "volume 0 source/output hashes violate the shim contract")
        require(xiso_format.sha256_fd(source_fd, pack9.byte_offset, pack9.size) ==
                xiso_format.sha256_fd(output_fd, pack9.byte_offset, pack9.size) ==
                expected_volume9_sha, "source-profile volume 9 changed")
        require(xiso_format.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                xiso_format.sha256_fd(output_fd, xbe.byte_offset, xbe.size) ==
                xiso_format.EXPECTED_XBE_SHA256, "default.xbe changed")

        expected_source = {
            "path": str(source), "size": source_info.st_size,
            "sha256_before": source_sha, "sha256_after": source_sha,
            "opened_read_only": True, "modified": False,
            "exact_pinned_profile_artifact": True,
        }
        expected_xdvdfs = {
            **source_directory, "file_count": len(files),
            "tree_identical_after_patch": True,
            "all_sector_extents_preserved": True,
            "pack0_sector": pack0.sector, "pack0_size": pack0.size,
            "pack9_sector": pack9.sector, "pack9_size": pack9.size,
            "default_xbe_sha256": xiso_format.EXPECTED_XBE_SHA256,
            "source_profile_volume9_sha256": expected_volume9_sha,
        }
        expected_roster = {
            **output_roster,
            "source_pack0_sha256": source_pack0_sha,
            "output_pack0_sha256": output_pack0_sha,
            "record_and_all_relative_pointers_bit_exact": True,
            "allocation_size_unchanged": True,
        }
        expected_patch = {
            "purpose": "diagnostic runtime dispatch shim only",
            "before": "s18", "after": "s42",
            "written_allocation_bytes": len(ASSET_AFTER),
            "changed_relative_bytes": CHANGED_RELATIVE,
            "allowed_changed_byte_offsets": CHANGED_ABSOLUTE,
            "actual_changed_byte_offsets": differences,
            "actual_changed_byte_count": 2,
            "all_other_xiso_bytes_identical": True,
            "loader_static_witness": {
                "active_stadium_accessor": "0x00077460",
                "asset_code_read": "0x00062c76 MOV EDX,[EAX+0x0c]",
                "filename_format_callsite": "0x00062c82",
                "filename_format": "%s%c%c.iff",
                "night_clear_expected_outer": "s42nd.iff",
            },
        }
        claims = {
            "diagnostic_only": True,
            "layout_identical_copy_only_xiso": True,
            "offline_two_byte_dispatch_shim_proved": True,
            "source_geometry_volume9_preserved": True,
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
        require(manifest["roster"] == expected_roster,
                "manifest ROST record mismatch")
        require(manifest["patch"] == expected_patch,
                "manifest patch record mismatch")
        output_record = manifest["output"]
        require(output_record == {
            "path": str(output), "size": output_info.st_size,
            "sha256": output_sha, "copy_method": output_record.get("copy_method"),
            "exclusively_created": True, "distinct_from_source_inode": True,
        } and output_record.get("copy_method") in {"copy_file_range", "pread_pwrite"},
                "manifest output record mismatch")
        require(manifest["claims"] == claims, "manifest claim boundary mismatch")
        require(xiso_format.sha256_fd(source_fd) == expected_source_sha and
                xiso_format.path_identity(source) == source_identity and
                xiso_format.path_identity(output) == output_identity,
                "an XISO changed during independent verification")
        require(xiso_format.path_identity(output_manifest) is not None and
                (proof_manifest is None or
                 xiso_format.path_identity(proof_manifest) is not None),
                "a manifest pathname disappeared during verification")
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
        "source_profile_volume9_sha256": expected_volume9_sha,
        "xdvdfs_tree_exact": True,
        "default_xbe_exact": True,
        "roster_pointer_and_allocation_exact": True,
        "source_unchanged": True,
        "xemu_target_outer_loaded_proved": False,
        "xemu_geometry_visibility_proved": False,
        "hardware_proved": False,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-profile", required=True, choices=sorted(SOURCE_PROFILES))
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--source-geometry-manifest", type=Path)
    parser.add_argument("--retail-xiso", type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--recipe", type=Path)
    parser.add_argument("--geometry-output-dir", type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    result = verify(
        args.source_profile, args.source_xiso, args.output_xiso, args.manifest,
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
            json.JSONDecodeError, struct.error) as exc:
        raise SystemExit(f"error: {exc}") from exc
