#!/usr/bin/env python3
"""Create a diagnostic XISO that redirects visible stadium 18 to ``s42``.

Accepted sources are either the pinned retail control or the pinned,
independently verified expanded-wall group36 diagnostic.  The writer preserves
the selected source geometry and every disc extent, then changes the two
differing UTF-16LE code bytes in stadium 18's existing ``s18`` allocation.  It
is a runtime-dispatch witness shim, not a roster or stadium editor.
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

import nfl_stadium_group36_geometry_xiso_verify as geometry_transport_verify
import nfl_uniform_color_xiso_direct_patch as xiso


SCHEMA = "nfl2k5_group36_s42_dispatch_xiso_patch/v1"
GEOMETRY_MANIFEST_SCHEMA = "nfl2k5_group36_geometry_xiso_patch/v1"
RETAIL_XISO_SHA256 = xiso.EXPECTED_XISO_SHA256
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
STADIUM_RECORD = STADIUM_TABLE + STADIUM_INDEX * STADIUM_STRIDE
ASSET_POINTER_FIELD = STADIUM_RECORD + 0x0C
ASSET_STRING = 0x76122
ASSET_BEFORE = ("s18\0").encode("utf-16le")
ASSET_AFTER = ("s42\0").encode("utf-16le")
CHANGED_RELATIVE = [
    index for index, values in enumerate(zip(ASSET_BEFORE, ASSET_AFTER))
    if values[0] != values[1]
]
EXPECTED_BODY_ABSOLUTE = 0x61732020
EXPECTED_STRING_ABSOLUTE = 0x617A8142
EXPECTED_CHANGED_ABSOLUTE = [0x617A8144, 0x617A8146]
MAX_JSON = 64 * 1024


class DispatchPatchError(ValueError):
    """The requested diagnostic artifact violates the pinned two-byte contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DispatchPatchError(message)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def regular(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise DispatchPatchError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def read_pinned_geometry_manifest(path: Path, source: Path) -> tuple[Path, dict[str, object]]:
    manifest = regular(path, "expanded-wall geometry XISO manifest")
    raw = manifest.read_bytes()
    require(0 < len(raw) <= MAX_JSON, "geometry manifest size is outside the v1 limit")
    require(hashlib.sha256(raw).hexdigest() == EXPANDED_WALL_MANIFEST_SHA256,
            "expanded-wall geometry manifest SHA-256 mismatch")
    value = json.loads(raw)
    require(raw == canonical_json(value), "geometry manifest is not canonical JSON")
    require(value.get("schema") == GEOMETRY_MANIFEST_SCHEMA,
            "geometry manifest schema mismatch")
    require(Path(value["output"]["path"]).resolve(strict=True) == source and
            value["output"]["sha256"] == EXPANDED_WALL_XISO_SHA256,
            "geometry manifest does not own the supplied expanded-wall XISO")
    require(value["native_geometry_proof"]["changed_volume_sha256"] ==
            EXPANDED_WALL_VOLUME9_SHA256 and
            value["patch"]["output_pack_sha256"] == EXPANDED_WALL_VOLUME9_SHA256 and
            value["native_geometry_proof"]["recipe_sha256"] ==
            EXPANDED_WALL_RECIPE_SHA256 and
            value["native_geometry_proof"]["geometry_manifest_sha256"] ==
            EXPANDED_WALL_NATIVE_MANIFEST_SHA256 and
            value["patch"]["path"] == PACK9_PATH,
            "expanded-wall manifest geometry proof changed")
    return manifest, value


def resolve_pointer(body: bytes, field: int, label: str) -> int:
    require(0 <= field <= len(body) - 4, f"{label} pointer field outside ROST body")
    value = struct.unpack_from("<i", body, field)[0]
    require(value != 0, f"{label} pointer is null")
    target = field + value - 1
    require(0 <= target < len(body), f"{label} pointer resolves outside ROST body")
    return target


def validate_roster(fd: int, pack0_offset: int, expected_asset: bytes) -> dict[str, object]:
    wrapper_absolute = pack0_offset + ROST_OUTER
    wrapper = xiso.read_exact(fd, wrapper_absolute, ROST_WRAPPER_SIZE)
    require(struct.unpack("<4s7I", wrapper) ==
            (b"ROST", ROST_BODY_SIZE, ROST_BODY_SIZE, 0, 0, 0, 0, 0),
            "main ROST wrapper mismatch")
    body_absolute = wrapper_absolute + ROST_WRAPPER_SIZE
    require(body_absolute == EXPECTED_BODY_ABSOLUTE, "ROST body absolute offset changed")
    body = xiso.read_exact(fd, body_absolute, ROST_BODY_SIZE)
    require(body[:12] == b"\0" * 12 and body[0x0C:0x10] == b"ROST" and
            struct.unpack_from("<I", body, 0x10)[0] == 17,
            "main ROST fixed header mismatch")
    require(resolve_pointer(body, 0x14, "root") == ROST_ROOT,
            "main ROST root offset mismatch")
    require(struct.unpack_from("<I", body, ROST_ROOT + 0x10)[0] == STADIUM_COUNT,
            "main ROST stadium count mismatch")
    require(resolve_pointer(body, ROST_ROOT + 0x14, "stadium table") == STADIUM_TABLE,
            "main ROST stadium table offset mismatch")
    require(STADIUM_TABLE + STADIUM_COUNT * STADIUM_STRIDE <= len(body),
            "main ROST stadium table exceeds body")
    require(resolve_pointer(body, ASSET_POINTER_FIELD, "stadium 18 asset code") == ASSET_STRING,
            "stadium 18 asset-code target mismatch")
    require(body[ASSET_STRING:ASSET_STRING + len(expected_asset)] == expected_asset,
            "stadium 18 asset-code bytes mismatch")
    references = []
    for field in range(0, len(body) - 3, 4):
        value = struct.unpack_from("<i", body, field)[0]
        if value and field + value - 1 == ASSET_STRING:
            references.append(field)
    require(references == [ASSET_POINTER_FIELD],
            "stadium 18 asset-code target is not uniquely referenced")
    string_absolute = body_absolute + ASSET_STRING
    require(string_absolute == EXPECTED_STRING_ABSOLUTE,
            "stadium 18 asset-code absolute offset changed")
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
        "asset_string_absolute_offset": string_absolute,
        "unique_aligned_relative_pointer_fields": references,
        "asset_code": expected_asset[:-2].decode("utf-16le"),
    }


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
    source_geometry_manifest_path: Path | None,
    retail_xiso_path: Path | None,
    index_path: Path | None,
    recipe_path: Path | None,
    geometry_output_dir: Path | None,
) -> tuple[str, str, dict[str, object]]:
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
        }

    require(all(value is not None for value in (
        source_geometry_manifest_path, retail_xiso_path, index_path,
        recipe_path, geometry_output_dir,
    )), "expanded_wall requires manifest, retail XISO, index, recipe, and geometry output")
    assert source_geometry_manifest_path is not None
    assert retail_xiso_path is not None
    assert index_path is not None
    assert recipe_path is not None
    assert geometry_output_dir is not None
    geometry_manifest, geometry_proof = read_pinned_geometry_manifest(
        source_geometry_manifest_path, source
    )
    verification = geometry_transport_verify.verify(
        retail_xiso_path, index_path, recipe_path, geometry_output_dir,
        source, geometry_manifest,
    )
    require(verification["output_xiso_sha256"] == EXPANDED_WALL_XISO_SHA256 and
            verification["changed_volume_sha256"] == EXPANDED_WALL_VOLUME9_SHA256 and
            verification["xemu_geometry_visibility_proved"] is False,
            "independent expanded-wall XISO verification result mismatch")
    return str(profile["source_sha256"]), str(profile["volume9_sha256"]), {
        "kind": "pinned independently verified expanded-wall geometry diagnostic",
        "independent_geometry_xiso_verifier_ran": True,
        "independent_verifier_schema": verification["schema"],
        "geometry_xiso_manifest_path": str(geometry_manifest),
        "geometry_xiso_manifest_sha256": EXPANDED_WALL_MANIFEST_SHA256,
        "geometry_xiso_manifest_schema": geometry_proof["schema"],
        "retail_xiso_path": str(regular(retail_xiso_path, "retail proof XISO")),
        "retail_xiso_sha256": RETAIL_XISO_SHA256,
        "native_geometry_volume9_sha256": EXPANDED_WALL_VOLUME9_SHA256,
        "recipe_sha256": EXPANDED_WALL_RECIPE_SHA256,
        "native_geometry_manifest_sha256": EXPANDED_WALL_NATIVE_MANIFEST_SHA256,
        "geometry_transport_changed_byte_count": verification["changed_byte_count"],
        "geometry_transport_changed_run_count": verification["changed_run_count"],
    }


def run(
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
    source = regular(source_xiso_path, "pinned source XISO")
    expected_source_sha, expected_volume9_sha, source_proof = prepare_source_profile(
        source_profile, source, source_geometry_manifest_path, retail_xiso_path,
        index_path, recipe_path, geometry_output_dir,
    )
    output = xiso.canonical_new_path(output_xiso_path)
    manifest = xiso.canonical_new_path(manifest_path)
    require(not output.exists() and not manifest.exists(),
            "output XISO and manifest must both be new paths")
    require(len({source, output, manifest}) == 3,
            "source, output, and output manifest must be distinct")

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
                "source-profile XISO SHA-256 mismatch")

        entries, directory = xiso.parse_xdvdfs(source_fd, source_info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        require(len(files) == FILE_COUNT, "source XDVDFS file count mismatch")
        pack0 = entries.get(PACK0_PATH.casefold())
        pack9 = entries.get(PACK9_PATH.casefold())
        xbe = entries.get("default.xbe")
        require(pack0 is not None and (pack0.sector, pack0.size) ==
                (PACK0_SECTOR, PACK0_SIZE), "volume 0 extent mismatch")
        require(pack9 is not None and (pack9.sector, pack9.size) ==
                (PACK9_SECTOR, PACK9_SIZE), "volume 9 extent mismatch")
        require(xbe is not None and xbe.size == xiso.EXPECTED_XBE_SIZE,
                "default.xbe extent mismatch")
        require(xiso.sha256_fd(source_fd, pack0.byte_offset, pack0.size) == PACK0_SHA256,
                "source volume 0 hash mismatch")
        require(xiso.sha256_fd(source_fd, pack9.byte_offset, pack9.size) ==
                expected_volume9_sha, "source-profile volume 9 hash mismatch")
        require(xiso.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                xiso.EXPECTED_XBE_SHA256, "source default.xbe mismatch")
        source_roster = validate_roster(source_fd, pack0.byte_offset, ASSET_BEFORE)
        absolute = int(source_roster["asset_string_absolute_offset"])
        allowed = {absolute + offset for offset in CHANGED_RELATIVE}
        require(sorted(allowed) == EXPECTED_CHANGED_ABSOLUTE and len(allowed) == 2,
                "authorized two-byte offset set changed")

        output_owned = xiso.reserve_file(output)
        require(output_owned.identity != source_identity, "output aliases source inode")
        copy_method = xiso.copy_fd_exact(source_fd, output_owned.descriptor,
                                         source_info.st_size)
        require(xiso.owned_path_matches(output_owned), "output pathname changed during copy")
        require(os.pwrite(output_owned.descriptor, ASSET_AFTER, absolute) == len(ASSET_AFTER),
                "short asset-code write")
        require(xiso.read_exact(output_owned.descriptor, absolute, len(ASSET_AFTER)) ==
                ASSET_AFTER, "asset-code readback mismatch")
        os.fsync(output_owned.descriptor)

        source_sha_after, output_sha, differences = xiso.compare_and_hash(
            source_fd, output_owned.descriptor, source_info.st_size, allowed
        )
        require(source_sha_after == source_sha_before,
                "source XISO changed during write")
        require(differences == EXPECTED_CHANGED_ABSOLUTE,
                "complete-image difference ledger changed")
        output_entries, output_directory = xiso.parse_xdvdfs(
            output_owned.descriptor, source_info.st_size
        )
        require(output_directory == directory and output_entries == entries,
                "XDVDFS tree or extents changed")
        output_roster = validate_roster(output_owned.descriptor, pack0.byte_offset, ASSET_AFTER)
        require({**source_roster, "asset_code": "s42"} == output_roster,
                "output ROST structure changed outside the asset string")
        output_pack0_sha = xiso.sha256_fd(
            output_owned.descriptor, pack0.byte_offset, pack0.size
        )
        require(xiso.sha256_fd(output_owned.descriptor, pack9.byte_offset, pack9.size) ==
                expected_volume9_sha, "source-profile volume 9 changed")
        require(xiso.sha256_fd(output_owned.descriptor, xbe.byte_offset, xbe.size) ==
                xiso.EXPECTED_XBE_SHA256, "default.xbe changed")
        require(xiso.path_identity(source) == source_identity and
                xiso.owned_path_matches(output_owned), "an artifact pathname changed")

        result: dict[str, object] = {
            "schema": SCHEMA,
            "source_profile": source_profile,
            "source": {
                "path": str(source), "size": source_info.st_size,
                "sha256_before": source_sha_before, "sha256_after": source_sha_after,
                "opened_read_only": True, "modified": False,
                "exact_pinned_profile_artifact": True,
            },
            "source_proof": source_proof,
            "xdvdfs": {
                **directory, "file_count": len(files),
                "tree_identical_after_patch": True,
                "all_sector_extents_preserved": True,
                "pack0_sector": pack0.sector, "pack0_size": pack0.size,
                "pack9_sector": pack9.sector, "pack9_size": pack9.size,
                "default_xbe_sha256": xiso.EXPECTED_XBE_SHA256,
                "source_profile_volume9_sha256": expected_volume9_sha,
            },
            "roster": {
                **output_roster,
                "source_pack0_sha256": PACK0_SHA256,
                "output_pack0_sha256": output_pack0_sha,
                "record_and_all_relative_pointers_bit_exact": True,
                "allocation_size_unchanged": True,
            },
            "patch": {
                "purpose": "diagnostic runtime dispatch shim only",
                "before": "s18", "after": "s42",
                "written_allocation_bytes": len(ASSET_AFTER),
                "changed_relative_bytes": CHANGED_RELATIVE,
                "allowed_changed_byte_offsets": EXPECTED_CHANGED_ABSOLUTE,
                "actual_changed_byte_offsets": differences,
                "actual_changed_byte_count": len(differences),
                "all_other_xiso_bytes_identical": True,
                "loader_static_witness": {
                    "active_stadium_accessor": "0x00077460",
                    "asset_code_read": "0x00062c76 MOV EDX,[EAX+0x0c]",
                    "filename_format_callsite": "0x00062c82",
                    "filename_format": "%s%c%c.iff",
                    "night_clear_expected_outer": "s42nd.iff",
                },
            },
            "output": {
                "path": str(output), "size": source_info.st_size,
                "sha256": output_sha, "copy_method": copy_method,
                "exclusively_created": True, "distinct_from_source_inode": True,
            },
            "claims": {
                "diagnostic_only": True,
                "layout_identical_copy_only_xiso": True,
                "offline_two_byte_dispatch_shim_proved": True,
                "source_geometry_volume9_preserved": True,
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
            args.source_profile, args.source_xiso, args.output_xiso, args.manifest,
            source_geometry_manifest_path=args.source_geometry_manifest,
            retail_xiso_path=args.retail_xiso, index_path=args.index,
            recipe_path=args.recipe, geometry_output_dir=args.geometry_output_dir,
        )
    except (OSError, ValueError, xiso.PatchError, KeyError,
            json.JSONDecodeError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_GROUP36_S42_DISPATCH_XISO_PATCH_COMPLETE "
        f"changed={result['patch']['actual_changed_byte_count']} "
        f"output_sha256={result['output']['sha256']} runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
