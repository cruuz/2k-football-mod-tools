#!/usr/bin/env python3
"""Independently verify the NFL 2K5 group36 same-footprint geometry patch.

This verifier imports no writer.  It reuses the earlier independent archive,
VC-LZ, SCNE, transform, material, and copied-volume verifier, but implements
the geometry recipe, native push-command decode, authorized-byte comparison,
and manifest reconstruction separately from the geometry writer.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import stat
import struct
from typing import Any

import nfl_stadium_group36_position_verify as base


VERIFY_SCHEMA = "nfl2k5_group36_same_footprint_geometry_verify/v1"
RECIPE_SCHEMA = "nfl2k5_group36_same_footprint_geometry_recipe/v1"
MANIFEST_SCHEMA = "nfl2k5_group36_same_footprint_geometry_patch/v1"
MAX_RECIPE_BYTES = 16 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
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
ENCODING = {
    **base.ENCODING,
    "index_component_type": "uint16_le",
    "index_order": "native_quad_order",
}


class GeometryVerifyError(ValueError):
    """The independently reconstructed result violates the fixed profile."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometryVerifyError(message)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in output, f"duplicate JSON key: {key}")
        output[key] = value
    return output


def _regular(path: Path, label: str) -> Path:
    path = path.expanduser()
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise GeometryVerifyError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    return path.resolve(strict=True)


def _load_json(path: Path, label: str, maximum: int) -> tuple[dict[str, Any], bytes]:
    path = _regular(path, label)
    raw = path.read_bytes()
    require(0 < len(raw) <= maximum, f"{label} size is outside its bound")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique,
            parse_constant=lambda token: (_ for _ in ()).throw(
                GeometryVerifyError(f"non-finite JSON constant {token} is forbidden")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GeometryVerifyError(f"{label} is not UTF-8 JSON: {exc}") from exc
    require(isinstance(value, dict), f"{label} root must be an object")
    require(raw == _canonical(value), f"{label} must be canonical sorted JSON")
    return value, raw


def _f32(value: object, label: str) -> float:
    require(type(value) in (int, float), f"{label} is not a JSON number")
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as exc:
        raise GeometryVerifyError(f"{label} is outside binary32 range") from exc
    require(math.isfinite(numeric), f"{label} is non-finite")
    try:
        decoded = struct.unpack("<f", struct.pack("<f", numeric))[0]
    except (OverflowError, struct.error) as exc:
        raise GeometryVerifyError(f"{label} is outside binary32 range") from exc
    require(decoded == numeric, f"{label} is not exactly binary32")
    return decoded


def load_recipe(path: Path) -> dict[str, object]:
    recipe, raw = _load_json(path, "same-footprint geometry recipe", MAX_RECIPE_BYTES)
    require(set(recipe) == {
        "schema", "operation", "profile_contract", "target", "encoding",
        "positions", "indices", "claim_flags",
    }, "recipe key set differs from geometry v1")
    require(recipe["schema"] == RECIPE_SCHEMA, "recipe schema differs")
    require(recipe["operation"] == "replace_exact_same_footprint_positions_and_quad_indices",
            "recipe operation differs")
    require(recipe["profile_contract"] == PROFILE_CONTRACT,
            "recipe immutable profile-contract reference differs")
    require(recipe["target"] == TARGET and recipe["encoding"] == ENCODING,
            "recipe target or encoding differs")
    require(recipe["claim_flags"] == {
        "same_vertex_count": True,
        "same_index_count": True,
        "changed_count_or_relocation": False,
        "runtime_visibility_proved": False,
        "production_mesh_importer": False,
    }, "recipe claims differ")
    positions = recipe["positions"]
    require(isinstance(positions, list) and len(positions) == VERTEX_COUNT,
            "recipe must contain four positions")
    packed = bytearray()
    for vertex, row in enumerate(positions):
        require(isinstance(row, list) and len(row) == 3,
                f"positions[{vertex}] is not XYZ")
        packed.extend(struct.pack("<3f", *(
            _f32(value, f"positions[{vertex}][{component}]")
            for component, value in enumerate(row)
        )))
    indices = recipe["indices"]
    require(isinstance(indices, list) and len(indices) == VERTEX_COUNT,
            "recipe must contain four index IDs")
    parsed_indices: list[int] = []
    for ordinal, value in enumerate(indices):
        require(type(value) is int and 0 <= value < VERTEX_COUNT,
                f"indices[{ordinal}] is not an in-range integer")
        parsed_indices.append(value)
    return {
        "sha256": base.sha256(raw),
        "packed_positions": bytes(packed),
        "indices": parsed_indices,
    }


def parse_quad_push(decoded: bytes) -> dict[str, object]:
    """Parse, do not normalize, the exact seven-word native quad stream."""
    require(len(decoded) == base.DECODED_SIZE, "decoded SCNE size differs")
    cursor = base.PUSH_OFFSET
    end = cursor + base.PUSH_SIZE
    active: int | None = None
    methods: list[str] = []
    indices: list[int] = []
    parameter_word_offsets: list[int] = []
    while cursor < end:
        header_offset = cursor
        header = struct.unpack_from("<I", decoded, cursor)[0]
        cursor += 4
        require((header & 0xE0030003) in (0, 0x40000000),
                "push command header signature differs")
        method = header & 0x1FFC
        count = (header >> 18) & 0x7FF
        require(cursor + count * 4 <= end, "push command exceeds seven-word extent")
        params = struct.unpack_from(f"<{count}I", decoded, cursor)
        param_offsets = [cursor + ordinal * 4 for ordinal in range(count)]
        cursor += count * 4
        if method == 0x17FC:
            methods.append("SET_BEGIN_END")
            require(count == 1, "SET_BEGIN_END parameter count differs")
            mode = params[0]
            if mode == 0:
                require(active == 8, "END is not closing one QUADS batch")
                active = None
            else:
                require(mode == 8 and active is None, "primitive mode is not one QUADS batch")
                active = mode
        elif method == 0x1800:
            methods.append("ARRAY_ELEMENT16")
            require(active == 8 and count == 2,
                    "ARRAY_ELEMENT16 is not the fixed two-word QUADS payload")
            parameter_word_offsets.extend(param_offsets)
            for word in params:
                indices.extend([word & 0xFFFF, word >> 16])
        else:
            raise GeometryVerifyError(
                f"unexpected method 0x{method:04x} at decoded 0x{header_offset:x}"
            )
    require(cursor == end and active is None,
            "push parser did not close on the exact boundary")
    require(methods == ["SET_BEGIN_END", "ARRAY_ELEMENT16", "SET_BEGIN_END"],
            "push method sequence differs")
    require(parameter_word_offsets == [INDEX_PARAMETER_OFFSET, INDEX_PARAMETER_OFFSET + 4],
            "index parameter word placement differs")
    require(len(indices) == VERTEX_COUNT and all(item < VERTEX_COUNT for item in indices),
            "quad index count or bounds differ")
    triangles = [(indices[0], indices[1], indices[2]),
                 (indices[0], indices[2], indices[3])]
    nondegenerate = sum(len(set(triangle)) == 3 for triangle in triangles)
    return {
        "indices": indices,
        "unique_index_count": len(set(indices)),
        "indices_are_permutation": sorted(indices) == list(range(VERTEX_COUNT)),
        "nondegenerate_triangle_count": nondegenerate,
        "degenerate_triangle_count": 2 - nondegenerate,
        "parameter_word_offsets": parameter_word_offsets,
    }


def _profile_contract_identity() -> None:
    """Independently bind to the immutable profile, not the parent spec hash."""
    path = Path(__file__).resolve().parents[1] / TOPOLOGY_SPEC_PATH
    require(path.is_file() and not path.is_symlink(), "topology specification unavailable")
    document, _ = _load_json(path, "topology specification", 1024 * 1024)
    profile = document.get("titles", {}).get("nfl2k5_xbox", {}).get(
        "selected_first_topology_profile", {}
    )
    require(isinstance(profile, dict), "selected topology profile unavailable")
    reference = profile.get("profile_contract_reference")
    contract = profile.get("immutable_profile_contract")
    require(reference == PROFILE_CONTRACT and isinstance(contract, dict),
            "immutable topology profile reference differs")
    require(base.sha256(_canonical(contract)) == PROFILE_CONTRACT["fingerprint"],
            "immutable topology profile fingerprint differs")
    require(contract.get("schema") == "2k_static_topology_immutable_profile_contract/v1"
            and contract.get("profile_id") == PROFILE_CONTRACT["id"],
            "immutable topology profile identity differs")
    require(contract.get("source_identity") == {
        "outer_id": base.TARGET["outer_id"],
        "decoded_sha256": base.SOURCE_DECODED_SHA256,
        "position_stream_sha256": base.TARGET["position_stream_sha256"],
        "push_sha256": base.PUSH_SHA256,
    }, "immutable topology source identity differs")
    target = contract.get("target", {})
    require(isinstance(target, dict) and (
        target.get("outer_index"), target.get("chunk_index"),
        target.get("scene_index"), target.get("shape_index"),
        target.get("vertex_count"), target.get("primary_command_word_count"),
    ) == (base.ENTRY_INDEX, base.CHUNK_INDEX, 2648, 4, 4, 7),
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
    ) == (base.DECODED_SIZE, base.RETAIL_CONSUMED, base.TAIL_SIZE,
          base.TAIL_SHA256, 0x40),
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


def _expected_manifest(
    recipe: dict[str, object], output_sha: str, output_decoded: bytes,
    output_body: bytes, consumed: int, padding: int, alias: int, scratch: int,
    changed_decoded: int, topology: dict[str, object], mode: str,
) -> dict[str, object]:
    packed_positions = bytes(recipe["packed_positions"])
    packed_indices = struct.pack("<4H", *list(recipe["indices"]))
    return {
        "schema": MANIFEST_SCHEMA,
        "mode": mode,
        "recipe": {
            "schema": RECIPE_SCHEMA,
            "sha256": recipe["sha256"],
            "contains_authored_geometry": False,
        },
        "profile_contract": PROFILE_CONTRACT,
        "target": TARGET,
        "source": {
            "index": {"name": "0", "size": base.INDEX_SIZE, "sha256": base.INDEX_SHA256},
            "volume": {
                "name": "9", "size": base.PACK_SIZE,
                "sha256_before": base.PACK_SHA256,
                "sha256_after": base.PACK_SHA256,
                "modified": False,
            },
            "resource": {
                "outer_index": base.ENTRY_INDEX,
                "chunk_index": base.CHUNK_INDEX,
                "pack_span": [base.CHUNK_START, base.CHUNK_END],
                "source_span_sha256": base.SOURCE_SPAN_SHA256,
                "source_decoded_sha256": base.SOURCE_DECODED_SHA256,
            },
        },
        "edit": {
            "position_span": [base.POSITION_OFFSET, base.POSITION_OFFSET + base.POSITION_SIZE],
            "index_halfword_span": [INDEX_PARAMETER_OFFSET, INDEX_PARAMETER_OFFSET + INDEX_PARAMETER_SIZE],
            "position_before_sha256": base.SOURCE_POSITION_SHA256,
            "position_after_sha256": base.sha256(packed_positions),
            "indices_before_sha256": base.sha256(struct.pack("<4H", 0, 1, 2, 3)),
            "indices_after_sha256": base.sha256(packed_indices),
            "indices_are_permutation": topology["indices_are_permutation"],
            "unique_index_count": topology["unique_index_count"],
            "decoded_after_sha256": base.sha256(output_decoded),
            "decoded_changed_byte_count": changed_decoded,
            "every_decoded_byte_outside_authorized_spans_bit_exact": True,
            "command_headers_methods_counts_modes_and_pointers_bit_exact": True,
        },
        "compression": {
            "codec": "VC-LZ", "stream_tag": 1, "offset_bits": 12,
            "retail_consumed_bytes": base.RETAIL_CONSUMED,
            "rebuilt_consumed_bytes": consumed,
            "rebuilt_stream_sha256": base.sha256(output_body[:consumed]),
            "zero_gap_before_fixed_tail_bytes": base.RETAIL_CONSUMED - consumed,
            "total_stored_padding_bytes": padding,
            "minimum_alias_scratch_bytes": alias,
            "scratch_before": 0x10, "scratch_after": scratch,
            "scratch_cap": 0x40,
            "fixed_opaque_tail_bytes": base.TAIL_SIZE,
            "fixed_opaque_tail_sha256": base.TAIL_SHA256,
            "independent_decode_matches_edited_bytes": True,
        },
        "output": {
            "volume_name": "9", "volume_size": base.PACK_SIZE,
            "volume_sha256": output_sha,
            "outside_target_chunk_sha256": base.OUTSIDE_SHA256,
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


def verify(index: Path, recipe_path: Path, output_dir: Path) -> dict[str, object]:
    _profile_contract_identity()
    base.parse_index(index)
    index = _regular(index, "NFL archive index")
    source_pack = _regular(index.parent / "9", "source volume 9")
    require(source_pack.stat().st_size == base.PACK_SIZE
            and base.sha256_file(source_pack) == base.PACK_SHA256,
            "source volume identity differs")
    output_dir = output_dir.expanduser()
    info = output_dir.lstat()
    require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            "output directory must be a real directory")
    output_dir = output_dir.resolve(strict=True)
    require(sorted(path.name for path in output_dir.iterdir()) == ["9", "manifest.json"],
            "output directory must contain only 9 and manifest.json")
    output_pack = _regular(output_dir / "9", "output volume 9")
    base.require_distinct_files(source_pack, output_pack)
    recipe = load_recipe(recipe_path)
    manifest, manifest_raw = _load_json(
        output_dir / "manifest.json", "geometry manifest", MAX_MANIFEST_BYTES
    )

    source_entry = base._read_exact(source_pack, base.ENTRY_PACK_OFFSET, base.ENTRY_SIZE)
    require(base.sha256(source_entry) == base.ENTRY_SHA256, "source outer entry differs")
    source_span = base._read_exact(source_pack, base.CHUNK_START, base.CHUNK_SPAN)
    output_span = base._read_exact(output_pack, base.CHUNK_START, base.CHUNK_SPAN)
    require(base.sha256(source_span) == base.SOURCE_SPAN_SHA256, "source span differs")
    source_fields = struct.unpack("<4s7I", source_span[:32])
    output_fields = struct.unpack("<4s7I", output_span[:32])
    require(source_fields == (b"SCNE", base.CHUNK_STORED, base.SYSTEM_BYTES,
                              base.VIDEO_BYTES, 0xFEEDBEEF, 0x10, 0, 0),
            "source wrapper differs")
    require(output_fields[:5] == source_fields[:5] and output_fields[6:] == source_fields[6:],
            "output wrapper changed outside scratch")
    require(all(left == right for offset, (left, right) in enumerate(
        zip(source_span[:32], output_span[:32])
    ) if not 0x14 <= offset < 0x18), "wrapper byte diff escaped scratch")

    source_body, output_body = source_span[32:], output_span[32:]
    source_decoded, source_lz = base.decompress_vc_lz(source_body, base.DECODED_SIZE)
    output_decoded, output_lz = base.decompress_vc_lz(output_body, base.DECODED_SIZE)
    require(source_lz == {"consumed": base.RETAIL_CONSUMED, "literals": 508197,
                          "matches": 158651, "tag": 1, "offset_bits": 12},
            "source VC-LZ metrics differ")
    require(base.sha256(source_decoded) == base.SOURCE_DECODED_SHA256,
            "source decoded SCNE differs")
    require(source_body[base.RETAIL_CONSUMED:] == output_body[base.RETAIL_CONSUMED:]
            and base.sha256(output_body[base.RETAIL_CONSUMED:]) == base.TAIL_SHA256,
            "fixed final opaque tail differs")
    consumed = int(output_lz["consumed"])
    require(consumed <= base.RETAIL_CONSUMED, "output overlaps fixed tail")
    require(not any(output_body[consumed:base.RETAIL_CONSUMED]),
            "gap before fixed tail is not zero")
    padding = base.CHUNK_STORED - consumed
    alias = base.minimum_overlap_scratch(output_body[:consumed], base.CHUNK_STORED,
                                         base.DECODED_SIZE)
    scratch = (max(padding, alias) + 15) & ~15
    require(output_fields[5] == scratch and scratch <= 0x40,
            "scratch is not the exact independently reconstructed value")

    source_positions = source_decoded[
        base.POSITION_OFFSET:base.POSITION_OFFSET + base.POSITION_SIZE
    ]
    expected_positions = bytes(recipe["packed_positions"])
    require(base.sha256(source_positions) == base.SOURCE_POSITION_SHA256,
            "source position lane differs")
    require(output_decoded[
        base.POSITION_OFFSET:base.POSITION_OFFSET + base.POSITION_SIZE
    ] == expected_positions, "output positions differ from recipe")
    source_topology = parse_quad_push(source_decoded)
    output_topology = parse_quad_push(output_decoded)
    require(source_topology["indices"] == [0, 1, 2, 3], "source quad indices differ")
    require(output_topology["indices"] == recipe["indices"],
            "output quad indices differ from recipe")

    allowed_positions = range(base.POSITION_OFFSET, base.POSITION_OFFSET + base.POSITION_SIZE)
    allowed_indices = range(INDEX_PARAMETER_OFFSET, INDEX_PARAMETER_OFFSET + INDEX_PARAMETER_SIZE)
    changed_offsets = [offset for offset, pair in enumerate(zip(source_decoded, output_decoded))
                       if pair[0] != pair[1]]
    require(all(offset in allowed_positions or offset in allowed_indices
                for offset in changed_offsets),
            "decoded output changed outside authorized geometry spans")
    normalized = bytearray(output_decoded)
    normalized[INDEX_PARAMETER_OFFSET:INDEX_PARAMETER_OFFSET + INDEX_PARAMETER_SIZE] = \
        source_decoded[INDEX_PARAMETER_OFFSET:INDEX_PARAMETER_OFFSET + INDEX_PARAMETER_SIZE]
    base.parse_target(bytes(normalized), expected_positions)

    pack_diff = base.compare_packs(source_pack, output_pack)
    output_sha = base.sha256_file(output_pack)
    no_op = expected_positions == source_positions and recipe["indices"] == [0, 1, 2, 3]
    mode = "no_op" if no_op else "patched"
    if no_op:
        require(output_span == source_span and output_sha == base.PACK_SHA256
                and pack_diff["changed_byte_count"] == 0,
                "no-op is not whole-volume byte-identical")
    else:
        require(output_sha != base.PACK_SHA256 and pack_diff["changed_byte_count"] > 0,
                "changed recipe did not change copied volume")
    expected_manifest = _expected_manifest(
        recipe, output_sha, output_decoded, output_body, consumed, padding, alias,
        scratch, len(changed_offsets), output_topology, mode,
    )
    require(manifest == expected_manifest, "manifest differs from independent reconstruction")

    def forbidden(value: object) -> bool:
        if isinstance(value, dict):
            return any(key in {"positions", "indices", "replacement_bytes"}
                       or forbidden(item) for key, item in value.items())
        if isinstance(value, list):
            return any(forbidden(item) for item in value)
        return isinstance(value, (bytes, bytearray))

    require(not forbidden(manifest), "manifest embeds authored geometry")
    require(base.sha256_file(index) == base.INDEX_SHA256
            and base.sha256_file(source_pack) == base.PACK_SHA256,
            "retail source changed during verification")
    return {
        "schema": VERIFY_SCHEMA,
        "mode": mode,
        "recipe_sha256": recipe["sha256"],
        "manifest_sha256": base.sha256(manifest_raw),
        "source_unchanged": True,
        "output_volume_sha256": output_sha,
        "outside_chunk_bit_exact": True,
        "decoded_changed_byte_count": len(changed_offsets),
        "outside_authorized_geometry_bit_exact": True,
        "position_after_sha256": base.sha256(expected_positions),
        "indices_after_sha256": base.sha256(struct.pack("<4H", *list(recipe["indices"]))),
        "indices_are_permutation": output_topology["indices_are_permutation"],
        "unique_index_count": output_topology["unique_index_count"],
        "nondegenerate_triangle_count": output_topology["nondegenerate_triangle_count"],
        "degenerate_triangle_count": output_topology["degenerate_triangle_count"],
        "consumed_bytes": consumed,
        "zero_gap_bytes": base.RETAIL_CONSUMED - consumed,
        "scratch_bytes": scratch,
        "fixed_tail_exact": True,
        "runtime_proved": False,
        "production_ready": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = verify(args.index, args.recipe, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError, GeometryVerifyError, base.VerifyError, json.JSONDecodeError,
        struct.error, KeyError, IndexError,
    ) as exc:
        raise SystemExit(f"error: {exc}") from exc
