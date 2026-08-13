#!/usr/bin/env python3
"""Fail-closed PNG importer for NFL 2K5 create-team live field art."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from nfl_outer import parse_archive, read_entry_range
from nfl_txtr import (COMPRESSED_SENTINEL, HEADER, Chunk, decode_chunk,
                      encode_rgba_png, parse_texture,
                      rebuild_compressed_chunk_fixed_span, swizzle_2d,
                      unswizzle_2d)
import nfl_tset_png_import as palette_tools
from nfl_create_team_field_art_inventory import (
    DEFAULT_INDEX, DEFAULT_JSON, INDEX_SHA256, INDEX_SIZE, LOGO_CODES,
    TEXTURES, WEATHERS, resource_id,
)


SCHEMA = "nfl2k5_create_team_field_art_png_import/v1"
MAX_PNG_BYTES = 32 * 1024 * 1024


class ImportError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ImportError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def difference_runs(before: bytes, after: bytes) -> list[list[int]]:
    require(len(before) == len(after), "difference inputs have unequal sizes")
    result: list[list[int]] = []
    for index, (left, right) in enumerate(zip(before, after)):
        if left == right:
            continue
        if not result or index != result[-1][1] + 1:
            result.append([index, index])
        else:
            result[-1][1] = index
    return result


def open_regular(path: Path, maximum: int, label: str) -> tuple[Path, bytes]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode) and opened.st_size <= maximum and
                (opened.st_dev, opened.st_ino) == (supplied.st_dev, supplied.st_ino),
                f"{label} identity/type/size changed")
        chunks = []
        remaining = opened.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            require(bool(block), f"short {label} read")
            chunks.append(block)
            remaining -= len(block)
        require(not os.read(descriptor, 1), f"{label} grew while reading")
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                f"{label} changed while reading")
        return resolved, b"".join(chunks)
    finally:
        os.close(descriptor)


def load_inventory(path: Path) -> tuple[Path, bytes, dict[str, Any]]:
    resolved, payload = open_regular(path, 32 * 1024 * 1024, "inventory")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ImportError("inventory is invalid JSON") from exc
    require(payload == canonical_json(value) and isinstance(value, dict) and
            value.get("schema") == "nfl2k5_create_team_field_art_inventory/v1" and
            value.get("source", {}).get("index_sha256") == INDEX_SHA256 and
            value.get("summary", {}).get("package_count") == 126 and
            value.get("summary", {}).get("texture_count") == 1134 and
            isinstance(value.get("textures"), list),
            "inventory schema/canonical identity changed")
    return resolved, payload, value


def select_target(inventory: dict[str, Any], logo_code: int, weather: str,
                  texture_name: str) -> dict[str, Any]:
    suffix = weather.upper()
    require(logo_code in LOGO_CODES and suffix in dict(WEATHERS) and
            texture_name in {item[0] for item in TEXTURES},
            "selector is outside the proved field-art family")
    selector = f"{logo_code}:{suffix}:{texture_name}"
    matches = [row for row in inventory["textures"]
               if isinstance(row, dict) and row.get("selector") == selector]
    require(len(matches) == 1, "inventory does not have exactly one target selector")
    target = matches[0]
    logical = f"ct{logo_code}{suffix}.iff"
    weather_index = [item[0] for item in WEATHERS].index(suffix)
    expected_index = 384 + weather_index * len(LOGO_CODES) + LOGO_CODES.index(logo_code)
    profile = next(item for item in TEXTURES if item[0] == texture_name)
    name, width, height, levels, palette_offset, video_bytes = profile
    require(target.get("logical_name") == logical and
            int(target.get("outer_index")) == expected_index and
            int(str(target.get("outer_id")), 16) == resource_id(logical) and
            int(target.get("chunk_index")) == [item[0] for item in TEXTURES].index(name) and
            int(target.get("width")) == width and int(target.get("height")) == height and
            int(target.get("mip_levels")) == levels and
            int(target.get("palette_offset")) == palette_offset and
            int(target.get("video_bytes")) == video_bytes and
            target.get("format_name") == "P8" and target.get("pack_path") == "vc_53450030/0",
            "selected inventory row disagrees with the proved selector/layout")
    return target


def target_chunk(target: dict[str, Any], scratch: int | None = None) -> Chunk:
    compressed = bool(target["compressed"])
    return Chunk(
        index=0, offset=0, kind="TXTR", stored_size=int(target["stored_size"]),
        system_bytes=int(target["system_bytes"]), video_bytes=int(target["video_bytes"]),
        compression_magic=COMPRESSED_SENTINEL if compressed else 0,
        overlap_scratch_bytes=(int(target["overlap_scratch_bytes"])
                               if scratch is None else scratch),
        reserved0=0, reserved1=0,
    )


def validate_texture(decoded: bytes, target: dict[str, Any]) -> object:
    texture = parse_texture(decoded, target_chunk(target))
    require(texture.name == target["name"] and texture.name_offset == 32 and
            texture.descriptor_offset == int(target["descriptor_offset"]) and
            texture.pixel_offset == 0 and
            texture.palette_offset == int(target["palette_offset"]) and
            texture.packed_format == int(str(target["packed_format"]), 16) and
            texture.packed_size == 0 and texture.descriptor_flags == 0x80000000 and
            texture.format_name == "P8" and
            texture.mip_levels == int(target["mip_levels"]) and
            texture.width == int(target["width"]) and
            texture.height == int(target["height"]) and texture.depth == 1,
            "target TXTR descriptor changed")
    return texture


def load_template(index_path: Path, target: dict[str, Any]) \
        -> tuple[Path, bytes, bytes, object | None]:
    supplied = index_path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "canonical index must be a non-symlink regular file")
    index = index_path.resolve(strict=True)
    info = index.stat(follow_symlinks=False)
    require((info.st_dev, info.st_ino, info.st_size) ==
            (supplied.st_dev, supplied.st_ino, INDEX_SIZE) and
            file_digest(index) == INDEX_SHA256,
            "canonical index identity changed")
    archive = parse_archive(index)
    entry = archive.entries[int(target["outer_index"])]
    require(entry.name_id == int(str(target["outer_id"]), 16) and
            entry.size == int(target["outer_size"]) and len(entry.segments) == 1 and
            entry.segments[0].pack_name == "0" and
            entry.segments[0].pack_offset == int(target["pack_offset"]),
            "selected package identity changed")
    span = read_entry_range(archive, entry, int(target["chunk_offset"]),
                            int(target["span_size"]))
    require(digest(span) == target["span_sha256"] and
            ["TXTR", *HEADER.unpack_from(span)[1:]] == target["complete_header"],
            "retail target span/header changed")
    decoded, decode_info = decode_chunk(span, target_chunk(target))
    require(len(decoded) == int(target["system_bytes"]) + int(target["video_bytes"]) and
            digest(decoded) == target["decoded_sha256"] and
            digest(decoded[:128]) == target["system_sha256"],
            "retail target decoded identity changed")
    if bool(target["compressed"]):
        require(decode_info is not None and
                decode_info.stream_tag == int(target["stream_tag"]) and
                decode_info.offset_bits == int(target["offset_bits"]) and
                decode_info.consumed_bytes == int(target["lz_consumed_bytes"]),
                "retail target compressed-stream identity changed")
    else:
        require(decode_info is None and int(target["stored_size"]) == len(decoded),
                "retail raw target identity changed")
    validate_texture(decoded, target)
    return index, span, decoded, decode_info


def generate_mips(rgba: bytes, base_width: int, base_height: int,
                  level_count: int) -> list[palette_tools.MipLevel]:
    require(len(rgba) == base_width * base_height * 4, "base RGBA size mismatch")
    result = [palette_tools.MipLevel(0, base_width, base_height, rgba)]
    current, width, height = rgba, base_width, base_height
    for level in range(1, level_count):
        next_width, next_height = max(1, width // 2), max(1, height // 2)
        output = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            for x in range(next_width):
                offsets = (((y * 2) * width + x * 2) * 4,
                           ((y * 2) * width + min(x * 2 + 1, width - 1)) * 4,
                           ((min(y * 2 + 1, height - 1)) * width + x * 2) * 4,
                           ((min(y * 2 + 1, height - 1)) * width +
                            min(x * 2 + 1, width - 1)) * 4)
                target_offset = (y * next_width + x) * 4
                for channel in range(4):
                    output[target_offset + channel] = (
                        sum(current[offset + channel] for offset in offsets) + 2) // 4
        current, width, height = bytes(output), next_width, next_height
        result.append(palette_tools.MipLevel(level, width, height, current))
    return result


def decode_levels(decoded: bytes, target: dict[str, Any]) \
        -> list[palette_tools.MipLevel]:
    width, height = int(target["width"]), int(target["height"])
    count = int(target["mip_levels"])
    video = decoded[128:]
    palette = palette_tools.parse_palette(video, int(target["palette_offset"]))
    result = []
    offset = 0
    for level in range(count):
        level_width, level_height = max(1, width >> level), max(1, height >> level)
        size = level_width * level_height
        swizzled = video[offset:offset + size]
        require(len(swizzled) == size, f"mip {level} is truncated")
        indices = unswizzle_2d(swizzled, level_width, level_height, 1)
        result.append(palette_tools.MipLevel(
            level, level_width, level_height,
            palette_tools.rgba_from_indices(indices, palette)))
        offset += size
    require(offset == int(target["palette_offset"]),
            "mip chain does not end at the palette")
    return result


def read_png(path: Path, width: int, height: int) -> tuple[Path, bytes, bytes]:
    resolved, payload = open_regular(path, MAX_PNG_BYTES, "input PNG")
    decoded_width, decoded_height, rgba = palette_tools.decode_rgba_png(
        payload, (width, height))
    require((decoded_width, decoded_height) == (width, height) and
            len(rgba) == width * height * 4,
            f"input PNG must be exact {width}x{height} RGBA8")
    return resolved, payload, rgba


def build_import(index_path: Path, inventory_path: Path, logo_code: int,
                 weather: str, texture_name: str, png_path: Path) \
        -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any]]:
    inventory_file, inventory_payload, inventory = load_inventory(inventory_path)
    target = select_target(inventory, logo_code, weather, texture_name)
    index, template_span, template_decoded, template_info = load_template(
        index_path, target)
    width, height, level_count = (int(target["width"]), int(target["height"]),
                                  int(target["mip_levels"]))
    png, png_payload, rgba = read_png(png_path, width, height)
    mips = generate_mips(rgba, width, height, level_count)
    def candidate_decoded(
        candidate_palette: list[tuple[int, int, int, int]],
        candidate_levels: list[bytes],
    ) -> bytes:
        chain = b"".join(
            swizzle_2d(indices, level.width, level.height, 1)
            for indices, level in zip(candidate_levels, mips)
        )
        return (
            template_decoded[:128]
            + chain
            + palette_tools.palette_bytes(candidate_palette)
        )

    if bool(target["compressed"]):
        # Only the compressed targets have a VC-LZ span to overflow. The tier
        # ladder starts at 256, so art that already fit is byte-for-byte
        # unchanged; only art that used to fail outright steps down.
        bounded = palette_tools.quantize_levels_to_vc_lz_bound(
            mips,
            candidate_decoded,
            stream_tag=int(target["stream_tag"]),
            offset_bits=int(target["offset_bits"]),
            max_encoded_size=int(target["stored_size"]),
        )
        palette, linear_levels, quantization = (
            bounded.palette, bounded.index_levels, bounded.quantization
        )
    else:
        palette, linear_levels, quantization = palette_tools.quantize_levels(mips)
    require(len(linear_levels) == level_count and
            sum(len(value) for value in linear_levels) == int(target["palette_offset"]),
            "quantized mip index allocation changed")
    quantized_levels = [palette_tools.MipLevel(
        source.level, source.width, source.height,
        palette_tools.rgba_from_indices(indices, palette))
        for source, indices in zip(mips, linear_levels)]
    index_chain = b"".join(swizzle_2d(indices, level.width, level.height, 1)
                           for indices, level in zip(linear_levels, mips))
    palette_bgra = palette_tools.palette_bytes(palette)
    require(len(index_chain) == int(target["palette_offset"]) and
            len(palette_bgra) == 1024, "P8 video allocation changed")
    rebuilt_decoded = template_decoded[:128] + index_chain + palette_bgra
    require(len(rebuilt_decoded) == len(template_decoded) and
            rebuilt_decoded[:128] == template_decoded[:128],
            "rebuilt decoded/system allocation changed")
    validate_texture(rebuilt_decoded, target)

    compression_record: dict[str, Any]
    rebuild_record: dict[str, Any]
    if bool(target["compressed"]):
        rebuilt_span, info = rebuild_compressed_chunk_fixed_span(
            template_span, rebuilt_decoded)
        header = HEADER.unpack_from(rebuilt_span)
        roundtrip, roundtrip_info = decode_chunk(
            rebuilt_span, target_chunk(target, int(header[5])))
        require(roundtrip_info is not None and roundtrip == rebuilt_decoded and
                len(rebuilt_span) == len(template_span) and
                header[:5] == HEADER.unpack_from(template_span)[:5] and
                header[6:] == HEADER.unpack_from(template_span)[6:] and
                info.loader_in_place_end_guard and info.loader_in_place_alias_guard,
                "compressed fixed-span rebuild failed")
        compression_record = {
            "mode": "vc_lz_fixed_span", "stream_tag": roundtrip_info.stream_tag,
            "offset_bits": roundtrip_info.offset_bits,
            "encoded_bytes": roundtrip_info.consumed_bytes,
            "stored_bytes": int(target["stored_size"]),
            "zero_padding_bytes": int(target["stored_size"]) -
                                  roundtrip_info.consumed_bytes,
            "fixed_span_fit": roundtrip_info.consumed_bytes <= int(target["stored_size"]),
        }
        rebuild_record = asdict(info)
    else:
        rebuilt_span = template_span[:HEADER.size] + rebuilt_decoded
        roundtrip, roundtrip_info = decode_chunk(rebuilt_span, target_chunk(target))
        require(roundtrip_info is None and roundtrip == rebuilt_decoded and
                len(rebuilt_span) == len(template_span) and
                rebuilt_span[:HEADER.size] == template_span[:HEADER.size],
                "raw fixed-span rebuild failed")
        compression_record = {"mode": "raw", "stored_bytes": len(rebuilt_decoded),
                              "fixed_span_fit": True}
        rebuild_record = {
            "kind": "TXTR", "stored_size": len(rebuilt_decoded),
            "system_bytes": int(target["system_bytes"]),
            "video_bytes": int(target["video_bytes"]),
            "complete_header_preserved": True,
        }

    decoded_levels = decode_levels(roundtrip, target)
    require(decoded_levels == quantized_levels,
            "independently decoded mips differ from quantized PNG")
    runs = difference_runs(template_span, rebuilt_span)
    require(runs, "input PNG produced a byte-identical retail target")
    changed = sum(end - start + 1 for start, end in runs)
    previews = []
    preview_rows = []
    for level in decoded_levels:
        name = f"mip{level.level}_{level.width}x{level.height}.png"
        payload = encode_rgba_png(level.width, level.height, level.rgba)
        require(palette_tools.decode_rgba_png(payload, (level.width, level.height)) ==
                (level.width, level.height, level.rgba),
                f"preview strict reparse failed: {name}")
        previews.append((name, payload))
        preview_rows.append({"level": level.level, "width": level.width,
                             "height": level.height, "file_name": name,
                             "rgba_sha256": digest(level.rgba),
                             "png_sha256": digest(payload)})

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "canonical_index": {"path": str(index), "size": INDEX_SIZE,
                            "sha256": INDEX_SHA256},
        "inventory": {"path": str(inventory_file),
                      "sha256": digest(inventory_payload)},
        "target": target,
        "input_png": {"path": str(png), "file_name": png.name,
                      "size": len(png_payload), "sha256": digest(png_payload),
                      "width": width, "height": height,
                      "rgba_sha256": digest(rgba),
                      "strict_rgba8_noninterlaced": True},
        "template": {"span_size": len(template_span),
                     "span_sha256": digest(template_span),
                     "decoded_sha256": digest(template_decoded),
                     "system_sha256": digest(template_decoded[:128]),
                     "compressed": bool(target["compressed"]),
                     "stream_tag": (template_info.stream_tag
                                    if template_info is not None else None),
                     "offset_bits": (template_info.offset_bits
                                     if template_info is not None else None)},
        "mips": {"filter": "unpremultiplied_rgba_2x2_box_round_nearest",
                 "level_count": level_count,
                 "dimensions": [[level.width, level.height] for level in mips],
                 "linear_index_bytes": [len(value) for value in linear_levels],
                 "each_level_swizzled_independently": True},
        "quantization": {"algorithm":
                         "weighted_median_cut_rgba_then_nearest_squared_error",
                         **quantization, "palette_entries": len(palette),
                         "unused_palette_entries_zero_filled": True},
        "compression": compression_record,
        "rebuild": {**rebuild_record, "span_size": len(rebuilt_span),
                    "span_sha256": digest(rebuilt_span),
                    "decoded_roundtrip_sha256": digest(roundtrip),
                    "index_chain_sha256": digest(index_chain),
                    "palette_bgra_sha256": digest(palette_bgra),
                    "changed_byte_count": changed,
                    "changed_run_count": len(runs), "changed_runs": runs,
                    "system_bytes_preserved": roundtrip[:128] == template_decoded[:128]},
        "previews": preview_rows,
        "claims": {
            "static_live_field_resource": True,
            "menu_or_team_select_imagery_modified": False,
            "fixed_span_only": True, "all_mips_generated_and_verified": True,
            "originals_modified": False, "xiso_created": False,
            "xemu_started": False, "title_executed": False,
            "runtime_visibility_proved": False,
            "portme": "PORTME(runtime): created-team gameplay capture is still required.",
        },
    }
    return rebuilt_span, previews, report


def create_file(path: Path, payload: bytes) -> tuple[int, int]:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0), 0o644)
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    success = False
    try:
        position = 0
        while position < len(payload):
            amount = os.write(descriptor, payload[position:])
            require(amount > 0, "short output write")
            position += amount
        os.fsync(descriptor)
        current = path.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (identity[0], identity[1], len(payload)),
                "output path/size changed")
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
            preview = target / "previews"
            if preview.exists():
                for child in preview.iterdir():
                    child.unlink()
                preview.rmdir()
            for name in ("replacement.txtr.bin", "import.json"):
                try:
                    (target / name).unlink()
                except FileNotFoundError:
                    pass
            target.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--logo-code", type=int, required=True)
    parser.add_argument("--weather", choices=tuple(item[0] for item in WEATHERS),
                        required=True)
    parser.add_argument("--texture", choices=tuple(item[0] for item in TEXTURES),
                        required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        span, previews, report = build_import(
            args.index, args.inventory, args.logo_code, args.weather,
            args.texture, args.png)
        write_outputs(args.output_dir, span, previews, report)
        print("NFL_CREATE_TEAM_FIELD_ART_PNG_IMPORT_OK "
              f"selector={report['target']['selector']} "
              f"mode={report['compression']['mode']} "
              f"changed={report['rebuild']['changed_byte_count']} "
              "runtime=false xemu_started=false")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
