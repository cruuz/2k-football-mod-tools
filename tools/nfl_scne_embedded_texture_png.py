#!/usr/bin/env python3
"""Export every NFL 2K5 SCNE-embedded P8 texture as deduplicated RGBA PNG.

This consumes the already validated SCNE descriptor/material ledgers, then
replays each represented scene directly from the outer archive.  It verifies
all 37,389 texture descriptors and all 55,905 material +0x30 fields before
writing one deterministic PNG per decoded-RGBA SHA-256.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import struct
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from nfl_outer import parse_archive, read_entry_range
from nfl_scene_probe import decode_resource, parse_inventory
from nfl_scne_inventory import pointer_name, resolve_relative, texture_info
from nfl_txtr import PNG_SIGNATURE, TxtrError, texture_to_rgba, write_png


SCHEMA = "nfl2k5_scne_embedded_texture_png/v1"
GIB = 1024**3

OCCURRENCE_FIELDS = [
    "occurrence_index", "scene_index", "outer_index", "outer_id",
    "chunk_index", "chunk_offset", "scene_name", "texture_index",
    "descriptor_offset", "unknown0", "pixel_offset", "palette_offset",
    "packed_format", "packed_size", "descriptor_flags", "extra_word_18",
    "extra_word_1c", "dimensions", "format_code", "format_name",
    "mip_levels", "width", "height", "depth", "conversion_status",
    "rgba_sha256", "png_path", "png_sha256", "png_size",
    "mapped_material_count", "mapped_material_names",
]

MATERIAL_FIELDS = [
    "material_occurrence_index", "scene_index", "outer_index", "outer_id",
    "chunk_index", "chunk_offset", "scene_name", "material_index",
    "material_name", "material_offset", "texture_pointer_field",
    "texture_target", "texture_index", "mapping_status", "format_name",
    "width", "height", "texture_descriptor_offset", "pixel_offset",
    "palette_offset", "packed_format", "packed_size", "descriptor_flags",
    "rgba_sha256", "png_path", "png_sha256", "png_size",
]

PNG_FIELDS = [
    "rgba_sha256", "width", "height", "png_path", "png_sha256",
    "png_size", "occurrence_count", "mapped_material_count",
    "representative_scene_index", "representative_outer_index",
    "representative_chunk_index", "representative_texture_index",
    "representative_descriptor_offset",
]


class CatalogError(ValueError):
    """A source, mapping, decoded texture, PNG, or disk assertion failed."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))


def write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fields,
            dialect="excel-tab",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_optional_int(value: str) -> int | None:
    return None if value == "" else int(value, 0)


def parse_png_rgba(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise CatalogError(f"{path}: missing PNG signature")
    cursor = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    while cursor < len(data):
        if cursor + 12 > len(data):
            raise CatalogError(f"{path}: truncated PNG chunk header")
        size = struct.unpack_from(">I", data, cursor)[0]
        kind = data[cursor + 4 : cursor + 8]
        payload_start = cursor + 8
        payload_end = payload_start + size
        crc_end = payload_end + 4
        if crc_end > len(data):
            raise CatalogError(f"{path}: chunk {kind!r} exceeds file")
        payload = data[payload_start:payload_end]
        expected_crc = struct.unpack_from(">I", data, payload_end)[0]
        actual_crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise CatalogError(f"{path}: chunk {kind!r} CRC mismatch")
        chunks.append((kind, payload))
        cursor = crc_end
        if kind == b"IEND":
            break
    if cursor != len(data):
        raise CatalogError(f"{path}: trailing bytes after IEND")
    if [kind for kind, _ in chunks] != [b"IHDR", b"IDAT", b"IEND"]:
        raise CatalogError(f"{path}: unexpected deterministic PNG chunk sequence")
    ihdr = chunks[0][1]
    if len(ihdr) != 13:
        raise CatalogError(f"{path}: invalid IHDR length")
    width, height, depth, color, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    if (depth, color, compression, filtering, interlace) != (8, 6, 0, 0, 0):
        raise CatalogError(f"{path}: expected non-interlaced RGBA8 PNG")
    try:
        scanlines = zlib.decompress(chunks[1][1])
    except zlib.error as exc:
        raise CatalogError(f"{path}: invalid IDAT stream: {exc}") from exc
    stride = width * 4
    if len(scanlines) != height * (stride + 1):
        raise CatalogError(f"{path}: unexpected decompressed scanline size")
    rgba = bytearray(width * height * 4)
    for row in range(height):
        source = row * (stride + 1)
        if scanlines[source] != 0:
            raise CatalogError(f"{path}: generated row {row} is not filter type 0")
        target = row * stride
        rgba[target : target + stride] = scanlines[source + 1 : source + 1 + stride]
    return width, height, bytes(rgba)


def check_disk(path: Path, minimum_free_bytes: int, label: str) -> int:
    probe = path
    while not probe.exists():
        if probe.parent == probe:
            break
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free < minimum_free_bytes:
        raise CatalogError(
            f"{label}: free space {free} is below required {minimum_free_bytes} bytes"
        )
    return free


def int_field(row: dict[str, str], key: str) -> int:
    return int(row[key], 0)


def expected_texture_fields(row: dict[str, str]) -> dict[str, int | str]:
    numeric = (
        "descriptor_offset", "pixel_offset", "palette_offset", "packed_format",
        "packed_size", "descriptor_flags", "dimensions", "format_code",
        "mip_levels", "width", "height", "depth",
    )
    result: dict[str, int | str] = {key: int_field(row, key) for key in numeric}
    result["format_name"] = row["format_name"]
    return result


def verify_texture_descriptor(
    output: bytes,
    system_size: int,
    resource: Any,
    row: dict[str, str],
) -> bytes:
    descriptor = int_field(row, "descriptor_offset")
    texture_index = int_field(row, "index")
    info = texture_info(output, descriptor, row["scene_name"], texture_index)
    actual: dict[str, int | str] = {
        "descriptor_offset": info.descriptor_offset,
        "pixel_offset": info.pixel_offset,
        "palette_offset": info.palette_offset,
        "packed_format": info.packed_format,
        "packed_size": info.packed_size,
        "descriptor_flags": info.descriptor_flags,
        "dimensions": info.dimensions,
        "format_code": info.format_code,
        "format_name": info.format_name,
        "mip_levels": info.mip_levels,
        "width": info.width,
        "height": info.height,
        "depth": info.depth,
    }
    expected = expected_texture_fields(row)
    if actual != expected:
        raise CatalogError(
            f"scene {row['scene_index']} texture {texture_index}: descriptor mismatch "
            f"{actual!r} != {expected!r}"
        )
    for key, offset in (("unknown0", 0), ("extra_word_18", 0x18), ("extra_word_1c", 0x1C)):
        actual_raw = struct.unpack_from("<I", output, descriptor + offset)[0]
        if actual_raw != int(row[key], 0):
            raise CatalogError(
                f"scene {row['scene_index']} texture {texture_index}: {key} mismatch"
            )
    if row["format_name"] != "P8" or int_field(row, "format_code") != 0x0B:
        raise CatalogError("catalog scope requires every occurrence to be Xbox P8")
    if row["conversion_status"] != "base_level_supported":
        raise CatalogError("catalog scope requires every occurrence to be decodable")
    rgba = texture_to_rgba(output, resource.as_chunk(), info)
    if len(rgba) != info.width * info.height * 4:
        raise CatalogError("decoded RGBA size mismatch")
    if sha256_bytes(rgba) != row["rgba_sha256"]:
        raise CatalogError(
            f"scene {row['scene_index']} texture {texture_index}: RGBA hash mismatch"
        )
    if system_size != resource.word_08:
        raise CatalogError("internal system-size mismatch")
    return rgba


def logical_png_path(logical_root: str, rgba_sha256: str) -> str:
    return str(
        PurePosixPath(logical_root)
        / "by_rgba_sha256"
        / rgba_sha256[:2]
        / f"{rgba_sha256}.png"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--resource-scan", type=Path, required=True)
    parser.add_argument("--scne-inventory", type=Path, required=True)
    parser.add_argument("--textures", type=Path, required=True)
    parser.add_argument("--materials", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--logical-asset-root", required=True)
    parser.add_argument("--manifest-json", type=Path, required=True)
    parser.add_argument("--occurrences-tsv", type=Path, required=True)
    parser.add_argument("--materials-tsv", type=Path, required=True)
    parser.add_argument("--pngs-tsv", type=Path, required=True)
    parser.add_argument("--minimum-free-gib", type=int, default=10)
    parser.add_argument("--progress-every", type=int, default=250)
    args = parser.parse_args()

    if args.minimum_free_gib < 1:
        raise CatalogError("minimum free-space threshold must be positive")
    minimum_free = args.minimum_free_gib * GIB
    check_disk(args.asset_dir, minimum_free, "before export")

    texture_source = read_tsv(args.textures)
    material_source = read_tsv(args.materials)
    if len(texture_source) != 37389:
        raise CatalogError(f"expected 37,389 texture occurrences, found {len(texture_source)}")
    if len(material_source) != 55905:
        raise CatalogError(f"expected 55,905 material rows, found {len(material_source)}")

    scne_inventory = json.loads(args.scne_inventory.read_text(encoding="utf-8"))
    if scne_inventory.get("schema") != "nfl2k5_scne_inventory/v1":
        raise CatalogError("unexpected SCNE inventory schema")
    if scne_inventory["summary"]["embedded_texture_count"] != len(texture_source):
        raise CatalogError("SCNE JSON/texture TSV count mismatch")
    if scne_inventory["summary"]["material_mapping_count"] != len(material_source):
        raise CatalogError("SCNE JSON/material TSV count mismatch")
    compact_scenes = scne_inventory["scenes"]
    if len(compact_scenes) != 4616:
        raise CatalogError("expected 4,616 compact SCNE scene records")

    resource_inventory, resources = parse_inventory(args.resource_scan)
    selected = [record for record in resources if record.kind == "SCNE"]
    if len(selected) != 4616:
        raise CatalogError("resource scan does not contain 4,616 SCNE chunks")
    archive = parse_archive(args.index)

    textures_by_scene: dict[int, list[dict[str, str]]] = defaultdict(list)
    materials_by_scene: dict[int, list[dict[str, str]]] = defaultdict(list)
    for occurrence_index, row in enumerate(texture_source):
        scene_index = int_field(row, "scene_index")
        row["_occurrence_index"] = str(occurrence_index)
        textures_by_scene[scene_index].append(row)
    for material_index, row in enumerate(material_source):
        scene_index = int_field(row, "scene_index")
        row["_material_occurrence_index"] = str(material_index)
        materials_by_scene[scene_index].append(row)

    union_scenes = sorted(set(textures_by_scene) | set(materials_by_scene))
    if len(union_scenes) != 4007:
        raise CatalogError(f"expected 4,007 represented scenes, found {len(union_scenes)}")

    expected_hash_dimensions: dict[str, tuple[int, int]] = {}
    occurrence_counts: Counter[str] = Counter()
    for row in texture_source:
        rgba_hash = row["rgba_sha256"]
        dimensions = (int_field(row, "width"), int_field(row, "height"))
        prior = expected_hash_dimensions.setdefault(rgba_hash, dimensions)
        if prior != dimensions:
            raise CatalogError(f"RGBA hash {rgba_hash} occurs with multiple dimensions")
        occurrence_counts[rgba_hash] += 1
    if len(expected_hash_dimensions) != 5351:
        raise CatalogError(
            f"expected 5,351 unique RGBA hashes, found {len(expected_hash_dimensions)}"
        )

    png_by_rgba: dict[str, dict[str, Any]] = {}
    decoded_occurrence_rows: list[dict[str, Any]] = []
    material_rows_verified = 0
    logical_root = str(PurePosixPath(args.logical_asset_root))

    for represented_index, scene_index in enumerate(union_scenes, 1):
        resource = selected[scene_index]
        compact = compact_scenes[scene_index]
        if int(compact["scene_index"]) != scene_index:
            raise CatalogError(f"compact scene order mismatch at {scene_index}")
        if (int(compact["outer_index"]), int(compact["chunk_index"])) != (
            resource.outer_index,
            resource.chunk_index,
        ):
            raise CatalogError(f"resource/SCNE JSON mapping mismatch at scene {scene_index}")
        entry = archive.entries[resource.outer_index]
        span = read_entry_range(
            archive, entry, resource.chunk_offset, 0x20 + resource.stored_size
        )
        output, decode_detail = decode_resource(span, resource)
        if decode_detail["decoded_sha256"] != compact["decoded_sha256"]:
            raise CatalogError(f"scene {scene_index}: decoded source hash mismatch")
        system_size = resource.word_08
        header_name_target, scene_name = pointer_name(
            output, 0x10, system_size, f"scene {scene_index} name"
        )
        if header_name_target is None or scene_name != compact["name"]:
            raise CatalogError(f"scene {scene_index}: source name mismatch")

        scene_textures = textures_by_scene.get(scene_index, [])
        for expected_texture_index, row in enumerate(scene_textures):
            if int_field(row, "index") != expected_texture_index:
                raise CatalogError(
                    f"scene {scene_index}: non-contiguous texture index ledger"
                )
            if (int_field(row, "outer_index"), int_field(row, "chunk_index")) != (
                resource.outer_index,
                resource.chunk_index,
            ) or row["scene_name"] != scene_name:
                raise CatalogError(f"scene {scene_index}: texture provenance mismatch")
            rgba = verify_texture_descriptor(output, system_size, resource, row)
            rgba_hash = row["rgba_sha256"]
            width = int_field(row, "width")
            height = int_field(row, "height")
            png_record = png_by_rgba.get(rgba_hash)
            if png_record is None:
                check_disk(args.asset_dir, minimum_free, f"before PNG {rgba_hash}")
                relative_inside = (
                    Path("by_rgba_sha256") / rgba_hash[:2] / f"{rgba_hash}.png"
                )
                target = args.asset_dir / relative_inside
                write_png(target, width, height, rgba)
                png_width, png_height, png_rgba = parse_png_rgba(target)
                if (png_width, png_height) != (width, height):
                    raise CatalogError(f"{target}: PNG IHDR dimension mismatch")
                if sha256_bytes(png_rgba) != rgba_hash:
                    raise CatalogError(f"{target}: PNG-decoded RGBA hash mismatch")
                png_bytes = target.read_bytes()
                png_record = {
                    "rgba_sha256": rgba_hash,
                    "width": width,
                    "height": height,
                    "png_path": logical_png_path(logical_root, rgba_hash),
                    "png_sha256": sha256_bytes(png_bytes),
                    "png_size": len(png_bytes),
                    "occurrence_count": occurrence_counts[rgba_hash],
                    "mapped_material_count": 0,
                    "representative_scene_index": scene_index,
                    "representative_outer_index": resource.outer_index,
                    "representative_chunk_index": resource.chunk_index,
                    "representative_texture_index": expected_texture_index,
                    "representative_descriptor_offset": int_field(
                        row, "descriptor_offset"
                    ),
                }
                png_by_rgba[rgba_hash] = png_record
            elif (png_record["width"], png_record["height"]) != (width, height):
                raise CatalogError(f"RGBA hash {rgba_hash}: inconsistent dimensions")

            decoded_occurrence_rows.append(
                {
                    "occurrence_index": int_field(row, "_occurrence_index"),
                    "scene_index": scene_index,
                    "outer_index": resource.outer_index,
                    "outer_id": resource.outer_id,
                    "chunk_index": resource.chunk_index,
                    "chunk_offset": resource.chunk_offset,
                    "scene_name": scene_name,
                    "texture_index": expected_texture_index,
                    **{
                        key: int_field(row, key)
                        for key in (
                            "descriptor_offset", "pixel_offset", "palette_offset",
                            "packed_format", "packed_size", "descriptor_flags",
                            "dimensions", "format_code", "mip_levels", "width",
                            "height", "depth", "mapped_material_count",
                        )
                    },
                    "unknown0": row["unknown0"],
                    "extra_word_18": row["extra_word_18"],
                    "extra_word_1c": row["extra_word_1c"],
                    "format_name": row["format_name"],
                    "conversion_status": row["conversion_status"],
                    "rgba_sha256": rgba_hash,
                    "png_path": png_record["png_path"],
                    "png_sha256": png_record["png_sha256"],
                    "png_size": png_record["png_size"],
                    "mapped_material_names": row["mapped_material_names"],
                }
            )

        for expected_material_index, row in enumerate(
            materials_by_scene.get(scene_index, [])
        ):
            if (int_field(row, "outer_index"), int_field(row, "chunk_index")) != (
                resource.outer_index,
                resource.chunk_index,
            ) or row["scene_name"] != scene_name:
                raise CatalogError(f"scene {scene_index}: material provenance mismatch")
            material_index = int_field(row, "material_index")
            material_offset = int_field(row, "material_offset")
            if material_index != expected_material_index:
                raise CatalogError(
                    f"scene {scene_index}: non-contiguous material index ledger"
                )
            name_target, material_name = pointer_name(
                output,
                material_offset,
                system_size,
                f"scene {scene_index} material {material_index} name",
            )
            if name_target is None or material_name != row["material_name"]:
                raise CatalogError(
                    f"scene {scene_index} material {material_index}: name mismatch"
                )
            pointer_field = int_field(row, "texture_pointer_field")
            if pointer_field != material_offset + 0x30:
                raise CatalogError(
                    f"scene {scene_index} material {material_index}: +0x30 field mismatch"
                )
            target = resolve_relative(
                output,
                pointer_field,
                system_size,
                f"scene {scene_index} material {material_index} texture",
            )
            expected_target = parse_optional_int(row["texture_target"])
            if target != expected_target:
                raise CatalogError(
                    f"scene {scene_index} material {material_index}: target mismatch"
                )
            material_rows_verified += 1

        if args.progress_every and represented_index % args.progress_every == 0:
            print(
                f"exported/verified {represented_index}/{len(union_scenes)} represented "
                f"SCNE chunks; {len(decoded_occurrence_rows)}/{len(texture_source)} "
                f"occurrences; {len(png_by_rgba)}/{len(expected_hash_dimensions)} PNGs",
                file=sys.stderr,
                flush=True,
            )

    if len(decoded_occurrence_rows) != len(texture_source):
        raise CatalogError("not every texture occurrence was decoded")
    if material_rows_verified != len(material_source):
        raise CatalogError("not every material source row was verified")
    if set(png_by_rgba) != set(expected_hash_dimensions):
        raise CatalogError("not every unique RGBA hash received a PNG")

    occurrence_by_key = {
        (int(row["scene_index"]), int(row["texture_index"])): row
        for row in decoded_occurrence_rows
    }
    if len(occurrence_by_key) != len(decoded_occurrence_rows):
        raise CatalogError("duplicate scene/texture occurrence key")

    material_names_by_texture: dict[tuple[int, int], list[str]] = defaultdict(list)
    enriched_material_rows: list[dict[str, Any]] = []
    mapped_material_count = 0
    unmapped_material_count = 0
    for source in material_source:
        scene_index = int_field(source, "scene_index")
        resource = selected[scene_index]
        texture_index = parse_optional_int(source["texture_index"])
        base: dict[str, Any] = {
            "material_occurrence_index": int_field(source, "_material_occurrence_index"),
            "scene_index": scene_index,
            "outer_index": resource.outer_index,
            "outer_id": resource.outer_id,
            "chunk_index": resource.chunk_index,
            "chunk_offset": resource.chunk_offset,
            "scene_name": source["scene_name"],
            "material_index": int_field(source, "material_index"),
            "material_name": source["material_name"],
            "material_offset": int_field(source, "material_offset"),
            "texture_pointer_field": int_field(source, "texture_pointer_field"),
            "texture_target": parse_optional_int(source["texture_target"]),
            "texture_index": texture_index,
        }
        if texture_index is None:
            if source["conversion_status"] != "unmapped":
                raise CatalogError("null texture index lacks unmapped source status")
            base.update(
                {
                    "mapping_status": "unmapped",
                    "format_name": None,
                    "width": None,
                    "height": None,
                    "texture_descriptor_offset": None,
                    "pixel_offset": None,
                    "palette_offset": None,
                    "packed_format": None,
                    "packed_size": None,
                    "descriptor_flags": None,
                    "rgba_sha256": None,
                    "png_path": None,
                    "png_sha256": None,
                    "png_size": None,
                }
            )
            unmapped_material_count += 1
        else:
            occurrence = occurrence_by_key.get((scene_index, texture_index))
            if occurrence is None:
                raise CatalogError("mapped material refers to absent occurrence")
            if base["texture_target"] != occurrence["descriptor_offset"]:
                raise CatalogError("mapped material target != texture descriptor")
            if (
                source["format_name"],
                int_field(source, "width"),
                int_field(source, "height"),
                source["conversion_status"],
            ) != (
                occurrence["format_name"],
                occurrence["width"],
                occurrence["height"],
                occurrence["conversion_status"],
            ):
                raise CatalogError("material/texture projection mismatch")
            base.update(
                {
                    "mapping_status": "mapped_embedded_texture",
                    "format_name": occurrence["format_name"],
                    "width": occurrence["width"],
                    "height": occurrence["height"],
                    "texture_descriptor_offset": occurrence["descriptor_offset"],
                    "pixel_offset": occurrence["pixel_offset"],
                    "palette_offset": occurrence["palette_offset"],
                    "packed_format": occurrence["packed_format"],
                    "packed_size": occurrence["packed_size"],
                    "descriptor_flags": occurrence["descriptor_flags"],
                    "rgba_sha256": occurrence["rgba_sha256"],
                    "png_path": occurrence["png_path"],
                    "png_sha256": occurrence["png_sha256"],
                    "png_size": occurrence["png_size"],
                }
            )
            mapped_material_count += 1
            material_names_by_texture[(scene_index, texture_index)].append(
                source["material_name"]
            )
            png_by_rgba[str(occurrence["rgba_sha256"])]["mapped_material_count"] += 1
        enriched_material_rows.append(base)

    for source, occurrence in zip(texture_source, decoded_occurrence_rows, strict=True):
        key = (int(occurrence["scene_index"]), int(occurrence["texture_index"]))
        names = material_names_by_texture.get(key, [])
        if len(names) != int_field(source, "mapped_material_count"):
            raise CatalogError(f"occurrence {key}: mapped material count mismatch")
        if "|".join(names) != source["mapped_material_names"]:
            raise CatalogError(f"occurrence {key}: mapped material name order mismatch")

    png_rows = [png_by_rgba[key] for key in sorted(png_by_rgba)]
    expected_physical = {
        args.asset_dir / "by_rgba_sha256" / row["rgba_sha256"][:2] /
        f"{row['rgba_sha256']}.png"
        for row in png_rows
    }
    actual_physical = set((args.asset_dir / "by_rgba_sha256").glob("*/*.png"))
    if actual_physical != expected_physical:
        raise CatalogError(
            f"PNG tree mismatch: expected {len(expected_physical)}, found {len(actual_physical)}"
        )

    occurrence_dimensions = Counter(
        f"{row['width']}x{row['height']}" for row in decoded_occurrence_rows
    )
    unique_dimensions = Counter(f"{row['width']}x{row['height']}" for row in png_rows)
    summary = {
        "scene_count": len(selected),
        "represented_scene_count": len(union_scenes),
        "texture_occurrence_count": len(decoded_occurrence_rows),
        "p8_occurrence_count": len(decoded_occurrence_rows),
        "unique_rgba_count": len(png_rows),
        "png_count": len(png_rows),
        "deduplicated_occurrence_count": len(decoded_occurrence_rows) - len(png_rows),
        "material_row_count": len(enriched_material_rows),
        "mapped_material_count": mapped_material_count,
        "unmapped_material_count": unmapped_material_count,
        "unreferenced_texture_occurrence_count": sum(
            int(row["mapped_material_count"]) == 0 for row in decoded_occurrence_rows
        ),
        "occurrence_dimension_counts": dict(sorted(occurrence_dimensions.items())),
        "unique_png_dimension_counts": dict(sorted(unique_dimensions.items())),
        "total_png_bytes": sum(int(row["png_size"]) for row in png_rows),
        "minimum_free_space_bytes": minimum_free,
        "all_source_descriptors_replayed": True,
        "all_source_rgba_hashes_match": True,
        "all_unique_png_ihdrs_match": True,
        "all_unique_png_rgba_hashes_match": True,
        "all_material_pointer_fields_replayed": True,
        "all_material_occurrence_links_preserved": True,
        "png_tree_has_no_missing_or_extra_files": True,
    }
    if (mapped_material_count, unmapped_material_count) != (45413, 10492):
        raise CatalogError("material mapping totals changed")

    manifest = {
        "schema": SCHEMA,
        "sources": {
            "index": str(args.index),
            "index_sha256": sha256_file(args.index),
            "resource_scan": str(args.resource_scan),
            "resource_scan_sha256": sha256_file(args.resource_scan),
            "scne_inventory": str(args.scne_inventory),
            "scne_inventory_sha256": sha256_file(args.scne_inventory),
            "texture_occurrences": str(args.textures),
            "texture_occurrences_sha256": sha256_file(args.textures),
            "material_mappings": str(args.materials),
            "material_mappings_sha256": sha256_file(args.materials),
        },
        "asset_root": logical_root,
        "format": {
            "container": "PNG",
            "signature": PNG_SIGNATURE.hex(),
            "bit_depth": 8,
            "color_type": 6,
            "channels": "RGBA",
            "interlace": 0,
            "row_filter": 0,
            "idat_zlib_level": 9,
            "deduplication_key": "SHA-256 of decoded width*height*4 RGBA bytes",
            "path_template": "by_rgba_sha256/{sha256[0:2]}/{sha256}.png",
        },
        "evidence": {
            "material_texture_pointer": "SCNE material record +0x30",
            "texture_descriptor_stride": 32,
            "xbox_format": "P8 (0x0B)",
            "palette_storage": "BGRA8 converted to RGBA8",
            "pixel_layout": "Xbox 2D swizzle decoded by verified nfl_txtr.unswizzle_2d",
            "semantic_limit": "mapping proves material occurrence -> descriptor, not shader slot or baseColor use",
        },
        "summary": summary,
        "pngs": png_rows,
        "occurrences": decoded_occurrence_rows,
        "materials": enriched_material_rows,
        "portme": [
            "PORTME: recover shader programs, texture-stage routing, UV set selection, sampler addressing/filtering, and blend state before assigning any PNG as glTF baseColor or another material semantic.",
            "PORTME: recover mip-tail offsets and runtime mip selection; this catalog intentionally exports the instruction-verified base level only.",
            "PORTME: implement a reverse PNG-to-P8 palette quantizer, Xbox swizzler, descriptor allocator, material-pointer relocation, and archive writer before claiming round-trip mod injection.",
        ],
    }

    write_tsv(args.occurrences_tsv, OCCURRENCE_FIELDS, decoded_occurrence_rows)
    write_tsv(args.materials_tsv, MATERIAL_FIELDS, enriched_material_rows)
    write_tsv(args.pngs_tsv, PNG_FIELDS, png_rows)
    args.manifest_json.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_json.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    check_disk(args.asset_dir, minimum_free, "after export")
    print(
        "NFL_SCNE_EMBEDDED_TEXTURE_PNG_EXPORT_PASS "
        f"occurrences={len(decoded_occurrence_rows)} unique_png={len(png_rows)} "
        f"materials={len(enriched_material_rows)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CatalogError, OSError, TxtrError, struct.error, ValueError) as exc:
        raise SystemExit(f"error: {exc}") from exc
