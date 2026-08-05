#!/usr/bin/env python3
"""Fixed-allocation APF ``digital_font`` DXT5A/H7A transport.

This module selects the one hash-pinned retail target and returns a rebuilt
``global.iff`` allocation in memory.  It does not expose filesystem outputs;
the copy-only CLI is ``apf_digital_font_patch.py``.
"""

from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import io
import math
from pathlib import Path
import stat
import struct

from PIL import Image, UnidentifiedImageError, __version__ as PILLOW_VERSION

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_digital_font_layout as layout
import apf_inner
import apf_outer
import apf_texture_patch as archive_patch
import apf_xenos_dxt5a as dxt5a


SCHEMA = "apf_digital_font_transport/v1"
MAX_H7A_CANDIDATES = 256
MAX_PNG_BYTES = 16 * 1024 * 1024


class FontTransportError(ValueError):
    """Raised when a font edit leaves the proved structural class."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_png(path: Path) -> tuple[bytes, str]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise FontTransportError("digital_font PNG must be a non-symlink regular file")
    payload = path.read_bytes()
    if len(payload) != info.st_size or not 0 < len(payload) <= MAX_PNG_BYTES:
        raise FontTransportError("digital_font PNG size is outside its limit")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            if image.format != "PNG" or image.size != (128, 128) or image.mode != "RGBA":
                raise FontTransportError("digital_font input must be an exact 128x128 RGBA PNG")
            rgba = image.tobytes()
    except (UnidentifiedImageError, OSError) as exc:
        raise FontTransportError(f"cannot decode digital_font PNG: {exc}") from exc
    dxt5a.rgba_to_alpha(rgba)
    return rgba, sha256(payload)


def _match_length(data: bytes, current: int, candidate: int, maximum: int) -> int:
    length = 0
    while length < maximum and data[current + length] == data[candidate + length]:
        length += 1
    return length


def compress_h7a_bounded(data: bytes, shift: int) -> bytes:
    """Memory-bounded equivalent of the project H7A greedy encoder.

    H7A references only the previous ``(1 << shift) - 1`` bytes.  Unlike the
    older general helper, this implementation removes keys after they leave
    that window, which keeps a 46.6 MB ``global.iff`` block practical.
    """

    if not 1 <= shift <= 15:
        raise FontTransportError(f"invalid H7A shift {shift}")
    max_distance = (1 << shift) - 1
    max_length = ((1 << (16 - shift)) - 1) + 3
    positions: dict[bytes, deque[int]] = defaultdict(deque)
    output = bytearray()
    cursor = 0

    def remember(position: int) -> None:
        if position + 3 > len(data):
            return
        key = data[position : position + 3]
        positions[key].append(position)
        expired = position - max_distance - 1
        if expired >= 0 and expired + 3 <= len(data):
            expired_key = data[expired : expired + 3]
            bucket = positions.get(expired_key)
            if bucket is not None:
                while bucket and bucket[0] <= expired:
                    bucket.popleft()
                if not bucket:
                    del positions[expired_key]

    def best_match(at: int) -> tuple[int, int]:
        """The longest non-overlapping back-reference available at ``at``."""
        best_length = 0
        best_distance = 0
        if at + 3 <= len(data):
            bucket = positions.get(data[at : at + 3])
            if bucket:
                    minimum = at - max_distance
                    candidates = 0
                    for candidate in reversed(bucket):
                        if candidate < minimum:
                            break
                        distance = at - candidate
                        if distance <= 0:
                            continue
                        length = _match_length(
                            data, at, candidate, min(max_length, len(data) - at)
                        )
                        # Never emit a match that reads bytes it is still
                        # writing.  Our decoder copies one byte at a time and so
                        # reproduces an overlapping run correctly, which is why
                        # this round-trips offline while the rebuilt asset comes
                        # back as fine speckle in game.  Retail settles it: the
                        # shipped 512x512 crest block holds 36,099 matches and
                        # not one overlaps, where a plain greedy encoder emits
                        # nearly eleven thousand, almost all at distance 2.
                        if length > distance:
                            length = distance
                        if length < 3:
                            continue
                        # On a tie prefer the FARTHER match.  Both encode to
                        # the same two bytes, but since a match may no longer
                        # overlap, the reachable length at the next position is
                        # bounded by the distance -- so taking the near copy
                        # caps every following match at the same short length
                        # and a run ramps up far more slowly.
                        if length > best_length or (
                            length == best_length and distance > best_distance
                        ):
                            best_length = length
                            best_distance = distance
                            if best_length == max_length:
                                break
                        candidates += 1
                        if candidates >= MAX_H7A_CANDIDATES:
                            break
        return best_length, best_distance

    while cursor < len(data):
        descriptor_offset = len(output)
        output.append(0)
        descriptor = 0
        for bit in range(8):
            if cursor >= len(data):
                break
            best_length, best_distance = best_match(cursor)
            if 3 <= best_length < max_length and cursor + 1 < len(data):
                # Lazy matching.  Forbidding overlap costs ratio at the start of
                # every repeated region, and this font block sits inside a fixed
                # allocation with very little slack.  Taking a literal when the
                # next position offers a longer match buys that back without
                # relaxing the rule.
                ahead_length, _ahead_distance = best_match(cursor + 1)
                if ahead_length > best_length:
                    best_length = 0
            if best_length >= 3:
                descriptor |= 1 << bit
                output.extend(
                    (((best_length - 3) << shift) | best_distance).to_bytes(2, "big")
                )
                consumed = best_length
            else:
                output.append(data[cursor])
                consumed = 1
            for position in range(cursor, cursor + consumed):
                remember(position)
            cursor += consumed
        output[descriptor_offset] = descriptor
    return bytes(output)


def _alpha_metrics(wanted: bytes, decoded: bytes) -> dict[str, object]:
    if len(wanted) != len(decoded):
        raise FontTransportError("alpha metric lengths differ")
    errors = [abs(first - second) for first, second in zip(wanted, decoded)]
    squared = sum(value * value for value in errors)
    rmse = math.sqrt(squared / len(errors)) if errors else 0.0
    return {
        "compared_pixels": len(errors),
        "different_pixels": sum(value != 0 for value in errors),
        "maximum_absolute_error": max(errors, default=0),
        "mean_absolute_error": sum(errors) / len(errors) if errors else 0.0,
        "rmse": rmse,
        "psnr_db": None if rmse == 0 else 20.0 * math.log10(255.0 / rmse),
    }


def _indices_summary(indices: list[int]) -> dict[str, object]:
    serialized = b"".join(value.to_bytes(4, "big") for value in indices)
    return {
        "count": len(indices),
        "first": indices[0] if indices else None,
        "last": indices[-1] if indices else None,
        "big_endian_u32_sha256": sha256(serialized),
        "indices_embedded": indices if len(indices) <= 256 else None,
    }


def _rebuild_entry(
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    new_texture: bytes,
) -> tuple[bytes, dict[str, object]]:
    if len(original_blocks) != 3 or len(original_stored) != 3:
        raise FontTransportError("PORTME: global.iff must have exactly three blocks")
    target_part = record.files[layout.INNER_INDEX].parts[1]
    new_block_1 = bytearray(original_blocks[1])
    new_block_1[target_part.offset : target_part.offset + target_part.length] = new_texture
    new_blocks = [original_blocks[0], bytes(new_block_1), original_blocks[2]]
    descriptor = record.blocks[1]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise FontTransportError("PORTME: global.iff VRAM block is not H7A-compressed")
    encoded = compress_h7a_bounded(new_blocks[1], descriptor.wrapper.shift)
    encoded_stored = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        len(new_blocks[1]),
        apf_inner.H7A_HEADER_SIZE + len(encoded),
        descriptor.unknown_10,
        descriptor.wrapper.shift,
    ) + encoded
    if apf_inner.decompress_h7a(encoded, len(new_blocks[1]), descriptor.wrapper.shift) != new_blocks[1]:
        raise FontTransportError("global.iff H7A encode/decode round-trip failed")
    new_stored = [original_stored[0], encoded_stored, original_stored[2]]

    header = bytearray(original_entry[: record.header_size])
    body = bytearray()
    cursor = record.header_size
    block_rows: list[dict[str, object]] = []
    for index, (block, stored) in enumerate(zip(record.blocks, new_stored)):
        if not block.is_compressed and len(stored) != block.uncompressed_length:
            raise FontTransportError("uncompressed global.iff block length changed")
        compressed_length = len(stored) if block.is_compressed else block.uncompressed_length
        struct.pack_into(
            ">8I", header, apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
            block.name_hash, block.type_hash, block.unknown_08, block.uncompressed_length,
            block.unknown_10, cursor, compressed_length, block.indexed,
        )
        block_rows.append({
            "index": index,
            "start_before": block.start_offset,
            "start_after": cursor,
            "stored_length_before": len(original_stored[index]),
            "stored_length_after": len(stored),
            "stored_sha256_before": sha256(original_stored[index]),
            "stored_sha256_after": sha256(stored),
            "decoded_sha256_before": sha256(original_blocks[index]),
            "decoded_sha256_after": sha256(new_blocks[index]),
        })
        body.extend(stored)
        cursor += len(stored)

    new_file_length = record.header_size + len(body)
    struct.pack_into(">I", header, 0x08, new_file_length)
    if record.footer is None:
        raise FontTransportError("PORTME: global.iff footer is missing")
    footer_total = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_total]
    old_tail = original_entry[record.file_length + footer_total :]
    if any(old_tail):
        raise FontTransportError("PORTME: global.iff allocation tail is nonzero")
    active = bytes(header) + bytes(body) + footer
    if len(active) > entry.size:
        raise FontTransportError(
            f"rebuilt global.iff exceeds fixed allocation by {len(active) - entry.size} bytes"
        )
    rebuilt = active + bytes(entry.size - len(active))

    memory_reader = archive_patch.BytesReader(rebuilt)
    rebuilt_record = apf_inner.parse_iff(memory_reader, entry)
    rebuilt_blocks = [
        apf_inner.decode_block(memory_reader, rebuilt_record, index, 1 << 30)
        for index in range(rebuilt_record.block_count)
    ]
    if rebuilt_blocks != new_blocks:
        raise FontTransportError("rebuilt global.iff does not decode as intended")
    before_parts = archive_patch._file_part_hashes(record, original_blocks)  # type: ignore[attr-defined]
    after_parts = archive_patch._file_part_hashes(rebuilt_record, rebuilt_blocks)  # type: ignore[attr-defined]
    changed_parts = [key for key in before_parts if before_parts[key] != after_parts[key]]
    if changed_parts != [(layout.INNER_INDEX, 1)]:
        raise FontTransportError(f"unexpected global.iff inner parts changed: {changed_parts}")
    return rebuilt, {
        "allocation_size": entry.size,
        "file_length_before": record.file_length,
        "file_length_after": new_file_length,
        "allocation_slack_before": len(old_tail),
        "allocation_slack_after": entry.size - len(active),
        "footer_sha256_before": sha256(footer),
        "footer_sha256_after": sha256(rebuilt[new_file_length : new_file_length + footer_total]),
        "footer_bit_exact": rebuilt[new_file_length : new_file_length + footer_total] == footer,
        "blocks": block_rows,
        "changed_inner_parts": [
            {"file_index": layout.INNER_INDEX, "part_index": 1, "block_index": 1}
        ],
        "unrelated_inner_part_count": len(before_parts) - 1,
        "all_750_unrelated_inner_parts_preserved": len(before_parts) == 751,
        "decoded_vram_outside_target_bit_exact": (
            original_blocks[1][: target_part.offset]
            == rebuilt_blocks[1][: target_part.offset]
            and original_blocks[1][target_part.offset + target_part.length :]
            == rebuilt_blocks[1][target_part.offset + target_part.length :]
        ),
        "dram_block_stored_bit_exact": original_stored[0] == new_stored[0],
        "sram_block_stored_bit_exact": original_stored[2] == new_stored[2],
        "h7a_decode_encode_decode_exact": True,
        "rebuilt_iff_reparsed": True,
    }


def build_patch(index_path: Path, png_path: Path) -> archive_patch.PatchResult:
    archive = apf_outer.parse_archive(index_path)
    entry = archive.entries[layout.OUTER_INDEX]
    if (
        entry.name_id != layout.OUTER_NAME_ID
        or len(entry.segments) != 1
        or entry.segments[0].pack_name != "0A"
    ):
        raise FontTransportError("digital_font target does not resolve to pinned global.iff")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        original_blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        original_stored = [
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        ]
    if sha256(original_entry) != layout.EXPECTED_ENTRY_SHA256:
        raise FontTransportError("global.iff differs from the pinned retail allocation")
    if record.block_count != 3 or record.file_count != 442 or record.warnings:
        raise FontTransportError("PORTME: global.iff structure changed")
    target = record.files[layout.INNER_INDEX]
    if (
        target.file_id != layout.INNER_FILE_ID
        or target.name != "digital_font"
        or target.type_name != "TXTR"
        or [(part.block_index, part.offset, part.length) for part in target.parts]
        != [(0, 0x5C9F20, 0xE0), (1, 0x643000, 0x2000)]
    ):
        raise FontTransportError("digital_font identity or part layout changed")
    dram = original_blocks[0][0x5C9F20 : 0x5CA000]
    texture = original_blocks[1][0x643000 : 0x645000]
    if sha256(dram) != layout.TARGET_DRAM_SHA256 or sha256(texture) != layout.TARGET_VRAM_SHA256:
        raise FontTransportError("digital_font retail target hashes changed")
    metadata = apf_inner.parse_txtr_metadata(dram)
    dxt5a.strict_descriptor(metadata)
    original_linear = dxt5a.extract_linear(texture)
    if dxt5a.insert_linear(original_linear) != texture:
        raise FontTransportError("retail DXT5A transport is not bit-exact")
    original_alpha = dxt5a.decode_linear_alpha(original_linear)
    original_rgba = dxt5a.alpha_to_rgba(original_alpha)
    wanted_rgba, png_file_sha = _load_png(png_path)
    wanted_alpha = dxt5a.rgba_to_alpha(wanted_rgba)
    source = {
        "archive_index": str(index_path),
        "physical_volume": "0A",
        "outer_entry_index": layout.OUTER_INDEX,
        "outer_name": "global.iff",
        "inner_file_index": layout.INNER_INDEX,
        "inner_name": "digital_font",
        "entry_sha256": sha256(original_entry),
        "texture_sha256": sha256(texture),
        "png_file_sha256": png_file_sha,
        "png_rgba_sha256": sha256(wanted_rgba),
        "png_alpha_sha256": sha256(wanted_alpha),
    }
    if wanted_rgba == original_rgba:
        return archive_patch.PatchResult(original_entry, {
            "schema": SCHEMA,
            "mode": "no_op",
            "source": source,
            "target": {"descriptor": metadata},
            "validation": {
                "xenos_tile_endian_roundtrip_bit_exact": True,
                "input_matches_decoded_source": True,
                "entry_bit_exact": True,
                "source_opened_read_only": True,
            },
            "backend": {
                "png": f"Pillow {PILLOW_VERSION}",
                "dxt5a": "not invoked for bit-exact no-op",
                "h7a": "not invoked for bit-exact no-op",
            },
            "portme": [dxt5a.PRODUCTION_ENCODER_CAVEAT],
        })

    new_linear, changed_indices, encoder_error = dxt5a.replace_changed_blocks(
        original_linear, wanted_alpha
    )
    if not changed_indices:
        raise FontTransportError("changed PNG produced no changed DXT5A block")
    new_texture = dxt5a.insert_linear(new_linear)
    if dxt5a.extract_linear(new_texture) != new_linear:
        raise FontTransportError("patched DXT5A tile/endian round-trip failed")
    decoded_alpha = dxt5a.decode_linear_alpha(new_linear)
    decoded_rgba = dxt5a.alpha_to_rgba(decoded_alpha)
    rebuilt, iff = _rebuild_entry(
        entry, record, original_entry, original_blocks, original_stored, new_texture
    )
    return archive_patch.PatchResult(rebuilt, {
        "schema": SCHEMA,
        "mode": "patched",
        "source": source,
        "target": {
            "descriptor": metadata,
            "global_ui_shared_texture_warning": True,
            "runtime_visibility_proved": False,
            "changed_dxt5a_blocks": _indices_summary(changed_indices),
            "encoder_total_squared_alpha_error": encoder_error,
            "texture_sha256_before": sha256(texture),
            "texture_sha256_after": sha256(new_texture),
            "linear_dxt5a_sha256_before": sha256(original_linear),
            "linear_dxt5a_sha256_after": sha256(new_linear),
            "decoded_alpha_sha256_before": sha256(original_alpha),
            "decoded_alpha_sha256_after": sha256(decoded_alpha),
            "decoded_rgba_sha256_after": sha256(decoded_rgba),
            "decode_back_metrics": _alpha_metrics(wanted_alpha, decoded_alpha),
        },
        "iff": iff,
        "binary_patch_manifest": {
            "physical_volume": "0A",
            "physical_offset": entry.segments[0].pack_offset,
            "replacement_length": entry.size,
            "original_sha256": sha256(original_entry),
            "replacement_sha256": sha256(rebuilt),
            **archive_patch._changed_extents(original_entry, rebuilt),  # type: ignore[attr-defined]
            "contains_replacement_bytes": False,
        },
        "validation": {
            "dxt5a_encode_decode_complete": True,
            "xenos_tile_endian_roundtrip_bit_exact": True,
            "h7a_decode_encode_decode_exact": True,
            "rebuilt_iff_reparsed": True,
            "footer_bit_exact": True,
            "fixed_outer_allocation": True,
            "all_750_unrelated_inner_parts_preserved": True,
            "decoded_vram_outside_target_bit_exact": True,
            "dram_and_sram_stored_blocks_preserved": True,
            "source_opened_read_only": True,
        },
        "backend": {
            "png": f"Pillow {PILLOW_VERSION}",
            "dxt5a": "project-native deterministic touched-block endpoint encoder",
            "dxt5a_production_caveat": dxt5a.PRODUCTION_ENCODER_CAVEAT,
            "xenos_transport": "Xenia-derived tile address plus 8-in-16 endian",
            "h7a": "project-native memory-bounded greedy encoder",
        },
        "portme": [
            dxt5a.PRODUCTION_ENCODER_CAVEAT,
            "capture a route that visibly exercises digital_font in Xenia and on hardware",
            "map every global UI consumer before describing side effects as scorebug-only",
        ],
    })
