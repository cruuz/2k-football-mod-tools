"""Bounded NFL 2K5 Stadium Studio P8 texture writer.

This module deliberately does not claim a general SCNE serializer.  It
resolves the canonical Stadium Studio selector back through the user's own
resource inventory, replays the strict SCNE parser, and accepts only embedded
P8 descriptors whose dimensions, complete mip chain, palette, material
ownership, compressed resource span, and single-pack XISO ownership can all be
proved from that source.  A user-authored RGBA8 PNG is compiled into the
existing fixed pixel/palette allocations and the complete SCNE is recompressed
without changing its size.

The source XISO and private archive cache are opened read-only.  Compiled SCNE
bytes exist only in memory and in the user's complete output XISO; shareable
edit state contains only the supplied PNG and metadata derived from it.

The original ``cement01`` constants and standalone verifier remain as a
backward-compatible receipt for the first runtime-proved target.  Product
builds use the dynamic resolver below; no retail catalog or payload ships.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
from typing import Any, Iterable, Mapping, Sequence

try:
    from .errors import ValidationError
    from .json_stream import iter_top_level_array, require_regular_file
    from .nfl2k5_source_cache import SOURCE_SHA256, SourceCache
    from .nfl2k5_stadium_cache import StadiumCacheResult
    from .nfl2k5_stadium_studio import StadiumTexture
    from . import platform_compat
except ImportError:
    # The sealed unified provider loads this reviewed file directly from its
    # pinned execution bundle.  Its narrow span compiler needs no product
    # package imports, so keep that execution closure explicit and tiny.
    class ValidationError(ValueError):
        pass

    SOURCE_SHA256 = (
        "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
    )
    SourceCache = Any  # type: ignore[misc,assignment]
    StadiumCacheResult = Any  # type: ignore[misc,assignment]

    @dataclass(frozen=True)
    class StadiumTexture:  # type: ignore[no-redef]
        texture_id: str
        scene_id: str
        texture_index: int
        width: int
        height: int
        format_name: str
        rgba_sha256: str
        png_sha256: str
        png_path: Path
        mapped_material_names: tuple[str, ...]
        mapped_material_count: int
        access_status: str

    def require_regular_file(path: Path, label: str) -> os.stat_result:
        try:
            info = path.lstat()
        except FileNotFoundError as exc:
            raise ValidationError(f"{label} is missing: {path}") from exc
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValidationError(f"{label} must be a regular file: {path}")
        return info

    def iter_top_level_array(*_args: object, **_kwargs: object) -> Any:
        raise ValidationError(
            "Private Stadium manifests are unavailable in unified-provider mode"
        )

    from types import SimpleNamespace

    def _positional_read(fd: int, count: int, offset: int) -> bytes:
        # Byte-identical stand-in for platform_compat.pread used only by the
        # flat sealed-provider closure, which has no package context to import
        # the sibling from.  That closure runs on the POSIX build host, so the
        # positional-read primitive is present and used directly; the seek
        # fallback exists purely so this never regresses another platform.
        primitive = getattr(os, "pread", None)
        if primitive is not None:
            return primitive(fd, count, offset)
        if count <= 0:
            return b""
        restore = os.lseek(fd, 0, os.SEEK_CUR)
        try:
            os.lseek(fd, offset, os.SEEK_SET)
            return os.read(fd, count)
        finally:
            os.lseek(fd, restore, os.SEEK_SET)

    platform_compat = SimpleNamespace(pread=_positional_read)


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from nfl_tset_png_import import (  # noqa: E402
    ImportError as PngImportError,
    MipLevel,
    decode_rgba_png,
    palette_bytes,
    quantize_levels,
    rgba_from_indices,
)
from nfl_txtr import (  # noqa: E402
    HEADER,
    TxtrError,
    compress_vc_lz,
    decompress_vc_lz,
    encode_rgba_png,
    minimum_vc_lz_overlap_scratch,
    swizzle_2d,
    unswizzle_2d,
)
import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402
from nfl_outer import (  # noqa: E402
    FormatError as OuterFormatError,
    parse_archive,
    read_entry_range,
)
from nfl_scene_probe import (  # noqa: E402
    ProbeError,
    ResourceRecord,
    decode_resource,
    parse_inventory,
)
from nfl_scne_inventory import ScneError, parse_scene  # noqa: E402


BUILD_SCHEMA = "2k5_mod_studio_stadium_texture_xiso/v1"
GENERAL_BUILD_SCHEMA = "2k5_mod_studio_stadium_p8_texture_xiso/v2"
UNIFIED_IMPORT_SCHEMA = "nfl2k5_stadium_texture_unified_import/v2"
SELECTOR_RE = re.compile(
    r"nfl2k5\.stadium\.o(?P<outer>\d{4})\.c(?P<chunk>\d{4})\."
    r"scene(?P<scene>\d{4})\.texture(?P<texture>\d{4})\Z"
)
TARGET_SCENE_ID = "nfl2k5.stadium.o3280.c0005.scene2648"
TARGET_TEXTURE_ID = f"{TARGET_SCENE_ID}.texture0002"
TARGET_MATERIAL_NAME = "cement01"
TARGET_MATERIAL_INDEX = 3

PACK_PATH = "vc_53450030/9"
PACK_NAME = "9"
PACK_SECTOR = 35_531
PACK_SIZE = 634_941_440
PACK_SHA256 = "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a"
INDEX_PATH = "vc_53450030/0"
INDEX_SECTOR = 796_479
INDEX_SIZE = 193_710_080
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
XDVDFS_FILE_COUNT = 19

OUTER_INDEX = 3280
OUTER_ID = "0xe4d6b0bc"
CHUNK_INDEX = 5
CHUNK_ENTRY_OFFSET = 0x5EA40
CHUNK_PACK_OFFSET = 0x07EA5A40
CHUNK_STORED_SIZE = 908_880
CHUNK_SPAN_SIZE = HEADER.size + CHUNK_STORED_SIZE
CHUNK_SPAN_SHA256 = "0cd1977a6097851f9366d935098bdd9e97144f3ffce0f8690593c2623fbbd73a"
SYSTEM_BYTES = 577_792
VIDEO_BYTES = 947_072
DECODED_SIZE = SYSTEM_BYTES + VIDEO_BYTES
DECODED_SHA256 = "229db9f309bf69eaa28901ae6e2e15b26a279b3f1f37abed01e36041c5e5ead8"
RETAIL_CONSUMED = 908_864
RETAIL_SCRATCH = 16
OPAQUE_TAIL_SIZE = 16
OPAQUE_TAIL_SHA256 = "cb57e42b9b8d9e1cba31e18c38dbc3347c8caa1361fcf7fe9cfad5b9f138fae4"
SCNE_OBSERVED_SCRATCH_MAX = 3_120

# All 477 private-cache stadium resources resolve wholly inside archive pack 8
# or 9.  These are identity metadata for the recognized retail XISO, not game
# bytes.  Dynamic resolution still proves the selected span from the user's
# own extracted packs and the unified provider rechecks the complete XISO pack.
STADIUM_PACKS: Mapping[str, tuple[int, int, str]] = {
    "8": (
        1_574_589,
        929_370_112,
        "265560a55bebc13e5c8bfbe7770dac2032624946b4767fad72191bb3266aca14",
    ),
    "9": (PACK_SECTOR, PACK_SIZE, PACK_SHA256),
}

TEXTURE_INDEX = 2
DESCRIPTOR_OFFSET = 0x5160
DESCRIPTOR_SIZE = 0x20
DESCRIPTOR_SHA256 = "d447cd630fe37ac3b5ab488971eb09d78754ec80754dbd72a88d0db47ce103fe"
MATERIAL_OFFSET = 0x5880
MATERIAL_SIZE = 0x80
MATERIAL_SHA256 = "63bb94564367521a2edc21fb33d355db9056a9b73a2b139c44f5fc7a78086efc"
TEXTURE_POINTER_FIELD = 0x58B0
PIXEL_OFFSET = 0x17300
PALETTE_OFFSET = 0x18840
PACKED_FORMAT = 0x06640B29
PACKED_SIZE = 0
DESCRIPTOR_FLAGS = 0x80000000
FORMAT_CODE = 0x0B
FORMAT_NAME = "P8"
MIP_DIMENSIONS = ((64, 64), (32, 32), (16, 16), (8, 8))
INDEX_CHAIN_BYTES = sum(width * height for width, height in MIP_DIMENSIONS)
PALETTE_BYTES = 1_024
STOCK_INDEX_SHA256 = "8628b0331fbb666082a167b22efdce5c400f21cd9bb6d8d04e4a47ff5c79b82d"
STOCK_PALETTE_SHA256 = "d4e1b89455a4d3366852d00572954a193374f8b06fec9d534bc7716c99a5573a"
STOCK_RGBA_SHA256 = "1da60e33174a818d47a239d467c69f9a7ec5b421aa9c5583356014b1bfa45b31"
STOCK_PNG_SHA256 = "f0db68aceb90f681a5d75b902b1686cf109cee13682c927a757f4291961fc28b"
STOCK_MIP_RGBA_SHA256 = (
    STOCK_RGBA_SHA256,
    "571772e3a58c6c59dd06c20b3a078e8111bb9bc17346890e1f4d13738d35bb2f",
    "a28b82df9ff01119f3b150e5cc171effeaff5676f0d2fdd3b7b386fa52e32566",
    "b5dea06667a5bd0fd2d88b0cc2546d149fa32ca127d0ce49761d1f180b5c6166",
)

ABSOLUTE_XISO_SPAN = PACK_SECTOR * xiso.SECTOR_SIZE + CHUNK_PACK_OFFSET
COPY_BLOCK = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024

FIXED_ALLOCATION_ERROR = (
    "This image cannot fit the stadium's fixed SCNE allocation after lossless "
    "resource compression. Simplify large noisy or detail-heavy areas; the "
    "source XISO and current edit are unchanged."
)
UNSUPPORTED_FORMAT_ERROR = (
    "That Stadium texture is export-only because it is not a bounded embedded "
    "P8 texture with a complete fixed mip/palette allocation."
)
SHARED_OWNERSHIP_NOTE = (
    "This embedded texture is owned by the cement01 material. All 33 surfaces "
    "linked to cement01 in this scene change together, including roof, the "
    "proved group36 wall, and the other listed structural groups."
)


class StadiumTextureWriterError(ValidationError):
    """The bounded target or output violated its fixed contract."""


@dataclass(frozen=True)
class StadiumP8TargetContract:
    texture_id: str = TARGET_TEXTURE_ID
    scene_id: str = TARGET_SCENE_ID
    texture_index: int = TEXTURE_INDEX
    material_index: int = TARGET_MATERIAL_INDEX
    material_name: str = TARGET_MATERIAL_NAME
    width: int = 64
    height: int = 64
    mip_dimensions: tuple[tuple[int, int], ...] = MIP_DIMENSIONS
    format_name: str = FORMAT_NAME
    shared_ownership_note: str = SHARED_OWNERSHIP_NOTE


@dataclass(frozen=True)
class DynamicStadiumP8Contract:
    """Source-derived fixed-allocation contract for one Stadium occurrence."""

    texture_id: str
    scene_id: str
    outer_index: int
    outer_id: str
    chunk_index: int
    scene_index: int
    texture_index: int
    width: int
    height: int
    mip_dimensions: tuple[tuple[int, int], ...]
    format_name: str
    descriptor_offset: int
    pixel_offset: int
    palette_offset: int
    packed_format: int
    packed_size: int
    descriptor_flags: int
    mapped_material_names: tuple[str, ...]
    mapped_material_count: int
    rgba_sha256: str
    pack_name: str
    pack_sector: int
    pack_size: int
    pack_sha256: str
    pack_offset: int
    chunk_offset: int
    stored_size: int
    system_bytes: int
    video_bytes: int
    decoded_sha256: str
    source_span_sha256: str
    retail_consumed: int
    retail_scratch: int
    opaque_tail_size: int
    opaque_tail_sha256: str
    shared_ownership_note: str

    @property
    def span_size(self) -> int:
        return HEADER.size + self.stored_size

    @property
    def index_chain_bytes(self) -> int:
        return sum(width * height for width, height in self.mip_dimensions)

    @property
    def xiso_pack_path(self) -> str:
        return f"vc_53450030/{self.pack_name}"

    @property
    def absolute_xiso_span(self) -> int:
        return self.pack_sector * xiso.SECTOR_SIZE + self.pack_offset

    def target_metadata(self) -> dict[str, object]:
        return {
            "selector": self.texture_id,
            "texture_id": self.texture_id,
            "scene_id": self.scene_id,
            "outer_index": self.outer_index,
            "outer_id": self.outer_id,
            "chunk_index": self.chunk_index,
            "scene_index": self.scene_index,
            "texture_index": self.texture_index,
            "dimensions": [self.width, self.height],
            "mip_dimensions": [list(value) for value in self.mip_dimensions],
            "format": self.format_name,
            "mapped_material_names": list(self.mapped_material_names),
            "mapped_material_count": self.mapped_material_count,
            "shared_ownership_note": self.shared_ownership_note,
            "xiso_pack_path": self.xiso_pack_path,
            "xiso_pack_sector": self.pack_sector,
            "xiso_pack_size": self.pack_size,
            "xiso_pack_sha256": self.pack_sha256,
            "pack_offset": self.pack_offset,
            "xiso_absolute_span_offset": self.absolute_xiso_span,
            "span_size": self.span_size,
            "span_sha256": self.source_span_sha256,
        }


@dataclass(frozen=True)
class CompiledStadiumTextureEdit:
    """In-memory private build input; ``rebuilt_span`` is never project data."""

    texture_id: str
    replacement_png_sha256: str
    replacement_rgba_sha256: str
    quantized_preview_png_sha256: str
    quantized_base_rgba_sha256: str
    mip_rgba_sha256: tuple[str, ...]
    quantization: dict[str, int]
    palette_entries: int
    decoded_after_sha256: str
    decoded_changed_byte_count: int
    encoded_sha256: str
    encoded_bytes: int
    zero_gap_bytes: int
    minimum_alias_scratch_bytes: int
    scratch_after: int
    source_span_sha256: str
    rebuilt_span_sha256: str
    quantized_preview_png: bytes = field(repr=False)
    rebuilt_span: bytes = field(repr=False)
    target_metadata: dict[str, object] = field(default_factory=dict)

    def public_metadata(self) -> dict[str, object]:
        """Return only user-authored/derived metadata, never retail bytes."""

        value = asdict(self)
        value.pop("quantized_preview_png")
        value.pop("rebuilt_span")
        return value


@dataclass(frozen=True)
class StadiumTextureBuildResult:
    output_xiso: Path
    manifest: Path
    output_sha256: str
    output_pack_sha256: str
    changed_byte_count: int
    changed_run_count: int
    copy_method: str


@dataclass(frozen=True)
class _SourceScne:
    span: bytes = field(repr=False)
    decoded: bytes = field(repr=False)
    opaque_tail: bytes = field(repr=False)


@dataclass(frozen=True)
class _ResolvedStadiumScene:
    contract: DynamicStadiumP8Contract
    resource: ResourceRecord
    span: bytes = field(repr=False)
    decoded: bytes = field(repr=False)
    opaque_tail: bytes = field(repr=False)
    texture_rows: tuple[dict[str, Any], ...] = field(repr=False)


@dataclass(frozen=True)
class _CompiledP8Payload:
    contract: DynamicStadiumP8Contract
    replacement_png_sha256: str
    replacement_rgba_sha256: str
    quantized_preview_png_sha256: str
    quantized_base_rgba_sha256: str
    mip_rgba_sha256: tuple[str, ...]
    quantization: dict[str, int]
    palette_entries: int
    decoded_changed_byte_count: int
    quantized_preview_png: bytes = field(repr=False)


@dataclass(frozen=True)
class _CompiledStadiumScene:
    source: _ResolvedStadiumScene
    textures: tuple[_CompiledP8Payload, ...]
    fixed: _FixedSpanBuild
    decoded_changed_byte_count: int


@dataclass(frozen=True)
class _FixedSpanBuild:
    span: bytes = field(repr=False)
    encoded: bytes = field(repr=False)
    decoded_sha256: str
    encoded_sha256: str
    encoded_bytes: int
    zero_gap_bytes: int
    minimum_alias_scratch_bytes: int
    scratch_after: int


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(COPY_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_fd(fd: int, offset: int = 0, length: int | None = None) -> str:
    digest = hashlib.sha256()
    position = offset
    remaining = length
    while remaining is None or remaining:
        request = COPY_BLOCK if remaining is None else min(COPY_BLOCK, remaining)
        block = platform_compat.pread(fd, request, position)
        if not block:
            break
        digest.update(block)
        position += len(block)
        if remaining is not None:
            remaining -= len(block)
    if length is not None and remaining:
        raise StadiumTextureWriterError("Short bounded read while hashing an XISO extent")
    return digest.hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _aligned16(value: int) -> int:
    return (value + 15) & ~15


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StadiumTextureWriterError(message)


def _rebuild_vc_lz_fixed_span(
    decoded: bytes,
    template_header: bytes,
    opaque_tail: bytes,
    *,
    consumed_cap: int,
    scratch_cap: int,
) -> _FixedSpanBuild:
    """Rebuild one compressed resource while preserving its fixed final tail.

    The parameters make this helper synthetic-testable; the public writer calls
    it only with the pinned stadium contract above.
    """

    _require(len(template_header) == HEADER.size, "SCNE template header size changed")
    fields = HEADER.unpack(template_header)
    kind, stored_size, system_bytes, video_bytes, magic, _scratch, reserved0, reserved1 = fields
    _require(kind == b"SCNE" and magic == 0xFEEDBEEF,
             "Fixed-span template is not a compressed SCNE resource")
    _require(reserved0 == reserved1 == 0, "SCNE reserved wrapper fields changed")
    _require(len(decoded) == system_bytes + video_bytes,
             "Decoded SCNE size differs from wrapper allocation")
    _require(stored_size == consumed_cap + len(opaque_tail),
             "SCNE consumed cap and opaque tail do not fill stored allocation")
    try:
        encoded, _compression = compress_vc_lz(
            decoded,
            stream_tag=1,
            offset_bits=12,
            max_encoded_size=consumed_cap,
            verify_roundtrip=True,
        )
        decoded_back, decode_info = decompress_vc_lz(encoded, len(decoded))
        alias = minimum_vc_lz_overlap_scratch(encoded, stored_size, len(decoded))
    except TxtrError as exc:
        raise StadiumTextureWriterError(FIXED_ALLOCATION_ERROR) from exc
    _require(decoded_back == decoded and decode_info.consumed_bytes == len(encoded),
             "Rebuilt SCNE stream failed its lossless decode check")
    zero_gap = consumed_cap - len(encoded)
    scratch = _aligned16(max(stored_size - len(encoded), alias))
    if scratch > scratch_cap:
        raise StadiumTextureWriterError(FIXED_ALLOCATION_ERROR)
    header = bytearray(template_header)
    struct.pack_into("<I", header, 0x14, scratch)
    span = bytes(header) + encoded + bytes(zero_gap) + opaque_tail
    _require(len(span) == HEADER.size + stored_size,
             "Rebuilt fixed SCNE span changed allocation")
    if opaque_tail:
        _require(span[-len(opaque_tail):] == opaque_tail,
                 "Rebuilt fixed SCNE span changed its opaque tail")
    return _FixedSpanBuild(
        span=span,
        encoded=encoded,
        decoded_sha256=_sha256_bytes(decoded),
        encoded_sha256=_sha256_bytes(encoded),
        encoded_bytes=len(encoded),
        zero_gap_bytes=zero_gap,
        minimum_alias_scratch_bytes=alias,
        scratch_after=scratch,
    )


def _regular(path: Path, label: str) -> Path:
    require_regular_file(path, label)
    return path.resolve(strict=True)


def _generate_mips(rgba: bytes) -> list[MipLevel]:
    _require(len(rgba) == 64 * 64 * 4, "Replacement PNG RGBA size is invalid")
    levels = [MipLevel(0, 64, 64, rgba)]
    current = rgba
    width = 64
    height = 64
    for level in range(1, len(MIP_DIMENSIONS)):
        next_width = width // 2
        next_height = height // 2
        output = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            for x in range(next_width):
                inputs = (
                    ((y * 2) * width + x * 2) * 4,
                    ((y * 2) * width + x * 2 + 1) * 4,
                    (((y * 2) + 1) * width + x * 2) * 4,
                    (((y * 2) + 1) * width + x * 2 + 1) * 4,
                )
                target = (y * next_width + x) * 4
                for channel in range(4):
                    output[target + channel] = (
                        sum(current[source + channel] for source in inputs) + 2
                    ) // 4
        current = bytes(output)
        width = next_width
        height = next_height
        levels.append(MipLevel(level, width, height, current))
    _require(
        tuple((item.width, item.height) for item in levels) == MIP_DIMENSIONS,
        "Generated stadium mip chain has unexpected dimensions",
    )
    return levels


def _decode_p8_mips(decoded: bytes) -> tuple[bytes, ...]:
    pixel_start = SYSTEM_BYTES + PIXEL_OFFSET
    palette_start = SYSTEM_BYTES + PALETTE_OFFSET
    _require(
        pixel_start + INDEX_CHAIN_BYTES <= len(decoded)
        and palette_start + PALETTE_BYTES <= len(decoded),
        "Stadium P8 ranges exceed the decoded SCNE",
    )
    palette_raw = decoded[palette_start:palette_start + PALETTE_BYTES]
    palette = [
        (palette_raw[index + 2], palette_raw[index + 1],
         palette_raw[index], palette_raw[index + 3])
        for index in range(0, PALETTE_BYTES, 4)
    ]
    result: list[bytes] = []
    cursor = pixel_start
    for width, height in MIP_DIMENSIONS:
        size = width * height
        linear = unswizzle_2d(decoded[cursor:cursor + size], width, height, 1)
        result.append(b"".join(bytes(palette[value]) for value in linear))
        cursor += size
    return tuple(result)


def _difference_ledger(before: bytes, after: bytes) -> dict[str, object]:
    _require(len(before) == len(after), "Difference-ledger spans have different sizes")
    offsets = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    offset_hash = hashlib.sha256()
    before_hash = hashlib.sha256()
    after_hash = hashlib.sha256()
    runs: list[tuple[int, int]] = []
    for offset in offsets:
        offset_hash.update(struct.pack("<I", offset))
        before_hash.update(before[offset:offset + 1])
        after_hash.update(after[offset:offset + 1])
        if not runs or runs[-1][1] != offset:
            runs.append((offset, offset + 1))
        else:
            runs[-1] = (runs[-1][0], offset + 1)
    return {
        "changed_byte_count": len(offsets),
        "changed_run_count": len(runs),
        "changed_offset_u32le_sha256": offset_hash.hexdigest(),
        "changed_before_bytes_sha256": before_hash.hexdigest(),
        "changed_after_bytes_sha256": after_hash.hexdigest(),
        "changed_run_pairs_u32le_sha256": _sha256_bytes(
            b"".join(struct.pack("<II", start, end) for start, end in runs)
        ),
    }


def _selector_parts(selector: str) -> tuple[int, int, int, int]:
    match = SELECTOR_RE.fullmatch(selector)
    if match is None:
        raise StadiumTextureWriterError(
            "That Stadium texture selector is not canonical. Re-open Stadium "
            "Studio and choose the texture again."
        )
    return tuple(
        int(match.group(name))
        for name in ("outer", "chunk", "scene", "texture")
    )  # type: ignore[return-value]


def _scene_id_from_parts(outer: int, chunk: int, scene: int) -> str:
    return f"nfl2k5.stadium.o{outer:04d}.c{chunk:04d}.scene{scene:04d}"


def _mip_dimensions(
    width: int, height: int, level_count: int
) -> tuple[tuple[int, int], ...]:
    _require(
        width >= 1
        and height >= 1
        and width & (width - 1) == 0
        and height & (height - 1) == 0
        and 1 <= level_count <= 16,
        UNSUPPORTED_FORMAT_ERROR,
    )
    result: list[tuple[int, int]] = []
    current_width, current_height = width, height
    for _level in range(level_count):
        result.append((current_width, current_height))
        current_width = max(1, current_width // 2)
        current_height = max(1, current_height // 2)
    return tuple(result)


def _generate_dynamic_mips(
    rgba: bytes, dimensions: tuple[tuple[int, int], ...]
) -> list[MipLevel]:
    _require(bool(dimensions), "Stadium texture has no mip levels")
    width, height = dimensions[0]
    _require(
        len(rgba) == width * height * 4,
        "Replacement Stadium PNG RGBA size is invalid",
    )
    levels = [MipLevel(0, width, height, rgba)]
    current = rgba
    for level, (next_width, next_height) in enumerate(dimensions[1:], 1):
        _require(
            next_width == max(1, width // 2)
            and next_height == max(1, height // 2),
            "Stadium texture mip dimensions are not a complete halving chain",
        )
        output = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            y0 = min(height - 1, y * 2)
            y1 = min(height - 1, y * 2 + 1)
            for x in range(next_width):
                x0 = min(width - 1, x * 2)
                x1 = min(width - 1, x * 2 + 1)
                inputs = (
                    (y0 * width + x0) * 4,
                    (y0 * width + x1) * 4,
                    (y1 * width + x0) * 4,
                    (y1 * width + x1) * 4,
                )
                target = (y * next_width + x) * 4
                for channel in range(4):
                    output[target + channel] = (
                        sum(current[source + channel] for source in inputs) + 2
                    ) // 4
        current = bytes(output)
        width, height = next_width, next_height
        levels.append(MipLevel(level, width, height, current))
    return levels


def _decode_dynamic_p8_mips(
    decoded: bytes, contract: DynamicStadiumP8Contract
) -> tuple[bytes, ...]:
    pixel_start = contract.system_bytes + contract.pixel_offset
    palette_start = contract.system_bytes + contract.palette_offset
    _require(
        pixel_start >= contract.system_bytes
        and pixel_start + contract.index_chain_bytes <= len(decoded)
        and palette_start >= contract.system_bytes
        and palette_start + PALETTE_BYTES <= len(decoded),
        "Stadium P8 allocation exceeds the decoded SCNE video buffer",
    )
    palette_raw = decoded[palette_start:palette_start + PALETTE_BYTES]
    palette = [
        (
            palette_raw[index + 2],
            palette_raw[index + 1],
            palette_raw[index],
            palette_raw[index + 3],
        )
        for index in range(0, PALETTE_BYTES, 4)
    ]
    result: list[bytes] = []
    cursor = pixel_start
    for width, height in contract.mip_dimensions:
        size = width * height
        try:
            linear = unswizzle_2d(decoded[cursor:cursor + size], width, height, 1)
        except TxtrError as exc:
            raise StadiumTextureWriterError(
                f"The Stadium P8 mip layout is unsupported ({exc})."
            ) from exc
        result.append(b"".join(bytes(palette[value]) for value in linear))
        cursor += size
    return tuple(result)


def _ownership_note(names: tuple[str, ...]) -> str:
    if not names:
        return (
            "This embedded texture has no direct material owner in the decoded "
            "stadium scene. It is structurally editable, but its visible runtime "
            "consumer may be indirect or absent."
        )
    label = ", ".join(names[:8])
    if len(names) > 8:
        label += f", and {len(names) - 8} more"
    return (
        f"This embedded texture is shared by {len(names)} material"
        f"{'s' if len(names) != 1 else ''}: {label}. Every surface linked to "
        "those materials changes together."
    )


class _DynamicStadiumResolver:
    """Resolve canonical selectors solely from the user's extracted source."""

    def __init__(self, index_path: Path, inventory_path: Path) -> None:
        self.index = _regular(index_path.expanduser(), "canonical extracted volume 0")
        self.inventory = _regular(
            inventory_path.expanduser(), "canonical resource inventory"
        )
        _require(
            self.index.name == "0" and self.index.stat().st_size == INDEX_SIZE,
            "Canonical extracted volume 0 is incompatible with Stadium Studio",
        )
        try:
            self.archive = parse_archive(self.index)
            inventory_document, resources = parse_inventory(self.inventory)
        except (OuterFormatError, ProbeError, OSError, ValueError) as exc:
            raise StadiumTextureWriterError(
                f"Could not resolve Stadium textures from the private game index ({exc})."
            ) from exc
        _require(
            inventory_document.get("schema")
            == "nfl2k5_resource_chunk_inventory/v1",
            "Canonical resource inventory schema changed",
        )
        self.scne_resources = tuple(row for row in resources if row.kind == "SCNE")
        _require(len(self.scne_resources) == 4_616, "NFL 2K5 SCNE inventory changed")

    def resolve(self, selector: str) -> _ResolvedStadiumScene:
        return self.resolve_many((selector,))[0]

    def resolve_many(
        self, selectors: Sequence[str]
    ) -> tuple[_ResolvedStadiumScene, ...]:
        _require(bool(selectors), "Choose at least one Stadium texture to compile")
        parts = [_selector_parts(value) for value in selectors]
        scene_keys = {(outer, chunk, scene) for outer, chunk, scene, _texture in parts}
        _require(
            len(scene_keys) == 1,
            "A Stadium resource compiler call may contain only one scene",
        )
        outer, chunk, scene = next(iter(scene_keys))
        _require(0 <= scene < len(self.scne_resources), "Stadium scene selector is out of range")
        resource = self.scne_resources[scene]
        _require(
            resource.outer_index == outer
            and resource.chunk_index == chunk
            and resource.kind == "SCNE"
            and resource.word_10 == 0xFEEDBEEF,
            "Stadium selector no longer resolves to its SCNE resource",
        )
        entry = self.archive.entries[outer]
        _require(
            entry.table_index == outer
            and f"0x{entry.name_id:08x}" == resource.outer_id
            and resource.chunk_offset + HEADER.size + resource.stored_size <= entry.size,
            "Stadium outer archive ownership changed",
        )
        span_size = HEADER.size + resource.stored_size
        try:
            span = read_entry_range(
                self.archive, entry, resource.chunk_offset, span_size
            )
            decoded, detail = decode_resource(span, resource)
            scene_document, _names, _mappings, _sample = parse_scene(
                scene, resource, decoded, {}
            )
        except (ProbeError, ScneError, TxtrError, struct.error, OSError) as exc:
            raise StadiumTextureWriterError(
                f"The selected Stadium SCNE failed its bounded source replay ({exc})."
            ) from exc
        _require(scene_document.get("name") == "stadium", "Selected SCNE is not a stadium")
        raw_textures = scene_document.get("embedded_textures")
        _require(isinstance(raw_textures, list), "Stadium SCNE has no texture table")
        texture_rows = tuple(row for row in raw_textures if isinstance(row, dict))
        _require(
            len(texture_rows) == len(raw_textures),
            "Stadium SCNE texture table contains an invalid record",
        )

        absolute_archive_start = entry.virtual_offset + resource.chunk_offset
        absolute_archive_end = absolute_archive_start + span_size
        pack = next(
            (
                row
                for row in self.archive.packs
                if row.virtual_start <= absolute_archive_start
                and absolute_archive_end <= row.virtual_end
            ),
            None,
        )
        _require(
            pack is not None and pack.name in STADIUM_PACKS,
            "That Stadium SCNE crosses an archive pack boundary and is export-only",
        )
        assert pack is not None
        pack_sector, pack_size, pack_sha = STADIUM_PACKS[pack.name]
        _require(
            pack.path.stat().st_size == pack.size == pack_size,
            "Private Stadium archive pack size changed",
        )
        pack_offset = absolute_archive_start - pack.virtual_start
        fields = HEADER.unpack_from(span)
        _require(
            fields
            == (
                b"SCNE",
                resource.stored_size,
                resource.word_08,
                resource.word_0c,
                0xFEEDBEEF,
                resource.word_14,
                0,
                0,
            ),
            "Stadium SCNE wrapper and resource inventory disagree",
        )
        lz = detail.get("lz")
        _require(isinstance(lz, dict), "Stadium SCNE is not losslessly compressed")
        retail_consumed = lz.get("consumed_bytes")
        _require(
            isinstance(retail_consumed, int)
            and not isinstance(retail_consumed, bool)
            and 0 < retail_consumed <= resource.stored_size,
            "Stadium SCNE compressed length is invalid",
        )
        opaque_tail = span[HEADER.size + retail_consumed:]
        decoded_sha = str(detail.get("decoded_sha256", ""))
        _require(
            len(decoded) == resource.output_size
            and decoded_sha == _sha256_bytes(decoded),
            "Stadium SCNE decoded source hash changed during replay",
        )

        base_values = {
            "outer_index": outer,
            "outer_id": resource.outer_id,
            "chunk_index": chunk,
            "scene_index": scene,
            "pack_name": pack.name,
            "pack_sector": pack_sector,
            "pack_size": pack_size,
            "pack_sha256": pack_sha,
            "pack_offset": pack_offset,
            "chunk_offset": resource.chunk_offset,
            "stored_size": resource.stored_size,
            "system_bytes": resource.word_08,
            "video_bytes": resource.word_0c,
            "decoded_sha256": decoded_sha,
            "source_span_sha256": _sha256_bytes(span),
            "retail_consumed": retail_consumed,
            "retail_scratch": resource.word_14,
            "opaque_tail_size": len(opaque_tail),
            "opaque_tail_sha256": _sha256_bytes(opaque_tail),
        }
        contracts = [
            self._target_contract(
                selector,
                texture_index,
                texture_rows,
                decoded,
                base_values,
            )
            for selector, (_outer, _chunk, _scene, texture_index)
            in zip(selectors, parts)
        ]
        return tuple(
            _ResolvedStadiumScene(
                contract=contract,
                resource=resource,
                span=span,
                decoded=decoded,
                opaque_tail=opaque_tail,
                texture_rows=texture_rows,
            )
            for contract in contracts
        )

    @staticmethod
    def _target_contract(
        selector: str,
        texture_index: int,
        texture_rows: tuple[dict[str, Any], ...],
        decoded: bytes,
        base_values: Mapping[str, object],
    ) -> DynamicStadiumP8Contract:
        _require(
            0 <= texture_index < len(texture_rows),
            "Stadium texture selector is outside this scene's texture table",
        )
        row = texture_rows[texture_index]
        _require(int(row.get("index", -1)) == texture_index, "Stadium texture order changed")
        required_integers = (
            "width",
            "height",
            "mip_levels",
            "descriptor_offset",
            "pixel_offset",
            "palette_offset",
            "packed_format",
            "packed_size",
            "descriptor_flags",
            "dimensions",
            "depth",
        )
        _require(
            all(
                isinstance(row.get(name), int)
                and not isinstance(row.get(name), bool)
                for name in required_integers
            ),
            "Stadium texture descriptor contains invalid numeric fields",
        )
        width = int(row["width"])
        height = int(row["height"])
        dimensions = _mip_dimensions(width, height, int(row["mip_levels"]))
        index_bytes = sum(w * h for w, h in dimensions)
        pixel_offset = int(row["pixel_offset"])
        palette_offset = int(row["palette_offset"])
        system_bytes = int(base_values["system_bytes"])
        descriptor = int(row["descriptor_offset"])
        _require(
            row.get("format_name") == "P8"
            and row.get("conversion_status") == "base_level_supported"
            and int(row["descriptor_flags"]) == 0x80000000
            and int(row["packed_size"]) == 0
            and int(row["dimensions"]) == 2
            and int(row["depth"]) == 1
            and descriptor >= 0
            and descriptor + 0x20 <= system_bytes
            and pixel_offset >= 0
            and palette_offset == pixel_offset + index_bytes
            and system_bytes + palette_offset + PALETTE_BYTES <= len(decoded),
            UNSUPPORTED_FORMAT_ERROR,
        )
        target_start = system_bytes + pixel_offset
        target_end = system_bytes + palette_offset + PALETTE_BYTES
        for other in texture_rows:
            if int(other.get("index", -1)) == texture_index:
                continue
            if other.get("format_name") != "P8":
                continue
            other_start = system_bytes + int(other.get("pixel_offset", -1))
            other_end = system_bytes + int(other.get("palette_offset", -1)) + PALETTE_BYTES
            _require(
                target_end <= other_start or target_start >= other_end,
                "That Stadium texture aliases another descriptor allocation and is export-only",
            )
        raw_names = row.get("mapped_material_names")
        _require(isinstance(raw_names, list), "Stadium material ownership is unavailable")
        names = tuple(str(value) for value in raw_names)
        _require(
            len(names) == int(row.get("mapped_material_count", -1)),
            "Stadium material ownership count changed",
        )
        outer = int(base_values["outer_index"])
        chunk = int(base_values["chunk_index"])
        scene = int(base_values["scene_index"])
        contract = DynamicStadiumP8Contract(
            texture_id=selector,
            scene_id=_scene_id_from_parts(outer, chunk, scene),
            texture_index=texture_index,
            width=width,
            height=height,
            mip_dimensions=dimensions,
            format_name="P8",
            descriptor_offset=descriptor,
            pixel_offset=pixel_offset,
            palette_offset=palette_offset,
            packed_format=int(row["packed_format"]),
            packed_size=int(row["packed_size"]),
            descriptor_flags=int(row["descriptor_flags"]),
            mapped_material_names=names,
            mapped_material_count=len(names),
            rgba_sha256=str(row.get("rgba_sha256", "")),
            shared_ownership_note=_ownership_note(names),
            **base_values,  # type: ignore[arg-type]
        )
        stock_mips = _decode_dynamic_p8_mips(decoded, contract)
        _require(
            len(contract.rgba_sha256) == 64
            and _sha256_bytes(stock_mips[0]) == contract.rgba_sha256,
            "Stadium P8 source pixels do not match the parsed descriptor",
        )
        return contract


def _read_dynamic_png(
    replacement_png: Path, contract: DynamicStadiumP8Contract
) -> tuple[bytes, bytes]:
    path = _regular(replacement_png.expanduser(), "replacement Stadium PNG")
    payload = path.read_bytes()
    try:
        width, height, rgba = decode_rgba_png(
            payload, expected_dimensions=(contract.width, contract.height)
        )
    except (PngImportError, TxtrError) as exc:
        raise StadiumTextureWriterError(
            f"This Stadium texture needs an exact {contract.width}x{contract.height} "
            f"non-interlaced RGBA8 PNG ({exc})."
        ) from exc
    _require(
        (width, height) == (contract.width, contract.height),
        "Replacement Stadium PNG dimensions changed during validation",
    )
    return payload, rgba


def _compile_resolved_scene(
    resolved: Sequence[_ResolvedStadiumScene],
    replacement_pngs: Sequence[Path],
) -> _CompiledStadiumScene:
    _require(
        len(resolved) == len(replacement_pngs) and bool(resolved),
        "Stadium replacement inputs are inconsistent",
    )
    source = resolved[0]
    _require(
        all(
            row.span == source.span
            and row.decoded == source.decoded
            and row.contract.scene_id == source.contract.scene_id
            for row in resolved
        ),
        "Stadium replacements do not share one source SCNE",
    )
    selectors = [row.contract.texture_id for row in resolved]
    _require(len(selectors) == len(set(selectors)), "Stadium texture target repeats")
    edited = bytearray(source.decoded)
    payloads: list[_CompiledP8Payload] = []
    allowed_ranges: list[range] = []
    for row, replacement_png in zip(resolved, replacement_pngs):
        contract = row.contract
        payload, rgba = _read_dynamic_png(replacement_png, contract)
        levels = _generate_dynamic_mips(rgba, contract.mip_dimensions)
        try:
            palette, linear_indices, quantization = quantize_levels(levels)
            swizzled = [
                swizzle_2d(indices, level.width, level.height, 1)
                for level, indices in zip(levels, linear_indices)
            ]
            palette_payload = palette_bytes(palette)
        except (PngImportError, TxtrError) as exc:
            raise StadiumTextureWriterError(
                f"Could not compile {contract.width}x{contract.height} PNG into "
                f"the Stadium P8 allocation ({exc})."
            ) from exc
        index_payload = b"".join(swizzled)
        _require(
            len(index_payload) == contract.index_chain_bytes
            and len(palette_payload) == PALETTE_BYTES,
            "Compiled Stadium P8 allocation size changed",
        )
        pixel_start = contract.system_bytes + contract.pixel_offset
        palette_start = contract.system_bytes + contract.palette_offset
        before_pixel = bytes(edited[pixel_start:pixel_start + len(index_payload)])
        before_palette = bytes(edited[palette_start:palette_start + PALETTE_BYTES])
        edited[pixel_start:pixel_start + len(index_payload)] = index_payload
        edited[palette_start:palette_start + PALETTE_BYTES] = palette_payload
        allowed_ranges.extend((
            range(pixel_start, pixel_start + len(index_payload)),
            range(palette_start, palette_start + PALETTE_BYTES),
        ))
        quantized_rgba = tuple(
            rgba_from_indices(indices, palette) for indices in linear_indices
        )
        preview = encode_rgba_png(
            contract.width, contract.height, quantized_rgba[0]
        )
        local_changed = sum(
            before != after
            for before, after in zip(before_pixel, index_payload)
        ) + sum(
            before != after
            for before, after in zip(before_palette, palette_payload)
        )
        payloads.append(_CompiledP8Payload(
            contract=contract,
            replacement_png_sha256=_sha256_bytes(payload),
            replacement_rgba_sha256=_sha256_bytes(rgba),
            quantized_preview_png_sha256=_sha256_bytes(preview),
            quantized_base_rgba_sha256=_sha256_bytes(quantized_rgba[0]),
            mip_rgba_sha256=tuple(_sha256_bytes(value) for value in quantized_rgba),
            quantization=dict(quantization),
            palette_entries=len(palette),
            decoded_changed_byte_count=local_changed,
            quantized_preview_png=preview,
        ))
    edited_bytes = bytes(edited)
    changed = [
        index
        for index, pair in enumerate(zip(source.decoded, edited_bytes))
        if pair[0] != pair[1]
    ]
    _require(
        all(any(index in allowed for allowed in allowed_ranges) for index in changed),
        "Decoded Stadium edit escaped selected pixel/palette allocations",
    )
    contract = source.contract
    fixed = _rebuild_vc_lz_fixed_span(
        edited_bytes,
        source.span[:HEADER.size],
        source.opaque_tail,
        consumed_cap=contract.retail_consumed,
        scratch_cap=SCNE_OBSERVED_SCRATCH_MAX,
    )
    return _CompiledStadiumScene(
        source=source,
        textures=tuple(payloads),
        fixed=fixed,
        decoded_changed_byte_count=len(changed),
    )


class Nfl2k5StadiumTextureWriter:
    """Compile every source-proved fixed-allocation Stadium P8 occurrence."""

    contract = StadiumP8TargetContract()

    def __init__(self, cache: SourceCache, stadium_cache: StadiumCacheResult) -> None:
        self.cache = cache
        self.stadium_cache = stadium_cache
        self.pack9, self.source_xiso, self.stock_png = self._bind_private_source()
        self._resolver = _DynamicStadiumResolver(cache.pack0, cache.inventory)
        self._editable_textures = self._load_private_editable_catalog()

    @property
    def editable_count(self) -> int:
        return len(self._editable_textures)

    def texture(self, texture_id: str) -> StadiumTexture:
        try:
            return self._editable_textures[texture_id]
        except KeyError as exc:
            raise StadiumTextureWriterError(
                "That Stadium texture is not in the private editable P8 catalog"
            ) from exc

    def supports(self, texture: StadiumTexture) -> bool:
        catalog = getattr(self, "_editable_textures", None)
        if catalog is None:
            # Synthetic/legacy contract tests construct the writer without a
            # private cache.  Keep the original cement01 gate in that narrow
            # circumstance; real product instances always own the full map.
            return (
                texture.texture_id == TARGET_TEXTURE_ID
                and texture.scene_id == TARGET_SCENE_ID
                and texture.texture_index == TEXTURE_INDEX
                and texture.width == 64
                and texture.height == 64
                and texture.format_name == FORMAT_NAME
                and texture.rgba_sha256 == STOCK_RGBA_SHA256
                and texture.png_sha256 == STOCK_PNG_SHA256
                and texture.mapped_material_names == (TARGET_MATERIAL_NAME,)
                and texture.mapped_material_count == 1
            )
        selected = catalog.get(texture.texture_id)
        return bool(
            selected is not None
            and texture.scene_id == selected.scene_id
            and texture.texture_index == selected.texture_index
            and texture.width == selected.width
            and texture.height == selected.height
            and texture.format_name == selected.format_name == "P8"
            and texture.rgba_sha256 == selected.rgba_sha256
            and texture.png_sha256 == selected.png_sha256
            and texture.png_path.resolve(strict=False)
            == selected.png_path.resolve(strict=False)
            and texture.mapped_material_names == selected.mapped_material_names
            and texture.mapped_material_count == selected.mapped_material_count
        )

    def read_validated_png(
        self,
        replacement_png: Path,
        texture: StadiumTexture | str | None = None,
    ) -> tuple[bytes, bytes]:
        """Read one exact authoring PNG and return its container and RGBA bytes."""

        if texture is None:
            selected = self._editable_textures.get(TARGET_TEXTURE_ID)
        elif isinstance(texture, str):
            selected = self._editable_textures.get(texture)
        else:
            selected = texture if self.supports(texture) else None
        if selected is None:
            raise StadiumTextureWriterError(
                "That Stadium texture does not have a bounded P8 writer"
            )
        contract = DynamicStadiumP8Contract(
            texture_id=selected.texture_id,
            scene_id=selected.scene_id,
            outer_index=0,
            outer_id="",
            chunk_index=0,
            scene_index=0,
            texture_index=selected.texture_index,
            width=selected.width,
            height=selected.height,
            mip_dimensions=((selected.width, selected.height),),
            format_name="P8",
            descriptor_offset=0,
            pixel_offset=0,
            palette_offset=0,
            packed_format=0,
            packed_size=0,
            descriptor_flags=0,
            mapped_material_names=selected.mapped_material_names,
            mapped_material_count=selected.mapped_material_count,
            rgba_sha256=selected.rgba_sha256,
            pack_name="9",
            pack_sector=PACK_SECTOR,
            pack_size=PACK_SIZE,
            pack_sha256=PACK_SHA256,
            pack_offset=0,
            chunk_offset=0,
            stored_size=0,
            system_bytes=0,
            video_bytes=0,
            decoded_sha256="",
            source_span_sha256="",
            retail_consumed=0,
            retail_scratch=0,
            opaque_tail_size=0,
            opaque_tail_sha256=_sha256_bytes(b""),
            shared_ownership_note=_ownership_note(selected.mapped_material_names),
        )
        return _read_dynamic_png(replacement_png, contract)

    def compile(
        self, texture: StadiumTexture, replacement_png: Path
    ) -> CompiledStadiumTextureEdit:
        if not self.supports(texture):
            raise StadiumTextureWriterError(
                "That stadium texture does not have a bounded writer yet"
            )
        source = self._resolver.resolve(texture.texture_id)
        self._require_catalog_match(texture, source.contract)
        scene = _compile_resolved_scene((source,), (replacement_png,))
        payload = scene.textures[0]
        fixed = scene.fixed
        return CompiledStadiumTextureEdit(
            texture_id=texture.texture_id,
            replacement_png_sha256=payload.replacement_png_sha256,
            replacement_rgba_sha256=payload.replacement_rgba_sha256,
            quantized_preview_png_sha256=payload.quantized_preview_png_sha256,
            quantized_base_rgba_sha256=payload.quantized_base_rgba_sha256,
            mip_rgba_sha256=payload.mip_rgba_sha256,
            quantization=payload.quantization,
            palette_entries=payload.palette_entries,
            decoded_after_sha256=fixed.decoded_sha256,
            decoded_changed_byte_count=scene.decoded_changed_byte_count,
            encoded_sha256=fixed.encoded_sha256,
            encoded_bytes=fixed.encoded_bytes,
            zero_gap_bytes=fixed.zero_gap_bytes,
            minimum_alias_scratch_bytes=fixed.minimum_alias_scratch_bytes,
            scratch_after=fixed.scratch_after,
            source_span_sha256=source.contract.source_span_sha256,
            rebuilt_span_sha256=_sha256_bytes(fixed.span),
            quantized_preview_png=payload.quantized_preview_png,
            rebuilt_span=fixed.span,
            target_metadata=source.contract.target_metadata(),
        )

    def validated_replacement(
        self, texture: StadiumTexture, replacement_png: Path
    ) -> tuple[bytes, bytes, CompiledStadiumTextureEdit]:
        """Compile first, then pin the exact user bytes staged by the product."""

        compiled = self.compile(texture, replacement_png)
        payload, rgba = self.read_validated_png(replacement_png, texture)
        _require(
            _sha256_bytes(payload) == compiled.replacement_png_sha256
            and _sha256_bytes(rgba) == compiled.replacement_rgba_sha256,
            "Replacement stadium PNG changed while it was being checked",
        )
        return payload, rgba, compiled

    def _load_private_editable_catalog(self) -> dict[str, StadiumTexture]:
        """Load only source-derived metadata; no private manifest ships."""

        manifest = _regular(
            self.stadium_cache.texture_manifest,
            "private Stadium texture manifest",
        )
        texture_root = self.stadium_cache.texture_root.resolve(strict=True)
        result_root = self.stadium_cache.root.resolve(strict=True)
        try:
            manifest.relative_to(result_root)
            texture_root.relative_to(result_root)
            result_root.relative_to(self.cache.root.resolve(strict=True))
        except ValueError as exc:
            raise StadiumTextureWriterError(
                "Private Stadium texture metadata escapes the SourceCache"
            ) from exc
        textures: dict[str, StadiumTexture] = {}
        for raw in iter_top_level_array(
            manifest, "occurrences", label="private Stadium texture manifest"
        ):
            if not isinstance(raw, dict):
                raise StadiumTextureWriterError(
                    "Private Stadium texture manifest has an invalid occurrence"
                )
            integer_fields = (
                "outer_index",
                "chunk_index",
                "scene_index",
                "texture_index",
                "width",
                "height",
                "mip_levels",
                "pixel_offset",
                "palette_offset",
                "descriptor_flags",
                "packed_size",
                "depth",
                "dimensions",
            )
            _require(
                all(
                    isinstance(raw.get(name), int)
                    and not isinstance(raw.get(name), bool)
                    for name in integer_fields
                ),
                "Private Stadium texture manifest has invalid numeric fields",
            )
            width = int(raw["width"])
            height = int(raw["height"])
            dimensions = _mip_dimensions(width, height, int(raw["mip_levels"]))
            _require(
                raw.get("scene_name") == "stadium"
                and raw.get("format_name") == "P8"
                and raw.get("conversion_status") == "base_level_supported"
                and int(raw["descriptor_flags"]) == 0x80000000
                and int(raw["packed_size"]) == 0
                and int(raw["depth"]) == 1
                and int(raw["dimensions"]) == 2
                and int(raw["palette_offset"]) - int(raw["pixel_offset"])
                == sum(w * h for w, h in dimensions),
                UNSUPPORTED_FORMAT_ERROR,
            )
            outer = int(raw["outer_index"])
            chunk = int(raw["chunk_index"])
            scene = int(raw["scene_index"])
            texture_index = int(raw["texture_index"])
            scene_id = _scene_id_from_parts(outer, chunk, scene)
            texture_id = f"{scene_id}.texture{texture_index:04d}"
            _require(texture_id not in textures, "Private Stadium texture repeats")
            rgba_hash = raw.get("rgba_sha256")
            png_hash = raw.get("png_sha256")
            names_value = raw.get("mapped_material_names")
            count = raw.get("mapped_material_count")
            _require(
                isinstance(rgba_hash, str)
                and len(rgba_hash) == 64
                and isinstance(png_hash, str)
                and len(png_hash) == 64
                and isinstance(names_value, str)
                and isinstance(count, int)
                and not isinstance(count, bool),
                "Private Stadium texture hashes/ownership are invalid",
            )
            names = tuple(value for value in names_value.split("|") if value)
            _require(len(names) == count, "Private Stadium material count changed")
            relative = Path("by_rgba_sha256") / rgba_hash[:2] / f"{rgba_hash}.png"
            declared = raw.get("png_path")
            _require(
                isinstance(declared, str)
                and Path(declared).as_posix().endswith(relative.as_posix()),
                "Private Stadium PNG path is noncanonical",
            )
            png_path = _regular(texture_root / relative, "private Stadium PNG")
            try:
                png_path.relative_to(texture_root)
            except ValueError as exc:
                raise StadiumTextureWriterError(
                    "Private Stadium PNG escapes its cache"
                ) from exc
            textures[texture_id] = StadiumTexture(
                texture_id=texture_id,
                scene_id=scene_id,
                texture_index=texture_index,
                width=width,
                height=height,
                format_name="P8",
                rgba_sha256=rgba_hash,
                png_sha256=png_hash,
                png_path=png_path,
                mapped_material_names=names,
                mapped_material_count=len(names),
                access_status="Editable",
            )
        _require(
            len(textures) == 23_838 and TARGET_TEXTURE_ID in textures,
            "Private Stadium P8 occurrence count changed",
        )
        return textures

    @staticmethod
    def _require_catalog_match(
        texture: StadiumTexture, contract: DynamicStadiumP8Contract
    ) -> None:
        _require(
            texture.texture_id == contract.texture_id
            and texture.scene_id == contract.scene_id
            and texture.texture_index == contract.texture_index
            and (texture.width, texture.height)
            == (contract.width, contract.height)
            and texture.format_name == contract.format_name == "P8"
            and texture.rgba_sha256 == contract.rgba_sha256
            and texture.mapped_material_names == contract.mapped_material_names
            and texture.mapped_material_count == contract.mapped_material_count,
            "Private Stadium catalog and source SCNE no longer agree",
        )
        png = _regular(texture.png_path, "private Stadium PNG")
        payload = png.read_bytes()
        _require(
            _sha256_bytes(payload) == texture.png_sha256,
            "Private Stadium PNG no longer matches its manifest",
        )
        try:
            width, height, rgba = decode_rgba_png(
                payload, expected_dimensions=(contract.width, contract.height)
            )
        except (PngImportError, TxtrError) as exc:
            raise StadiumTextureWriterError(
                f"Private Stadium PNG failed its independent decode ({exc})."
            ) from exc
        _require(
            (width, height) == (contract.width, contract.height)
            and _sha256_bytes(rgba) == contract.rgba_sha256,
            "Private Stadium PNG pixels no longer match the source SCNE",
        )

    def build_xiso(
        self,
        compiled: CompiledStadiumTextureEdit,
        output_xiso: Path,
        manifest_path: Path,
    ) -> StadiumTextureBuildResult:
        """Create a complete layout-identical XISO or leave no failed output."""

        self._validate_compiled(compiled)
        output_xiso = output_xiso.expanduser()
        manifest_path = manifest_path.expanduser()
        output_xiso.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        output = xiso.canonical_new_path(output_xiso)
        manifest = xiso.canonical_new_path(manifest_path)
        source = _regular(self.source_xiso, "retail source XISO")
        _require(output != manifest and output != source and manifest != source,
                 "Source, output XISO, and manifest paths must be distinct")
        _require(not output.exists() and not manifest.exists(),
                 "Output XISO and build manifest must both be new files")

        source_fd = os.open(
            source,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        output_owned: xiso.OwnedFile | None = None
        manifest_owned: xiso.OwnedFile | None = None
        success = False
        try:
            source_info = os.fstat(source_fd)
            _require(
                stat.S_ISREG(source_info.st_mode)
                and source_info.st_size == xiso.EXPECTED_XISO_SIZE,
                "Retail source XISO descriptor is incompatible",
            )
            source_identity = xiso.fd_identity(source_fd)
            _require(xiso.path_identity(source) == source_identity,
                     "Retail source XISO pathname changed after open")
            source_sha = _sha256_fd(source_fd)
            _require(source_sha == xiso.EXPECTED_XISO_SHA256,
                     "Retail source XISO hash does not match NFL 2K5 USA")
            entries, directory = xiso.parse_xdvdfs(source_fd, source_info.st_size)
            files = [row for row in entries.values() if not (row.attributes & 0x10)]
            pack = entries.get(PACK_PATH.casefold())
            index = entries.get(INDEX_PATH.casefold())
            xbe = entries.get("default.xbe")
            _require(len(files) == XDVDFS_FILE_COUNT, "XDVDFS file count changed")
            _require(pack is not None and (pack.sector, pack.size) == (PACK_SECTOR, PACK_SIZE),
                     "XDVDFS volume 9 extent changed")
            _require(index is not None and (index.sector, index.size) == (INDEX_SECTOR, INDEX_SIZE),
                     "XDVDFS volume 0 extent changed")
            _require(xbe is not None and xbe.size == xiso.EXPECTED_XBE_SIZE,
                     "default.xbe extent changed")
            _require(pack.byte_offset + CHUNK_PACK_OFFSET == ABSOLUTE_XISO_SPAN,
                     "Authorized stadium XISO span arithmetic changed")
            retail_span = xiso.read_exact(source_fd, ABSOLUTE_XISO_SPAN, CHUNK_SPAN_SIZE)
            _require(_sha256_bytes(retail_span) == CHUNK_SPAN_SHA256,
                     "Retail XISO stadium SCNE span changed")
            _require(retail_span != compiled.rebuilt_span,
                     "Replacement stadium span is a no-op")
            ledger = _difference_ledger(retail_span, compiled.rebuilt_span)

            output_owned = xiso.reserve_file(output)
            _require(output_owned.identity != source_identity, "Output XISO aliases source")
            copy_method = xiso.copy_fd_exact(source_fd, output_owned.descriptor, source_info.st_size)
            _require(xiso.owned_path_matches(output_owned),
                     "Output XISO pathname changed during copy")
            written = os.pwrite(
                output_owned.descriptor, compiled.rebuilt_span, ABSOLUTE_XISO_SPAN
            )
            _require(written == CHUNK_SPAN_SIZE, "Short stadium SCNE XISO write")
            _require(
                xiso.read_exact(output_owned.descriptor, ABSOLUTE_XISO_SPAN, CHUNK_SPAN_SIZE)
                == compiled.rebuilt_span,
                "Stadium SCNE XISO readback differs",
            )
            os.fsync(output_owned.descriptor)
            output_entries, output_directory = xiso.parse_xdvdfs(
                output_owned.descriptor, source_info.st_size
            )
            _require(output_entries == entries and output_directory == directory,
                     "Output XDVDFS tree or extents changed")
            output_sha = _sha256_fd(output_owned.descriptor)
            output_pack_sha = _sha256_fd(
                output_owned.descriptor, pack.byte_offset, pack.size
            )
            _require(_sha256_fd(source_fd) == source_sha,
                     "Retail source XISO changed during build")

            document: dict[str, object] = {
                "schema": BUILD_SCHEMA,
                "target": {
                    "texture_id": TARGET_TEXTURE_ID,
                    "scene_id": TARGET_SCENE_ID,
                    "outer_index": OUTER_INDEX,
                    "outer_id": OUTER_ID,
                    "chunk_index": CHUNK_INDEX,
                    "scene_index": 2648,
                    "texture_index": TEXTURE_INDEX,
                    "material_index": TARGET_MATERIAL_INDEX,
                    "material_name": TARGET_MATERIAL_NAME,
                    "dimensions": [64, 64],
                    "mip_dimensions": [list(value) for value in MIP_DIMENSIONS],
                    "format": FORMAT_NAME,
                    "shared_ownership_note": SHARED_OWNERSHIP_NOTE,
                },
                "authored_replacement": compiled.public_metadata(),
                "source": {
                    "path": str(source),
                    "size": source_info.st_size,
                    "sha256": source_sha,
                    "opened_read_only": True,
                    "modified": False,
                    "private_cache_png_sha256": STOCK_PNG_SHA256,
                },
                "resource": {
                    "pack_path": PACK_PATH,
                    "pack_sector": pack.sector,
                    "pack_size": pack.size,
                    "pack_span_offset": CHUNK_PACK_OFFSET,
                    "absolute_xiso_span": ABSOLUTE_XISO_SPAN,
                    "span_size": CHUNK_SPAN_SIZE,
                    "source_span_sha256": CHUNK_SPAN_SHA256,
                    "replacement_span_sha256": compiled.rebuilt_span_sha256,
                    "decoded_pixel_span": [
                        SYSTEM_BYTES + PIXEL_OFFSET,
                        SYSTEM_BYTES + PIXEL_OFFSET + INDEX_CHAIN_BYTES,
                    ],
                    "decoded_palette_span": [
                        SYSTEM_BYTES + PALETTE_OFFSET,
                        SYSTEM_BYTES + PALETTE_OFFSET + PALETTE_BYTES,
                    ],
                    "fixed_opaque_tail_bytes": OPAQUE_TAIL_SIZE,
                    "fixed_opaque_tail_sha256": OPAQUE_TAIL_SHA256,
                    "retail_consumed_bytes": RETAIL_CONSUMED,
                    "scratch_observed_retail_max": SCNE_OBSERVED_SCRATCH_MAX,
                    **ledger,
                    "all_xiso_bytes_outside_span_bit_exact": True,
                },
                "xdvdfs": {
                    **directory,
                    "file_count": len(files),
                    "tree_identical_after_patch": True,
                    "all_sector_extents_preserved": True,
                },
                "output": {
                    "path": str(output),
                    "size": source_info.st_size,
                    "sha256": output_sha,
                    "volume_9_sha256": output_pack_sha,
                    "copy_method": copy_method,
                    "exclusively_created": True,
                },
                "claims": {
                    "bounded_existing_geometry_texture_write": True,
                    "descriptor_palette_pixel_and_mips_verified": True,
                    "layout_identical_copy_only_xiso": True,
                    "private_cache_source_binding": True,
                    "project_contains_retail_bytes": False,
                    "xemu_boot_spot_check": False,
                    "xemu_visible_texture_spot_check": False,
                    "original_hardware_tested": False,
                },
            }
            payload = _canonical_json(document)
            _require(len(payload) <= MAX_MANIFEST_BYTES, "Build manifest is unexpectedly large")
            manifest_owned = xiso.reserve_file(manifest, mode=0o600)
            _write_owned(manifest_owned, payload)
            _require(
                xiso.path_identity(source) == source_identity
                and xiso.owned_path_matches(output_owned)
                and xiso.owned_path_matches(manifest_owned),
                "An artifact pathname changed during stadium build",
            )
            success = True
            return StadiumTextureBuildResult(
                output_xiso=output,
                manifest=manifest,
                output_sha256=output_sha,
                output_pack_sha256=output_pack_sha,
                changed_byte_count=int(ledger["changed_byte_count"]),
                changed_run_count=int(ledger["changed_run_count"]),
                copy_method=copy_method,
            )
        finally:
            os.close(source_fd)
            if output_owned is not None:
                os.close(output_owned.descriptor)
            if manifest_owned is not None:
                os.close(manifest_owned.descriptor)
            if not success:
                xiso.unlink_if_owned(manifest_owned)
                xiso.unlink_if_owned(output_owned)

    def _bind_private_source(self) -> tuple[Path, Path, Path]:
        source = self.cache.source
        if (
            not source.recognized
            or source.fingerprint_id != "nfl2k5-usa-retail-xiso"
            or source.sha256 != SOURCE_SHA256
            or source.kind != "xiso"
        ):
            raise StadiumTextureWriterError(
                "The stadium texture writer requires the recognized NFL 2K5 USA XISO"
            )
        cache_root = self.cache.root.resolve(strict=True)
        result_root = self.stadium_cache.root.resolve(strict=True)
        try:
            result_root.relative_to(cache_root)
        except ValueError as exc:
            raise StadiumTextureWriterError(
                "Stadium texture manifests must remain inside the private SourceCache"
            ) from exc
        if not self.stadium_cache.private or self.stadium_cache.shareable:
            raise StadiumTextureWriterError("Stadium texture cache is not marked private")
        manifest = _regular(self.stadium_cache.texture_manifest, "private stadium texture manifest")
        texture_root = self.stadium_cache.texture_root.resolve(strict=True)
        try:
            manifest.relative_to(result_root)
            texture_root.relative_to(result_root)
        except ValueError as exc:
            raise StadiumTextureWriterError("Stadium texture cache path escapes its root") from exc

        occurrence: dict[str, Any] | None = None
        for raw in iter_top_level_array(manifest, "occurrences", label="private stadium texture manifest"):
            if not isinstance(raw, dict):
                continue
            if (
                raw.get("outer_index") == OUTER_INDEX
                and raw.get("chunk_index") == CHUNK_INDEX
                and raw.get("scene_index") == 2648
                and raw.get("texture_index") == TEXTURE_INDEX
            ):
                _require(occurrence is None, "Private texture manifest duplicates cement01")
                occurrence = raw
        _require(occurrence is not None, "Private texture manifest is missing cement01")
        expected = {
            "scene_name": "stadium",
            "outer_id": OUTER_ID,
            "chunk_offset": CHUNK_ENTRY_OFFSET,
            "descriptor_offset": DESCRIPTOR_OFFSET,
            "pixel_offset": PIXEL_OFFSET,
            "palette_offset": PALETTE_OFFSET,
            "packed_format": PACKED_FORMAT,
            "packed_size": PACKED_SIZE,
            "descriptor_flags": DESCRIPTOR_FLAGS,
            "format_code": FORMAT_CODE,
            "format_name": FORMAT_NAME,
            "mip_levels": len(MIP_DIMENSIONS),
            "width": 64,
            "height": 64,
            "depth": 1,
            "dimensions": 2,
            "rgba_sha256": STOCK_RGBA_SHA256,
            "png_sha256": STOCK_PNG_SHA256,
            "mapped_material_names": TARGET_MATERIAL_NAME,
            "mapped_material_count": 1,
        }
        for key, value in expected.items():
            _require(occurrence.get(key) == value,
                     f"Private cement01 manifest field changed: {key}")

        material: dict[str, Any] | None = None
        for raw in iter_top_level_array(manifest, "materials", label="private stadium texture manifest"):
            if not isinstance(raw, dict):
                continue
            if (
                raw.get("outer_index") == OUTER_INDEX
                and raw.get("chunk_index") == CHUNK_INDEX
                and raw.get("scene_index") == 2648
                and raw.get("material_index") == TARGET_MATERIAL_INDEX
            ):
                _require(material is None, "Private texture manifest duplicates cement01 material")
                material = raw
        _require(material is not None, "Private texture manifest is missing cement01 material")
        _require(
            material.get("material_name") == TARGET_MATERIAL_NAME
            and material.get("mapping_status") == "mapped_embedded_texture"
            and material.get("material_offset") == MATERIAL_OFFSET
            and material.get("texture_pointer_field") == TEXTURE_POINTER_FIELD
            and material.get("texture_target") == DESCRIPTOR_OFFSET
            and material.get("texture_descriptor_offset") == DESCRIPTOR_OFFSET
            and material.get("texture_index") == TEXTURE_INDEX,
            "Private cement01 material ownership changed",
        )
        relative = Path("by_rgba_sha256") / STOCK_RGBA_SHA256[:2] / f"{STOCK_RGBA_SHA256}.png"
        stock_png = _regular(texture_root / relative, "private cement01 PNG")
        try:
            stock_png.relative_to(texture_root)
        except ValueError as exc:
            raise StadiumTextureWriterError("Private cement01 PNG escapes texture cache") from exc
        _require(_sha256_file(stock_png) == STOCK_PNG_SHA256,
                 "Private cement01 PNG no longer matches its manifest")
        pack9 = _regular(self.cache.pack0.parent / PACK_NAME, "private archive volume 9")
        _require(pack9.stat().st_size == PACK_SIZE, "Private archive volume 9 size changed")
        source_xiso = _regular(Path(source.selected_path), "retail source XISO")
        return pack9, source_xiso, stock_png

    def _read_source_scne(self) -> _SourceScne:
        with self.pack9.open("rb") as stream:
            stream.seek(CHUNK_PACK_OFFSET)
            span = stream.read(CHUNK_SPAN_SIZE)
        _require(len(span) == CHUNK_SPAN_SIZE, "Private SCNE span is truncated")
        _require(_sha256_bytes(span) == CHUNK_SPAN_SHA256,
                 "Private SCNE span no longer matches the target")
        fields = HEADER.unpack_from(span)
        _require(
            fields == (
                b"SCNE", CHUNK_STORED_SIZE, SYSTEM_BYTES, VIDEO_BYTES,
                0xFEEDBEEF, RETAIL_SCRATCH, 0, 0,
            ),
            "Private SCNE wrapper contract changed",
        )
        try:
            decoded, info = decompress_vc_lz(
                span[HEADER.size:HEADER.size + RETAIL_CONSUMED], DECODED_SIZE
            )
        except TxtrError as exc:
            raise StadiumTextureWriterError(f"Private stadium SCNE did not decode ({exc})") from exc
        _require(info.consumed_bytes == RETAIL_CONSUMED,
                 "Retail stadium VC-LZ consumed length changed")
        _require(_sha256_bytes(decoded) == DECODED_SHA256,
                 "Private stadium decoded SCNE changed")
        tail = span[-OPAQUE_TAIL_SIZE:]
        _require(_sha256_bytes(tail) == OPAQUE_TAIL_SHA256,
                 "Private stadium opaque tail changed")
        _require(_sha256_bytes(decoded[DESCRIPTOR_OFFSET:DESCRIPTOR_OFFSET + DESCRIPTOR_SIZE])
                 == DESCRIPTOR_SHA256, "cement01 texture descriptor changed")
        _require(_sha256_bytes(decoded[MATERIAL_OFFSET:MATERIAL_OFFSET + MATERIAL_SIZE])
                 == MATERIAL_SHA256, "cement01 material record changed")
        pixel_start = SYSTEM_BYTES + PIXEL_OFFSET
        palette_start = SYSTEM_BYTES + PALETTE_OFFSET
        _require(_sha256_bytes(decoded[pixel_start:pixel_start + INDEX_CHAIN_BYTES])
                 == STOCK_INDEX_SHA256, "cement01 stock P8 indices changed")
        _require(_sha256_bytes(decoded[palette_start:palette_start + PALETTE_BYTES])
                 == STOCK_PALETTE_SHA256, "cement01 stock palette changed")
        mips = _decode_p8_mips(decoded)
        _require(tuple(_sha256_bytes(value) for value in mips) == STOCK_MIP_RGBA_SHA256,
                 "cement01 stock mip decode changed")
        return _SourceScne(span=span, decoded=decoded, opaque_tail=tail)

    @staticmethod
    def _validate_compiled(compiled: CompiledStadiumTextureEdit) -> None:
        _require(compiled.texture_id == TARGET_TEXTURE_ID,
                 "Compiled edit targets another stadium texture")
        _require(compiled.source_span_sha256 == CHUNK_SPAN_SHA256,
                 "Compiled edit came from another SCNE span")
        _require(len(compiled.rebuilt_span) == CHUNK_SPAN_SIZE,
                 "Compiled stadium span has the wrong size")
        _require(_sha256_bytes(compiled.rebuilt_span) == compiled.rebuilt_span_sha256,
                 "Compiled stadium span changed in memory")
        _require(_sha256_bytes(compiled.quantized_preview_png)
                 == compiled.quantized_preview_png_sha256,
                 "Compiled stadium preview changed in memory")


def _write_owned(owned: xiso.OwnedFile, payload: bytes) -> None:
    _require(xiso.owned_path_matches(owned), "Owned manifest pathname changed before write")
    position = 0
    while position < len(payload):
        written = os.pwrite(owned.descriptor, payload[position:], position)
        _require(written > 0, "Short build-manifest write")
        position += written
    os.ftruncate(owned.descriptor, len(payload))
    os.fsync(owned.descriptor)
    _require(xiso.read_exact(owned.descriptor, 0, len(payload)) == payload,
             "Build-manifest readback differs")


def _compiled_payload_metadata(payload: _CompiledP8Payload) -> dict[str, object]:
    return {
        "texture_id": payload.contract.texture_id,
        "replacement_png_sha256": payload.replacement_png_sha256,
        "replacement_rgba_sha256": payload.replacement_rgba_sha256,
        "quantized_preview_png_sha256": payload.quantized_preview_png_sha256,
        "quantized_base_rgba_sha256": payload.quantized_base_rgba_sha256,
        "mip_rgba_sha256": list(payload.mip_rgba_sha256),
        "quantization": payload.quantization,
        "palette_entries": payload.palette_entries,
        "decoded_changed_byte_count": payload.decoded_changed_byte_count,
        "target": payload.contract.target_metadata(),
    }


def build_unified_stadium_texture_imports(
    index_path: Path,
    inventory_path: Path,
    edits: Sequence[tuple[str, Path]],
) -> list[
    tuple[
        bytes,
        list[tuple[str, bytes]],
        dict[str, Any],
        str,
        dict[str, Any],
    ]
]:
    """Compile arbitrary safe P8 edits, composing edits in the same SCNE.

    The result contains one non-overlapping fixed SCNE span per selected scene.
    This is why a project may safely edit several surfaces in one stadium: the
    SCNE is decoded once, all disjoint pixel/palette allocations are updated,
    and the resource is recompressed once.
    """

    _require(bool(edits), "Choose at least one Stadium texture to build")
    selectors = [selector for selector, _path in edits]
    _require(len(selectors) == len(set(selectors)), "Stadium texture target repeats")
    resolver = _DynamicStadiumResolver(index_path, inventory_path)
    grouped: dict[tuple[int, int, int], list[tuple[str, Path]]] = {}
    for selector, png in edits:
        outer, chunk, scene, _texture = _selector_parts(selector)
        grouped.setdefault((outer, chunk, scene), []).append((selector, png))
    results = []
    for _scene_key, rows in grouped.items():
        scene_selectors = [selector for selector, _png in rows]
        pngs = [png for _selector, png in rows]
        resolved = resolver.resolve_many(scene_selectors)
        compiled = _compile_resolved_scene(resolved, pngs)
        first = resolved[0].contract
        bundle_selector = (
            first.texture_id
            if len(rows) == 1
            else f"{first.scene_id}.texture-bundle"
        )
        target = first.target_metadata()
        target.update({
            "selector": bundle_selector,
            "texture_ids": scene_selectors,
            "texture_count": len(scene_selectors),
        })
        previews = [
            (
                f"stadium-{payload.contract.scene_index:04d}-"
                f"texture{payload.contract.texture_index:04d}-preview.png",
                payload.quantized_preview_png,
            )
            for payload in compiled.textures
        ]
        input_pngs = [
            {
                "target": payload.contract.texture_id,
                "path": str(path),
                "sha256": payload.replacement_png_sha256,
                "rgba_sha256": payload.replacement_rgba_sha256,
                "width": payload.contract.width,
                "height": payload.contract.height,
            }
            for payload, path in zip(compiled.textures, pngs)
        ]
        report = {
            "schema": UNIFIED_IMPORT_SCHEMA,
            "input_pngs": input_pngs,
            "target": target,
            "replacement": {
                "span_size": len(compiled.fixed.span),
                "span_sha256": _sha256_bytes(compiled.fixed.span),
                "encoded_sha256": compiled.fixed.encoded_sha256,
                "encoded_bytes": compiled.fixed.encoded_bytes,
                "zero_gap_bytes": compiled.fixed.zero_gap_bytes,
                "scratch_after": compiled.fixed.scratch_after,
                "decoded_after_sha256": compiled.fixed.decoded_sha256,
                "decoded_changed_byte_count": compiled.decoded_changed_byte_count,
            },
            "compiled_textures": [
                _compiled_payload_metadata(payload)
                for payload in compiled.textures
            ],
            "claims": {
                "source_derived_selector_resolution": True,
                "bounded_p8_textures_only": True,
                "complete_mip_chains_regenerated": True,
                "fixed_scne_allocation_preserved": True,
                "same_scene_edits_composed_before_compression": True,
                "opaque_tail_preserved": True,
                "geometry_materials_and_other_textures_preserved": True,
                "all_linked_material_surfaces_change_together": True,
                "contains_retail_bytes": False,
            },
        }
        results.append((
            compiled.fixed.span,
            previews,
            report,
            bundle_selector,
            target,
        ))
    return results


def build_unified_stadium_texture_import(
    index_path: Path,
    inventory_or_png: Path,
    selector: str | None = None,
    replacement_png: Path | None = None,
) -> tuple[
    bytes,
    list[tuple[str, bytes]],
    dict[str, Any],
    str,
    dict[str, Any],
]:
    """Backward-compatible single-target bridge for the unified provider."""

    if selector is None and replacement_png is None:
        # Legacy two-argument cement01 route.  The inventory stays in the same
        # private SourceCache as the extracted archive.
        replacement_png = inventory_or_png
        selector = TARGET_TEXTURE_ID
        inventory_path = (
            index_path.expanduser().resolve(strict=True).parents[3]
            / "indexes"
            / "nfl2k5_resource_chunks_v2.json"
        )
    else:
        inventory_path = inventory_or_png
    _require(
        isinstance(selector, str) and replacement_png is not None,
        "Stadium unified import arguments are incomplete",
    )
    results = build_unified_stadium_texture_imports(
        index_path,
        inventory_path,
        ((selector, replacement_png),),
    )
    _require(len(results) == 1, "Single Stadium import produced multiple resources")
    return results[0]


__all__ = [
    "BUILD_SCHEMA",
    "CompiledStadiumTextureEdit",
    "DynamicStadiumP8Contract",
    "FIXED_ALLOCATION_ERROR",
    "GENERAL_BUILD_SCHEMA",
    "Nfl2k5StadiumTextureWriter",
    "build_unified_stadium_texture_import",
    "build_unified_stadium_texture_imports",
    "SELECTOR_RE",
    "SHARED_OWNERSHIP_NOTE",
    "StadiumP8TargetContract",
    "StadiumTextureBuildResult",
    "StadiumTextureWriterError",
    "TARGET_SCENE_ID",
    "TARGET_TEXTURE_ID",
]
