#!/usr/bin/env python3
"""Build a hash-pinned inventory of NFL 2K5 live player face/head assets."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
from typing import Any
import zlib

from nfl_outer import Entry, parse_archive, read_entry_range
from nfl_txtr import (COMPRESSED_SENTINEL, HEADER, Chunk, decode_chunk,
                      decode_dxt1, minimum_vc_lz_overlap_scratch,
                      parse_texture)
import nfl_uniform_color_xiso_direct_patch as xiso
from xbe_info import Xbe


SCHEMA = "nfl2k5_live_face_texture_compatibility/v1"
ROOT = Path(__file__).resolve().parents[1]
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
TXTR_INVENTORY_SHA256 = "5295168a4596b7be273e534b36efd2b53f44c7ed5f16893110a63413397f4929"
CHUNK_INVENTORY_SHA256 = "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"
XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
PACK_SHA256 = {
    "2": "21e00e0f41b3e016e416c44f3e1f3a07f9d5d7fdb5b9fe586685fadceb335886",
    "3": "921a139a9fd1a9470cc77f78455a6282e426376d4c201635b97a512d1f947aa7",
}
MATERIAL_TSV_SHA256 = "ac222dc0e773f1f09a1aa1e774858f2dd0e82de1a35b6bec154ff98208c0f040"
SUBMESH_TSV_SHA256 = "1ad92465a5ba6e94a78511b6533b61e5297caed1dbab49885cdb45f92ef048cc"
FACE_ID = re.compile(r"^[fhn](\d{4})$")
PF_FIRST = 1198
PF_LAST = 1821
F_OUTER = 3100
SELECTOR_COUNT = 624
DXT_BASE_BYTES = 32768
F_MIP_DIMENSIONS = tuple((256 >> level, 256 >> level) for level in range(6))
F_MIP_BYTES = tuple(((width + 3) // 4) * ((height + 3) // 4) * 8
                    for width, height in F_MIP_DIMENSIONS)
F_DXT_BYTES = sum(F_MIP_BYTES)


class CompatibilityError(ValueError):
    """Raised when any pinned identity or inferred relationship changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompatibilityError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def pin(path: Path, logical_path: str) -> dict[str, Any]:
    """Pin bytes while keeping private host paths out of retained evidence."""

    resolved = path.resolve(strict=True)
    return {"path": logical_path, "size": resolved.stat().st_size,
            "sha256": file_digest(resolved)}


def canonical_hash(value: object) -> str:
    return digest(json.dumps(value, sort_keys=True,
                             separators=(",", ":")).encode())


def resource_chunk(span: bytes, index: int = 0) -> Chunk:
    require(len(span) >= HEADER.size, "resource span is shorter than its wrapper")
    fields = HEADER.unpack_from(span)
    try:
        kind = fields[0].decode("ascii")
    except UnicodeDecodeError as exc:
        raise CompatibilityError("resource FourCC is not ASCII") from exc
    chunk = Chunk(index, 0, kind, *fields[1:])
    require(chunk.end_offset == len(span), "resource wrapper/span size mismatch")
    return chunk


def locate_range(entry: Entry, relative_offset: int, size: int) \
        -> list[dict[str, Any]]:
    require(relative_offset >= 0 and size > 0 and
            relative_offset + size <= entry.size, "range exceeds outer entry")
    remaining = size
    relative = relative_offset
    pieces = []
    for segment in entry.segments:
        if relative >= segment.size:
            relative -= segment.size
            continue
        take = min(remaining, segment.size - relative)
        pieces.append({
            "pack_ordinal": segment.pack_ordinal,
            "pack_name": segment.pack_name,
            "pack_offset": segment.pack_offset + relative,
            "size": take,
        })
        remaining -= take
        relative = 0
        if not remaining:
            break
    require(remaining == 0, "range-to-pack mapping is incomplete")
    return pieces


def utf16z(data: bytes, offset: int) -> str:
    require(0 <= offset < len(data), "UTF-16 string offset is out of range")
    end = None
    for position in range(offset, len(data) - 1, 2):
        if data[position:position + 2] == b"\0\0":
            end = position
            break
    require(end is not None, "UTF-16 string is unterminated")
    try:
        return data[offset:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise CompatibilityError("invalid UTF-16 string") from exc


def validate_xbe(path: Path) -> dict[str, Any]:
    require(file_digest(path) == XBE_SHA256, "default.xbe SHA-256 mismatch")
    image = Xbe(path)

    def read(address: int, size: int) -> bytes:
        offset = image.va_to_offset(address, size)
        return image.data[offset:offset + size]

    strings = {
        "f_format": (0x00E656B0, "f%04d"),
        "face_textures": (0x00E656BC, "FaceTextures"),
        "s_format": (0x00E656D8, "s%04d"),
        "face_shapes": (0x00E656E4, "FaceShapes"),
        "h_format": (0x00E656FC, "h%04d"),
        "n_format": (0x00E65708, "n%04d"),
        "pf_format": (0x00E793A8, "pf%04d.iff"),
        "low_face_textures": (0x00E62E5A, "LFaceTextures"),
        "ingame_faces": (0x00E62E78, "igfaces.iff"),
        "loader_face_shapes": (0x00E62E90, "FaceShapes"),
    }
    resolved = {}
    for key, (address, expected) in strings.items():
        actual = image.utf16z_va(address)
        require(actual == expected,
                f"XBE face string changed at 0x{address:08x}")
        resolved[key] = {"address": f"0x{address:08x}", "value": actual}

    material_names = {
        18: "SKIN_face", 19: "SKIN_skull", 20: "SKIN_eyegloss",
        21: "HI_eyeblack", 22: "SKIN_neck",
    }
    materials = {}
    for index, expected in material_names.items():
        pointer = struct.unpack("<I", read(0x004EEE68 + index * 4, 4))[0]
        actual = image.utf16z_va(pointer)
        require(actual == expected, f"XBE face material index {index} changed")
        materials[str(index)] = {"name": actual, "pointer": f"0x{pointer:08x}"}

    ranges = {
        "player_face_head_builder": (0x0008EFA0, 2116,
            "c65bb4dbabf5bae103d1b54c3624d96c8765a10e89f5e658dcbf5c07a779caa1"),
        "material_texture_writer": (0x0008E3F0, 64,
            "e1bc93ece080f679677f8608023d969dc7b14d6a6bb835b7e75bd222704ad908"),
        "shape_apply": (0x0008E7D0, 89,
            "63449f55265abd6c036c3bd7b59a046f8d7c90fcbc3d9cd00d775c62e1d0b744"),
        "global_lookup": (0x00042FF0, 104,
            "70ffab2672c97dcca199fa7d1503ad688820be27cc005eaedb76630211693e1f"),
        "context_lookup": (0x000449E0, 104,
            "710fd5ba9fd2a147042dd4c5f133cc2a8d36dcdc10b47417d17ec65df9b46191"),
        "player_face_prefetch": (0x0012F160, 915,
            "33144d179e2e9d8e18ee56d0969b048c476571e7388161b3f0b793c6f4a57283"),
        "face_registry_init": (0x00073EC0, 102,
            "930743b42c5fc052f09f3fc1c83ee1c287d47af745d420842053b5fb46af045a"),
    }
    functions = {}
    for key, (address, size, expected) in ranges.items():
        actual = digest(read(address, size))
        require(actual == expected, f"XBE function proof changed: {key}")
        functions[key] = {"address": f"0x{address:08x}", "size": size,
                          "sha256": actual}
    return {
        "sha256": XBE_SHA256,
        "selector_field": "player_record +0x06 unsigned 16-bit face/head ID",
        "strings": resolved,
        "material_pointer_table": "0x004EEE68",
        "materials": materials,
        "material_texture_pointer_field": "+0x30",
        "material_texture_writer_store": "0x0008E422",
        "function_ranges": functions,
        "binding": {
            "f####": ["SKIN_face", "SKIN_eyegloss", "HI_eyeblack(optional)"],
            "h####": ["SKIN_face", "SKIN_eyegloss", "HI_eyeblack(optional)"],
            "n####": ["SKIN_neck", "SKIN_skull"],
            "s####": ["SHAP applied by function 0x0008E7D0"],
            "prefetch_package": "pf%04d.iff",
            "fallback_formula": (
                "9001 + 100*((player_record[0x18]>>7)&7) + "
                "((player_record[0x20]>>17)&7)"
            ),
        },
    }


def validate_scene(material_path: Path, submesh_path: Path) -> dict[str, Any]:
    require(file_digest(material_path) == MATERIAL_TSV_SHA256,
            "scene material TSV SHA-256 mismatch")
    require(file_digest(submesh_path) == SUBMESH_TSV_SHA256,
            "scene submesh TSV SHA-256 mismatch")
    wanted = {"SKIN_face", "SKIN_skull", "SKIN_eyegloss", "HI_eyeblack",
              "SKIN_neck"}
    with material_path.open(newline="", encoding="utf-8") as stream:
        material_rows = [row for row in csv.DictReader(stream, delimiter="\t")
                         if row["scene_name"] in {"hi_head", "lo_body"} and
                         row["material_name"] in wanted]
    with submesh_path.open(newline="", encoding="utf-8") as stream:
        submesh_rows = [row for row in csv.DictReader(stream, delimiter="\t")
                        if row["scene_name"] in {"hi_head", "lo_body"} and
                        row["material_name"] in wanted]
    material_counts = Counter((row["scene_name"], row["material_name"])
                              for row in material_rows)
    submesh_counts = Counter((row["scene_name"], row["material_name"])
                             for row in submesh_rows)
    expected = {
        ("lo_body", "SKIN_face"), ("lo_body", "SKIN_neck"),
        ("hi_head", "SKIN_face"), ("hi_head", "SKIN_skull"),
        ("hi_head", "SKIN_eyegloss"), ("hi_head", "HI_eyeblack"),
        ("hi_head", "SKIN_neck"),
    }
    require(set(material_counts) == expected and
            all(material_counts[key] == 1 for key in expected) and
            all(submesh_counts[key] > 0 for key in expected),
            "shared player scene face/head materials changed")
    return {
        "material_rows": len(material_rows), "submesh_rows": len(submesh_rows),
        "material_counts": {f"{scene}/{name}": material_counts[(scene, name)]
                            for scene, name in sorted(expected)},
        "submesh_counts": {f"{scene}/{name}": submesh_counts[(scene, name)]
                           for scene, name in sorted(expected)},
        "interpretation": (
            "hi_head/lo_body contain indexed geometry for the proved material names; "
            "their texture pointer fields are filled by the player builder"
        ),
    }


def run(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    index_path = root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
    txtr_path = root / "reports/assets/nfl2k5_all_txtr_inventory_v2.json"
    chunks_path = root / "reports/assets/nfl2k5_resource_chunks_v2.json"
    xbe_path = root / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
    source_path = root / "ESPN NFL 2K5 (USA).xiso.iso"
    material_path = root / "reports/assets/nfl2k5_scne_material_textures.tsv"
    submesh_path = root / "reports/assets/nfl2k5_scne_submeshes.tsv"
    require(file_digest(index_path) == INDEX_SHA256, "canonical index hash mismatch")
    require(file_digest(txtr_path) == TXTR_INVENTORY_SHA256,
            "TXTR inventory hash mismatch")
    require(file_digest(chunks_path) == CHUNK_INVENTORY_SHA256,
            "chunk inventory hash mismatch")
    xbe_evidence = validate_xbe(xbe_path)
    scene_evidence = validate_scene(material_path, submesh_path)

    txtr_value = json.loads(txtr_path.read_bytes())
    chunk_value = json.loads(chunks_path.read_bytes())
    require(txtr_value.get("schema") == "nfl2k5_all_txtr_inventory/v1" and
            chunk_value.get("schema") == "nfl2k5_resource_chunk_inventory/v1",
            "source inventory schema mismatch")
    live_textures = [row for row in txtr_value["textures"]
                     if FACE_ID.fullmatch(str(row["name"]))]
    by_name = {str(row["name"]): row for row in live_textures}
    require(len(live_textures) == SELECTOR_COUNT * 3 and
            len(by_name) == len(live_textures), "live f/h/n name coverage changed")
    id_sets = {family: {name[1:] for name in by_name if name.startswith(family)}
               for family in "fhn"}
    require(all(len(values) == SELECTOR_COUNT for values in id_sets.values()) and
            id_sets["f"] == id_sets["h"] == id_sets["n"],
            "f/h/n selector sets differ")
    face_ids = sorted(id_sets["f"])

    chunks = {(int(row["outer_index"]), int(row["chunk_index"])): row
              for row in chunk_value["chunks"]}
    archive = parse_archive(index_path)
    require(archive.entries[F_OUTER].name_id == 0x3C097D22,
            "FaceTextures aggregate outer identity changed")
    for name, expected in PACK_SHA256.items():
        pack = next(item for item in archive.packs if item.name == name)
        require(file_digest(pack.path) == expected,
                f"extracted pack {name} hash mismatch")

    source_info = source_path.lstat()
    require(stat.S_ISREG(source_info.st_mode) and not stat.S_ISLNK(source_info.st_mode),
            "source XISO must be a non-symlink regular file")
    source = source_path.resolve(strict=True)
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(source_fd)
        require((opened.st_dev, opened.st_ino, opened.st_size) ==
                (source_info.st_dev, source_info.st_ino, xiso.EXPECTED_XISO_SIZE),
                "source XISO identity/size changed")
        xdvdfs, _ = xiso.parse_xdvdfs(source_fd, opened.st_size)
        pack_records = {}
        for name, expected in PACK_SHA256.items():
            path = f"vc_53450030/{name}"
            record = xdvdfs.get(path.casefold())
            require(record is not None and
                    xiso.sha256_fd(source_fd, record.byte_offset, record.size) == expected,
                    f"source XISO pack {name} changed")
            assert record is not None
            pack_records[name] = {
                "path": path, "sector": record.sector,
                "byte_offset": record.byte_offset, "size": record.size,
                "sha256": expected,
            }

        resources = []
        shapes = []
        selectors = []
        layout_counts: Counter[str] = Counter()
        stored_sizes: dict[str, list[int]] = {family: [] for family in "fhn"}
        for face_id in face_ids:
            selector_resources = {}
            pf_outers = set()
            for family in "fhn":
                source_row = by_name[f"{family}{face_id}"]
                outer_index = int(source_row["outer_index"])
                chunk_index = int(source_row["chunk_index"])
                expected_outer = F_OUTER if family == "f" else outer_index
                require(outer_index == expected_outer and
                        (family == "f" or PF_FIRST <= outer_index <= PF_LAST),
                        f"{family}{face_id} outer ownership changed")
                item = chunks[(outer_index, chunk_index)]
                require(item["kind"] == "TXTR" and
                        int(item["chunk_offset"]) == int(source_row["chunk_offset"]),
                        f"{family}{face_id} chunk inventory differs")
                entry = archive.entries[outer_index]
                span_size = HEADER.size + int(item["stored_size"])
                span = read_entry_range(archive, entry, int(item["chunk_offset"]),
                                        span_size)
                chunk = resource_chunk(span, chunk_index)
                decoded, decode_info = decode_chunk(span, chunk)
                texture = parse_texture(decoded, chunk)
                require(texture.name == f"{family}{face_id}" and
                        texture.name_offset == 32 and texture.descriptor_offset == 44 and
                        texture.pixel_offset == 0 and texture.palette_offset == 0 and
                        texture.packed_size == 0 and
                        texture.descriptor_flags == 0x80000000 and
                        texture.dimensions == 2 and texture.format_name == "DXT1" and
                        texture.width == 256 and texture.height == 256 and
                        texture.depth == 1 and
                        digest(decoded) == source_row["decoded_sha256"],
                        f"{family}{face_id} TXTR descriptor/hash changed")
                if family == "f":
                    require(chunk.compression_magic == 0 and chunk.system_bytes == 128 and
                            chunk.video_bytes == 43712 and chunk.stored_size == 43840 and
                            texture.packed_format == 0x08860C29 and
                            texture.mip_levels == 6 and decode_info is None and
                            len(decoded) == 43840 and F_DXT_BYTES == 43680 and
                            decoded[128 + F_DXT_BYTES:] == bytes(32),
                            f"f{face_id} six-mip raw allocation changed")
                    post = read_entry_range(archive, entry,
                                            int(item["chunk_offset"]) + span_size, 32)
                    require(post == bytes(32), f"f{face_id} slot padding changed")
                    mip_dimensions = F_MIP_DIMENSIONS
                    mip_bytes = F_MIP_BYTES
                    lz = None
                else:
                    require(chunk.compression_magic == COMPRESSED_SENTINEL and
                            chunk.system_bytes == 128 and chunk.video_bytes == 32768 and
                            texture.packed_format == 0x08810C29 and
                            texture.mip_levels == 1 and decode_info is not None and
                            len(decoded) == 32896,
                            f"{family}{face_id} compressed allocation changed")
                    exact_scratch = minimum_vc_lz_overlap_scratch(
                        span[HEADER.size:HEADER.size + decode_info.consumed_bytes],
                        chunk.stored_size, len(decoded))
                    require(chunk.overlap_scratch_bytes >= exact_scratch,
                            f"{family}{face_id} retail alias scratch is insufficient")
                    lz = {
                        "stream_tag": decode_info.stream_tag,
                        "offset_bits": decode_info.offset_bits,
                        "length_bits": decode_info.length_bits,
                        "consumed_bytes": decode_info.consumed_bytes,
                        "unused_bytes": chunk.stored_size - decode_info.consumed_bytes,
                        "retail_exact_minimum_overlap_scratch_bytes": exact_scratch,
                    }
                    mip_dimensions = ((256, 256),)
                    mip_bytes = (DXT_BASE_BYTES,)
                    pf_outers.add(outer_index)

                base_rgba = decode_dxt1(decoded[128:128 + DXT_BASE_BYTES], 256, 256)
                require(digest(base_rgba) == source_row["rgba_sha256"],
                        f"{family}{face_id} base-level decode changed")
                pieces = locate_range(entry, int(item["chunk_offset"]), span_size)
                require(len(pieces) == 1, f"{family}{face_id} crosses pack segments")
                piece = pieces[0]
                expected_pack = "3" if family == "f" else "2"
                require(piece["pack_name"] == expected_pack,
                        f"{family}{face_id} moved to another pack")
                pack = pack_records[expected_pack]
                absolute = int(pack["byte_offset"]) + int(piece["pack_offset"])
                require(os.pread(source_fd, span_size, absolute) == span,
                        f"{family}{face_id} source-XISO span differs")
                layout = {
                    "family_class": "f_six_mip_raw" if family == "f" else "hn_base_compressed",
                    "system_bytes": chunk.system_bytes,
                    "video_bytes": chunk.video_bytes,
                    "name_offset": texture.name_offset,
                    "descriptor_offset": texture.descriptor_offset,
                    "pixel_offset": texture.pixel_offset,
                    "packed_format": f"0x{texture.packed_format:08x}",
                    "format": "DXT1", "mip_levels": texture.mip_levels,
                    "mip_dimensions": [list(value) for value in mip_dimensions],
                    "mip_bytes": list(mip_bytes), "linear_dxt_blocks": True,
                }
                layout_signature = canonical_hash(layout)
                layout_counts[layout_signature] += 1
                stored_sizes[family].append(chunk.stored_size)
                logical_outer = "FaceTextures aggregate" if family == "f" \
                    else f"pf{face_id}.iff"
                row = {
                    "face_id": face_id, "family": family,
                    "resource_name": f"{family}{face_id}",
                    "outer_logical_name": logical_outer,
                    "outer_index": outer_index,
                    "outer_id": f"0x{entry.name_id:08x}",
                    "outer_size": entry.size,
                    "chunk_index": chunk_index,
                    "chunk_offset": int(item["chunk_offset"]),
                    "stored_size": chunk.stored_size,
                    "span_size": span_size,
                    "system_bytes": chunk.system_bytes,
                    "video_bytes": chunk.video_bytes,
                    "decoded_size": len(decoded),
                    "compressed": chunk.compressed,
                    "compression_magic": f"0x{chunk.compression_magic:08x}",
                    "overlap_scratch_bytes": chunk.overlap_scratch_bytes,
                    "name_offset": texture.name_offset,
                    "descriptor_offset": texture.descriptor_offset,
                    "pixel_offset": texture.pixel_offset,
                    "palette_offset": texture.palette_offset,
                    "packed_format": f"0x{texture.packed_format:08x}",
                    "descriptor_flags": f"0x{texture.descriptor_flags:08x}",
                    "format": "DXT1", "width": 256, "height": 256,
                    "mip_levels": texture.mip_levels,
                    "mip_dimensions": [list(value) for value in mip_dimensions],
                    "mip_bytes": list(mip_bytes),
                    "trailing_video_zero_bytes": 32 if family == "f" else 0,
                    "post_span_slot_zero_bytes": 32 if family == "f" else 0,
                    "system_sha256": digest(decoded[:128]),
                    "video_sha256": digest(decoded[128:]),
                    "decoded_sha256": digest(decoded),
                    "base_rgba_sha256": digest(base_rgba),
                    "span_sha256": digest(span),
                    "layout_signature_sha256": layout_signature,
                    "lz": lz,
                    "span_segments": pieces,
                    "xiso_pack_path": pack["path"],
                    "xiso_pack_sector": pack["sector"],
                    "xiso_pack_byte_offset": pack["byte_offset"],
                    "xiso_pack_size": pack["size"],
                    "xiso_pack_sha256": pack["sha256"],
                    "xiso_absolute_span_offset": absolute,
                    "source_xiso_span_matches": True,
                    "fixed_span_png_importer_compatible": True,
                }
                selector_resources[family] = len(resources)
                resources.append(row)

            require(len(pf_outers) == 1, f"pf{face_id}.iff h/n ownership differs")
            pf_outer = next(iter(pf_outers))
            entry = archive.entries[pf_outer]
            expected_name = f"pf{face_id}.iff"
            expected_id = zlib.crc32(expected_name.upper().encode("utf-16le")) & 0xFFFFFFFF
            require(entry.name_id == expected_id,
                    f"{expected_name} CRC32 filename identity changed")
            shape_item = chunks[(pf_outer, 2)]
            require(shape_item["kind"] == "SHAP", f"{expected_name} chunk 2 is not SHAP")
            shape_span = read_entry_range(
                archive, entry, int(shape_item["chunk_offset"]),
                HEADER.size + int(shape_item["stored_size"]))
            shape_chunk = resource_chunk(shape_span, 2)
            shape_body, shape_info = decode_chunk(shape_span, shape_chunk)
            shape_name = utf16z(shape_body, 32)
            require(not shape_chunk.compressed and shape_info is None and
                    shape_name == f"s{face_id}" and
                    int(shape_item["chunk_offset"]) + len(shape_span) == entry.size,
                    f"{expected_name} shape identity/layout changed")
            shape_piece = locate_range(entry, int(shape_item["chunk_offset"]),
                                       len(shape_span))
            require(len(shape_piece) == 1 and shape_piece[0]["pack_name"] == "2",
                    f"s{face_id} crosses pack segments")
            shape_absolute = (int(pack_records["2"]["byte_offset"]) +
                              int(shape_piece[0]["pack_offset"]))
            require(os.pread(source_fd, len(shape_span), shape_absolute) == shape_span,
                    f"s{face_id} source-XISO span differs")
            shape_index = len(shapes)
            shapes.append({
                "face_id": face_id, "resource_name": shape_name,
                "outer_logical_name": expected_name, "outer_index": pf_outer,
                "outer_id": f"0x{entry.name_id:08x}", "outer_size": entry.size,
                "filename_crc32_utf16le_upper_verified": True,
                "chunk_index": 2, "chunk_offset": int(shape_item["chunk_offset"]),
                "stored_size": shape_chunk.stored_size,
                "span_size": len(shape_span), "system_word": shape_chunk.system_bytes,
                "span_sha256": digest(shape_span), "body_sha256": digest(shape_body),
                "span_segments": shape_piece,
                "xiso_pack_path": pack_records["2"]["path"],
                "xiso_absolute_span_offset": shape_absolute,
                "source_xiso_span_matches": True,
                "png_import_supported": False,
                "portme": "PORTME: SHAP geometry editing is not implemented.",
            })
            selectors.append({
                "face_id": face_id, "generic_fallback": int(face_id) >= 9000,
                "pf_outer_index": pf_outer, "pf_logical_name": expected_name,
                "resource_row_indices": selector_resources,
                "shape_row_index": shape_index,
            })
    finally:
        os.close(source_fd)

    family_counts = Counter(row["family"] for row in resources)
    pf_outer_indices = {int(row["pf_outer_index"]) for row in selectors}
    require(len(resources) == SELECTOR_COUNT * 3 and len(shapes) == SELECTOR_COUNT and
            len(selectors) == SELECTOR_COUNT and
            family_counts == Counter({"f": 624, "h": 624, "n": 624}) and
            pf_outer_indices == set(range(PF_FIRST, PF_LAST + 1)) and
            len(layout_counts) == 2, "final live face corpus coverage changed")
    generic = [value for value in face_ids if int(value) >= 9000]
    expected_generic = [f"{prefix}{suffix:02d}" for prefix in range(90, 96)
                        for suffix in range(1, 8)]
    require(generic == expected_generic, "generic fallback selector set changed")

    all_textures = txtr_value["textures"]
    distinction = {
        "live_f_h_n_texture_count": len(resources),
        "portrait_photo_texture_count": sum(
            re.fullmatch(r"\d\d_photo_\d\d?", str(row["name"])) is not None
            for row in all_textures),
        "team_select_unif_helm_card_texture_count": sum(
            str(row["name"]).startswith(("unif_", "helm_")) for row in all_textures),
        "crowd_head_texture_count": sum(
            re.fullmatch(r"head0[1-8]", str(row["name"]), re.IGNORECASE) is not None
            for row in all_textures),
        "referee_face_names": sorted({str(row["name"]) for row in all_textures
                                      if str(row["name"]).startswith("rface_")}),
        "h0000_iff_through_h0096_iff": (
            "outer Hilt/Highlight resources; unrelated to h#### TXTR chunks inside pf####.iff"
        ),
    }
    require(distinction["portrait_photo_texture_count"] == 128 and
            distinction["team_select_unif_helm_card_texture_count"] == 1902 and
            distinction["crowd_head_texture_count"] == 2550 and
            distinction["referee_face_names"] == ["rface_00", "rface_02"],
            "menu/crowd/referee distinction counts changed")

    report = {
        "schema": SCHEMA,
        "inputs": {
            "canonical_index": pin(index_path, "user-source/vc_53450030/0"),
            "txtr_inventory": pin(
                txtr_path, "generation-evidence/nfl2k5_all_txtr_inventory_v2.json"
            ),
            "chunk_inventory": pin(
                chunks_path, "generation-evidence/nfl2k5_resource_chunks_v2.json"
            ),
            "default_xbe": pin(xbe_path, "user-source/default.xbe"),
            "scene_materials": pin(
                material_path, "generation-evidence/nfl2k5_scne_material_textures.tsv"
            ),
            "scene_submeshes": pin(
                submesh_path, "generation-evidence/nfl2k5_scne_submeshes.tsv"
            ),
            "retail_xiso": {
                "path": "user-source/ESPN NFL 2K5.xiso.iso",
                "size": xiso.EXPECTED_XISO_SIZE,
                "expected_sha256": xiso.EXPECTED_XISO_SHA256,
                "opened_read_only": True,
            },
            "packs": pack_records,
        },
        "summary": {
            "selector_count": SELECTOR_COUNT, "custom_selector_count": 582,
            "generic_fallback_selector_count": 42,
            "f_texture_count": family_counts["f"],
            "h_texture_count": family_counts["h"],
            "n_texture_count": family_counts["n"],
            "shape_count": len(shapes), "texture_resource_count": len(resources),
            "total_linked_resource_count": len(resources) + len(shapes),
            "f_h_n_s_sets_identical": True,
            "pf_outer_first": PF_FIRST, "pf_outer_last": PF_LAST,
            "pf_outer_count": PF_LAST - PF_FIRST + 1,
            "f_outer_index": F_OUTER, "f_outer_id": "0x3c097d22",
            "layout_class_count": len(layout_counts),
            "layout_signature_counts": dict(sorted(layout_counts.items())),
            "stored_size_ranges": {
                family: {"minimum": min(values), "maximum": max(values),
                         "allocation_count": len(set(values))}
                for family, values in stored_sizes.items()
            },
            "all_spans_single_pack_segment": True,
            "all_source_xiso_spans_match": True,
            "all_compressed_retail_alias_guards_valid": True,
            "all_filename_ids_match_crc32_upper_utf16le": True,
        },
        "layout_contracts": {
            "f": {
                "format": "DXT1", "width": 256, "height": 256,
                "mip_levels": 6, "mip_dimensions": [list(v) for v in F_MIP_DIMENSIONS],
                "mip_bytes": list(F_MIP_BYTES), "dxt_chain_bytes": F_DXT_BYTES,
                "system_bytes": 128, "video_bytes": 43712,
                "trailing_video_zero_bytes": 32, "fixed_span_bytes": 43872,
                "compression": "raw", "post_span_slot_zero_bytes": 32,
            },
            "h_n": {
                "format": "DXT1", "width": 256, "height": 256,
                "mip_levels": 1, "dxt_bytes": DXT_BASE_BYTES,
                "system_bytes": 128, "video_bytes": 32768,
                "decoded_bytes": 32896, "compression": "VC-LZ FEEDBEEF",
                "fixed_stored_allocation_per_target": True,
            },
            "dxt_block_order": "linear row-major; no Xbox swizzle step",
        },
        "xbe_live_binding": xbe_evidence,
        "shared_player_scene_binding": scene_evidence,
        "asset_family_distinction": distinction,
        "generic_fallback_face_ids": generic,
        "selectors": selectors,
        "resources": resources,
        "shapes": shapes,
        "claims": {
            "actual_live_3d_player_face_head_resources": True,
            "portrait_or_menu_cards_modified": False,
            "offline_fixed_span_png_import_feasible_for_f_h_n": True,
            "shape_geometry_import_implemented": False,
            "originals_modified": False, "xemu_started": False,
            "title_executed": False, "runtime_visibility_proved": False,
            "portme": [
                "PORTME(SHAP): decode and author s#### head geometry/morph data.",
                "PORTME(runtime): capture a close-up in an emulator before claiming visibility.",
                "PORTME(roster): map each roster slot to player_record +0x06 and document fallback use.",
            ],
        },
    }
    return report, resources


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "face_id", "family", "resource_name", "outer_logical_name", "outer_index",
        "outer_id", "outer_size", "chunk_index", "chunk_offset", "stored_size",
        "span_size", "system_bytes", "video_bytes", "decoded_size", "compressed",
        "overlap_scratch_bytes", "name_offset", "descriptor_offset", "packed_format",
        "mip_levels", "system_sha256", "video_sha256", "decoded_sha256",
        "base_rgba_sha256", "span_sha256", "layout_signature_sha256", "pack_name",
        "pack_offset", "xiso_absolute_span_offset", "lz_stream_tag", "lz_offset_bits",
        "lz_consumed_bytes", "lz_unused_bytes",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            lz = row["lz"] or {}
            piece = row["span_segments"][0]
            writer.writerow({
                **{field: row.get(field, "") for field in fields},
                "pack_name": piece["pack_name"], "pack_offset": piece["pack_offset"],
                "lz_stream_tag": lz.get("stream_tag", ""),
                "lz_offset_bits": lz.get("offset_bits", ""),
                "lz_consumed_bytes": lz.get("consumed_bytes", ""),
                "lz_unused_bytes": lz.get("unused_bytes", ""),
            })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", type=Path,
                        default=ROOT / "reports/assets/nfl2k5_live_face_texture_compatibility.json")
    parser.add_argument("--tsv", type=Path,
                        default=ROOT / "reports/assets/nfl2k5_live_face_texture_compatibility.tsv")
    args = parser.parse_args()
    try:
        report, rows = run(args.root.resolve(strict=True))
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        write_tsv(args.tsv, rows)
        print(
            "NFL_LIVE_FACE_TEXTURE_COMPATIBILITY_OK "
            f"selectors={report['summary']['selector_count']} "
            f"textures={report['summary']['texture_resource_count']} "
            f"shapes={report['summary']['shape_count']} runtime=false xemu_started=false"
        )
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
