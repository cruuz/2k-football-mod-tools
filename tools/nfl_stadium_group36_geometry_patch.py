#!/usr/bin/env python3
"""Fail-closed same-footprint position + quad-index writer for NFL 2K5.

This is deliberately narrower than a general mesh importer.  It rewrites the
four existing FLOAT3 vertices and the four existing ARRAY_ELEMENT16 IDs of
retail stadium/group36 without changing any count, command header, pointer,
record, primitive mode, allocation, or opaque byte.  The copied-volume and
VC-LZ publication safety is inherited from the proved position-only writer;
the geometry recipe and decoded edit boundary are independently checked here.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
from typing import Any

import nfl_stadium_group36_position_patch as base
from nfl_txtr import (
    HEADER,
    TxtrError,
    compress_vc_lz,
    decompress_vc_lz,
    minimum_vc_lz_overlap_scratch,
)


RECIPE_SCHEMA = "nfl2k5_group36_same_footprint_geometry_recipe/v1"
MANIFEST_SCHEMA = "nfl2k5_group36_same_footprint_geometry_patch/v1"
MAX_RECIPE_BYTES = 16 * 1024
TOPOLOGY_SPEC_PATH = "reports/specs/2k_static_topology_conformance_requirements.v1.json"
PROFILE_CONTRACT = {
    "id": "nfl2k5_group36_same_footprint_quad_index_replace/v1",
    "fingerprint_algorithm": "sha256-canonical-json-indent2-sortkeys-v1",
    "fingerprint": "668cfc91f6ff398e23a649a695dec950ad8e2529f32a772d65bd8861a447e284",
}
INDEX_PARAMETER_OFFSET = base.PUSH_OFFSET + 12
INDEX_PARAMETER_SIZE = 8
VERTEX_COUNT = 4

TARGET = {
    **base.TARGET,
    "push_decoded_offset": base.PUSH_OFFSET,
    "push_size_bytes": base.PUSH_SIZE,
    "push_sha256": base.PUSH_SHA256,
    "primary_command_word_count": 7,
    "primitive": "NV097_SET_BEGIN_END_QUADS",
    "index_method": "NV097_ARRAY_ELEMENT16",
    "index_count": 4,
}


class GeometryPatchError(ValueError):
    """The recipe, source, edit, budget, or publication contract failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometryPatchError(message)


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in output, f"duplicate JSON key: {key}")
        output[key] = value
    return output


def _binary32(value: object, label: str) -> float:
    require(type(value) in (int, float), f"{label} must be a JSON number")
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as exc:
        raise GeometryPatchError(f"{label} is outside binary32 range") from exc
    require(math.isfinite(numeric), f"{label} must be finite")
    try:
        encoded = struct.pack("<f", numeric)
    except (OverflowError, struct.error) as exc:
        raise GeometryPatchError(f"{label} is outside binary32 range") from exc
    decoded = struct.unpack("<f", encoded)[0]
    require(decoded == numeric, f"{label} must be exactly representable as binary32")
    return decoded


def _profile_contract_identity() -> None:
    """Validate only the immutable selected-profile contract, never the parent hash."""
    path = Path(__file__).resolve().parents[1] / TOPOLOGY_SPEC_PATH
    require(path.is_file() and not path.is_symlink(), "topology specification is unavailable")
    raw = path.read_bytes()
    require(0 < len(raw) <= 1024 * 1024, "topology specification size is unbounded")
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GeometryPatchError(f"topology specification is invalid JSON: {exc}") from exc
    require(isinstance(document, dict), "topology specification root differs")
    profile = document.get("titles", {}).get("nfl2k5_xbox", {}).get(
        "selected_first_topology_profile", {}
    )
    require(isinstance(profile, dict), "selected topology profile is unavailable")
    reference = profile.get("profile_contract_reference")
    contract = profile.get("immutable_profile_contract")
    require(reference == PROFILE_CONTRACT and isinstance(contract, dict),
            "immutable topology profile reference differs")
    require(base.sha256(_canonical_json(contract)) == PROFILE_CONTRACT["fingerprint"],
            "immutable topology profile fingerprint differs")
    require(contract.get("schema") == "2k_static_topology_immutable_profile_contract/v1"
            and contract.get("profile_id") == PROFILE_CONTRACT["id"],
            "immutable topology profile identity differs")
    require(contract.get("source_identity") == {
        "outer_id": base.TARGET["outer_id"],
        "decoded_sha256": base.DECODED_SHA256,
        "position_stream_sha256": base.TARGET["position_stream_sha256"],
        "push_sha256": base.PUSH_SHA256,
    }, "immutable topology source identity differs")
    target = contract.get("target", {})
    require(isinstance(target, dict) and (
        target.get("outer_index"), target.get("chunk_index"),
        target.get("scene_index"), target.get("shape_index"),
        target.get("vertex_count"), target.get("primary_command_word_count"),
    ) == (base.OUTER_INDEX, base.CHUNK_INDEX, 2648, 4, 4, 7),
            "immutable topology target fields differ")
    require(contract.get("position_lane") == {
        "decoded_offset": base.POSITION_OFFSET,
        "size_bytes": base.POSITION_SIZE,
        "component_type": "float32_le",
        "components_per_vertex": 3,
        "stride_bytes": 12,
        "coordinate_space": "raw_xbox",
    }, "immutable topology position lane differs")
    quad = contract.get("quad_index_lane", {})
    require(isinstance(quad, dict) and (
        quad.get("push_decoded_offset"), quad.get("push_size_bytes"),
        quad.get("parameter_decoded_offset"), quad.get("parameter_size_bytes"),
        quad.get("component_type"), quad.get("index_count"),
        quad.get("minimum_id"), quad.get("maximum_id"),
        quad.get("primitive_method"), quad.get("index_method"),
    ) == (base.PUSH_OFFSET, base.PUSH_SIZE, INDEX_PARAMETER_OFFSET,
          INDEX_PARAMETER_SIZE, "uint16_le", 4, 0, 3,
          "NV097_SET_BEGIN_END_QUADS", "NV097_ARRAY_ELEMENT16"),
            "immutable topology quad lane differs")
    budget = contract.get("container_budget", {})
    require(isinstance(budget, dict) and (
        budget.get("decoded_size_bytes"), budget.get("retail_consumed_cap_bytes"),
        budget.get("fixed_opaque_tail_bytes"), budget.get("fixed_opaque_tail_sha256"),
        budget.get("scratch_cap_bytes"),
    ) == (base.DECODED_SIZE, base.RETAIL_CONSUMED, base.OPAQUE_TAIL_SIZE,
          base.OPAQUE_TAIL_SHA256, base.MAX_SCRATCH),
            "immutable topology container budget differs")
    require(contract.get("authorized_changes") == {
        "same_count_positions": True,
        "same_count_quad_indices": True,
        "changed_vertex_or_index_count": False,
        "changed_command_headers_methods_counts_modes_or_pointers": False,
        "changed_stream_declarations_material_transform_selectors_or_bounds": False,
        "changed_allocation_or_relocation": False,
    }, "immutable topology authorization differs")
    require(contract.get("claim_boundary") == {
        "offline_structural_write_back": True,
        "runtime_visibility": False,
        "xemu_visibility": False,
        "original_xbox_hardware": False,
        "material_uv_normal_writer": False,
        "automatic_decimator": False,
        "production_mesh_importer": False,
    }, "immutable topology claim boundary differs")


def load_recipe(path: Path) -> dict[str, object]:
    recipe_path = base.regular(path, "same-footprint geometry recipe")
    raw = recipe_path.read_bytes()
    require(0 < len(raw) <= MAX_RECIPE_BYTES, "recipe size is outside 1..16384 bytes")
    try:
        recipe = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                GeometryPatchError(f"non-finite JSON constant {token} is forbidden")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GeometryPatchError(f"recipe is not valid UTF-8 JSON: {exc}") from exc
    require(isinstance(recipe, dict), "recipe root must be an object")
    require(raw == _canonical_json(recipe), "recipe must be canonical sorted JSON")
    require(set(recipe) == {
        "schema", "operation", "profile_contract", "target", "encoding",
        "positions", "indices", "claim_flags",
    }, "recipe fields differ from geometry v1")
    require(recipe["schema"] == RECIPE_SCHEMA, "recipe schema differs")
    require(recipe["operation"] == "replace_exact_same_footprint_positions_and_quad_indices",
            "recipe operation differs")
    require(recipe["profile_contract"] == PROFILE_CONTRACT,
            "recipe immutable profile-contract reference differs")
    require(recipe["target"] == TARGET, "recipe target differs from group36")
    require(recipe["encoding"] == {
        **base.ENCODING,
        "index_component_type": "uint16_le",
        "index_order": "native_quad_order",
    }, "recipe geometry encoding differs")
    require(recipe["claim_flags"] == {
        "same_vertex_count": True,
        "same_index_count": True,
        "changed_count_or_relocation": False,
        "runtime_visibility_proved": False,
        "production_mesh_importer": False,
    }, "recipe claim boundary differs")

    rows = recipe["positions"]
    require(isinstance(rows, list) and len(rows) == VERTEX_COUNT,
            "recipe must contain exactly four positions")
    positions: list[tuple[float, float, float]] = []
    for vertex, row in enumerate(rows):
        require(isinstance(row, list) and len(row) == 3,
                f"positions[{vertex}] must contain exactly XYZ")
        positions.append(tuple(
            _binary32(component, f"positions[{vertex}][{axis}]")
            for axis, component in enumerate(row)
        ))
    packed_positions = b"".join(struct.pack("<3f", *row) for row in positions)
    require(len(packed_positions) == base.POSITION_SIZE, "packed position extent drift")

    authored_indices = recipe["indices"]
    require(isinstance(authored_indices, list) and len(authored_indices) == VERTEX_COUNT,
            "recipe indices must contain exactly four IDs")
    indices: list[int] = []
    for ordinal, value in enumerate(authored_indices):
        require(type(value) is int, f"indices[{ordinal}] must be an integer")
        require(0 <= value < VERTEX_COUNT,
                f"indices[{ordinal}] must be in [0,{VERTEX_COUNT})")
        indices.append(value)
    return {
        "path": recipe_path,
        "sha256": base.sha256(raw),
        "packed_positions": packed_positions,
        "indices": indices,
    }


def _push_indices(decoded: bytes) -> list[int]:
    require(len(decoded) == base.DECODED_SIZE, "decoded SCNE length drift")
    words = struct.unpack_from("<7I", decoded, base.PUSH_OFFSET)
    begin_header, begin_mode, array_header, pair0, pair1, end_header, end_mode = words
    require((begin_header & 0x1FFC, (begin_header >> 18) & 0x7FF, begin_mode) ==
            (0x17FC, 1, 8), "group36 BEGIN/QUADS command changed")
    require((array_header & 0x1FFC, (array_header >> 18) & 0x7FF) == (0x1800, 2),
            "group36 ARRAY_ELEMENT16 command changed")
    require((end_header & 0x1FFC, (end_header >> 18) & 0x7FF, end_mode) ==
            (0x17FC, 1, 0), "group36 END command changed")
    return [pair0 & 0xFFFF, pair0 >> 16, pair1 & 0xFFFF, pair1 >> 16]


def _aligned16(value: int) -> int:
    return (value + 15) & ~15


def build_span(
    source: dict[str, object], packed_positions: bytes, indices: list[int]
) -> tuple[bytes, dict[str, object]]:
    decoded = bytes(source["decoded"])
    require(base.sha256(decoded[base.PUSH_OFFSET:base.PUSH_OFFSET + base.PUSH_SIZE]) ==
            base.PUSH_SHA256, "source group36 push stream drift")
    retail_indices = _push_indices(decoded)
    require(retail_indices == [0, 1, 2, 3], "retail group36 quad identity drift")
    require(len(packed_positions) == base.POSITION_SIZE, "position payload size drift")
    require(len(indices) == VERTEX_COUNT and all(0 <= item < VERTEX_COUNT for item in indices),
            "index payload escaped fixed-count bounds")

    original_positions = decoded[base.POSITION_OFFSET:base.POSITION_OFFSET + base.POSITION_SIZE]
    no_op = packed_positions == original_positions and indices == retail_indices
    if no_op:
        # Identity is a byte-preservation path, not a deterministic-recompression
        # assumption.  Derive the transport metrics from the already validated
        # retail stream, then return the original complete fixed span verbatim.
        encoded = bytes(source["retail_stream"])
        source_span = bytes(source["span"])
        tail = bytes(source["tail"])
        require(len(encoded) == base.RETAIL_CONSUMED,
                "no-op retail consumed-stream extent drift")
        require(len(source_span) == base.CHUNK_SPAN_SIZE,
                "no-op source fixed-span extent drift")
        require(source_span[-base.OPAQUE_TAIL_SIZE:] == tail,
                "no-op fixed opaque tail placement drift")
        padding = base.CHUNK_STORED_SIZE - len(encoded)
        alias = minimum_vc_lz_overlap_scratch(
            encoded, base.CHUNK_STORED_SIZE, base.DECODED_SIZE
        )
        scratch = _aligned16(max(padding, alias))
        require(padding == base.OPAQUE_TAIL_SIZE and alias == 0
                and scratch == base.RETAIL_SCRATCH,
                "no-op retail scratch derivation drift")
        packed_retail_indices = struct.pack("<4H", *retail_indices)
        return source_span, {
            "mode": "no_op",
            "decoded": decoded,
            "position_before_sha256": base.sha256(original_positions),
            "position_after_sha256": base.sha256(packed_positions),
            "indices_before_sha256": base.sha256(packed_retail_indices),
            "indices_after_sha256": base.sha256(packed_retail_indices),
            "indices_are_permutation": True,
            "unique_index_count": VERTEX_COUNT,
            "decoded_after_sha256": base.sha256(decoded),
            "decoded_changed_byte_count": 0,
            "encoded_sha256": base.sha256(encoded),
            "encoded_bytes": len(encoded),
            "zero_gap_bytes": 0,
            "padding_bytes": padding,
            "minimum_alias_scratch_bytes": alias,
            "scratch_after": scratch,
            "literal_count": 508_197,
            "match_count": 158_651,
        }

    edited = bytearray(decoded)
    edited[base.POSITION_OFFSET:base.POSITION_OFFSET + base.POSITION_SIZE] = packed_positions
    struct.pack_into("<4H", edited, INDEX_PARAMETER_OFFSET, *indices)
    edited_bytes = bytes(edited)
    require(_push_indices(edited_bytes) == indices, "writer push reconstruction differs from recipe")
    changed_offsets = [offset for offset, pair in enumerate(zip(decoded, edited_bytes)) if pair[0] != pair[1]]
    position_range = range(base.POSITION_OFFSET, base.POSITION_OFFSET + base.POSITION_SIZE)
    index_range = range(INDEX_PARAMETER_OFFSET, INDEX_PARAMETER_OFFSET + INDEX_PARAMETER_SIZE)
    require(all(offset in position_range or offset in index_range for offset in changed_offsets),
            "decoded edit escaped authorized position/index bytes")
    require(
        decoded[base.PUSH_OFFSET:INDEX_PARAMETER_OFFSET] ==
        edited_bytes[base.PUSH_OFFSET:INDEX_PARAMETER_OFFSET]
        and decoded[INDEX_PARAMETER_OFFSET + INDEX_PARAMETER_SIZE:base.PUSH_OFFSET + base.PUSH_SIZE] ==
        edited_bytes[INDEX_PARAMETER_OFFSET + INDEX_PARAMETER_SIZE:base.PUSH_OFFSET + base.PUSH_SIZE],
        "push header/method/mode/placement changed",
    )

    try:
        encoded, metrics = compress_vc_lz(
            edited_bytes, stream_tag=1, offset_bits=12,
            max_encoded_size=base.RETAIL_CONSUMED, verify_roundtrip=True,
        )
    except TxtrError as exc:
        raise GeometryPatchError(
            "replacement exceeds the retail VC-LZ consumed-stream allocation; "
            "same footprint does not imply compressed-container fit"
        ) from exc
    decoded_back, info = decompress_vc_lz(encoded, base.DECODED_SIZE)
    require(decoded_back == edited_bytes and info.consumed_bytes == len(encoded),
            "writer-side VC-LZ decode does not reconstruct edited geometry")
    gap = base.RETAIL_CONSUMED - len(encoded)
    padding = base.CHUNK_STORED_SIZE - len(encoded)
    alias = minimum_vc_lz_overlap_scratch(encoded, base.CHUNK_STORED_SIZE, base.DECODED_SIZE)
    scratch = _aligned16(max(padding, alias))
    require(scratch <= base.MAX_SCRATCH,
            f"replacement needs scratch 0x{scratch:x}, above proved group36 cap 0x{base.MAX_SCRATCH:x}")
    source_span = bytes(source["span"])
    tail = bytes(source["tail"])
    header = bytearray(source_span[:HEADER.size])
    struct.pack_into("<I", header, 0x14, scratch)
    rebuilt = bytes(header) + encoded + bytes(gap) + tail
    require(len(rebuilt) == base.CHUNK_SPAN_SIZE, "rebuilt fixed span size changed")
    require(rebuilt[-base.OPAQUE_TAIL_SIZE:] == tail, "fixed opaque tail changed")
    return rebuilt, {
        "mode": "patched",
        "decoded": edited_bytes,
        "position_before_sha256": base.sha256(original_positions),
        "position_after_sha256": base.sha256(packed_positions),
        "indices_before_sha256": base.sha256(struct.pack("<4H", *retail_indices)),
        "indices_after_sha256": base.sha256(struct.pack("<4H", *indices)),
        "indices_are_permutation": sorted(indices) == list(range(VERTEX_COUNT)),
        "unique_index_count": len(set(indices)),
        "decoded_after_sha256": base.sha256(edited_bytes),
        "decoded_changed_byte_count": len(changed_offsets),
        "encoded_sha256": base.sha256(encoded),
        "encoded_bytes": len(encoded),
        "zero_gap_bytes": gap,
        "padding_bytes": padding,
        "minimum_alias_scratch_bytes": alias,
        "scratch_after": scratch,
        "literal_count": metrics.literal_count,
        "match_count": metrics.match_count,
    }


def _manifest(
    recipe: dict[str, object], output_pack: Path, build: dict[str, object], source_after: str
) -> dict[str, object]:
    output_sha = base.sha256_file(output_pack)
    outside_sha = base.sha256_outside_chunk(output_pack)
    require(outside_sha == base.OUTSIDE_CHUNK_SHA256, "output changed outside target chunk")
    return {
        "schema": MANIFEST_SCHEMA,
        "mode": build["mode"],
        "recipe": {
            "schema": RECIPE_SCHEMA,
            "sha256": recipe["sha256"],
            "contains_authored_geometry": False,
        },
        "profile_contract": PROFILE_CONTRACT,
        "target": TARGET,
        "source": {
            "index": {"name": base.INDEX_NAME, "size": base.INDEX_SIZE, "sha256": base.INDEX_SHA256},
            "volume": {
                "name": base.PACK_NAME, "size": base.PACK_SIZE,
                "sha256_before": base.PACK_SHA256, "sha256_after": source_after,
                "modified": False,
            },
            "resource": {
                "outer_index": base.OUTER_INDEX,
                "chunk_index": base.CHUNK_INDEX,
                "pack_span": [base.CHUNK_PACK_OFFSET, base.CHUNK_PACK_END],
                "source_span_sha256": base.CHUNK_SPAN_SHA256,
                "source_decoded_sha256": base.DECODED_SHA256,
            },
        },
        "edit": {
            "position_span": [base.POSITION_OFFSET, base.POSITION_OFFSET + base.POSITION_SIZE],
            "index_halfword_span": [INDEX_PARAMETER_OFFSET, INDEX_PARAMETER_OFFSET + INDEX_PARAMETER_SIZE],
            "position_before_sha256": build["position_before_sha256"],
            "position_after_sha256": build["position_after_sha256"],
            "indices_before_sha256": build["indices_before_sha256"],
            "indices_after_sha256": build["indices_after_sha256"],
            "indices_are_permutation": build["indices_are_permutation"],
            "unique_index_count": build["unique_index_count"],
            "decoded_after_sha256": build["decoded_after_sha256"],
            "decoded_changed_byte_count": build["decoded_changed_byte_count"],
            "every_decoded_byte_outside_authorized_spans_bit_exact": True,
            "command_headers_methods_counts_modes_and_pointers_bit_exact": True,
        },
        "compression": {
            "codec": "VC-LZ", "stream_tag": 1, "offset_bits": 12,
            "retail_consumed_bytes": base.RETAIL_CONSUMED,
            "rebuilt_consumed_bytes": build["encoded_bytes"],
            "rebuilt_stream_sha256": build["encoded_sha256"],
            "zero_gap_before_fixed_tail_bytes": build["zero_gap_bytes"],
            "total_stored_padding_bytes": build["padding_bytes"],
            "minimum_alias_scratch_bytes": build["minimum_alias_scratch_bytes"],
            "scratch_before": base.RETAIL_SCRATCH,
            "scratch_after": build["scratch_after"],
            "scratch_cap": base.MAX_SCRATCH,
            "fixed_opaque_tail_bytes": base.OPAQUE_TAIL_SIZE,
            "fixed_opaque_tail_sha256": base.OPAQUE_TAIL_SHA256,
            "independent_decode_matches_edited_bytes": True,
        },
        "output": {
            "volume_name": base.PACK_NAME,
            "volume_size": base.PACK_SIZE,
            "volume_sha256": output_sha,
            "outside_target_chunk_sha256": outside_sha,
            "outside_target_chunk_bit_exact": True,
            "directory_files": ["9", "manifest.json"],
            "manifest_contains_authored_geometry": False,
        },
        "claims": {
            "same_footprint_position_write_back": True,
            "same_footprint_native_quad_index_write_back": True,
            "changed_vertex_or_index_count_write_back": False,
            "material_uv_skin_morph_transform_or_bounds_write_back": False,
            "xemu_runtime_visibility_proved": False,
            "original_xbox_runtime_visibility_proved": False,
            "production_mesh_importer": False,
        },
    }


def _copy_and_patch_owned_volume(
    source_pack: Path,
    output_pack: Path,
    rebuilt: bytes,
    *,
    patch_offset: int,
    expected_size: int,
) -> tuple[int, int]:
    """Create, copy, and patch one staged inode without reopening its pathname.

    Keeping the exclusive-create descriptor open through the patch prevents a
    raced pathname replacement from redirecting the write into an attacker
    selected symlink target.  The final pathname/inode check makes such a race
    a refusal before publication.
    """
    require(
        0 <= patch_offset <= expected_size
        and len(rebuilt) <= expected_size - patch_offset,
        "staged patch extent exceeds the copied volume",
    )
    with source_pack.open("rb") as left, output_pack.open("x+b") as right:
        info = os.fstat(right.fileno())
        owned = (info.st_dev, info.st_ino)
        require(base._inode(output_pack) == owned,
                "staged volume pathname changed after creation")
        while block := left.read(8 * 1024 * 1024):
            right.write(block)
        right.flush()
        require(os.fstat(right.fileno()).st_size == expected_size,
                "copied staged volume size changed")
        right.seek(patch_offset)
        right.write(rebuilt)
        right.flush()
        os.fsync(right.fileno())
        require(os.fstat(right.fileno()).st_size == expected_size,
                "patched staged volume size changed")
        require(base._inode(output_pack) == owned,
                "staged volume pathname changed during copy/patch")
    return owned


def patch(index: Path, recipe_path: Path, output_dir: Path) -> dict[str, object]:
    _profile_contract_identity()
    recipe = load_recipe(recipe_path)
    output_dir = output_dir.expanduser()
    parent_info = output_dir.parent.lstat()
    require(stat.S_ISDIR(parent_info.st_mode) and not stat.S_ISLNK(parent_info.st_mode),
            "output parent must be a real non-symlink directory")
    parent = output_dir.parent.resolve(strict=True)
    requested = parent / output_dir.name
    source_index = base.regular(index, "NFL archive index")
    source_pack_candidate = base.regular(source_index.parent / base.PACK_NAME, "NFL source volume 9")
    require(requested != source_pack_candidate.parent, "refusing to use source directory as output")
    try:
        requested.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise GeometryPatchError(f"refusing to overwrite existing output directory: {output_dir}") from exc
    reservation_inode: tuple[int, int] | None = base._inode(requested)
    staging: Path | None = None
    staging_inode: tuple[int, int] | None = None
    known: dict[str, tuple[int, int]] = {}
    try:
        source = base._validate_source(source_index)
        rebuilt, build = build_span(
            source, bytes(recipe["packed_positions"]), list(recipe["indices"])
        )
        source_pack = Path(source["pack"])
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=requested))
        staging_inode = base._inode(staging)
        output_pack = staging / base.PACK_NAME
        known[base.PACK_NAME] = _copy_and_patch_owned_volume(
            source_pack,
            output_pack,
            rebuilt,
            patch_offset=base.CHUNK_PACK_OFFSET,
            expected_size=base.PACK_SIZE,
        )
        require(output_pack.stat().st_size == base.PACK_SIZE, "output volume size changed")
        source_after = base.sha256_file(source_pack)
        require(source_after == base.PACK_SHA256, "retail source changed during write")
        manifest = _manifest(recipe, output_pack, build, source_after)
        manifest_path = staging / "manifest.json"
        with manifest_path.open("xb") as stream:
            info = os.fstat(stream.fileno())
            known["manifest.json"] = (info.st_dev, info.st_ino)
            require(base._inode(manifest_path) == known["manifest.json"],
                    "staged manifest pathname changed after creation")
            stream.write(_canonical_json(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        base._publish_staged_no_replace(
            requested, reservation_inode, staging, staging_inode, known
        )
        return manifest
    except Exception:
        base._safe_cleanup_owned_reservation(
            requested, reservation_inode, staging, staging_inode, known
        )
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = patch(args.index, args.recipe, args.output_dir)
    print(
        "NFL_GROUP36_GEOMETRY_PATCH_COMPLETE "
        f"mode={manifest['mode']} output={args.output_dir / base.PACK_NAME} "
        f"sha256={manifest['output']['volume_sha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError, GeometryPatchError, base.PositionPatchError, TxtrError,
        struct.error, KeyError, IndexError,
    ) as exc:
        raise SystemExit(f"error: {exc}") from exc
