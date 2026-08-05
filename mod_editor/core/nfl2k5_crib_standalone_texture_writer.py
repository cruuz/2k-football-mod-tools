"""Fixed-allocation writer for standalone NFL 2K5 Crib textures.

The Crib owns two standalone P8 families outside its SCNE resources:

* 114 raw TXTR allocations in the Team Item aggregate; and
* 68 VC-LZ TXTR allocations in the main Crib aggregate.

The compressed family includes one reflection map whose palette follows a
109,440-byte source-owned video gap and one row-major ``VC_P8_LINEAR`` ticker.
This writer derives every physical span from the user's archive index, keeps
those unusual bytes in place, and changes only the selected pixel chain and
palette inside an otherwise fixed resource allocation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import stat
import struct
from typing import Any

from .errors import ValidationError
from .nfl2k5_crib import (
    CribAsset,
    CribStorage,
    _generate_mips,
    load_nfl2k5_crib_catalog,
)

try:
    import nfl_tset_png_import as palette_tools
    from nfl_outer import FormatError, parse_archive, read_entry_range
    from nfl_txtr import (
        HEADER,
        TxtrError,
        decode_chunk,
        encode_rgba_png,
        parse_chunks,
        parse_texture,
        rebuild_compressed_chunk_fixed_span,
        swizzle_2d,
        texture_to_rgba,
    )
except ImportError as exc:  # pragma: no cover - installation boundary
    raise RuntimeError("The NFL standalone texture toolchain is unavailable") from exc


SCHEMA = "nfl2k5_crib_standalone_texture_import/v1"
PACK_METADATA = {
    "C": {
        "path": "vc_53450030/C",
        "retail_sector": 2_554_593,
        "size": 315_131_904,
        "sha256": "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090",
    },
}
PALETTE_BYTES = 1_024
REFLECTION_GAP_BYTES = 109_440


class CribStandaloneTextureWriterError(ValidationError):
    """A standalone Crib target or fixed-span rebuild failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CribStandaloneTextureWriterError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class _PhysicalSpan:
    pack_name: str
    pack_offset: int
    replacement_offset: int
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _Resolved:
    asset: CribAsset
    span: bytes
    chunk: Any
    decoded: bytes
    texture: Any
    physical_spans: tuple[_PhysicalSpan, ...]


def _asset_for(selector: str) -> CribAsset:
    try:
        asset = load_nfl2k5_crib_catalog().by_selector(selector)
    except ValidationError as exc:
        raise CribStandaloneTextureWriterError(str(exc)) from exc
    _require(
        asset.editable
        and asset.storage in {
            CribStorage.TEAM_ITEM_AGGREGATE,
            CribStorage.EXTERNAL_TEXTURE,
        }
        and not asset.selector.startswith("crib_team_photo:"),
        "Choose an editable standalone Crib item, logo, bobblehead, or ticker.",
    )
    _require(
        asset.format_name in {"P8", "VC_P8_LINEAR"},
        f"{asset.label} is not a supported P8 texture.",
    )
    return asset


def is_editable_selector(selector: str) -> bool:
    try:
        _asset_for(selector)
    except CribStandaloneTextureWriterError:
        return False
    return True


def _physical_spans(entry: Any, offset: int, payload: bytes) \
        -> tuple[_PhysicalSpan, ...]:
    _require(
        offset >= 0 and offset + len(payload) <= entry.size,
        "Standalone Crib texture leaves its owning aggregate.",
    )
    result: list[_PhysicalSpan] = []
    logical_start = 0
    replacement_offset = 0
    range_end = offset + len(payload)
    for segment in entry.segments:
        logical_end = logical_start + segment.size
        part_start = max(offset, logical_start)
        part_end = min(range_end, logical_end)
        if part_start < part_end:
            size = part_end - part_start
            piece = payload[replacement_offset:replacement_offset + size]
            _require(len(piece) == size, "Crib physical span split is incomplete.")
            result.append(_PhysicalSpan(
                pack_name=segment.pack_name,
                pack_offset=segment.pack_offset + part_start - logical_start,
                replacement_offset=replacement_offset,
                size=size,
                sha256=_sha256(piece),
            ))
            replacement_offset += size
        logical_start = logical_end
        if part_end == range_end:
            break
    _require(
        bool(result) and replacement_offset == len(payload) and len(result) <= 2,
        "Standalone Crib texture does not map to one complete fixed span.",
    )
    _require(
        all(row.pack_name in PACK_METADATA for row in result),
        "Standalone Crib texture moved to an unreviewed archive pack.",
    )
    return tuple(result)


def _resolve(index_path: Path, selector: str) -> _Resolved:
    asset = _asset_for(selector)
    try:
        archive = parse_archive(index_path)
        entry = archive.entries[asset.outer_index]
        _require(
            entry.name_id == int(asset.outer_id, 0)
            and entry.size == asset.outer_size,
            "The selected Crib aggregate changed.",
        )
        span = read_entry_range(
            archive,
            entry,
            asset.chunk_offset,
            HEADER.size + asset.stored_size,
        )
        chunks = parse_chunks(span)
        _require(len(chunks) == 1, "Crib target is not one bounded TXTR.")
        chunk = chunks[0]
        decoded, _detail = decode_chunk(span, chunk)
        texture = parse_texture(decoded, chunk)
        rgba = texture_to_rgba(decoded, chunk, texture)
    except CribStandaloneTextureWriterError:
        raise
    except (OSError, IndexError, FormatError, TxtrError, ValueError) as exc:
        raise CribStandaloneTextureWriterError(
            f"Could not resolve {asset.label} from the private source ({exc})."
        ) from exc
    _require(
        chunk.kind == "TXTR"
        and chunk.stored_size == asset.stored_size
        and chunk.system_bytes == asset.system_bytes
        and chunk.video_bytes == asset.video_bytes,
        f"The fixed TXTR wrapper for {asset.label} changed.",
    )
    _require(
        texture.name == asset.selector.rsplit(":", 1)[-1]
        and texture.descriptor_offset == asset.descriptor_offset
        and texture.pixel_offset == asset.pixel_offset
        and texture.palette_offset == asset.palette_offset
        and texture.packed_format == asset.packed_format
        and texture.packed_size == asset.packed_size
        and texture.width == asset.width
        and texture.height == asset.height
        and texture.mip_levels == asset.mip_levels
        and texture.format_name == asset.format_name,
        f"The texture descriptor for {asset.label} changed.",
    )
    _require(
        _sha256(decoded) == asset.decoded_sha256
        and _sha256(rgba) == asset.rgba_sha256,
        f"The source allocation for {asset.label} differs from the catalog.",
    )
    _require(
        (asset.storage is CribStorage.EXTERNAL_TEXTURE) is chunk.compressed,
        f"The compression class for {asset.label} changed.",
    )
    dimensions = tuple(
        (max(1, asset.width >> level), max(1, asset.height >> level))
        for level in range(asset.mip_levels)
    )
    chain_bytes = sum(width * height for width, height in dimensions)
    _require(
        asset.pixel_offset == 0
        and asset.palette_offset >= chain_bytes
        and asset.palette_offset + PALETTE_BYTES <= asset.video_bytes,
        f"The P8 allocation for {asset.label} changed.",
    )
    gap = asset.palette_offset - chain_bytes
    if asset.selector == "crib_external_texture:8:reflection":
        _require(gap == REFLECTION_GAP_BYTES,
                 "The reflection map's source-owned video gap changed.")
    else:
        _require(gap == 0, f"{asset.label} has an unreviewed P8 video gap.")
    _require(
        (asset.format_name == "VC_P8_LINEAR")
        == (asset.selector == "crib_external_texture:77:ticker_src")
        and (asset.format_name != "VC_P8_LINEAR" or asset.mip_levels == 1),
        "The row-major ticker layout changed.",
    )
    return _Resolved(
        asset=asset,
        span=span,
        chunk=chunk,
        decoded=decoded,
        texture=texture,
        physical_spans=_physical_spans(entry, asset.chunk_offset, span),
    )


def _read_png(path: Path, asset: CribAsset) -> tuple[bytes, bytes]:
    try:
        supplied = path.expanduser().lstat()
        _require(
            stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "Replacement PNG must be a regular, non-symlink file.",
        )
        _require(supplied.st_size <= palette_tools.MAX_PNG_BYTES,
                 "Replacement PNG exceeds the 32 MiB bound.")
        payload = path.expanduser().read_bytes()
        width, height, rgba = palette_tools.decode_rgba_png(
            payload, asset.dimensions
        )
    except CribStandaloneTextureWriterError:
        raise
    except (OSError, ValueError) as exc:
        raise CribStandaloneTextureWriterError(
            f"This Crib texture needs an exact {asset.width}×{asset.height} "
            f"non-interlaced RGBA8 PNG ({exc})."
        ) from exc
    _require(
        (width, height) == asset.dimensions,
        "Replacement PNG dimensions changed during validation.",
    )
    return payload, rgba


def _compile(resolved: _Resolved, png_path: Path) \
        -> tuple[bytes, bytes, dict[str, Any]]:
    asset = resolved.asset
    png_payload, rgba = _read_png(png_path, asset)
    levels = _generate_mips(rgba, asset.width, asset.height, asset.mip_levels)
    chain_bytes = sum(level.width * level.height for level in levels)
    gap_start = asset.system_bytes + chain_bytes
    palette_start = asset.system_bytes + asset.palette_offset
    gap_before = resolved.decoded[gap_start:palette_start]

    def candidate_decoded(
        palette: list[tuple[int, int, int, int]],
        index_levels: list[bytes],
    ) -> bytes:
        _require(len(index_levels) == len(levels), "Crib mip count changed.")
        encoded_levels = (
            index_levels
            if asset.format_name == "VC_P8_LINEAR"
            else [
                swizzle_2d(indices, level.width, level.height, 1)
                for indices, level in zip(index_levels, levels)
            ]
        )
        chain = b"".join(encoded_levels)
        _require(len(chain) == chain_bytes, "Crib P8 mip allocation changed.")
        rebuilt = bytearray(resolved.decoded)
        rebuilt[asset.system_bytes:asset.system_bytes + chain_bytes] = chain
        rebuilt[palette_start:palette_start + PALETTE_BYTES] = \
            palette_tools.palette_bytes(palette)
        result = bytes(rebuilt)
        _require(
            result[gap_start:palette_start] == gap_before,
            "Crib source-owned video gap changed.",
        )
        return result

    try:
        if resolved.chunk.compressed:
            stream = resolved.span[HEADER.size:]
            _require(len(stream) >= 9, "Crib VC-LZ prefix is truncated.")
            output_size, stream_tag = struct.unpack_from("<II", stream, 0)
            offset_bits = stream[8]
            _require(output_size == len(resolved.decoded),
                     "Crib VC-LZ output size changed.")
            bounded = palette_tools.quantize_levels_to_vc_lz_bound(
                levels,
                candidate_decoded,
                stream_tag=stream_tag,
                offset_bits=offset_bits,
                max_encoded_size=resolved.chunk.stored_size,
            )
            palette = bounded.palette
            index_levels = bounded.index_levels
            quantization = dict(bounded.quantization)
            rebuilt_decoded = bounded.decoded
            rebuilt_span, rebuild = rebuild_compressed_chunk_fixed_span(
                resolved.span, rebuilt_decoded
            )
            _require(
                rebuild.recompressed_bytes == len(bounded.compressed)
                and rebuilt_span[
                    HEADER.size:HEADER.size + len(bounded.compressed)
                ] == bounded.compressed,
                "Crib bounded VC-LZ stream changed during fixed-span rebuild.",
            )
            compression = {
                "encoded_bytes": rebuild.recompressed_bytes,
                "zero_padding_bytes": rebuild.zero_padding_bytes,
                "offset_bits": offset_bits,
                "palette_fit_attempts": list(bounded.attempts),
            }
        else:
            palette, index_levels, quantization = palette_tools.quantize_levels(levels)
            rebuilt_decoded = candidate_decoded(palette, index_levels)
            rebuilt_span = resolved.span[:HEADER.size] + rebuilt_decoded
            compression = {"compressed": False}
    except (TxtrError, ValueError) as exc:
        raise CribStandaloneTextureWriterError(
            f"Could not fit {asset.label} into its fixed game allocation ({exc})."
        ) from exc

    _require(
        len(rebuilt_span) == len(resolved.span),
        "Standalone Crib replacement changed its fixed span size.",
    )
    chunks = parse_chunks(rebuilt_span)
    _require(len(chunks) == 1, "Rebuilt standalone Crib TXTR is malformed.")
    rebuilt_chunk = chunks[0]
    roundtrip, _detail = decode_chunk(rebuilt_span, rebuilt_chunk)
    rebuilt_texture = parse_texture(roundtrip, rebuilt_chunk)
    _require(
        roundtrip == rebuilt_decoded
        and rebuilt_texture == resolved.texture
        and roundtrip[:asset.system_bytes] == resolved.decoded[:asset.system_bytes]
        and roundtrip[gap_start:palette_start] == gap_before,
        "Rebuilt standalone Crib TXTR changed metadata or source-owned bytes.",
    )
    base_rgba = texture_to_rgba(roundtrip, rebuilt_chunk, rebuilt_texture)
    preview = encode_rgba_png(asset.width, asset.height, base_rgba)
    _require(
        palette_tools.decode_rgba_png(preview, asset.dimensions)
        == (asset.width, asset.height, base_rgba),
        "Standalone Crib preview failed its pixel round-trip.",
    )
    allowed = (
        range(asset.system_bytes, asset.system_bytes + chain_bytes),
        range(palette_start, palette_start + PALETTE_BYTES),
    )
    changed_decoded = [
        index for index, pair in enumerate(zip(resolved.decoded, roundtrip))
        if pair[0] != pair[1]
    ]
    _require(
        all(any(index in span for span in allowed) for index in changed_decoded),
        "Standalone Crib edit escaped its pixel/palette allocation.",
    )
    report = {
        "schema": SCHEMA,
        "input_png": {
            "path": str(png_path),
            "sha256": _sha256(png_payload),
            "rgba_sha256": _sha256(rgba),
            "width": asset.width,
            "height": asset.height,
        },
        "replacement": {
            "span_size": len(rebuilt_span),
            "span_sha256": _sha256(rebuilt_span),
            "decoded_sha256": _sha256(roundtrip),
            "decoded_changed_byte_count": len(changed_decoded),
            "quantized_base_rgba_sha256": _sha256(base_rgba),
            "palette_entries": len(palette),
            "quantization": quantization,
            **compression,
        },
        "claims": {
            "fixed_txtr_allocation_only": True,
            "complete_declared_p8_mip_chain_regenerated": True,
            "wrapper_descriptor_and_system_preserved": True,
            "reflection_109440_byte_pre_palette_gap_preserved": (
                asset.selector == "crib_external_texture:8:reflection"
            ),
            "ticker_src_row_major_vc_p8_linear": (
                asset.selector == "crib_external_texture:77:ticker_src"
            ),
            "physical_extent_derived_from_private_archive": True,
            "contains_retail_bytes": False,
        },
    }
    return rebuilt_span, preview, report


def build_unified_crib_standalone_texture_imports(
    index_path: Path,
    selector: str,
    png_path: Path,
) -> list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]]:
    """Compile one logical standalone Crib texture into its physical spans."""

    resolved = _resolve(index_path, selector)
    rebuilt, preview, report = _compile(resolved, png_path)
    logical_sha = _sha256(rebuilt)
    result = []
    for part_index, piece in enumerate(resolved.physical_spans):
        replacement = rebuilt[
            piece.replacement_offset:piece.replacement_offset + piece.size
        ]
        _require(len(replacement) == piece.size,
                 "Crib replacement physical split is incomplete.")
        pack = PACK_METADATA[piece.pack_name]
        target_selector = (
            selector if len(resolved.physical_spans) == 1
            else f"{selector}:physical:{part_index + 1}-of-{len(resolved.physical_spans)}"
        )
        target = {
            "selector": target_selector,
            "logical_selector": selector,
            "asset_id": resolved.asset.asset_id,
            "outer_index": resolved.asset.outer_index,
            "chunk_index": resolved.asset.chunk_index,
            "format": resolved.asset.format_name,
            "width": resolved.asset.width,
            "height": resolved.asset.height,
            "mip_levels": resolved.asset.mip_levels,
            "physical_span_index": part_index,
            "physical_span_count": len(resolved.physical_spans),
            "replacement_offset": piece.replacement_offset,
            "logical_span_size": len(resolved.span),
            "logical_span_sha256": _sha256(resolved.span),
            "logical_replacement_sha256": logical_sha,
            "xiso_pack_path": pack["path"],
            "xiso_pack_sector": pack["retail_sector"],
            "xiso_pack_size": pack["size"],
            "xiso_pack_sha256": pack["sha256"],
            "pack_offset": piece.pack_offset,
            # Diagnostic only. The build re-derives the live absolute address
            # from xiso_pack_path + pack_offset before reading or writing.
            "xiso_absolute_span_offset": (
                int(pack["retail_sector"]) * 2_048 + piece.pack_offset
            ),
            "span_size": piece.size,
            "span_sha256": piece.sha256,
        }
        part_report = dict(report)
        part_report["target"] = target
        previews = [(
            f"crib-{resolved.asset.chunk_index:04d}-preview.png", preview
        )] if part_index == 0 else []
        result.append((replacement, previews, part_report, target_selector, target))
    _require(
        b"".join(row[0] for row in result) == rebuilt,
        "Crib physical spans do not reassemble to the rebuilt TXTR.",
    )
    return result


__all__ = [
    "CribStandaloneTextureWriterError",
    "REFLECTION_GAP_BYTES",
    "build_unified_crib_standalone_texture_imports",
    "is_editable_selector",
]
