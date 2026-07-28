#!/usr/bin/env python3
"""Replace the NFL 2K5 Crib ``bar_monitor`` texture in a copied retail XISO.

This is intentionally one bounded proof route, not a generic SCNE writer.  It
accepts an exact 128x128 RGBA8 PNG, regenerates the five P8 mip levels, safely
recompresses the owning ``room`` SCNE, and changes only that fixed SCNE span
inside a newly-created XISO.  The source image is opened read-only.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import platform_compat  # noqa: E402

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import nfl_crib_team_photo_png_import as photo
from nfl_scene_probe import ResourceRecord, decode_resource
from nfl_scne_inventory import parse_scene
import nfl_tset_png_import as palette_tools
from nfl_txtr import (
    COMPRESSED_SENTINEL,
    HEADER,
    compress_vc_lz,
    decode_chunk,
    encode_rgba_png,
    minimum_vc_lz_overlap_scratch,
    swizzle_2d,
    unswizzle_2d,
)
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_crib_bar_monitor_png_xiso/v1"
SELECTOR = "crib_scene_texture:room:22"
ASSET_ID = "nfl2k5.crib.scene.c0002.t022"

PACK_PATH = "vc_53450030/C"
PACK_SECTOR = 2_554_593
PACK_SIZE = 315_131_904
PACK_SHA256 = "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090"
OUTER_INDEX = 4248
OUTER_ID = 0xC61A9833
OUTER_SIZE = 5_131_344
OUTER_PACK_OFFSET = 167_442_432
OUTER_SHA256 = "b1237a4d43ff6cbbe8de0b40c1f623a32a7f77e900873d6b4fb4f4527ad10bb2"
CHUNK_INDEX = 2
CHUNK_OFFSET = 114_960
SPAN_PACK_OFFSET = OUTER_PACK_OFFSET + CHUNK_OFFSET
# Where this span sits in the project's own rebuild. Documentation and test
# fixture only -- NEVER a gate: a differently packed dump puts it elsewhere,
# so the writer derives the offset from pack C's actual position instead.
SPAN_ABSOLUTE = 5_399_363_856
STORED_SIZE = 1_588_496
SPAN_SIZE = HEADER.size + STORED_SIZE
SYSTEM_BYTES = 666_240
VIDEO_BYTES = 1_942_144
DECODED_SIZE = SYSTEM_BYTES + VIDEO_BYTES
SOURCE_SPAN_SHA256 = "defc083de29b3b2dc3e2dd6681cfc2cd7ee13b30b213f9f84f8bd4f75e7296dd"
SOURCE_DECODED_SHA256 = "e1627f1e0f3f64b9f3ddd61606bda56924ab1525f14efc573ee1ef17d77ba3f0"
SOURCE_SYSTEM_SHA256 = "0605117aef1c04b4262360a60260bc07f77c528fc384efa2f82e33ac45bb64ac"
SOURCE_VIDEO_SHA256 = "5d18e3757c0a6542868aacf13e37d9d12a2d04d42bc4fbae25afd07a0a335555"
SOURCE_WRAPPER_SHA256 = "497f06d91c978d4c682d77be8925743d5d0fdbf3d226ec17cfb4d0a823d33970"

RETAIL_SCRATCH = 16
RETAIL_CONSUMED = 1_588_484
RETAIL_STREAM_SHA256 = "26d96407c1c7d99fcad984768e20e2a1a2fca72462e600c522b3807f19dbb7c5"
OPAQUE_TAIL_SIZE = STORED_SIZE - RETAIL_CONSUMED
OPAQUE_TAIL_SHA256 = "1066822350173c85ed6e2f120f240915988c32a894d0c433569ed7637864796e"
MAX_SAFE_SCRATCH = 3_120

SCENE_INDEX = 4186
SCENE_NAME = "room"
TEXTURE_INDEX = 22
TEXTURE_DESCRIPTOR_OFFSET = 24_880
TEXTURE_DESCRIPTOR_SHA256 = "6eb6d404b554fa7045d39f52802961151508533666d47681c39822f9c23e5a7d"
PACKED_FORMAT = 0x07750B29
PIXEL_OFFSET = 740_096
PALETTE_OFFSET = 761_920
MATERIAL_INDEX = 43
MATERIAL_NAME = "bar_monitor"
MATERIAL_OFFSET = 31_312
MATERIAL_SHA256 = "ce3fc6211b1053ced2abcc39e2995d9d15a477a1b845974f0bb936648e6c0e63"
SHAPE_INDEX = 4
SHAPE_NAME = "r2_living_room"
SHAPE_OFFSET = 42_448
SHAPE_SHA256 = "8e5ad6f8279dea0afe1027c80678694f190fa9fb1c880e7ac928d8564ea98cf2"
SUBMESH_INDEX = 3
SUBMESH_OFFSET = 349_936
SUBMESH_SHA256 = "6c9c8ac20d6da023c91da5b604d32a41cc886946f09acd9829ed3d841eff39d5"
COMMAND_OFFSET = 354_196
COMMAND_SIZE = 172
COMMAND_SHA256 = "df7ca7eeb4b37ab3acb5983cbd2f42472cc8ffb7d59ac60afba4a15285dad33f"

MIP_DIMENSIONS = (128, 64, 32, 16, 8)
MIP_INDEX_BYTES = (16_384, 4_096, 1_024, 256, 64)
INDEX_CHAIN_BYTES = sum(MIP_INDEX_BYTES)
PALETTE_BYTES = 1_024
TARGET_VIDEO_OFFSET = SYSTEM_BYTES + PIXEL_OFFSET
TARGET_ALLOCATION_BYTES = INDEX_CHAIN_BYTES + PALETTE_BYTES
SOURCE_ALLOCATION_SHA256 = "ea8b2fe8b9024903b563c4245bc5f840514b79254e6e077e28db4354742244e2"
SOURCE_BASE_RGBA_SHA256 = "1c422972318922fa79d0a8dd5c8827d70277c1c92ebb87a67f0cd80ca27ce075"

MAX_PNG_BYTES = 32 * 1024 * 1024
COMPARE_CHUNK = 16 * 1024 * 1024


class BarMonitorError(ValueError):
    """A source, PNG, rebuild, or copied XISO failed the bounded contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BarMonitorError(message)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def align16(value: int) -> int:
    return (value + 15) & ~15


def resource_record(scratch: int) -> ResourceRecord:
    return ResourceRecord(
        outer_index=OUTER_INDEX,
        outer_id=f"0x{OUTER_ID:08x}",
        outer_size=OUTER_SIZE,
        chunk_index=CHUNK_INDEX,
        chunk_offset=CHUNK_OFFSET,
        kind="SCNE",
        stored_size=STORED_SIZE,
        word_08=SYSTEM_BYTES,
        word_0c=VIDEO_BYTES,
        word_10=COMPRESSED_SENTINEL,
        word_14=scratch,
    )


def _verify_scene(decoded: bytes, scratch: int, *, source: bool) -> dict[str, Any]:
    record = resource_record(scratch)
    scene, _names, mappings, _sample = parse_scene(SCENE_INDEX, record, decoded, {})
    require(scene["name"] == SCENE_NAME, "owning SCNE is no longer the room scene")
    require(
        len(scene["nodes"]) == 79
        and len(scene["shapes"]) == 79
        and len(scene["materials"]) == 122
        and len(scene["submeshes"]) == 177,
        "room SCNE table counts changed",
    )
    texture = scene["embedded_textures"][TEXTURE_INDEX]
    require(
        texture["descriptor_offset"] == TEXTURE_DESCRIPTOR_OFFSET
        and texture["pixel_offset"] == PIXEL_OFFSET
        and texture["palette_offset"] == PALETTE_OFFSET
        and texture["packed_format"] == PACKED_FORMAT
        and texture["packed_size"] == 0
        and texture["descriptor_flags"] == 0x80000000
        and texture["format_name"] == "P8"
        and texture["mip_levels"] == 5
        and texture["width"] == texture["height"] == 128,
        "bar_monitor embedded texture descriptor changed",
    )
    material = scene["materials"][MATERIAL_INDEX]
    require(
        material["record_offset"] == MATERIAL_OFFSET
        and material["name"] == MATERIAL_NAME
        and material["texture_pointer_field"] == MATERIAL_OFFSET + 0x30
        and material["texture_target"] == TEXTURE_DESCRIPTOR_OFFSET
        and material["texture_index"] == TEXTURE_INDEX,
        "bar_monitor material-to-texture ownership changed",
    )
    mapping = mappings[MATERIAL_INDEX]
    require(mapping["material_name"] == MATERIAL_NAME and
            mapping["texture_index"] == TEXTURE_INDEX,
            "bar_monitor material mapping changed")
    shape = scene["shapes"][SHAPE_INDEX]
    require(
        shape["record_offset"] == SHAPE_OFFSET
        and shape["name"] == SHAPE_NAME
        and shape["vertex_count"] == 2_927
        and shape["submesh_count"] == 20,
        "bar_monitor owning room shape changed",
    )
    submeshes = [
        item for item in scene["submeshes"]
        if item["shape_index"] == SHAPE_INDEX
        and item["submesh_index"] == SUBMESH_INDEX
    ]
    require(len(submeshes) == 1, "bar_monitor owning submesh is unavailable")
    submesh = submeshes[0]
    require(
        submesh["record_offset"] == SUBMESH_OFFSET
        and submesh["material_index"] == MATERIAL_INDEX
        and submesh["material_name"] == MATERIAL_NAME
        and submesh["command_offset"] == COMMAND_OFFSET
        and submesh["primary_command_word_count"] == 43
        and submesh["secondary_command_word_count"] == 0
        and submesh["primitive_mode_counts"] == {"END": 1, "TRIANGLE_STRIP": 1}
        and submesh["index_element_count"] == 72
        and submesh["draw_array_vertex_count"] == 6
        and submesh["maximum_vertex_index"] == 618,
        "bar_monitor owning submesh/command contract changed",
    )
    require(
        sha256(decoded[TEXTURE_DESCRIPTOR_OFFSET:TEXTURE_DESCRIPTOR_OFFSET + 0x20])
        == TEXTURE_DESCRIPTOR_SHA256
        and sha256(decoded[MATERIAL_OFFSET:MATERIAL_OFFSET + 0x80]) == MATERIAL_SHA256
        and sha256(decoded[SHAPE_OFFSET:SHAPE_OFFSET + 0x100]) == SHAPE_SHA256
        and sha256(decoded[SUBMESH_OFFSET:SUBMESH_OFFSET + 0x80]) == SUBMESH_SHA256
        and sha256(decoded[COMMAND_OFFSET:COMMAND_OFFSET + COMMAND_SIZE]) == COMMAND_SHA256,
        "bar_monitor descriptor/material/geometry records changed",
    )
    if source:
        require(sha256(decoded[:SYSTEM_BYTES]) == SOURCE_SYSTEM_SHA256 and
                sha256(decoded[SYSTEM_BYTES:]) == SOURCE_VIDEO_SHA256,
                "source room SCNE system/video identity changed")
    return {"scene": scene, "texture": texture, "submesh": submesh}


def _decode_source_span(span: bytes) -> tuple[bytes, bytes]:
    require(len(span) == SPAN_SIZE and sha256(span) == SOURCE_SPAN_SHA256,
            "retail room SCNE span size/hash mismatch")
    require(sha256(span[:HEADER.size]) == SOURCE_WRAPPER_SHA256,
            "retail room SCNE wrapper hash mismatch")
    fields = HEADER.unpack_from(span)
    require(fields == (
        b"SCNE", STORED_SIZE, SYSTEM_BYTES, VIDEO_BYTES,
        COMPRESSED_SENTINEL, RETAIL_SCRATCH, 0, 0,
    ), "retail room SCNE wrapper fields changed")
    decoded, detail = decode_resource(span, resource_record(RETAIL_SCRATCH))
    require(len(decoded) == DECODED_SIZE and sha256(decoded) == SOURCE_DECODED_SHA256,
            "retail room SCNE decoded identity changed")
    lz = detail.get("lz")
    require(isinstance(lz, dict) and
            lz.get("stream_tag") == 1 and lz.get("offset_bits") == 12 and
            lz.get("consumed_bytes") == RETAIL_CONSUMED,
            "retail room SCNE VC-LZ contract changed")
    stream = span[HEADER.size:HEADER.size + RETAIL_CONSUMED]
    tail = span[HEADER.size + RETAIL_CONSUMED:]
    require(sha256(stream) == RETAIL_STREAM_SHA256,
            "retail room SCNE compressed stream changed")
    require(len(tail) == OPAQUE_TAIL_SIZE and sha256(tail) == OPAQUE_TAIL_SHA256,
            "retail room SCNE opaque final bytes changed")
    _verify_scene(decoded, RETAIL_SCRATCH, source=True)
    allocation = decoded[
        TARGET_VIDEO_OFFSET:TARGET_VIDEO_OFFSET + TARGET_ALLOCATION_BYTES
    ]
    require(sha256(allocation) == SOURCE_ALLOCATION_SHA256,
            "retail bar_monitor P8 allocation changed")
    return decoded, tail


def read_png(path: Path) -> tuple[Path, bytes, bytes]:
    try:
        resolved, payload, rgba = photo.read_png(path)
    except (photo.CribPhotoImportError, palette_tools.ImportError) as exc:
        raise BarMonitorError(
            "bar_monitor requires an exact 128x128 non-interlaced RGBA8 PNG: "
            f"{exc}"
        ) from exc
    require(0 < len(payload) <= MAX_PNG_BYTES, "bar_monitor PNG size is invalid")
    return resolved, payload, rgba


def _compile_pixels(rgba: bytes) -> tuple[bytes, bytes, dict[str, Any]]:
    levels = photo.generate_mips(rgba)
    palette, linear_levels, quantization = palette_tools.quantize_levels(levels)
    require(tuple(len(item) for item in linear_levels) == MIP_INDEX_BYTES,
            "bar_monitor quantized mip sizes changed")
    swizzled = [
        swizzle_2d(indices, level.width, level.height, 1)
        for indices, level in zip(linear_levels, levels)
    ]
    index_chain = b"".join(swizzled)
    palette_bgra = palette_tools.palette_bytes(palette)
    require(len(index_chain) == INDEX_CHAIN_BYTES and
            len(palette_bgra) == PALETTE_BYTES,
            "bar_monitor fixed P8 allocation changed")

    palette_rgba = [
        bytes((palette_bgra[index * 4 + 2], palette_bgra[index * 4 + 1],
               palette_bgra[index * 4], palette_bgra[index * 4 + 3]))
        for index in range(256)
    ]
    cursor = 0
    decoded_levels: list[bytes] = []
    for level, expected in zip(levels, linear_levels):
        size = level.width * level.height
        actual = unswizzle_2d(index_chain[cursor:cursor + size],
                              level.width, level.height, 1)
        require(actual == expected, "bar_monitor mip swizzle round-trip changed")
        decoded_levels.append(b"".join(palette_rgba[value] for value in actual))
        cursor += size
    require(cursor == INDEX_CHAIN_BYTES, "bar_monitor mip traversal changed")
    preview = encode_rgba_png(128, 128, decoded_levels[0])
    require(palette_tools.decode_rgba_png(preview, (128, 128)) ==
            (128, 128, decoded_levels[0]),
            "bar_monitor replacement preview failed strict PNG reparse")
    return index_chain + palette_bgra, preview, {
        "filter": "unpremultiplied_rgba_2x2_box_round_nearest",
        "dimensions": [[value, value] for value in MIP_DIMENSIONS],
        "index_bytes": list(MIP_INDEX_BYTES),
        "shared_palette_across_all_levels": True,
        "each_level_swizzled_independently": True,
        "palette_entries_used": len(palette),
        "quantization": quantization,
        "decoded_level_rgba_sha256": [sha256(item) for item in decoded_levels],
    }


def difference_runs(before: bytes, after: bytes) -> tuple[int, list[list[int]]]:
    require(len(before) == len(after), "difference inputs changed size")
    changed = 0
    runs: list[list[int]] = []
    for offset, (left, right) in enumerate(zip(before, after)):
        if left == right:
            continue
        changed += 1
        if not runs or offset != runs[-1][1] + 1:
            runs.append([offset, offset])
        else:
            runs[-1][1] = offset
    return changed, runs


def compile_replacement(source_span: bytes, rgba: bytes) -> tuple[bytes, bytes, dict[str, Any]]:
    decoded, opaque_tail = _decode_source_span(source_span)
    allocation, preview, mip_report = _compile_pixels(rgba)
    rebuilt_decoded = bytearray(decoded)
    rebuilt_decoded[
        TARGET_VIDEO_OFFSET:TARGET_VIDEO_OFFSET + TARGET_ALLOCATION_BYTES
    ] = allocation
    rebuilt_decoded_bytes = bytes(rebuilt_decoded)
    require(len(rebuilt_decoded_bytes) == DECODED_SIZE,
            "bar_monitor rebuild changed decoded SCNE size")
    changed_decoded, decoded_runs = difference_runs(decoded, rebuilt_decoded_bytes)
    require(changed_decoded > 0 and all(
        TARGET_VIDEO_OFFSET <= start <= end < TARGET_VIDEO_OFFSET + TARGET_ALLOCATION_BYTES
        for start, end in decoded_runs
    ), "bar_monitor decoded changes escape its fixed P8 allocation or are empty")

    try:
        stream, compression = compress_vc_lz(
            rebuilt_decoded_bytes,
            stream_tag=1,
            offset_bits=12,
            max_encoded_size=RETAIL_CONSUMED,
            verify_roundtrip=True,
        )
    except Exception as exc:
        raise BarMonitorError(
            "This PNG is too visually complex for the room SCNE's fixed compressed "
            "allocation. Simplify large noisy/dithered areas and try again. "
            f"Encoder detail: {exc}"
        ) from exc
    unused = STORED_SIZE - len(stream)
    exact_scratch = minimum_vc_lz_overlap_scratch(
        stream, STORED_SIZE, DECODED_SIZE
    )
    required_scratch = align16(max(unused, exact_scratch))
    require(
        required_scratch <= MAX_SAFE_SCRATCH,
        "This PNG compresses outside the conservative room-SCNE loader envelope "
        f"({required_scratch} scratch bytes required; {MAX_SAFE_SCRATCH} proved). "
        "Add a small amount of repeated visual detail and try again.",
    )
    wrapper = HEADER.pack(
        b"SCNE", STORED_SIZE, SYSTEM_BYTES, VIDEO_BYTES,
        COMPRESSED_SENTINEL, max(RETAIL_SCRATCH, required_scratch), 0, 0,
    )
    fill = STORED_SIZE - len(stream) - len(opaque_tail)
    require(fill >= 0, "bar_monitor compressed stream overlaps the preserved tail")
    replacement = wrapper + stream + bytes(fill) + opaque_tail
    require(len(replacement) == SPAN_SIZE and
            replacement[-OPAQUE_TAIL_SIZE:] == opaque_tail,
            "bar_monitor fixed-span assembly changed size/tail")

    rebuilt_chunk = resource_record(max(RETAIL_SCRATCH, required_scratch)).as_chunk()
    roundtrip, info = decode_chunk(replacement, rebuilt_chunk)
    require(info is not None and info.consumed_bytes == len(stream) and
            roundtrip == rebuilt_decoded_bytes,
            "bar_monitor rebuilt SCNE failed independent decode")
    parsed = _verify_scene(roundtrip, max(RETAIL_SCRATCH, required_scratch), source=False)
    texture = parsed["texture"]
    require(texture.get("rgba_sha256") == sha256(preview_rgba(preview)),
            "bar_monitor reparsed base texture differs from preview")
    require(roundtrip[:SYSTEM_BYTES] == decoded[:SYSTEM_BYTES],
            "bar_monitor rebuild changed SCNE system/geometry bytes")
    outside_before = decoded[:TARGET_VIDEO_OFFSET] + decoded[
        TARGET_VIDEO_OFFSET + TARGET_ALLOCATION_BYTES:
    ]
    outside_after = roundtrip[:TARGET_VIDEO_OFFSET] + roundtrip[
        TARGET_VIDEO_OFFSET + TARGET_ALLOCATION_BYTES:
    ]
    require(outside_before == outside_after,
            "bar_monitor rebuild changed another decoded allocation")

    return replacement, preview, {
        "mips": mip_report,
        "decoded": {
            "size": len(roundtrip),
            "sha256": sha256(roundtrip),
            "changed_byte_count": changed_decoded,
            "changed_run_count": len(decoded_runs),
            "changed_runs": decoded_runs,
            "changes_bounded_to_target_allocation": True,
            "system_geometry_identical": True,
            "replacement_allocation_sha256": sha256(allocation),
        },
        "compression": {
            **asdict(compression),
            "retail_consumed_cap": RETAIL_CONSUMED,
            "stored_bytes": STORED_SIZE,
            "unused_stored_bytes": unused,
            "exact_minimum_overlap_scratch_bytes": exact_scratch,
            "required_aligned_scratch_bytes": required_scratch,
            "written_wrapper_scratch_bytes": max(RETAIL_SCRATCH, required_scratch),
            "conservative_corpus_scratch_cap": MAX_SAFE_SCRATCH,
            "opaque_tail_bytes_preserved": len(opaque_tail),
            "opaque_tail_sha256": sha256(opaque_tail),
        },
        "replacement_span": {
            "size": len(replacement),
            "sha256": sha256(replacement),
            "fixed_allocation": True,
        },
    }


def preview_rgba(png: bytes) -> bytes:
    width, height, rgba = palette_tools.decode_rgba_png(png, (128, 128))
    require((width, height) == (128, 128), "preview dimensions changed")
    return rgba


def _open_regular_readonly(path: Path, label: str) -> tuple[Path, int, tuple[int, int]]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise BarMonitorError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    identity = common.fd_identity(descriptor)
    try:
        require(common.path_identity(resolved) == identity,
                f"{label} pathname identity changed")
    except Exception:
        os.close(descriptor)
        raise
    return resolved, descriptor, identity


def pwrite_all(descriptor: int, offset: int, payload: bytes) -> None:
    cursor = 0
    while cursor < len(payload):
        written = platform_compat.pwrite(descriptor, payload[cursor:], offset + cursor)
        require(written > 0, f"short XISO write at 0x{offset + cursor:x}")
        cursor += written


def reserve_staging(final: Path, role: str) -> common.OwnedFile:
    """Reserve a hidden sibling; the requested final name stays absent."""

    for attempt in range(100):
        candidate = final.with_name(
            f".{final.name}.codex-{role}-building-{os.getpid()}-{attempt}"
        )
        try:
            return common.reserve_file(candidate)
        except common.PatchError:
            if common.path_identity(candidate) is not None:
                continue
            raise
    raise BarMonitorError(f"could not reserve a private {role} staging file")


def publish_owned(staging: common.OwnedFile, final: Path) -> tuple[Path, tuple[int, int]]:
    """No-replace publish a fully written inode with a hard link."""

    require(common.owned_path_matches(staging),
            "staging pathname changed before publication")
    require(common.path_identity(final) is None,
            f"final output appeared during build: {final}")
    try:
        os.link(staging.path, final, follow_symlinks=False)
    except FileExistsError as exc:
        raise BarMonitorError(f"final output appeared during build: {final}") from exc
    require(common.path_identity(final) == staging.identity,
            "published pathname does not reference the verified staging inode")
    # Commit the hard link's directory entry where the platform offers that.
    # Windows has no directory-flush primitive, so the helper reports ``False``
    # instead of pretending the entry reached the platter.
    platform_compat.fsync_directory(final.parent)
    return final, staging.identity


def unlink_identity(path: Path, identity: tuple[int, int]) -> None:
    if common.path_identity(path) == identity:
        path.unlink()


def compare_images(source_fd: int, output_fd: int, size: int,
                   absolute: int, replacement: bytes) -> tuple[str, str, int, int]:
    """Hash both images and prove equality everywhere except the selected span."""

    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    changed = 0
    runs = 0
    in_run = False
    position = 0
    target_end = absolute + len(replacement)
    while position < size:
        request = min(COMPARE_CHUNK, size - position)
        before = platform_compat.pread(source_fd, request, position)
        after = platform_compat.pread(output_fd, request, position)
        require(len(before) == request and len(after) == request,
                "short read during full copied-XISO comparison")
        source_hash.update(before)
        output_hash.update(after)
        overlap_start = max(position, absolute)
        overlap_end = min(position + request, target_end)
        if overlap_start >= overlap_end:
            require(before == after,
                    f"copied XISO changed outside target near 0x{position:x}")
        else:
            left_count = overlap_start - position
            right_start = overlap_end - position
            require(before[:left_count] == after[:left_count] and
                    before[right_start:] == after[right_start:],
                    f"copied XISO changed outside target near 0x{position:x}")
            for left, right in zip(
                before[left_count:right_start], after[left_count:right_start]
            ):
                different = left != right
                if different:
                    changed += 1
                    if not in_run:
                        runs += 1
                in_run = different
        position += request
    require(common.read_exact(output_fd, absolute, len(replacement)) == replacement,
            "copied XISO target span differs from compiled replacement")
    require(changed > 0, "copied XISO contains no bar_monitor change")
    return source_hash.hexdigest(), output_hash.hexdigest(), changed, runs


def validate_xiso_source(source_fd: int) -> tuple[dict[str, common.XdvdfsEntry], dict[str, int], common.XdvdfsEntry]:
    info = os.fstat(source_fd)
    # Identity is per-extent, never the whole container. The image size, the
    # sector a file landed on, and therefore its absolute byte offset are all
    # artifacts of how the disc was dumped or repacked -- extract-xiso
    # relocates every file. Pack C's and default.xbe's exact sizes and hashes
    # below are what actually identify this game, and gating on the container
    # refused legal dumps before they could run.
    require(stat.S_ISREG(info.st_mode), "source XISO must be a regular file")
    entries, directory = common.parse_xdvdfs(source_fd, info.st_size)
    pack = entries.get(PACK_PATH.casefold())
    xbe = entries.get("default.xbe")
    require(pack is not None and pack.size == PACK_SIZE, "pack C extent changed")
    require(xbe is not None and xbe.size == common.EXPECTED_XBE_SIZE,
            "default.xbe extent changed")
    assert pack is not None and xbe is not None
    require(common.sha256_fd(source_fd, pack.byte_offset, pack.size) == PACK_SHA256,
            "retail pack C hash changed")
    require(common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
            common.EXPECTED_XBE_SHA256, "retail default.xbe hash changed")
    absolute = pack.byte_offset + SPAN_PACK_OFFSET
    require(absolute + SPAN_SIZE <= pack.byte_offset + pack.size,
            "bar_monitor SCNE span does not lie inside pack C")
    require(common.sha256_fd(source_fd, pack.byte_offset + OUTER_PACK_OFFSET,
                             OUTER_SIZE) == OUTER_SHA256,
            "room aggregate identity changed")
    return entries, directory, pack


def build_xiso(source_path: Path, png_path: Path, output_path: Path,
               preview_path: Path, manifest_path: Path) -> dict[str, Any]:
    source, source_fd, source_identity = _open_regular_readonly(source_path, "source XISO")
    output = common.canonical_new_path(output_path)
    preview_out = common.canonical_new_path(preview_path)
    manifest_out = common.canonical_new_path(manifest_path)
    require(len({source, output, preview_out, manifest_out}) == 4,
            "source/output/preview/manifest paths must be distinct")
    require(not output.exists() and not preview_out.exists() and not manifest_out.exists(),
            "output XISO, preview, or manifest already exists")
    output_owned: common.OwnedFile | None = None
    preview_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    published: list[tuple[Path, tuple[int, int]]] = []
    success = False
    try:
        entries, directory, pack = validate_xiso_source(source_fd)
        source_size = os.fstat(source_fd).st_size
        source_sha_before = common.sha256_fd(source_fd)
        span_absolute = pack.byte_offset + SPAN_PACK_OFFSET
        source_span = common.read_exact(source_fd, span_absolute, SPAN_SIZE)
        png, png_payload, rgba = read_png(png_path)
        replacement, preview, compile_report = compile_replacement(source_span, rgba)
        require(common.path_identity(source) == source_identity,
                "source XISO pathname changed before copying")

        output_owned = reserve_staging(output, "xiso")
        require(common.fd_identity(output_owned.descriptor) != source_identity,
                "output XISO aliases source inode")
        copy_method = common.copy_fd_exact(
            source_fd, output_owned.descriptor, source_size
        )
        pwrite_all(output_owned.descriptor, span_absolute, replacement)
        os.fsync(output_owned.descriptor)
        require(common.owned_path_matches(output_owned),
                "output XISO pathname changed during build")
        require(common.path_identity(source) == source_identity,
                "source XISO pathname changed during build")
        source_sha, output_sha, changed, changed_runs = compare_images(
            source_fd, output_owned.descriptor, source_size,
            span_absolute, replacement,
        )
        require(source_sha == source_sha_before,
                "source XISO changed during build")
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_size
        )
        require(output_entries == entries and output_directory == directory,
                "copied XISO filesystem tree/layout changed")
        xbe = entries["default.xbe"]
        require(common.sha256_fd(output_owned.descriptor, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256, "copied XISO default.xbe changed")
        output_span = common.read_exact(output_owned.descriptor, span_absolute, SPAN_SIZE)
        output_decoded, _ = decode_chunk(
            output_span,
            resource_record(HEADER.unpack_from(output_span)[5]).as_chunk(),
        )
        _verify_scene(output_decoded, HEADER.unpack_from(output_span)[5], source=False)

        preview_owned = reserve_staging(preview_out, "preview")
        pwrite_all(preview_owned.descriptor, 0, preview)
        os.ftruncate(preview_owned.descriptor, len(preview))
        os.fsync(preview_owned.descriptor)
        require(common.owned_path_matches(preview_owned) and
                common.read_exact(preview_owned.descriptor, 0, len(preview)) == preview,
                "preview output write/readback changed")

        report: dict[str, Any] = {
            "schema": SCHEMA,
            "target": {
                "selector": SELECTOR,
                "asset_id": ASSET_ID,
                "scene": SCENE_NAME,
                "texture_index": TEXTURE_INDEX,
                "material": MATERIAL_NAME,
                "owning_shape": SHAPE_NAME,
                "owning_submesh_index": SUBMESH_INDEX,
                "width": 128,
                "height": 128,
                "format": "P8",
                "mip_levels": 5,
            },
            "source": {
                "path": str(source),
                "size": source_size,
                "sha256_before_and_after": source_sha,
                "opened_read_only": True,
                "modified": False,
            },
            "input_png": {
                "path": str(png),
                "file_name": png.name,
                "size": len(png_payload),
                "sha256": sha256(png_payload),
                "rgba_sha256": sha256(rgba),
                "strict_rgba8_noninterlaced": True,
            },
            "compile": compile_report,
            "output": {
                "path": str(output),
                "size": source_size,
                "sha256": output_sha,
                "copy_method": copy_method,
                "target_absolute_offset": span_absolute,
                "target_span_bytes": SPAN_SIZE,
                "changed_byte_count": changed,
                "changed_run_count": changed_runs,
                "all_differences_inside_selected_fixed_span": True,
                "xdvdfs_tree_and_layout_identical": True,
                "default_xbe_identical": True,
            },
            "preview": {
                "path": str(preview_out),
                "size": len(preview),
                "sha256": sha256(preview),
                "rgba_sha256": sha256(preview_rgba(preview)),
            },
            "safety": {
                "source_never_opened_writable": True,
                "failed_build_owned_outputs_removed": True,
                "partial_xiso_never_published_at_requested_path": True,
                "revert_route": "rebuild from the unchanged source XISO without this edit",
                "manifest_contains_retail_bytes": False,
                "public_tool_contains_retail_bytes": False,
                "runtime_visibility_proved": False,
            },
        }
        manifest_owned = reserve_staging(manifest_out, "manifest")
        payload = canonical_json(report)
        pwrite_all(manifest_owned.descriptor, 0, payload)
        os.ftruncate(manifest_owned.descriptor, len(payload))
        os.fsync(manifest_owned.descriptor)
        require(common.owned_path_matches(manifest_owned) and
                common.read_exact(manifest_owned.descriptor, 0, len(payload)) == payload,
                "manifest output write/readback changed")

        # Publish sidecars first and the verified XISO last. A hard interruption
        # can leave a hidden staging file, but never a partial requested XISO.
        published.append(publish_owned(preview_owned, preview_out))
        published.append(publish_owned(manifest_owned, manifest_out))
        published.append(publish_owned(output_owned, output))
        for owned in (preview_owned, manifest_owned, output_owned):
            common.unlink_if_owned(owned)
        success = True
        return report
    finally:
        os.close(source_fd)
        for owned in (output_owned, preview_owned, manifest_owned):
            if owned is not None:
                os.close(owned.descriptor)
        if not success:
            for path, identity in reversed(published):
                unlink_identity(path, identity)
            for owned in (manifest_owned, preview_owned, output_owned):
                common.unlink_if_owned(owned)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--preview", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = build_xiso(
            args.source_xiso, args.png, args.output_xiso,
            args.preview, args.manifest,
        )
    except (OSError, ValueError, KeyError, TypeError, struct.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "selector": SELECTOR,
        "output_xiso": report["output"]["path"],
        "output_sha256": report["output"]["sha256"],
        "preview": report["preview"]["path"],
        "runtime_visibility_proved": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ASSET_ID",
    "BarMonitorError",
    "SCHEMA",
    "SELECTOR",
    "build_xiso",
    "compile_replacement",
    "compare_images",
    "preview_rgba",
    "read_png",
    "validate_xiso_source",
]
