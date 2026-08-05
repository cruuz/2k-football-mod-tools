#!/usr/bin/env python3
"""Independently verify a published APF whole-shell crest catalog.

The verifier does not import either crest writer.  It parses pristine and
built archives with the generic outer/IFF readers, independently decodes all
118 ``uniform_logo`` package pairs, and reimplements the retail physical Y/Z
decal-to-shell-atlas nearest map.  The selected package must contain the exact
caller-supplied atlas in both layers; every other package layer must equal the
independently migrated retail source layer.

The logo cache is checked separately.  All 234 nonselected cache sub-block
pairs must remain byte-exact even if repacking moved their offsets.  The two
selected cache layers must decode identically and remain semantic rather than
being replaced by the shell atlas; an optional semantic PNG makes that selected
cache comparison exact too.

This is a headless file-level verifier.  It makes no runtime, gameplay,
original-hardware, or visual-quality claim.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence
import zlib

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
for search_root in (ROOT, ROOT / "tools"):
    if str(search_root) not in sys.path:
        sys.path.insert(0, str(search_root))

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402


SCHEMA = "apf2k8_helmet_shell_catalog_verify/v1"
CLAIM = "independent_headless_file_level_catalog_verification"
CATALOG_COUNT = 118
WIDTH = 512
HEIGHT = 512
RGBA_LENGTH = WIDTH * HEIGHT * 4
BASE_LENGTH = 0x80000
MIP_LENGTH = 0x2C000
VRAM_LENGTH = BASE_LENGTH + MIP_LENGTH
DRAM_LENGTH = 0xE0
MAX_DECOMPRESSED = 128 * 1024 * 1024

HELMET_OUTER_INDEX = 1310
HELMET_NAME = "helmet_00"
HELMET_SYSTEM_LENGTH = 0xD5680
STRIDE = 32

CACHE_DIRECTORY_INDEX = 171
CACHE_PAYLOAD_INDEX = 213
CACHE_DIRECTORY_SIZE = 0xA000
CACHE_PAYLOAD_SIZE = 0x9E0800
CACHE_HEADER_SIZE = 0x2924
CACHE_FILE_COUNT = 236
CACHE_DRAM_STRIDE = 0xE0
CACHE_VRAM_STRIDE = 0xAC000
CACHE_AUX_DRAM_STORED_LENGTH = 0x71
CACHE_MAGIC = 0xF0985030
CACHE_TXTR_HASH = 0x5C369069
CACHE_NAME = "uniform_logocache.cdf"


class VerifyError(ValueError):
    """The source, output, or expected artifact left the verifier contract."""


@dataclass(frozen=True)
class LodSpec:
    name: str
    index_offset: int
    index_count: int
    shell_index_start: int
    shell_index_count: int
    carrier_index_start: int
    carrier_index_count: int
    stream_start: int
    vertex_count: int
    center: tuple[float, float, float]
    scale: tuple[float, float, float]
    shell_triangles: int
    carrier_triangles: int


LODS = (
    LodSpec(
        "helmet_hi", 0x9C30, 9773, 2623, 4800, 7423, 1046,
        0xEA1C, 3856,
        (0.0, 4.927330017089844, 1.7508296966552734),
        (13.967263221740723,) * 3, 2464, 536,
    ),
    LodSpec(
        "helmet_lo", 0xCCCF0, 1552, 359, 659, 1018, 231,
        0xCDA9C, 799,
        (0.0, 2.8593978881835938, 2.8941473960876465),
        (16.119155883789062,) * 3, 432, 184,
    ),
)


@dataclass(frozen=True)
class DecodedLayer:
    name: str
    rgba: bytes
    mip_length: int
    dram: bytes


@dataclass(frozen=True)
class DecodedPackage:
    asset_index: int
    outer_index: int
    raw_sha256: str
    layers: Mapping[str, DecodedLayer]


@dataclass(frozen=True)
class CacheEntry:
    name: str
    catalog: int
    level: int
    file_id: int
    aggregate_slot: int
    stream_a: int
    length_a: int
    stream_b: int
    length_b: int


@dataclass(frozen=True)
class CacheDirectory:
    entries: tuple[CacheEntry, ...]
    total_stream_length: int


def require(value: object, message: str) -> None:
    if not value:
        raise VerifyError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def crc32_name(value: str) -> int:
    """Return the outer archive's uppercase filename identity."""

    return zlib.crc32(value.upper().encode("ascii")) & 0xFFFFFFFF


def crc32_inner_name(value: str) -> int:
    """Return an internal IFF footer filename's case-sensitive identity."""

    return zlib.crc32(value.encode("ascii")) & 0xFFFFFFFF


def resolve_catalog(archive: apf_outer.Archive) -> dict[int, int]:
    """Resolve all uniform-logo entries only from their on-disc CRC identities."""

    by_id: dict[int, list[int]] = {}
    for entry in archive.entries:
        by_id.setdefault(entry.name_id & 0xFFFFFFFF, []).append(entry.table_index)
    result: dict[int, int] = {}
    for asset in range(CATALOG_COUNT):
        name = f"uniform_logo_{asset:02d}.iff"
        matches = by_id.get(crc32_name(name), [])
        require(len(matches) == 1, f"source-resolved crest {name} has {len(matches)} owners")
        result[asset] = matches[0]
    require(len(set(result.values())) == CATALOG_COUNT,
            "crest catalog outer ownership is not one-to-one")
    return result


def _strict_descriptor(metadata: Mapping[str, object]) -> None:
    expected = {
        "width": WIDTH, "height": HEIGHT, "pitch_pixels": WIDTH,
        "format": 15, "endianness": 1, "dimension": 1,
        "tiled": True, "stacked": False,
        "vc_base_data_length": BASE_LENGTH, "vc_mip_data_length": MIP_LENGTH,
    }
    differences = {
        key: (metadata.get(key), wanted)
        for key, wanted in expected.items() if metadata.get(key) != wanted
    }
    require(not differences, f"crest TXTR descriptor differs: {differences}")
    require(list(metadata.get("swizzle_components", ())) == [2, 1, 0, 3],
            "crest TXTR swizzle differs")


def decode_4444(metadata: Mapping[str, object], base: bytes) -> bytes:
    """Decode tiled Xenos 4:4:4:4 without using the package writer."""

    _strict_descriptor(metadata)
    require(len(base) == BASE_LENGTH, "crest base allocation differs")
    linear = apf_inner._untile_2d(  # type: ignore[attr-defined]
        base, WIDTH, HEIGHT, WIDTH, 1, 1, 2,
    )
    linear = apf_inner._endian_swap(linear, 1)  # type: ignore[attr-defined]
    values = np.frombuffer(linear, dtype="<u2")
    require(values.size == WIDTH * HEIGHT, "crest base texel count differs")
    output = np.empty((values.size, 4), dtype=np.uint8)
    # Stored selector [2,1,0,3] converts raw BGRA nibbles to display RGBA.
    output[:, 0] = ((values >> 8) & 15) * 17
    output[:, 1] = ((values >> 4) & 15) * 17
    output[:, 2] = (values & 15) * 17
    output[:, 3] = ((values >> 12) & 15) * 17
    return output.tobytes()


def _decode_package(
    archive: apf_outer.Archive,
    reader: apf_inner.ArchiveReader,
    asset: int,
    outer_index: int,
) -> DecodedPackage:
    try:
        entry = archive.entries[outer_index]
        record = apf_inner.parse_iff(reader, entry)
    except (IndexError, apf_inner.FormatError) as exc:
        raise VerifyError(f"could not parse crest package {asset:02d}: {exc}") from exc
    require(
        len(entry.segments) == 1 and entry.segments[0].pack_name == archive.index_path.name,
        f"crest package {asset:02d} is not in one {archive.index_path.name} segment",
    )
    require(record.block_count == 2 and record.file_count == 2,
            f"crest package {asset:02d} block/file inventory differs")
    try:
        blocks = [
            apf_inner.decode_block(reader, record, number, 1 << 30)
            for number in range(record.block_count)
        ]
    except apf_inner.FormatError as exc:
        raise VerifyError(f"could not decode crest package {asset:02d}: {exc}") from exc
    found = {item.name: item for item in record.files}
    result: dict[str, DecodedLayer] = {}
    for name in ("logo_l0", "logo_l1"):
        item = found.get(name)
        require(item is not None and item.type_name == "TXTR",
                f"crest package {asset:02d} is missing {name}/TXTR")
        require(len(item.parts) == 2, f"crest package {asset:02d} {name} part count differs")
        dram_part = next((part for part in item.parts if part.length == DRAM_LENGTH), None)
        vram_part = next((part for part in item.parts if part.length == VRAM_LENGTH), None)
        require(dram_part is not None and vram_part is not None,
                f"crest package {asset:02d} {name} ownership differs")
        dram = blocks[dram_part.block_index][dram_part.offset : dram_part.offset + DRAM_LENGTH]
        vram = blocks[vram_part.block_index][vram_part.offset : vram_part.offset + VRAM_LENGTH]
        require(len(dram) == DRAM_LENGTH and len(vram) == VRAM_LENGTH,
                f"crest package {asset:02d} {name} is truncated")
        try:
            metadata = apf_inner.parse_txtr_metadata(dram)
        except apf_inner.FormatError as exc:
            raise VerifyError(f"crest package {asset:02d} {name} metadata failed: {exc}") from exc
        base = vram[:BASE_LENGTH]
        result[name] = DecodedLayer(
            name, decode_4444(metadata, base), len(vram) - BASE_LENGTH, dram,
        )
    raw = reader.read(entry, 0, entry.size)
    return DecodedPackage(asset, outer_index, sha256_bytes(raw), result)


def open_catalog(path: Path) -> tuple[apf_outer.Archive, dict[int, int]]:
    try:
        archive = apf_outer.parse_archive(path)
    except apf_outer.FormatError as exc:
        raise VerifyError(f"could not parse archive {path}: {exc}") from exc
    return archive, resolve_catalog(archive)


def _link_read_only_reference(source: Path, destination: Path) -> None:
    """Expose one existing pack in a private parse view without copying it."""

    try:
        os.symlink(source.resolve(strict=True), destination)
        return
    except (OSError, NotImplementedError, AttributeError) as symlink_error:
        try:
            os.link(source, destination)
            return
        except OSError as hardlink_error:
            raise VerifyError(
                f"could not create private read-only reference for {source.name}: "
                f"symlink={symlink_error}; hardlink={hardlink_error}"
            ) from hardlink_error


def open_standalone_output_catalog(
    output_path: Path,
    source_archive: apf_outer.Archive,
) -> tuple[apf_outer.Archive, dict[int, int]]:
    """Parse a standalone copied 0A beside temporary pristine sibling links.

    The shipped Team Logo artifact intentionally contains only a new ``0A``;
    the user boots it beside their unmodified ``0B/1A/1B`` packs.  Verification
    recreates exactly that view under a private temporary directory, then
    rebinds the parsed archive to the original read-only paths before cleanup.
    No sibling link is retained beside the standalone output.
    """

    require(output_path.name == source_archive.packs[0].name,
            "standalone output basename does not match the source index pack")
    with tempfile.TemporaryDirectory(prefix="apf-shell-catalog-view-") as directory:
        view = Path(directory)
        _link_read_only_reference(output_path, view / output_path.name)
        for pack in source_archive.packs[1:]:
            _link_read_only_reference(pack.path, view / pack.name)
        parsed, catalog = open_catalog(view / output_path.name)
        require(
            [(pack.name, pack.declared_size) for pack in parsed.packs]
            == [(pack.name, pack.declared_size) for pack in source_archive.packs],
            "standalone output changed the declared sibling-pack contract",
        )
        source_by_name = {pack.name: pack for pack in source_archive.packs}
        rebound_packs = tuple(
            replace(
                pack,
                path=(output_path if pack.ordinal == 0 else source_by_name[pack.name].path),
            )
            for pack in parsed.packs
        )
        rebound = replace(parsed, index_path=output_path, packs=rebound_packs)
    return rebound, catalog


def _snorm(value: int) -> float:
    return max(value / 32767.0, -1.0)


def _unit(values: Iterable[float]) -> np.ndarray:
    result = np.asarray(tuple(values), dtype=np.float64)
    length = float(np.linalg.norm(result))
    require(math.isfinite(length) and length > 1.0e-12, "zero/non-finite SCNE vector")
    return result / length


def expand_strip(values: Iterable[int]) -> list[tuple[int, int, int]]:
    output: list[tuple[int, int, int]] = []
    strip: list[int] = []
    for value in values:
        if value == 0xFFFF:
            strip.clear()
            continue
        strip.append(value)
        if len(strip) < 3:
            continue
        number = len(strip) - 3
        first, second, third = strip[-3:]
        if number & 1:
            first, second = second, first
        if len({first, second, third}) == 3:
            output.append((first, second, third))
    return output


def _read_helmet_system(archive: apf_outer.Archive) -> bytes:
    try:
        entry = archive.entries[HELMET_OUTER_INDEX]
        require(
            len(entry.segments) == 1
            and entry.segments[0].pack_name == archive.index_path.name,
            "helmet_00 outer entry is not contained in the selected 0A",
        )
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            matches = [
                item for item in record.files
                if item.name == HELMET_NAME and item.type_name == "SCNE"
            ]
            require(len(matches) == 1 and len(matches[0].parts) == 1,
                    "helmet_00 SCNE ownership differs")
            part = matches[0].parts[0]
            block = apf_inner.decode_block(reader, record, part.block_index, MAX_DECOMPRESSED)
    except (IndexError, apf_inner.FormatError) as exc:
        raise VerifyError(f"could not decode source helmet SCNE: {exc}") from exc
    system = block[part.offset : part.offset + part.length]
    require(len(system) == HELMET_SYSTEM_LENGTH, "helmet_00 system length differs")
    return system


def _geometry(
    system: bytes, spec: LodSpec,
) -> tuple[
    np.ndarray, np.ndarray, np.ndarray, list[tuple[int, int, int]],
    list[tuple[int, int, int]],
]:
    positions = np.empty((spec.vertex_count, 3), dtype=np.float64)
    normals = np.empty_like(positions)
    uvs = np.empty((spec.vertex_count, 2), dtype=np.float64)
    for vertex in range(spec.vertex_count):
        offset = spec.stream_start + vertex * STRIDE
        raw = tuple(_snorm(value) for value in struct.unpack_from(">3h", system, offset))
        positions[vertex] = [
            spec.center[axis] + raw[axis] * spec.scale[axis] for axis in range(3)
        ]
        normals[vertex] = _unit(
            _snorm(value) for value in struct.unpack_from(">3h", system, offset + 8)
        )
        uvs[vertex] = (
            2.0 * _snorm(struct.unpack_from(">h", system, offset + 14)[0]),
            2.0 * _snorm(struct.unpack_from(">h", system, offset + 22)[0]),
        )
    words = struct.unpack_from(f">{spec.index_count}H", system, spec.index_offset)
    shell = expand_strip(words[
        spec.shell_index_start : spec.shell_index_start + spec.shell_index_count
    ])
    carrier = expand_strip(words[
        spec.carrier_index_start : spec.carrier_index_start + spec.carrier_index_count
    ])
    require(len(shell) == spec.shell_triangles and len(carrier) == spec.carrier_triangles,
            f"{spec.name} source topology differs")
    exterior: list[tuple[int, int, int]] = []
    for face in shell:
        indices = np.asarray(face)
        center = positions[indices].mean(axis=0)
        normal = normals[indices].sum(axis=0)
        radial = center - np.asarray(spec.center)
        if float(np.dot(normal, radial)) > 0.0:
            exterior.append(face)
    require(bool(exterior), f"{spec.name} exterior shell is missing")
    return positions, normals, uvs, exterior, carrier


def _raster_shell_points(
    positions: np.ndarray,
    uvs: np.ndarray,
    faces: Sequence[tuple[int, int, int]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Raster exact shell atlas texel centers to physical points and sides."""

    points = np.full((WIDTH * HEIGHT, 3), np.nan, dtype=np.float64)
    sides = np.zeros(WIDTH * HEIGHT, dtype=np.int8)
    assigned = np.zeros(WIDTH * HEIGHT, dtype=np.bool_)
    for face_tuple in faces:
        face = np.asarray(face_tuple, dtype=np.int32)
        triangle = uvs[face]
        first_x = max(0, math.ceil(float(triangle[:, 0].min()) * WIDTH - 0.5))
        last_x = min(WIDTH - 1, math.floor(float(triangle[:, 0].max()) * WIDTH - 0.5))
        first_y = max(0, math.ceil(float(triangle[:, 1].min()) * HEIGHT - 0.5))
        last_y = min(HEIGHT - 1, math.floor(float(triangle[:, 1].max()) * HEIGHT - 0.5))
        if first_x > last_x or first_y > last_y:
            continue
        grid_y, grid_x = np.mgrid[first_y : last_y + 1, first_x : last_x + 1]
        u_value = (grid_x + 0.5) / WIDTH
        v_value = (grid_y + 0.5) / HEIGHT
        first, second, third = triangle
        denominator = (
            (second[1] - third[1]) * (first[0] - third[0])
            + (third[0] - second[0]) * (first[1] - third[1])
        )
        require(abs(float(denominator)) > 1.0e-12, "shell UV triangle collapsed")
        first_weight = (
            (second[1] - third[1]) * (u_value - third[0])
            + (third[0] - second[0]) * (v_value - third[1])
        ) / denominator
        second_weight = (
            (third[1] - first[1]) * (u_value - third[0])
            + (first[0] - third[0]) * (v_value - third[1])
        ) / denominator
        third_weight = 1.0 - first_weight - second_weight
        inside = (first_weight >= -1.0e-10) & (second_weight >= -1.0e-10) & (third_weight >= -1.0e-10)
        if not bool(inside.any()):
            continue
        atlas_indices = (grid_y * WIDTH + grid_x)[inside]
        require(not bool(assigned[atlas_indices].any()), "shell UV atlas raster overlaps")
        weights = np.column_stack((
            first_weight[inside], second_weight[inside], third_weight[inside],
        ))
        points[atlas_indices] = weights @ positions[face]
        sides[atlas_indices] = 1 if float(positions[face, 0].sum()) >= 0.0 else -1
        assigned[atlas_indices] = True
    return points, sides, assigned


def _lod_retail_sample_map(system: bytes, spec: LodSpec) -> tuple[np.ndarray, dict[str, object]]:
    """Independently map retail carrier UVs to stock shell-atlas texel centers."""

    positions, _normals, uvs, shell_faces, carrier_faces = _geometry(system, spec)
    points, sides, covered = _raster_shell_points(positions, uvs, shell_faces)
    samples = np.full(WIDTH * HEIGHT, -2, dtype=np.int32)
    samples[covered] = -1
    best_error = np.full(WIDTH * HEIGHT, np.inf, dtype=np.float64)
    best_u = np.zeros(WIDTH * HEIGHT, dtype=np.float64)
    best_v = np.zeros(WIDTH * HEIGHT, dtype=np.float64)

    face_sides: dict[int, list[tuple[int, int, int]]] = {
        -1: [face for face in carrier_faces if np.all(positions[np.asarray(face), 0] <= 1.0e-5)],
        1: [face for face in carrier_faces if np.all(positions[np.asarray(face), 0] >= -1.0e-5)],
    }
    require(bool(face_sides[-1]) and len(face_sides[-1]) == len(face_sides[1]),
            f"{spec.name} retail carrier is not bilateral")
    mapped_counts: dict[str, int] = {}
    for side in (-1, 1):
        atlas_indices = np.flatnonzero(covered & (sides == side))
        yz_points = points[atlas_indices][:, 1:]
        for face_tuple in face_sides[side]:
            face = np.asarray(face_tuple, dtype=np.int32)
            tri = positions[face]
            first, second, third = tri
            denominator = (
                (second[1] - third[1]) * (first[2] - third[2])
                + (third[2] - second[2]) * (first[1] - third[1])
            )
            if abs(float(denominator)) <= 1.0e-12:
                continue
            first_weight = (
                (second[1] - third[1]) * (yz_points[:, 1] - third[2])
                + (third[2] - second[2]) * (yz_points[:, 0] - third[1])
            ) / denominator
            second_weight = (
                (third[1] - first[1]) * (yz_points[:, 1] - third[2])
                + (first[2] - third[2]) * (yz_points[:, 0] - third[1])
            ) / denominator
            third_weight = 1.0 - first_weight - second_weight
            inside = (first_weight >= -1.0e-7) & (second_weight >= -1.0e-7) & (third_weight >= -1.0e-7)
            if not bool(inside.any()):
                continue
            weights = np.column_stack((first_weight, second_weight, third_weight))
            projected_x = weights @ tri[:, 0]
            errors = np.abs(np.abs(projected_x) - np.abs(points[atlas_indices, 0]))
            improve = inside & (errors < best_error[atlas_indices])
            if not bool(improve.any()):
                continue
            targets = atlas_indices[improve]
            best_error[targets] = errors[improve]
            uv_values = weights[improve] @ uvs[face]
            best_u[targets] = uv_values[:, 0]
            best_v[targets] = uv_values[:, 1]
        mapped = np.isfinite(best_error[atlas_indices])
        targets = atlas_indices[mapped]
        in_domain = (
            (best_u[targets] >= 0.0) & (best_u[targets] <= 1.0)
            & (best_v[targets] >= 0.0) & (best_v[targets] <= 1.0)
        )
        valid_targets = targets[in_domain]
        x_value = np.clip(np.rint(best_u[valid_targets] * WIDTH - 0.5), 0, WIDTH - 1).astype(np.int32)
        y_value = np.clip(np.rint(best_v[valid_targets] * HEIGHT - 0.5), 0, HEIGHT - 1).astype(np.int32)
        samples[valid_targets] = y_value * WIDTH + x_value
        mapped_counts["right" if side == 1 else "left"] = len(valid_targets)
    require(all(mapped_counts.values()), f"{spec.name} maps no carrier texels on one side")
    return samples, {
        "node": spec.name,
        "covered_shell_atlas_texels": int(covered.sum()),
        "mapped_retail_texels": mapped_counts,
        "map_sha256": sha256_bytes(samples.astype(">i4", copy=False).tobytes()),
    }


def build_retail_migration_map(system: bytes) -> tuple[np.ndarray, dict[str, object]]:
    maps: list[np.ndarray] = []
    rows: list[dict[str, object]] = []
    for spec in LODS:
        values, row = _lod_retail_sample_map(system, spec)
        maps.append(values)
        rows.append(row)
    high, low = maps
    combined = high.copy()
    low_only = high == -2
    combined[low_only] = low[low_only]
    return combined, {
        "algorithm": "independent_vectorized_physical_yz_to_shell_atlas_nearest_v1",
        "high_lod_priority": True,
        "low_lod_only_texel_count": int(np.count_nonzero(low_only & (low != -2))),
        "combined_map_sha256": sha256_bytes(combined.astype(">i4", copy=False).tobytes()),
        "lods": rows,
    }


def migrate_retail_rgba(retail_rgba: bytes, sample_map: np.ndarray) -> bytes:
    require(len(retail_rgba) == RGBA_LENGTH, "retail crest layer is not 512x512 RGBA")
    source = np.frombuffer(retail_rgba, dtype=np.uint8).reshape((-1, 4))
    output = np.empty_like(source)
    output[:] = source[0]
    mapped = sample_map >= 0
    output[mapped] = source[sample_map[mapped]]
    return output.tobytes()


def palette_is_subset(output_rgba: bytes, source_rgba: bytes) -> bool:
    """Compare exact RGBA palettes with vectorized packed-pixel identities."""

    require(len(output_rgba) == RGBA_LENGTH and len(source_rgba) == RGBA_LENGTH,
            "palette comparison layer is not 512x512 RGBA")
    source_values = np.unique(np.frombuffer(source_rgba, dtype=">u4"))
    output_values = np.unique(np.frombuffer(output_rgba, dtype=">u4"))
    return bool(np.isin(output_values, source_values, assume_unique=True).all())


def validate_semantic_mask(rgba: bytes, label: str) -> dict[str, object]:
    require(len(rgba) == RGBA_LENGTH, f"{label} is not 512x512 RGBA")
    pixels = np.frombuffer(rgba, dtype=np.uint8).reshape((-1, 4))
    require(bool(np.all(pixels[:, 2] == 0)), f"{label} uses blue")
    require(bool(np.all(pixels % 17 == 0)), f"{label} leaves the four-bit lattice")
    sums = pixels[:, 0].astype(np.uint16) + pixels[:, 1].astype(np.uint16)
    require(bool(np.all(sums <= 255)), f"{label} exceeds one red/green unit")
    active = sums > 0
    require(bool(active.any()), f"{label} has no active art")
    return {
        "rgba_sha256": sha256_bytes(rgba),
        "active_texel_count": int(active.sum()),
        "unique_rgba_count": int(len(np.unique(pixels, axis=0))),
        "blue_zero": True,
        "four_bit_lattice": True,
        "red_plus_green_at_most_255": True,
    }


def _cache_directory(raw: bytes) -> CacheDirectory:
    require(len(raw) == CACHE_DIRECTORY_SIZE, "logo-cache directory allocation differs")
    fields = struct.unpack_from(">10I", raw, 0)
    magic, header_size, file_length, zero, block_count, block_ptr, file_count, file_ptr, aux_ptr, name_ptr = fields
    require(
        (magic, header_size, file_length, zero, block_count, file_count)
        == (CACHE_MAGIC, CACHE_HEADER_SIZE, CACHE_HEADER_SIZE, 0, 2, CACHE_FILE_COUNT),
        "logo-cache header differs",
    )
    block_table = 0x14 + block_ptr - 1
    file_table = 0x1C + file_ptr - 1
    aux_table = 0x20 + aux_ptr - 1
    name_offset = 0x24 + name_ptr - 1
    require((block_table, file_table, aux_table, name_offset) == (0x28, 0x68, 0x1688, 0x28F8),
            "logo-cache table pointers differ")
    descriptors: list[tuple[int, int, int]] = []
    cursor = file_table + CACHE_FILE_COUNT * 4
    for index in range(CACHE_FILE_COUNT):
        pointer = file_table + index * 4
        target = pointer + struct.unpack_from(">I", raw, pointer)[0] - 1
        require(target == cursor, f"logo-cache descriptor {index} is not packed")
        file_id, type_hash, count, dram_offset, vram_offset = struct.unpack_from(">5I", raw, target)
        require(type_hash == CACHE_TXTR_HASH and count == 2,
                f"logo-cache descriptor {index} type differs")
        require(dram_offset % CACHE_DRAM_STRIDE == 0 and vram_offset % CACHE_VRAM_STRIDE == 0,
                f"logo-cache descriptor {index} is unaligned")
        require(dram_offset // CACHE_DRAM_STRIDE == vram_offset // CACHE_VRAM_STRIDE,
                f"logo-cache descriptor {index} slots disagree")
        descriptors.append((file_id, dram_offset // CACHE_DRAM_STRIDE, target))
        cursor += 0x14
    require(cursor == aux_table, "logo-cache descriptors do not end at auxiliary table")
    auxiliary: list[tuple[int, int, int, int]] = []
    cursor = aux_table + CACHE_FILE_COUNT * 4
    previous_end = 0
    for index in range(CACHE_FILE_COUNT):
        pointer = aux_table + index * 4
        target = pointer + struct.unpack_from(">I", raw, pointer)[0] - 1
        require(target == cursor, f"logo-cache auxiliary {index} is not packed")
        stream_a, len_a, stream_b, len_b = struct.unpack_from(">4I", raw, target)
        require(stream_a == previous_end and stream_b == stream_a + len_a,
                f"logo-cache stream {index} is not contiguous")
        require(len_a == CACHE_AUX_DRAM_STORED_LENGTH,
                f"logo-cache DRAM stored length {index} differs")
        auxiliary.append((stream_a, len_a, stream_b, len_b))
        previous_end = stream_b + len_b
        cursor += 0x10
    require(cursor == name_offset, "logo-cache auxiliary table end differs")
    end = name_offset
    while end + 1 < len(raw) and raw[end : end + 2] != b"\0\0":
        end += 2
    try:
        internal_name = raw[name_offset:end].decode("utf-16be")
    except UnicodeDecodeError as exc:
        raise VerifyError("logo-cache internal name is not valid UTF-16BE") from exc
    require(internal_name == CACHE_NAME and end + 2 == header_size,
            "logo-cache internal name differs")
    require(file_length + 8 <= len(raw), "logo-cache has no name footer")
    footer_magic = struct.unpack_from(">I", raw, file_length)[0]
    footer_size = struct.unpack_from("<I", raw, file_length + 4)[0]
    require(footer_magic == apf_inner.NAME_FOOTER_MAGIC,
            "logo-cache name-footer magic differs")
    footer_end = file_length + 8 + footer_size
    require(footer_end <= len(raw), "logo-cache name footer is out of bounds")
    names = apf_inner._parse_footer_names(  # type: ignore[attr-defined]
        raw[file_length + 8 : footer_end], CACHE_FILE_COUNT,
    )
    expected_names = {
        (f"{catalog:02d}_logo_l{level}", "TXTR")
        for catalog in range(CATALOG_COUNT)
        for level in range(2)
    }
    require(set(names) == expected_names and len(set(names)) == CACHE_FILE_COUNT,
            "logo-cache footer is not the exact 118 x 2 catalog")
    require(not any(raw[footer_end:]), "logo-cache alignment tail contains nonzero bytes")
    entries: list[CacheEntry] = []
    for index, ((name, type_name), descriptor, aux) in enumerate(zip(names, descriptors, auxiliary)):
        file_id, slot, _offset = descriptor
        require(type_name == "TXTR" and file_id == crc32_inner_name(name),
                f"logo-cache name/id mismatch at {index}")
        try:
            catalog_text, level_text = name.split("_logo_l", 1)
            catalog, level = int(catalog_text), int(level_text)
        except (ValueError, TypeError) as exc:
            raise VerifyError(f"logo-cache name syntax differs: {name}") from exc
        require(0 <= catalog < CATALOG_COUNT and level in (0, 1),
                f"logo-cache name range differs: {name}")
        entries.append(CacheEntry(name, catalog, level, file_id, slot, *aux))
    require(len({entry.name for entry in entries}) == CACHE_FILE_COUNT,
            "logo-cache names are not unique")
    return CacheDirectory(tuple(entries), previous_end)


def _read_outer_raw(
    archive: apf_outer.Archive, reader: apf_inner.ArchiveReader, index: int, size: int,
) -> bytes:
    try:
        entry = archive.entries[index]
    except IndexError as exc:
        raise VerifyError(f"archive has no outer {index}") from exc
    require(
        entry.size == size
        and len(entry.segments) == 1
        and entry.segments[0].pack_name == archive.index_path.name,
            f"outer {index} allocation differs")
    return reader.read(entry, 0, size)


def _decompress_cache_part(stored: bytes, expected: int, label: str) -> bytes:
    require(len(stored) >= apf_inner.H7A_HEADER_SIZE, f"{label} H7A wrapper is truncated")
    magic, uncompressed, compressed, _unknown, shift = struct.unpack_from(">5I", stored, 0)
    require(magic == apf_inner.H7A_MAGIC and uncompressed == expected,
            f"{label} H7A header differs")
    require(compressed == len(stored) and 1 <= shift <= 15,
            f"{label} H7A stored length/shift differs")
    decoded = apf_inner.decompress_h7a(
        stored[apf_inner.H7A_HEADER_SIZE:], expected, shift,
    )
    require(len(decoded) == expected, f"{label} decoded length differs")
    return decoded


def verify_cache(
    source_archive: apf_outer.Archive,
    output_archive: apf_outer.Archive,
    selected_asset: int,
    expected_atlas: bytes,
    expected_semantic: bytes | None,
) -> dict[str, object]:
    with apf_inner.ArchiveReader(source_archive) as source_reader, apf_inner.ArchiveReader(output_archive) as output_reader:
        source_directory_raw = _read_outer_raw(source_archive, source_reader, CACHE_DIRECTORY_INDEX, CACHE_DIRECTORY_SIZE)
        output_directory_raw = _read_outer_raw(output_archive, output_reader, CACHE_DIRECTORY_INDEX, CACHE_DIRECTORY_SIZE)
        source_payload = _read_outer_raw(source_archive, source_reader, CACHE_PAYLOAD_INDEX, CACHE_PAYLOAD_SIZE)
        output_payload = _read_outer_raw(output_archive, output_reader, CACHE_PAYLOAD_INDEX, CACHE_PAYLOAD_SIZE)
    source_directory = _cache_directory(source_directory_raw)
    output_directory = _cache_directory(output_directory_raw)
    require(source_directory.total_stream_length <= len(source_payload),
            "source logo-cache streams exceed their payload")
    require(output_directory.total_stream_length <= len(output_payload),
            "output logo-cache streams exceed their payload")
    require(not any(source_payload[source_directory.total_stream_length:]),
            "source logo-cache payload tail is nonzero")
    require(not any(output_payload[output_directory.total_stream_length:]),
            "output logo-cache payload tail is nonzero")
    source_by_name = {entry.name: entry for entry in source_directory.entries}
    output_by_name = {entry.name: entry for entry in output_directory.entries}
    require(set(source_by_name) == set(output_by_name), "logo-cache name inventory changed")
    unchanged = 0
    selected_rgba: list[bytes] = []
    for name in sorted(source_by_name):
        before, after = source_by_name[name], output_by_name[name]
        require(
            (before.file_id, before.aggregate_slot, before.catalog, before.level)
            == (after.file_id, after.aggregate_slot, after.catalog, after.level),
            f"logo-cache descriptor identity changed: {name}",
        )
        before_a = source_payload[before.stream_a : before.stream_a + before.length_a]
        before_b = source_payload[before.stream_b : before.stream_b + before.length_b]
        after_a = output_payload[after.stream_a : after.stream_a + after.length_a]
        after_b = output_payload[after.stream_b : after.stream_b + after.length_b]
        require(
            len(before_a) == before.length_a
            and len(before_b) == before.length_b
            and len(after_a) == after.length_a
            and len(after_b) == after.length_b,
            f"logo-cache stream is truncated: {name}",
        )
        if before.catalog != selected_asset:
            require(before_a == after_a and before_b == after_b,
                    f"nonselected logo-cache sub-block changed: {name}")
            unchanged += 1
            continue
        dram = _decompress_cache_part(after_a, CACHE_DRAM_STRIDE, f"{name} DRAM")
        vram = _decompress_cache_part(after_b, CACHE_VRAM_STRIDE, f"{name} VRAM")
        metadata = apf_inner.parse_txtr_metadata(dram)
        rgba = decode_4444(metadata, vram[:BASE_LENGTH])
        validate_semantic_mask(rgba, f"selected cache {name}")
        selected_rgba.append(rgba)
    require(unchanged == CACHE_FILE_COUNT - 2,
            "nonselected logo-cache verification count differs")
    require(len(selected_rgba) == 2 and selected_rgba[0] == selected_rgba[1],
            "selected cache l0/l1 decoded semantic layers differ")
    require(selected_rgba[0] != expected_atlas,
            "selected menu cache incorrectly contains the shell atlas")
    if expected_semantic is not None:
        require(selected_rgba[0] == expected_semantic,
                "selected cache does not equal the expected semantic design")
    return {
        "nonselected_cache_layer_count": unchanged,
        "nonselected_stored_h7a_subblocks_byte_exact": True,
        "selected_l0_l1_decoded_identical": True,
        "selected_is_semantic_not_shell_atlas": True,
        "selected_semantic_rgba_sha256": sha256_bytes(selected_rgba[0]),
        "selected_exact_expected_semantic": expected_semantic is not None,
        "source_directory_sha256": sha256_bytes(source_directory_raw),
        "output_directory_sha256": sha256_bytes(output_directory_raw),
        "source_payload_sha256": sha256_bytes(source_payload),
        "output_payload_sha256": sha256_bytes(output_payload),
    }


def _load_rgba(path: Path, label: str) -> bytes:
    require(path.is_file() and not path.is_symlink(), f"{label} is unavailable: {path}")
    with Image.open(path) as image:
        image.load()
        require(image.size == (WIDTH, HEIGHT), f"{label} is not 512x512")
        return image.convert("RGBA").tobytes()


def _find_package_hashes(value: object) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if isinstance(value, dict):
        candidate = value.get("package_entry_sha256_by_asset_index")
        if isinstance(candidate, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in candidate.items()):
            found.append(candidate)  # type: ignore[arg-type]
        for child in value.values():
            found.extend(_find_package_hashes(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_package_hashes(child))
    return found


def verify(
    source_path: Path,
    output_path: Path,
    *,
    selected_asset: int,
    selected_outer: int,
    expected_atlas: bytes | None,
    expected_atlas_sha256: str,
    expected_semantic: bytes | None = None,
    compilation_receipt: Path | None = None,
) -> dict[str, object]:
    source_path = Path(os.path.abspath(os.fspath(Path(source_path).expanduser())))
    output_path = Path(os.path.abspath(os.fspath(Path(output_path).expanduser())))
    for path, label in ((source_path, "source"), (output_path, "output")):
        require(path.is_file() and not path.is_symlink(),
                f"{label} 0A is not a regular non-symlink file: {path}")
    source_stat, output_stat = source_path.stat(), output_path.stat()
    require((source_stat.st_dev, source_stat.st_ino) != (output_stat.st_dev, output_stat.st_ino),
            "source and output 0A alias one inode")
    require(0 <= selected_asset < CATALOG_COUNT, "selected asset is outside 0..117")
    require(len(expected_atlas_sha256) == 64 and all(c in "0123456789abcdef" for c in expected_atlas_sha256),
            "expected atlas SHA-256 is malformed")
    if expected_atlas is not None:
        require(len(expected_atlas) == RGBA_LENGTH, "expected atlas is not 512x512 RGBA")
        require(sha256_bytes(expected_atlas) == expected_atlas_sha256,
                "expected atlas PNG/hash disagree")
        validate_semantic_mask(expected_atlas, "expected selected shell atlas")
    if expected_semantic is not None:
        validate_semantic_mask(expected_semantic, "expected selected semantic cache")

    source_sha_before = sha256_file(source_path)
    output_sha_before = sha256_file(output_path)
    source_archive, source_catalog = open_catalog(source_path)
    output_archive, output_catalog = open_standalone_output_catalog(
        output_path, source_archive,
    )
    require(source_catalog == output_catalog, "output crest catalog ownership changed")
    require(source_catalog[selected_asset] == selected_outer,
            "selected asset/outer pair does not match the archive")

    source_system = _read_helmet_system(source_archive)
    sample_map, map_report = build_retail_migration_map(source_system)
    selected_decoded_hash: str | None = None
    selected_output_rgba: bytes | None = None
    nonselected_rows: dict[str, object] = {}
    receipt_hashes: dict[str, str] | None = None
    if compilation_receipt is not None:
        require(compilation_receipt.is_file() and not compilation_receipt.is_symlink(),
                "compilation receipt is unavailable")
        document = json.loads(compilation_receipt.read_text(encoding="utf-8"))
        candidates = _find_package_hashes(document)
        require(len(candidates) == 1, "compilation receipt package-hash inventory is missing/ambiguous")
        receipt_hashes = candidates[0]
        require(set(receipt_hashes) == {str(index) for index in range(CATALOG_COUNT)},
                "compilation receipt package-hash inventory is incomplete")

    # Stream one source/output package pair at a time.  Holding the complete
    # decoded 118 x 2 x 2 catalog would waste roughly half a gigabyte of RAM.
    with apf_inner.ArchiveReader(source_archive) as source_reader, apf_inner.ArchiveReader(output_archive) as output_reader:
        for asset in range(CATALOG_COUNT):
            outer_index = source_catalog[asset]
            before = _decode_package(source_archive, source_reader, asset, outer_index)
            after = _decode_package(output_archive, output_reader, asset, outer_index)
            require(before.outer_index == after.outer_index == outer_index,
                    f"crest package {asset:02d} outer ownership changed")
            if receipt_hashes is not None:
                require(receipt_hashes[str(asset)] == after.raw_sha256,
                        f"published package {asset:02d} hash differs from compilation receipt")
            layer_rows: dict[str, object] = {}
            for name in ("logo_l0", "logo_l1"):
                source_layer = before.layers[name]
                output_layer = after.layers[name]
                require(source_layer.dram == output_layer.dram,
                        f"crest package {asset:02d} {name} DRAM descriptor changed")
                selected_contract: dict[str, object] | None = None
                if asset == selected_asset:
                    actual_hash = sha256_bytes(output_layer.rgba)
                    require(actual_hash == expected_atlas_sha256,
                            f"selected package {name} atlas hash differs")
                    selected_contract = validate_semantic_mask(
                        output_layer.rgba, f"selected package {name}",
                    )
                    if expected_atlas is not None:
                        require(output_layer.rgba == expected_atlas,
                                f"selected package {name} atlas bytes differ")
                    selected_decoded_hash = actual_hash
                    selected_output_rgba = output_layer.rgba
                    expected_hash = expected_atlas_sha256
                else:
                    expected = migrate_retail_rgba(source_layer.rgba, sample_map)
                    require(output_layer.rgba == expected,
                            f"nonselected package {asset:02d} {name} migration differs")
                    require(palette_is_subset(output_layer.rgba, source_layer.rgba),
                            f"nonselected package {asset:02d} {name} introduced a palette value")
                    expected_hash = sha256_bytes(expected)
                layer_rows[name] = {
                    "source_rgba_sha256": sha256_bytes(source_layer.rgba),
                    "expected_output_rgba_sha256": expected_hash,
                    "output_rgba_sha256": sha256_bytes(output_layer.rgba),
                    "palette_values_preserved": asset != selected_asset,
                    "mip_tail_size_valid": output_layer.mip_length == MIP_LENGTH,
                    "mip_content_scope": "size_only_not_independently_regenerated",
                    "selected_semantic_contract": selected_contract,
                }
            if asset == selected_asset:
                require(after.layers["logo_l0"].rgba == after.layers["logo_l1"].rgba,
                        "selected package l0/l1 decoded atlases differ")
            nonselected_rows[str(asset)] = {
                "outer_index": after.outer_index,
                "output_entry_sha256": after.raw_sha256,
                "layers": layer_rows,
            }
    require(
        selected_decoded_hash == expected_atlas_sha256 and selected_output_rgba is not None,
        "selected atlas was not independently witnessed",
    )

    cache_report = verify_cache(
        source_archive, output_archive, selected_asset,
        expected_atlas or selected_output_rgba,
        expected_semantic,
    )
    source_sha_after = sha256_file(source_path)
    output_sha_after = sha256_file(output_path)
    require(source_sha_after == source_sha_before, "pristine source changed during verification")
    require(output_sha_after == output_sha_before, "standalone output changed during verification")
    return {
        "schema": SCHEMA,
        "claim": CLAIM,
        "runtime_or_visual_quality_proved": False,
        "source": {
            "path": str(source_path),
            "sha256_before": source_sha_before,
            "sha256_after": source_sha_after,
            "unchanged": True,
            "opened_read_only": True,
        },
        "output": {
            "path": str(output_path),
            "sha256_before": output_sha_before,
            "sha256_after": output_sha_after,
            "unchanged": True,
            "distinct_inode_from_source": True,
            "standalone_0a_verified_with_private_pristine_sibling_view": True,
            "retained_sibling_links_created": False,
        },
        "selected": {
            "asset_index": selected_asset,
            "outer_index": selected_outer,
            "atlas_rgba_sha256": selected_decoded_hash,
            "l0_l1_decoded_identical": True,
            "expected_atlas_bytes_supplied": expected_atlas is not None,
        },
        "catalog": {
            "package_count": CATALOG_COUNT,
            "layer_count": CATALOG_COUNT * 2,
            "selected_package_count": 1,
            "nonselected_package_count": CATALOG_COUNT - 1,
            "all_nonselected_layers_exact_independent_physical_migration": True,
            "all_output_dram_descriptors_exact_source": True,
            "published_entry_hashes_match_optional_receipt": receipt_hashes is not None,
            "packages": nonselected_rows,
        },
        "retail_migration_map": map_report,
        "cache": cache_report,
        "limitations": [
            "package mip tails are allocation-checked but not independently regenerated by this verifier",
            "selected cache is exact only when --expected-semantic-png is supplied",
            "no emulator, gameplay, hardware, or visual-quality claim is made",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-0a", required=True, type=Path)
    parser.add_argument("--output-0a", required=True, type=Path)
    parser.add_argument("--selected-asset", required=True, type=int)
    parser.add_argument("--selected-outer", required=True, type=int)
    parser.add_argument("--expected-atlas-png", type=Path)
    parser.add_argument("--expected-atlas-sha256")
    parser.add_argument("--expected-semantic-png", type=Path)
    parser.add_argument("--compilation-receipt", type=Path)
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        expected_atlas = (
            _load_rgba(args.expected_atlas_png, "expected atlas PNG")
            if args.expected_atlas_png is not None else None
        )
        expected_hash = (
            args.expected_atlas_sha256.lower()
            if isinstance(args.expected_atlas_sha256, str)
            else sha256_bytes(expected_atlas) if expected_atlas is not None else ""
        )
        require(bool(expected_hash),
                "supply --expected-atlas-png and/or --expected-atlas-sha256")
        expected_semantic = (
            _load_rgba(args.expected_semantic_png, "expected semantic PNG")
            if args.expected_semantic_png is not None else None
        )
        report = verify(
            args.source_0a, args.output_0a,
            selected_asset=args.selected_asset,
            selected_outer=args.selected_outer,
            expected_atlas=expected_atlas,
            expected_atlas_sha256=expected_hash,
            expected_semantic=expected_semantic,
            compilation_receipt=args.compilation_receipt,
        )
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, ValueError, VerifyError, apf_inner.FormatError, apf_outer.FormatError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
