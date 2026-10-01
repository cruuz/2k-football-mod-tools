"""2026 kick meter, experimental: the kick HUD redrawn in the 2026 ESPN bar's look, with the retail behaviour.

Three scene resources of ``gamedata.iff`` (outer 346, pack 0) make the kick HUD (beta 76 km census):

- ``KickArrow`` (chunk 75): the aim arrow, its shadow and the tick row drawn in the world at the ball. Here its
  32x32 texture turns white over black (arrow and ticks white, shadow black).
- ``KickMeter`` (chunk 76): the gauge. Its two textures, its 575 vertex slots (positions, UVs, colours) and the
  strip lists of its 13 submeshes are redrawn: a black badge with the bar's bright rim, a recessed 210-degree
  channel, a white fill with a steel tail, a white slider thumb, the MAX window outlined in the bar's red, a flat
  perspective field, a black MPH tab and a bold italic MAX with a red underline.
- ``windmeter`` (chunk 77): the wind arrow, recoloured white and greys.
- The wind speed digits: a digits-only FONT drawn from the 2026 bar's traced numerals, appended to gamedata.iff as
  its last chunk (6,688 bytes, through a streamed pack-0 rebuild), and the kick HUD init's font3 lookup re-pointed
  at it (a 4-byte push operand at 0xBABED; the FONT takes a name the executable already carries).

Neither code nor curves change: the meter value, its timing, sweep, the MAX window (v >= 0.98), the MAX clip, the
wind read-out and the aim stay the retail game's. The bones, the aux_14 animation bindings and curves,
the materials (names, order, flags, tints), the texture descriptors and every vertex slot's submesh stay retail;
each submesh's new strip list stays inside its retail command area. The band's U at every path point is the
retail fill scroll at the moment the marker passes it, so the fill front sits under the marker at every value.

Each scene is compiled at build time from the copy's own retail span (checked against its SHA-256 pin, decoded,
redrawn from the shipped PNGs and geometry, refit into its retail stored span with the 32-byte wrapper and scratch
word byte-identical), checked against its applied pin and read back; the FONT is compiled from shipped data only. ``revert_image`` restores
the retail spans exactly from a retail source (the repository holds only their SHA-256 pins). The art and the
geometry come from ``reports/b76_km/author_kick_meter.py``. Composes with the sprite scorebug (which accepts these
three spans at their retail or applied pins) and with the ESPN presentation marks. EXPERIMENTAL and UNWITNESSED.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any

OWNER = "nfl2k5_kick_meter_2026"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_KEY = "kick_meter_2026"
BUILD_CAPTION = "Kick meter (2026 ESPN style)"
HELP_TEXT = (
    "Redraws the kick meter in the look of the 2026 ESPN score bar: a black badge with the bar's bright rim, a white "
    "power fill in a recessed channel with a slider thumb, the MAX window outlined in red, a clean field and wind "
    "arrow for the wind read-out, a black MPH tab with the wind speed in the bar's numerals and a bold MAX. The aim "
    "arrow on the field turns white. Only the look changes: the meter's timing, sweep, MAX window and wind are the "
    "game's own. The three scenes are rebuilt inside their retail space; the numerals add a 6.7 KB font. Works with "
    "the sprite scorebug and the ESPN presentation marks. Off in every preset; needs a disc image. Appearance in "
    "game is unwitnessed."
)
ROOT = Path(__file__).resolve().parents[2]
ART_DIR = ROOT / "data" / "nfl2k5_kick_meter_2026"
PINS_PATH = ROOT / "data" / "nfl2k5_kick_meter_2026_pins.json"
PINS_SCHEMA = "nfl2k5_kick_meter_2026_pins/v1"
GEOMETRY_SCHEMA = "nfl2k5_kick_meter_2026_geometry/v1"
ART_FILES = ("arrow32.png", "digits.png", "geometry.json", "meter128.png", "meter64.png")
OUTER_INDEX, OUTER_NAME_ID = 346, 0x00B6926C      # gamedata.iff
RESOURCES = (("KickArrow", 75), ("KickMeter", 76), ("windmeter", 77))   # (scene, chunk) in write order

# KickMeter decoded layout (retail; every offset is checked through the retail decoded SHA-256 pin first).
METER_SYSTEM = 18560                                # system bytes; the video buffer (two P8 textures) follows
METER_VERTICES = 575
METER_POSITIONS, METER_ATTRIBUTES = 0x2060, 0x2DE0  # NORMSHORT3 stride 6; D3DCOLOR, NORMSHORT2, SHORT1 stride 10
# submesh: (command area, retail capacity in words, first vertex, vertex count, bone selector)
METER_SUBMESHES = {
    "a_meter": (5952, 65, 0, 80, 0), "b_ball": (6212, 8, 80, 4, 3), "c_frame": (6244, 108, 84, 104, 0),
    "d_middle": (6676, 62, 188, 69, 0), "e_nowind": (6924, 26, 257, 28, 0), "f_frame1": (7028, 89, 285, 100, 0),
    "g_frame2": (7384, 82, 385, 74, 0), "h_wind": (7712, 8, 459, 4, 0), "i_lambert5": (7744, 35, 463, 22, 9),
    "j_max1": (7884, 40, 485, 41, 6), "k_max1": (8044, 8, 526, 4, 6), "l_max": (8076, 41, 530, 41, 6),
    "m_max": (8240, 8, 571, 4, 6),
}
# (PNG, width, height, pixel offset, palette offset) inside the video buffer
METER_TEXTURES = (("meter64.png", 64, 64, 0, 4096), ("meter128.png", 128, 128, 5120, 21504))
ARROW_SYSTEM, ARROW_TEXTURE = 8448, ("arrow32.png", 32, 32, 0, 1024)
WIND_ATTRIBUTES, WIND_VERTICES = 0xAA0, 45
# The byte ranges each compiled resource may change (decoded offsets, end exclusive); everything else stays retail.
CHANGED = {
    "KickArrow": ((ARROW_SYSTEM, ARROW_SYSTEM + 2048),),
    "KickMeter": ((METER_POSITIONS, METER_POSITIONS + 6 * METER_VERTICES),
                  (METER_ATTRIBUTES, METER_ATTRIBUTES + 10 * METER_VERTICES),
                  (5952, 8240 + 4 * 8), (METER_SYSTEM, METER_SYSTEM + 22528)),
    "windmeter": ((WIND_ATTRIBUTES, WIND_ATTRIBUTES + 10 * WIND_VERTICES),),
}
BEGIN_END, STRIP, ELEMENT16 = 0x000417FC, 6, 0x40001800

# The wind digits (b76 km, part 2): a digits-only FONT drawn from the 2026 bar's traced numerals, appended to
# gamedata.iff as its last chunk, and the kick HUD init's font3 lookup re-pointed at it. The FONT reuses a name
# the executable already carries (the UTF-16 "windmeter" at 0xE67E48, otherwise a SCNE name), so the only XBE
# change is the push operand at 0xBABED; lookups are typed, so the windmeter scene still resolves.
FONT_NAME = "windmeter"
FONT_NAME_VA, FONT3_NAME_VA = 0x00E67E48, 0x00E67E94
FONT_PUSH_VA = 0x000BABEC                            # push imm32 in FUN_000ba940, then mov edx,'FONT'; call 0x449E0
FONT_PUSH_RETAIL = bytes.fromhex("68947ee600ba464f4e5433c9e8e39df8ff")
FONT_PUSH_APPLIED = bytes.fromhex("68487ee600ba464f4e5433c9e8e39df8ff")
FONT_MIN, FONT_MAX = 0x2D, 0x39                      # '-' '.' '/' and the ten digits: all "%d" can print
FONT_ATLAS = (64, 64)
FONT_FORMAT = 0x06610B29                             # P8, one level, 2^6 x 2^6 (font3 is 0x07810B29, 256 x 128)
FONT_PALETTE = b"".join(bytes((255, 255, 255, 17 * i)) for i in range(16))   # BGRA: white, alpha 0x00..0xFF


class KickMeterError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise KickMeterError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tools():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))


def _outer_image():
    _tools()
    import nfl2k5_playbook_position_recode as recode  # noqa: E402
    return recode.OuterImage


def art_pins() -> dict[str, str]:
    return {name: sha((ART_DIR / name).read_bytes()) for name in ART_FILES if (ART_DIR / name).is_file()}


# --- pins ---------------------------------------------------------------------------------------------

_PINS: dict | None = None


def _check_pins(document: dict) -> dict:
    require(document.get("schema") == PINS_SCHEMA, "unsupported kick meter pins schema")
    outer = document.get("outer") or {}
    require(outer.get("index") == OUTER_INDEX and outer.get("name_id") == OUTER_NAME_ID and type(outer.get("size")) is int,
            "the pins must name gamedata.iff (outer 346)")
    rows = document.get("resources") or []
    require([(r.get("scene"), r.get("chunk_index")) for r in rows] == list(RESOURCES),
            "the pins must name KickArrow, KickMeter and windmeter in chunk order")
    hexed = lambda v: isinstance(v, str) and len(v) == 64 and set(v) <= set("0123456789abcdef")  # noqa: E731
    for row in rows:
        require(all(type(row.get(key)) is int and row[key] > 0 for key in ("chunk_offset", "span_size", "decoded_size")),
                f"{row.get('scene')}: pin geometry is incomplete")
        require(row["chunk_offset"] + row["span_size"] <= outer["size"], f"{row['scene']}: pin escapes the outer")
        require(all(hexed(row.get(key)) for key in ("retail_sha256", "applied_sha256", "retail_decoded_sha256",
                                                     "applied_decoded_sha256"))
                and row["retail_sha256"] != row["applied_sha256"], f"{row['scene']}: span pins are incomplete")
    spans = sorted((r["chunk_offset"], r["chunk_offset"] + r["span_size"]) for r in rows)
    require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "pinned kick meter spans overlap")
    font = document.get("font") or {}
    require(font.get("name") == FONT_NAME and type(font.get("chunk_size")) is int and font["chunk_size"] % 16 == 0
            and hexed(font.get("chunk_sha256")), "the pins must name the wind digits FONT chunk")
    return document


def _pins() -> dict:
    """The shipped pins, cross-checked against the shipped art and geometry."""

    global _PINS
    if _PINS is None:
        require(PINS_PATH.is_file(), "kick meter pins are missing from this build")
        document = _check_pins(json.loads(PINS_PATH.read_text(encoding="utf-8")))
        require(document.get("art") == art_pins(), "the shipped kick meter art differs from the pinned art")
        _PINS = document
    return _PINS


def available() -> bool:
    try:
        _pins()
        geometry()
    except (OSError, ValueError):
        return False
    return True


def geometry() -> dict:
    """The shipped geometry, checked against the retail submesh layout."""

    document = json.loads((ART_DIR / "geometry.json").read_text(encoding="utf-8"))
    require(document.get("schema") == GEOMETRY_SCHEMA, "unsupported kick meter geometry schema")
    meter = document["kick_meter"]
    vertices, strips = meter["vertices"], meter["strips"]
    require(len(vertices) == METER_VERTICES and all(len(v) == 7 for v in vertices), "the geometry must fill 575 vertex slots")
    require(all(all(type(x) is int for x in v) and all(-32768 <= x <= 32767 for x in v[:5]) and 0 <= v[5] <= 0xFFFFFFFF
                for v in vertices), "vertex lanes out of range")
    require(sorted(strips) == sorted(METER_SUBMESHES), "the geometry must give a strip for each of the 13 submeshes")
    for name, (_at, capacity, first, count, selector) in METER_SUBMESHES.items():
        ind = strips[name]
        require(len(ind) >= 3 and len(ind) % 2 == 0, f"{name}: strip needs an even count of at least 4")
        require(all(first <= i < first + count for i in ind), f"{name}: strip leaves its retail vertex slots")
        require(3 + len(ind) // 2 + 2 <= capacity, f"{name}: strip exceeds the retail command area")
        require(all(vertices[i][6] == selector for i in range(first, first + count)), f"{name}: bone selector changed")
    shades = document["windmeter"]["shades"]
    require(all(isinstance(k, str) and isinstance(v, str) for k, v in shades.items()) and len(shades) == 4,
            "the wind arrow needs its four shade pairs")
    return document


# --- compile ------------------------------------------------------------------------------------------

def _decode(span: bytes):
    _tools()
    import nfl_txtr as txtr
    chunk = txtr.parse_chunks(span, allow_trailing=True)[0]
    require(chunk.kind == "SCNE" and chunk.compression_magic == txtr.COMPRESSED_SENTINEL, "not a compressed SCNE span")
    decoded, _info = txtr.decode_chunk(span, chunk)
    return chunk, decoded


def _p8(png: str, width: int, height: int) -> tuple[bytes, bytes]:
    """Swizzled 8-bit indices and the 1,024-byte palette for one shipped PNG (the retail quantiser)."""

    _tools()
    import nfl_tset_png_import as palettes
    import nfl_txtr as txtr
    try:
        w, h, rgba = palettes.decode_rgba_png((ART_DIR / png).read_bytes(), (width, height))
    except ValueError as exc:
        raise KickMeterError(f"{png}: {exc}") from exc
    palette, indices, _q = palettes.quantize_levels([palettes.MipLevel(0, w, h, rgba)], 256)
    return txtr.swizzle_2d(indices[0], w, h, 1), palettes.palette_bytes(palette)


def _commands(indices: list[int], capacity: int) -> bytes:
    words = ([BEGIN_END, STRIP, ELEMENT16 | ((len(indices) // 2) << 18)]
             + [indices[i] | indices[i + 1] << 16 for i in range(0, len(indices), 2)] + [BEGIN_END, 0])
    require(len(words) <= capacity, "strip exceeds its command area")
    return struct.pack(f"<{capacity}I", *(words + [0] * (capacity - len(words))))


def compile_kick_meter(decoded: bytes) -> bytes:
    document = geometry()
    buf = bytearray(decoded)
    require(len(buf) == METER_SYSTEM + 22528, "KickMeter allocation changed")
    for k, (qx, qy, qz, qu, qv, argb, selector) in enumerate(document["kick_meter"]["vertices"]):
        struct.pack_into("<3h", buf, METER_POSITIONS + 6 * k, qx, qy, qz)
        struct.pack_into("<I2hh", buf, METER_ATTRIBUTES + 10 * k, argb, qu, qv, selector)
    for name, (at, capacity, *_rest) in METER_SUBMESHES.items():
        buf[at:at + 4 * capacity] = _commands(document["kick_meter"]["strips"][name], capacity)
    for png, width, height, pixels, palette in METER_TEXTURES:
        indices, table = _p8(png, width, height)
        buf[METER_SYSTEM + pixels:METER_SYSTEM + pixels + len(indices)] = indices
        buf[METER_SYSTEM + palette:METER_SYSTEM + palette + 1024] = table
    return bytes(buf)


def compile_windmeter(decoded: bytes) -> bytes:
    shades = {int(k, 16): int(v, 16) for k, v in geometry()["windmeter"]["shades"].items()}
    buf = bytearray(decoded)
    require(len(buf) == 3840, "windmeter allocation changed")
    for k in range(WIND_VERTICES):
        at = WIND_ATTRIBUTES + 10 * k
        colour = struct.unpack_from("<I", buf, at)[0]
        if colour in shades:
            struct.pack_into("<I", buf, at, shades[colour])
    return bytes(buf)


def compile_kick_arrow(decoded: bytes) -> bytes:
    png, width, height, pixels, palette = ARROW_TEXTURE
    buf = bytearray(decoded)
    require(len(buf) == ARROW_SYSTEM + 2048, "KickArrow allocation changed")
    indices, table = _p8(png, width, height)
    buf[ARROW_SYSTEM + pixels:ARROW_SYSTEM + pixels + len(indices)] = indices
    buf[ARROW_SYSTEM + palette:ARROW_SYSTEM + palette + 1024] = table
    return bytes(buf)


COMPILERS = {"KickArrow": compile_kick_arrow, "KickMeter": compile_kick_meter, "windmeter": compile_windmeter}


def changed_outside(scene: str, before: bytes, after: bytes) -> list[int]:
    """Decoded offsets that differ outside the ranges this option may change (must be empty)."""

    allowed = CHANGED[scene]
    return [i for i in range(len(before)) if before[i] != after[i] and not any(a <= i < b for a, b in allowed)]


def compile_span(span: bytes, row: dict) -> tuple[bytes, dict[str, Any]]:
    """The 2026 replacement for one retail span (complete resource; wrapper and scratch word kept)."""

    _tools()
    import nfl_vc_lz_fill as fill
    require(sha(span) == row["retail_sha256"], f"{row['scene']}: the span is not the pinned retail resource")
    chunk, decoded = _decode(span)
    require(sha(decoded) == row["retail_decoded_sha256"], f"{row['scene']}: the decoded scene is not retail")
    after = COMPILERS[row["scene"]](decoded)
    require(not changed_outside(row["scene"], decoded, after), f"{row['scene']}: a change escaped its allowed ranges")
    try:
        rebuilt, info = fill.rebuild_fixed_span_filled(span, after, encoder="auto")
    except ValueError as exc:
        raise KickMeterError(f"{row['scene']}: {exc}") from exc
    _chunk, back = _decode(rebuilt)
    require(back == after and len(rebuilt) == len(span) and rebuilt[:32] == span[:32],
            f"{row['scene']}: the fixed-span round trip failed")
    return rebuilt, dict(decoded_sha256=sha(after), compressed_bytes=info.compressed_bytes, filled_bytes=info.filled_bytes,
                         padding_bytes=info.padding_bytes, stored_size=info.stored_size, scratch_bytes=info.scratch_bytes,
                         exact_minimum_scratch=info.exact_minimum_scratch, wrapper_identical=info.wrapper_identical)


# --- the wind digits FONT ---------------------------------------------------------------------------------

def _digits_atlas() -> bytes:
    """The shipped 64x64 digits atlas as 8-bit palette indices 0..15 (alpha / 17), row major."""
    _tools()
    import nfl_tset_png_import as palettes
    try:
        w, h, rgba = palettes.decode_rgba_png((ART_DIR / "digits.png").read_bytes(), FONT_ATLAS)
    except ValueError as exc:
        raise KickMeterError(f"digits.png: {exc}") from exc
    alpha = rgba[3::4]
    require(all(a % 17 == 0 for a in alpha), "digits.png must carry the sixteen FONT alpha levels")
    return bytes(a // 17 for a in alpha)


def compile_digits_font() -> bytes:
    """The complete FONT chunk (32-byte raw wrapper + system + video) for the wind digits.

    The layout is the retail FONT contract (``tools/nfl_main_menu_font.parse_font``): the UTF-16 name at +0x20, the
    object at the next 16-byte boundary (bounds, one range, space and line advance, font3's vertical metrics and a
    P8 texture header), the range record, thirteen 96-byte glyph records ('-' to '9'; '.' and '/' are empty), then
    the swizzled 64x64 atlas and the 16-entry white alpha palette in a 1,024-byte palette area. Deterministic:
    shipped data only, no retail bytes."""
    _tools()
    import nfl_txtr as txtr
    metrics = geometry()["digits"]
    require(tuple(metrics["atlas"]) == FONT_ATLAS, "the digits atlas size changed")
    body = bytearray(0x20)
    body[0x0C:0x10] = b"FONT"
    name = (FONT_NAME + "\0").encode("utf-16le")
    body += name
    obj = (len(body) + 15) & ~15
    body += b"\xff" * (obj - len(body))
    ranges = obj + 0xC0
    glyphs = ranges + 0x10
    struct.pack_into("<I", body, 0x10, 0x20 - 0x10 + 1)
    struct.pack_into("<I", body, 0x14, obj - 0x14 + 1)
    width, height = FONT_ATLAS
    body += struct.pack("<HHIIIIIiI", FONT_MIN, FONT_MAX, 1, ranges - (obj + 8) + 1, metrics["space_advance"],
                        metrics["line_advance"], 18, -6, 22)
    body += struct.pack("<8I", 0, 0, width * height, FONT_FORMAT, 0, 0x80000000, 0x0001FFFF, 0)
    body += bytes(0x80)
    require(len(body) == ranges, "FONT object size changed")
    body += struct.pack("<HHI", FONT_MIN, FONT_MAX, glyphs - (ranges + 4) + 1) + b"\xff" * 8
    for code in range(FONT_MIN, FONT_MAX + 1):
        glyph = metrics["glyphs"].get(chr(code))
        if glyph is None:                                    # '.' and '/': never printed by "%d"
            body += struct.pack("<I", 5) + b"\xff" * 12 + bytes(64) + bytes(16)
            continue
        x0, y0, x1, y1 = glyph["quad"]
        u0, v0, u1, v1 = glyph["atlas"]
        require((x1 - x0, y1 - y0) == (u1 - u0, v1 - v0), f"glyph {chr(code)!r} is not one texel per pixel")
        body += struct.pack("<I", glyph["advance"]) + b"\xff" * 12
        body += struct.pack("<16f", x0, y0, 0, 0, x1, y0, 0, 0, x0, y1, 0, 0, x1, y1, 0, 0)
        body += struct.pack("<4f", u0 / width, v0 / height, u1 / width, v1 / height)
    body += b"\xff" * (-len(body) % 128)
    system = len(body)
    video = txtr.swizzle_2d(_digits_atlas(), width, height, 1) + FONT_PALETTE + bytes(1024 - len(FONT_PALETTE))
    decoded = bytes(body) + video
    return struct.pack("<4s7I", b"FONT", len(decoded), system, len(video), 0, 0, 0, 0) + decoded


def font_state(outer_read, outer_size: int, pins: dict) -> str:
    """'present' when the wind digits FONT is gamedata.iff's last chunk (its exact pinned bytes), else 'absent'."""
    size, digest = pins["font"]["chunk_size"], pins["font"]["chunk_sha256"]
    if outer_size < size:
        return "absent"
    return "present" if sha(bytes(outer_read(size, outer_size - size))) == digest else "absent"


# --- the executable: the font3 lookup re-pointed at the wind digits --------------------------------------

def _xbe_image(payload: bytes):
    from .nfl2k5_bump_strength import _sections
    sections = _sections(payload)

    def offset(va: int, size: int) -> int:
        for section in sections:
            if section.virtual_address <= va and va + size <= section.virtual_address + section.raw_size:
                return section.raw_offset + va - section.virtual_address
        raise KickMeterError(f"0x{va:x} is outside the executable's sections")
    return offset


def xbe_status(payload: bytes) -> str:
    """retail / applied / foreign for the push at 0xBABEC (and the two UTF-16 names it can point at)."""
    try:
        offset = _xbe_image(payload)
        names = (payload[offset(FONT_NAME_VA, 20):offset(FONT_NAME_VA, 20) + 20],
                 payload[offset(FONT3_NAME_VA, 12):offset(FONT3_NAME_VA, 12) + 12])
        if names != ((FONT_NAME + "\0").encode("utf-16le"), "font3\0".encode("utf-16le")):
            return "foreign"
        at = offset(FONT_PUSH_VA, len(FONT_PUSH_RETAIL))
        site = payload[at:at + len(FONT_PUSH_RETAIL)]
    except (KickMeterError, ValueError, struct.error):
        return "foreign"
    return "retail" if site == FONT_PUSH_RETAIL else "applied" if site == FONT_PUSH_APPLIED else "foreign"


def apply_xbe(payload: bytes) -> tuple[bytes, dict[str, Any]]:
    """The 4-byte push operand, guarded, with the section digests re-sealed."""
    from .nfl2k5_bump_strength import _sections, section_digest
    state = xbe_status(payload)
    require(state in ("retail", "applied"), "default.xbe's kick HUD font lookup is not the retail or 2026 bytes")
    edits = [dict(label="kick_meter_digits_font", va=hex(FONT_PUSH_VA + 1), size=4,
                  before=FONT_PUSH_RETAIL[1:5].hex(), after=FONT_PUSH_APPLIED[1:5].hex())]
    if state == "applied":
        return payload, dict(status="already_applied", changed_bytes=0, edits=edits)
    buffer = bytearray(payload)
    at = _xbe_image(payload)(FONT_PUSH_VA, len(FONT_PUSH_RETAIL))
    buffer[at:at + len(FONT_PUSH_APPLIED)] = FONT_PUSH_APPLIED
    for section in _sections(buffer):
        buffer[section.header_offset + 36:section.header_offset + 56] = section_digest(buffer, section)
    result = bytes(buffer)
    require(xbe_status(result) == "applied", "the kick HUD font lookup read-back failed")
    return result, dict(status="applied", changed_bytes=sum(a != b for a, b in zip(payload, result)), edits=edits,
                        before_sha256=sha(payload), after_sha256=sha(result))


def xbe_reservations(payload: bytes) -> list[dict[str, Any]]:
    """The cave manifest's ownership row: the four operand bytes this option writes in default.xbe."""
    require(xbe_status(payload) == "applied", "the kick HUD font lookup is not re-pointed")
    return [dict(owner=OWNER, start=hex(FONT_PUSH_VA + 1), end=hex(FONT_PUSH_VA + 5), size=4,
                 basis="in-place kick_meter_digits_font (no runtime space)")]


class XbePatch:
    """Adapter for the shared executable gates and the cave manifest's ownership recorder."""
    OWNER = OWNER
    REQUESTS = ()
    apply = staticmethod(apply_xbe)
    status = staticmethod(xbe_status)
    reservations = staticmethod(xbe_reservations)


# --- images -------------------------------------------------------------------------------------------

def _sprite():
    from . import nfl2k5_scorebug_sprite as sprite
    return sprite


def _entry(archive, pins: dict, *, sprite_folder=None, retail_size: bool = False):
    """gamedata.iff's outer entry, or None when it is not the pinned resource.

    The pinned outer at its retail size; or (unless ``retail_size``) that outer followed by the wind digits FONT as
    its last chunk; or grown by exactly the sprite scorebug's appended resources (with or without the FONT after
    them): the sprite checks the whole outer (its retail HUD with the ESPN presentation marks and these three spans
    at their retail or applied pins, and its own appendix for ``sprite_folder``) and sets the FONT aside itself."""

    outer = pins["outer"]
    if outer["index"] >= len(archive.entries):
        return None
    entry = archive.entries[outer["index"]]
    if entry.name_id != outer["name_id"]:
        return None
    if entry.size == outer["size"]:
        return entry
    if retail_size or entry.size < outer["size"]:
        return None
    read = lambda count, at: archive.read(entry.virtual_offset + at, count)  # noqa: E731
    if entry.size == outer["size"] + pins["font"]["chunk_size"] and font_state(read, entry.size, pins) == "present":
        return entry
    return entry if _sprite().gamedata_status(read, entry.size, sprite_folder) == "applied" else None


def _state(span: bytes, row: dict) -> str:
    have = sha(span)
    return "retail" if have == row["retail_sha256"] else "applied" if have == row["applied_sha256"] else "foreign"


def _xbe_of(source) -> bytes:
    """default.xbe from a disc image, or from a folder of extracted files (the folder or its parent)."""
    path = Path(source)
    if path.is_dir():
        for candidate in (path / "default.xbe", path.parent / "default.xbe"):
            if candidate.is_file():
                return candidate.read_bytes()
        raise KickMeterError("the source folder has no default.xbe")
    from . import nfl2k5_music_archive as archive
    with archive.Disc(path, descriptors=()) as disc:
        x = disc.entries["default.xbe"]
        require(x.size <= 16 * archive.BLOCK, "oversized XBE")
        return disc.read(x.size, x.byte_offset)


def resource_states(source, *, pins: dict | None = None, sprite_folder=None) -> dict[str, str] | None:
    """{scene: retail | applied | foreign} for the three spans, 'font': present | absent and 'xbe': retail | applied
    | foreign; None when gamedata.iff is foreign."""

    pins = _check_pins(pins) if pins is not None else _pins()
    with _outer_image()(source) as archive:
        entry = _entry(archive, pins, sprite_folder=sprite_folder)
        if entry is None:
            return None
        states = {row["scene"]: _state(archive.read(entry.virtual_offset + row["chunk_offset"], row["span_size"]), row)
                  for row in pins["resources"]}
        states["font"] = font_state(lambda count, at: archive.read(entry.virtual_offset + at, count), entry.size, pins)
    states["xbe"] = xbe_status(_xbe_of(source))
    return states


def image_status(source, *, pins: dict | None = None, sprite_folder=None) -> str:
    """retail / applied / mixed / foreign across the three kick HUD scenes, the wind digits FONT and the font lookup."""

    states = resource_states(source, pins=pins, sprite_folder=sprite_folder)
    if states is None or states["xbe"] == "foreign" or "foreign" in (states[scene] for scene, _chunk in RESOURCES):
        return "foreign"
    parts = {states[scene] for scene, _chunk in RESOURCES} | {states["xbe"],
                                                              "applied" if states["font"] == "present" else "retail"}
    return parts.pop() if len(parts) == 1 else "mixed"


status = image_status


def _write_all(archive, plan: list[tuple[int, bytes, bytes]]) -> None:
    written: list[tuple[int, bytes]] = []
    try:
        for at, before, after in plan:
            require(archive.read(at, len(before)) == before, "a kick meter span changed after preflight")
            require(archive.write(at, after) == len(after), "short kick meter write")
            written.append((at, before))
            require(archive.read(at, len(after)) == after, "kick meter read-back differs")
    except BaseException:
        for at, before in reversed(written):
            archive.write(at, before)
        raise


def _transaction(path, pins: dict, *, font: str, xbe: str) -> dict[str, Any]:
    """One paired write on the disposable copy: gamedata.iff gains ('add') or loses ('remove') the wind digits FONT
    as its last chunk through a streamed pack-0 rebuild (the Guardian overlay's transaction), and default.xbe's font
    lookup is re-pointed ('apply') or restored ('restore'). Rolled back on failure; 'keep' leaves either part."""

    import os
    from . import nfl2k5_depth_chart_storage as storage
    from . import nfl2k5_music_archive as archive  # noqa: I001
    from . import nfl2k5_resource_growth as growth
    from . import platform_compat as io
    chunk = compile_digits_font()
    require(len(chunk) == pins["font"]["chunk_size"] and sha(chunk) == pins["font"]["chunk_sha256"],
            "the wind digits FONT differs from its pin")
    path = Path(path).resolve()
    with archive.Disc(path, descriptors=()) as disc:
        identity = archive.identity(path)
        entry = disc.archive_entries[OUTER_INDEX]
        require(entry.name_id == OUTER_NAME_ID, "outer 346 is not gamedata.iff")
        x = disc.entries["default.xbe"]
        require(x.size <= 16 * archive.BLOCK, "oversized XBE")
        old_xbe = disc.read(x.size, x.byte_offset)
        new_xbe = old_xbe
        if xbe == "apply":
            new_xbe = apply_xbe(old_xbe)[0]
        elif xbe == "restore":
            new_xbe = restore_xbe(old_xbe)
        plan = None
        if font != "keep":
            outer = disc.read_entry_range(entry, 0, entry.size)
            present = font_state(lambda n, at: outer[at:at + n], len(outer), pins) == "present"
            if font == "add" and not present:
                after = outer + chunk
            elif font == "remove" and present:
                after = outer[:-len(chunk)]
            else:
                after = None
            if after is not None:
                p = disc.pack_extents["0"]
                read_pack = lambda n, at: disc.read(n, p.byte_offset + at)  # noqa: E731
                plan = growth.plan_pack0(read_pack, p.size, OUTER_INDEX, OUTER_NAME_ID, after, padding_bytes=(0, 0x9F))
                require(plan.start == entry.virtual_offset, "gamedata.iff is not contained in pack 0")
        if plan is None and new_xbe == old_xbe:
            return dict(pack_transport=None, xbe_transport=None, image_growth=0)
        old_size = disc.image_size
        nodes = []
        if plan is not None:
            nodes.append((disc.nodes["0"][0], struct.pack("<II", p.sector, p.size)))
        xnode = storage.image_file_node(disc.read, x.base_offset, old_size, x.path)
        require(xnode[1:] == (x.sector, x.size), "XBE node disagrees with its extent")
        nodes.append((xnode[0], struct.pack("<II", x.sector, x.size)))
        require(archive.identity(path) == identity, "image changed after the kick meter preflight")
        with path.open("r+b") as writer:
            fd = writer.fileno()

            def write(data, at):
                require(io.pwrite(fd, data, at) == len(data), "short kick meter transaction write")

            transport = xtransport = None
            attempted_xbe = False
            try:
                if plan is not None:
                    offset = archive.align_up(old_size)
                    if offset > old_size:
                        write(bytes(offset - old_size), old_size)
                    transport = growth.write_pack0(fd, read_pack, plan, offset)
                    write(struct.pack("<II", (offset - p.base_offset) // 2048, plan.size_after), nodes[0][0])
                if new_xbe != old_xbe:
                    # Same size, same place: only the push operand and the section digests differ.
                    require(len(new_xbe) == len(old_xbe), "the font lookup edit never changes the XBE size")
                    attempted_xbe = True
                    write(new_xbe, x.byte_offset)
                    require(io.pread(fd, len(new_xbe), x.byte_offset) == new_xbe, "kick meter XBE read-back differs")
                    xtransport = dict(offset=x.byte_offset, size=len(new_xbe), in_place=True)
                os.fsync(fd)
            except Exception as exc:
                try:
                    for node, data in reversed(nodes):
                        write(data, node)
                    if attempted_xbe:
                        write(old_xbe, x.byte_offset)
                    os.ftruncate(fd, old_size)
                    os.fsync(fd)
                    require(all(io.pread(fd, 8, node) == data for node, data in nodes), "kick meter rollback node mismatch")
                    require(io.pread(fd, x.size, x.byte_offset) == old_xbe, "kick meter rollback XBE mismatch")
                except Exception as rollback:
                    raise KickMeterError(f"{exc}; rollback failed: {rollback}; discard the output copy") from exc
                raise
            image_growth = os.fstat(fd).st_size - old_size
    return dict(pack_transport=transport, xbe_transport=xtransport, image_growth=image_growth)


def restore_xbe(payload: bytes) -> bytes:
    """The retail push operand back, guarded, with the section digests re-sealed."""
    from .nfl2k5_bump_strength import _sections, section_digest
    state = xbe_status(payload)
    require(state in ("retail", "applied"), "default.xbe's kick HUD font lookup is not the retail or 2026 bytes")
    if state == "retail":
        return payload
    buffer = bytearray(payload)
    at = _xbe_image(payload)(FONT_PUSH_VA, len(FONT_PUSH_APPLIED))
    buffer[at:at + len(FONT_PUSH_RETAIL)] = FONT_PUSH_RETAIL
    for section in _sections(buffer):
        buffer[section.header_offset + 36:section.header_offset + 56] = section_digest(buffer, section)
    result = bytes(buffer)
    require(xbe_status(result) == "retail", "the kick HUD font lookup restore read-back failed")
    return result


def apply_to_image(target, *, pins: dict | None = None, progress=None, sprite_folder=None) -> dict[str, Any]:
    """Build-only: ``target`` is the caller's disposable output image. Retail or applied parts only.

    First the three scenes in place (fixed spans), then one paired transaction: the wind digits FONT appended to
    gamedata.iff and the font lookup re-pointed at it."""

    pins = _check_pins(pins) if pins is not None else _pins()
    say = progress or (lambda message, done, total: None)
    rows: list[dict[str, Any]] = []
    plan: list[tuple[int, bytes, bytes]] = []
    states = resource_states(target, pins=pins, sprite_folder=sprite_folder)
    require(states is not None, "gamedata.iff is not the pinned USA resource (retail, or grown only by the sprite "
                                "scorebug and this option's wind digits); rebuild from a supported source")
    require(states["xbe"] != "foreign", "default.xbe's kick HUD font lookup is not the retail or 2026 bytes")
    with _outer_image()(target, writable=True) as archive:
        entry = _entry(archive, pins, sprite_folder=sprite_folder)
        require(entry is not None, "gamedata.iff changed after the kick meter preflight")
        appended = "sprite scorebug" if entry.size not in (pins["outer"]["size"],
                                                          pins["outer"]["size"] + pins["font"]["chunk_size"]) else "none"
        total = len(pins["resources"])
        for index, row in enumerate(pins["resources"]):
            at = entry.virtual_offset + row["chunk_offset"]
            before = archive.read(at, row["span_size"])
            state = _state(before, row)
            require(state != "foreign", f"{row['scene']}: the span is neither retail nor this option's 2026 kick meter; "
                                        "rebuild from a supported USA source")
            out = dict(scene=row["scene"], chunk_index=row["chunk_index"], chunk_offset=row["chunk_offset"],
                       span_size=row["span_size"], retail_sha256=row["retail_sha256"],
                       applied_sha256=row["applied_sha256"], state_before=state)
            if state == "retail":
                say(f"2026 kick meter: {row['scene']} ({index + 1} of {total})", index, total)
                after, detail = compile_span(before, row)
                require(sha(after) == row["applied_sha256"], f"{row['scene']}: the compiled scene differs from its applied pin")
                plan.append((at, before, after))
                out.update(written=True, changed_bytes=sum(a != b for a, b in zip(before, after)), **detail)
            else:
                out.update(written=False, changed_bytes=0)
            rows.append(out)
        _write_all(archive, plan)
    say("2026 kick meter: the wind digits", total, total)
    transaction = _transaction(target, pins, font="add", xbe="apply")
    say("2026 kick meter: done", total, total)
    state = image_status(target, pins=pins, sprite_folder=sprite_folder)
    require(state == "applied", "the 2026 kick meter failed its read-back on the copy")
    return dict(label=LABEL, option=BUILD_KEY, state=state, runtime_witnessed=False, outer=dict(pins["outer"]),
                resources=rows, written=len(plan), already_applied=len(rows) - len(plan),
                changed_bytes=sum(row["changed_bytes"] for row in rows), gamedata_appended=appended,
                font=dict(name=FONT_NAME, chunk_size=pins["font"]["chunk_size"], chunk_sha256=pins["font"]["chunk_sha256"],
                          state_before=states["font"]),
                xbe=dict(site=hex(FONT_PUSH_VA + 1), state_before=states["xbe"], bytes=4),
                gamedata_growth=pins["font"]["chunk_size"] if states["font"] == "absent" else 0,
                image_growth=transaction["image_growth"], pack_transport=transaction["pack_transport"])


def verify(source, *, enabled: bool = True, pins: dict | None = None, sprite_folder=None) -> dict[str, Any]:
    state = image_status(source, pins=pins, sprite_folder=sprite_folder)
    require(state == ("applied" if enabled else "retail"), "the 2026 kick meter does not match the request")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False)


def revert_image(target, retail_source, *, pins: dict | None = None, progress=None, sprite_folder=None) -> dict[str, Any]:
    """Exact revert: the three retail spans (read from a retail source and checked against their pins), the wind
    digits FONT removed from gamedata.iff and the retail font lookup."""

    pins = _check_pins(pins) if pins is not None else _pins()
    say = progress or (lambda message, done, total: None)
    retail: dict[str, bytes] = {}
    with _outer_image()(retail_source) as source:
        entry = _entry(source, pins, retail_size=True)
        require(entry is not None, "the retail source's gamedata.iff is not the pinned USA resource")
        for row in pins["resources"]:
            span = source.read(entry.virtual_offset + row["chunk_offset"], row["span_size"])
            require(sha(span) == row["retail_sha256"], f"{row['scene']}: the retail source is not retail")
            retail[row["scene"]] = span
    plan: list[tuple[int, bytes, bytes]] = []
    rows = []
    with _outer_image()(target, writable=True) as archive:
        entry = _entry(archive, pins, sprite_folder=sprite_folder)
        require(entry is not None, "gamedata.iff is not the pinned USA resource")
        for index, row in enumerate(pins["resources"]):
            at = entry.virtual_offset + row["chunk_offset"]
            before = archive.read(at, row["span_size"])
            state = _state(before, row)
            require(state != "foreign", f"{row['scene']}: the span is neither retail nor this option's kick meter")
            if state == "applied":
                say(f"Restoring {row['scene']}", index, len(pins["resources"]))
                plan.append((at, before, retail[row["scene"]]))
            rows.append(dict(scene=row["scene"], state_before=state, restored=state == "applied"))
        _write_all(archive, plan)
    transaction = _transaction(target, pins, font="remove", xbe="restore")
    state = image_status(target, pins=pins, sprite_folder=sprite_folder)
    require(state == "retail", "the exact revert failed its read-back")
    return dict(label=LABEL, option=BUILD_KEY, state=state, resources=rows, restored=len(plan), runtime_witnessed=False,
                image_growth=transaction["image_growth"])


def _locate(archive, chunk_index: int) -> tuple[int, int]:
    """(chunk offset inside gamedata.iff, span size) of one chunk, from the outer's own chunk table."""

    _tools()
    import nfl_txtr as txtr
    entry = archive.entries[OUTER_INDEX]
    outer = archive.read(entry.virtual_offset, entry.size)
    chunks = txtr.parse_chunks(outer, allow_trailing=True)
    require(chunk_index < len(chunks), "gamedata.iff has fewer chunks than pinned")
    chunk = chunks[chunk_index]
    return chunk.offset, 32 + chunk.stored_size


def record_pins(source, out_path: Path | str | None = PINS_PATH) -> dict:
    """Author-time: retail and applied pins for the three scenes from a retail source (image or loose packs)."""

    resources = []
    with _outer_image()(source) as archive:
        entry = archive.entries[OUTER_INDEX]
        require(entry.name_id == OUTER_NAME_ID, "the source's outer 346 is not gamedata.iff")
        outer = dict(index=OUTER_INDEX, name_id=OUTER_NAME_ID, size=entry.size)
        for scene, chunk_index in RESOURCES:
            offset, size = _locate(archive, chunk_index)
            span = archive.read(entry.virtual_offset + offset, size)
            _chunk, decoded = _decode(span)
            require(decoded[0x20:0x20 + 2 * len(scene)].decode("utf-16le") == scene, f"chunk {chunk_index} is not {scene}")
            row = dict(scene=scene, chunk_index=chunk_index, chunk_offset=offset, span_size=size, decoded_size=len(decoded),
                       retail_sha256=sha(span), retail_decoded_sha256=sha(decoded))
            after, detail = compile_span(span, dict(row, applied_sha256="0" * 64, applied_decoded_sha256="0" * 64))
            row.update(applied_sha256=sha(after), applied_decoded_sha256=detail["decoded_sha256"],
                       fill={k: v for k, v in detail.items() if k != "decoded_sha256"})
            resources.append(row)
    chunk = compile_digits_font()
    font = dict(name=FONT_NAME, chunk_size=len(chunk), chunk_sha256=sha(chunk), name_va=hex(FONT_NAME_VA),
                push_va=hex(FONT_PUSH_VA))
    document = dict(schema=PINS_SCHEMA, outer=outer, art=art_pins(), resources=resources, font=font,
                    runtime_witnessed=False)
    _check_pins(document)
    if out_path is not None:
        Path(out_path).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return document


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_kick_meter_2026", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status").add_argument("source")
    pins = sub.add_parser("record-pins")
    pins.add_argument("source")
    pins.add_argument("--out", default=str(PINS_PATH))
    revert = sub.add_parser("revert")
    revert.add_argument("target")
    revert.add_argument("retail_source")
    args = parser.parse_args(argv)
    if args.command == "status":
        print(image_status(args.source))
    elif args.command == "record-pins":
        document = record_pins(args.source, args.out)
        print(json.dumps({r["scene"]: r["applied_sha256"] for r in document["resources"]}, indent=2))
    else:
        print(json.dumps(revert_image(args.target, args.retail_source), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
