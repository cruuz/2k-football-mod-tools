#!/usr/bin/env python3
"""Build a stadium-only, user-cache-private glTF and PNG product corpus.

The worker consumes exactly two retail-derived inputs supplied by the product:
archive pack 0 and the resource-chunk inventory.  It first decodes only the
SCNE object header/name needed to select ``stadium`` scenes, then applies the
existing strict SCNE parser, static glTF exporter, and embedded P8 decoder only
to those selected scenes.

Every completed scene has an atomic sidecar checkpoint.  Re-running the worker
validates and reuses those checkpoints, so an interrupted multi-minute build
does not restart from zero.  All paths are confined beneath the caller's
SourceCache and all output is mode 0600/0700 private data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
from typing import Any, Iterable
from uuid import uuid4

from nfl_outer import FormatError, parse_archive, read_entry_range
from nfl_scene_probe import ProbeError, ResourceRecord, decode_resource, parse_inventory
from nfl_scne_embedded_texture_png import parse_png_rgba
from nfl_scne_inventory import (
    DESCRIPTOR_SIZE,
    ScneError,
    parse_scene,
    pointer_name,
    resolve_relative,
    texture_info,
)
from nfl_static_gltf import PORTME as GLTF_PORTME, export_scene, safe_name
from nfl_txtr import TxtrError, encode_rgba_png, texture_to_rgba


SELECTION_SCHEMA = "2k5_mod_studio_stadium_selection/v1"
SCENE_RECORD_SCHEMA = "2k5_mod_studio_stadium_scene_record/v1"
RESULT_SCHEMA = "2k5_mod_studio_stadium_cache_result/v1"
GLTF_MANIFEST_SCHEMA = "nfl2k5_static_gltf_manifest/v2"
TEXTURE_MANIFEST_SCHEMA = "nfl2k5_scne_embedded_texture_png/v1"
ESTIMATED_PRIVATE_BYTES = 750 * 1024**2
COPY_BLOCK = 1024 * 1024
MAX_JSON_BYTES = 128 * 1024**2
EXPECTED_PACK_NAMES = "0123456789ABCDEF"


TEXTURE_PORTME = [
    "PORTME: shader stage, UV set, sampler addressing/filtering, and blend "
    "semantics remain unproved.",
    "PORTME: only the instruction-verified embedded P8 base level is exported.",
    "PORTME: general PNG-to-SCNE texture serialization remains unavailable.",
]


class StadiumWorkerError(ValueError):
    """The bounded private derivation cannot safely continue."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(COPY_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def _mkdir_private(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise StadiumWorkerError(f"private output directory is unsafe: {path}")
    os.chmod(path, 0o700)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_bytes(path: Path, payload: bytes) -> None:
    _mkdir_private(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _atomic_json(path: Path, value: object) -> None:
    _atomic_bytes(path, _canonical_json(value))


def _regular_file(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise StadiumWorkerError(f"{label} is missing: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise StadiumWorkerError(f"{label} must be a regular, non-link file: {path}")
    return path.resolve(strict=True)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    resolved = _regular_file(path, label)
    if resolved.stat().st_size > MAX_JSON_BYTES:
        raise StadiumWorkerError(f"{label} is unexpectedly large")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StadiumWorkerError(f"could not read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise StadiumWorkerError(f"{label} is not a JSON object")
    return value


def _confined(root: Path, path: Path, label: str) -> Path:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise StadiumWorkerError(f"{label} escapes the private SourceCache") from exc
    return resolved


def _safe_relative(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise StadiumWorkerError(f"{label} path is missing")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise StadiumWorkerError(f"{label} path is unsafe")
    path = root / relative
    return _confined(root, _regular_file(path, label), label)


def _validate_archive_pack_set(cache_root: Path, pack0: Path) -> tuple[Path, ...]:
    """Resolve the recognized retail pack set without following cache links."""

    if pack0.name != "0":
        raise StadiumWorkerError("archive pack 0 must use its canonical filename")
    packs: list[Path] = []
    for name in EXPECTED_PACK_NAMES:
        path = _regular_file(pack0.parent / name, f"archive pack {name}")
        packs.append(_confined(cache_root, path, f"archive pack {name}"))
    return tuple(packs)


def _emit(stage: str, completed: int, total: int) -> None:
    print(
        "STADIUM_CACHE_PROGRESS "
        + json.dumps(
            {"stage": stage, "completed": completed, "total": total},
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )


def _tree_size(root: Path, *, exclude_result: bool = True) -> int:
    total = 0
    for path in root.rglob("*"):
        if exclude_result and path == root / "result.json":
            continue
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode):
            total += info.st_size
    return total


def _source_identity(
    scene_index: int, resource: ResourceRecord, digest: str
) -> dict[str, Any]:
    return {
        "scene_index": scene_index,
        "outer_index": resource.outer_index,
        "outer_id": resource.outer_id,
        "chunk_index": resource.chunk_index,
        "chunk_offset": resource.chunk_offset,
        "stored_size": resource.stored_size,
        "system_bytes": resource.word_08,
        "video_bytes": resource.word_0c,
        "decoded_sha256": digest,
        "scene_name": "stadium",
    }


def _decode(archive: Any, resource: ResourceRecord) -> tuple[bytes, dict[str, Any]]:
    entry = archive.entries[resource.outer_index]
    span = read_entry_range(
        archive,
        entry,
        resource.chunk_offset,
        0x20 + resource.stored_size,
    )
    output, detail = decode_resource(span, resource)
    return output, detail


def _scene_name(output: bytes, resource: ResourceRecord, scene_index: int) -> str:
    if len(output) != resource.word_08 + resource.word_0c \
            or output[0x0C:0x10] != b"SCNE":
        raise StadiumWorkerError(
            f"SCNE {scene_index} decoded wrapper/object marker is invalid"
        )
    system_size = resource.word_08
    _header_target, header_name = pointer_name(
        output, 0x10, system_size, f"scene {scene_index} header name"
    )
    descriptor = resolve_relative(
        output, 0x14, system_size, f"scene {scene_index} descriptor"
    )
    if descriptor is None or descriptor + DESCRIPTOR_SIZE > system_size:
        raise StadiumWorkerError(f"SCNE {scene_index} has no bounded descriptor")
    _descriptor_target, descriptor_name = pointer_name(
        output, descriptor, system_size, f"scene {scene_index} descriptor name"
    )
    if not header_name or header_name != descriptor_name:
        raise StadiumWorkerError(
            f"SCNE {scene_index} header/descriptor scene names disagree"
        )
    return header_name


def _load_or_discover_selection(
    *,
    output_root: Path,
    archive: Any,
    scne_resources: list[ResourceRecord],
    inventory_sha256: str,
    pack0_size: int,
    source_sha256: str,
    expected_scenes: int,
) -> dict[str, Any]:
    path = output_root / "selection.json"
    fingerprint = {
        "inventory_sha256": inventory_sha256,
        "pack0_size": pack0_size,
        "resource_scene_count": len(scne_resources),
        "source_sha256": source_sha256,
    }
    if path.exists():
        value = _read_json(path, "stadium selection checkpoint")
        rows = value.get("stadium_scenes")
        if (
            value.get("schema") != SELECTION_SCHEMA
            or value.get("source") != fingerprint
            or not isinstance(rows, list)
            or len(rows) != expected_scenes
        ):
            raise StadiumWorkerError(
                "private stadium selection checkpoint is incompatible; remove only "
                f"the private staging directory {output_root} and retry"
            )
        return value

    selected: list[dict[str, Any]] = []
    total = len(scne_resources)
    for scene_index, resource in enumerate(scne_resources):
        decoded, detail = _decode(archive, resource)
        name = _scene_name(decoded, resource, scene_index)
        if name == "stadium":
            selected.append(
                _source_identity(scene_index, resource, str(detail["decoded_sha256"]))
            )
        if (scene_index + 1) % 50 == 0 or scene_index + 1 == total:
            _emit("Finding stadium scenes in your game", scene_index + 1, total)
    if len(selected) != expected_scenes:
        raise StadiumWorkerError(
            f"bounded name scan found {len(selected)} stadium scenes; "
            f"{expected_scenes} were expected for the recognized game"
        )
    value = {
        "schema": SELECTION_SCHEMA,
        "source": fingerprint,
        "selection_rule": (
            "Decode each SCNE object header and descriptor name; fully parse only "
            "records whose exact UTF-16LE name is stadium."
        ),
        "stadium_scenes": selected,
    }
    _atomic_json(path, value)
    return value


def _ensure_png(
    texture_root: Path,
    rgba_sha256: str,
    width: int,
    height: int,
    rgba: bytes,
) -> tuple[str, str, int]:
    if _sha256_bytes(rgba) != rgba_sha256:
        raise StadiumWorkerError("SCNE texture RGBA differs from its strict parser hash")
    relative = Path("by_rgba_sha256") / rgba_sha256[:2] / f"{rgba_sha256}.png"
    target = texture_root / relative
    payload = encode_rgba_png(width, height, rgba)
    png_hash = _sha256_bytes(payload)
    if target.exists():
        resolved = _regular_file(target, "resumable stadium texture PNG")
        if _sha256_file(resolved) != png_hash:
            raise StadiumWorkerError(
                f"resumable private PNG changed unexpectedly: {relative.as_posix()}"
            )
    else:
        _atomic_bytes(target, payload)
    png_width, png_height, png_rgba = parse_png_rgba(target)
    if (png_width, png_height) != (width, height) \
            or _sha256_bytes(png_rgba) != rgba_sha256:
        raise StadiumWorkerError("generated stadium PNG failed its independent decode check")
    return relative.as_posix(), png_hash, len(payload)


def _record_path(output_root: Path, source: dict[str, Any]) -> Path:
    return output_root / "scene_records" / (
        f"{int(source['scene_index']):04d}_"
        f"{int(source['outer_index']):04d}_"
        f"{int(source['chunk_index']):04d}.json"
    )


def _validate_completed_record(
    output_root: Path,
    source: dict[str, Any],
    hash_cache: dict[Path, str],
) -> dict[str, Any] | None:
    path = _record_path(output_root, source)
    if not path.exists():
        return None
    if path.is_symlink():
        raise StadiumWorkerError("stadium scene checkpoint cannot be a symlink")
    try:
        record = _read_json(path, "stadium scene checkpoint")
    except StadiumWorkerError:
        return None
    if record.get("schema") != SCENE_RECORD_SCHEMA or record.get("source") != source:
        return None
    export = record.get("export")
    occurrences = record.get("occurrences")
    materials = record.get("materials")
    pngs = record.get("pngs")
    if not isinstance(export, dict) or not isinstance(occurrences, list) \
            or not isinstance(materials, list) or not isinstance(pngs, list):
        return None
    if export.get("status") == "exported":
        try:
            gltf = _safe_relative(
                output_root / "models", export.get("gltf"), "resumable stadium glTF"
            )
            binary = _safe_relative(
                output_root / "models", export.get("bin"), "resumable stadium binary"
            )
        except StadiumWorkerError:
            return None
        for item, expected in (
            (gltf, export.get("gltf_sha256")),
            (binary, export.get("bin_sha256")),
        ):
            digest = hash_cache.setdefault(item, _sha256_file(item))
            if digest != expected:
                return None
    elif export.get("status") != "withheld":
        return None
    for png in pngs:
        if not isinstance(png, dict):
            return None
        try:
            path = _safe_relative(
                output_root / "textures", png.get("png_path"), "resumable stadium PNG"
            )
        except StadiumWorkerError:
            return None
        digest = hash_cache.setdefault(path, _sha256_file(path))
        if digest != png.get("png_sha256"):
            return None
    return record


def _process_scene(
    *,
    output_root: Path,
    archive: Any,
    resource: ResourceRecord,
    source: dict[str, Any],
    conversion_cache: dict[tuple[object, ...], dict[str, str]],
) -> dict[str, Any]:
    decoded, detail = _decode(archive, resource)
    if detail.get("decoded_sha256") != source["decoded_sha256"]:
        raise StadiumWorkerError(
            f"stadium SCNE {source['outer_index']}/{source['chunk_index']} changed "
            "since the bounded name scan"
        )
    scene, _names, mappings, _sample = parse_scene(
        int(source["scene_index"]), resource, decoded, conversion_cache
    )
    if scene.get("name") != "stadium":
        raise StadiumWorkerError("selected stadium SCNE changed its decoded name")

    models = output_root / "models"
    textures = output_root / "textures"
    _mkdir_private(models)
    _mkdir_private(textures)
    base = (
        f"{resource.outer_index:04d}_{resource.chunk_index:04d}_"
        f"{safe_name(str(scene['name']))}"
    )
    gltf_name = f"{base}.gltf"
    bin_name = f"{base}.bin"
    document, binary, detail_row = export_scene(
        decoded, scene, {"decoded_sha256": source["decoded_sha256"]}, bin_name
    )
    common: dict[str, Any] = {
        "scene_index": int(source["scene_index"]),
        "outer_index": resource.outer_index,
        "chunk_index": resource.chunk_index,
        "scene_name": "stadium",
        "decoded_sha256": source["decoded_sha256"],
        "source_shape_count": len(scene["shapes"]),
        "eligible_shape_indices": detail_row["eligible_shape_indices"],
        "withheld_shapes": detail_row["withheld_shapes"],
    }
    if document is None:
        export: dict[str, Any] = {
            **common,
            "status": "withheld",
            "portme": (
                "PORTME: scene has no shape with an executable-proved nonempty "
                "register-0 position"
            ),
        }
    else:
        gltf_payload = _canonical_json(document)
        _atomic_bytes(models / bin_name, binary)
        _atomic_bytes(models / gltf_name, gltf_payload)
        export = {
            **common,
            "status": "exported",
            "gltf": gltf_name,
            "bin": bin_name,
            "gltf_sha256": _sha256_bytes(gltf_payload),
            "bin_sha256": _sha256_bytes(binary),
            "binary_bytes": len(binary),
            "mesh_count": int(detail_row["mesh_count"]),
            "primitive_count": int(detail_row["primitive_count"]),
            "vertex_count": int(detail_row["vertex_count"]),
            "raw_index_count": int(detail_row["raw_index_count"]),
            "gltf_index_count": int(detail_row["gltf_index_count"]),
            "float3_shape_count": int(detail_row.get("float3_shape_count", 0)),
            "normshort3_shape_count": int(
                detail_row.get("normshort3_shape_count", 0)
            ),
        }

    occurrences: list[dict[str, Any]] = []
    pngs: dict[str, dict[str, Any]] = {}
    for texture in scene["embedded_textures"]:
        index = int(texture["index"])
        info = texture_info(
            decoded, int(texture["descriptor_offset"]), "stadium", index
        )
        rgba = texture_to_rgba(decoded, resource.as_chunk(), info)
        rgba_hash = _sha256_bytes(rgba)
        if texture.get("conversion_status") != "base_level_supported" \
                or texture.get("rgba_sha256") != rgba_hash:
            raise StadiumWorkerError(
                f"stadium texture {index} is outside the proved P8 base-level decoder"
            )
        png_path, png_hash, png_size = _ensure_png(
            textures, rgba_hash, info.width, info.height, rgba
        )
        mapped_names = tuple(str(name) for name in texture["mapped_material_names"])
        occurrence = {
            "scene_index": int(source["scene_index"]),
            "outer_index": resource.outer_index,
            "outer_id": resource.outer_id,
            "chunk_index": resource.chunk_index,
            "chunk_offset": resource.chunk_offset,
            "scene_name": "stadium",
            "texture_index": index,
            "descriptor_offset": int(texture["descriptor_offset"]),
            "unknown0": texture["unknown0"],
            "pixel_offset": info.pixel_offset,
            "palette_offset": info.palette_offset,
            "packed_format": info.packed_format,
            "packed_size": info.packed_size,
            "descriptor_flags": info.descriptor_flags,
            "extra_word_18": texture["extra_word_18"],
            "extra_word_1c": texture["extra_word_1c"],
            "dimensions": info.dimensions,
            "format_code": info.format_code,
            "format_name": info.format_name,
            "mip_levels": info.mip_levels,
            "width": info.width,
            "height": info.height,
            "depth": info.depth,
            "conversion_status": "base_level_supported",
            "rgba_sha256": rgba_hash,
            "png_path": png_path,
            "png_sha256": png_hash,
            "png_size": png_size,
            "mapped_material_count": len(mapped_names),
            "mapped_material_names": "|".join(mapped_names),
        }
        occurrences.append(occurrence)
        png = pngs.get(rgba_hash)
        if png is None:
            png = {
                "rgba_sha256": rgba_hash,
                "width": info.width,
                "height": info.height,
                "png_path": png_path,
                "png_sha256": png_hash,
                "png_size": png_size,
                "occurrence_count": 0,
                "mapped_material_count": 0,
                "representative_scene_index": int(source["scene_index"]),
                "representative_outer_index": resource.outer_index,
                "representative_chunk_index": resource.chunk_index,
                "representative_texture_index": index,
                "representative_descriptor_offset": info.descriptor_offset,
            }
            pngs[rgba_hash] = png
        elif (
            png["width"], png["height"], png["png_sha256"], png["png_path"]
        ) != (info.width, info.height, png_hash, png_path):
            raise StadiumWorkerError("deduplicated stadium PNG metadata disagrees")
        png["occurrence_count"] += 1
        png["mapped_material_count"] += len(mapped_names)

    occurrence_by_index = {
        int(row["texture_index"]): row for row in occurrences
    }
    materials: list[dict[str, Any]] = []
    for mapping in mappings:
        material_name = mapping.get("material_name")
        if not isinstance(material_name, str) or not material_name:
            raise StadiumWorkerError(
                f"stadium material {mapping.get('material_index')} has no safe name"
            )
        texture_index = mapping.get("texture_index")
        base_material: dict[str, Any] = {
            "scene_index": int(source["scene_index"]),
            "outer_index": resource.outer_index,
            "outer_id": resource.outer_id,
            "chunk_index": resource.chunk_index,
            "chunk_offset": resource.chunk_offset,
            "scene_name": "stadium",
            "material_index": int(mapping["material_index"]),
            "material_name": material_name,
            "material_offset": int(mapping["material_offset"]),
            "texture_pointer_field": int(mapping["texture_pointer_field"]),
            "texture_target": mapping["texture_target"],
            "texture_index": texture_index,
        }
        if texture_index is None:
            base_material.update(
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
        else:
            occurrence = occurrence_by_index.get(int(texture_index))
            if occurrence is None:
                raise StadiumWorkerError("stadium material maps to a missing texture")
            base_material.update(
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
        materials.append(base_material)

    record = {
        "schema": SCENE_RECORD_SCHEMA,
        "source": source,
        "export": export,
        "occurrences": occurrences,
        "materials": materials,
        "pngs": [pngs[key] for key in sorted(pngs)],
    }
    _atomic_json(_record_path(output_root, source), record)
    return record


def _aggregate_pngs(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    stable_fields = (
        "width", "height", "png_path", "png_sha256", "png_size"
    )
    for record in records:
        for raw in record["pngs"]:
            digest = str(raw["rgba_sha256"])
            current = combined.get(digest)
            if current is None:
                combined[digest] = dict(raw)
                continue
            if any(current[field] != raw[field] for field in stable_fields):
                raise StadiumWorkerError(
                    f"cross-scene PNG metadata changed for RGBA {digest}"
                )
            current["occurrence_count"] += int(raw["occurrence_count"])
            current["mapped_material_count"] += int(raw["mapped_material_count"])
    return [combined[key] for key in sorted(combined)]


def finalize_records(
    *,
    output_root: Path,
    records: list[dict[str, Any]],
    source_sha256: str,
    inventory_sha256: str,
    pack0_relative: str,
    inventory_relative: str,
    resumed_scene_count: int,
) -> dict[str, Any]:
    """Aggregate validated per-scene checkpoints into product manifests."""

    exports = [record["export"] for record in records]
    occurrences = [row for record in records for row in record["occurrences"]]
    materials = [row for record in records for row in record["materials"]]
    pngs = _aggregate_pngs(records)
    exports.sort(key=lambda row: (
        int(row["scene_index"]), int(row["outer_index"]), int(row["chunk_index"])
    ))
    occurrences.sort(key=lambda row: (
        int(row["scene_index"]), int(row["texture_index"])
    ))
    materials.sort(key=lambda row: (
        int(row["scene_index"]), int(row["material_index"])
    ))
    exported = [row for row in exports if row.get("status") == "exported"]
    withheld = [row for row in exports if row.get("status") == "withheld"]
    gltf_summary: dict[str, Any] = {
        "scene_count": len(exports),
        "exported_scene_count": len(exported),
        "withheld_scene_count": len(withheld),
        "source_shape_count": sum(int(row["source_shape_count"]) for row in exports),
        "eligible_shape_count": sum(
            len(row["eligible_shape_indices"]) for row in exports
        ),
        "withheld_shape_count": sum(len(row["withheld_shapes"]) for row in exports),
        "mesh_count": sum(int(row.get("mesh_count", 0)) for row in exports),
        "primitive_count": sum(
            int(row.get("primitive_count", 0)) for row in exports
        ),
        "vertex_count": sum(int(row.get("vertex_count", 0)) for row in exports),
        "raw_index_count": sum(
            int(row.get("raw_index_count", 0)) for row in exports
        ),
        "gltf_index_count": sum(
            int(row.get("gltf_index_count", 0)) for row in exports
        ),
        "binary_bytes": sum(int(row.get("binary_bytes", 0)) for row in exports),
        "float3_shape_count": sum(
            int(row.get("float3_shape_count", 0)) for row in exports
        ),
        "normshort3_shape_count": sum(
            int(row.get("normshort3_shape_count", 0)) for row in exports
        ),
        "all_exported_positions_executable_proved": True,
        "all_exported_positions_float3_or_normshort3": True,
        "all_exported_topology_bounded": True,
        "stadium_only": True,
    }
    gltf_manifest = {
        "schema": GLTF_MANIFEST_SCHEMA,
        "source_index": pack0_relative,
        "source_resource_scan": inventory_relative,
        "source_hashes": {"resource_scan_sha256": inventory_sha256},
        "selection": {
            "scene_name": "stadium",
            "source": "decoded SCNE header and descriptor names",
        },
        "summary": gltf_summary,
        "portme": GLTF_PORTME,
        "exports": exports,
    }
    texture_summary = {
        "scene_count": len(exports),
        "represented_scene_count": len(records),
        "texture_occurrence_count": len(occurrences),
        "p8_occurrence_count": len(occurrences),
        "unique_rgba_count": len(pngs),
        "png_count": len(pngs),
        "deduplicated_occurrence_count": len(occurrences) - len(pngs),
        "material_row_count": len(materials),
        "mapped_material_count": sum(
            row["texture_index"] is not None for row in materials
        ),
        "unmapped_material_count": sum(
            row["texture_index"] is None for row in materials
        ),
        "unreferenced_texture_occurrence_count": sum(
            int(row["mapped_material_count"]) == 0 for row in occurrences
        ),
        "total_png_bytes": sum(int(row["png_size"]) for row in pngs),
        "all_source_descriptors_replayed": True,
        "all_source_rgba_hashes_match": True,
        "all_unique_png_ihdrs_match": True,
        "all_unique_png_rgba_hashes_match": True,
        "all_material_occurrence_links_preserved": True,
        "stadium_only": True,
    }
    texture_manifest = {
        "schema": TEXTURE_MANIFEST_SCHEMA,
        "sources": {
            "index": pack0_relative,
            "resource_scan": inventory_relative,
            "resource_scan_sha256": inventory_sha256,
        },
        "asset_root": "by_rgba_sha256",
        "format": {
            "container": "PNG",
            "channels": "RGBA",
            "deduplication_key": "SHA-256 of decoded RGBA bytes",
            "path_template": "by_rgba_sha256/{sha256[0:2]}/{sha256}.png",
        },
        "evidence": {
            "material_texture_pointer": "SCNE material record +0x30",
            "texture_descriptor_stride": 32,
            "xbox_format": "P8 (0x0B)",
            "selection": "exact decoded scene name stadium",
        },
        "summary": texture_summary,
        "pngs": pngs,
        "occurrences": occurrences,
        "materials": materials,
        "portme": TEXTURE_PORTME,
    }
    models_manifest = output_root / "models" / "manifest.json"
    textures_manifest = output_root / "textures" / "manifest.json"
    _atomic_json(models_manifest, gltf_manifest)
    _atomic_json(textures_manifest, texture_manifest)
    result_summary = {
        "stadium_scene_count": len(exports),
        "exported_scene_count": len(exported),
        "withheld_scene_count": len(withheld),
        "texture_occurrence_count": len(occurrences),
        "material_row_count": len(materials),
        "unique_png_count": len(pngs),
    }
    result = {
        "schema": RESULT_SCHEMA,
        "source_sha256": source_sha256,
        "private_user_cache": True,
        "shareable": False,
        "source_inputs": {
            "pack0": pack0_relative,
            "archive_pack_names": list(EXPECTED_PACK_NAMES),
            "resource_inventory": inventory_relative,
            "resource_inventory_sha256": inventory_sha256,
        },
        "paths": {
            "gltf_manifest": "models/manifest.json",
            "texture_manifest": "textures/manifest.json",
            "texture_root": "textures",
        },
        "hashes": {
            "gltf_manifest_sha256": _sha256_file(models_manifest),
            "texture_manifest_sha256": _sha256_file(textures_manifest),
        },
        "summary": result_summary,
        "estimated_private_bytes": ESTIMATED_PRIVATE_BYTES,
        "derived_payload_bytes": _tree_size(output_root),
        "resumed_scene_count": resumed_scene_count,
    }
    _atomic_json(output_root / "result.json", result)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--pack0", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--expected-scenes", type=int, required=True)
    parser.add_argument("--minimum-free-bytes", type=int, default=1024**3)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if len(args.source_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in args.source_sha256
    ):
        raise StadiumWorkerError("source SHA-256 is invalid")
    if args.expected_scenes < 1 or args.minimum_free_bytes < 0:
        raise StadiumWorkerError("scene count/free-space bounds are invalid")
    cache_root = args.cache_root.resolve(strict=True)
    root_info = cache_root.lstat()
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        raise StadiumWorkerError("SourceCache root is not a private directory")
    pack0 = _confined(cache_root, _regular_file(args.pack0, "archive pack 0"), "pack 0")
    inventory = _confined(
        cache_root,
        _regular_file(args.inventory, "resource inventory"),
        "resource inventory",
    )
    _validate_archive_pack_set(cache_root, pack0)
    output_root = args.output
    _mkdir_private(output_root)
    output_root = _confined(cache_root, output_root, "private stadium output")
    existing_bytes = _tree_size(output_root, exclude_result=False)
    needed = max(0, ESTIMATED_PRIVATE_BYTES - existing_bytes)
    free = shutil.disk_usage(output_root).free
    if free < needed + args.minimum_free_bytes:
        raise StadiumWorkerError(
            f"private Stadium Studio cache needs about {needed:,} additional bytes "
            f"plus a {args.minimum_free_bytes:,}-byte reserve; only {free:,} are free"
        )

    inventory_sha = _sha256_file(inventory)
    resource_document, resources = parse_inventory(inventory)
    scne_resources = [resource for resource in resources if resource.kind == "SCNE"]
    declared = int(resource_document["summary"]["resource_kind_counts"]["SCNE"])
    if len(scne_resources) != declared:
        raise StadiumWorkerError(
            f"resource inventory contains {len(scne_resources)} SCNE chunks but "
            f"declares {declared}"
        )
    archive = parse_archive(pack0)
    selection = _load_or_discover_selection(
        output_root=output_root,
        archive=archive,
        scne_resources=scne_resources,
        inventory_sha256=inventory_sha,
        pack0_size=pack0.stat().st_size,
        source_sha256=args.source_sha256,
        expected_scenes=args.expected_scenes,
    )
    resource_by_key = {
        (resource.outer_index, resource.chunk_index): resource
        for resource in scne_resources
    }
    records: list[dict[str, Any]] = []
    conversion_cache: dict[tuple[object, ...], dict[str, str]] = {}
    hash_cache: dict[Path, str] = {}
    resumed = 0
    selected_rows = selection["stadium_scenes"]
    for index, source in enumerate(selected_rows, 1):
        assert isinstance(source, dict)
        key = (int(source["outer_index"]), int(source["chunk_index"]))
        resource = resource_by_key.get(key)
        if resource is None:
            raise StadiumWorkerError(f"selected stadium resource {key} disappeared")
        record = _validate_completed_record(output_root, source, hash_cache)
        if record is None:
            record = _process_scene(
                output_root=output_root,
                archive=archive,
                resource=resource,
                source=source,
                conversion_cache=conversion_cache,
            )
        else:
            resumed += 1
        records.append(record)
        _emit("Building private Stadium Studio scenes", index, len(selected_rows))
    if len(records) != args.expected_scenes:
        raise StadiumWorkerError("not every selected stadium scene has a checkpoint")

    pack0_relative = pack0.relative_to(cache_root).as_posix()
    inventory_relative = inventory.relative_to(cache_root).as_posix()
    result = finalize_records(
        output_root=output_root,
        records=records,
        source_sha256=args.source_sha256,
        inventory_sha256=inventory_sha,
        pack0_relative=pack0_relative,
        inventory_relative=inventory_relative,
        resumed_scene_count=resumed,
    )
    _emit("Private Stadium Studio manifests ready", 1, 1)
    print(
        "STADIUM_CACHE_COMPLETE "
        + json.dumps(
            {
                "derived_payload_bytes": result["derived_payload_bytes"],
                "exported_scenes": result["summary"]["exported_scene_count"],
                "stadium_scenes": result["summary"]["stadium_scene_count"],
                "texture_occurrences": result["summary"]["texture_occurrence_count"],
                "unique_pngs": result["summary"]["unique_png_count"],
                "resumed_scenes": resumed,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        FormatError,
        OSError,
        ProbeError,
        ScneError,
        StadiumWorkerError,
        TxtrError,
        ValueError,
        struct.error,
    ) as exc:
        print(
            "STADIUM_CACHE_FINDINGS "
            + json.dumps(
                {
                    "code": "bounded_private_derivation_failed",
                    "message": str(exc).strip() or exc.__class__.__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
