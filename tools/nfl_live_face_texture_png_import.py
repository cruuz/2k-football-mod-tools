#!/usr/bin/env python3
"""Fail-closed PNG importer for NFL 2K5 live f####/h####/n#### TXTRs."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from nfl_dxt1 import Dxt1Error, encode_dxt1_opaque
from nfl_live_face_texture_targets import (DEFAULT_REPORT, FaceTarget,
                                            select_target)
from nfl_outer import parse_archive, read_entry_range
from nfl_txtr import (HEADER, Chunk, decode_chunk, decode_dxt1, encode_rgba_png,
                      minimum_vc_lz_overlap_scratch, parse_texture,
                      rebuild_compressed_chunk_fixed_span)
import nfl_tset_png_import as png_tools


SCHEMA = "nfl2k5_live_face_texture_png_import/v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
INDEX_SIZE = 193_710_080
BASE_SIZE = 256
F_MIP_DIMENSIONS = tuple((BASE_SIZE >> level, BASE_SIZE >> level)
                         for level in range(6))
F_MIP_BYTES = tuple(((width + 3) // 4) * ((height + 3) // 4) * 8
                    for width, height in F_MIP_DIMENSIONS)
MAX_PNG_BYTES = 32 * 1024 * 1024


class ImportFailure(ValueError):
    """Raised before output when an input or fixed allocation fails closed."""


@dataclass(frozen=True)
class Mip:
    level: int
    width: int
    height: int
    rgba: bytes


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ImportFailure(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def difference_runs(before: bytes, after: bytes) -> list[list[int]]:
    require(len(before) == len(after), "difference inputs have unequal size")
    result: list[list[int]] = []
    for offset, (left, right) in enumerate(zip(before, after)):
        if left == right:
            continue
        if not result or offset != result[-1][1] + 1:
            result.append([offset, offset])
        else:
            result[-1][1] = offset
    return result


def open_read_regular(path: Path, maximum: int, label: str) -> tuple[Path, bytes]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(descriptor)
        require((opened.st_dev, opened.st_ino) ==
                (supplied.st_dev, supplied.st_ino) and opened.st_size <= maximum,
                f"{label} identity/type/size changed")
        blocks = []
        remaining = opened.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            require(bool(block), f"short {label} read")
            blocks.append(block)
            remaining -= len(block)
        require(not os.read(descriptor, 1), f"{label} grew while reading")
        payload = b"".join(blocks)
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                f"{label} changed while reading")
        return resolved, payload
    finally:
        os.close(descriptor)


def read_png(path: Path) -> tuple[Path, bytes, bytes]:
    resolved, payload = open_read_regular(path, MAX_PNG_BYTES, "input PNG")
    width, height, rgba = png_tools.decode_rgba_png(payload, (BASE_SIZE, BASE_SIZE))
    require(width == BASE_SIZE and height == BASE_SIZE and
            len(rgba) == BASE_SIZE * BASE_SIZE * 4,
            "input PNG is not exact 256x256 RGBA8")
    require(all(rgba[offset] == 255 for offset in range(3, len(rgba), 4)),
            "live face/head PNG must be fully opaque")
    return resolved, payload, rgba


def generate_mips(rgba: bytes, levels: int) -> list[Mip]:
    require(levels in {1, 6} and len(rgba) == BASE_SIZE * BASE_SIZE * 4,
            "mip request/base RGBA size mismatch")
    result = [Mip(0, BASE_SIZE, BASE_SIZE, rgba)]
    current = rgba
    width = height = BASE_SIZE
    for level in range(1, levels):
        next_width, next_height = width // 2, height // 2
        downsampled = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            for x in range(next_width):
                sources = (
                    ((y * 2) * width + x * 2) * 4,
                    ((y * 2) * width + x * 2 + 1) * 4,
                    (((y * 2) + 1) * width + x * 2) * 4,
                    (((y * 2) + 1) * width + x * 2 + 1) * 4,
                )
                target = (y * next_width + x) * 4
                for channel in range(4):
                    downsampled[target + channel] = (
                        sum(current[source + channel] for source in sources) + 2
                    ) // 4
        current = bytes(downsampled)
        width, height = next_width, next_height
        result.append(Mip(level, width, height, current))
    expected = F_MIP_DIMENSIONS if levels == 6 else ((256, 256),)
    require(tuple((mip.width, mip.height) for mip in result) == expected,
            "generated mip dimensions differ from the proved chain")
    return result


def as_chunk(target: FaceTarget, overlap_scratch: int | None = None) -> Chunk:
    return Chunk(
        0, 0, "TXTR", target.stored_size, target.system_bytes,
        target.video_bytes, target.compression_magic,
        target.overlap_scratch_bytes if overlap_scratch is None else overlap_scratch,
        0, 0,
    )


def validate_texture(decoded: bytes, target: FaceTarget) -> object:
    texture = parse_texture(decoded, as_chunk(target))
    expected_packed = 0x08860C29 if target.family == "f" else 0x08810C29
    expected_mips = 6 if target.family == "f" else 1
    require(texture.name == target.resource_name and texture.name_offset == 32 and
            texture.descriptor_offset == 44 and texture.pixel_offset == 0 and
            texture.palette_offset == 0 and texture.packed_format == expected_packed and
            texture.packed_size == 0 and texture.descriptor_flags == 0x80000000 and
            texture.format_name == "DXT1" and texture.mip_levels == expected_mips and
            texture.width == 256 and texture.height == 256 and texture.depth == 1,
            "live face/head TXTR descriptor changed")
    return texture


def load_template(index_path: Path, target: FaceTarget) \
        -> tuple[Path, bytes, bytes, object | None]:
    supplied = index_path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "canonical index must be a non-symlink regular file")
    index = index_path.resolve(strict=True)
    info = index.stat(follow_symlinks=False)
    require((info.st_dev, info.st_ino, info.st_size) ==
            (supplied.st_dev, supplied.st_ino, INDEX_SIZE) and
            file_digest(index) == INDEX_SHA256,
            "canonical index size/path/hash changed")
    archive = parse_archive(index)
    entry = archive.entries[target.outer_index]
    require(entry.name_id == target.outer_id and entry.size == target.outer_size,
            "selected outer package changed")
    span = read_entry_range(archive, entry, target.chunk_offset, target.span_size)
    require(len(span) == target.span_size and digest(span) == target.span_sha256 and
            HEADER.unpack_from(span) == target.complete_header,
            "retail target span/header changed")
    decoded, decode_info = decode_chunk(span, as_chunk(target))
    require(len(decoded) == target.decoded_size and
            digest(decoded) == target.decoded_sha256 and
            digest(decoded[:128]) == target.system_sha256 and
            digest(decoded[128:]) == target.video_sha256,
            "retail target decoded identity changed")
    validate_texture(decoded, target)
    base_rgba = decode_dxt1(decoded[128:128 + 32768], 256, 256)
    require(digest(base_rgba) == target.base_rgba_sha256,
            "retail base-level DXT1 decode changed")
    if target.family == "f":
        require(decode_info is None and decoded[-32:] == bytes(32) and
                read_entry_range(archive, entry,
                                 target.chunk_offset + target.span_size, 32) == bytes(32),
                "f target raw tail/slot padding changed")
    else:
        require(decode_info is not None and
                decode_info.stream_tag == target.stream_tag and
                decode_info.offset_bits == target.offset_bits and
                decode_info.consumed_bytes == target.lz_consumed_bytes and
                target.stored_size - decode_info.consumed_bytes == target.lz_unused_bytes,
                "retail h/n compressed stream identity changed")
        exact = minimum_vc_lz_overlap_scratch(
            span[HEADER.size:HEADER.size + decode_info.consumed_bytes],
            target.stored_size, target.decoded_size)
        require(exact == target.retail_exact_minimum_overlap_scratch_bytes and
                target.overlap_scratch_bytes >= exact,
                "retail h/n alias-scratch proof changed")
    return index, span, decoded, decode_info


def build_import(index_path: Path, compatibility_path: Path, face_id: str,
                 family: str, png_path: Path) \
        -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any]]:
    compatibility, _, compatibility_payload, target = select_target(
        face_id, family, compatibility_path)
    index, template_span, template_decoded, template_info = load_template(
        index_path, target)
    png, png_payload, rgba = read_png(png_path)
    mips = generate_mips(rgba, target.mip_levels)

    encoded_levels = []
    dxt_rows = []
    decoded_levels = []
    for mip in mips:
        encoded, encode_info = encode_dxt1_opaque(mip.rgba, mip.width, mip.height)
        decoded_rgba = decode_dxt1(encoded, mip.width, mip.height)
        require(len(encoded) == ((mip.width + 3) // 4) *
                ((mip.height + 3) // 4) * 8 and
                all(decoded_rgba[offset] == 255
                    for offset in range(3, len(decoded_rgba), 4)),
                f"DXT1 level {mip.level} round-trip layout changed")
        encoded_levels.append(encoded)
        decoded_levels.append(Mip(mip.level, mip.width, mip.height, decoded_rgba))
        dxt_rows.append({
            **asdict(encode_info), "level": mip.level,
            "input_rgba_sha256": digest(mip.rgba),
            "encoded_sha256": digest(encoded),
            "decoded_rgba_sha256": digest(decoded_rgba),
        })
    dxt_chain = b"".join(encoded_levels)
    expected_dxt_bytes = 43680 if target.family == "f" else 32768
    require(len(dxt_chain) == expected_dxt_bytes,
            "encoded DXT1 chain does not fill the proved pixel allocation")
    video = dxt_chain + (bytes(32) if target.family == "f" else b"")
    require(len(video) == target.video_bytes, "rebuilt video allocation changed")
    rebuilt_decoded = template_decoded[:128] + video
    require(len(rebuilt_decoded) == target.decoded_size and
            rebuilt_decoded[:128] == template_decoded[:128],
            "rebuilt decoded/system allocation changed")
    validate_texture(rebuilt_decoded, target)

    if target.family == "f":
        rebuilt_span = template_span[:HEADER.size] + rebuilt_decoded
        require(len(rebuilt_span) == target.span_size and
                rebuilt_span[:HEADER.size + 128] ==
                template_span[:HEADER.size + 128] and
                rebuilt_span[-32:] == bytes(32),
                "raw f fixed-span rebuild escaped its video allocation")
        rebuild_record: dict[str, Any] = {
            "mode": "raw_fixed_span", "span_size": len(rebuilt_span),
            "wrapper_preserved": True, "system_bytes_preserved": True,
            "trailing_video_zero_bytes_preserved": True,
            "post_span_slot_zero_bytes_not_included_and_untouched": 32,
        }
        roundtrip = rebuilt_span[HEADER.size:]
        roundtrip_info = None
    else:
        rebuilt_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
            template_span, rebuilt_decoded)
        rebuilt_header = HEADER.unpack_from(rebuilt_span)
        require(rebuilt_header[:5] == target.complete_header[:5] and
                rebuilt_header[6:] == target.complete_header[6:] and
                rebuilt_header[5] >= target.overlap_scratch_bytes and
                len(rebuilt_span) == target.span_size and
                rebuild_info.loader_in_place_end_guard and
                rebuild_info.loader_in_place_alias_guard,
                "compressed h/n fixed-span rebuild changed its contract")
        rebuilt_chunk = as_chunk(target, rebuilt_header[5])
        roundtrip, roundtrip_info = decode_chunk(rebuilt_span, rebuilt_chunk)
        require(roundtrip_info is not None and roundtrip == rebuilt_decoded and
                roundtrip_info.consumed_bytes == rebuild_info.recompressed_bytes,
                "compressed h/n independent round trip failed")
        rebuild_record = {"mode": "vc_lz_fixed_span", **asdict(rebuild_info)}

    require(roundtrip == rebuilt_decoded, "rebuilt decoded bytes changed on round trip")
    position = 128
    for encoded, decoded_level in zip(encoded_levels, decoded_levels):
        require(roundtrip[position:position + len(encoded)] == encoded and
                decode_dxt1(roundtrip[position:position + len(encoded)],
                            decoded_level.width, decoded_level.height) ==
                decoded_level.rgba,
                f"rebuilt DXT1 level {decoded_level.level} differs")
        position += len(encoded)
    runs = difference_runs(template_span, rebuilt_span)
    require(runs, "input PNG produced a byte-identical retail target")
    changed = sum(end - start + 1 for start, end in runs)
    minimum_change = HEADER.size + 128 if target.family == "f" else 0x14
    require(all(start >= minimum_change for start, _ in runs),
            "rebuilt differences escaped allowed wrapper/video bytes")

    previews = []
    preview_rows = []
    for mip in decoded_levels:
        name = f"mip{mip.level}_{mip.width}x{mip.height}.png"
        payload = encode_rgba_png(mip.width, mip.height, mip.rgba)
        require(png_tools.decode_rgba_png(payload, (mip.width, mip.height)) ==
                (mip.width, mip.height, mip.rgba),
                f"generated preview failed strict reparse: {name}")
        previews.append((name, payload))
        preview_rows.append({
            "level": mip.level, "width": mip.width, "height": mip.height,
            "file_name": name, "png_sha256": digest(payload),
            "rgba_sha256": digest(mip.rgba), "strictly_reparsed": True,
        })

    target_record = asdict(target)
    target_record["outer_id"] = f"0x{target.outer_id:08x}"
    target_record["compression_magic"] = f"0x{target.compression_magic:08x}"
    report = {
        "schema": SCHEMA,
        "canonical_index": {"path": str(index), "size": INDEX_SIZE,
                            "sha256": INDEX_SHA256},
        "compatibility_report": {"path": str(compatibility),
                                 "sha256": digest(compatibility_payload)},
        "target": target_record,
        "input_png": {
            "path": str(png), "file_name": png.name, "size": len(png_payload),
            "sha256": digest(png_payload), "width": 256, "height": 256,
            "rgba_sha256": digest(rgba), "strict_rgba8_noninterlaced": True,
            "all_alpha_255": True,
        },
        "template": {
            "span_sha256": digest(template_span),
            "decoded_sha256": digest(template_decoded),
            "system_sha256": digest(template_decoded[:128]),
            "lz_consumed_bytes": (None if template_info is None
                                   else template_info.consumed_bytes),
        },
        "mips": {
            "filter": "unpremultiplied_rgba_2x2_box_round_nearest",
            "level_count": len(mips),
            "dimensions": [[mip.width, mip.height] for mip in mips],
            "encoded_bytes": [len(value) for value in encoded_levels],
            "linear_dxt_blocks_no_swizzle": True,
        },
        "dxt1": {
            "encoder": "deterministic_opaque_unique_rgb565_pair_search",
            "lossy": True, "levels": dxt_rows,
            "chain_bytes": len(dxt_chain), "chain_sha256": digest(dxt_chain),
            "independent_decoder_roundtrip_verified": True,
        },
        "rebuild": {
            **rebuild_record, "span_sha256": digest(rebuilt_span),
            "decoded_roundtrip_sha256": digest(roundtrip),
            "changed_byte_count": changed, "changed_run_count": len(runs),
            "changed_runs": runs, "fixed_span_fit": True,
        },
        "previews": preview_rows,
        "claims": {
            "actual_live_3d_face_head_resource": True,
            "portrait_or_menu_card_modified": False,
            "fixed_span_only": True, "originals_modified": False,
            "xiso_created": False, "xemu_started": False,
            "title_executed": False, "runtime_visibility_proved": False,
            "shape_geometry_modified": False,
            "portme": "PORTME(runtime): capture the selected player before claiming visibility.",
        },
    }
    return rebuilt_span, previews, report


def create_file(path: Path, payload: bytes) -> tuple[int, int]:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0), 0o644)
    opened = os.fstat(descriptor)
    identity = (opened.st_dev, opened.st_ino)
    success = False
    try:
        offset = 0
        while offset < len(payload):
            amount = os.write(descriptor, payload[offset:])
            require(amount > 0, "short output write")
            offset += amount
        os.fsync(descriptor)
        current = path.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (identity[0], identity[1], len(payload)),
                "output pathname/size changed")
        success = True
        return identity
    finally:
        os.close(descriptor)
        if not success:
            try:
                current = path.stat(follow_symlinks=False)
                if (current.st_dev, current.st_ino) == identity:
                    path.unlink()
            except FileNotFoundError:
                pass


def write_outputs(output_dir: Path, span: bytes,
                  previews: list[tuple[str, bytes]], report: dict[str, Any]) -> None:
    parent = output_dir.parent.resolve(strict=True)
    target = parent / output_dir.name
    require(not target.exists() and not target.is_symlink(),
            "output directory already exists")
    os.mkdir(target, 0o755)
    success = False
    try:
        preview_dir = target / "previews"
        os.mkdir(preview_dir, 0o755)
        create_file(target / "replacement.txtr.bin", span)
        for name, payload in previews:
            require(Path(name).name == name, "unsafe preview filename")
            create_file(preview_dir / name, payload)
        create_file(target / "import.json", canonical_json(report))
        success = True
    finally:
        if not success:
            for child in ((target / "previews").glob("*")
                          if (target / "previews").exists() else []):
                child.unlink()
            for child in (target / "replacement.txtr.bin", target / "import.json"):
                try:
                    child.unlink()
                except FileNotFoundError:
                    pass
            try:
                (target / "previews").rmdir()
            except FileNotFoundError:
                pass
            target.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--face-id", required=True)
    parser.add_argument("--family", required=True, choices=("f", "h", "n"))
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        span, previews, report = build_import(
            args.index, args.compatibility, args.face_id, args.family, args.png)
        write_outputs(args.output_dir, span, previews, report)
        print(
            "NFL_LIVE_FACE_TEXTURE_PNG_IMPORT_OK "
            f"target={report['target']['resource_name']} "
            f"span={len(span)} mips={report['mips']['level_count']} "
            "runtime=false xemu_started=false"
        )
        return 0
    except (Dxt1Error, ImportFailure, OSError, ValueError, KeyError,
            json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
