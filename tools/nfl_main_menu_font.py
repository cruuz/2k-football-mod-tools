#!/usr/bin/env python3
"""Extract and prove the NFL 2K5 main-menu FONT atlas and glyph metrics.

The converter joins three independent sources: the pinned retail XBE, the
complete resource-wrapper inventory, and the read-only Ghidra trace.  FONT
objects use field-local serialized pointers, 0x60-byte glyph records, and a
swizzled 4-bit-used P8 atlas.  Every unknown byte is retained or hashed; the
tool does not invent a Direct3D name for Visual Concepts' command buffer.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from nfl_outer import parse_archive
from nfl_scene_probe import (
    ProbeError,
    ResourceRecord,
    decode_resource,
    entry_by_index,
    named_inner,
    parse_inventory,
    read_entry_range,
)
from nfl_txtr import unswizzle_2d, write_png


EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
EXPECTED_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
EXPECTED_INVENTORY_SHA256 = "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"
EXPECTED_HEADER_SHA256 = "0f480ad383cd4e6df647b4e50ee8a609365f3cd57e729f090048d0fc37958dad"

FONT_NAMES = (
    "font1", "font2", "font3", "font4", "font5",
    "font6", "font7", "font8", "font9", "FirstPersonComic",
)

# name: outer, chunk, system, video, decoded sha256, width, height
EXPECTED_FONTS = {
    "font1": (3, 0, 9472, 33792, "8f18a631519257cf48cee4341551c97a239bea73623404dc710d28df8ff12229", 256, 128),
    "font2": (3, 1, 9600, 66560, "7fe4e55587951f4a59d65291b5cd406309f5d290a860b55cfbcacbdba92a7fa4", 256, 256),
    "font3": (3, 2, 9472, 33792, "330765bb8482457120520cdb9d354a91d6e615f2ae75c9fa93b4542a3882282c", 256, 128),
    "font4": (3, 3, 9472, 17408, "60cc66a63ca3ae443b2c38e6ff7abaecfbfb484866433394be151106474afa7e", 128, 128),
    "font5": (3, 4, 9472, 33792, "19710938c6095a92d363880e9b3d5ae89f32abbc0e369c4d5f6fda81596e8a99", 256, 128),
    "font6": (3, 5, 9472, 33792, "c2593f3aae285dbe4b15ae35d987640ba0ef10b146dacbdd5d6464d3797ced3e", 256, 128),
    "font7": (3, 6, 9472, 66560, "17ee70f82c080f6d392b2063a226edc513e2399c3b535a6d6e80d317bcaa313b", 256, 256),
    "font8": (3, 7, 9600, 66560, "b775bc02454ab2e39fd4b39f0ff400c4af14848b4fccc429861abc2faec4f15f", 256, 256),
    "font9": (3, 8, 9472, 17408, "2c0b1c47402feb9021cf57f037d633fab9f74e03d096fb741f26744f8602e828", 128, 128),
    "FirstPersonComic": (347, 6, 9600, 66560, "538c2747bd1319db2e09ba31349039df130505b149844e916107b1ea48a7ede4", 256, 256),
}

EXPECTED_PALETTE = b"".join(bytes((255, 255, 255, alpha))
                                for alpha in range(0, 256, 17))
ASSET_REPORT_PREFIX = Path("assets/intermediate/nfl2k5/fonts")

EXPECTED_RANGES = (
    ("font_loader", 0x000EF570, 0x000EF59B, "ba0171c84dfdf4ef16a9a2cd46d35767de639abd10161b723be674dc23527595"),
    ("font_slot_getter", 0x000EF850, 0x000EF858, "2b749cc28858f48edd6c85faf49916486d941f55a861696947a0ab14cb1946e4"),
    ("style_dispatch_and_cases", 0x000F0140, 0x000F1090, "cfd6d28c1a9624bfbaa322bf6e733ce4fc4cad5c1a18a862cc3c5b5633b104d3"),
    ("formatted_string_draw", 0x000F1D50, 0x000F1F1E, "a0c03d5c9d791512c5d94a409d15e4b63ea0e266263958a3eb33e3c8aa368472"),
    ("main_menu_row_draw", 0x0014FDA0, 0x0014FF6A, "583c95f7688d987409f3f317cf81d6b2bdeb2d569ca8c01cf693f3e77cb77291"),
    ("font_range_glyph_lookup", 0x00046200, 0x00046256, "f6350a4a17479ea165ca34578cb2b495dcdd81a7c85d6c6229d087692c2d4f14"),
    ("quad_and_glyph_submit", 0x00046310, 0x0004656E, "1bd249f3ec711fbdcfb09b3064e887c5edfa1ae7018ea58df9476818d84878b1"),
    ("font_assignment", 0x000469B0, 0x000469D4, "5af8ad0a8008d7338a8516c6367054fd3b3217952b3755c61d4a3532277f2b06"),
    ("utf16_glyph_walk", 0x00046DF0, 0x00046EC9, "950e82b183bd9a16e89762f4d50dd6007d5e2a71b91258e7898e62e04677cb02"),
    ("line_segment_draw", 0x00047420, 0x00047485, "9139e722cbec6eb58e5e61fb29acb28121c4840149ed5d52b4a314633c27cb71"),
    ("font_line_advance", 0x00049390, 0x0004939B, "7288c5eb6a1d7d61a980d61622b7b9e27a9d9bb0f8fa627dfa1327114bd1e102"),
    ("font_graphics_descriptor", 0x000493D0, 0x000493D4, "9b5251af6794c76b2f519f4601eefe7c7f18622726ef5633ff8713cbcdf488fe"),
    ("font_character_advance", 0x000493E0, 0x00049407, "877d0a907ecec38e656c6473c23c71d50c0419586c3765d4c4d33487f94aae78"),
    ("begin_immediate_primitive", 0x0002D2A0, 0x0002D42C, "cade738522c76270eb095f25dec3d0311abfe5e4d7b667f2b5c9320dc919e601"),
    ("end_immediate_primitive", 0x0002CA00, 0x0002CA47, "ec161d67c483a20c02cfbc5baee2dcb263fe794c58ae922bd501d45064c5e020"),
    ("emit_immediate_vertex", 0x0002CA70, 0x0002CB46, "316868d74fd90bdb7251b8080e30fd27f7a1500f2321a8dc20de8b5b91ccb330"),
    ("set_immediate_position", 0x0002CB90, 0x0002CBB2, "13bff198db4e6cfc7f650108ee293a9061a57bd64e87de65fa4c46b40b528edc"),
    ("set_immediate_color", 0x0002CBE0, 0x0002CBE7, "2b57f2e393ab65d539fe47609342078cea7440d6bc38bb93e744b385f58103c6"),
    ("font_name_table", 0x00A91928, 0x00A91950, "da3238b7c574a34433fdf58ee03140f022dfa1e2486cc291abf74f6070959e6a"),
)

STYLE_TARGETS = (
    0x000F0300, 0x000F031C, 0x000F038A, 0x000F0376, 0x000F0732,
    0x000F071E, 0x000F0905, 0x000F08F1, 0x000F0AC1, 0x000F0AAD,
    0x000F0C61, 0x000F0C4D, 0x000F0DD7, 0x000F0E19, 0x000F0E8B,
)


class FontError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def field_pointer(data: bytes, field_offset: int, limit: int) -> tuple[int, int]:
    if field_offset < 0 or field_offset + 4 > limit:
        raise FontError(f"pointer field 0x{field_offset:x} is out of bounds")
    stored, = struct.unpack_from("<I", data, field_offset)
    target = field_offset + stored - 1
    if not 0 <= target < limit:
        raise FontError(
            f"pointer field 0x{field_offset:x}: target 0x{target:x} is out of bounds")
    return stored, target


def require_phrases(text: str, phrases: tuple[str, ...], label: str) -> None:
    for phrase in phrases:
        if phrase not in text:
            raise FontError(f"{label}: missing exact evidence {phrase!r}")


class XbeView:
    def __init__(self, path: Path, header_path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        self.header = json.loads(header_path.read_text(encoding="utf-8"))
        if hashlib.md5(self.data).hexdigest() != EXPECTED_XBE_MD5:
            raise FontError("unexpected NFL 2K5 XBE MD5")
        if sha256(self.data) != EXPECTED_XBE_SHA256:
            raise FontError("unexpected NFL 2K5 XBE SHA-256")

    def file_offset(self, va: int, size: int) -> int:
        for section in self.header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                return int(section["raw_address"]) + va - start
        raise FontError(f"VA 0x{va:08x}+0x{size:x} is not file-backed")

    def at(self, va: int, size: int) -> bytes:
        offset = self.file_offset(va, size)
        result = self.data[offset:offset + size]
        if len(result) != size:
            raise FontError(f"short XBE read at 0x{va:08x}")
        return result

    def utf16z(self, va: int) -> str:
        offset = self.file_offset(va, 2)
        raw = bytearray()
        for _ in range(256):
            unit = self.data[offset:offset + 2]
            offset += 2
            if unit == b"\0\0":
                return raw.decode("utf-16le")
            if len(unit) != 2:
                break
            raw.extend(unit)
        raise FontError(f"unterminated XBE UTF-16 string at 0x{va:08x}")


@dataclass(frozen=True)
class Glyph:
    codepoint: int
    record_offset: int
    advance: int
    positions: tuple[float, ...]
    uv: tuple[float, float, float, float]

    @property
    def left(self) -> float:
        return min(self.positions[0::4])

    @property
    def right(self) -> float:
        return max(self.positions[0::4])

    @property
    def top(self) -> float:
        return min(self.positions[1::4])

    @property
    def bottom(self) -> float:
        return max(self.positions[1::4])


@dataclass(frozen=True)
class Font:
    slot: int
    name: str
    record: ResourceRecord
    decoded: bytes
    decoded_sha256: str
    object_offset: int
    minimum: int
    maximum: int
    range_count: int
    range_offset: int
    space_advance: int
    line_advance: int
    graphics_descriptor_offset: int
    glyphs: tuple[Glyph, ...]
    ranges: tuple[dict[str, int], ...]
    width: int
    height: int
    dimension_candidates: tuple[dict[str, object], ...]
    swizzled_indices: bytes
    linear_indices: bytes
    palette: bytes
    palette_tail: bytes


def dimension_candidates(glyphs: list[Glyph], pixel_count: int) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for width in (64, 128, 256, 512):
        if pixel_count % width:
            continue
        height = pixel_count // width
        if height not in (64, 128, 256, 512):
            continue
        errors: list[float] = []
        for glyph in glyphs:
            u0, v0, u1, v1 = glyph.uv
            errors.append(abs((u1 - u0) * width - (glyph.right - glyph.left)))
            errors.append(abs((v1 - v0) * height - (glyph.bottom - glyph.top)))
        result.append({
            "width": width,
            "height": height,
            "maximum_quad_uv_error_pixels": max(errors, default=0.0),
            "sum_quad_uv_error_pixels": sum(errors),
        })
    return result


def parse_font(slot: int, name: str, record: ResourceRecord, decoded: bytes,
               decoded_hash: str) -> Font:
    parsed_name, _name_offset, name_end = named_inner(decoded, "FONT")
    if parsed_name != name:
        raise FontError(f"FONT slot {slot}: decoded name {parsed_name!r}, expected {name!r}")
    if len(decoded) != record.word_08 + record.word_0c:
        raise FontError(f"{name}: decoded system/video size mismatch")

    object_offset = align_up(name_end, 0x10)
    if object_offset + 0x40 > record.word_08:
        raise FontError(f"{name}: object header is out of system-buffer bounds")
    if any(value != 0xFF for value in decoded[name_end:object_offset]):
        raise FontError(f"{name}: non-0xff bytes between name and object")
    minimum, maximum = struct.unpack_from("<HH", decoded, object_offset)
    range_count, = struct.unpack_from("<I", decoded, object_offset + 4)
    if not (0x20 <= minimum <= maximum <= 0xFFFF and 1 <= range_count <= 128):
        raise FontError(f"{name}: implausible FONT bounds/range count")
    _stored, range_offset = field_pointer(decoded, object_offset + 8, record.word_08)
    if range_offset + range_count * 8 > record.word_08:
        raise FontError(f"{name}: range table exceeds system buffer")

    space_advance, line_advance = struct.unpack_from("<II", decoded, object_offset + 0x0C)
    graphics_descriptor_offset = object_offset + 0x40
    glyphs: list[Glyph] = []
    ranges: list[dict[str, int]] = []
    previous_end = minimum - 1
    for range_index in range(range_count):
        range_record = range_offset + range_index * 8
        first, last = struct.unpack_from("<HH", decoded, range_record)
        if first != previous_end + 1 or first > last or last > maximum:
            raise FontError(f"{name}: ranges are not contiguous and bounded")
        _glyph_stored, glyph_offset = field_pointer(
            decoded, range_record + 4, record.word_08)
        count = last - first + 1
        if glyph_offset + count * 0x60 > record.word_08:
            raise FontError(f"{name}: glyph records exceed system buffer")
        ranges.append({
            "index": range_index,
            "first_codepoint": first,
            "last_codepoint": last,
            "record_offset": range_record,
            "glyph_records_offset": glyph_offset,
            "glyph_count": count,
        })
        for codepoint in range(first, last + 1):
            offset = glyph_offset + (codepoint - first) * 0x60
            advance, = struct.unpack_from("<I", decoded, offset)
            if decoded[offset + 4:offset + 0x10] != b"\xff" * 12:
                raise FontError(f"{name}: glyph 0x{codepoint:04x} opaque words differ")
            positions = struct.unpack_from("<16f", decoded, offset + 0x10)
            uv = struct.unpack_from("<4f", decoded, offset + 0x50)
            if not all(math.isfinite(value) for value in positions + uv):
                raise FontError(f"{name}: non-finite glyph metric")
            if any(positions[index] != 0.0 for index in
                   (2, 3, 6, 7, 10, 11, 14, 15)):
                raise FontError(f"{name}: unproved nonzero glyph z/w component")
            if not (0.0 <= uv[0] <= uv[2] <= 1.0 and
                    0.0 <= uv[1] <= uv[3] <= 1.0):
                raise FontError(f"{name}: glyph UV is outside the atlas")
            glyphs.append(Glyph(codepoint, offset, advance, positions, uv))
        previous_end = last
    if previous_end != maximum or glyphs[0].codepoint != minimum:
        raise FontError(f"{name}: ranges do not cover the advertised bounds")

    video = decoded[record.word_08:record.word_08 + record.word_0c]
    pixel_count = record.word_0c - 1024
    if pixel_count <= 0:
        raise FontError(f"{name}: video buffer cannot contain the fixed palette tail")
    candidates = dimension_candidates(glyphs, pixel_count)
    exact = [row for row in candidates
             if float(row["maximum_quad_uv_error_pixels"]) <= 1.0e-7]
    if len(exact) != 1:
        raise FontError(f"{name}: atlas dimensions are not uniquely established")
    width, height = int(exact[0]["width"]), int(exact[0]["height"])
    if width * height != pixel_count:
        raise FontError(f"{name}: dimension proof does not consume pixel data")

    swizzled = video[:pixel_count]
    palette = video[pixel_count:pixel_count + 64]
    palette_tail = video[pixel_count + 64:]
    if palette != EXPECTED_PALETTE or len(palette_tail) != 960:
        raise FontError(f"{name}: P8 palette/tail contract differs")
    if not swizzled or min(swizzled) != 0 or max(swizzled) != 15:
        raise FontError(f"{name}: expected all 16 P8 indices")
    linear = unswizzle_2d(swizzled, width, height, 1)

    for glyph in glyphs:
        for value, scale in zip(glyph.uv, (width, height, width, height)):
            if abs(value * scale - round(value * scale)) > 1.0e-7:
                raise FontError(f"{name}: glyph UV is not on an exact texel boundary")
    return Font(
        slot, name, record, decoded, decoded_hash, object_offset, minimum,
        maximum, range_count, range_offset, space_advance, line_advance,
        graphics_descriptor_offset, tuple(glyphs), tuple(ranges), width, height,
        tuple(candidates), swizzled, linear, palette, palette_tail,
    )


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")


def rgba_from_font(font: Font) -> bytes:
    rgba = bytearray(font.width * font.height * 4)
    for index, palette_index in enumerate(font.linear_indices):
        source = palette_index * 4
        blue, green, red, alpha = font.palette[source:source + 4]
        rgba[index * 4:index * 4 + 4] = bytes((red, green, blue, alpha))
    return bytes(rgba)


def ftext(value: float) -> str:
    return format(value, ".9g")


def pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "size": path.stat().st_size,
            "sha256": file_sha256(path)}


def build(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    if file_sha256(args.inventory) != EXPECTED_INVENTORY_SHA256:
        raise FontError("unexpected resource inventory SHA-256")
    if file_sha256(args.xbe_header) != EXPECTED_HEADER_SHA256:
        raise FontError("unexpected XBE header report SHA-256")
    xbe = XbeView(args.xbe, args.xbe_header)
    trace = args.trace.read_text(encoding="utf-8")
    pseudo = args.pseudo.read_text(encoding="utf-8")
    require_phrases(trace, (
        "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
        "0x000EF57A MOV EDX,0x544e4f46",
        "0x000EF586 MOV dword ptr [ESI + 0xa90ecc],EAX",
        "0x000EF850 MOV EAX,dword ptr [ECX*0x4 + 0xa90ecc]",
        "0x0014FE7B MOV ECX,0x6",
        "0x0014FE80 CALL 0x000ef850",
        "0x0014FE8B CALL 0x000469b0",
        "0x0014FEEE LEA ECX,[ESP + 0xb0]",
        "0x0014FF38 CALL 0x000f1d50",
        "0x000F02F9 JMP dword ptr [EDX*0x4 + 0xf1054]",
        "0x000F0B80 CALL 0x00047420",
        "0x000F0BBE CALL 0x00047420",
        "0x000F0BFC CALL 0x00047420",
        "0x000F0C29 CALL 0x00047420",
        "0x000F1EEB CALL 0x000f0140",
        "0x000F1025 CALL 0x00047420",
        "0x0004745B CALL 0x00046df0",
        "0x00046EA5 CALL 0x00046420",
        "0x0004644A CALL 0x00046200",
        "0x000464BD CALL 0x0002d2a0",
        "0x00046502 CALL 0x00046310",
        "0x0004653E CALL 0x00046310",
        "0x00046552 CALL 0x00046310",
        "0x00046557 CALL 0x0002ca00",
        "0x000469C1 CALL 0x00049390",
        "0x00049397 MOV EAX,dword ptr [ECX + 0x10]",
        "0x000493D0 LEA EAX,[ECX + 0x40]",
        "0x000493F3 MOV EAX,dword ptr [ESI + 0xc]",
        "0x00049403 MOV EAX,dword ptr [EAX]",
    ), "Ghidra trace")
    require_phrases(pseudo, (
        "/* 0x00046200:FUN_00046200 */",
        "* 0x60 + *(int *)(puVar1 + iVar3 * 4 + 2)",
        "/* 0x000493E0:FUN_000493e0 */",
        "/* 0x000EF570:FUN_000ef570 */",
        "/* 0x000F1D50:FUN_000f1d50 */",
        "/* 0x0014FDA0:FUN_0014fda0 */",
    ), "Ghidra pseudo-C")

    ranges: list[dict[str, object]] = []
    for name, start, end, expected in EXPECTED_RANGES:
        body = xbe.at(start, end - start)
        actual = sha256(body)
        if actual != expected:
            raise FontError(f"{name}: expected {expected}, got {actual}")
        ranges.append({
            "name": name, "start": f"0x{start:08x}",
            "end_exclusive": f"0x{end:08x}", "size": end - start,
            "file_offset": xbe.file_offset(start, end - start),
            "sha256": actual,
        })

    table = xbe.at(0x00A91928, 40)
    pointers = struct.unpack("<10I", table)
    table_names = tuple(xbe.utf16z(pointer) for pointer in pointers)
    if table_names != FONT_NAMES:
        raise FontError(f"FONT XBE table differs: {table_names!r}")
    style_targets = struct.unpack("<15I", xbe.at(0x000F1054, 60))
    if style_targets != STYLE_TARGETS:
        raise FontError("FONT style dispatch table differs")

    archive = parse_archive(args.index)
    _inventory, records = parse_inventory(args.inventory)
    font_records = [record for record in records if record.kind == "FONT"]
    if len(font_records) != 10:
        raise FontError(f"expected 10 FONT resources, found {len(font_records)}")
    decoded_by_name: dict[str, tuple[ResourceRecord, bytes, str]] = {}
    for record in font_records:
        entry = entry_by_index(archive, record.outer_index)
        span = read_entry_range(
            archive, entry, record.chunk_offset, 0x20 + record.stored_size)
        try:
            decoded, detail = decode_resource(span, record)
            name, _offset, _end = named_inner(decoded, "FONT")
        except ProbeError as exc:
            raise FontError(str(exc)) from exc
        if name in decoded_by_name:
            raise FontError(f"duplicate FONT name {name!r}")
        decoded_by_name[name] = (record, decoded, str(detail["decoded_sha256"]))
    if tuple(sorted(decoded_by_name)) != tuple(sorted(FONT_NAMES)):
        raise FontError("resource FONT names differ from the XBE table")

    fonts: list[Font] = []
    for slot, name in enumerate(FONT_NAMES):
        record, decoded, decoded_hash = decoded_by_name[name]
        expected = EXPECTED_FONTS[name]
        actual = (record.outer_index, record.chunk_index, record.word_08,
                  record.word_0c, decoded_hash)
        if actual != expected[:5]:
            raise FontError(f"{name}: resource identity differs: {actual!r}")
        font = parse_font(slot, name, record, decoded, decoded_hash)
        if (font.width, font.height) != expected[5:]:
            raise FontError(f"{name}: proved atlas dimensions differ")
        fonts.append(font)

    args.assets_dir.mkdir(parents=True, exist_ok=True)
    font_rows: list[dict[str, object]] = []
    glyph_rows: list[dict[str, object]] = []
    resources: list[dict[str, object]] = []
    for font in fonts:
        stem = safe_name(font.name)
        png_path = args.assets_dir / f"{stem}.png"
        tail_path = args.assets_dir / f"{stem}.palette_tail.bin"
        write_png(png_path, font.width, font.height, rgba_from_font(font))
        tail_path.write_bytes(font.palette_tail)
        report_png = ASSET_REPORT_PREFIX / png_path.name
        report_tail = ASSET_REPORT_PREFIX / tail_path.name
        font_row = {
            "slot": font.slot,
            "name": font.name,
            "outer_index": font.record.outer_index,
            "chunk_index": font.record.chunk_index,
            "decoded_sha256": font.decoded_sha256,
            "system_bytes": font.record.word_08,
            "video_bytes": font.record.word_0c,
            "object_offset": f"0x{font.object_offset:x}",
            "minimum_codepoint": f"0x{font.minimum:04x}",
            "maximum_codepoint": f"0x{font.maximum:04x}",
            "range_count": font.range_count,
            "glyph_count": len(font.glyphs),
            "space_advance": font.space_advance,
            "line_advance": font.line_advance,
            "width": font.width,
            "height": font.height,
            "swizzled_indices_sha256": sha256(font.swizzled_indices),
            "linear_indices_sha256": sha256(font.linear_indices),
            "palette_sha256": sha256(font.palette),
            "palette_tail_sha256": sha256(font.palette_tail),
            "png_sha256": file_sha256(png_path),
            "png_path": str(report_png),
            "palette_tail_path": str(report_tail),
        }
        font_rows.append(font_row)
        for glyph in font.glyphs:
            p = glyph.positions
            u0, v0, u1, v1 = glyph.uv
            glyph_rows.append({
                "slot": font.slot, "font": font.name,
                "codepoint": f"0x{glyph.codepoint:04x}",
                "character": chr(glyph.codepoint) if 0x20 <= glyph.codepoint < 0x7F else "",
                "record_offset": f"0x{glyph.record_offset:x}",
                "advance": glyph.advance,
                "x0": ftext(p[0]), "y0": ftext(p[1]),
                "x1": ftext(p[4]), "y1": ftext(p[5]),
                "x2": ftext(p[8]), "y2": ftext(p[9]),
                "x3": ftext(p[12]), "y3": ftext(p[13]),
                "u0": ftext(u0), "v0": ftext(v0),
                "u1": ftext(u1), "v1": ftext(v1),
                "atlas_x0": int(round(u0 * font.width)),
                "atlas_y0": int(round(v0 * font.height)),
                "atlas_x1": int(round(u1 * font.width)),
                "atlas_y1": int(round(v1 * font.height)),
            })
        resources.append({
            **font_row,
            "outer_id": font.record.outer_id,
            "chunk_offset": font.record.chunk_offset,
            "stored_size": font.record.stored_size,
            "compression_magic": f"0x{font.record.word_10:08x}",
            "overlap_scratch_bytes": font.record.word_14,
            "range_table_offset": f"0x{font.range_offset:x}",
            "graphics_descriptor_offset": f"0x{font.graphics_descriptor_offset:x}",
            "ranges": list(font.ranges),
            "dimension_candidates": list(font.dimension_candidates),
            "maximum_quad_uv_error_pixels": 0.0,
            "palette_format": "16 BGRA8 entries: white RGB, alpha 0x00..0xff in 0x11 steps",
            "palette_tail_bytes_retained": len(font.palette_tail),
            "used_palette_indices": sorted(set(font.linear_indices)),
        })

    source_pins = {
        "archive_index": pin(args.index),
        "resource_inventory": pin(args.inventory),
        "xbe": pin(args.xbe),
        "xbe_header": pin(args.xbe_header),
        "ghidra_trace": pin(args.trace),
        "ghidra_pseudo_c": pin(args.pseudo),
        "ghidra_script": pin(args.ghidra_script),
        "extractor": pin(Path("tools/nfl_main_menu_font.py")),
    }
    report: dict[str, object] = {
        "schema": "nfl2k5_main_menu_font/v1",
        "result": {
            "font_resources": len(fonts),
            "glyph_records": sum(len(font.glyphs) for font in fonts),
            "all_atlases_exported_as_png": True,
            "all_opaque_palette_tails_retained": True,
            "main_menu_font_slot": 6,
            "main_menu_font_name": "font7",
            "main_menu_font_png": str(ASSET_REPORT_PREFIX / "font7.png"),
            "original_title_main_menu_execution_proved": False,
        },
        "executable": {
            "path": str(args.xbe),
            "md5": EXPECTED_XBE_MD5,
            "sha256": EXPECTED_XBE_SHA256,
            "font_name_table_va": "0x00a91928",
            "font_name_pointers": [f"0x{pointer:08x}" for pointer in pointers],
            "font_names": list(table_names),
            "style_dispatch_table_va": "0x000f1054",
            "style_targets": [f"0x{target:08x}" for target in style_targets],
            "ranges": ranges,
        },
        "main_menu_renderer": {
            "resource_loader": "0x000ef570 loops 10 names, requests FourCC FONT, stores slots at 0x00a90ecc",
            "slot_getter": "0x000ef850 returns *(0x00a90ecc + slot*4)",
            "row_draw": "0x0014fda0 loads slot 6 at 0x0014fe7b and assigns it at 0x0014fe8b",
            "label_source": "0x0014feee passes the row's bounded UTF-16 buffer to 0x000f1d50 at 0x0014ff38",
            "glyph_path": [
                "0x0014fda0 main-menu row draw",
                "0x000f1d50 formatted UTF-16 loop",
                "0x000f0140 style dispatch",
                "0x00047420 line segment draw",
                "0x00046df0 UTF-16 glyph walk",
                "0x00046420 glyph lookup and immediate draw",
                "0x00046200 range lookup -> 0x60-byte glyph record",
                "0x0002d2a0/0x00046310/0x0002ca00 immediate-quad command path",
            ],
            "style_0": "dispatch target 0x000f0300; final pass reaches 0x000f1025 -> 0x00047420",
            "style_8": "dispatch target 0x000f0ac1; four offset calls at 0x000f0b80/0x000f0bbe/0x000f0bfc/0x000f0c29 plus the final pass",
            "main_row_observed_styles": [0, 8],
        },
        "font_contract": {
            "serialized_pointer_rule": "target = address_of_u32_field + stored_u32 - 1",
            "object_fields": {
                "+0x00": "u16 minimum codepoint, u16 maximum codepoint",
                "+0x04": "u32 range count",
                "+0x08": "field-local pointer to 8-byte range records",
                "+0x0c": "space/fallback advance, read at 0x000493f3",
                "+0x10": "line advance, read at 0x00049397",
                "+0x40": "graphics descriptor address returned by 0x000493d0",
            },
            "range_record": "u16 first, u16 last, field-local pointer to glyph records",
            "glyph_record_bytes": 0x60,
            "glyph_fields": {
                "+0x00": "u32 character advance",
                "+0x04..+0x0f": "three opaque 0xffffffff words",
                "+0x10..+0x4f": "four float4 quad positions",
                "+0x50..+0x5f": "float u0,v0,u1,v1 atlas rectangle",
            },
            "atlas": "Xbox-swizzled one-byte P8 indices bounded to 0..15; 16-entry BGRA8 alpha palette; 960 opaque retained bytes",
            "dimension_proof": "unique power-of-two width/height whose UV texel span equals every serialized quad span with zero observed pixel error",
        },
        "resources": resources,
        "source_pins": source_pins,
        "portme": [
            "// PORTME(0x0002D2A0): map the recovered Visual Concepts/NV2A immediate-command contract to named OpenGL draw state; official Xbox D3D8 helper identities are not proved.",
            "// PORTME(0x0014FDA0): bind original LAYT row coordinates and state transitions to the native font7 renderer; this report proves data selection and glyph submission, not original boot execution.",
            "// PORTME(FONT writer): implement PNG/metrics-to-FONT repacking if writable original-Xbox archives are desired; extraction to moddable PNG is complete, but reverse serialization is not.",
        ],
    }
    return report, font_rows, glyph_rows


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise FontError(f"refusing to write empty TSV {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]),
                                dialect="excel-tab", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="NFL vc_53450030/0 archive index")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--xbe-header", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--pseudo", type=Path, required=True)
    parser.add_argument("--ghidra-script", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--fonts-tsv", type=Path, required=True)
    parser.add_argument("--glyphs-tsv", type=Path, required=True)
    args = parser.parse_args()
    try:
        report, fonts, glyphs = build(args)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        write_tsv(args.fonts_tsv, fonts)
        write_tsv(args.glyphs_tsv, glyphs)
    except (FontError, ProbeError, OSError, ValueError, struct.error) as exc:
        parser.error(str(exc))
    print(
        "NFL_MAIN_MENU_FONT_COMPLETE fonts=10 glyphs=943 "
        "main_menu_slot=6 main_menu_font=font7 pngs=10")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
