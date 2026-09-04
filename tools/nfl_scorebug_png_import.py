#!/usr/bin/env python3
"""Fail-closed PNG importer for the proved NFL 2K5 scorebug texture family.

Supported targets are the 64x64 field-scorebug frame atlas (``score_buga``),
the 128x64 ESPN strip bound by the same executable table (``shield_espn``),
and the shared 128x128 ``digital_font`` atlas.  The latter is deliberately
labelled global: changing it can affect UI outside the scorebug.

The output is one size-preserving TXTR span.  This tool never writes an Xbox
archive, XISO, or original file.
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


SCHEMA = "nfl2k5_scorebug_png_import/v1"
AUDIT_SCHEMA = "vc_scorebug_presentation_audit/v1"
DEFAULT_INDEX = Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
DEFAULT_AUDIT = Path("reports/assets/scorebug_presentation_audit.json")
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
INDEX_SIZE = 193_710_080
AUDIT_SHA256 = "57bcbb1c0ff8e6c2376565365aba523e4c2fe8cdb66d3a7058daa84993c2ccd1"
TARGET_NAMES = ("score_buga", "shield_espn", "digital_font")
MAX_PNG_BYTES = 32 * 1024 * 1024


class ScorebugImportError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ScorebugImportError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def open_regular(path: Path, maximum: int, label: str) -> tuple[Path, bytes]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= maximum and
                (info.st_dev, info.st_ino) == (supplied.st_dev, supplied.st_ino),
                f"{label} identity/type/size changed")
        chunks: list[bytes] = []
        remaining = info.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            require(bool(block), f"short {label} read")
            chunks.append(block)
            remaining -= len(block)
        require(not os.read(descriptor, 1), f"{label} grew while reading")
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (info.st_dev, info.st_ino, info.st_size),
                f"{label} changed while reading")
        return resolved, b"".join(chunks)
    finally:
        os.close(descriptor)


def load_audit(path: Path) -> tuple[Path, bytes, dict[str, Any]]:
    resolved, payload = open_regular(path, 4 * 1024 * 1024, "scorebug audit")
    require(digest(payload) == AUDIT_SHA256, "scorebug audit SHA-256 changed")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ScorebugImportError("scorebug audit is invalid JSON") from exc
    require(payload == canonical_json(value) and isinstance(value, dict) and
            value.get("schema") == AUDIT_SCHEMA,
            "scorebug audit schema/canonical encoding changed")
    return resolved, payload, value


def select_target(report: dict[str, Any], name: str) -> dict[str, Any]:
    require(name in TARGET_NAMES, "target is outside the proved scorebug family")
    rows = report["nfl2k5"]["texture_targets"]
    matches = [row for row in rows if row.get("name") == name]
    require(len(matches) == 1, "scorebug audit target identity changed")
    target = matches[0]
    expected = {
        "score_buga": (346, 53, 64, 64, 4096, 5120, 2400),
        "shield_espn": (346, 26, 128, 64, 8192, 9216, 5920),
        "digital_font": (3, 46, 128, 128, 16384, 17408, 2720),
    }[name]
    require((int(target["outer_index"]), int(target["chunk_index"]),
             int(target["width"]), int(target["height"]),
             int(target["palette_offset"]), int(target["video_bytes"]),
             int(target["stored_size"])) == expected and
            target["format_name"] == "P8" and int(target["mip_levels"]) == 1 and
            bool(target["compressed"]) and int(target["system_bytes"]) == 128 and
            target["pack_path"] == "vc_53450030/0" and
            target["pack_sha256"] == INDEX_SHA256,
            "scorebug target layout changed")
    return target


def chunk_for(target: dict[str, Any], scratch: int) -> Chunk:
    return Chunk(0, 0, "TXTR", int(target["stored_size"]),
                 int(target["system_bytes"]), int(target["video_bytes"]),
                 COMPRESSED_SENTINEL, scratch, 0, 0)


def validate_texture(decoded: bytes, target: dict[str, Any], scratch: int) -> object:
    texture = parse_texture(decoded, chunk_for(target, scratch))
    require(texture.name == target["name"] and
            texture.descriptor_offset == int(target["descriptor_offset"]) and
            texture.pixel_offset == 0 and
            texture.palette_offset == int(target["palette_offset"]) and
            texture.packed_format == int(str(target["packed_format"]), 16) and
            texture.packed_size == 0 and texture.descriptor_flags == 0x80000000 and
            texture.format_name == "P8" and texture.mip_levels == 1 and
            texture.width == int(target["width"]) and
            texture.height == int(target["height"]) and texture.depth == 1,
            "scorebug TXTR descriptor changed")
    return texture


def validate_template(span: bytes, target: dict[str, Any]) \
        -> tuple[bytes, bytes, object, int]:
    """The retail TXTR span's own identity checks, wherever the bytes came from.

    ``read_template`` reads them out of an extracted pack archive (developer machines).
    A user only ever has the disc image, and the span sits at a pinned pack-relative
    offset inside it, so ``build_import(template_span=...)`` hands the same bytes here
    instead.  Every check below is on the span itself -- digest, TXTR wrapper, VC-LZ
    decode identity, texture descriptor -- so the two routes are equally fail-closed;
    the archive route additionally proves which outer package the span was cut from,
    which is exactly what a caller reading the image at that offset already knows.
    """

    require(digest(span) == target["span_sha256"], "retail TXTR span changed")
    header = HEADER.unpack_from(span)
    require(header[0] == b"TXTR" and header[1] == int(target["stored_size"]) and
            header[2] == 128 and header[3] == int(target["video_bytes"]) and
            header[4] == COMPRESSED_SENTINEL and header[6:] == (0, 0),
            "retail TXTR wrapper changed")
    scratch = int(header[5])
    decoded, decode_info = decode_chunk(span, chunk_for(target, scratch))
    require(decode_info is not None and digest(decoded) == target["decoded_sha256"] and
            decode_info.stream_tag == int(target["lz_stream_tag"]) and
            decode_info.offset_bits == int(target["lz_offset_bits"]) and
            decode_info.consumed_bytes == int(target["lz_consumed_bytes"]),
            "retail TXTR decode identity changed")
    validate_texture(decoded, target, scratch)
    return span, decoded, decode_info, scratch


def read_template(index_path: Path, target: dict[str, Any]) \
        -> tuple[Path, bytes, bytes, object, int]:
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
            entry.segments[0].pack_offset + int(target["chunk_offset"]) ==
                int(target["pack_offset"]),
            "scorebug outer package identity changed")
    span = read_entry_range(archive, entry, int(target["chunk_offset"]),
                            int(target["span_size"]))
    span, decoded, decode_info, scratch = validate_template(span, target)
    return index, span, decoded, decode_info, scratch


def read_png(path: Path, width: int, height: int) -> tuple[Path, bytes, bytes]:
    resolved, payload = open_regular(path, MAX_PNG_BYTES, "input PNG")
    got_width, got_height, rgba = palette_tools.decode_rgba_png(
        payload, (width, height))
    require((got_width, got_height) == (width, height) and
            len(rgba) == width * height * 4,
            f"input PNG must be exact {width}x{height} RGBA8")
    return resolved, payload, rgba


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


def build_import(index_path: Path | None, audit_path: Path, target_name: str,
                 png_path: Path, *, template_span: bytes | None = None
                 ) -> tuple[bytes, bytes, dict[str, Any]]:
    """Build one replacement span.

    ``template_span`` is the retail span read straight out of the user's disc image (the
    only route available on an install: the extracted pack archive at ``index_path`` is a
    developer artefact and is never shipped).  When it is given, ``index_path`` is not
    touched at all; when it is not, the span is cut out of the extracted archive exactly
    as before.  Both routes run the same span validation, so a replacement built either
    way is byte-for-byte the same.
    """

    audit_file, audit_payload, audit = load_audit(audit_path)
    target = select_target(audit, target_name)
    if template_span is not None:
        index = None
        template_span, template_decoded, template_info, scratch = validate_template(
            bytes(template_span), target)
    else:
        require(index_path is not None, "no retail template: neither a span nor an index")
        assert index_path is not None
        index, template_span, template_decoded, template_info, scratch = read_template(
            index_path, target)
    width, height = int(target["width"]), int(target["height"])
    png, png_payload, rgba = read_png(png_path, width, height)
    source_level = palette_tools.MipLevel(0, width, height, rgba)
    def candidate_decoded(
        candidate_palette: list[tuple[int, int, int, int]],
        candidate_levels: list[bytes],
    ) -> bytes:
        return (
            template_decoded[:128]
            + swizzle_2d(candidate_levels[0], width, height, 1)
            + palette_tools.palette_bytes(candidate_palette)
        )

    # The tier ladder starts at 256, so art that already fit the retail span is
    # byte-for-byte unchanged; only art that used to fail outright steps down.
    bounded = palette_tools.quantize_levels_to_vc_lz_bound(
        [source_level],
        candidate_decoded,
        stream_tag=int(target["lz_stream_tag"]),
        offset_bits=int(target["lz_offset_bits"]),
        max_encoded_size=int(target["stored_size"]),
    )
    palette, levels, quantization = (
        bounded.palette, bounded.index_levels, bounded.quantization
    )
    require(len(levels) == 1 and len(levels[0]) == width * height and
            len(levels[0]) == int(target["palette_offset"]),
            "scorebug P8 index allocation changed")
    index_chain = swizzle_2d(levels[0], width, height, 1)
    palette_bgra = palette_tools.palette_bytes(palette)
    require(len(index_chain) == int(target["palette_offset"]) and
            len(palette_bgra) == 1024, "scorebug P8 video allocation changed")
    rebuilt_decoded = bounded.decoded
    require(rebuilt_decoded == template_decoded[:128] + index_chain + palette_bgra,
            "bounded quantizer decoded layout disagrees with the rebuilt chain")
    require(len(rebuilt_decoded) == len(template_decoded) and
            rebuilt_decoded[:128] == template_decoded[:128],
            "scorebug decoded/system allocation changed")
    validate_texture(rebuilt_decoded, target, scratch)
    rebuilt_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
        template_span, rebuilt_decoded)
    rebuilt_header = HEADER.unpack_from(rebuilt_span)
    rebuilt_scratch = int(rebuilt_header[5])
    roundtrip, roundtrip_info = decode_chunk(
        rebuilt_span, chunk_for(target, rebuilt_scratch))
    require(roundtrip_info is not None and roundtrip == rebuilt_decoded and
            len(rebuilt_span) == len(template_span) and
            rebuilt_header[:5] == HEADER.unpack_from(template_span)[:5] and
            rebuilt_header[6:] == HEADER.unpack_from(template_span)[6:] and
            rebuild_info.loader_in_place_end_guard and
            rebuild_info.loader_in_place_alias_guard,
            "scorebug compressed fixed-span rebuild failed")
    validate_texture(roundtrip, target, rebuilt_scratch)

    linear = unswizzle_2d(roundtrip[128:128 + width * height], width, height, 1)
    decoded_palette = palette_tools.parse_palette(
        roundtrip[128:], int(target["palette_offset"]))
    preview_rgba = palette_tools.rgba_from_indices(linear, decoded_palette)
    preview = encode_rgba_png(width, height, preview_rgba)
    require(palette_tools.decode_rgba_png(preview, (width, height)) ==
            (width, height, preview_rgba), "scorebug preview strict reparse failed")
    runs = difference_runs(template_span, rebuilt_span)
    require(runs, "input PNG produced a byte-identical retail target")
    changed = sum(last - first + 1 for first, last in runs)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        # Which retail archive this replacement was cut against.  Either the extracted pack
        # was opened and hashed (developer route), or the span itself came from the user's
        # image and matched the audited digest of that pack's span (install route) -- so the
        # pack identity is proved either way, but only the first route touched a file.
        "canonical_index": ({"path": str(index), "size": INDEX_SIZE, "sha256": INDEX_SHA256,
                             "source": "extracted pack archive"} if index is not None else
                            {"path": None, "size": INDEX_SIZE, "sha256": INDEX_SHA256,
                             "source": "retail span read from the disc image being written",
                             "pack_file_opened": False}),
        "audit": {"path": str(audit_file), "sha256": digest(audit_payload)},
        "target": target,
        "input_png": {"path": str(png), "file_name": png.name,
                      "size": len(png_payload), "sha256": digest(png_payload),
                      "width": width, "height": height,
                      "rgba_sha256": digest(rgba),
                      "strict_rgba8_noninterlaced": True},
        "quantization": {
            "algorithm": "weighted_median_cut_rgba_then_nearest_squared_error",
            # The bounded ladder can quantize a replacement down to fit its
            # fixed VC-LZ span. That is lossy, so it is recorded here and
            # reported to the user rather than applied silently.
            "palette_fit_attempts": list(bounded.attempts),
            "palette_was_reduced": len(bounded.attempts) > 1,
            **quantization, "palette_entries": len(palette),
            "unused_palette_entries_zero_filled": True,
        },
        "compression": {
            "mode": "vc_lz_fixed_span",
            "stream_tag": roundtrip_info.stream_tag,
            "offset_bits": roundtrip_info.offset_bits,
            "encoded_bytes": roundtrip_info.consumed_bytes,
            "stored_bytes": int(target["stored_size"]),
            "zero_padding_bytes": int(target["stored_size"]) -
                                  roundtrip_info.consumed_bytes,
            "fixed_span_fit": roundtrip_info.consumed_bytes <=
                              int(target["stored_size"]),
        },
        "rebuild": {
            **asdict(rebuild_info), "span_size": len(rebuilt_span),
            "span_sha256": digest(rebuilt_span),
            "decoded_roundtrip_sha256": digest(roundtrip),
            "index_chain_sha256": digest(index_chain),
            "palette_bgra_sha256": digest(palette_bgra),
            "changed_byte_count": changed, "changed_run_count": len(runs),
            "changed_runs": runs, "system_bytes_preserved": True,
        },
        "preview": {"file_name": "preview.png", "sha256": digest(preview),
                    "rgba_sha256": digest(preview_rgba), "width": width,
                    "height": height},
        "claims": {
            "field_scorebug_code_bound_texture": target_name in {
                "score_buga", "shield_espn"
            },
            "shared_global_font_texture": target_name == "digital_font",
            "fixed_span_only": True, "originals_modified": False,
            "xiso_created": False, "xemu_started": False,
            "title_executed": False, "runtime_visibility_proved": False,
            "portme": "PORTME(runtime): capture the modified field scorebug in xemu.",
        },
    }
    return rebuilt_span, preview, report


def create_file(path: Path, payload: bytes) -> tuple[int, int]:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0), 0o644)
    info = os.fstat(descriptor)
    identity = (info.st_dev, info.st_ino)
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


def write_outputs(output_dir: Path, span: bytes, preview: bytes,
                  report: dict[str, Any]) -> None:
    parent = output_dir.parent.resolve(strict=True)
    target = parent / output_dir.name
    require(not target.exists() and not target.is_symlink(),
            "output directory already exists")
    os.mkdir(target, 0o755)
    success = False
    try:
        create_file(target / "replacement.txtr.bin", span)
        create_file(target / "preview.png", preview)
        create_file(target / "import.json", canonical_json(report))
        success = True
    finally:
        if not success:
            for name in ("replacement.txtr.bin", "preview.png", "import.json"):
                try:
                    (target / name).unlink()
                except FileNotFoundError:
                    pass
            target.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--target", choices=TARGET_NAMES, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        span, preview, report = build_import(
            args.index, args.audit, args.target, args.png)
        write_outputs(args.output_dir, span, preview, report)
        print("NFL_SCOREBUG_PNG_IMPORT_OK "
              f"target={args.target} changed={report['rebuild']['changed_byte_count']} "
              "runtime=false")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
