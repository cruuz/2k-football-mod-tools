"""Bounded package-local equipment recolours and independent P8 mip imports.

The uniform ``TSET`` resources in chunks 4 through 10 do not contain one
independent index image per named texture.  Every named sock, glove, shoe, and
similar variant in a chunk shares one swizzled mip/index chain and owns only an
independent 256-entry BGRA palette.  Replacing that shared chain for one name
would silently reshape every sibling.

Legacy project PNGs retain palette projection. New glove/shoe imports append
an aligned, coverage-filtered index chain and repoints only its descriptor.
Sibling descriptors, palettes and every shared mip remain exact. The decoded
video allocation grows, but the recompressed TSET stays inside its original
file span. EXPERIMENTAL / UNWITNESSED: gameplay residency and rendering need a
close/distant witness. Unsupported layouts and compression overflow fail closed.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any, Iterable

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_equipment_import_intent import (
    INTENT_CHUNK, OWN_TEXTURE, PALETTE_ONLY, import_mode, import_settings,
)


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_all_texture_xiso_workflow as p8_writer  # noqa: E402
from nfl_outer import parse_archive, read_entry_bytes  # noqa: E402
import nfl_tset_png_import as palette_tools  # noqa: E402
from nfl_txtr import (  # noqa: E402
    HEADER,
    TextureInfo,
    TxtrError,
    decode_chunk,
    compress_vc_lz,
    encode_rgba_png,
    parse_chunks,
    rebuild_compressed_chunk_fixed_span,
    minimum_vc_lz_overlap_scratch,
    swizzle_2d,
    texture_to_rgba,
    unswizzle_2d,
)


CATALOG_SCHEMA = "nfl2k5_uniform_equipment_export_catalog/v1"
DEFAULT_CATALOG = (
    ROOT / "mod_editor/data/nfl2k5_uniform_equipment_export_catalog.v1.json"
)
CATALOG_SIZE = 5_851_450
CATALOG_SHA256 = "fa2c9ca9bcc267b6981735347bf6daf6243d6ab8b83fba268804c280cfd94173"
EXPECTED_TARGETS = 28_530
MAX_PNG_BYTES = 32 * 1024 * 1024
PALETTE_BYTES = 1_024
PALETTE_LIMITS = (256, 128, 64, 32, 16, 8, 4, 2)
SUPPORTED_CHUNKS = frozenset(range(4, 11))
SUPPORTED_FORMAT = 0x0B
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_DECODED_BYTES = 2 * 1024 * 1024
CHAIN_PINS = ROOT / "mod_editor/data/nfl2k5_equipment_chain_pins.v1.json"
# Filled by the streaming retail census tool; contains hashes, never retail art.
CHAIN_PINS_SHA256 = "32ab51a7a70aea4e5bec1cff6b3f6542fb7a3f198b494939b8864313bc099628"
CATALOG_COLUMNS = (
    "outer_index",
    "set_selector",
    "tset_chunk_index",
    "reference_index",
    "name",
    "width",
    "height",
    "pixel_offset",
    "palette_offset",
    "packed_format",
    "packed_size",
    "descriptor_flags",
    "base_pixel_sha256",
    "palette_bgra_sha256",
)


# How the game finds each equipment texture (retail default.xbe, proved
# offline on the pinned executable; see tests/mod_editor/test_nfl2k5_equipment_consumers.py).
#
# The player texture binding table at 0x004EEAF8 has 96 rows of (UTF-16 name
# pointer, context-first word).  FUN_0008E620 fills the runtime cache from it
# through FUN_0008E5C0 (adds ``_mud`` for the mud quadrants) and FUN_0008E580:
# a context-first row (1) is looked up in the player's HOME/AWAY uniform
# context first; a global row (0) goes straight to FUN_000449E0(0, 'TXTR',
# name), which walks the loaded resource contexts newest-first (FUN_00043DB0
# inserts every new context at the list head).  The generic shoe, glove, elbow
# pad, long-sleeve and wristband variants are global rows, and only uniform
# packages carry those names, so every player -- both teams -- samples the copy
# inside the most recently loaded uniform package: the away team's package in
# a game (FUN_00062BE0 creates HOME at 0x0006327A and AWAY at 0x00063298), or
# the viewed team's ``<code>h0.iff``/``<code>a0.iff`` package on the front-end
# Edit Player screen (FUN_00091940 loads that one package alone).  That is why
# a shoe staged in one package showed on the Edit Player preview model and
# nowhere else.  Team-coloured variants (context-first rows) really are
# package-local.
#
# The shoe style selector (player record byte +0x0C, three bits per shoe,
# FUN_0008EFA0 tail at 0x0008F74A -> FUN_0008EF20) indexes the table at
# 0x004EF7C0: style 0..5 -> rows 84, 85, 86, 87, 88, 89 below; style 6 is the
# global-pack ``shoes_taped`` (row 90), which is not a package texture.
BINDING_TABLE_ROWS: dict[str, int] = {
    "glove01": 27, "glove02": 28, "glove03": 29, "glove04": 30,
    "glove05": 31, "glove06": 32, "glove07": 33, "glove08": 34,
    "longsleeve01": 35, "longsleeve02": 36, "longsleeve03": 37,
    "elbowpad01": 68, "elbowpad02": 69, "elbowpad03": 70, "elbowpad04": 71,
    "elbowpad05": 72, "elbowpad06": 73, "elbowpad07": 74,
    "wristband01": 78, "wristband02": 79, "wristband09": 83,
    "shoes01": 84, "shoes04": 85, "shoes09": 86, "shoes02": 87, "shoes03": 88, "shoes10": 89,
    "socks00": 91,
}
GLOBAL_LOOKUP_NAMES = frozenset({
    "glove01", "glove02", "glove03", "glove04", "longsleeve01", "longsleeve02",
    "elbowpad01", "elbowpad02", "elbowpad03", "elbowpad04", "wristband01", "wristband02",
    "shoes01", "shoes04", "shoes02", "shoes03",
})
CONTEXT_FIRST_NAMES = frozenset(BINDING_TABLE_ROWS) - GLOBAL_LOOKUP_NAMES
#: Edit Player "Style 1".."Style 6" in shoe-style order (style value 0..5).
SHOE_STYLE_NAMES = ("shoes01", "shoes04", "shoes09", "shoes02", "shoes03", "shoes10")


class EquipmentCompileCache:
    """Caller-owned memo for one build: decoded artwork and compiled spans.

    A global equipment variant is staged once per sampled uniform package, and
    the retail chunk-8 shoe span of Tennessee ``28H0`` is byte-identical in 169
    other packages. Identical retail bytes receiving identical artwork compile
    to identical bytes, so a build that passes one cache through every
    equipment group compiles each distinct span once. Nothing is cached
    without an explicit cache object; callers own its lifetime and bound.
    """

    def __init__(self, *, compiled_limit: int = 128, artwork_limit: int = 32) -> None:
        _require(compiled_limit > 0 and artwork_limit > 0, "Equipment compile cache bounds must be positive")
        self.compiled: "OrderedDict[tuple[Any, ...], _CompiledGroup]" = OrderedDict()
        self.artwork: "OrderedDict[tuple[Any, ...], tuple[bytes, bytes, list[Any]]]" = OrderedDict()
        self.compiled_limit = compiled_limit
        self.artwork_limit = artwork_limit
        self.hits = 0
        self.misses = 0

    def statistics(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "entries": len(self.compiled),
                "artwork_entries": len(self.artwork)}

    def clear(self) -> None:
        self.compiled.clear()
        self.artwork.clear()
        self.hits = self.misses = 0


class UniformEquipmentWriterError(ValueError):
    """A logical selector, private source, PNG, or fixed span is unsafe."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise UniformEquipmentWriterError(message)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_digest(path: Path) -> str:
    supplied = path.lstat()
    _require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        f"Private extracted pack must be a regular, non-link file: {path}",
    )
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0),
    )
    try:
        opened = os.fstat(descriptor)
        _require(
            (opened.st_dev, opened.st_ino, opened.st_size)
            == (supplied.st_dev, supplied.st_ino, supplied.st_size),
            f"Private extracted pack changed while opening: {path}",
        )
        result = hashlib.sha256()
        while True:
            block = os.read(descriptor, 16 * 1024 * 1024)
            if not block:
                break
            result.update(block)
        current = path.stat(follow_symlinks=False)
        _require(
            (current.st_dev, current.st_ino, current.st_size)
            == (opened.st_dev, opened.st_ino, opened.st_size),
            f"Private extracted pack changed while hashing: {path}",
        )
        return result.hexdigest()
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class EquipmentTarget:
    outer_index: int
    set_selector: str
    chunk_index: int
    reference_index: int
    name: str
    width: int
    height: int
    pixel_offset: int
    palette_offset: int
    packed_format: int
    packed_size: int
    descriptor_flags: int
    base_pixel_sha256: str
    palette_bgra_sha256: str

    @property
    def asset_id(self) -> str:
        return (
            f"tset:{self.outer_index}:{self.chunk_index}:"
            f"{self.reference_index}:{self.name}"
        )

    @property
    def mip_levels(self) -> int:
        return (self.packed_format >> 16) & 0xF

    @property
    def format_code(self) -> int:
        return (self.packed_format >> 8) & 0xFF


def load_targets(
    path: Path = DEFAULT_CATALOG,
) -> tuple[dict[str, EquipmentTarget], dict[tuple[int, int], tuple[EquipmentTarget, ...]]]:
    """Read the exact retail-free catalog and expose logical/physical maps."""

    resolved = path.expanduser()
    _require(resolved.is_file() and not resolved.is_symlink(),
             f"Uniform-equipment catalog is missing: {resolved}")
    payload = resolved.read_bytes()
    _require(
        len(payload) == CATALOG_SIZE and _digest(payload) == CATALOG_SHA256,
        "Uniform-equipment catalog identity changed",
    )
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UniformEquipmentWriterError(
            f"Uniform-equipment catalog is invalid JSON: {exc}"
        ) from exc
    _require(
        document.get("schema") == CATALOG_SCHEMA
        and document.get("columns") == list(CATALOG_COLUMNS)
        and document.get("contract") == {
            "access": "preview-export-and-palette-import",
            "import_mode": "fixed-shared-index-palette",
            "import_supported": True,
            "retail_payload_bytes": False,
            "source_rows": 32_334,
            "source_tsv_sha256":
                "f8c60d618cab8326d7a215936a2e66a75d9f399c13c0087608fbc2010bcd3abd",
        },
        "Uniform-equipment catalog contract changed",
    )
    rows = document.get("rows")
    _require(isinstance(rows, list) and len(rows) == EXPECTED_TARGETS,
             "Uniform-equipment catalog row count changed")
    by_id: dict[str, EquipmentTarget] = {}
    grouped: dict[tuple[int, int], list[EquipmentTarget]] = {}
    for number, raw in enumerate(rows, 1):
        _require(isinstance(raw, list) and len(raw) == len(CATALOG_COLUMNS),
                 f"Uniform-equipment catalog row {number} has the wrong shape")
        row = dict(zip(CATALOG_COLUMNS, raw))
        target = EquipmentTarget(
            outer_index=int(row["outer_index"]),
            set_selector=str(row["set_selector"]),
            chunk_index=int(row["tset_chunk_index"]),
            reference_index=int(row["reference_index"]),
            name=str(row["name"]),
            width=int(row["width"]),
            height=int(row["height"]),
            pixel_offset=int(row["pixel_offset"]),
            palette_offset=int(row["palette_offset"]),
            packed_format=int(row["packed_format"]),
            packed_size=int(row["packed_size"]),
            descriptor_flags=int(row["descriptor_flags"]),
            base_pixel_sha256=str(row["base_pixel_sha256"]),
            palette_bgra_sha256=str(row["palette_bgra_sha256"]),
        )
        _require(
            target.chunk_index in SUPPORTED_CHUNKS
            and target.format_code == SUPPORTED_FORMAT
            and target.packed_size == 0
            and target.pixel_offset == 0
            and target.asset_id not in by_id,
            f"Uniform-equipment row {number} is not a unique supported P8 target",
        )
        by_id[target.asset_id] = target
        grouped.setdefault((target.outer_index, target.chunk_index), []).append(target)
    return by_id, {
        key: tuple(sorted(value, key=lambda item: item.reference_index))
        for key, value in grouped.items()
    }


def in_game_lookup(name: str) -> str:
    """``"global"`` (newest loaded package wins) or ``"context_first"`` (own package)."""

    base = name[:-4] if name.endswith("_mud") else name
    _require(base in BINDING_TABLE_ROWS, f"Unknown uniform-equipment texture name: {name}")
    return "global" if base in GLOBAL_LOOKUP_NAMES else "context_first"


def sampled_package(set_selector: str) -> bool:
    """Whether the game can ever bind a global equipment row from this package.

    Away packages (``<code>A<style>``) are the last uniform context created in
    every game, so the away team's copy wins the newest-first walk for both
    teams; ``<code>H0``/``<code>A0`` are the only packages the front-end Edit
    Player preview loads (alone).  Other home styles are never the newest
    uniform context anywhere, so their generic copies are never sampled.
    """

    return set_selector[2:3] == "A" or set_selector[2:] == "H0"


def consumer_targets(
    target: EquipmentTarget, by_id: dict[str, EquipmentTarget],
) -> tuple[EquipmentTarget, ...]:
    """Every catalog copy of ``target``'s texture the game can actually sample.

    Team-coloured (context-first) variants resolve to the selected package
    only.  Global variants resolve to the selected package plus every package
    :func:`sampled_package` accepts, in archive order, so an import reaches the
    copy the game binds in a game and the copy the Edit Player preview shows.
    """

    if in_game_lookup(target.name) == "context_first":
        return (target,)
    result = {target.asset_id: target}
    for item in by_id.values():
        if (item.chunk_index, item.reference_index, item.name) != (
                target.chunk_index, target.reference_index, target.name):
            continue
        if sampled_package(item.set_selector):
            result[item.asset_id] = item
    return tuple(sorted(result.values(), key=lambda item: item.outer_index))


def _pointer(payload: bytes, field: int, limit: int, label: str) -> int:
    _require(field + 4 <= limit, f"{label} pointer field is out of bounds")
    relative = struct.unpack_from("<i", payload, field)[0]
    target = field + relative - 1
    _require(0 <= target < limit, f"{label} pointer is out of bounds")
    return target


def _utf16z(payload: bytes, start: int, limit: int, label: str) -> str:
    cursor = start
    while cursor + 2 <= limit and payload[cursor:cursor + 2] != b"\0\0":
        cursor += 2
    _require(cursor + 2 <= limit, f"{label} is not NUL terminated")
    try:
        return payload[start:cursor].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise UniformEquipmentWriterError(f"{label} is invalid UTF-16") from exc


def _texture(target: EquipmentTarget, descriptor_offset: int) -> TextureInfo:
    return TextureInfo(
        name=target.name,
        name_offset=0,
        descriptor_offset=descriptor_offset,
        pixel_offset=target.pixel_offset,
        palette_offset=target.palette_offset,
        packed_format=target.packed_format,
        packed_size=target.packed_size,
        descriptor_flags=target.descriptor_flags,
        dimensions=(target.packed_format >> 4) & 0xF,
        format_code=target.format_code,
        format_name="P8",
        mip_levels=target.mip_levels,
        width=target.width,
        height=target.height,
        depth=1 << ((target.packed_format >> 28) & 0xF),
    )


def _validate_layout(
    decoded: bytes,
    chunk: Any,
    rows: tuple[EquipmentTarget, ...],
) -> tuple[dict[int, TextureInfo], list[bytes]]:
    _require(
        len(decoded) == chunk.system_bytes + chunk.video_bytes
        and len(decoded) >= 8,
        "Uniform-equipment TSET decoded size changed",
    )
    version, count = struct.unpack_from("<II", decoded, 0)
    _require(version == 0x0D and count == len(rows),
             "Uniform-equipment TSET version/reference count changed")
    _require(
        tuple(item.reference_index for item in rows) == tuple(range(count)),
        "Uniform-equipment reference order changed",
    )
    video = decoded[chunk.system_bytes:]
    textures: dict[int, TextureInfo] = {}
    common_layout: tuple[int, int, int, int] | None = None
    for target in rows:
        base = 0x18 + target.reference_index * 0x24
        _require(decoded[base:base + 4] == b"TXTR",
                 f"{target.asset_id} embedded TXTR marker changed")
        name_offset = _pointer(
            decoded, base + 4, chunk.system_bytes, f"{target.asset_id} name"
        )
        descriptor_offset = _pointer(
            decoded, base + 8, chunk.system_bytes, f"{target.asset_id} descriptor"
        )
        name = _utf16z(
            decoded, name_offset, chunk.system_bytes, f"{target.asset_id} name"
        )
        _require(name == target.name and descriptor_offset + 24 <= chunk.system_bytes,
                 f"{target.asset_id} name/descriptor moved")
        _unknown, pixel, palette, packed_format, packed_size, flags = \
            struct.unpack_from("<6I", decoded, descriptor_offset)
        _require(
            pixel == target.pixel_offset
            and palette == target.palette_offset
            and packed_format == target.packed_format
            and packed_size == target.packed_size
            and flags == target.descriptor_flags
            and target.format_code == SUPPORTED_FORMAT,
            f"{target.asset_id} is not the reviewed swizzled P8 descriptor",
        )
        layout = (
            target.pixel_offset, target.width, target.height, target.mip_levels
        )
        _require(common_layout in {None, layout},
                 "Uniform-equipment references no longer share one index layout")
        common_layout = layout
        base_bytes = target.width * target.height
        _require(
            _digest(video[pixel:pixel + base_bytes]) == target.base_pixel_sha256
            and _digest(video[palette:palette + PALETTE_BYTES])
                == target.palette_bgra_sha256,
            f"{target.asset_id} no longer matches the reviewed source hashes",
        )
        textures[target.reference_index] = _texture(target, descriptor_offset)
    assert common_layout is not None
    pixel_offset, width, height, mip_levels = common_layout
    expected_chain = sum(
        max(1, width >> level) * max(1, height >> level)
        for level in range(mip_levels)
    )
    _require(
        pixel_offset == 0
        and expected_chain == min(item.palette_offset for item in rows)
        and all(
            item.palette_offset + PALETTE_BYTES <= len(video)
            for item in rows
        )
        and len({item.palette_offset for item in rows}) == len(rows),
        "Uniform-equipment shared index/palette allocation changed",
    )
    indices: list[bytes] = []
    cursor = pixel_offset
    for level in range(mip_levels):
        level_width = max(1, width >> level)
        level_height = max(1, height >> level)
        size = level_width * level_height
        indices.append(unswizzle_2d(
            video[cursor:cursor + size], level_width, level_height, 1
        ))
        cursor += size
    _require(cursor == expected_chain, "Uniform-equipment mip chain size changed")
    return textures, indices


def _read_png(
    path: Path, target: EquipmentTarget, cache: EquipmentCompileCache | None = None,
) -> tuple[bytes, bytes, list[Any]]:
    requested = path.expanduser()
    supplied = requested.lstat()
    _require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode)
        and 0 < supplied.st_size <= MAX_PNG_BYTES,
        f"{target.asset_id} PNG must be a regular file no larger than 32 MiB",
    )
    resolved = requested.resolve(strict=True)
    payload = resolved.read_bytes()
    current = resolved.stat(follow_symlinks=False)
    _require(
        (current.st_dev, current.st_ino, current.st_size)
        == (supplied.st_dev, supplied.st_ino, supplied.st_size),
        f"{target.asset_id} PNG changed while it was read",
    )
    # A global equipment variant is staged once per sampled package with the
    # same artwork; decode and mip-filter each distinct PNG once. An explicit
    # own-texture choice names its target inside the PNG, so that key keeps the
    # asset ID and a copied intent is still validated against its own variant.
    key = (_digest(payload), target.asset_id if INTENT_CHUNK in payload else None,
           target.width, target.height, target.mip_levels)
    cached = cache.artwork.get(key) if cache is not None else None
    if cached is not None:
        cache.artwork.move_to_end(key)
        return cached
    try:
        width, height, rgba = palette_tools.decode_rgba_png(
            payload, (target.width, target.height)
        )
        if import_mode(payload, target.asset_id, rgba) == OWN_TEXTURE:
            from mod_editor.core.nfl2k5_digit_texture import make_digit_mips

            levels = make_digit_mips(rgba, width, height, target.mip_levels)
            # Preserve even invisible RGB from an exported straight-alpha PNG.
            # Lower mips still filter coverage without invisible colour bleed.
            levels[0] = replace(levels[0], rgba=rgba)
            scale = import_settings(payload, target.asset_id, rgba)[1]
            shift = scale.bit_length() - 1
            _require(shift < len(levels), "Equipment image size removes every mip level")
            levels = [replace(level, level=number) for number, level in enumerate(levels[shift:])]
        else:
            levels = p8_writer.generate_mips(
                rgba, width, height, target.mip_levels
            )
    except (ValueError, p8_writer.TextureWorkflowError) as exc:
        raise UniformEquipmentWriterError(str(exc)) from exc
    if cache is not None:
        cache.artwork[key] = (payload, rgba, levels)
        while len(cache.artwork) > cache.artwork_limit:
            cache.artwork.popitem(last=False)
    return payload, rgba, levels


def _chain_pins() -> dict[tuple[int, int], str]:
    payload = CHAIN_PINS.read_bytes()
    _require(_digest(payload) == CHAIN_PINS_SHA256, "Equipment source pin catalog changed")
    document = json.loads(payload)
    _require(document.get("schema") == "nfl2k5_equipment_chain_pins/v1",
             "Equipment source pin schema changed")
    return {(outer, chunk): digest for outer, chunk, digest in document["rows"]}


def _rebuild_grown_video(template_span: bytes, candidate: bytes):
    """Use the existing VC-LZ codec and overlap validator with a larger video heap.

    TSET loader 0x451D0 allocates system + video + scratch from the wrapper;
    0x45280 reads exactly stored_size bytes. No outer size/offset changes.
    """
    chunk = parse_chunks(template_span)[0]
    _require(chunk.kind == "TSET" and chunk.compressed
             and chunk.reserved0 == chunk.reserved1 == 0,
             "Independent equipment requires the reviewed compressed TSET wrapper")
    _require(chunk.output_size <= len(candidate) <= MAX_DECODED_BYTES,
             "Independent equipment exceeds the bounded decoded allocation")
    _decoded, original = decode_chunk(template_span, chunk)
    assert original is not None
    # As in the fixed-span Stadium writer, try the source geometry first,
    # then the retail-observed 10/11/12-bit distance tiers. Long runs in a new
    # chain need a different distance/length split than detailed shared art.
    # This changes only the lossless transport, never a sibling's decoded data.
    bit_candidates = tuple(dict.fromkeys((original.offset_bits, 10, 11, 12)))
    for offset_bits in bit_candidates:
        try:
            encoded, _info = compress_vc_lz(
                candidate, stream_tag=original.stream_tag, offset_bits=offset_bits,
                max_encoded_size=chunk.stored_size, verify_roundtrip=True,
            )
            strategy = "retail_greedy"
            break
        except TxtrError as exc:
            if not (str(exc).startswith("VC-LZ stream needs more than the ")
                    or (str(exc).startswith("VC-LZ stream is ") and " exceeds " in str(exc))):
                raise
            from mod_editor.core.nfl2k5_equipment_lz import compress_equipment_optimal

            try:
                encoded = compress_equipment_optimal(
                    candidate, stream_tag=original.stream_tag, offset_bits=offset_bits,
                    max_encoded_size=chunk.stored_size,
                )
                strategy = "optimal_token_parse"
                break
            except TxtrError as optimal_error:
                if not (str(optimal_error).startswith("VC-LZ stream is ")
                        and " exceeds " in str(optimal_error)):
                    raise
                if offset_bits == bit_candidates[-1]:
                    raise
    padding = chunk.stored_size - len(encoded)
    minimum = minimum_vc_lz_overlap_scratch(encoded, chunk.stored_size, len(candidate))
    scratch = chunk.overlap_scratch_bytes
    if padding > scratch or minimum > scratch:
        from nfl_vc_lz_fill import fill_stream
        encoded, _expanded = fill_stream(encoded, candidate, chunk.stored_size, slack=min(scratch, 16))
        padding = chunk.stored_size - len(encoded)
        minimum = minimum_vc_lz_overlap_scratch(encoded, chunk.stored_size, len(candidate))
    _require(padding <= scratch and minimum <= scratch,
             "Equipment cannot fit with the retail loader scratch allowance")
    video = len(candidate) - chunk.system_bytes
    rebuilt = HEADER.pack(
        b"TSET", chunk.stored_size, chunk.system_bytes, video,
        chunk.compression_magic, scratch, chunk.reserved0, chunk.reserved1,
    ) + encoded + bytes(padding)
    actual, checked = decode_chunk(rebuilt, replace(chunk, video_bytes=video,
                                                   overlap_scratch_bytes=scratch))
    _require(actual == candidate and checked is not None
             and checked.consumed_bytes == len(encoded),
             "Independent equipment failed its compressed round trip")
    # The existing receipt type keeps callers and palette-only receipts stable.
    from nfl_txtr import FixedSpanRebuildInfo

    @dataclass(frozen=True)
    class EquipmentRebuildInfo(FixedSpanRebuildInfo):
        strategy: str

    return rebuilt, EquipmentRebuildInfo(
        kind="TSET", stored_size=chunk.stored_size, system_bytes=chunk.system_bytes,
        video_bytes=video, stream_tag=original.stream_tag, offset_bits=offset_bits,
        original_consumed_bytes=original.consumed_bytes,
        original_unused_bytes=chunk.stored_size - original.consumed_bytes,
        recompressed_bytes=len(encoded), zero_padding_bytes=padding,
        original_overlap_scratch_bytes=chunk.overlap_scratch_bytes,
        exact_minimum_overlap_scratch_bytes=minimum,
        required_overlap_scratch_bytes=(max(padding, minimum) + 15) & ~15,
        rebuilt_overlap_scratch_bytes=scratch,
        overlap_scratch_changed=scratch != chunk.overlap_scratch_bytes,
        loader_in_place_end_guard=scratch >= padding,
        loader_in_place_alias_guard=scratch >= minimum,
        template_decoded_matches_input=False, compressed_stream_matches_template=False,
        complete_span_matches_template=False, decoded_sha256=_digest(candidate),
        rebuilt_span_sha256=_digest(rebuilt),
        strategy=strategy,
    )


def _overflow(exc: TxtrError) -> bool:
    message = str(exc)
    return (message.startswith("VC-LZ stream needs more than the ")
            or (message.startswith("VC-LZ stream is ") and " exceeds " in message))


def _rebuild_fixed_span(template_span: bytes, candidate: bytes, *, independent: bool):
    """Share lossless geometry search and keep the retail scratch word.

    Both palette-only and independent imports use greedy/optimal compression,
    then fill the stream when necessary to retain wrapper +0x14. The keyword
    remains part of the compile interface; decoded growth is read from bytes.
    """

    return _rebuild_grown_video(template_span, candidate)


def decode_equipment_levels(decoded: bytes, chunk: Any, texture: TextureInfo) -> list[bytes]:
    """Decode every declared level using its descriptor and one BGRA palette."""
    levels = []
    cursor = texture.pixel_offset
    for level in range(texture.mip_levels):
        width, height = max(1, texture.width >> level), max(1, texture.height >> level)
        levels.append(texture_to_rgba(decoded, chunk, replace(
            texture, pixel_offset=cursor, width=width, height=height, mip_levels=1,
        )))
        cursor += width * height
    return levels


def apply_equipment_span(current: bytes, replacement: bytes,
                         receipt: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Exact-span replay gate used by offline proofs and bounded callers.

    The disc compositor already provides the same before/after hash gate for
    physical writes. This pure operation cannot append twice or accept a mixed
    chunk, and validates the replacement before returning any changed bytes.
    """
    target, after = receipt["target"], receipt["replacement"]
    _require(len(current) == len(replacement) == target["span_size"] == after["span_size"]
             and _digest(replacement) == after["span_sha256"],
             "Equipment replacement or fixed span changed")
    digest = _digest(current)
    _require(digest in (target["span_sha256"], after["span_sha256"]),
             "Equipment TSET contains mixed or foreign bytes")
    return replacement, {"changed": digest != after["span_sha256"],
                         "before_sha256": digest, "after_sha256": after["span_sha256"],
                         "span_size": len(replacement)}


def _project_palette(
    indices: list[bytes], levels: list[Any], maximum: int
) -> tuple[bytes, int]:
    try:
        from .equipment_palette import representatives, distance
    except ImportError:  # loaded by file path (the unified provider's sealed bundle has no package)
        from mod_editor.core.equipment_palette import representatives, distance

    buckets = [Counter() for _ in range(256)]
    base_indices = set(indices[0])
    for level_number, (index_bytes, level) in enumerate(zip(indices, levels)):
        _require(len(index_bytes) * 4 == len(level.rgba),
                 "Uniform-equipment authored mip/index size differs")
        for palette_index, offset in zip(index_bytes, range(0, len(level.rgba), 4)):
            # Base colours determine every index used by the base. Lower mips
            # may fill unused entries but cannot average away the exported P8.
            if level_number == 0 or palette_index not in base_indices:
                buckets[palette_index][tuple(level.rgba[offset:offset + 4])] += 1
    desired = {
        index: min(bucket, key=lambda c: (-bucket[c], c))
        for index, bucket in enumerate(buckets) if bucket
    }
    histogram: Counter[tuple[int, int, int, int]] = Counter()
    for index, color in desired.items():
        histogram[color] += sum(buckets[index].values())
    colours = representatives(histogram, maximum)
    mapped: list[tuple[int, int, int, int]] = []
    for index in range(256):
        color = desired.get(index)
        if color is None:
            mapped.append((0, 0, 0, 0))
            continue
        mapped.append(min(
            colours,
            key=lambda candidate: (
                distance(color, candidate),
                candidate,
            ),
        ))
    return palette_tools.palette_bytes(mapped), len(colours)


def _quality(requested: bytes, actual: bytes) -> dict[str, int]:
    _require(len(requested) == len(actual), "Equipment preview size changed")
    squared = 0
    maximum = 0
    differing = 0
    for offset in range(0, len(requested), 4):
        changed = False
        for channel in range(4):
            error = abs(requested[offset + channel] - actual[offset + channel])
            squared += error * error
            maximum = max(maximum, error)
            changed = changed or bool(error)
        differing += int(changed)
    return {
        "differing_pixel_count": differing,
        "maximum_channel_error": maximum,
        "total_pixel_count": len(requested) // 4,
        "total_squared_rgba_error": squared,
    }


@dataclass(frozen=True)
class _CompiledGroup:
    """One physical TSET compile, independent of which package asked for it.

    Identical retail spans (Tennessee's ``28H0`` shoe chunk is byte-identical
    in 169 other packages) receiving identical artwork produce identical
    bytes, so a global variant staged across every sampled package compiles
    once per distinct span. Package identity (asset IDs, set selectors, pack
    offsets, preview names) is layered on afterwards, never cached.
    """

    rebuilt_span: bytes
    rebuilt_decoded_sha256: str
    video_end: int
    rebuild_info: Any
    decode_offset_bits: int
    attempts: tuple[dict[str, Any], ...]
    independent: frozenset[int]
    edit_templates: dict[int, dict[str, Any]]
    previews: dict[int, bytes]


def _rows_signature(rows: tuple[EquipmentTarget, ...]) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (item.reference_index, item.name, item.width, item.height, item.pixel_offset,
         item.palette_offset, item.packed_format, item.packed_size, item.descriptor_flags,
         item.base_pixel_sha256, item.palette_bgra_sha256)
        for item in rows
    )


def _compile_group(
    template_span: bytes,
    chunk: Any,
    decoded: bytes,
    decode_info: Any,
    rows: tuple[EquipmentTarget, ...],
    authored: dict[int, tuple[EquipmentTarget, bytes, bytes, list[Any]]],
    independent: set[int],
) -> _CompiledGroup:
    textures, indices = _validate_layout(decoded, chunk, rows)

    # Allocate after ALL original bytes, including palette alignment gaps. Only
    # these selected descriptors move; no sibling ever references the append.
    updated_textures = dict(textures)
    video_end = chunk.video_bytes
    for reference in sorted(independent):
        texture = textures[reference]
        levels = authored[reference][3]
        width, height, count = levels[0].width, levels[0].height, len(levels)
        packed = (texture.packed_format & ~0x0FFF0000) | (count << 16) \
            | ((width.bit_length() - 1) << 20) | ((height.bit_length() - 1) << 24)
        texture = replace(texture, width=width, height=height, mip_levels=count, packed_format=packed)
        start = (video_end + 127) & ~127
        updated_textures[reference] = replace(texture, pixel_offset=start)
        video_end = start + sum(
            max(1, texture.width >> level) * max(1, texture.height >> level)
            for level in range(texture.mip_levels)
        )
    if independent:
        video_end = (video_end + 127) & ~127
    _require(chunk.system_bytes + video_end <= MAX_DECODED_BYTES,
             "Independent equipment exceeds the bounded decoded allocation")

    attempts: list[dict[str, Any]] = []
    rebuilt_decoded: bytes | None = None
    rebuilt_span: bytes | None = None
    rebuild_info: Any | None = None
    selected_entries: dict[int, int] = {}
    selected_quality: dict[int, Any] = {}
    tried: set[str] = set()
    for maximum in PALETTE_LIMITS:
        candidate = bytearray(decoded + bytes(video_end - chunk.video_bytes))
        entries: dict[int, int] = {}
        qualities: dict[int, Any] = {}
        try:
            for reference, (target, _payload, _rgba, levels) in sorted(authored.items()):
                if reference in independent:
                    from mod_editor.core.equipment_palette import quantize

                    colors, index_levels, quality = quantize(levels, maximum)
                    palette, actual_entries = palette_tools.palette_bytes(colors), len(colors)
                    qualities[reference] = quality
                    texture = updated_textures[reference]
                    struct.pack_into("<I", candidate, texture.descriptor_offset + 4,
                                     texture.pixel_offset)
                    struct.pack_into("<I", candidate, texture.descriptor_offset + 12,
                                     texture.packed_format)
                    cursor = chunk.system_bytes + texture.pixel_offset
                    for level, level_indices in zip(levels, index_levels):
                        swizzled = swizzle_2d(level_indices, level.width, level.height, 1)
                        candidate[cursor:cursor + len(swizzled)] = swizzled
                        cursor += len(swizzled)
                else:
                    palette, actual_entries = _project_palette(indices, levels, maximum)
                entries[reference] = actual_entries
                start = chunk.system_bytes + target.palette_offset
                candidate[start:start + PALETTE_BYTES] = palette
        except ValidationError as exc:
            attempts.append({"maximum_palette_entries": maximum,
                             "result": "coverage_quality_refused", "reason": str(exc)})
            continue
        signature = _digest(candidate)
        if signature in tried:
            continue
        tried.add(signature)
        try:
            span, info = _rebuild_fixed_span(template_span, bytes(candidate), independent=bool(independent))
        except TxtrError as exc:
            message = str(exc)
            if not (
                message.startswith("VC-LZ stream needs more than the ")
                or (message.startswith("VC-LZ stream is ") and " exceeds " in message)
            ):
                raise UniformEquipmentWriterError(message) from exc
            attempts.append({
                "maximum_palette_entries": maximum,
                "palette_entries": entries,
                "result": "vc_lz_overflow",
            })
            continue
        rebuilt_decoded = bytes(candidate)
        rebuilt_span = span
        rebuild_info = info
        selected_entries = entries
        selected_quality = qualities
        attempts.append({
            "encoded_bytes": info.recompressed_bytes,
            "maximum_palette_entries": maximum,
            "palette_entries": entries,
            "result": "fit",
        })
        break
    _require(
        rebuilt_decoded is not None and rebuilt_span is not None,
        f"This equipment art cannot fit inside the retail {chunk.stored_size:,}-byte TSET "
        + ("while keeping its complete smaller images and edge coverage. " if independent
           else "even with a two-colour palette. ")
        + "Choose a smaller game image, fewer colours or simpler shapes and try again.",
    )
    assert rebuild_info is not None

    decoded_roundtrip, roundtrip_info = decode_chunk(
        rebuilt_span,
        type(chunk)(
            index=chunk.index,
            offset=0,
            kind=chunk.kind,
            stored_size=chunk.stored_size,
            system_bytes=chunk.system_bytes,
            video_bytes=video_end,
            compression_magic=chunk.compression_magic,
            overlap_scratch_bytes=chunk.overlap_scratch_bytes,
            reserved0=chunk.reserved0,
            reserved1=chunk.reserved1,
        ),
    )
    _require(
        roundtrip_info is not None and decoded_roundtrip == rebuilt_decoded,
        "Rebuilt uniform-equipment TSET failed independent decode",
    )

    selected_ranges = {
        (
            chunk.system_bytes + target.palette_offset,
            chunk.system_bytes + target.palette_offset + PALETTE_BYTES,
        )
        for target, _payload, _rgba, _levels in authored.values()
    }
    selected_ranges.update(
        (textures[reference].descriptor_offset + 4, textures[reference].descriptor_offset + 8)
        for reference in independent
    )
    selected_ranges.update(
        (textures[reference].descriptor_offset + 12, textures[reference].descriptor_offset + 16)
        for reference in independent
    )
    cursor = 0
    for start, end in sorted(selected_ranges):
        _require(decoded[cursor:start] == rebuilt_decoded[cursor:start],
                 "Uniform-equipment rebuild changed bytes outside selected palettes")
        cursor = end
    _require(decoded[cursor:] == rebuilt_decoded[cursor:len(decoded)],
             "Uniform-equipment rebuild changed bytes outside selected palettes")

    previews: dict[int, bytes] = {}
    edit_templates: dict[int, dict[str, Any]] = {}
    for reference, (target, _payload, authored_rgba, levels) in authored.items():
        before = texture_to_rgba(decoded, chunk, textures[reference])
        texture = updated_textures[reference]
        after_levels = decode_equipment_levels(
            rebuilt_decoded, replace(chunk, video_bytes=video_end), texture,
        )
        after = after_levels[0]
        try:
            from .equipment_palette import quality as palette_quality
        except ImportError:  # loaded by file path (no package)
            from mod_editor.core.equipment_palette import quality as palette_quality
        measured = palette_quality(levels[0].rgba if reference in independent else authored_rgba, after)
        overflow = any(attempt["result"] == "vc_lz_overflow" for attempt in attempts)
        measured["merge_reason"] = (
            f"to fit the fixed {chunk.stored_size:,}-byte compressed TSET budget"
            if overflow else "to fit the shared retail index artwork; choose its own texture for a new design"
            if reference not in independent else "to fit the 256-colour P8 palette"
        )
        selected_quality[reference] = measured
        _require(before != after or reference in independent,
                 f"Replacement equals retail for {target.asset_id}")
        preview = encode_rgba_png(texture.width, texture.height, after)
        previews[reference] = preview
        edit_templates[reference] = {
            "name": target.name,
            "palette_entries": selected_entries[reference],
            "palette_offset": target.palette_offset,
            "preview_sha256": _digest(preview),
            "projection_quality": _quality(
                levels[0].rgba if reference in independent else authored_rgba, after,
            ),
            "reference_index": reference,
            "import_mode": OWN_TEXTURE if reference in independent else PALETTE_ONLY,
            "descriptor_offset": texture.descriptor_offset,
            "pixel_offset": texture.pixel_offset,
            "requested_dimensions": [target.width, target.height],
            "encoded_dimensions": [texture.width, texture.height],
            "mip_levels": texture.mip_levels,
            "size_reduction": target.width // texture.width,
            "mip_filter": ("premultiplied_rgba_area_from_base"
                           if reference in independent else "retail_index_projection"),
            "palette_quality": selected_quality[reference],
            "levels": [
                {"level": level.level, "width": level.width, "height": level.height,
                 "pixel_offset": texture.pixel_offset + sum(
                     previous.width * previous.height for previous in levels[:level.level]
                 ), "input_rgba_sha256": _digest(level.rgba),
                 "decoded_rgba_sha256": _digest(actual),
                 "quality": _quality(level.rgba, actual)}
                for level, actual in zip(levels, after_levels)
            ],
        }

    for target in rows:
        if target.reference_index in authored:
            continue
        before_levels = decode_equipment_levels(decoded, chunk, textures[target.reference_index])
        after_levels = decode_equipment_levels(
            rebuilt_decoded, chunk, textures[target.reference_index]
        )
        _require(before_levels == after_levels,
                 f"Editing equipment changed sibling {target.asset_id}")

    return _CompiledGroup(
        rebuilt_span=rebuilt_span,
        rebuilt_decoded_sha256=_digest(rebuilt_decoded),
        video_end=video_end,
        rebuild_info=rebuild_info,
        decode_offset_bits=decode_info.offset_bits,
        attempts=tuple(attempts),
        independent=frozenset(independent),
        edit_templates=edit_templates,
        previews=previews,
    )


def build_unified_uniform_equipment_imports(
    index: Path,
    edits: Iterable[tuple[str, Path]],
    *,
    pack_hashes: dict[str, str] | None = None,
    catalog_path: Path = DEFAULT_CATALOG,
    compile_cache: EquipmentCompileCache | None = None,
) -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    """Compile logical edits sharing one TSET into one fixed physical span.

    ``compile_cache`` lets one build reuse the compiled bytes of a retail span
    it has already compiled with the same artwork (see
    :class:`EquipmentCompileCache`); package identity is never cached.
    """

    requested = tuple((str(asset_id), Path(path)) for asset_id, path in edits)
    _require(bool(requested), "Choose at least one uniform-equipment texture")
    by_id, groups = load_targets(catalog_path)
    selected: list[tuple[EquipmentTarget, Path]] = []
    seen: set[str] = set()
    for asset_id, path in requested:
        target = by_id.get(asset_id)
        _require(target is not None,
                 f"{asset_id} is not a reviewed uniform-equipment P8 target")
        _require(asset_id not in seen, f"Uniform-equipment edit repeats {asset_id}")
        seen.add(asset_id)
        assert target is not None
        selected.append((target, path))
    physical = {(item.outer_index, item.chunk_index) for item, _path in selected}
    _require(len(physical) == 1,
             "One uniform-equipment compile may target only one physical TSET")
    outer_index, chunk_index = next(iter(physical))
    rows = groups[(outer_index, chunk_index)]

    archive = parse_archive(Path(index))
    _require(0 <= outer_index < len(archive.entries),
             "Uniform-equipment outer selector is outside the private archive")
    entry = archive.entries[outer_index]
    _require(entry.size <= MAX_PACKAGE_BYTES and len(entry.segments) >= 1,
             "Uniform-equipment package is too large or has no pack extent")
    package = read_entry_bytes(archive, entry)
    matches = [
        chunk for chunk in parse_chunks(package, allow_trailing=True)
        if chunk.index == chunk_index and chunk.kind == "TSET"
    ]
    _require(len(matches) == 1,
             "Uniform-equipment TSET selector is absent or ambiguous")
    chunk = matches[0]
    # Three uniform packages straddle two pack files (01H11, 25H3, 24A10). The
    # physical edit is the one TSET span, so it is writable whenever that span
    # lies inside a single extent; only a span crossing the seam is read-only.
    segment = None
    segment_start = 0
    for candidate_segment in entry.segments:
        if (segment_start <= chunk.offset
                and chunk.end_offset <= segment_start + candidate_segment.size):
            segment = candidate_segment
            break
        segment_start += candidate_segment.size
    _require(segment is not None,
             "Uniform-equipment TSET span crosses pack extents and is read-only")
    _require(chunk.output_size <= MAX_DECODED_BYTES,
             "Equipment decoded allocation exceeds the reviewed size bound")
    template_span = package[chunk.offset:chunk.end_offset]
    template_sha256 = _digest(template_span)
    # The stream geometry is the wrapper's, so it is read from the template
    # header without a full decode; the compile itself decodes and validates.
    _require(chunk.compressed, "Uniform-equipment TSET is not compressed")

    authored: dict[int, tuple[EquipmentTarget, bytes, bytes, list[Any]]] = {}
    independent: set[int] = set()
    input_rows: list[dict[str, Any]] = []
    signature: list[tuple[int, str, str, int]] = []
    for target, path in selected:
        payload, rgba, levels = _read_png(path, target, compile_cache)
        authored[target.reference_index] = (target, payload, rgba, levels)
        mode, scale = import_settings(payload, target.asset_id, rgba)
        if mode == OWN_TEXTURE:
            independent.add(target.reference_index)
        signature.append((target.reference_index, _digest(rgba), mode, scale))
        input_rows.append({
            "target": target.asset_id,
            "path": str(path.resolve(strict=True)),
            "file_name": path.name,
            "sha256": _digest(payload),
            "rgba_sha256": _digest(rgba),
            "width": target.width,
            "height": target.height,
            "import_mode": mode,
        })

    if independent:
        _require(_chain_pins().get((outer_index, chunk_index)) == template_sha256,
                 "Independent equipment TSET no longer matches the complete retail source pin")

    key = (template_sha256, chunk_index, chunk.stored_size, chunk.system_bytes, chunk.video_bytes,
           chunk.overlap_scratch_bytes, _rows_signature(rows), tuple(sorted(signature)))
    compiled = compile_cache.compiled.get(key) if compile_cache is not None else None
    if compiled is None:
        decoded, decode_info = decode_chunk(package, chunk)
        _require(decode_info is not None, "Uniform-equipment TSET is not compressed")
        compiled = _compile_group(template_span, chunk, decoded, decode_info, rows, authored, independent)
        if compile_cache is not None:
            compile_cache.compiled[key] = compiled
            compile_cache.misses += 1
            while len(compile_cache.compiled) > compile_cache.compiled_limit:
                compile_cache.compiled.popitem(last=False)
    else:
        compile_cache.compiled.move_to_end(key)
        compile_cache.hits += 1
    rebuilt_span = compiled.rebuilt_span
    rebuild_info = compiled.rebuild_info

    previews: list[tuple[str, bytes]] = []
    edit_reports: list[dict[str, Any]] = []
    for target, _path in selected:
        preview_name = (
            f"equipment_{outer_index}_{chunk_index}_"
            f"{target.reference_index}_{target.name}.png"
        )
        previews.append((preview_name, compiled.previews[target.reference_index]))
        template = compiled.edit_templates[target.reference_index]
        edit_reports.append({
            "asset_id": target.asset_id,
            "name": template["name"],
            "palette_entries": template["palette_entries"],
            "palette_offset": template["palette_offset"],
            "preview_file": preview_name,
            "preview_sha256": template["preview_sha256"],
            "projection_quality": dict(template["projection_quality"]),
            "reference_index": template["reference_index"],
            "set_selector": target.set_selector,
            "import_mode": template["import_mode"],
            "descriptor_offset": template["descriptor_offset"],
            "pixel_offset": template["pixel_offset"],
            "requested_dimensions": list(template["requested_dimensions"]),
            "encoded_dimensions": list(template["encoded_dimensions"]),
            "mip_levels": template["mip_levels"],
            "size_reduction": template["size_reduction"],
            "mip_filter": template["mip_filter"],
            "palette_quality": template["palette_quality"],
            "levels": [dict(level, quality=dict(level["quality"])) for level in template["levels"]],
        })

    pack = archive.packs[segment.pack_ordinal]
    hashes = pack_hashes if pack_hashes is not None else {}
    if pack.name not in hashes:
        hashes[pack.name] = _file_digest(pack.path)
    span_size = len(template_span)
    pack_offset = segment.pack_offset + (chunk.offset - segment_start)
    selector = f"uniform-equipment-tset:{outer_index}:{chunk_index}"
    target_record = {
        "chunk_index": chunk_index,
        "format": "P8 independent mip chains" if independent else "P8 shared-index palettes",
        "outer_index": outer_index,
        "pack_offset": pack_offset,
        "selector": selector,
        "span_sha256": template_sha256,
        "span_size": span_size,
        "xiso_absolute_span_offset": pack_offset,
        "xiso_pack_path": f"vc_53450030/{pack.name}",
        # Layout-dependent and deliberately ignored when binding the user's
        # XISO. The absolute offset is re-derived from the located pack extent.
        "xiso_pack_sector": 0,
        "xiso_pack_sha256": hashes[pack.name],
        "xiso_pack_size": pack.size,
    }
    report = {
        "schema": "nfl2k5_uniform_equipment_texture_import/v1",
        "experimental_unwitnessed": bool(independent),
        "allocation": {
            "original_video_bytes": chunk.video_bytes, "video_bytes": compiled.video_end,
            "added_video_bytes": compiled.video_end - chunk.video_bytes,
            "system_bytes": chunk.system_bytes,
            "load_allocation_bytes": chunk.system_bytes + compiled.video_end
                                     + rebuild_info.rebuilt_overlap_scratch_bytes,
            "independent_variant_count": len(independent),
        },
        "compression": asdict(rebuild_info),
        "lossless_offset_bit_candidates": (
            list(dict.fromkeys((compiled.decode_offset_bits, 10, 11, 12)))
            if independent or getattr(rebuild_info, "strategy", None) is not None
            else [compiled.decode_offset_bits]),
        "bounded_palette_fit": {
            "attempts": [dict(attempt) for attempt in compiled.attempts],
            "selected_encoded_bytes": rebuild_info.recompressed_bytes,
            "stored_size_bound": chunk.stored_size,
        },
        "edits": edit_reports,
        "input_pngs": input_rows,
        "replacement": {
            "decoded_sha256": compiled.rebuilt_decoded_sha256,
            "span_sha256": _digest(rebuilt_span),
            "span_size": len(rebuilt_span),
            "zero_padding_bytes": rebuild_info.zero_padding_bytes,
        },
        "target": target_record,
        "claims": {
            "fixed_tset_span_only": True,
            "selected_palette_allocations_only": not independent,
            "shared_index_and_mip_chain_preserved": True,
            "unselected_palette_bytes_and_pixels_preserved": True,
            "system_descriptors_and_names_preserved": not independent,
            "only_selected_pixel_pointers_and_format_words_changed": bool(independent),
            "all_sibling_mips_preserved": True,
            "runtime_visibility_proved": False,
        },
    }
    return rebuilt_span, previews, report, selector, target_record


__all__ = [
    "BINDING_TABLE_ROWS",
    "CATALOG_SHA256",
    "CATALOG_SIZE",
    "CONTEXT_FIRST_NAMES",
    "DEFAULT_CATALOG",
    "EquipmentTarget",
    "GLOBAL_LOOKUP_NAMES",
    "SHOE_STYLE_NAMES",
    "EquipmentCompileCache",
    "UniformEquipmentWriterError",
    "build_unified_uniform_equipment_imports",
    "consumer_targets",
    "decode_equipment_levels",
    "apply_equipment_span",
    "in_game_lookup",
    "load_targets",
    "sampled_package",
]
