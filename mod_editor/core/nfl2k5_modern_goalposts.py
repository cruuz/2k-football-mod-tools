"""Modern goalposts: the uprights 35 ft above the crossbar (the NFL rule since 2014) in every venue.

Every venue draws ONE shared goalpost: the ``goalpost`` scene of ``gamedata.iff`` (outer 346, pack 0, chunk 88). The
goal setup ``0x98220`` finds each stadium scene's ``goalShape1`` / ``goalShape2`` markers (linked ``goal1_north`` /
``goal2_south``; every one of the 477 retail stadium scenes carries both, and the SoFi-derived venue builders keep the
retail markers), instantiates the scene three times per end (the normal copy, plus a pair with altered material
state, one of them alpha-blended, that the draw ``0x985B0`` uses instead when the camera is behind that goal within 20
yards of the middle) and binds the stadium's ``pad_north`` / ``pad_south`` art to its ``pad`` material. Its planar shadow is the ``goalpost_shadow`` scene (chunk 71,
node ``goal_shadow``, drawn by ``0x98720`` through the shadow projector ``0x1C3560``). Retail, from the decoded data:
the post 6 ft behind the end line with its 6 ft pad, the gooseneck, the crossbar's top at 10 ft (304.8 cm), the
uprights 18 ft 6 in apart inside (563.9 cm, 4 in thick) rising to 40 ft (1,219.2 cm): 30 ft above the crossbar, the
rule of the 2004 game. No wind ribbons are modelled (the pole has no other parts).

This option makes them modern, in place:

* ``goalpost``: the 56 upright-top vertices (both posts and their caps) go from 1,219.2 to 1,371.6 cm (45 ft, 35 ft
  above the crossbar); ``goalpost_shadow``: its 32 the same. Nothing else moves: the base, pad, gooseneck, crossbar,
  width, the vertex colours (baked lighting; this vertex format has no normals) and the UVs (the pole samples one
  constant texel patch and draws untextured in the pole's gold) are retail, as are the vertex count and the strips.
  The shapes' NORMSHORT3 position constant grows with the posts (scale ``+0x10`` and the y offset ``+0x24`` x 1.125,
  every vertex re-quantised; unmoved vertices stay within half a quantisation step, 0.011 cm) and the bounding
  sphere (``+0x00`` centre, ``+0x48`` radius) is recomputed to enclose the new tops: the frustum test ``0x215A0``
  culls the goal by it. Each scene is refit into its retail stored span with the 32-byte wrapper identical.
* ``default.xbe``, two in-place guarded edits (12 bytes) plus the ``.text`` digest:
  - the upright lines ``0x985B0`` draws over the posts (so a 4 in post never vanishes at a distance) end at the
    model's top: the two ``push 1219.2`` at ``0x986AA`` and ``0x986FB`` become ``push 1371.6``;
  - the ball/goalpost collision ``0x1C68C0`` tests each upright as a cylinder (``0x1C5DD0``) up to ``r + 1219.2``,
    the 1,219.2 read from ``0x50A510``, a constant shared with unrelated code (``0x19F0B5``, ``0x19F17E``,
    ``0x216450``) that stays untouched; the one ``fadd`` at ``0x1C6A2C`` is re-pointed at the read-only literal
    1,371.6 at ``0x4F689C`` (31 reads, no writes in the executable), so a kick that meets the new upper five feet of
    a post hits it instead of passing through it.

The scoring rule needs nothing: ``0x157C10`` interpolates the ball where it crosses the end-line plane (5,486.4 cm)
and calls the kick good inside the rectangle at ``0x510410``: x within the uprights' inside edges (+/- 281.94 cm) and
y from the crossbar (304.8) to 30,480 cm (1,000 ft), i.e. the uprights extended, with no tie to the posts' height.

EXPERIMENTAL and UNWITNESSED: proved offline (decoded geometry, byte receipts, renders from the data); the look in
the game and a ball meeting the new top of a post are for Noah's eyes.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any, Callable

OWNER = "nfl2k5_modern_goalposts"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_KEY = "modern_goalposts"
BUILD_CAPTION = "Modern goalposts (35 ft uprights)"
HELP_TEXT = (
    "Makes the goalposts in every stadium modern: the uprights rise 35 feet above the crossbar (45 feet above the "
    "field), as the NFL has required since 2014, instead of the 2004 game's 30 feet. The base, pad, gooseneck, "
    "crossbar, width and colours stay the game's own; the goalpost's shadow grows with it, the thin lines the game "
    "draws over distant posts reach the new tops and a kick that meets the new top of a post hits it. Scoring is "
    "unchanged: a kick is good between the uprights extended, as before. The two shared goalpost scenes are rebuilt "
    "inside their retail space and 12 bytes of the executable change. Off in every preset; needs a disc image. "
    "Appearance in game is unwitnessed."
)
ROOT = Path(__file__).resolve().parents[2]
PINS_PATH = ROOT / "data" / "nfl2k5_modern_goalposts_pins.json"
PINS_SCHEMA = "nfl2k5_modern_goalposts_pins/v1"
OUTER_INDEX, OUTER_NAME_ID = 346, 0x00B6926C        # gamedata.iff
PACK_HEADER = 0x0C + 36 * 4                          # the vc_53450030 index header, then 12-byte entries
ALIGNMENT = 0x800

CROSSBAR_TOP = 304.8          # cm: 10 ft
RETAIL_TOP = 1219.2           # cm: 40 ft, 30 ft above the crossbar (the rule the 2004 game follows)
MODERN_TOP = 1371.6           # cm: 45 ft, 35 ft above the crossbar (NFL Rule 1, since 2014)
GROWTH = MODERN_TOP / RETAIL_TOP   # 1.125: the y position constant grows with the posts
TOP_TOLERANCE = 0.05          # cm: the retail tops decode at 1,219.2074
POSITION_CONSTANT, SCALE_LANES, OFFSET_LANES = 0x10, 0x10, 0x20
SPHERE_CENTRE, SPHERE_RADIUS = 0x00, 0x48

# Decoded layouts of the two retail scenes (each offset is used only after the retail decoded SHA-256 pin matched):
# shape record, NORMSHORT3 position stream (stride 6), vertex count, upright-top vertices.
SCENES = {
    "goalpost_shadow": dict(chunk=71, record=576, positions=1696, vertices=174, tops=32, size=4864),
    "goalpost": dict(chunk=88, record=704, positions=2208, vertices=243, tops=56, size=6400),
}
RESOURCES = (("goalpost_shadow", 71), ("goalpost", 88))     # (scene, chunk) in chunk order

# default.xbe: (label, VA, retail bytes, modern bytes)
SHARED_TOP_VA = 0x0050A510        # 1219.2f: the collision's upright top, shared with 0x19F0B5 / 0x19F17E / 0x216450
MODERN_LITERAL_VA = 0x004F689C    # 1371.6f: a read-only literal (31 fcomp/fsub/fmul/fadd/fld reads, no writes)
PUSH_RETAIL = b"\x68" + struct.pack("<f", RETAIL_TOP)
PUSH_MODERN = b"\x68" + struct.pack("<f", MODERN_TOP)
FADD_RETAIL = b"\xd8\x05" + struct.pack("<I", SHARED_TOP_VA)
FADD_MODERN = b"\xd8\x05" + struct.pack("<I", MODERN_LITERAL_VA)
XBE_SITES = (
    ("upright_line_left_top", 0x000986AA, PUSH_RETAIL, PUSH_MODERN),
    ("upright_line_right_top", 0x000986FB, PUSH_RETAIL, PUSH_MODERN),
    ("upright_collision_top", 0x001C6A2C, FADD_RETAIL, FADD_MODERN),
)
XBE_GUARDS = ((MODERN_LITERAL_VA, struct.pack("<f", MODERN_TOP)),)   # the literal the collision now reads


class ModernGoalpostsError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ModernGoalpostsError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _tools():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))


# --- the scenes ------------------------------------------------------------------------------------------------

def _normshort(value: int) -> float:
    return value / 32767.0 if value >= 0 else value / 32768.0


def _encode_normshort(value: float) -> int:
    scaled = value * 32767.0 if value >= 0 else value * 32768.0
    return max(-32768, min(32767, int(round(scaled))))


def positions(decoded: bytes, scene: str) -> list[tuple[float, float, float]]:
    """The decoded positions (cm, the game's model space: y up, z toward the field) of one goalpost scene."""

    spec = SCENES[scene]
    rec = spec["record"]
    scale = struct.unpack_from("<f", decoded, rec + SCALE_LANES)[0]
    offset = struct.unpack_from("<3f", decoded, rec + OFFSET_LANES)
    out = []
    for k in range(spec["vertices"]):
        q = struct.unpack_from("<3h", decoded, spec["positions"] + 6 * k)
        out.append(tuple(_normshort(q[a]) * scale + offset[a] for a in range(3)))
    return out


def bounding_sphere(points) -> tuple[tuple[float, float, float], float]:
    """(centre, radius) enclosing every point as stored (binary32): the bounding-box centre and the largest distance,
    widened by four binary32 steps (the venue builders' rule, nfl2k5_scne_builder.bounding_sphere)."""

    from .nfl2k5_scne_builder import bounding_sphere as sphere
    centre, radius = sphere(points)
    return tuple(float(c) for c in centre), float(radius)


def compile_scene(scene: str, decoded: bytes) -> bytes:
    """The modern goalpost scene from its retail decoded bytes (same size; only the position stream, the position
    constant and the bounding sphere change)."""

    spec = SCENES[scene]
    require(len(decoded) == spec["size"], f"{scene}: allocation changed")
    buf = bytearray(decoded)
    rec = spec["record"]
    scale = struct.unpack_from("<4f", buf, rec + SCALE_LANES)
    offset = struct.unpack_from("<4f", buf, rec + OFFSET_LANES)
    require(scale[0] == scale[1] == scale[2] > 0 and scale[3] == 0 and offset[3] == 1.0,
            f"{scene}: the position constant is not the retail uniform form")
    require(struct.unpack_from("<H", buf, rec + 0x4C)[0] == spec["vertices"], f"{scene}: vertex count changed")
    old = positions(bytes(buf), scene)
    tops = {k for k, p in enumerate(old) if abs(p[1] - RETAIL_TOP) <= TOP_TOLERANCE}
    require(len(tops) == spec["tops"], f"{scene}: {len(tops)} upright-top vertices, expected {spec['tops']}")
    others = [p for k, p in enumerate(old) if k not in tops]
    require(max(p[1] for p in others) <= CROSSBAR_TOP + 0.5, f"{scene}: geometry between the crossbar and the tops")
    new = [(p[0], MODERN_TOP, p[2]) if k in tops else p for k, p in enumerate(old)]
    new_scale = _f32(scale[0] * GROWTH)
    new_offset = (offset[0], _f32(offset[1] * GROWTH), offset[2])
    for p in new:
        require(all(abs(p[a] - new_offset[a]) <= new_scale for a in range(3)), f"{scene}: a vertex leaves the range")
    struct.pack_into("<4f", buf, rec + SCALE_LANES, new_scale, new_scale, new_scale, 0.0)
    struct.pack_into("<4f", buf, rec + OFFSET_LANES, new_offset[0], new_offset[1], new_offset[2], 1.0)
    for k, p in enumerate(new):
        q = tuple(_encode_normshort((p[a] - new_offset[a]) / new_scale) for a in range(3))
        struct.pack_into("<3h", buf, spec["positions"] + 6 * k, *q)
    stored = positions(bytes(buf), scene)
    centre, radius = bounding_sphere(stored)
    struct.pack_into("<4f", buf, rec + SPHERE_CENTRE, centre[0], centre[1], centre[2], 1.0)
    struct.pack_into("<f", buf, rec + SPHERE_RADIUS, radius)
    step = new_scale / 32767.0
    require(all(math.dist(a, b) <= step for a, b in zip(stored, new)), f"{scene}: re-quantisation drifted")
    require(all(abs(stored[k][1] - MODERN_TOP) <= step for k in tops), f"{scene}: the new tops missed 45 ft")
    return bytes(buf)


def changed_ranges(scene: str) -> tuple[tuple[int, int], ...]:
    """Decoded byte ranges this option may change in a scene (end exclusive)."""

    spec = SCENES[scene]
    rec = spec["record"]
    return ((rec + SPHERE_CENTRE, rec + 0x10), (rec + SCALE_LANES, rec + 0x30), (rec + SPHERE_RADIUS, rec + 0x4C),
            (spec["positions"], spec["positions"] + 6 * spec["vertices"]))


def changed_outside(scene: str, before: bytes, after: bytes) -> list[int]:
    allowed = changed_ranges(scene)
    return [i for i in range(len(before)) if before[i] != after[i] and not any(a <= i < b for a, b in allowed)]


def _decode(span: bytes):
    _tools()
    import nfl_txtr as txtr
    chunk = txtr.parse_chunks(bytes(span), allow_trailing=True)[0]
    require(chunk.kind == "SCNE" and chunk.compression_magic == txtr.COMPRESSED_SENTINEL, "not a compressed SCNE span")
    decoded, _info = txtr.decode_chunk(bytes(span), chunk)
    return chunk, decoded


def decode_span(span: bytes) -> bytes:
    return _decode(span)[1]


def compile_span(span: bytes, row: dict) -> tuple[bytes, dict[str, Any]]:
    """The modern replacement for one retail span (complete resource; wrapper and scratch word kept)."""

    _tools()
    import nfl_vc_lz_fill as fill
    require(sha(span) == row["retail_sha256"], f"{row['scene']}: the span is not the pinned retail resource")
    _chunk, decoded = _decode(span)
    require(sha(decoded) == row["retail_decoded_sha256"], f"{row['scene']}: the decoded scene is not retail")
    after = compile_scene(row["scene"], decoded)
    require(not changed_outside(row["scene"], decoded, after), f"{row['scene']}: a change escaped its allowed ranges")
    try:
        rebuilt, info = fill.rebuild_fixed_span_filled(bytes(span), after, encoder="auto")
    except ValueError as exc:
        raise ModernGoalpostsError(f"{row['scene']}: {exc}") from exc
    _chunk, back = _decode(rebuilt)
    require(back == after and len(rebuilt) == len(span) and rebuilt[:32] == bytes(span[:32]),
            f"{row['scene']}: the fixed-span round trip failed")
    return rebuilt, dict(decoded_sha256=sha(after), compressed_bytes=info.compressed_bytes,
                         filled_bytes=info.filled_bytes, padding_bytes=info.padding_bytes, stored_size=info.stored_size,
                         scratch_bytes=info.scratch_bytes, exact_minimum_scratch=info.exact_minimum_scratch,
                         wrapper_identical=info.wrapper_identical)


# --- pins ------------------------------------------------------------------------------------------------------

_PINS: dict | None = None


def _hexed(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= set("0123456789abcdef")


def _check_pins(document: dict) -> dict:
    require(document.get("schema") == PINS_SCHEMA, "unsupported modern goalposts pins schema")
    outer = document.get("outer") or {}
    require(outer.get("index") == OUTER_INDEX and outer.get("name_id") == OUTER_NAME_ID and type(outer.get("size")) is int,
            "the pins must name gamedata.iff (outer 346)")
    rows = document.get("resources") or []
    require([(r.get("scene"), r.get("chunk_index")) for r in rows] == list(RESOURCES),
            "the pins must name goalpost_shadow and goalpost in chunk order")
    for row in rows:
        require(all(type(row.get(key)) is int and row[key] > 0 for key in ("chunk_offset", "span_size", "decoded_size")),
                f"{row.get('scene')}: pin geometry is incomplete")
        require(row["chunk_offset"] + row["span_size"] <= outer["size"], f"{row['scene']}: pin escapes the outer")
        require(all(_hexed(row.get(key)) for key in ("retail_sha256", "applied_sha256", "retail_decoded_sha256",
                                                      "applied_decoded_sha256"))
                and row["retail_sha256"] != row["applied_sha256"], f"{row['scene']}: span pins are incomplete")
    spans = sorted((r["chunk_offset"], r["chunk_offset"] + r["span_size"]) for r in rows)
    require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "pinned goalpost spans overlap")
    return document


def pins() -> dict:
    global _PINS
    if _PINS is None:
        require(PINS_PATH.is_file(), "modern goalposts pins are missing from this build")
        _PINS = _check_pins(json.loads(PINS_PATH.read_text(encoding="utf-8")))
    return _PINS


def available() -> bool:
    try:
        pins()
    except (OSError, ValueError):
        return False
    return True


def span_rows(document: dict | None = None) -> tuple[tuple[str, int, int, str, str], ...]:
    """((scene, chunk offset, span size, retail SHA-256, applied SHA-256), ...) in offset order (for the sprite
    scorebug's gamedata.iff rule)."""

    document = pins() if document is None else _check_pins(document)
    return tuple(sorted(((r["scene"], r["chunk_offset"], r["span_size"], r["retail_sha256"], r["applied_sha256"])
                         for r in document["resources"]), key=lambda r: r[1]))


def _state(span: bytes, row: dict) -> str:
    have = sha(span)
    return "retail" if have == row["retail_sha256"] else "applied" if have == row["applied_sha256"] else "foreign"


# --- gamedata.iff as bytes (pack 0) ------------------------------------------------------------------------------

def locate_outer(pack0: bytes) -> tuple[int, int]:
    """(offset inside pack 0, size) of gamedata.iff, from pack 0's own index (it must lie wholly inside pack 0)."""

    require(len(pack0) >= PACK_HEADER, "pack 0 is shorter than its index header")
    count, reserved, populated = struct.unpack_from("<III", pack0, 0)
    require(reserved == 0 and OUTER_INDEX < count <= 1_000_000 and 1 <= populated <= 36, "implausible pack 0 index")
    blocks = struct.unpack_from("<I", pack0, 12)[0]
    require(blocks * ALIGNMENT == len(pack0), "pack 0's declared size differs from the file")
    require(PACK_HEADER + 12 * count <= len(pack0), "the index runs past pack 0")
    name_id, size, offset_blocks = struct.unpack_from("<III", pack0, PACK_HEADER + 12 * OUTER_INDEX)
    require(name_id == OUTER_NAME_ID, "outer 346 is not gamedata.iff")
    offset = offset_blocks * ALIGNMENT
    require(offset + size <= len(pack0), "gamedata.iff is not wholly inside pack 0")
    return offset, size


def locate_chunks(outer: bytes, document: dict | None = None) -> dict[str, tuple[int, int]]:
    """{scene: (chunk offset, span size)} from gamedata.iff's own chunk table, checked against the pinned layout."""

    document = pins() if document is None else document
    _tools()
    import nfl_txtr as txtr
    chunks = txtr.parse_chunks(bytes(outer), allow_trailing=True)
    out = {}
    for row in document["resources"]:
        require(row["chunk_index"] < len(chunks), "gamedata.iff has fewer chunks than pinned")
        chunk = chunks[row["chunk_index"]]
        require(chunk.kind == "SCNE", f"{row['scene']}: chunk {row['chunk_index']} is not a scene")
        out[row["scene"]] = (chunk.offset, 32 + chunk.stored_size)
        require(out[row["scene"]] == (row["chunk_offset"], row["span_size"]),
                f"{row['scene']}: gamedata.iff is laid out differently from the pinned retail layout")
    return out


def pack0_states(pack0: bytes, document: dict | None = None) -> dict[str, str]:
    document = pins() if document is None else document
    at, size = locate_outer(pack0)
    outer = pack0[at:at + size]
    where = locate_chunks(outer, document)
    return {row["scene"]: _state(outer[where[row["scene"]][0]:sum(where[row["scene"]])], row)
            for row in document["resources"]}


def apply_pack0(pack0: bytes, document: dict | None = None) -> tuple[bytes, dict[str, Any]]:
    """Pack 0 with both goalpost spans modern (retail or already-modern spans only); everything else unchanged."""

    document = pins() if document is None else _check_pins(document)
    at, size = locate_outer(pack0)
    outer = pack0[at:at + size]
    where = locate_chunks(outer, document)
    out = bytearray(pack0)
    rows = []
    for row in document["resources"]:
        offset, span_size = where[row["scene"]]
        before = outer[offset:offset + span_size]
        state = _state(before, row)
        require(state != "foreign", f"{row['scene']}: the span is neither retail nor the modern goalpost")
        item = dict(scene=row["scene"], chunk_index=row["chunk_index"], pack0_offset=at + offset, span_size=span_size,
                    state_before=state, before_sha256=sha(before))
        if state == "retail":
            after, detail = compile_span(before, row)
            require(sha(after) == row["applied_sha256"], f"{row['scene']}: the compiled scene differs from its pin")
            out[at + offset:at + offset + span_size] = after
            item.update(written=True, after_sha256=sha(after), changed_bytes=sum(a != b for a, b in zip(before, after)),
                        **detail)
        else:
            item.update(written=False, after_sha256=sha(before), changed_bytes=0)
        rows.append(item)
    result = bytes(out)
    require(set(pack0_states(result, document).values()) == {"applied"}, "the goalpost read-back failed")
    return result, dict(outer_offset=at, outer_size=size, resources=rows)


# --- the executable ---------------------------------------------------------------------------------------------

def _xbe_offsets(payload: bytes) -> Callable[[int, int], int]:
    from .nfl2k5_bump_strength import _sections
    sections = _sections(payload)

    def offset(va: int, size: int) -> int:
        for section in sections:
            if section.virtual_address <= va and va + size <= section.virtual_address + section.raw_size:
                return section.raw_offset + va - section.virtual_address
        raise ModernGoalpostsError(f"0x{va:x} is outside the executable's sections")
    return offset


def xbe_status(payload: bytes) -> str:
    """retail / applied / foreign for the three sites (and the 1,371.6 literal the collision reads when applied)."""

    try:
        from . import nfl2k5_period_goalposts as period    # b77-v1b: the owner supersedes the three operands below
        if period.allocations(payload) and period.status(payload) == "applied":
            return "applied"
        offset = _xbe_offsets(payload)
        for va, value in XBE_GUARDS:
            at = offset(va, len(value))
            if payload[at:at + len(value)] != value:
                return "foreign"
        states = set()
        for _label, va, before, after in XBE_SITES:
            at = offset(va, len(before))
            site = payload[at:at + len(before)]
            states.add("retail" if site == before else "applied" if site == after else "foreign")
    except (ModernGoalpostsError, ValueError, struct.error):
        return "foreign"
    return states.pop() if len(states) == 1 else "foreign"


def _reseal(buffer: bytearray, touched: set[int]) -> list[int]:
    from .nfl2k5_bump_strength import _sections, section_digest
    sealed = []
    for section in _sections(bytes(buffer)):
        if section.index in touched:
            buffer[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(buffer), section)
            sealed.append(section.index)
    return sealed


def _touched_sections(payload: bytes) -> set[int]:
    from .nfl2k5_bump_strength import _sections
    sections = _sections(payload)
    offset = _xbe_offsets(payload)
    touched = set()
    for _label, va, before, _after in XBE_SITES:
        at = offset(va, len(before))
        touched |= {s.index for s in sections if s.raw_offset <= at < s.raw_offset + s.raw_size}
    return touched


def apply_xbe(payload: bytes) -> tuple[bytes, dict[str, Any]]:
    """The three sites, guarded, with the touched section's digest re-sealed."""

    state = xbe_status(payload)
    require(state in ("retail", "applied"), "default.xbe's goalpost sites are not the retail or modern bytes")
    edits = [dict(label=label, va=hex(va), size=len(before), before=before.hex(), after=after.hex())
             for label, va, before, after in XBE_SITES]
    if state == "applied":
        return payload, dict(status="already_applied", changed_bytes=0, edits=edits, sections_resealed=[])
    buffer = bytearray(payload)
    offset = _xbe_offsets(payload)
    for _label, va, before, after in XBE_SITES:
        at = offset(va, len(before))
        buffer[at:at + len(after)] = after
    sealed = _reseal(buffer, _touched_sections(payload))
    result = bytes(buffer)
    require(xbe_status(result) == "applied", "the goalpost executable read-back failed")
    return result, dict(status="applied", changed_bytes=sum(a != b for a, b in zip(payload, result)), edits=edits,
                        sections_resealed=sealed, before_sha256=sha(payload), after_sha256=sha(result))


def restore_xbe(payload: bytes) -> bytes:
    from . import nfl2k5_period_goalposts as period
    require(not (period.allocations(payload) and period.status(payload) == "applied"),
            "the period goalposts owner is installed in the executable's allocator; rebuild from a verified base to remove it")
    state = xbe_status(payload)
    require(state in ("retail", "applied"), "default.xbe's goalpost sites are not the retail or modern bytes")
    if state == "retail":
        return payload
    buffer = bytearray(payload)
    offset = _xbe_offsets(payload)
    for _label, va, before, after in XBE_SITES:
        at = offset(va, len(after))
        buffer[at:at + len(before)] = before
    _reseal(buffer, _touched_sections(payload))
    result = bytes(buffer)
    require(xbe_status(result) == "retail", "the goalpost executable restore read-back failed")
    return result


def operand_ranges() -> list[tuple[str, int, int]]:
    """(label, VA, size) of the four-byte operand each site rewrites (its opcode bytes stay retail)."""

    out = []
    for label, va, before, after in XBE_SITES:
        opcode = 1 if before[0] == 0x68 else 2          # push imm32 / fadd dword ptr [disp32]
        require(before[:opcode] == after[:opcode] and len(before) - opcode == 4, f"{label}: not a 4-byte operand edit")
        out.append((label, va + opcode, 4))
    return out


def xbe_reservations(payload: bytes) -> list[dict[str, Any]]:
    """The cave manifest's ownership rows: the three in-place operands this option writes in default.xbe."""

    require(xbe_status(payload) == "applied", "the goalpost executable sites are not modern")
    from . import nfl2k5_period_goalposts as period
    if period.allocations(payload) and period.status(payload) == "applied":
        # b77-v1b: the three v1 operands are superseded by the owner's four in-place sites (its code and cell are its
        # own allocator rows)
        a = period.allocations(payload)
        out = []
        for label, va, _accepted, after in period.sites(a["code"]["va"], a["read_only"]["va"]):
            skip = 1 if label == "stadium_load_hook" else 0
            out.append(dict(owner=OWNER, start=hex(va + skip), end=hex(va + len(after)), size=len(after) - skip,
                            basis=f"in-place {label} (no runtime space of its own)"))
        return out
    return [dict(owner=OWNER, start=hex(va), end=hex(va + size), size=size, basis=f"in-place {label} (no runtime space)")
            for label, va, size in operand_ranges()]


class XbePatch:
    """Adapter for the shared executable gates and the cave manifest's ownership recorder."""
    OWNER = OWNER
    REQUESTS = ()
    apply = staticmethod(apply_xbe)
    status = staticmethod(xbe_status)
    reservations = staticmethod(xbe_reservations)


# --- disc images (the Studio's build path) ----------------------------------------------------------------------

def _outer_image():
    _tools()
    import nfl2k5_playbook_position_recode as recode  # noqa: E402
    return recode.OuterImage


def _image_outer(archive, document: dict) -> tuple[int, dict[str, tuple[int, int]]]:
    """(gamedata.iff's virtual offset, {scene: (chunk offset, span size)}) of an opened outer archive."""

    require(OUTER_INDEX < len(archive.entries), "the archive has no outer 346")
    entry = archive.entries[OUTER_INDEX]
    require(entry.name_id == OUTER_NAME_ID, "outer 346 is not gamedata.iff")
    outer = archive.read(entry.virtual_offset, entry.size)
    return entry.virtual_offset, locate_chunks(outer, document)


def _xbe_of(source) -> bytes:
    """default.xbe from a disc image, or from a folder of extracted files (the folder or its parent)."""

    path = Path(source)
    if path.is_dir():
        for candidate in (path / "default.xbe", path.parent / "default.xbe"):
            if candidate.is_file():
                return candidate.read_bytes()
        raise ModernGoalpostsError("the source folder has no default.xbe")
    from . import nfl2k5_music_archive as archive
    with archive.Disc(path, descriptors=()) as disc:
        x = disc.entries["default.xbe"]
        require(x.size <= 16 * archive.BLOCK, "oversized XBE")
        return disc.read(x.size, x.byte_offset)


def resource_states(source, *, document: dict | None = None) -> dict[str, str] | None:
    """{scene: retail | applied | foreign, 'xbe': retail | applied | foreign}; None when gamedata.iff is foreign."""

    document = pins() if document is None else _check_pins(document)
    try:
        with _outer_image()(source) as archive:
            base, where = _image_outer(archive, document)
            states = {row["scene"]: _state(archive.read(base + where[row["scene"]][0], where[row["scene"]][1]), row)
                      for row in document["resources"]}
    except (ModernGoalpostsError, ValueError):
        return None
    states["xbe"] = xbe_status(_xbe_of(source))
    return states


def image_status(source, *, document: dict | None = None) -> str:
    """retail / applied / mixed / foreign across the two goalpost scenes and the executable sites."""

    states = resource_states(source, document=document)
    if states is None or "foreign" in states.values():
        return "foreign"
    parts = set(states.values())
    return parts.pop() if len(parts) == 1 else "mixed"


status = image_status


def _write_all(archive, plan: list[tuple[int, bytes, bytes]]) -> None:
    written: list[tuple[int, bytes]] = []
    try:
        for at, before, after in plan:
            require(archive.read(at, len(before)) == before, "a goalpost span changed after preflight")
            require(archive.write(at, after) == len(after), "short goalpost write")
            written.append((at, before))
            require(archive.read(at, len(after)) == after, "goalpost read-back differs")
    except BaseException:
        for at, before in reversed(written):
            archive.write(at, before)
        raise


def _write_xbe(path, transform: Callable[[bytes], bytes]) -> dict[str, Any] | None:
    """Same size, same place: only the three operands and the .text digest differ."""

    import os
    from . import nfl2k5_music_archive as archive
    from . import platform_compat as io
    path = Path(path).resolve()
    with archive.Disc(path, descriptors=()) as disc:
        identity = archive.identity(path)
        x = disc.entries["default.xbe"]
        require(x.size <= 16 * archive.BLOCK, "oversized XBE")
        old = disc.read(x.size, x.byte_offset)
        offset, size = x.byte_offset, x.size
    new = transform(old)
    if new == old:
        return None
    require(len(new) == len(old), "the goalpost sites never change the XBE size")
    require(archive.identity(path) == identity, "image changed after the goalpost preflight")
    with path.open("r+b") as writer:
        fd = writer.fileno()
        try:
            require(io.pwrite(fd, new, offset) == len(new), "short goalpost XBE write")
            require(io.pread(fd, size, offset) == new, "goalpost XBE read-back differs")
            os.fsync(fd)
        except Exception:
            io.pwrite(fd, old, offset)
            os.fsync(fd)
            raise
    return dict(offset=offset, size=size, in_place=True, before_sha256=sha(old), after_sha256=sha(new))


def apply_to_image(target, *, document: dict | None = None, progress=None) -> dict[str, Any]:
    """Build-only: ``target`` is the caller's disposable output image. Retail or applied parts only."""

    document = pins() if document is None else _check_pins(document)
    say = progress or (lambda message, done, total: None)
    states = resource_states(target, document=document)
    require(states is not None, "gamedata.iff is not laid out as the retail USA resource; rebuild from a supported source")
    require(states["xbe"] != "foreign", "default.xbe's goalpost sites are not the retail or modern bytes")
    rows: list[dict[str, Any]] = []
    plan: list[tuple[int, bytes, bytes]] = []
    with _outer_image()(target, writable=True) as archive:
        base, where = _image_outer(archive, document)
        total = len(document["resources"])
        for index, row in enumerate(document["resources"]):
            offset, size = where[row["scene"]]
            at = base + offset
            before = archive.read(at, size)
            state = _state(before, row)
            require(state != "foreign", f"{row['scene']}: the span is neither retail nor the modern goalpost; "
                                        "rebuild from a supported USA source")
            out = dict(scene=row["scene"], chunk_index=row["chunk_index"], chunk_offset=offset, span_size=size,
                       retail_sha256=row["retail_sha256"], applied_sha256=row["applied_sha256"], state_before=state)
            if state == "retail":
                say(f"Modern goalposts: {row['scene']} ({index + 1} of {total})", index, total)
                after, detail = compile_span(before, row)
                require(sha(after) == row["applied_sha256"], f"{row['scene']}: the compiled scene differs from its pin")
                plan.append((at, before, after))
                out.update(written=True, changed_bytes=sum(a != b for a, b in zip(before, after)), **detail)
            else:
                out.update(written=False, changed_bytes=0)
            rows.append(out)
        _write_all(archive, plan)
    say("Modern goalposts: the executable", total, total)
    xbe = _write_xbe(target, lambda payload: apply_xbe(payload)[0])
    state = image_status(target, document=document)
    require(state == "applied", "the modern goalposts failed their read-back on the copy")
    return dict(label=LABEL, option=BUILD_KEY, state=state, runtime_witnessed=False, outer=dict(document["outer"]),
                resources=rows, written=len(plan), already_applied=len(rows) - len(plan),
                changed_bytes=sum(row["changed_bytes"] for row in rows),
                xbe=dict(state_before=states["xbe"], sites=[dict(label=l, va=hex(v)) for l, v, _b, _a in XBE_SITES],
                         transport=xbe),
                upright_top_cm=MODERN_TOP, crossbar_top_cm=CROSSBAR_TOP)


def verify(source, *, enabled: bool = True, document: dict | None = None) -> dict[str, Any]:
    state = image_status(source, document=document)
    require(state == ("applied" if enabled else "retail"), "the modern goalposts do not match the request")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False)


def revert_image(target, retail_source, *, document: dict | None = None, progress=None) -> dict[str, Any]:
    """Exact revert: the two retail spans (read from a retail source and checked against their pins) and the retail
    executable sites."""

    document = pins() if document is None else _check_pins(document)
    say = progress or (lambda message, done, total: None)
    retail: dict[str, bytes] = {}
    with _outer_image()(retail_source) as source:
        base, where = _image_outer(source, document)
        for row in document["resources"]:
            span = source.read(base + where[row["scene"]][0], where[row["scene"]][1])
            require(sha(span) == row["retail_sha256"], f"{row['scene']}: the retail source is not retail")
            retail[row["scene"]] = span
    plan: list[tuple[int, bytes, bytes]] = []
    rows = []
    with _outer_image()(target, writable=True) as archive:
        base, where = _image_outer(archive, document)
        for index, row in enumerate(document["resources"]):
            at = base + where[row["scene"]][0]
            before = archive.read(at, where[row["scene"]][1])
            state = _state(before, row)
            require(state != "foreign", f"{row['scene']}: the span is neither retail nor the modern goalpost")
            if state == "applied":
                say(f"Restoring {row['scene']}", index, len(document["resources"]))
                plan.append((at, before, retail[row["scene"]]))
            rows.append(dict(scene=row["scene"], state_before=state, restored=state == "applied"))
        _write_all(archive, plan)
    _write_xbe(target, restore_xbe)
    state = image_status(target, document=document)
    require(state == "retail", "the exact revert failed its read-back")
    return dict(label=LABEL, option=BUILD_KEY, state=state, resources=rows, restored=len(plan), runtime_witnessed=False)


# --- author time -------------------------------------------------------------------------------------------------

def record_pins(pack0_path, out_path: Path | str | None = PINS_PATH) -> dict:
    """Author-time: retail and applied pins for the two scenes from a RETAIL pack 0 (vc_53450030/0)."""

    pack0 = Path(pack0_path).read_bytes()
    at, size = locate_outer(pack0)
    outer = pack0[at:at + size]
    _tools()
    import nfl_txtr as txtr
    chunks = txtr.parse_chunks(outer, allow_trailing=True)
    resources = []
    for scene, chunk_index in RESOURCES:
        chunk = chunks[chunk_index]
        span = outer[chunk.offset:chunk.offset + 32 + chunk.stored_size]
        _chunk, decoded = _decode(span)
        require(decoded[0x20:0x20 + 2 * len(scene) + 2] == (scene + "\0").encode("utf-16le"),
                f"chunk {chunk_index} is not {scene}")
        row = dict(scene=scene, chunk_index=chunk_index, chunk_offset=chunk.offset, span_size=len(span),
                   decoded_size=len(decoded), retail_sha256=sha(span), retail_decoded_sha256=sha(decoded))
        after, detail = compile_span(span, dict(row, applied_sha256="0" * 64, applied_decoded_sha256="0" * 64))
        row.update(applied_sha256=sha(after), applied_decoded_sha256=detail["decoded_sha256"],
                   fill={k: v for k, v in detail.items() if k != "decoded_sha256"})
        resources.append(row)
    document = dict(schema=PINS_SCHEMA, outer=dict(index=OUTER_INDEX, name_id=OUTER_NAME_ID, size=size),
                    resources=resources, upright_top_cm=dict(retail=RETAIL_TOP, modern=MODERN_TOP),
                    crossbar_top_cm=CROSSBAR_TOP, runtime_witnessed=False)
    _check_pins(document)
    if out_path is not None:
        Path(out_path).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                  newline="\n")
    return document


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_modern_goalposts",
                                     description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status").add_argument("source")
    record = sub.add_parser("record-pins")
    record.add_argument("retail_pack0")
    record.add_argument("--out", default=str(PINS_PATH))
    revert = sub.add_parser("revert")
    revert.add_argument("target")
    revert.add_argument("retail_source")
    args = parser.parse_args(argv)
    if args.command == "status":
        print(image_status(args.source))
    elif args.command == "record-pins":
        document = record_pins(args.retail_pack0, args.out)
        print(json.dumps({r["scene"]: r["applied_sha256"] for r in document["resources"]}, indent=2))
    else:
        print(json.dumps(revert_image(args.target, args.retail_source), indent=2))
    return 0


__all__ = ["BUILD_KEY", "BUILD_CAPTION", "CROSSBAR_TOP", "HELP_TEXT", "LABEL", "MODERN_TOP", "OWNER", "RETAIL_TOP",
           "ModernGoalpostsError", "XbePatch", "apply_pack0", "apply_to_image", "apply_xbe", "available",
           "compile_scene", "compile_span", "image_status", "pack0_states", "pins", "positions", "record_pins",
           "resource_states", "restore_xbe", "revert_image", "span_rows", "status", "verify", "xbe_status"]


if __name__ == "__main__":
    raise SystemExit(main())
