#!/usr/bin/env python3
"""Conform source-indexed triangles to the proved NFL ``upper_deck`` writer.

This metadata-only authoring adapter accepts two or four oriented TRIANGLES
whose elements are IDs of the pinned 12 retail source records.  It proves that
the triangles can be represented exactly by one or two native QUADS, chooses a
deterministic record order, and emits the existing 4/8-record source-subset
recipe consumed by ``nfl_stadium_upper_deck_subset_patch.py``.

No positions, attributes, materials, bounds, or retail payload bytes are read
or emitted.  This is not edited-glTF import and does not widen the downstream
writer's offline-only, single-target claim boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_SCHEMA = (
    ROOT / "reports/specs/nfl2k5_upper_deck_source_triangle_mesh.schema.json"
)
DEFAULT_RECIPE_SCHEMA = (
    ROOT / "reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json"
)
DEFAULT_CLOSURE = (
    ROOT / "reports/specs/nfl2k5_upper_deck_source_subset_writeback_closure.v1.json"
)

INPUT_SCHEMA = "nfl2k5_upper_deck_source_triangle_mesh/v1"
RECIPE_SCHEMA = "nfl2k5_upper_deck_source_subset_recipe/v1"
VALIDATION_SCHEMA = "nfl2k5_upper_deck_source_triangle_conformance/v1"
TARGET_ID = "nfl2k5/stadium/o3280/c5/s1"
SOURCE_DECODED_SHA256 = (
    "229db9f309bf69eaa28901ae6e2e15b26a279b3f1f37abed01e36041c5e5ead8"
)
SOURCE_VERTEX_COUNT = 12
CHANGED_VERTEX_COUNTS = (4, 8)
ATTRIBUTE_POLICY = "copy_complete_source_records"

INPUT_SCHEMA_SIZE = 1_571
INPUT_SCHEMA_SHA256 = (
    "ac2822d22a01e66e004d9e65510c5ed100a1b58d1bdba11e55373a932a8c2dff"
)
RECIPE_SCHEMA_SIZE = 2_209
RECIPE_SCHEMA_SHA256 = (
    "4fac01c6cffe03481b456899ec2b2f3cd25f74954d5db94ccb3b8351f841ca4b"
)
CLOSURE_SIZE = 13_933
CLOSURE_SHA256 = (
    "38a4b176fb39cab86b134d3b1c6d03043513771229cdf1e444ef6baa01912fba"
)
MAX_INPUT_BYTES = 8 * 1024


class SourceTriangleConformanceError(ValueError):
    """The authority, source-indexed mesh, or native-quad proof failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceTriangleConformanceError(message)


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _regular_file(path: Path, label: str) -> Path:
    selected = path.expanduser()
    try:
        info = selected.lstat()
    except FileNotFoundError as exc:
        raise SourceTriangleConformanceError(
            f"{label} does not exist: {selected}"
        ) from exc
    require(
        stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        f"{label} must be a non-symlink regular file",
    )
    return selected.resolve(strict=True)


def _load_json(path: Path, label: str, maximum: int) -> tuple[dict[str, Any], bytes]:
    selected = _regular_file(path, label)
    size = selected.stat().st_size
    require(0 < size <= maximum, f"{label} size is outside its limit")
    payload = selected.read_bytes()
    require(len(payload) == size, f"{label} changed while reading")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                SourceTriangleConformanceError(
                    f"non-finite JSON constant {token} is forbidden"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceTriangleConformanceError(
            f"{label} is not UTF-8 JSON: {exc}"
        ) from exc
    require(isinstance(value, dict), f"{label} root must be an object")
    require(payload == canonical_json(value), f"{label} must be canonical sorted JSON")
    return value, payload


def _load_pinned_json(
    path: Path,
    label: str,
    expected_size: int,
    expected_sha256: str,
) -> dict[str, Any]:
    value, payload = _load_json(path, label, expected_size)
    require(
        len(payload) == expected_size and sha256(payload) == expected_sha256,
        f"{label} size or SHA-256 differs from the pinned authority",
    )
    return value


def _validate_input_schema(schema: dict[str, Any]) -> None:
    require(
        schema.get("$id") == INPUT_SCHEMA
        and schema.get("additionalProperties") is False,
        "source-triangle schema identity or closed-object rule differs",
    )
    require(
        schema.get("required")
        == [
            "schema",
            "target_id",
            "source_decoded_sha256",
            "primitive",
            "attribute_policy",
            "triangles",
        ],
        "source-triangle schema required fields differ",
    )
    properties = schema.get("properties", {})
    require(
        properties.get("schema", {}).get("const") == INPUT_SCHEMA
        and properties.get("target_id", {}).get("const") == TARGET_ID
        and properties.get("source_decoded_sha256", {}).get("const")
        == SOURCE_DECODED_SHA256
        and properties.get("primitive", {}).get("const") == "TRIANGLES"
        and properties.get("attribute_policy", {}).get("const")
        == ATTRIBUTE_POLICY,
        "source-triangle schema target or policy pins differ",
    )
    triangles = properties.get("triangles", {})
    element = triangles.get("items", {})
    require(
        triangles.get("minItems") == 2
        and triangles.get("maxItems") == 4
        and triangles.get("uniqueItems") is True
        and element.get("minItems") == 3
        and element.get("maxItems") == 3
        and element.get("uniqueItems") is True
        and element.get("items")
        == {"maximum": 11, "minimum": 0, "type": "integer"},
        "source-triangle schema topology domain differs",
    )


def _validate_recipe_schema(schema: dict[str, Any]) -> None:
    require(
        schema.get("$id") == RECIPE_SCHEMA
        and schema.get("additionalProperties") is False,
        "downstream recipe schema identity or closed-object rule differs",
    )
    properties = schema.get("properties", {})
    require(
        properties.get("schema", {}).get("const") == RECIPE_SCHEMA
        and properties.get("target_id", {}).get("const") == TARGET_ID
        and properties.get("source_decoded_sha256", {}).get("const")
        == SOURCE_DECODED_SHA256
        and properties.get("new_vertex_count", {}).get("enum") == [4, 8],
        "downstream recipe schema target/count pins differ",
    )
    source_ids = properties.get("source_vertex_ids", {})
    require(
        source_ids.get("uniqueItems") is True
        and source_ids.get("minItems") == 4
        and source_ids.get("maxItems") == 8
        and source_ids.get("items")
        == {"maximum": 11, "minimum": 0, "type": "integer"},
        "downstream recipe source-ID domain differs",
    )


def _validate_closure(closure: dict[str, Any]) -> None:
    require(
        closure.get("schema")
        == "nfl2k5_upper_deck_source_subset_writeback_closure/v1",
        "downstream closure schema differs",
    )
    scope = closure.get("scope", {})
    require(
        scope.get("target_id") == TARGET_ID
        and scope.get("status") == "offline-byte-roundtrip-proved",
        "downstream closure target or status differs",
    )
    claims = closure.get("claim_flags", {})
    require(
        claims.get("changed_count_source_subset_writer_implemented") is True
        and claims.get("independent_changed_count_verifier_implemented") is True
        and claims.get("nonidentity_synchronized_whole_record_remap_proved") is True
        and claims.get("identity_noop_whole_volume_exact") is True
        and claims.get("arbitrary_external_vertex_authoring_proved") is False
        and claims.get("edited_gltf_import_proved") is False
        and claims.get("bounds_or_culling_serializer_proved") is False
        and claims.get("runtime_visibility_proved") is False
        and claims.get("production_ready") is False,
        "downstream closure claim boundary differs",
    )
    changed = closure.get("implementation_contract", {}).get("changed_modes", {})
    require(
        changed.get("admitted_vertex_counts") == [4, 8]
        and changed.get("source_vertex_id_range") == [0, 11]
        and changed.get("source_vertex_ids_must_be_distinct") is True
        and changed.get("complete_records_copied_across_every_active_stream") is True
        and changed.get("external_positions_or_attributes_admitted") is False,
        "downstream changed-mode contract differs",
    )
    shape = closure.get("format_contract", {}).get("shape", {})
    require(
        shape.get("native_primitive") == "QUADS"
        and shape.get("draw_arrays_start") == 0
        and shape.get("source_vertex_count") == SOURCE_VERTEX_COUNT
        and shape.get("target_id") == TARGET_ID,
        "downstream native-quad target differs",
    )
    authority = closure.get("authority", {}).get("recipe_schema", {})
    require(
        authority.get("schema") == RECIPE_SCHEMA
        and authority.get("sha256") == RECIPE_SCHEMA_SHA256
        and authority.get("size_bytes") == RECIPE_SCHEMA_SIZE,
        "downstream closure recipe authority differs",
    )


def load_authorities(
    input_schema_path: Path = DEFAULT_INPUT_SCHEMA,
    recipe_schema_path: Path = DEFAULT_RECIPE_SCHEMA,
    closure_path: Path = DEFAULT_CLOSURE,
) -> dict[str, dict[str, Any]]:
    input_schema = _load_pinned_json(
        input_schema_path,
        "source-triangle schema",
        INPUT_SCHEMA_SIZE,
        INPUT_SCHEMA_SHA256,
    )
    recipe_schema = _load_pinned_json(
        recipe_schema_path,
        "downstream recipe schema",
        RECIPE_SCHEMA_SIZE,
        RECIPE_SCHEMA_SHA256,
    )
    closure = _load_pinned_json(
        closure_path,
        "downstream source-subset closure",
        CLOSURE_SIZE,
        CLOSURE_SHA256,
    )
    _validate_input_schema(input_schema)
    _validate_recipe_schema(recipe_schema)
    _validate_closure(closure)
    return {
        "input_schema": input_schema,
        "recipe_schema": recipe_schema,
        "closure": closure,
    }


def _canonical_oriented_triangle(values: Sequence[int]) -> tuple[int, int, int]:
    require(len(values) == 3, "triangle must contain exactly three source IDs")
    triangle = tuple(values)
    rotations = (
        triangle,
        (triangle[1], triangle[2], triangle[0]),
        (triangle[2], triangle[0], triangle[1]),
    )
    return min(rotations)


def _triangle_multiset(
    triangles: Iterable[Sequence[int]],
) -> tuple[tuple[int, int, int], ...]:
    return tuple(sorted(_canonical_oriented_triangle(row) for row in triangles))


def expand_native_quads(source_vertex_ids: Sequence[int]) -> list[list[int]]:
    require(
        len(source_vertex_ids) in CHANGED_VERTEX_COUNTS,
        "native-quad source-ID count must be exactly four or eight",
    )
    triangles: list[list[int]] = []
    for base in range(0, len(source_vertex_ids), 4):
        a, b, c, d = source_vertex_ids[base : base + 4]
        triangles.extend(([a, b, c], [a, c, d]))
    return triangles


def _canonical_quad_for_pair(
    left: Sequence[int], right: Sequence[int]
) -> tuple[int, int, int, int] | None:
    intended = _triangle_multiset((left, right))
    source_ids = sorted(set(left) | set(right))
    if len(source_ids) != 4:
        return None
    candidates: set[tuple[int, int, int, int]] = set()
    for candidate in itertools.permutations(source_ids):
        if _triangle_multiset(expand_native_quads(candidate)) != intended:
            continue
        rotated = candidate[2:] + candidate[:2]
        candidates.add(min(candidate, rotated))
    if not candidates:
        return None
    require(
        len(candidates) == 1,
        "triangle pair has more than one oriented native-quad representation",
    )
    return next(iter(candidates))


def _pairings(count: int) -> tuple[tuple[tuple[int, int], ...], ...]:
    if count == 2:
        return (((0, 1),),)
    require(count == 4, "source mesh must contain exactly two or four triangles")
    return (
        ((0, 1), (2, 3)),
        ((0, 2), (1, 3)),
        ((0, 3), (1, 2)),
    )


def conform_source_indexed_quads(
    triangles: object,
) -> tuple[list[int], dict[str, Any]]:
    require(isinstance(triangles, list), "triangles must be an array")
    require(
        len(triangles) in (2, 4),
        "source mesh must contain exactly two or four triangles",
    )
    checked: list[tuple[int, int, int]] = []
    for triangle_index, row in enumerate(triangles):
        require(
            isinstance(row, list) and len(row) == 3,
            f"triangles[{triangle_index}] must contain exactly three source IDs",
        )
        values: list[int] = []
        for element_index, value in enumerate(row):
            require(
                type(value) is int,
                f"triangles[{triangle_index}][{element_index}] must be an integer, not a boolean",
            )
            require(
                0 <= value < SOURCE_VERTEX_COUNT,
                f"triangles[{triangle_index}][{element_index}] is outside [0,11]",
            )
            values.append(value)
        require(
            len(set(values)) == 3,
            f"triangles[{triangle_index}] is topologically degenerate",
        )
        checked.append(tuple(values))

    oriented = [_canonical_oriented_triangle(row) for row in checked]
    require(
        len(set(oriented)) == len(oriented),
        "duplicate oriented triangle is forbidden, including cyclic duplicates",
    )
    expected_vertex_count = len(checked) * 2
    require(
        len(set(value for row in checked for value in row)) == expected_vertex_count,
        "one or two native quads must use exactly four or eight distinct source IDs",
    )

    conformed: set[tuple[int, ...]] = set()
    for pairing in _pairings(len(checked)):
        quads: list[tuple[int, int, int, int]] = []
        failed = False
        for left_index, right_index in pairing:
            quad = _canonical_quad_for_pair(
                checked[left_index], checked[right_index]
            )
            if quad is None:
                failed = True
                break
            quads.append(quad)
        if failed:
            continue
        flattened = tuple(value for quad in sorted(quads) for value in quad)
        if len(set(flattened)) != len(flattened):
            continue
        if _triangle_multiset(expand_native_quads(flattened)) != _triangle_multiset(
            checked
        ):
            continue
        conformed.add(flattened)

    require(
        conformed,
        "triangles cannot be partitioned into disjoint oriented native QUADS",
    )
    require(
        len(conformed) == 1,
        "triangles have multiple source-record/native-quad conformations",
    )
    source_ids = list(next(iter(conformed)))
    return source_ids, {
        "input_triangle_count": len(checked),
        "native_quad_count": len(source_ids) // 4,
        "new_vertex_count": len(source_ids),
        "distinct_source_vertex_count": len(set(source_ids)),
        "oriented_triangle_multiset_preserved": True,
        "winding_reversal_admitted": False,
        "external_vertex_or_attribute_values_admitted": False,
    }


def load_source_mesh(path: Path) -> tuple[dict[str, Any], bytes]:
    value, payload = _load_json(path, "source-indexed triangle mesh", MAX_INPUT_BYTES)
    require(
        set(value)
        == {
            "attribute_policy",
            "primitive",
            "schema",
            "source_decoded_sha256",
            "target_id",
            "triangles",
        },
        "source-indexed triangle mesh fields differ from v1",
    )
    require(value.get("schema") == INPUT_SCHEMA, "source mesh schema differs")
    require(value.get("target_id") == TARGET_ID, "source mesh target differs")
    require(
        value.get("source_decoded_sha256") == SOURCE_DECODED_SHA256,
        "source mesh decoded-source identity differs",
    )
    require(value.get("primitive") == "TRIANGLES", "source mesh primitive differs")
    require(
        value.get("attribute_policy") == ATTRIBUTE_POLICY,
        "source mesh attribute policy differs",
    )
    return value, payload


def conform_mesh(value: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    source_ids, facts = conform_source_indexed_quads(value.get("triangles"))
    recipe = {
        "new_vertex_count": len(source_ids),
        "schema": RECIPE_SCHEMA,
        "source_decoded_sha256": SOURCE_DECODED_SHA256,
        "source_vertex_ids": source_ids,
        "target_id": TARGET_ID,
    }
    require(
        len(source_ids) in CHANGED_VERTEX_COUNTS
        and len(set(source_ids)) == len(source_ids),
        "conformed recipe escaped the downstream count/source-ID boundary",
    )
    return recipe, facts


def _write_exclusive(path: Path, payload: bytes) -> Path:
    selected = path.expanduser()
    parent = selected.parent
    try:
        parent_info = parent.lstat()
    except FileNotFoundError as exc:
        raise SourceTriangleConformanceError(
            f"output parent does not exist: {parent}"
        ) from exc
    require(
        stat.S_ISDIR(parent_info.st_mode) and not stat.S_ISLNK(parent_info.st_mode),
        "output parent must be a non-symlink directory",
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(selected, flags, 0o600)
    except FileExistsError as exc:
        raise SourceTriangleConformanceError("output already exists") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            selected.unlink()
        except OSError:
            pass
        raise
    resolved = selected.resolve(strict=True)
    require(
        resolved.read_bytes() == payload,
        "published recipe differs from intended canonical bytes",
    )
    return resolved


def _success_summary(
    input_payload: bytes,
    recipe_payload: bytes,
    facts: dict[str, Any],
) -> dict[str, Any]:
    return {
        "attribute_policy": ATTRIBUTE_POLICY,
        "contains_retail_geometry": False,
        "edited_gltf_import_proved": False,
        "input_sha256": sha256(input_payload),
        "native_quad_count": facts["native_quad_count"],
        "new_vertex_count": facts["new_vertex_count"],
        "oriented_triangle_multiset_preserved": True,
        "output_recipe_schema": RECIPE_SCHEMA,
        "output_recipe_sha256": sha256(recipe_payload),
        "runtime_visibility_proved": False,
        "schema": VALIDATION_SCHEMA,
        "target_id": TARGET_ID,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Conform source-record TRIANGLES into the pinned NFL 2K5 "
            "upper_deck 4/8-record native-QUADS recipe."
        )
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="exclusive new recipe path; omit to write canonical recipe JSON to stdout",
    )
    parser.add_argument("--input-schema", type=Path, default=DEFAULT_INPUT_SCHEMA)
    parser.add_argument("--recipe-schema", type=Path, default=DEFAULT_RECIPE_SCHEMA)
    parser.add_argument("--closure", type=Path, default=DEFAULT_CLOSURE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        load_authorities(args.input_schema, args.recipe_schema, args.closure)
        source_mesh, input_payload = load_source_mesh(args.input)
        recipe, facts = conform_mesh(source_mesh)
        recipe_payload = canonical_json(recipe)
        if args.output is None:
            sys.stdout.buffer.write(recipe_payload)
        else:
            _write_exclusive(args.output, recipe_payload)
            print(
                json.dumps(
                    _success_summary(input_payload, recipe_payload, facts),
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
    except (OSError, SourceTriangleConformanceError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
