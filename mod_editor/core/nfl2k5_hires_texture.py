"""Bounded P8 family compiler. EXPERIMENTAL / UNWITNESSED.

This is separate from the fixed-span writers. Ordinary TXTRs change two
descriptor words. Pinned two-palette jersey TSETs and appended SCNE midfield
rasters have separate layout validators. Linear name strips remain refused.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import io
import struct

from PIL import Image
from tools import nfl_txtr as txtr
from tools import nfl_tset_png_import as palettes

VERSION = "nfl2k5_hires_texture/v2"
MAX_SPAN = 2 * 1024**2
MAX_SCENE_SPAN = 8 * 1024**2


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Asset:
    key: str
    outer: int
    chunk: int
    name_id: int
    name: str
    native: int
    levels: int
    descriptor: int
    stream_tag: int
    offset_bits: int
    retail_sha256: str
    system_sha256: str
    native_height: int = 0
    family: str = ""
    kit: str = ""
    kind: str = "TXTR"
    system_size: int = 128
    second_descriptor: int = 0
    original_video: int = 0
    original_pixels: int = 0
    original_palette: int = 0
    baseline_sha256: str = ""

    @property
    def height(self):
        return self.native_height or self.native

    @property
    def palette_count(self):
        return 2 if self.kind == "TSET" else 1

    @property
    def consumer(self):
        return {"helmets": "helmet", "field_logos": "field_logo", "stock_fields": "stock_fields",
                "numbers": "numbers", "jerseys": "jerseys", "scorebug": "scorebug"}.get(self.family, self.key)

    def dimensions(self, scale):
        require(type(scale) is int and scale in (1, 2), "Only native or 2x output is supported")
        return [(self.native * scale >> i, self.height * scale >> i) for i in range(self.levels)]

    def format_word(self, scale):
        exponent = (self.native * scale).bit_length() - 1
        height_exponent = (self.height * scale).bit_length() - 1
        return 0xB29 | (self.levels << 16) | (exponent << 20) | (height_exponent << 24)

    def video_size(self, scale):
        return sum(w*h for w, h in self.dimensions(scale)) + 1024*self.palette_count


ASSETS = (
    Asset("scorebug", 346, 53, 0x00B6926C, "score_buga", 64, 1, 56, 1, 11,
          "b17fe5ddc714bc2f508e38cbff5143d86828e9bca4748011dd54200624583b21",
          "7c4a0f68f81db5db40ebf33a3084e95f4b85f019774f6663302aa9ba85ceb170"),
    Asset("field_logo", 384, 0, 0xD4DE004F, "center_logo", 256, 6, 56, 113, 10,
          "ea7da5c66e03f8bdf1724a73f021ccaf6b8bb4726179d449a65e783b0192a010",
          "86a78c124024902d492a4b4db219e02df1811c62e7694a088b9ee7ec643ebb6d"),
    Asset("helmet", 3613, 11, 0x341ECD96, "helmet00", 256, 6, 52, 115, 10,
          "c6f56638ebf3c77993d87f810cd31b6d7abc2b754da8172ed5184e4bc7508725",
          "3204efb25d509873cffe3e0d17c2d43c9fe77010a34d023b4e608bccec70b133"),
)
PILOT_ASSETS = ASSETS
# Generated, reviewable metadata only; no game bytes or runtime research files.
from .nfl2k5_hires_catalog import ROWS
ASSETS = ASSETS + tuple(Asset(**row) for row in ROWS)
BY_KEY = {a.key: a for a in ASSETS}


def inspect_span(raw, asset):
    """Validate layout before decode. Structural validity alone is not ownership."""
    if asset.kind != "TXTR":
        from .nfl2k5_hires_layouts import inspect_span as inspect_layout
        return inspect_layout(raw, asset)
    require(isinstance(raw, bytes) and 42 <= len(raw) <= MAX_SPAN, "Texture span exceeds bounds")
    fields = txtr.HEADER.unpack_from(raw)
    kind, stored, system, video, magic, scratch, r0, r1 = fields
    require(kind == b"TXTR" and stored == len(raw) - 32 and stored % 16 == 0
            and system == 128 and magic == txtr.COMPRESSED_SENTINEL and r0 == r1 == 0
            and scratch <= MAX_SPAN and scratch % 16 == 0, "Foreign texture wrapper")
    sizes = {sum(w*h for w, h in asset.dimensions(s)) + 1024: s for s in (1, 2)}
    require(video in sizes, "Foreign texture video allocation")
    scale = sizes[video]
    chunk = txtr.parse_chunks(raw)[0]
    decoded, compression = txtr.decode_chunk(raw, chunk)
    texture = txtr.parse_texture(decoded, chunk)
    require(texture.name == asset.name and texture.name_offset == 32
            and texture.descriptor_offset == asset.descriptor and texture.pixel_offset == 0
            and texture.palette_offset == video - 1024
            and texture.packed_format == asset.format_word(scale)
            and texture.packed_size == 0 and texture.descriptor_flags == 0x80000000,
            "Foreign texture descriptor or shared layout")
    system_data = bytearray(decoded[:128])
    struct.pack_into("<II", system_data, asset.descriptor + 8,
                     sum(w*h for w, h in asset.dimensions(1)), asset.format_word(1))
    require(sha(system_data) == asset.system_sha256, "Foreign texture system object")
    require(compression.stream_tag == asset.stream_tag and compression.offset_bits == asset.offset_bits,
            "Foreign VC-LZ stream parameters")
    stream = raw[32:32 + compression.consumed_bytes]
    minimum = txtr.minimum_vc_lz_overlap_scratch(stream, stored, len(decoded))
    require(scratch >= max(minimum, stored - compression.consumed_bytes, stored - len(decoded)),
            "Unsafe in-place decompression scratch")
    palette = palettes.parse_palette(decoded[128:], video - 1024)
    levels, at = [], 128
    for i, (width, height) in enumerate(asset.dimensions(scale)):
        indices = txtr.unswizzle_2d(decoded[at:at + width*height], width, height, 1)
        rgba = palettes.rgba_from_indices(indices, palette)
        levels.append(dict(level=i, width=width, height=height, index_sha256=sha(indices),
                           rgba_sha256=sha(rgba)))
        at += width*height
    return dict(key=asset.key, scale=scale, descriptor_hex=decoded[asset.descriptor:asset.descriptor+24].hex(),
                span_sha256=sha(raw), decoded_sha256=sha(decoded), system_bytes=system, video_bytes=video,
                stored_bytes=stored, span_bytes=len(raw), scratch_bytes=scratch,
                load_allocation_bytes=system + video + scratch,
                palette_sha256=sha(decoded[-1024:]), palette_offset=video-1024,
                compression=asdict(compression), minimum_overlap_scratch=minimum, mips=levels), bytes(system_data)


def png_rgba(payload, asset):
    require(isinstance(payload, bytes) and 0 < len(payload) <= 32*1024**2, "PNG exceeds 32 MiB")
    with Image.open(io.BytesIO(payload)) as image:
        require(image.format == "PNG" and image.size == (asset.native*2, asset.height*2)
                and getattr(image, "n_frames", 1) == 1, f"{asset.key}: supply an exact {asset.native*2}x{asset.height*2} PNG")
        return image.convert("RGBA").tobytes()


def _mips(rgba, asset, scale):
    return _raster_mips(rgba, asset.native, asset.height, asset.levels, scale)


@lru_cache(maxsize=4)
def _raster_mips(rgba, native, native_height, levels, scale):
    """Same round-half-up RGBA box rule as the retail live-helmet importer."""
    result = []
    width, height = native*2, native_height*2
    # Native output starts from the retained 2x authoring raster, never P8 output.
    count = levels + (1 if scale == 1 else 0)
    current = rgba
    for level in range(count):
        if level >= (1 if scale == 1 else 0):
            result.append(palettes.MipLevel(len(result), width, height, current))
        if level + 1 == count:
            break
        down = bytearray(width*height)
        for y in range(height//2):
            for x in range(width//2):
                offsets = (((2*y)*width+2*x)*4, ((2*y)*width+2*x+1)*4,
                           ((2*y+1)*width+2*x)*4, ((2*y+1)*width+2*x+1)*4)
                at = (y*(width//2)+x)*4
                for channel in range(4):
                    down[at+channel] = (sum(current[o+channel] for o in offsets)+2)//4
        width //= 2
        height //= 2
        current = bytes(down)
    return result


def compile_texture(system, rgba, asset, scale):
    if asset.kind != "TXTR":
        from .nfl2k5_hires_layouts import compile_texture as compile_layout
        return compile_layout(system, rgba, asset, scale)
    require(sha(system) == asset.system_sha256, "Compiler requires the pinned native system object")
    require(len(rgba) == asset.native*asset.height*16, "Authored raster size differs")
    asset.dimensions(scale)
    levels = _mips(rgba, asset, scale)
    palette, indices, quality = _quantized(rgba, asset.native, asset.height, asset.levels, scale)
    video = b"".join(txtr.swizzle_2d(ind, mip.width, mip.height, 1)
                     for ind, mip in zip(indices, levels)) + palettes.palette_bytes(palette)
    header = bytearray(system)
    struct.pack_into("<II", header, asset.descriptor+8, len(video)-1024, asset.format_word(scale))
    decoded = bytes(header) + video
    encoded, compression = txtr.compress_vc_lz(decoded, stream_tag=asset.stream_tag,
        offset_bits=asset.offset_bits, max_encoded_size=MAX_SPAN-32, max_candidate_comparisons=50_000_000)
    stored = (len(encoded)+15) & ~15
    minimum = txtr.minimum_vc_lz_overlap_scratch(encoded, stored, len(decoded))
    scratch = (max(minimum, stored-len(encoded), stored-len(decoded))+15) & ~15
    raw = txtr.HEADER.pack(b"TXTR", stored, 128, len(video), txtr.COMPRESSED_SENTINEL, scratch, 0, 0)
    raw += encoded + bytes(stored-len(encoded))
    checked, _ = inspect_span(raw, asset)
    for mip, ind, result in zip(levels, indices, checked["mips"]):
        require(result["rgba_sha256"] == sha(palettes.rgba_from_indices(ind, palette)), "Mip read-back differs")
    return raw, dict(compiler=VERSION, quality=dict(quality), encoder=asdict(compression),
                     mip_policy="retain-retail-count", mip_filter="RGBA box, round half up",
                     decoded=checked, authored_rgba_sha256=sha(rgba))


@lru_cache(maxsize=4)
def _quantized(rgba, width, height, levels, scale):
    return palettes.quantize_levels(_raster_mips(rgba, width, height, levels, scale))
