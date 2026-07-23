#!/usr/bin/env python3
"""Validate the complete NFL 2K5 SCNE embedded-texture PNG catalog."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from nfl_scne_embedded_texture_png import (
    MATERIAL_FIELDS,
    OCCURRENCE_FIELDS,
    PNG_FIELDS,
    SCHEMA,
    parse_png_rgba,
    sha256_bytes,
    sha256_file,
)


class ValidationError(ValueError):
    pass


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))


def serialized(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def verify_json_tsv(
    json_rows: list[dict[str, Any]],
    tsv_rows: list[dict[str, str]],
    fields: list[str],
    label: str,
) -> None:
    if len(json_rows) != len(tsv_rows):
        raise ValidationError(f"{label}: JSON/TSV row count mismatch")
    for index, (json_row, tsv_row) in enumerate(zip(json_rows, tsv_rows, strict=True)):
        if list(tsv_row) != fields:
            raise ValidationError(f"{label}: TSV field order changed")
        for field in fields:
            if serialized(json_row.get(field)) != tsv_row[field]:
                raise ValidationError(
                    f"{label} row {index} field {field}: "
                    f"{serialized(json_row.get(field))!r} != {tsv_row[field]!r}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--occurrences", type=Path, required=True)
    parser.add_argument("--materials", type=Path, required=True)
    parser.add_argument("--pngs", type=Path, required=True)
    parser.add_argument("--source-textures", type=Path, required=True)
    parser.add_argument("--source-materials", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--minimum-free-gib", type=int, default=10)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ValidationError("manifest schema mismatch")
    occurrence_rows = read_tsv(args.occurrences)
    material_rows = read_tsv(args.materials)
    png_rows = read_tsv(args.pngs)
    source_textures = read_tsv(args.source_textures)
    source_materials = read_tsv(args.source_materials)

    verify_json_tsv(
        manifest["occurrences"], occurrence_rows, OCCURRENCE_FIELDS, "occurrences"
    )
    verify_json_tsv(
        manifest["materials"], material_rows, MATERIAL_FIELDS, "materials"
    )
    verify_json_tsv(manifest["pngs"], png_rows, PNG_FIELDS, "PNGs")

    summary = manifest["summary"]
    exact_summary = {
        "scene_count": 4616,
        "represented_scene_count": 4007,
        "texture_occurrence_count": 37389,
        "p8_occurrence_count": 37389,
        "unique_rgba_count": 5351,
        "png_count": 5351,
        "deduplicated_occurrence_count": 32038,
        "material_row_count": 55905,
        "mapped_material_count": 45413,
        "unmapped_material_count": 10492,
        "unreferenced_texture_occurrence_count": 157,
        "minimum_free_space_bytes": 10 * 1024**3,
        "all_source_descriptors_replayed": True,
        "all_source_rgba_hashes_match": True,
        "all_unique_png_ihdrs_match": True,
        "all_unique_png_rgba_hashes_match": True,
        "all_material_pointer_fields_replayed": True,
        "all_material_occurrence_links_preserved": True,
        "png_tree_has_no_missing_or_extra_files": True,
    }
    for key, value in exact_summary.items():
        if summary.get(key) != value:
            raise ValidationError(f"summary {key}: {summary.get(key)!r} != {value!r}")
    if len(occurrence_rows) != 37389 or len(material_rows) != 55905 or len(png_rows) != 5351:
        raise ValidationError("catalog row totals changed")
    if len(source_textures) != 37389 or len(source_materials) != 55905:
        raise ValidationError("source ledger totals changed")

    sources = manifest["sources"]
    for key, path in (
        ("texture_occurrences", args.source_textures),
        ("material_mappings", args.source_materials),
    ):
        if sources[key] != str(path) or sources[f"{key}_sha256"] != sha256_file(path):
            raise ValidationError(f"source provenance mismatch for {key}")

    source_texture_fields = [
        "scene_index", "outer_index", "chunk_index", "scene_name",
        "descriptor_offset", "unknown0", "pixel_offset", "palette_offset",
        "packed_format", "packed_size", "descriptor_flags", "extra_word_18",
        "extra_word_1c", "dimensions", "format_code", "format_name",
        "mip_levels", "width", "height", "depth", "conversion_status",
        "rgba_sha256", "mapped_material_count", "mapped_material_names",
    ]
    for index, (source, output) in enumerate(
        zip(source_textures, occurrence_rows, strict=True)
    ):
        if output["occurrence_index"] != str(index):
            raise ValidationError("occurrence index is not contiguous")
        if output["texture_index"] != source["index"]:
            raise ValidationError("source texture index projection mismatch")
        for field in source_texture_fields:
            if output[field] != source[field]:
                raise ValidationError(f"occurrence {index}: source field {field} changed")
        if output["format_name"] != "P8" or output["conversion_status"] != "base_level_supported":
            raise ValidationError("non-P8 or unsupported occurrence entered catalog")

    source_material_fields = [
        "scene_index", "outer_index", "chunk_index", "scene_name",
        "material_index", "material_name", "material_offset",
        "texture_pointer_field", "texture_target", "texture_index",
    ]
    for index, (source, output) in enumerate(
        zip(source_materials, material_rows, strict=True)
    ):
        if output["material_occurrence_index"] != str(index):
            raise ValidationError("material occurrence index is not contiguous")
        for field in source_material_fields:
            if output[field] != source[field]:
                raise ValidationError(f"material {index}: source field {field} changed")
        expected_status = (
            "mapped_embedded_texture"
            if source["conversion_status"] == "base_level_supported"
            else "unmapped"
        )
        if output["mapping_status"] != expected_status:
            raise ValidationError(f"material {index}: mapping status changed")

    png_by_hash = {row["rgba_sha256"]: row for row in png_rows}
    if len(png_by_hash) != 5351:
        raise ValidationError("duplicate RGBA row in unique PNG ledger")
    occurrences_by_hash = Counter(row["rgba_sha256"] for row in occurrence_rows)
    materials_by_hash = Counter(
        row["rgba_sha256"] for row in material_rows if row["mapping_status"] != "unmapped"
    )
    dimensions_by_hash: dict[str, set[tuple[int, int]]] = defaultdict(set)
    first_occurrence: dict[str, dict[str, str]] = {}
    occurrence_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in occurrence_rows:
        rgba_hash = row["rgba_sha256"]
        dimensions_by_hash[rgba_hash].add((int(row["width"]), int(row["height"])))
        first_occurrence.setdefault(rgba_hash, row)
        key = (row["scene_index"], row["texture_index"])
        if key in occurrence_by_key:
            raise ValidationError("duplicate scene/texture occurrence key")
        occurrence_by_key[key] = row
        unique = png_by_hash.get(rgba_hash)
        if unique is None:
            raise ValidationError("occurrence references absent PNG hash")
        for field in ("png_path", "png_sha256", "png_size"):
            if row[field] != unique[field]:
                raise ValidationError("occurrence PNG projection mismatch")
    if any(len(values) != 1 for values in dimensions_by_hash.values()):
        raise ValidationError("one RGBA hash spans multiple dimensions")

    mapped_names: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in material_rows:
        if row["mapping_status"] == "unmapped":
            for field in (
                "texture_index", "texture_descriptor_offset", "rgba_sha256",
                "png_path", "png_sha256", "png_size",
            ):
                if row[field] != "":
                    raise ValidationError("unmapped material has derived texture data")
            continue
        key = (row["scene_index"], row["texture_index"])
        occurrence = occurrence_by_key.get(key)
        if occurrence is None:
            raise ValidationError("mapped material refers to absent occurrence")
        if row["texture_target"] != occurrence["descriptor_offset"]:
            raise ValidationError("material target/descriptor mismatch")
        for material_field, occurrence_field in (
            ("texture_descriptor_offset", "descriptor_offset"),
            ("rgba_sha256", "rgba_sha256"),
            ("png_path", "png_path"),
            ("png_sha256", "png_sha256"),
            ("png_size", "png_size"),
        ):
            if row[material_field] != occurrence[occurrence_field]:
                raise ValidationError("mapped material projection mismatch")
        mapped_names[key].append(row["material_name"])
    for key, occurrence in occurrence_by_key.items():
        names = mapped_names.get(key, [])
        if len(names) != int(occurrence["mapped_material_count"]):
            raise ValidationError("occurrence material count mismatch")
        if "|".join(names) != occurrence["mapped_material_names"]:
            raise ValidationError("occurrence material name order mismatch")

    expected_paths: set[Path] = set()
    aggregate = hashlib.sha256()
    total_png_bytes = 0
    for rgba_hash in sorted(png_by_hash):
        row = png_by_hash[rgba_hash]
        expected_path = (
            args.asset_dir / "by_rgba_sha256" / rgba_hash[:2] / f"{rgba_hash}.png"
        )
        expected_paths.add(expected_path)
        logical_suffix = f"by_rgba_sha256/{rgba_hash[:2]}/{rgba_hash}.png"
        if not row["png_path"].endswith(logical_suffix):
            raise ValidationError("unique PNG logical path mismatch")
        width, height, rgba = parse_png_rgba(expected_path)
        if (width, height) != (int(row["width"]), int(row["height"])):
            raise ValidationError("unique PNG IHDR mismatch")
        if sha256_bytes(rgba) != rgba_hash:
            raise ValidationError("unique PNG decoded RGBA hash mismatch")
        png_bytes = expected_path.read_bytes()
        if sha256_bytes(png_bytes) != row["png_sha256"]:
            raise ValidationError("unique PNG file hash mismatch")
        if len(png_bytes) != int(row["png_size"]):
            raise ValidationError("unique PNG size mismatch")
        if int(row["occurrence_count"]) != occurrences_by_hash[rgba_hash]:
            raise ValidationError("unique PNG occurrence count mismatch")
        if int(row["mapped_material_count"]) != materials_by_hash[rgba_hash]:
            raise ValidationError("unique PNG material count mismatch")
        representative = first_occurrence[rgba_hash]
        for unique_field, occurrence_field in (
            ("representative_scene_index", "scene_index"),
            ("representative_outer_index", "outer_index"),
            ("representative_chunk_index", "chunk_index"),
            ("representative_texture_index", "texture_index"),
            ("representative_descriptor_offset", "descriptor_offset"),
        ):
            if row[unique_field] != representative[occurrence_field]:
                raise ValidationError("unique PNG representative mismatch")
        aggregate.update(row["png_path"].encode("utf-8") + b"\0")
        aggregate.update(bytes.fromhex(row["png_sha256"]))
        total_png_bytes += len(png_bytes)

    actual_paths = set((args.asset_dir / "by_rgba_sha256").glob("*/*.png"))
    if actual_paths != expected_paths:
        raise ValidationError("PNG tree has missing or extra files")
    if total_png_bytes != summary["total_png_bytes"]:
        raise ValidationError("total PNG byte count mismatch")
    if summary["occurrence_dimension_counts"] != dict(
        sorted(Counter(f"{row['width']}x{row['height']}" for row in occurrence_rows).items())
    ):
        raise ValidationError("occurrence dimension domain mismatch")
    if summary["unique_png_dimension_counts"] != dict(
        sorted(Counter(f"{row['width']}x{row['height']}" for row in png_rows).items())
    ):
        raise ValidationError("unique PNG dimension domain mismatch")
    if shutil.disk_usage(args.asset_dir).free < args.minimum_free_gib * 1024**3:
        raise ValidationError("free-space floor was violated")

    if manifest["evidence"]["semantic_limit"] != (
        "mapping proves material occurrence -> descriptor, not shader slot or baseColor use"
    ):
        raise ValidationError("semantic limit changed")
    if not all(item.startswith("PORTME:") for item in manifest["portme"]):
        raise ValidationError("manifest lacks explicit PORTME boundaries")

    print(
        "NFL_SCNE_EMBEDDED_TEXTURE_PNG_VALIDATION_PASS "
        f"occurrences={len(occurrence_rows)} unique_png={len(png_rows)} "
        f"materials={len(material_rows)} tree_sha256={aggregate.hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, OSError, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
