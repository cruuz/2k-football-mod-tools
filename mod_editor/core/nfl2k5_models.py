"""Export & Import Models: every NFL 2K5 SCNE model to glTF 2.0 and back.

Every 3D model the game draws -- player bodies and heads, helmets, face masks,
hands, balls, referees, coaches, cheerleaders, crowds, props, the Crib, menu
objects, trophies, stadiums -- is a ``SCNE`` resource inside the
``vc_53450030`` pack archive.  The studio's private source cache already holds
those packs and a resource inventory derived from the user's own disc, so this
module never touches research assets: it decodes a scene straight from the
cache, writes a Blender-readable glTF 2.0 file beside a binary buffer, and,
for an edited file coming back, rewrites the vertex lanes the game reads into
a COPY of the disc image.

What is exported (per shape):
* positions -- ``FLOAT3`` copied, ``NORMSHORT3`` decoded with the shape's
  proved scale/offset (``position = normshort3 * scale + offset``);
* normals -- register 2 ``NORMPACKED3`` (11/11/10-bit signed);
* texture coordinates -- register 6 ``NORMSHORT2``, un-normalised with the
  SHAPE's OWN constant: ``uv = normshort2 * (Su, Sv) + (Ou, Ov)``, the four
  floats at shape record ``+0x30..+0x3C``.  Every NFL 2K5 vertex shader that
  routes register 6 to a texture coordinate computes exactly
  ``MAD oT0.xy, v6.xyyy, c[-89].xyyy, c[-89].zwww`` (18 of the 20 programs in
  the executable; the other two copy v6 through unchanged), and the draw path
  loads c[-89] from ``[shape + 0x30]`` right beside the proved position
  constant at ``+0x10``/``+0x20``.  There is no V flip: Sv is positive on
  every shape sampled.  Beta 56 shipped the fixed rule ``u = (n + 1) / 2``,
  ``v = (1 - n) / 2``, "verified on the referee" -- that was the special case
  ``S = O = 0.5`` plus a flip that merely looked plausible on a striped shirt;
  the referee's real constant is (0.81, 1.24, 0.55, 0.18) and 242 of 282
  stadium shapes tile (S up to 12), so the fixed rule collapsed every tiled
  surface onto one repeat and mirrored V everywhere;
* vertex colours -- register 3 ``D3DCOLOR``, written as the custom attribute
  ``_NFL_COLOR`` (VEC4 float, r g b a in 0..1).  In game it is baked lighting
  (``MUL oD0, v3, c[-90]``, mean 155/255) that multiplies the texture; as
  ``COLOR_0`` Blender would multiply it into the base colour and every texture
  looks dark and blotchy, so ``COLOR_0`` is only written on request
  (``include_vertex_colors_as_color0``);
* the Stadium Studio contract -- ``nfl2k5_texture_id`` on every material,
  texture and image, images named after the first material that maps them,
  ``source_*`` extras on meshes, primitives and nodes, and a root node named
  ``nfl2k5_units_centimetre_to_metre`` -- so the Stadium Studio's texture
  write-back and the community Blender add-on accept this export unchanged;
* topology -- the decoded NV2A push streams (triangle strips and quads), one
  glTF primitive per game submesh, each bound to its material;
* materials and the embedded P8 textures they reference, as PNG images inside
  the buffer, so Blender's material preview shows the game surface;
* a skin (joints, JOINTS_0/WEIGHTS_0, inverse binds) for every shape whose
  transform table has more than one entry, through the executable-proved
  palette contract (selector = 3 x local slot, per-submesh remap, CPU blends);
* morph channel names and counts as metadata (the delta encoding is not yet
  decoded, so channels are listed, not exported as morph targets);
* a ``_NFL_VERTEX_INDEX`` custom attribute carrying each vertex's game index,
  which lets an edited file come back even after Blender re-orders vertices.

What import does: same-topology edits.  The vertex count, triangle
connectivity and every non-lane byte stay exactly as the game shipped them;
positions (and normals / UVs / ``_NFL_COLOR`` when the file carries them) are
re-encoded into the game's fixed-point lanes.  Edits that push a ``NORMSHORT3``
shape outside its retail range are absorbed by widening the shape's
scale/offset; a UV edit outside ``O +/- S`` widens the shape's UV constant at
``+0x30`` the same way, one axis at a time.  A file
with a different vertex count is fitted by nearest-vertex projection and the
report says so.  Nothing is added or removed: the compressed resource is
rebuilt into its retail span with the wrapper byte-identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
from typing import Any, Callable, Iterable, Mapping, Sequence

from mod_editor.core import platform_compat

ROOT = Path(__file__).resolve().parents[2]
PACK_FOLDER = Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030")
ARCHIVE_NAME = "vc_53450030"
GLTF_UNIT_SCALE = 0.01                      # the game authors in centimetres; glTF is metres
VERTEX_INDEX_ATTRIBUTE = "_NFL_VERTEX_INDEX"
COLOUR_ATTRIBUTE = "_NFL_COLOR"             # the D3DCOLOR lane, r g b a as floats 0..1
UV_CONSTANT_OFFSET = 0x30                   # shape record: Su, Sv, Ou, Ov (four floats) = shader c[-89]
UV_CONSTANT_FORMAT = "<4f"
#: The Stadium Studio contract (``nfl2k5_stadium_studio.py`` imports these from here): the
#: canonical texture id every material/texture/image carries, and the root node's name.
GLTF_TEXTURE_ID_KEY = "nfl2k5_texture_id"
GLTF_MATERIAL_INDEX_KEY = "nfl2k5_material_index"
ROOT_NODE_NAME = "nfl2k5_units_centimetre_to_metre"
SCHEMA_EXPORT = "nfl2k5_model_export/v2"
SCHEMA_IMPORT = "nfl2k5_model_import/v1"
PALETTE_SLOTS = 56
REMAP_SENTINEL = 0x7F7F
HEADER_SIZE = 0x20
ProgressSink = Callable[[str, int, int], None]


class ModelsError(ValueError):
    """A models export/import refusal with a user-facing message."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelsError(message)


# ------------------------------------------------------------------ tool modules

def _tools_module(name: str):
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return importlib.import_module(name)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# ------------------------------------------------------------------ codecs

def decode_vc_lz_prefix(stream: bytes, limit: int) -> bytes:
    """The first ``limit`` output bytes of a VC-LZ stream (the title's decoder, stopped early).

    Same token rules as ``nfl_txtr.decompress_vc_lz``; used to read a scene's name without
    inflating the whole resource, which makes listing 4,616 models a second's work.
    """
    if len(stream) < 10:
        raise ModelsError("compressed stream is shorter than its prefix")
    output_size = struct.unpack_from("<I", stream, 0)[0]
    offset_bits = stream[8]
    distance_mask = (1 << offset_bits) - 1
    length_mask = (1 << (16 - offset_bits)) - 1
    want = min(limit, output_size)
    out = bytearray()
    src = 9
    flags = stream[src]
    src += 1
    flag_mask = 1
    while len(out) < want:
        if flags & flag_mask:
            if src + 2 > len(stream):
                break
            code = struct.unpack_from("<H", stream, src)[0]
            src += 2
            distance = code & distance_mask
            length = ((code >> offset_bits) & length_mask) + 3
            if distance == 0 or distance > len(out):
                break
            start = len(out) - distance
            # the title copies backwards; sources never overlap the destination in shipped data
            out.extend(out[start:start + length])
        else:
            if src >= len(stream):
                break
            out.append(stream[src])
            src += 1
        flag_mask = (flag_mask << 1) & 0xFF
        if flag_mask == 0 and len(out) < want:
            if src >= len(stream):
                break
            flags = stream[src]
            src += 1
            flag_mask = 1
    return bytes(out[:want])


def normshort(value: int) -> float:
    """Xbox signed-normalised 16-bit: /32767 when >= 0, /32768 when negative."""
    return value / 32767.0 if value >= 0 else value / 32768.0


def encode_normshort(value: float) -> int:
    scaled = value * 32767.0 if value >= 0 else value * 32768.0
    return max(-32768, min(32767, int(round(scaled))))


def decode_normpacked3(word: int) -> tuple[float, float, float]:
    """NV2A ``NORMPACKED3``: x bits 0..10, y bits 11..21, z bits 22..31 (signed)."""
    x = word & 0x7FF
    y = (word >> 11) & 0x7FF
    z = (word >> 22) & 0x3FF
    if x & 0x400:
        x -= 0x800
    if y & 0x400:
        y -= 0x800
    if z & 0x200:
        z -= 0x400
    return (x / 1023.0 if x >= 0 else x / 1024.0,
            y / 1023.0 if y >= 0 else y / 1024.0,
            z / 511.0 if z >= 0 else z / 512.0)


def encode_normpacked3(x: float, y: float, z: float) -> int:
    def pack(value: float, positive: int, negative: int, mask: int) -> int:
        scaled = value * positive if value >= 0 else value * negative
        quantised = max(-negative, min(positive, int(round(scaled))))
        return quantised & mask
    return pack(x, 1023, 1024, 0x7FF) | (pack(y, 1023, 1024, 0x7FF) << 11) | (pack(z, 511, 512, 0x3FF) << 22)


def _normalise(vector: Sequence[float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1e-12:
        return (0.0, 0.0, 1.0)
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def d3dcolor_to_rgba(word: int) -> tuple[int, int, int, int]:
    """``D3DCOLOR`` (0xAARRGGBB) -> (r, g, b, a) bytes."""
    return ((word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF, (word >> 24) & 0xFF)


def rgba_to_d3dcolor(r: int, g: int, b: int, a: int) -> int:
    clamp = [max(0, min(255, int(round(c)))) for c in (r, g, b, a)]
    return (clamp[3] << 24) | (clamp[0] << 16) | (clamp[1] << 8) | clamp[2]


def _float32(value: float) -> float:
    """``value`` rounded to the nearest binary32, the way the shape record stores it."""
    return float(struct.unpack("<f", struct.pack("<f", value))[0])


# ------------------------------------------------------------------ Stadium Studio contract

def scene_contract_id(scene_name: str, outer_index: int, chunk_index: int, scene_index: int) -> str:
    """The Stadium Studio's scene id: ``nfl2k5.stadium.o3136.c0006.scene1974`` for a stadium.

    ``scene_index`` is the resource's position among the archive's SCNE resources in inventory
    order -- the same enumeration the private stadium cache worker uses -- so a stadium exported
    here carries the very ids the Stadium Studio's texture write-back keys on.  Other scenes
    use their own (file-safe) name in place of ``stadium``.
    """
    return (f"nfl2k5.{safe_file_name(scene_name)}.o{int(outer_index):04d}.c{int(chunk_index):04d}."
            f"scene{int(scene_index):04d}")


def texture_contract_id(scene_id: str, texture_index: int) -> str:
    return f"{scene_id}.texture{int(texture_index):04d}"


# ------------------------------------------------------------------ catalog

# Friendly grouping by scene name. Order matters: the first match wins.
GROUP_RULES: tuple[tuple[str, str, str], ...] = (
    (r"^(hi_body|lo_body|hi_head|hands|facemask|facial_anim|player_lo|sideline_player|shadow_\d+|shadow_low|c_shadow)$",
     "players", "Players"),
    (r"helmet|facemask", "helmets", "Helmets & face masks"),
    (r"^(ball|game_ball|ballindi|ball_shadow|propsball|propsball_shadow|tee|goalpost|goalpost_shadow|goalnet|marks|divot|flag|propschain|chain_gang|KickArrow|KickMeter|windmeter|pylon)",
     "field", "Balls & field props"),
    (r"^(referee|referee_shadow|chaingang|coach|coach_asst|coach_desk|trainer|cameraman|security|vip|commish|ball_guy|tutorial_coaches)",
     "officials", "Officials, coaches & staff"),
    (r"^(cheerleader|crowd)", "crowd", "Cheerleaders & crowd"),
    (r"^props", "props", "Sideline props"),
    (r"^(stadium|field|detail_layer|cityscape|skybox|intro_cameras|scoreboard)$", "stadiums", "Stadiums & environment"),
    (r"^HI_", "trophies", "Trophy room & records"),
    (r"^cutscene|kolber|berman|sc_|ESPN_25", "cutscenes", "Cutscenes & studio"),
    (r"bobblehead|^(room|air_hockey|bar_|bench_|coffee_table|console_table|couch|credenza|dart|end_table|fish_tank|glass|gumball|guitar|jukebox|lamp|paddles|phone|popcorn|puck|punching_bag|recliner|rink|soda_machine|sofa|speaker|table|theater|trivia|wall_clock|water_feature|framed_jersey|mug|helmet_mug|cap|open_book|closed_book|paper_football|ceiling_fan|logodisk|mini_helmet|fullsize_helmet|foam_finger)",
     "crib", "The Crib"),
    (r"^(main_menu|menu|nav_|gui|cursor|buttons|icon|selector|playcall|player_frame|playercard|playerinfopanel|player_lineup|player_photo|team_|draft_menu|front_office|franchise_lo|user_lo|primetime_lo|score_bug|ticker|ticks|replayOverlay|overlay_wipe|pop_up|pie_chart|radar_chart|route_arrow|crosshair|weekly_prep|unlockables|gamecast|media|geometry_font|create_a_team|double_team_select|single_team_select|Menubackground|marks|end_icon|blue_icon|cell_phone|shockwave|icon_)",
     "menus", "Menus & interface"),
)
GROUP_LABELS: dict[str, str] = {group: label for _pattern, group, label in GROUP_RULES}
GROUP_LABELS["other"] = "Other"
GROUP_ORDER = ("players", "helmets", "field", "officials", "crowd", "props", "stadiums",
               "trophies", "cutscenes", "crib", "menus", "other")


def safe_file_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "model"


def group_for_name(name: str) -> str:
    for pattern, group, _label in GROUP_RULES:
        if re.search(pattern, name):
            return group
    return "other"


@dataclass(frozen=True)
class ModelEntry:
    key: str                       # "o{outer}c{chunk}"
    outer_index: int
    chunk_index: int
    name: str
    group: str
    stored_size: int
    decoded_size: int

    @property
    def label(self) -> str:
        return f"{self.name}  (outer {self.outer_index}, chunk {self.chunk_index})"


def model_key(outer_index: int, chunk_index: int) -> str:
    return f"o{int(outer_index)}c{int(chunk_index)}"


def parse_model_key(key: str) -> tuple[int, int]:
    match = re.fullmatch(r"o(\d+)c(\d+)", key.strip())
    _require(match is not None, f"Not a model key: {key!r}")
    assert match is not None
    return int(match.group(1)), int(match.group(2))


class ModelSource:
    """One opened pack archive + inventory (the studio's private cache or a research extraction)."""

    def __init__(self, index_path: Path, inventory_path: Path) -> None:
        self.index_path = Path(index_path)
        self.inventory_path = Path(inventory_path)
        outer = _tools_module("nfl_outer")
        probe = _tools_module("nfl_scene_probe")
        try:
            self.archive = outer.parse_archive(self.index_path)
            _document, resources = probe.parse_inventory(self.inventory_path)
        except Exception as exc:  # noqa: BLE001 - one user-facing message
            raise ModelsError(f"Could not open the model archive: {exc}") from exc
        self._outer = outer
        self._probe = probe
        self.resources = {(r.outer_index, r.chunk_index): r for r in resources if r.kind == "SCNE"}
        # inventory-order position among the SCNE resources: the Stadium Studio's ``scene_index``
        self._scene_positions = {identity: position for position, identity in enumerate(self.resources)}
        self._names: dict[tuple[int, int], str] | None = None

    def scene_index(self, resource: Any) -> int:
        """The resource's position among the archive's SCNE resources (inventory order)."""
        return int(self._scene_positions[(resource.outer_index, resource.chunk_index)])

    # -- names / catalog --------------------------------------------------
    NAME_PREFIX_BYTES = 512        # every shipped scene keeps its name at decoded offset 0x20
    NAME_SPAN_BYTES = 4096

    def _scene_name(self, resource: Any) -> str:
        """The scene's name from a bounded decode of the first bytes of its resource."""
        inventory = _tools_module("nfl_scne_inventory")
        fallback = f"scene_{resource.outer_index}_{resource.chunk_index}"
        entry = self.archive.entries[resource.outer_index]
        span_size = min(HEADER_SIZE + self.NAME_SPAN_BYTES, HEADER_SIZE + resource.stored_size)
        try:
            head = self._outer.read_entry_range(self.archive, entry, resource.chunk_offset, span_size)
            magic = struct.unpack_from("<I", head, 0x10)[0]
            if magic == 0xFEEDBEEF:              # VC-LZ compressed body
                prefix = decode_vc_lz_prefix(head[HEADER_SIZE:], self.NAME_PREFIX_BYTES)
            else:                                # stored raw
                prefix = head[HEADER_SIZE:HEADER_SIZE + self.NAME_PREFIX_BYTES]
        except Exception:  # noqa: BLE001 - a scene we cannot name still appears, by its identity
            return fallback
        if len(prefix) < 0x18 or prefix[0x0C:0x10] != b"SCNE":
            return fallback
        try:
            _target, name = inventory.pointer_name(prefix, 0x10, len(prefix), "scene name")
        except Exception:  # noqa: BLE001
            return fallback
        return str(name or fallback)

    def catalog(self, progress: ProgressSink | None = None) -> list[ModelEntry]:
        """Every SCNE in the archive, named. Decodes each scene header once (cached per source)."""
        entries: list[ModelEntry] = []
        total = len(self.resources)
        for done, ((outer_index, chunk_index), resource) in enumerate(sorted(self.resources.items())):
            if progress and done % 200 == 0:
                progress("Reading model names", done, total)
            name = self._scene_name(resource)
            entries.append(ModelEntry(
                model_key(outer_index, chunk_index), outer_index, chunk_index, name,
                group_for_name(name), int(resource.stored_size), int(resource.word_08 + resource.word_0c),
            ))
        if progress:
            progress("Reading model names", total, total)
        return entries

    # -- decoding -----------------------------------------------------------
    def resource(self, key: str) -> Any:
        outer_index, chunk_index = parse_model_key(key)
        resource = self.resources.get((outer_index, chunk_index))
        _require(resource is not None, f"No model at outer {outer_index}, chunk {chunk_index}.")
        return resource

    def span(self, resource: Any) -> bytes:
        entry = self.archive.entries[resource.outer_index]
        return self._outer.read_entry_range(self.archive, entry, resource.chunk_offset,
                                            HEADER_SIZE + resource.stored_size)

    def decode(self, resource: Any) -> tuple[bytes, dict[str, Any]]:
        return self._probe.decode_resource(self.span(resource), resource)

    def decode_span(self, span: bytes, resource: Any) -> bytes:
        """Decode any span laid out like ``resource`` (e.g. a rebuilt one) to its system bytes."""
        decoded, _detail = self._probe.decode_resource(bytes(span), resource)
        return decoded

    def parse(self, key: str) -> tuple[Any, bytes, dict[str, Any]]:
        """(resource, decoded bytes, parsed scene dict) for one model key."""
        inventory = _tools_module("nfl_scne_inventory")
        resource = self.resource(key)
        decoded, _detail = self.decode(resource)
        scene, _names, _mappings, _sample = inventory.parse_scene(
            resource.outer_index * 100_000 + resource.chunk_index, resource, decoded, {}
        )
        return resource, decoded, scene

    def archive_segments(self, resource: Any) -> tuple[Any, ...]:
        """Which pack file(s) hold this resource's span, and where inside them."""
        entry = self.archive.entries[resource.outer_index]
        starts = [pack.virtual_start for pack in self.archive.packs]
        return self._outer.range_segments(
            self.archive.packs, starts, entry.virtual_offset + resource.chunk_offset,
            HEADER_SIZE + resource.stored_size,
        )


# ------------------------------------------------------------------ shape decoding

@dataclass
class ShapeLanes:
    """Everything the exporter/importer needs to know about one shape's vertex lanes."""
    index: int
    name: str
    record_offset: int
    vertex_count: int
    transform_count: int
    blend_count: int
    submesh_count: int
    morph_count: int
    position_format: str
    position_stream: int
    position_offset: int
    position_stride: int
    scale: float
    offset: tuple[float, float, float]
    normal: tuple[int, int, int] | None       # (stream, byte offset, stride)
    texcoord: tuple[int, int, int] | None
    colour: tuple[int, int, int] | None
    selector: tuple[int, int, int] | None
    stream_offsets: tuple[int, ...]
    stream_strides: tuple[int, ...]
    uv_scale: tuple[float, float] = (1.0, 1.0)       # shape +0x30, +0x34 (shader c[-89].xy)
    uv_offset: tuple[float, float] = (0.0, 0.0)      # shape +0x38, +0x3C (shader c[-89].zw)


def read_uv_constant(decoded: bytes, record_offset: int) -> tuple[tuple[float, float], tuple[float, float]]:
    """``((Su, Sv), (Ou, Ov))`` from the four floats at shape record ``+0x30``."""
    su, sv, ou, ov = struct.unpack_from(UV_CONSTANT_FORMAT, decoded, int(record_offset) + UV_CONSTANT_OFFSET)
    return (float(su), float(sv)), (float(ou), float(ov))


def _shape_lanes(scene: Mapping[str, Any], shape: Mapping[str, Any], decoded: bytes | None = None) -> ShapeLanes:
    """Lane layout of one shape; with ``decoded`` the shape's UV constant is read as well."""
    streams = {int(s["stream_index"]): s for s in shape["vertex_streams"]}
    descriptors = {int(d["register"]): d for d in shape["attribute_descriptors"]}
    position = descriptors.get(0)
    _require(position is not None, f"shape {shape['name']} has no position register")
    assert position is not None

    def lane(register: int, expected: str) -> tuple[int, int, int] | None:
        descriptor = descriptors.get(register)
        if descriptor is None or descriptor["format_name"] != expected:
            return None
        stream = streams.get(int(descriptor["stream_index"]))
        if stream is None:
            return None
        return (int(descriptor["stream_index"]), int(descriptor["byte_offset"]), int(stream["stride"]))

    position_stream = streams.get(int(position["stream_index"]))
    _require(position_stream is not None, f"shape {shape['name']} has no position stream")
    assert position_stream is not None
    offsets = tuple(int(s["offset"]) for _i, s in sorted(streams.items()))
    strides = tuple(int(s["stride"]) for _i, s in sorted(streams.items()))
    lanes = ShapeLanes(
        index=int(shape["index"]), name=str(shape["name"]), record_offset=int(shape["record_offset"]),
        vertex_count=int(shape["vertex_count"]), transform_count=int(shape["transform_count"]),
        blend_count=0, submesh_count=int(shape["submesh_count"]), morph_count=int(shape["morph_channel_count"]),
        position_format=str(position["format_name"]), position_stream=int(position["stream_index"]),
        position_offset=int(position["byte_offset"]), position_stride=int(position_stream["stride"]),
        scale=1.0, offset=(0.0, 0.0, 0.0),
        normal=lane(2, "NORMPACKED3"), texcoord=lane(6, "NORMSHORT2"), colour=lane(3, "D3DCOLOR"),
        selector=lane(1, "SHORT1"), stream_offsets=offsets, stream_strides=strides,
    )
    if decoded is not None:
        lanes.uv_scale, lanes.uv_offset = read_uv_constant(decoded, lanes.record_offset)
    return lanes


def _stream_base(scene: Mapping[str, Any], shape: Mapping[str, Any], stream_index: int) -> int:
    for stream in shape["vertex_streams"]:
        if int(stream["stream_index"]) == stream_index:
            return int(stream["offset"])
    raise ModelsError(f"shape {shape['name']} has no vertex stream {stream_index}")


def read_positions(decoded: bytes, shape: Mapping[str, Any], lanes: ShapeLanes) -> list[tuple[float, float, float]]:
    base = _stream_base({}, shape, lanes.position_stream)
    out: list[tuple[float, float, float]] = []
    if lanes.position_format == "FLOAT3":
        for vertex in range(lanes.vertex_count):
            out.append(struct.unpack_from("<3f", decoded, base + vertex * lanes.position_stride + lanes.position_offset))
        return out
    _require(lanes.position_format == "NORMSHORT3",
             f"shape {lanes.name}: position format {lanes.position_format} has no proved decoder")
    scale = struct.unpack_from("<f", decoded, lanes.record_offset + 0x10)[0]
    offset = struct.unpack_from("<3f", decoded, lanes.record_offset + 0x20)
    lanes.scale, lanes.offset = float(scale), tuple(float(v) for v in offset)
    for vertex in range(lanes.vertex_count):
        q = struct.unpack_from("<3h", decoded, base + vertex * lanes.position_stride + lanes.position_offset)
        out.append(tuple(normshort(q[axis]) * scale + offset[axis] for axis in range(3)))
    return out


def read_lane_u32(decoded: bytes, shape: Mapping[str, Any], lane: tuple[int, int, int], count: int) -> list[int]:
    base = _stream_base({}, shape, lane[0])
    return [struct.unpack_from("<I", decoded, base + v * lane[2] + lane[1])[0] for v in range(count)]


def read_lane_2h(decoded: bytes, shape: Mapping[str, Any], lane: tuple[int, int, int], count: int) -> list[tuple[int, int]]:
    base = _stream_base({}, shape, lane[0])
    return [struct.unpack_from("<2h", decoded, base + v * lane[2] + lane[1]) for v in range(count)]


def read_lane_h(decoded: bytes, shape: Mapping[str, Any], lane: tuple[int, int, int], count: int) -> list[int]:
    base = _stream_base({}, shape, lane[0])
    return [struct.unpack_from("<h", decoded, base + v * lane[2] + lane[1])[0] for v in range(count)]


# ------------------------------------------------------------------ skin decoding

@dataclass
class ShapeSkin:
    transforms: list[dict[str, Any]]          # index, name, parent, absolute, local
    influences: list[list[tuple[int, float]]]  # per vertex: [(joint, weight)]
    notes: list[str] = field(default_factory=list)


def decode_skin(decoded: bytes, shape: Mapping[str, Any], lanes: ShapeLanes,
                submeshes: Sequence[Mapping[str, Any]]) -> ShapeSkin | None:
    """Joints and per-vertex influences through the proved palette contract; None when rigid."""
    inventory = _tools_module("nfl_scne_inventory")
    gltf_tool = _tools_module("nfl_scne_gltf")
    limit = len(decoded)
    record = lanes.record_offset
    transform_count = lanes.transform_count
    if transform_count <= 1 or lanes.selector is None:
        return None
    blend_count = struct.unpack_from("<H", decoded, record + 0x52)[0]
    transform_start = inventory.resolve_relative(decoded, record + 0x64, limit, "transforms")
    blend_start = inventory.resolve_relative(decoded, record + 0x60, limit, "blends") if blend_count else None
    submesh_start = inventory.resolve_relative(decoded, record + 0x70, limit, "submeshes")
    if transform_start is None or submesh_start is None:
        return None
    transforms: list[dict[str, Any]] = []
    for index in range(transform_count):
        raw_offset = transform_start + index * 0x70
        absolute = struct.unpack_from("<3f", decoded, raw_offset + 0x40)
        local = struct.unpack_from("<3f", decoded, raw_offset + 0x50)
        parent = struct.unpack_from("<i", decoded, raw_offset + 0x64)[0]
        _target, name = inventory.pointer_name(decoded, raw_offset + 0x60, limit, f"transform {index}")
        if parent >= index or parent < -1:
            return None
        transforms.append({"index": index, "name": str(name or f"joint_{index}"), "parent": parent,
                           "absolute": tuple(float(v) for v in absolute), "local": tuple(float(v) for v in local)})
    blends: list[list[tuple[int, float]]] = []
    for index in range(blend_count):
        assert blend_start is not None
        raw_offset = blend_start + index * 0x1C
        blend_type = struct.unpack_from("<I", decoded, raw_offset)[0]
        if blend_type not in (2, 3):
            return None
        active: list[tuple[int, float]] = []
        for source in range(blend_type):
            joint, weight = struct.unpack_from("<If", decoded, raw_offset + 4 + source * 8)
            if joint >= transform_count or not math.isfinite(weight):
                return None
            active.append((int(joint), float(weight)))
        blends.append(active)
    selectors = read_lane_h(decoded, shape, lanes.selector, lanes.vertex_count)
    resolved: dict[int, int] = {}
    for submesh in submeshes:
        submesh_offset = int(submesh["record_offset"])
        first_slot, last_slot = struct.unpack_from("<HH", decoded, submesh_offset + 4)
        mappings = struct.unpack_from(f"<{PALETTE_SLOTS}H", decoded, submesh_offset + 8)
        batches = gltf_tool.decode_batches(decoded, int(submesh["command_offset"]),
                                           int(submesh["primary_command_word_count"]))
        for _mode, indices in batches:
            for vertex in indices:
                selector = selectors[vertex]
                if selector < 0 or selector % 3:
                    return None
                slot = selector // 3
                if slot >= PALETTE_SLOTS:
                    return None
                global_index = mappings[slot]
                if global_index == REMAP_SENTINEL or global_index >= transform_count + blend_count:
                    return None
                previous = resolved.get(vertex)
                if previous is not None and previous != global_index:
                    return None
                resolved[vertex] = global_index
    influences: list[list[tuple[int, float]]] = []
    for vertex in range(lanes.vertex_count):
        global_index = resolved.get(vertex)
        if global_index is None:
            influences.append([(0, 1.0)])
        elif global_index < transform_count:
            influences.append([(global_index, 1.0)])
        else:
            influences.append(list(blends[global_index - transform_count]))
    skin = ShapeSkin(transforms, influences)
    unresolved = lanes.vertex_count - len(resolved)
    if unresolved:
        skin.notes.append(f"{unresolved} vertices are not referenced by any submesh; bound to the root joint")
    return skin


# ------------------------------------------------------------------ morph channels

def morph_channels(decoded: bytes, lanes: ShapeLanes) -> list[dict[str, Any]]:
    inventory = _tools_module("nfl_scne_inventory")
    if lanes.morph_count == 0:
        return []
    limit = len(decoded)
    table = inventory.resolve_relative(decoded, lanes.record_offset + 0x74, limit, "morph table")
    if table is None:
        return []
    channels: list[dict[str, Any]] = []
    for index in range(lanes.morph_count):
        raw_offset = table + index * 0x0C
        _target, name = inventory.pointer_name(decoded, raw_offset, limit, f"morph {index}")
        count, data_offset = struct.unpack_from("<II", decoded, raw_offset + 4)
        channels.append({"index": index, "name": str(name or f"channel_{index}"),
                         "record_count": int(count), "data_offset": int(data_offset)})
    return channels


# ------------------------------------------------------------------ glTF export

def _align4(binary: bytearray) -> None:
    while len(binary) % 4:
        binary.append(0)


class _GltfBuilder:
    def __init__(self) -> None:
        self.binary = bytearray()
        self.buffer_views: list[dict[str, Any]] = []
        self.accessors: list[dict[str, Any]] = []
        self.meshes: list[dict[str, Any]] = []
        self.nodes: list[dict[str, Any]] = []
        self.materials: list[dict[str, Any]] = []
        self.images: list[dict[str, Any]] = []
        self.textures: list[dict[str, Any]] = []
        self.skins: list[dict[str, Any]] = []

    def view(self, payload: bytes, target: int | None) -> int:
        _align4(self.binary)
        entry: dict[str, Any] = {"buffer": 0, "byteOffset": len(self.binary), "byteLength": len(payload)}
        if target is not None:
            entry["target"] = target
        self.binary.extend(payload)
        self.buffer_views.append(entry)
        return len(self.buffer_views) - 1

    def accessor(self, view: int, component_type: int, count: int, kind: str, *,
                 minimum: Sequence[float] | None = None, maximum: Sequence[float] | None = None,
                 normalized: bool = False) -> int:
        entry: dict[str, Any] = {"bufferView": view, "byteOffset": 0, "componentType": component_type,
                                 "count": count, "type": kind}
        if minimum is not None and maximum is not None:
            entry["min"] = list(minimum)
            entry["max"] = list(maximum)
        if normalized:
            entry["normalized"] = True
        self.accessors.append(entry)
        return len(self.accessors) - 1


@dataclass
class ExportResult:
    key: str
    name: str
    gltf_path: Path
    bin_path: Path
    readme_path: Path
    shapes: list[dict[str, Any]]
    notes: list[str]
    textures: int

    def summary(self) -> str:
        skinned = sum(1 for s in self.shapes if s.get("skin"))
        vertices = sum(int(s["vertex_count"]) for s in self.shapes)
        return (f"{self.name}: {len(self.shapes)} mesh(es), {vertices:,} vertices, "
                f"{self.textures} texture(s), {skinned} skinned")


def _decode_texture_png(decoded: bytes, resource: Any, scene: Mapping[str, Any],
                        texture: Mapping[str, Any]) -> dict[str, Any] | None:
    """PNG bytes plus the provenance the Stadium Studio records, or None outside the P8 decoder.

    Keys: ``png``, ``width``, ``height``, ``has_alpha``, ``rgba_sha256`` (the hash the private
    stadium cache names its PNGs by) and ``format_name``.
    """
    inventory = _tools_module("nfl_scne_inventory")
    txtr = _tools_module("nfl_txtr")
    try:
        info = inventory.texture_info(decoded, int(texture["descriptor_offset"]), str(scene["name"]), int(texture["index"]))
        rgba = txtr.texture_to_rgba(decoded, resource.as_chunk(), info)
        has_alpha = any(rgba[i] != 255 for i in range(3, len(rgba), 4))
        return {"png": txtr.encode_rgba_png(info.width, info.height, rgba), "width": int(info.width),
                "height": int(info.height), "has_alpha": has_alpha, "rgba_sha256": _sha256(bytes(rgba)),
                "format_name": str(info.format_name)}
    except Exception:  # noqa: BLE001 - a texture outside the P8 decoder is skipped, not fatal
        return None


def uv_to_gltf(u: int, v: int, scale: Sequence[float], offset: Sequence[float]) -> tuple[float, float]:
    """Game NORMSHORT2 lane -> glTF texture coordinate: ``n * S + O`` with the shape's own constant.

    ``scale``/``offset`` are the shape's ``(Su, Sv)`` and ``(Ou, Ov)`` from record ``+0x30``,
    exactly what the vertex shader does with c[-89] (see the module docstring).  No V flip.
    """
    return (normshort(u) * float(scale[0]) + float(offset[0]), normshort(v) * float(scale[1]) + float(offset[1]))


def uv_from_gltf(u: float, v: float, scale: Sequence[float], offset: Sequence[float]) -> tuple[int, int]:
    """glTF texture coordinate -> game NORMSHORT2 lane (inverse of :func:`uv_to_gltf`, clamped to the lane)."""
    def axis(value: float, s: float, o: float) -> int:
        if s == 0.0:
            return 0
        return encode_normshort(max(-1.0, min(1.0, (float(value) - o) / s)))
    return (axis(u, float(scale[0]), float(offset[0])), axis(v, float(scale[1]), float(offset[1])))


def uv_in_range(value: float, s: float, o: float) -> bool:
    """True when ``value`` encodes into the NORMSHORT2 lane under (s, o) within half a quantisation step."""
    if s == 0.0:
        return abs(float(value) - o) <= 1e-9
    n = (float(value) - o) / s
    return -1.0 - 0.5 / 32768.0 <= n <= 1.0 + 0.5 / 32767.0


def fit_uv_range(uvs: Sequence[Sequence[float]], scale: Sequence[float], offset: Sequence[float], *,
                 margin: float = 1.001) -> tuple[tuple[float, float], tuple[float, float], tuple[bool, bool]]:
    """Widen a shape's UV constant so every ``uvs`` pair encodes; mirrors the NORMSHORT3 position widening.

    Returns ``(scale, offset, widened)``; an axis whose values all fit keeps its retail constant
    byte for byte, an axis that does not gets ``O = centre`` and ``S = half extent x margin`` of
    the edited values, both rounded to binary32 as the record stores them.
    """
    new_scale = [float(scale[0]), float(scale[1])]
    new_offset = [float(offset[0]), float(offset[1])]
    widened = [False, False]
    for axis in range(2):
        values = [float(uv[axis]) for uv in uvs]
        if not values or all(uv_in_range(value, new_scale[axis], new_offset[axis]) for value in values):
            continue
        low, high = min(values), max(values)
        centre = _float32((low + high) / 2.0)
        half = (high - low) / 2.0
        if half <= 0.0:
            half = abs(new_scale[axis]) or 1e-3
        new_scale[axis] = _float32(half * margin) or new_scale[axis]
        new_offset[axis] = centre
        widened[axis] = True
    return (new_scale[0], new_scale[1]), (new_offset[0], new_offset[1]), (widened[0], widened[1])


def export_model(source: ModelSource, key: str, destination: Path, *,
                 include_textures: bool = True, include_skins: bool = True,
                 include_vertex_colors_as_color0: bool = False,
                 progress: ProgressSink | None = None) -> ExportResult:
    """Write ``destination`` (.gltf) + sibling .bin + README for one model key.

    ``include_vertex_colors_as_color0`` additionally writes the D3DCOLOR lane as ``COLOR_0`` (the
    in-game baked look: Blender multiplies it into the base colour).  The lane is always carried
    as the custom attribute ``_NFL_COLOR`` so it round-trips through import untouched.
    """
    gltf_tool = _tools_module("nfl_scne_gltf")
    progress = progress or (lambda *_a: None)
    progress("Decoding the model", 0, 3)
    resource, decoded, scene = source.parse(key)
    scene_name = str(scene["name"])
    scene_id = scene_contract_id(scene_name, int(resource.outer_index), int(resource.chunk_index),
                                 source.scene_index(resource))
    destination = Path(destination).expanduser()
    if destination.suffix.lower() != ".gltf":
        destination = destination.with_suffix(".gltf")
    bin_path = destination.with_suffix(".bin")
    readme_path = destination.with_name(destination.stem + "-README.txt")

    builder = _GltfBuilder()
    notes: list[str] = []
    shapes_out: list[dict[str, Any]] = []
    submeshes_by_shape: dict[int, list[Mapping[str, Any]]] = {}
    for submesh in scene["submeshes"]:
        submeshes_by_shape.setdefault(int(submesh["shape_index"]), []).append(submesh)

    # materials + textures, under the Stadium Studio contract (nfl2k5_stadium_studio._embed_textures):
    # images are named by the first material that maps them and every material/texture/image carries
    # the canonical nfl2k5_texture_id, so replace_textures_from_gltf accepts this file unchanged.
    material_index_map: dict[int, int] = {}
    texture_count = 0
    textured_material_count = 0
    mapping_rows: list[dict[str, Any]] = []
    image_bytes = 0
    if include_textures:
        progress("Decoding textures", 1, 3)
        mapped_names: dict[int, list[str]] = {}
        for material in scene["materials"]:
            if material.get("texture_index") is not None:
                mapped_names.setdefault(int(material["texture_index"]), []).append(str(material.get("name") or ""))
        texture_slots: dict[int, int] = {}
        texture_alpha: dict[int, bool] = {}
        for material_index, material in enumerate(scene["materials"]):
            texture_index = material.get("texture_index")
            texture_id: str | None = None
            entry: dict[str, Any] = {"name": str(material.get("name") or f"material_{material_index}"),
                                     "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0},
                                     "doubleSided": True}
            if texture_index is not None:
                texture_index = int(texture_index)
                texture_id = texture_contract_id(scene_id, texture_index)
                if texture_index not in texture_slots:
                    texture = scene["embedded_textures"][texture_index] if texture_index < len(scene["embedded_textures"]) else None
                    png = _decode_texture_png(decoded, resource, scene, texture) if texture is not None else None
                    if png is not None:
                        texture_alpha[texture_index] = bool(png["has_alpha"])
                        view = builder.view(png["png"], None)
                        image_bytes += len(png["png"])
                        names = [name for name in mapped_names.get(texture_index, []) if name]
                        image_name = names[0] if names else f"texture{texture_index:04d}"
                        builder.images.append({"name": image_name, "mimeType": "image/png", "bufferView": view,
                                               "extras": {GLTF_TEXTURE_ID_KEY: texture_id,
                                                          "nfl2k5_texture_index": texture_index,
                                                          "nfl2k5_scene_id": scene_id,
                                                          "rgba_sha256": png["rgba_sha256"],
                                                          "width": png["width"], "height": png["height"],
                                                          "format_name": png["format_name"]}})
                        builder.textures.append({"name": image_name, "sampler": 0, "source": len(builder.images) - 1,
                                                 "extras": {GLTF_TEXTURE_ID_KEY: texture_id}})
                        texture_slots[texture_index] = len(builder.textures) - 1
                        texture_count += 1
                        mapping_rows.append({"texture_id": texture_id, "texture_index": texture_index,
                                             "image_index": len(builder.images) - 1, "image_name": image_name,
                                             "width": png["width"], "height": png["height"],
                                             "mapped_material_names": list(mapped_names.get(texture_index, []))})
                if texture_index in texture_slots:
                    entry["pbrMetallicRoughness"]["baseColorTexture"] = {"index": texture_slots[texture_index], "texCoord": 0}
                    textured_material_count += 1
                    if texture_alpha.get(texture_index):
                        entry["alphaMode"] = "MASK"
                        entry["alphaCutoff"] = 0.5
            entry["extras"] = {GLTF_MATERIAL_INDEX_KEY: material_index,
                               "nfl2k5_mapping_status": "mapped_embedded_texture" if texture_index is not None else "unmapped",
                               GLTF_TEXTURE_ID_KEY: texture_id}
            builder.materials.append(entry)
            material_index_map[material_index] = len(builder.materials) - 1

    progress("Writing geometry", 2, 3)
    node_names: dict[int, str] = {}
    for node in scene["nodes"]:
        for shape_index in node.get("matching_shape_indices", []):
            node_names.setdefault(int(shape_index), str(node.get("name") or ""))
    material_names = {index: str(material.get("name") or "") for index, material in enumerate(scene["materials"])}

    for shape in scene["shapes"]:
        lanes = _shape_lanes(scene, shape, decoded)
        if lanes.vertex_count <= 0:
            notes.append(f"{lanes.name}: no vertices; skipped")
            continue
        if lanes.position_format not in ("FLOAT3", "NORMSHORT3"):
            notes.append(f"{lanes.name}: position format {lanes.position_format} is not decodable yet; skipped")
            continue
        positions = read_positions(decoded, shape, lanes)
        flat = [component for vertex in positions for component in vertex]
        minima = [min(flat[i::3]) for i in range(3)]
        maxima = [max(flat[i::3]) for i in range(3)]
        position_view = builder.view(struct.pack(f"<{len(flat)}f", *flat), 34962)
        attributes: dict[str, int] = {
            "POSITION": builder.accessor(position_view, 5126, lanes.vertex_count, "VEC3", minimum=minima, maximum=maxima)}
        shape_report: dict[str, Any] = {"index": lanes.index, "name": lanes.name, "vertex_count": lanes.vertex_count,
                                        "position_format": lanes.position_format, "scale": lanes.scale,
                                        "offset": list(lanes.offset), "submeshes": len(submeshes_by_shape.get(lanes.index, [])),
                                        "transform_count": lanes.transform_count, "morph_count": lanes.morph_count}
        if lanes.normal is not None:
            words = read_lane_u32(decoded, shape, lanes.normal, lanes.vertex_count)
            normals = [_normalise(decode_normpacked3(word)) for word in words]
            flat_n = [c for n in normals for c in n]
            attributes["NORMAL"] = builder.accessor(builder.view(struct.pack(f"<{len(flat_n)}f", *flat_n), 34962),
                                                    5126, lanes.vertex_count, "VEC3")
            shape_report["normals"] = True
        if lanes.texcoord is not None:
            pairs = read_lane_2h(decoded, shape, lanes.texcoord, lanes.vertex_count)
            uvs = [uv_to_gltf(u, v, lanes.uv_scale, lanes.uv_offset) for u, v in pairs]
            flat_uv = [c for uv in uvs for c in uv]
            attributes["TEXCOORD_0"] = builder.accessor(builder.view(struct.pack(f"<{len(flat_uv)}f", *flat_uv), 34962),
                                                        5126, lanes.vertex_count, "VEC2",
                                                        minimum=[min(flat_uv[0::2]), min(flat_uv[1::2])],
                                                        maximum=[max(flat_uv[0::2]), max(flat_uv[1::2])])
            shape_report["uvs"] = True
            shape_report["uv_scale"] = list(lanes.uv_scale)
            shape_report["uv_offset"] = list(lanes.uv_offset)
        if lanes.colour is not None:
            words = read_lane_u32(decoded, shape, lanes.colour, lanes.vertex_count)
            rgba = bytearray()
            for word in words:
                rgba.extend(d3dcolor_to_rgba(word))
            floats = struct.pack(f"<{len(rgba)}f", *[c / 255.0 for c in rgba])
            attributes[COLOUR_ATTRIBUTE] = builder.accessor(builder.view(floats, 34962), 5126, lanes.vertex_count, "VEC4")
            if include_vertex_colors_as_color0:
                attributes["COLOR_0"] = builder.accessor(builder.view(bytes(rgba), 34962), 5121, lanes.vertex_count,
                                                         "VEC4", normalized=True)
            shape_report["colours"] = True
        # the game's own vertex numbering, so an edited file can come back in any order
        index_floats = struct.pack(f"<{lanes.vertex_count}f", *[float(v) for v in range(lanes.vertex_count)])
        attributes[VERTEX_INDEX_ATTRIBUTE] = builder.accessor(builder.view(index_floats, 34962), 5126,
                                                              lanes.vertex_count, "SCALAR")

        skin_index: int | None = None
        skin = decode_skin(decoded, shape, lanes, submeshes_by_shape.get(lanes.index, [])) if include_skins else None
        if skin is not None:
            joints = bytearray()
            weights = bytearray()
            for influences in skin.influences:
                padded = (influences + [(0, 0.0)] * 4)[:4]
                total = sum(weight for _j, weight in padded) or 1.0
                joints.extend(struct.pack("<4H", *[joint for joint, _w in padded]))
                weights.extend(struct.pack("<4f", *[weight / total for _j, weight in padded]))
            attributes["JOINTS_0"] = builder.accessor(builder.view(bytes(joints), 34962), 5123, lanes.vertex_count, "VEC4")
            attributes["WEIGHTS_0"] = builder.accessor(builder.view(bytes(weights), 34962), 5126, lanes.vertex_count, "VEC4")
            inverse = bytearray()
            for transform in skin.transforms:
                x, y, z = transform["absolute"]
                inverse.extend(struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -x, -y, -z, 1))
            inverse_accessor = builder.accessor(builder.view(bytes(inverse), None), 5126, len(skin.transforms), "MAT4")
            joint_base = len(builder.nodes)
            root_joint = joint_base
            for transform in skin.transforms:
                builder.nodes.append({"name": f"{lanes.name}:{transform['name']}",
                                      "translation": list(transform["local"]),
                                      "extras": {"nfl2k5_transform_index": transform["index"],
                                                 "absolute_bind_translation": list(transform["absolute"])}})
            for transform in skin.transforms:
                if transform["parent"] == -1:
                    root_joint = joint_base + transform["index"]
                else:
                    builder.nodes[joint_base + transform["parent"]].setdefault("children", []).append(joint_base + transform["index"])
            builder.skins.append({"name": f"{lanes.name}_skin", "inverseBindMatrices": inverse_accessor,
                                  "skeleton": root_joint, "joints": [joint_base + i for i in range(len(skin.transforms))]})
            skin_index = len(builder.skins) - 1
            shape_report["skin"] = {"joints": len(skin.transforms), "notes": skin.notes}
            notes.extend(f"{lanes.name}: {note}" for note in skin.notes)

        primitives: list[dict[str, Any]] = []
        for submesh in submeshes_by_shape.get(lanes.index, []):
            batches = gltf_tool.decode_batches(decoded, int(submesh["command_offset"]), int(submesh["primary_command_word_count"]))
            for xbox_mode, raw_indices in batches:
                gltf_mode, indices, _conversion = gltf_tool.gltf_topology(xbox_mode, raw_indices)
                if not indices:
                    continue
                index_view = builder.view(struct.pack(f"<{len(indices)}H", *indices), 34963)
                submesh_material = int(submesh["material_index"])
                primitive: dict[str, Any] = {
                    "attributes": dict(attributes),
                    "indices": builder.accessor(index_view, 5123, len(indices), "SCALAR", minimum=[min(indices)], maximum=[max(indices)]),
                    "mode": gltf_mode,
                    "extras": {"nfl2k5_submesh_index": int(submesh["submesh_index"]),
                               GLTF_MATERIAL_INDEX_KEY: submesh_material,
                               # the Stadium Studio / static exporter names for the same facts
                               "source_submesh_index": int(submesh["submesh_index"]),
                               "source_material_index": submesh_material,
                               "source_material_name": material_names.get(submesh_material, ""),
                               "source_auxiliary_index": int(submesh.get("auxiliary_index", 0) or 0),
                               "xbox_primitive_mode": int(xbox_mode),
                               "topology_conversion": _conversion},
                }
                material = material_index_map.get(submesh_material)
                if material is not None:
                    primitive["material"] = material
                primitives.append(primitive)
        if not primitives:
            notes.append(f"{lanes.name}: no drawable submesh; exported as points")
            primitives.append({"attributes": dict(attributes), "mode": 0})
        channels = morph_channels(decoded, lanes)
        if lanes.position_format == "NORMSHORT3":
            position_decode: dict[str, Any] = {
                "equation": "position.xyz = normshort3(register0.xyz) * scale + offset.xyz",
                "serialized_scale_field": "+0x10", "serialized_offset_fields": ["+0x20", "+0x24", "+0x28"],
                "scale": lanes.scale, "offset": list(lanes.offset),
                "shader_instruction": "MAD r4.xyz, v0.xyzz, c[-88].wwww, c[-88].xyzz"}
        else:
            position_decode = {"equation": "position.xyz = little_endian_FLOAT3(register0.xyz)", "identity_decode": True}
        mesh_extras: dict[str, Any] = {"nfl2k5_shape_index": lanes.index, "nfl2k5_vertex_count": lanes.vertex_count,
                                       "nfl2k5_position_format": lanes.position_format,
                                       "nfl2k5_morph_channels": [c["name"] for c in channels],
                                       "nfl2k5_uv_scale": list(lanes.uv_scale), "nfl2k5_uv_offset": list(lanes.uv_offset),
                                       # the Stadium Studio / static exporter names for the same facts
                                       "source_shape_index": lanes.index, "source_record_offset": lanes.record_offset,
                                       "position_format": lanes.position_format, "position_decode": position_decode,
                                       "texcoord_decode": {
                                           "equation": "uv = normshort2(register6.xy) * (Su, Sv) + (Ou, Ov)",
                                           "serialized_fields": ["+0x30", "+0x34", "+0x38", "+0x3C"],
                                           "scale": list(lanes.uv_scale), "offset": list(lanes.uv_offset),
                                           "v_flip": False,
                                           "shader_instruction": "MAD oT0.xy, v6.xyyy, c[-89].xyyy, c[-89].zwww"},
                                       "vertex_attribute_descriptors": shape["attribute_descriptors"],
                                       "transform_record_count": lanes.transform_count,
                                       "morph_channel_record_count": lanes.morph_count}
        builder.meshes.append({"name": lanes.name, "primitives": primitives, "extras": mesh_extras})
        node: dict[str, Any] = {"name": node_names.get(lanes.index) or lanes.name, "mesh": len(builder.meshes) - 1,
                                "extras": {"nfl2k5_shape_index": lanes.index, "source_shape_index": lanes.index}}
        if skin_index is not None:
            node["skin"] = skin_index
        builder.nodes.append(node)
        shape_report["morph_channels"] = [c["name"] for c in channels]
        shapes_out.append(shape_report)

    _require(bool(builder.meshes), f"{scene_name}: nothing exportable (no decodable geometry)")
    # one root scaled to metres; every former root (mesh nodes + skeleton roots) hangs from it
    claimed: set[int] = set()
    for node in builder.nodes:
        claimed.update(node.get("children", []))
    roots = [i for i in range(len(builder.nodes)) if i not in claimed]
    builder.nodes.append({"name": ROOT_NODE_NAME, "scale": [GLTF_UNIT_SCALE] * 3, "children": roots,
                          "extras": {"nfl2k5_scene_name": scene_name}})
    document: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "2K5 Mod Studio Models",
                  "extras": {"schema": SCHEMA_EXPORT, "model_key": key, "scene_name": scene_name,
                             "source_outer_index": int(resource.outer_index), "source_chunk_index": int(resource.chunk_index),
                             "source_scene_index": source.scene_index(resource), "nfl2k5_scene_id": scene_id,
                             "decoded_sha256": _sha256(decoded), "unit_scale": GLTF_UNIT_SCALE,
                             "vertex_index_attribute": VERTEX_INDEX_ATTRIBUTE, "colour_attribute": COLOUR_ATTRIBUTE,
                             "source": {"scene_index": source.scene_index(resource), "outer_index": int(resource.outer_index),
                                        "chunk_index": int(resource.chunk_index), "scene_name": scene_name,
                                        "decoded_sha256": _sha256(decoded)}}},
        "scene": 0,
        "scenes": [{"name": scene_name, "nodes": [len(builder.nodes) - 1]}],
        "nodes": builder.nodes,
        "meshes": builder.meshes,
        "accessors": builder.accessors,
        "bufferViews": builder.buffer_views,
        "buffers": [{"uri": bin_path.name, "byteLength": len(builder.binary)}],
        "extras": {
            "nfl2k5_scene_id": scene_id,
            "nfl2k5_unit_contract": {"authored_unit": "centimetre", "gltf_unit": "metre", "applied_as": "root node scale",
                                     "scale": GLTF_UNIT_SCALE, "buffer_rewritten": False},
            "nfl2k5_texcoord_contract": {
                "equation": "TEXCOORD_0 = normshort2(register 6) * (Su, Sv) + (Ou, Ov); (Su, Sv, Ou, Ov) = shape record +0x30..+0x3C",
                "v_flip": False,
                "proof": "every NFL 2K5 vertex shader routing v6 to oT0: MAD oT0.xy, v6.xyyy, c[-89].xyyy, c[-89].zwww; "
                         "the draw path loads c[-89] from [shape + 0x30] beside the position constant at +0x10/+0x20",
                "per_mesh_extras": ["nfl2k5_uv_scale", "nfl2k5_uv_offset", "texcoord_decode"]},
            "nfl2k5_vertex_colour_contract": {
                "attribute": COLOUR_ATTRIBUTE, "layout": "VEC4 float, r g b a in 0..1, from the D3DCOLOR lane (register 3)",
                "in_game": "baked lighting multiplied into the texture (MUL oD0, v3, c[-90])",
                "color0_written": bool(include_vertex_colors_as_color0)},
        },
    }
    if builder.materials:
        document["materials"] = builder.materials
        document["extras"]["nfl2k5_texture_contract"] = {
            "embedded_image_count": len(builder.images), "material_count": len(builder.materials),
            "textured_material_count": textured_material_count, "geometry_bytes_preserved": False,
            "image_bytes_appended": image_bytes,
            "provenance": ("SCNE embedded P8 base levels decoded by tools/nfl_txtr.texture_to_rgba and PNG-encoded by "
                           "encode_rgba_png at export time; rgba_sha256 on each image is the private stadium cache's PNG key"),
            "sampler_note": "REPEAT wrap; the tiled UVs above need it. Game sampler state is otherwise unproved",
            "texcoord_note": "TEXCOORD_0 is bound (per-shape scale/offset from shape +0x30, shader-proved); "
                             "the Stadium Studio's own export carries positions only",
            "mapping": mapping_rows}
    if builder.textures:
        document["samplers"] = [{"name": "nfl2k5_models_preview", "magFilter": 9729, "minFilter": 9987,
                                 "wrapS": 10497, "wrapT": 10497}]
        document["textures"] = builder.textures
        document["images"] = builder.images
    if builder.skins:
        document["skins"] = builder.skins

    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(document, indent=1) + "\n").encode("utf-8")
    written: list[Path] = []
    try:
        for path, blob in ((destination, payload), (bin_path, bytes(builder.binary))):
            with open(path, "wb") as handle:
                handle.write(blob)
            written.append(path)
        readme_path.write_text(export_readme(scene_name, shapes_out, notes, color0=include_vertex_colors_as_color0),
                               encoding="utf-8", newline="\n")
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    progress("Model exported", 3, 3)
    return ExportResult(key, scene_name, destination, bin_path, readme_path, shapes_out, notes, texture_count)


def export_readme(scene_name: str, shapes: Sequence[Mapping[str, Any]], notes: Sequence[str], *,
                  color0: bool = False) -> str:
    lines = [f"NFL 2K5 model export: {scene_name}", "=" * (20 + len(scene_name)), "",
             "Open the .gltf in Blender (File > Import > glTF 2.0). Units are metres; the game authors",
             "in centimetres, so the root node carries a 0.01 scale. Keep that root.", "",
             "What you can change and bring back with Models > Import:",
             "  * vertex POSITIONS (move, sculpt, proportional edit) -- every mesh here",
             "  * NORMALS and UVs where this export carries them (see the mesh list below)",
             "  * VERTEX COLOURS: the _NFL_COLOR attribute (r g b a, 0..1) is the game's baked lighting;",
             "    in game it multiplies the texture. Paint it in Blender and it comes back (Attributes ticked)",
             "  * textures: edit the embedded images in Blender and, for a stadium, hand this file to the",
             "    Stadiums page's texture write-back (every image carries its nfl2k5_texture_id and is named",
             "    after the material that maps it); or export/import textures on the texture tabs", "",
             "UVs follow the game's own rule: each mesh stores a scale/offset (shape record +0x30), and",
             "uv = lane * scale + offset, with no V flip -- so tiled surfaces (seat rows, crowd, concrete,",
             "ads) legitimately run past 0..1 and repeat; the mesh list gives each mesh's tiling.",
             "Sampler wrap is REPEAT. A UV edit outside a mesh's range widens that mesh's constant on import.", "",
             ("COLOR_0 IS included (the baked in-game look): Blender multiplies it into the base colour, so"
              if color0 else
              "COLOR_0 is NOT included (textures show at full brightness in Blender); tick 'Bake vertex colours"),
             ("textures look darker than the texture files themselves. Untick the option to export without it."
              if color0 else
              "into COLOR_0' on the Models page to see the darker in-game look instead."), "",
             "What you cannot change (the game's allocation is fixed):",
             "  * the number of vertices or triangles, or which triangles exist",
             "  * bones, weights, animations",
             "  * body-type / face morph deltas (their channels are listed but not editable yet)", "",
             "Blender export settings that make the trip back work (File > Export > glTF 2.0):",
             "  * Include > Data > Mesh > tick 'Attributes' (keeps the _NFL_VERTEX_INDEX and _NFL_COLOR lanes;",
             "    without it the importer falls back to nearest-vertex matching, which still works for small moves)",
             "  * Include > Data > Mesh > tick 'Apply Modifiers' only if you added none that change topology",
             "  * do not merge or decimate; keep every mesh; keep names", "",
             "Meshes in this file:"]
    for shape in shapes:
        parts = [f"{int(shape['vertex_count']):,} vertices", f"{int(shape['submeshes'])} submesh(es)",
                 shape["position_format"].lower() + " positions"]
        if shape.get("normals"):
            parts.append("normals")
        if shape.get("uvs"):
            scale = shape.get("uv_scale") or (1.0, 1.0)
            parts.append(f"uvs (tiling x{float(scale[0]):.2f} / x{float(scale[1]):.2f})")
        if shape.get("colours"):
            parts.append("vertex colours (_NFL_COLOR" + (" + COLOR_0)" if color0 else ")"))
        if shape.get("skin"):
            parts.append(f"skin with {shape['skin']['joints']} joints")
        if shape.get("morph_channels"):
            parts.append("morph channels: " + ", ".join(shape["morph_channels"]))
        lines.append(f"  - {shape['name']}: " + ", ".join(parts))
    if notes:
        lines += ["", "Notes:"] + [f"  - {note}" for note in notes]
    lines += ["", "The player body (hi_body) and head (hi_head) are shared base meshes: editing them changes",
              "every player. Per-player looks come from morph weights and textures, not from separate meshes.", ""]
    return "\n".join(lines)



# ------------------------------------------------------------------ glTF reading (import)

_COMPONENT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class GltfFile:
    """A .gltf (+ external/data-URI buffers) or .glb, read just enough for vertex lanes."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        raw = self.path.read_bytes()
        self.buffers: list[bytes] = []
        if raw[:4] == b"glTF":
            _magic, _version, length = struct.unpack_from("<4sII", raw, 0)
            offset = 12
            document: dict[str, Any] | None = None
            binary = b""
            while offset + 8 <= min(length, len(raw)):
                chunk_length, chunk_type = struct.unpack_from("<II", raw, offset)
                chunk = raw[offset + 8: offset + 8 + chunk_length]
                if chunk_type == 0x4E4F534A:      # JSON
                    document = json.loads(chunk.decode("utf-8"))
                elif chunk_type == 0x004E4942:    # BIN
                    binary = chunk
                offset += 8 + chunk_length
            _require(document is not None, f"{self.path.name}: not a glTF binary container")
            assert document is not None
            self.document = document
            for buffer in document.get("buffers", []):
                self.buffers.append(self._load_buffer(buffer, binary))
        else:
            try:
                self.document = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ModelsError(f"{self.path.name}: not a glTF file ({exc})") from exc
            for buffer in self.document.get("buffers", []):
                self.buffers.append(self._load_buffer(buffer, b""))

    def _load_buffer(self, buffer: Mapping[str, Any], glb_binary: bytes) -> bytes:
        uri = buffer.get("uri")
        if uri is None:
            return glb_binary
        if str(uri).startswith("data:"):
            import base64
            head, _sep, payload = str(uri).partition(",")
            _require("base64" in head, f"{self.path.name}: unsupported data URI buffer")
            return base64.b64decode(payload)
        from urllib.parse import unquote
        relative = unquote(str(uri))
        _require("/.." not in relative and not relative.startswith("/") and ":" not in relative,
                 f"{self.path.name}: buffer path escapes the file's folder")
        candidate = self.path.parent / relative
        _require(candidate.is_file(), f"{self.path.name}: missing buffer file {relative} (export as .glb, or keep the .bin beside the .gltf)")
        return candidate.read_bytes()

    def accessor(self, index: int) -> list[tuple[float, ...]]:
        accessors = self.document.get("accessors", [])
        _require(0 <= index < len(accessors), f"{self.path.name}: accessor {index} missing")
        accessor = accessors[index]
        _require("sparse" not in accessor, f"{self.path.name}: sparse accessors are not supported")
        fmt, size = _COMPONENT[int(accessor["componentType"])]
        width = _COUNT[str(accessor["type"])]
        count = int(accessor["count"])
        view = self.document["bufferViews"][int(accessor["bufferView"])]
        data = self.buffers[int(view.get("buffer", 0))]
        stride = int(view.get("byteStride", 0)) or size * width
        base = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
        normalized = bool(accessor.get("normalized", False))
        out: list[tuple[float, ...]] = []
        for i in range(count):
            values = struct.unpack_from(f"<{width}{fmt}", data, base + i * stride)
            if normalized and fmt != "f":
                limit = {"b": 127.0, "B": 255.0, "h": 32767.0, "H": 65535.0, "I": 4294967295.0}[fmt]
                values = tuple(max(-1.0, v / limit) for v in values)
            out.append(tuple(float(v) for v in values))
        return out

    # -- node transforms ------------------------------------------------------
    def world_matrices(self) -> dict[int, list[float]]:
        """Column-major 4x4 world matrix for every node (glTF conventions)."""
        nodes = self.document.get("nodes", [])
        parents: dict[int, int] = {}
        for index, node in enumerate(nodes):
            for child in node.get("children", []):
                parents[int(child)] = index
        cache: dict[int, list[float]] = {}

        def local(node: Mapping[str, Any]) -> list[float]:
            if "matrix" in node:
                return [float(v) for v in node["matrix"]]
            t = [float(v) for v in node.get("translation", (0.0, 0.0, 0.0))]
            q = [float(v) for v in node.get("rotation", (0.0, 0.0, 0.0, 1.0))]
            sc = [float(v) for v in node.get("scale", (1.0, 1.0, 1.0))]
            x, y, z, w = q
            r = [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w),
                 2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w),
                 2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)]
            # column-major: columns are the rotated, scaled basis vectors
            return [r[0] * sc[0], r[1] * sc[0], r[2] * sc[0], 0.0,
                    r[3] * sc[1], r[4] * sc[1], r[5] * sc[1], 0.0,
                    r[6] * sc[2], r[7] * sc[2], r[8] * sc[2], 0.0,
                    t[0], t[1], t[2], 1.0]

        def world(index: int) -> list[float]:
            if index in cache:
                return cache[index]
            own = local(nodes[index])
            parent = parents.get(index)
            result = own if parent is None else _matmul(world(parent), own)
            cache[index] = result
            return result

        for index in range(len(nodes)):
            world(index)
        return cache


def _matmul(a: Sequence[float], b: Sequence[float]) -> list[float]:
    """Column-major 4x4 product a*b."""
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            out[col * 4 + row] = sum(a[k * 4 + row] * b[col * 4 + k] for k in range(4))
    return out


def _transform_point(m: Sequence[float], p: Sequence[float]) -> tuple[float, float, float]:
    x, y, z = p
    return (m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14])


def _transform_direction(m: Sequence[float], d: Sequence[float]) -> tuple[float, float, float]:
    x, y, z = d
    return _normalise((m[0] * x + m[4] * y + m[8] * z, m[1] * x + m[5] * y + m[9] * z, m[2] * x + m[6] * y + m[10] * z))


@dataclass
class EditedMesh:
    name: str
    node_name: str
    positions: list[tuple[float, float, float]]          # game centimetres, scene space
    normals: list[tuple[float, float, float]] | None
    uvs: list[tuple[float, float]] | None
    source_indices: list[int] | None                       # from the _NFL_VERTEX_INDEX lane
    colours: list[tuple[float, float, float, float]] | None = None   # from the _NFL_COLOR lane, 0..1


def read_edited_meshes(gltf: GltfFile) -> list[EditedMesh]:
    """Every mesh in the file with its vertices brought back to game centimetres."""
    document = gltf.document
    matrices = gltf.world_matrices()
    meshes = document.get("meshes", [])
    result: list[EditedMesh] = []
    seen: set[int] = set()
    for node_index, node in enumerate(document.get("nodes", [])):
        mesh_index = node.get("mesh")
        if mesh_index is None or int(mesh_index) in seen:
            continue
        seen.add(int(mesh_index))
        mesh = meshes[int(mesh_index)]
        identity = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        matrix = matrices.get(node_index, identity)
        if node.get("skin") is not None:
            # glTF: a skinned mesh ignores its own node transform; its vertices live in bind space,
            # which any joint's (world x inverseBind) maps to world space (all joints agree at bind).
            skin = document.get("skins", [])[int(node["skin"])]
            joints = [int(j) for j in skin.get("joints", [])]
            ibm_accessor = skin.get("inverseBindMatrices")
            if joints and ibm_accessor is not None:
                inverse = gltf.accessor(int(ibm_accessor))
                matrix = _matmul(matrices.get(joints[0], identity), list(inverse[0]))
            else:
                matrix = identity
        positions: list[tuple[float, float, float]] = []
        normals: list[tuple[float, float, float]] = []
        uvs: list[tuple[float, float]] = []
        indices: list[int] = []
        colours: list[tuple[float, float, float, float]] = []
        have_normals = have_uvs = have_indices = have_colours = True
        loaded: set[int] = set()
        for primitive in mesh.get("primitives", []):
            attributes = primitive.get("attributes", {})
            position_accessor = attributes.get("POSITION")
            if position_accessor is None or int(position_accessor) in loaded:
                continue                              # shared accessor across primitives = same vertices
            loaded.add(int(position_accessor))
            raw_positions = gltf.accessor(int(position_accessor))
            for p in raw_positions:
                x, y, z = _transform_point(matrix, p)
                positions.append((x / GLTF_UNIT_SCALE, y / GLTF_UNIT_SCALE, z / GLTF_UNIT_SCALE))
            if "NORMAL" in attributes and have_normals:
                normals.extend(_transform_direction(matrix, n) for n in gltf.accessor(int(attributes["NORMAL"])))
            else:
                have_normals = False
            if "TEXCOORD_0" in attributes and have_uvs:
                uvs.extend((float(u), float(v)) for u, v in gltf.accessor(int(attributes["TEXCOORD_0"])))
            else:
                have_uvs = False
            if VERTEX_INDEX_ATTRIBUTE in attributes and have_indices:
                indices.extend(int(round(v[0])) for v in gltf.accessor(int(attributes[VERTEX_INDEX_ATTRIBUTE])))
            else:
                have_indices = False
            if COLOUR_ATTRIBUTE in attributes and have_colours:
                # VEC4 float as exported, or Blender's BYTE_COLOR (normalized u8/u16); a VEC3 gets alpha 1
                for row in gltf.accessor(int(attributes[COLOUR_ATTRIBUTE])):
                    padded = (list(row) + [1.0, 1.0, 1.0, 1.0])[:4]
                    colours.append((float(padded[0]), float(padded[1]), float(padded[2]), float(padded[3])))
            else:
                have_colours = False
        if not positions:
            continue
        result.append(EditedMesh(str(mesh.get("name") or f"mesh_{mesh_index}"), str(node.get("name") or ""),
                                 positions, normals if have_normals and len(normals) == len(positions) else None,
                                 uvs if have_uvs and len(uvs) == len(positions) else None,
                                 indices if have_indices and len(indices) == len(positions) else None,
                                 colours if have_colours and len(colours) == len(positions) else None))
    return result


# ------------------------------------------------------------------ fitting

def _strip_blender_suffix(name: str) -> str:
    return re.sub(r"\.\d{3}$", "", name.strip())


def _nearest_map(sources: Sequence[tuple[float, float, float]],
                 targets: Sequence[tuple[float, float, float]]) -> list[int]:
    """For every source point, the index of the nearest target point (uniform-grid search)."""
    if not targets:
        return []
    cell = max(1e-6, max(max(abs(c) for c in p) for p in targets) / 64.0)
    grid: dict[tuple[int, int, int], list[int]] = {}
    for index, p in enumerate(targets):
        grid.setdefault(tuple(int(math.floor(c / cell)) for c in p), []).append(index)  # type: ignore[arg-type]

    def nearest(p: tuple[float, float, float]) -> int:
        cx, cy, cz = (int(math.floor(c / cell)) for c in p)
        best, best_d = -1, math.inf
        for radius in range(0, 4):
            for x in range(cx - radius, cx + radius + 1):
                for y in range(cy - radius, cy + radius + 1):
                    for z in range(cz - radius, cz + radius + 1):
                        if max(abs(x - cx), abs(y - cy), abs(z - cz)) != radius:
                            continue
                        for index in grid.get((x, y, z), ()):
                            q = targets[index]
                            d = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 + (q[2] - p[2]) ** 2
                            if d < best_d:
                                best, best_d = index, d
            if best >= 0:
                return best
        # sparse fallback
        return min(range(len(targets)), key=lambda i: sum((targets[i][k] - p[k]) ** 2 for k in range(3)))
    return [nearest(p) for p in sources]


@dataclass
class ImportShapeReport:
    index: int
    name: str
    matched_by: str
    edited_vertices: int
    source_vertices: int
    covered_vertices: int
    positions_changed: int = 0
    normals_changed: int = 0
    uvs_changed: int = 0
    max_move_cm: float = 0.0
    rescaled: bool = False
    scale_before: float = 0.0
    scale_after: float = 0.0
    notes: list[str] = field(default_factory=list)
    colours_changed: int = 0
    uv_rescaled: bool = False                 # the shape's UV constant at +0x30 was widened


@dataclass
class CompiledModelImport:
    key: str
    name: str
    outer_index: int
    chunk_index: int
    template_span_sha256: str
    decoded_before_sha256: str
    decoded_after_sha256: str
    rebuilt_span: bytes = field(repr=False)
    changed_bytes: int = 0
    shapes: list[ImportShapeReport] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        moved = sum(s.positions_changed for s in self.shapes)
        parts = [f"{self.name}: {moved:,} vertices moved across {len(self.shapes)} mesh(es)"]
        normals = sum(s.normals_changed for s in self.shapes)
        uvs = sum(s.uvs_changed for s in self.shapes)
        colours = sum(s.colours_changed for s in self.shapes)
        if normals:
            parts.append(f"{normals:,} normals")
        if uvs:
            parts.append(f"{uvs:,} UVs")
        if colours:
            parts.append(f"{colours:,} vertex colours")
        if any(s.rescaled for s in self.shapes):
            parts.append("range widened")
        if any(s.uv_rescaled for s in self.shapes):
            parts.append("UV range widened")
        return ", ".join(parts) + f"; {self.changed_bytes:,} bytes change on disc"

    def report(self) -> dict[str, Any]:
        return {"schema": SCHEMA_IMPORT, "model_key": self.key, "scene_name": self.name,
                "outer_index": self.outer_index, "chunk_index": self.chunk_index,
                "template_span_sha256": self.template_span_sha256,
                "decoded_before_sha256": self.decoded_before_sha256, "decoded_after_sha256": self.decoded_after_sha256,
                "rebuilt_span_sha256": _sha256(self.rebuilt_span), "changed_bytes": self.changed_bytes,
                "shapes": [vars(s) for s in self.shapes], "notes": list(self.notes)}


def compile_import(source: ModelSource, key: str, edited_path: Path, *, write_normals: bool = True,
                   write_uvs: bool = False, allow_rescale: bool = True, write_colours: bool = True,
                   progress: ProgressSink | None = None) -> CompiledModelImport:
    """Fit an edited glTF/GLB onto the game's own vertices and rebuild the resource in place.

    Normals, UVs and vertex colours are only ever written for vertices matched exactly (the vertex
    index lane or an identical vertex order); a nearest-vertex fit moves positions only, because
    seam vertices split by Blender would otherwise carry a neighbour's UV or shading normal back.
    UVs are inverted through the shape's own constant (``(uv - O) / S``); an edit outside the
    range widens ``S``/``O`` at record ``+0x30`` per axis when ``allow_rescale`` is on, exactly as
    positions widen ``+0x10``/``+0x20``.  Vertex colours come from the ``_NFL_COLOR`` attribute only.
    """
    progress = progress or (lambda *_a: None)
    progress("Reading the edited model", 0, 4)
    gltf = GltfFile(Path(edited_path))
    edited = read_edited_meshes(gltf)
    _require(bool(edited), f"{Path(edited_path).name}: no meshes with positions")
    progress("Decoding the game's model", 1, 4)
    resource, decoded, scene = source.parse(key)
    template_span = source.span(resource)
    scene_name = str(scene["name"])
    output = bytearray(decoded)
    notes: list[str] = []
    reports: list[ImportShapeReport] = []

    shapes = [shape for shape in scene["shapes"] if int(shape["vertex_count"]) > 0]
    by_name: dict[str, list[Mapping[str, Any]]] = {}
    for shape in shapes:
        by_name.setdefault(str(shape["name"]), []).append(shape)
    used: set[int] = set()
    pairs: list[tuple[Mapping[str, Any], EditedMesh, str]] = []
    unmatched: list[EditedMesh] = []
    for mesh in edited:
        candidates = by_name.get(_strip_blender_suffix(mesh.name)) or by_name.get(_strip_blender_suffix(mesh.node_name)) or []
        chosen = next((c for c in candidates if int(c["index"]) not in used), None)
        if chosen is None:
            unmatched.append(mesh)
            continue
        used.add(int(chosen["index"]))
        pairs.append((chosen, mesh, "name"))
    remaining = [shape for shape in shapes if int(shape["index"]) not in used]
    for mesh in unmatched:
        if not remaining:
            notes.append(f"{mesh.name}: no matching game mesh; ignored")
            continue
        if len(remaining) == 1 and len(unmatched) == 1:
            chosen = remaining.pop(0)
        else:
            # closest vertex count, then order
            chosen = min(remaining, key=lambda s: abs(int(s["vertex_count"]) - len(mesh.positions)))
            remaining.remove(chosen)
        used.add(int(chosen["index"]))
        pairs.append((chosen, mesh, "order"))
        notes.append(f"{mesh.name}: matched to {chosen['name']} by order (rename meshes to the game names to be explicit)")
    _require(bool(pairs), "None of the file's meshes match this model")

    progress("Fitting vertices", 2, 4)
    for shape, mesh, how in pairs:
        lanes = _shape_lanes(scene, shape, decoded)
        original = read_positions(decoded, shape, lanes)
        count = lanes.vertex_count
        report = ImportShapeReport(lanes.index, lanes.name, how, len(mesh.positions), count, 0)
        # source vertex -> list of edited vertices
        groups: dict[int, list[int]] = {}
        if mesh.source_indices is not None and all(0 <= i < count for i in mesh.source_indices):
            for edited_index, source_index in enumerate(mesh.source_indices):
                groups.setdefault(source_index, []).append(edited_index)
            report.matched_by = f"{how} + vertex index lane"
        elif len(mesh.positions) == count:
            groups = {i: [i] for i in range(count)}
            report.matched_by = f"{how} + same vertex order"
            report.notes.append("no vertex index lane in the file; assumed the original vertex order "
                                "(tick Include > Data > Mesh > Attributes when exporting from Blender)")
        else:
            nearest = _nearest_map(original, mesh.positions)
            groups = {i: [nearest[i]] for i in range(count)}
            report.matched_by = f"{how} + nearest vertex"
            report.notes.append(f"vertex count differs ({len(mesh.positions):,} vs {count:,}) and no index lane: "
                                "each game vertex took the nearest edited vertex; expect approximation")
        exact = "nearest" not in report.matched_by
        report.covered_vertices = len(groups)
        if report.covered_vertices < count:
            report.notes.append(f"{count - report.covered_vertices:,} game vertices are absent from the file and keep their original position")

        # new positions (average of the edited copies of each game vertex)
        new_positions = list(original)
        for source_index, members in groups.items():
            xs = [mesh.positions[m] for m in members]
            new_positions[source_index] = tuple(sum(c[a] for c in xs) / len(xs) for a in range(3))  # type: ignore[misc]
        moves = [math.dist(new_positions[i], original[i]) for i in range(count)]
        report.max_move_cm = max(moves) if moves else 0.0
        # A vertex counts as moved only past half a quantisation step of the source lane, so float
        # round-trips through the file (and Blender) never register as edits.
        step = (lanes.scale / 32767.0) if lanes.position_format == "NORMSHORT3" else 1e-4
        moved = [m > step * 0.5 for m in moves]

        base = _stream_base({}, shape, lanes.position_stream)
        if lanes.position_format == "FLOAT3":
            for i in range(count):
                if moved[i]:
                    struct.pack_into("<3f", output, base + i * lanes.position_stride + lanes.position_offset, *new_positions[i])
                    report.positions_changed += 1
        else:
            scale, offset = lanes.scale, lanes.offset
            report.scale_before = scale
            extent = max((abs(new_positions[i][a] - offset[a]) for i in range(count) for a in range(3)), default=0.0)
            if extent > scale * (32767.0 / 32768.0):
                _require(allow_rescale, f"{lanes.name}: the edit leaves the mesh's encodable range and range widening is off")
                centre = tuple((max(p[a] for p in new_positions) + min(p[a] for p in new_positions)) / 2.0 for a in range(3))
                half = max((abs(p[a] - centre[a]) for p in new_positions for a in range(3)), default=1.0)
                scale = float(struct.unpack("<f", struct.pack("<f", half * 1.001))[0]) or scale
                offset = tuple(float(struct.unpack("<f", struct.pack("<f", c))[0]) for c in centre)  # type: ignore[assignment]
                struct.pack_into("<f", output, lanes.record_offset + 0x10, scale)
                struct.pack_into("<3f", output, lanes.record_offset + 0x20, *offset)
                report.rescaled = True
                report.notes.append(f"encodable range widened: scale {lanes.scale:.3f} -> {scale:.3f} cm "
                                    f"(precision {scale / 32767 * 10:.2f} mm per step)")
            report.scale_after = scale
            for i in range(count):
                if not moved[i] and not report.rescaled:
                    continue                      # untouched vertex, untouched lane bytes
                point = new_positions[i] if moved[i] else original[i]
                q = tuple(encode_normshort(max(-1.0, min(1.0, (point[a] - offset[a]) / scale))) for a in range(3))
                at = base + i * lanes.position_stride + lanes.position_offset
                struct.pack_into("<3h", output, at, *q)
                if moved[i]:
                    report.positions_changed += 1

        if write_normals and exact and mesh.normals is not None and lanes.normal is not None:
            nbase = _stream_base({}, shape, lanes.normal[0])
            for source_index, members in groups.items():
                ns = [mesh.normals[m] for m in members]
                n = _normalise(tuple(sum(v[a] for v in ns) / len(ns) for a in range(3)))
                at = nbase + source_index * lanes.normal[2] + lanes.normal[1]
                current = _normalise(decode_normpacked3(struct.unpack_from("<I", output, at)[0]))
                # only a real change of direction (> ~1 degree) is written; re-encoding noise is not
                if sum(current[a] * n[a] for a in range(3)) < 0.99985:
                    struct.pack_into("<I", output, at, encode_normpacked3(*n))
                    report.normals_changed += 1
        elif write_normals and lanes.normal is not None and report.positions_changed:
            report.notes.append("the game's original shading normals were kept"
                                + ("" if exact else " (nearest-vertex fit)") + ("" if mesh.normals is not None else "; the file carries none"))
        if write_uvs and exact and mesh.uvs is not None and lanes.texcoord is not None:
            ubase = _stream_base({}, shape, lanes.texcoord[0])
            raw_uvs = read_lane_2h(decoded, shape, lanes.texcoord, count)
            wanted: dict[int, tuple[float, float]] = {}
            for source_index, members in groups.items():
                us = [mesh.uvs[m] for m in members]
                wanted[source_index] = us[0] if len(us) == 1 else (sum(x[0] for x in us) / len(us), sum(x[1] for x in us) / len(us))
            # every vertex keeps its decoded UV unless the file moved it; the whole set must encode
            targets = [wanted.get(i) or uv_to_gltf(raw_uvs[i][0], raw_uvs[i][1], lanes.uv_scale, lanes.uv_offset)
                       for i in range(count)]
            uv_scale, uv_offset, widened = fit_uv_range(targets, lanes.uv_scale, lanes.uv_offset)
            if any(widened):
                _require(allow_rescale, f"{lanes.name}: the UV edit leaves the mesh's encodable range and range widening is off")
                struct.pack_into(UV_CONSTANT_FORMAT, output, lanes.record_offset + UV_CONSTANT_OFFSET,
                                 uv_scale[0], uv_scale[1], uv_offset[0], uv_offset[1])
                report.uv_rescaled = True
                axes = " and ".join(name for name, flag in zip(("U", "V"), widened) if flag)
                report.notes.append(f"UV range widened on {axes}: scale ({lanes.uv_scale[0]:.4f}, {lanes.uv_scale[1]:.4f}) -> "
                                    f"({uv_scale[0]:.4f}, {uv_scale[1]:.4f}), offset ({lanes.uv_offset[0]:.4f}, {lanes.uv_offset[1]:.4f}) -> "
                                    f"({uv_offset[0]:.4f}, {uv_offset[1]:.4f})")
            for i in range(count):
                if i not in wanted and not any(widened):
                    continue                      # untouched vertex, untouched lane bytes
                qu, qv = uv_from_gltf(targets[i][0], targets[i][1], uv_scale, uv_offset)
                if i not in wanted:               # re-quantise only the axis whose constant moved
                    qu = qu if widened[0] else raw_uvs[i][0]
                    qv = qv if widened[1] else raw_uvs[i][1]
                if raw_uvs[i] != (qu, qv):
                    struct.pack_into("<2h", output, ubase + i * lanes.texcoord[2] + lanes.texcoord[1], qu, qv)
                    if i in wanted:
                        report.uvs_changed += 1
        if write_colours and exact and mesh.colours is not None and lanes.colour is not None:
            cbase = _stream_base({}, shape, lanes.colour[0])
            for source_index, members in groups.items():
                cs = [mesh.colours[m] for m in members]
                word = rgba_to_d3dcolor(*[sum(c[k] for c in cs) / len(cs) * 255.0 for k in range(4)])
                at = cbase + source_index * lanes.colour[2] + lanes.colour[1]
                if struct.unpack_from("<I", output, at)[0] != word:
                    struct.pack_into("<I", output, at, word)
                    report.colours_changed += 1
        reports.append(report)
        notes.extend(f"{report.name}: {note}" for note in report.notes)

    changed = sum(1 for a, b in zip(decoded, output) if a != b)
    _require(changed > 0, "The edited file does not change any vertex of this model")
    progress("Rebuilding the compressed resource", 3, 4)
    fill = _tools_module("nfl_vc_lz_fill")
    try:
        rebuilt, info = fill.rebuild_fixed_span_filled(template_span, bytes(output), encoder="auto")
    except Exception as exc:  # noqa: BLE001 - the tool raises TxtrError with the size arithmetic
        raise ModelsError(
            f"{scene_name}: the edited model no longer fits the space the disc reserves for it ({exc}). "
            "Edits that keep unmoved vertices exactly where they were compress best; try a smaller or smoother change."
        ) from exc
    compiled = CompiledModelImport(key, scene_name, int(resource.outer_index), int(resource.chunk_index),
                                   _sha256(template_span), _sha256(decoded), _sha256(bytes(output)), rebuilt,
                                   changed, reports, notes)
    compiled.notes.append(f"compressed stream {info.filled_bytes:,} of {info.stored_size:,} bytes; wrapper identical: {info.wrapper_identical}")
    progress("Ready to write", 4, 4)
    return compiled


# ------------------------------------------------------------------ writing a disc copy

def _xdvdfs_pack_entries(descriptor: int, size: int) -> dict[str, Any]:
    xiso = _tools_module("nfl_uniform_color_xiso_direct_patch")
    entries, _directory = xiso.parse_xdvdfs(descriptor, size)
    packs: dict[str, Any] = {}
    for path, entry in entries.items():
        parts = str(path).replace("\\", "/").split("/")
        if len(parts) >= 2 and parts[-2].lower() == ARCHIVE_NAME:
            packs[parts[-1]] = entry
    _require(bool(packs), "This disc image has no vc_53450030 pack archive in its file table")
    return packs


def image_spans(source: ModelSource, compiled: CompiledModelImport, descriptor: int, size: int) -> list[tuple[int, int, int]]:
    """(absolute image offset, offset within the resource span, length) for every pack segment."""
    resource = source.resource(compiled.key)
    packs = _xdvdfs_pack_entries(descriptor, size)
    spans: list[tuple[int, int, int]] = []
    consumed = 0
    for segment in source.archive_segments(resource):
        entry = packs.get(str(segment.pack_name))
        _require(entry is not None, f"pack file vc_53450030/{segment.pack_name} is not in this disc image")
        assert entry is not None
        _require(segment.pack_offset + segment.size <= int(entry.size), "resource span exceeds its pack file on this disc")
        spans.append((int(entry.byte_offset) + int(segment.pack_offset), consumed, int(segment.size)))
        consumed += int(segment.size)
    _require(consumed == len(compiled.rebuilt_span), "resource span arithmetic changed")
    return spans


def write_import_copy(source: ModelSource, compiled: CompiledModelImport, source_image: Path, target_image: Path,
                      *, overwrite: bool = False, progress: ProgressSink | None = None) -> dict[str, Any]:
    """Copy ``source_image`` to ``target_image`` and write the rebuilt resource into the copy."""
    import shutil
    progress = progress or (lambda *_a: None)
    source_image, target_image = Path(source_image), Path(target_image)
    _require(source_image.is_file(), f"source image is not a file: {source_image}")
    _require(not _same_file(source_image, target_image), "The copy must not be the source image")
    _require(overwrite or not target_image.exists(), f"{target_image} already exists")
    template_span = source.span(source.resource(compiled.key))
    _require(_sha256(template_span) == compiled.template_span_sha256, "The model source changed since the import was compiled")
    progress("Copying the disc image", 0, 3)
    shutil.copyfile(source_image, target_image)
    flags = os.O_RDWR | getattr(os, "O_BINARY", 0)
    descriptor = os.open(target_image, flags)
    receipt: dict[str, Any]
    try:
        size = os.fstat(descriptor).st_size
        progress("Locating the resource on the disc", 1, 3)
        spans = image_spans(source, compiled, descriptor, size)
        state = []
        for absolute, inner, length in spans:
            current = platform_compat.pread(descriptor, length, absolute)
            if current == template_span[inner: inner + length]:
                state.append("retail")
            elif current == compiled.rebuilt_span[inner: inner + length]:
                state.append("applied")
            else:
                raise ModelsError("This disc's copy of the model is neither the original nor this edit; refusing to write over it")
        progress("Writing the edited model", 2, 3)
        for absolute, inner, length in spans:
            written = platform_compat.pwrite(descriptor, compiled.rebuilt_span[inner: inner + length], absolute)
            _require(written == length, "short write into the disc copy")
            _require(platform_compat.pread(descriptor, length, absolute) == compiled.rebuilt_span[inner: inner + length],
                     "read-back differs after the write")
        os.fsync(descriptor)
        receipt = {"schema": SCHEMA_IMPORT + "-receipt", "source_image": str(source_image), "target_image": str(target_image),
                   "spans": [{"image_offset": a, "length": n, "was": s} for (a, _i, n), s in zip(spans, state)],
                   **compiled.report()}
    finally:
        os.close(descriptor)
    receipt_path = target_image.with_name(target_image.name.split(".")[0] + f".{compiled.name}.models-receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    receipt["receipt_path"] = str(receipt_path)
    progress("Edited model written", 3, 3)
    return receipt


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.abspath(a) == os.path.abspath(b)

__all__ = [
    "GROUP_LABELS", "GROUP_ORDER", "ModelEntry", "safe_file_name", "ModelSource", "ModelsError", "ExportResult",
    "export_model", "export_readme", "group_for_name", "model_key", "parse_model_key",
    "decode_normpacked3", "encode_normpacked3", "normshort", "encode_normshort", "uv_to_gltf", "uv_from_gltf",
    "uv_in_range", "fit_uv_range", "read_uv_constant", "d3dcolor_to_rgba", "rgba_to_d3dcolor",
    "scene_contract_id", "texture_contract_id", "GLTF_TEXTURE_ID_KEY", "GLTF_MATERIAL_INDEX_KEY", "ROOT_NODE_NAME",
    "COLOUR_ATTRIBUTE", "VERTEX_INDEX_ATTRIBUTE", "UV_CONSTANT_OFFSET",
    "GltfFile", "EditedMesh", "read_edited_meshes", "ImportShapeReport", "CompiledModelImport", "compile_import",
    "image_spans", "write_import_copy",
]
