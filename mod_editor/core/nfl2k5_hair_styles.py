"""Hair styles (b775 job hs1): new player hair models in NEW slots, chosen per player by a roster byte.

EXPERIMENTAL / UNWITNESSED until Noah's own games.

Noah 10/15 and 10/17: add hair models, never replace: "find out a way to have more than one hair model option" and
"Hairstyles, you can research and add some new models you create." Retail NFL 2K5 has exactly one optional hair mesh
(``HAIR_dreads``, switched on by roster +0x18 bit 0). This feature keeps it, every Dreads bit and every retail byte of
the two player scenes, and ADDS seven meshes and nine textures:

* the close-up head (``hi_head``, outer 3 chunk 115) and the distant body (``lo_body``, chunk 113) each get seven new
  materials ``HAIR_<mesh>`` (hidden until a player asks for one), seven submeshes copied from the dreads submesh (same
  head/neck skin palette, plus the thorax for long hair), their push words, their vertices at the end of every vertex
  stream, and their names. Each addition is inserted right after the table or stream it extends, and every
  self-relative pointer the game's own scene loader relocates (pinned census in ``pointer_fields.json``, taken by
  running 0x45BC0 under Unicorn) is moved with it. ``strip_scene`` undoes the growth byte for byte;
* nine 64 x 64 P8 hair textures are appended to outer 3 as raw TXTR resources (``hair_locs_dark`` ...), found by
  name at run time exactly as retail finds ``dread`` (0x449E0 with no container: the resident global.iff);
* roster record byte +0x0D, low nibble = hair style (the Studio field ``hair_style``; zero in every retail and
  SOFTDRINK record). 0 = retail (the Dreads bit decides), 1 = the retail dreads, 2..12 = the styles below, 13 = no
  hair model even with the Dreads bit (players who have cut their locs), 14..15 = reserved (behave like 0);
* a code cave replaces the 45-byte dreads block of the player builder (0x8F5B9): style 0 tests the Dreads bit and
  runs the original block, style 1 runs the original block, a new style looks its texture up by name and shows
  ``HAIR_<mesh>`` through the same routine retail uses (0x8E3F0). The cave first checks that the model row is lo_body
  or hi_head and that the instance carries exactly the grown material count, so a scene without the added slots never
  shows anything. Model instances are refilled from the hidden templates before every build (0x8F8EC -> 0x2E120), so
  a style never carries over to the next player.

Composition: Modern helmets writes the same two scenes in place, before this step; its classifier strips the hair
growth first (``strip_scene``), so the two commute. The Guardian overlay pins absolute spans of outer 3 and is refused
together with hair styles (both grow the player models).
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import nfl2k5_models as models

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_hair_styles"
GEOMETRY_PATH = DATA_DIR / "geometry.json"
POINTERS_PATH = DATA_DIR / "pointer_fields.json"
PINS_PATH = DATA_DIR / "pins.json"
ART_DIR = DATA_DIR / "art"
SCHEMA = "nfl2k5_hair_styles/v1"
GEOMETRY_SCHEMA = "nfl2k5_hair_styles/geometry/v1"
POINTERS_SCHEMA = "nfl2k5_hair_styles/pointer_fields/v1"
LABEL = BUILD_CAPTION = UI_LABEL = "Hair styles (new hair models per player)"
EVIDENCE = "EXPERIMENTAL / UNWITNESSED"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Adds seven hair models (long locs, short twists, long flowing hair, afro puff, braids, "
    "bun, mullet) and their textures to the player models, next to the retail dreads, and the code that shows the one "
    "a player's 'Hair style' roster field asks for. Retail dreads and every Dreads bit stay as they are; players with "
    "hair style 0 look exactly like retail. Needs a disc image.")

OUTER = 3
HI, LO = "o3c115", "o3c113"
KEYS = (LO, HI)
DREAD_CHUNK = 186
# the seven added meshes, in slot order (material index = retail count + slot)
MESHES = ("long_locs", "short_twists", "long_flow", "afro_puff", "braids", "bun", "mullet")
K = len(MESHES)
# the nine added textures (TXTR resource names are "hair_" + key)
TEXTURES = ("locs_dark", "locs_light", "twists_dark", "braids_dark", "strands_blond", "strands_brown",
            "strands_black", "curls_dark", "bun_dark")


@dataclass(frozen=True)
class Style:
    index: int
    key: str
    label: str
    mesh: str
    texture: str


STYLES = (
    Style(2, "long_locs", "Long locs", "long_locs", "locs_dark"),
    Style(3, "short_twists", "Short twists", "short_twists", "twists_dark"),
    Style(4, "long_flow_blond", "Long hair, blond", "long_flow", "strands_blond"),
    Style(5, "long_flow_brown", "Long hair, brown", "long_flow", "strands_brown"),
    Style(6, "afro_puff", "Afro puff", "afro_puff", "curls_dark"),
    Style(7, "braids", "Braids", "braids", "braids_dark"),
    Style(8, "bun", "Bun", "bun", "bun_dark"),
    Style(9, "mullet_brown", "Mullet, brown", "mullet", "strands_brown"),
    Style(10, "mullet_blond", "Mullet, blond", "mullet", "strands_blond"),
    Style(11, "long_locs_light", "Long locs, light ends", "long_locs", "locs_light"),
    Style(12, "long_flow_black", "Long hair, black", "long_flow", "strands_black"),
)
MAX_STYLE = 12
#: style 13 draws no hair model at all, even for a player with the Dreads bit (players who have cut their locs)
NONE_STYLE = 13
STYLE_LABELS = (("Retail (Dreads bit)", "Retail dreads") + tuple(s.label for s in STYLES)
                + ("No hair model",) + tuple(f"Reserved {i}" for i in range(NONE_STYLE + 1, 16)))
STYLE_BY_INDEX = {s.index: s for s in STYLES}
STYLE_BY_KEY = {s.key: s for s in STYLES}

# retail shape facts per scene (PROVED on the USA disc; Modern helmets keeps every one of them)
RETAIL = {HI: dict(materials=60, submeshes=65, vertices=11727, streams=2),
          LO: dict(materials=203, submeshes=111, vertices=5065, streams=3)}
#: palette slot -> joint of the added submeshes: the retail dreads' head and neck slots, plus the thorax
PALETTE = {HI: {"head": (14, 2), "neck": (22, 1), "thorax": (21, 0)},
           LO: {"head": (23, 12), "neck": (22, 11), "thorax": (24, 10)}}
INSERT_ALIGN = 128


class HairStylesError(ValueError):
    pass


def require(condition: object, message: str) -> None:
    if not condition:
        raise HairStylesError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tool(name: str):
    return models._tools_module(name)


def align(value: int, to: int = INSERT_ALIGN) -> int:
    return (value + to - 1) // to * to


# ------------------------------------------------------------------------------------------------ data

def _load_json(path: Path, schema: str) -> dict[str, Any]:
    require(path.is_file(), f"hair styles data missing: {path.name}")
    stat = path.stat()
    return _cached_json(str(path), stat.st_size, stat.st_mtime_ns, schema)


@lru_cache(maxsize=8)
def _cached_json(path: str, size: int, mtime_ns: int, schema: str) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    require(document.get("schema") == schema, f"{Path(path).name} has another schema")
    return document


def load_geometry(path: Path | None = None) -> dict[str, Any]:
    document = _load_json(GEOMETRY_PATH if path is None else Path(path), GEOMETRY_SCHEMA)
    require(tuple(document["meshes"]) == MESHES, "the geometry's mesh list differs from the catalogue")
    return document


def load_pointer_fields() -> dict[str, list[int]]:
    document = _load_json(POINTERS_PATH, POINTERS_SCHEMA)
    return {key: [int(v) for v in document["scenes"][key]] for key in KEYS}


def load_pins(path: Path | None = None) -> dict[str, Any]:
    return _load_json(PINS_PATH if path is None else Path(path), SCHEMA)


def available() -> bool:
    """The shipped geometry, art and pointer census agree with the pins (the build step's precondition)."""
    try:
        pins = load_pins()
        load_geometry()
        load_pointer_fields()
        return (pins["geometry_sha256"] == sha(GEOMETRY_PATH.read_bytes())
                and pins["pointer_fields_sha256"] == sha(POINTERS_PATH.read_bytes())
                and all(pins["art_sha256"][k] == sha((ART_DIR / f"{k}.png").read_bytes()) for k in TEXTURES))
    except (HairStylesError, OSError, KeyError, ValueError):
        return False


def texture_name(key: str) -> str:
    return "hair_" + key


def art_rgba(key: str) -> bytes:
    from PIL import Image
    path = ART_DIR / f"{key}.png"
    require(path.is_file(), f"hair texture art missing: {path.name}")
    with Image.open(path) as image:
        require(image.size == (64, 64), f"{path.name} must be 64 x 64")
        return image.convert("RGBA").tobytes()


def _part(document: Mapping[str, Any], key: str, mesh: str) -> tuple[bytes, list[int]]:
    item = document["scenes"][key]["parts"][mesh]
    records = base64.b64decode(item["records"])
    raw = base64.b64decode(item["strip"])
    return records, list(struct.unpack(f"<{len(raw) // 2}H", raw))


# ------------------------------------------------------------------------------------------------ scene layout

@dataclass
class Layout:
    key: str
    size: int
    descriptor: int
    materials: int              # material table offset
    material_count: int
    shape: int                  # shape record offset
    submeshes: int
    submesh_count: int
    vertex_count: int
    streams: list[tuple[int, int]]   # (offset, stride) in stream order
    command_end: int
    names: dict[int, str]            # material index -> name
    submesh_rows: list[dict[str, Any]]


def _rel(buf: bytes, at: int) -> int | None:
    value = struct.unpack_from("<i", buf, at)[0]
    return None if value == 0 else at + value - 1


def _wide(buf: bytes, at: int) -> str:
    end = at
    while end + 1 < len(buf) and buf[end:end + 2] != b"\0\0":
        end += 2
    return bytes(buf[at:end]).decode("utf-16le", "replace")


def layout(key: str, decoded: bytes) -> Layout:
    """The player scene's tables, read straight from its own pointers (works on retail and grown scenes)."""
    d = bytes(decoded)
    require(len(d) > 0x200 and d[12:16] == b"SCNE", f"{key}: not a scene")
    descriptor = _rel(d, 0x14)
    require(descriptor is not None and 0 < descriptor < len(d), f"{key}: no descriptor")
    material_count = struct.unpack_from("<I", d, descriptor + 0x1C)[0]
    materials = _rel(d, descriptor + 0x20)
    shape_count = struct.unpack_from("<I", d, descriptor + 0x2C)[0]
    shape = _rel(d, descriptor + 0x30)
    require(materials is not None and shape is not None and shape_count == 1, f"{key}: the player scene has one shape")
    vertex_count = struct.unpack_from("<H", d, shape + 0x4C)[0]
    submesh_count = struct.unpack_from("<H", d, shape + 0x54)[0]
    submeshes = _rel(d, shape + 0x70)
    require(submeshes is not None, f"{key}: no submesh table")
    streams = []
    for st in range(8):
        base = _rel(d, shape + 0xD4 + 4 * st)
        if base is None:
            break
        stride = struct.unpack_from("<H", d, shape + 0xC4 + 2 * st)[0]
        require(0 < stride <= 64, f"{key}: stream {st} has no stride")
        streams.append((base, stride))
    names = {}
    for i in range(material_count):
        at = _rel(d, materials + 0x80 * i)
        names[i] = _wide(d, at) if at is not None else ""
    rows = []
    command_end = 0
    for i in range(submesh_count):
        rec = submeshes + 0x80 * i
        material = struct.unpack_from("<H", d, rec)[0]
        command = _rel(d, rec + 0x78)
        words = struct.unpack_from("<H", d, rec + 0x7C)[0]
        rows.append(dict(index=i, record=rec, material=material, name=names.get(material, ""),
                         command=command, words=words))
        if command is not None:
            command_end = max(command_end, command + 4 * words)
    return Layout(key, len(d), descriptor, materials, material_count, shape, submeshes, submesh_count, vertex_count,
                  streams, command_end, names, rows)


def scene_state(key: str, decoded: bytes) -> str:
    """retail-shaped | grown | foreign (the hair growth only; Modern helmets' in-place writes are not judged here)."""
    try:
        lay = layout(key, decoded)
    except (HairStylesError, struct.error, IndexError, KeyError):
        return "foreign"
    base = RETAIL[key]
    if (lay.material_count, lay.submesh_count, lay.vertex_count) == (base["materials"], base["submeshes"],
                                                                      base["vertices"]):
        return "retail" if "HAIR_dreads" in lay.names.values() else "foreign"
    if lay.material_count == base["materials"] + K and lay.submesh_count == base["submeshes"] + K:
        added = [lay.names[base["materials"] + k] for k in range(K)]
        return "grown" if added == [material_name(m) for m in MESHES] else "foreign"
    return "foreign"


def material_name(mesh: str) -> str:
    return "HAIR_" + mesh


# ------------------------------------------------------------------------------------------------ growth

@dataclass
class Plan:
    """Where the growth goes, in the coordinates of the retail-shaped scene."""
    inserts: list[tuple[int, bytes]]        # (offset before which the bytes go, bytes) sorted by offset

    def shift(self, offset: int) -> int:
        return offset + sum(len(data) for at, data in self.inserts if at <= offset)


def _template(lay: Layout, decoded: bytes) -> tuple[bytes, bytes]:
    names = {v: k for k, v in lay.names.items()}
    require("HAIR_dreads" in names, f"{lay.key}: no HAIR_dreads material")
    material = names["HAIR_dreads"]
    rows = [r for r in lay.submesh_rows if r["material"] == material]
    require(len(rows) == 1, f"{lay.key}: HAIR_dreads is not one submesh")
    mat = bytes(decoded[lay.materials + 0x80 * material: lay.materials + 0x80 * (material + 1)])
    sub = bytes(decoded[rows[0]["record"]: rows[0]["record"] + 0x80])
    return mat, sub


def _remap(key: str, template: bytes) -> bytes:
    """The dreads submesh record's palette fields with the thorax slot added."""
    rec = bytearray(template)
    slots = PALETTE[key]
    first, last = struct.unpack_from("<HH", rec, 4)
    for _name, (slot, joint) in slots.items():
        current = struct.unpack_from("<H", rec, 8 + 2 * slot)[0]
        require(current in (0x7F7F, joint), f"{key}: palette slot {slot} is taken")
        struct.pack_into("<H", rec, 8 + 2 * slot, joint)
        first, last = min(first, slot), max(last, slot)
    struct.pack_into("<HH", rec, 4, first, last)
    return bytes(rec)


def build_plan(key: str, decoded: bytes, document: Mapping[str, Any]) -> tuple[Plan, dict[str, Any]]:
    """The byte insertions that add the K hair meshes to a retail-shaped scene (pointers are not yet moved)."""
    from .nfl2k5_modern_helmets import encode_strip
    lay = layout(key, decoded)
    base = RETAIL[key]
    require((lay.material_count, lay.submesh_count, lay.vertex_count) == (base["materials"], base["submeshes"],
                                                                        base["vertices"]),
            f"{key}: the scene is not the retail-shaped player scene")
    require(len(lay.streams) == base["streams"], f"{key}: the vertex streams changed")
    expect = document["scenes"][key]
    require(expect["vertex_count"] == lay.vertex_count and expect["strides"] == [s for _o, s in lay.streams],
            f"{key}: the geometry was authored for another vertex layout")
    record_size = sum(s for _o, s in lay.streams)
    mat_t, sub_t = _template(lay, decoded)
    sub_t = _remap(key, sub_t)
    # vertices and push words
    per_stream = [bytearray() for _ in lay.streams]
    words: list[int] = []
    part_rows = []
    first = lay.vertex_count
    for mesh in MESHES:
        records, strip = _part(document, key, mesh)
        require(len(records) % record_size == 0 and records, f"{key}/{mesh}: vertex records are not whole")
        count = len(records) // record_size
        require(strip and max(strip) < count, f"{key}/{mesh}: strip index out of range")
        for v in range(count):
            at = v * record_size
            for s, (_o, stride) in enumerate(lay.streams):
                per_stream[s] += records[at:at + stride]
                at += stride
        mesh_words = encode_strip([first + i for i in strip])
        part_rows.append(dict(mesh=mesh, first_vertex=first, vertices=count, word_offset=len(words),
                              words=len(mesh_words), strip=len(strip)))
        words += mesh_words
        first += count
    added = first - lay.vertex_count
    require(first < 0xFFFF, f"{key}: too many vertices")
    # names (UTF-16, appended at the very end of the scene)
    name_blob = bytearray()
    name_at = []
    for mesh in MESHES:
        name_at.append(len(name_blob))
        name_blob += (material_name(mesh) + "\0").encode("utf-16le")
    inserts: list[tuple[int, bytes]] = []
    material_offset = lay.materials + 0x80 * lay.material_count
    submesh_offset = lay.submeshes + 0x80 * lay.submesh_count
    inserts.append((material_offset, b"M" * (0x80 * K)))          # placeholders, filled after the plan is known
    inserts.append((submesh_offset, b"S" * (0x80 * K)))
    inserts.append((lay.command_end, struct.pack(f"<{len(words)}I", *words).ljust(align(4 * len(words)), b"\0")))
    for s, (offset, stride) in enumerate(lay.streams):
        end = offset + lay.vertex_count * stride
        inserts.append((end, bytes(per_stream[s]).ljust(align(len(per_stream[s])), b"\0")))
    inserts.append((lay.size, bytes(name_blob).ljust(align(len(name_blob)), b"\0")))
    require(len({at for at, _ in inserts}) == len(inserts), f"{key}: two insertions at one offset")
    plan = Plan(sorted(inserts, key=lambda t: t[0]))
    info = dict(material_offset=material_offset, submesh_offset=submesh_offset, command_end=lay.command_end,
                name_at=name_at, parts=part_rows, added_vertices=added, words=len(words),
                material_template=mat_t, submesh_template=sub_t)
    return plan, info


def grow_scene(key: str, decoded: bytes, document: Mapping[str, Any] | None = None,
               pointer_fields: Sequence[int] | None = None) -> tuple[bytes, dict[str, Any]]:
    """The retail-shaped scene with the hair meshes added; every relocated pointer moved with its target."""
    document = load_geometry() if document is None else document
    fields = load_pointer_fields()[key] if pointer_fields is None else list(pointer_fields)
    d = bytes(decoded)
    lay = layout(key, d)
    plan, info = build_plan(key, d, document)
    # every pinned pointer field must resolve inside the scene (refuses a foreign layout)
    targets = {}
    for field in fields:
        target = _rel(d, field)
        require(target is not None and 0 <= target <= len(d), f"{key}: pointer field {field:#x} does not resolve")
        targets[field] = target
    out = bytearray()
    cursor = 0
    for at, data in plan.inserts:
        out += d[cursor:at]
        out += data
        cursor = at
    out += d[cursor:]
    for field, target in targets.items():
        new_field, new_target = plan.shift(field), plan.shift(target)
        struct.pack_into("<i", out, new_field, new_target - new_field + 1)
    # fill the material and submesh records
    material_at = plan.shift(info["material_offset"]) - 0x80 * K
    submesh_at = plan.shift(info["submesh_offset"]) - 0x80 * K
    command_at = plan.shift(info["command_end"]) - align(4 * info["words"])
    names_at = len(out) - align(sum(2 * (len(material_name(m)) + 1) for m in MESHES))
    for k, mesh in enumerate(MESHES):
        rec = bytearray(info["material_template"])
        at = material_at + 0x80 * k
        struct.pack_into("<i", rec, 0, names_at + info["name_at"][k] - at + 1)
        out[at:at + 0x80] = rec
        part = info["parts"][k]
        rec = bytearray(info["submesh_template"])
        at = submesh_at + 0x80 * k
        struct.pack_into("<H", rec, 0, lay.material_count + k)
        word_at = command_at + 4 * part["word_offset"]
        struct.pack_into("<i", rec, 0x78, word_at - (at + 0x78) + 1)
        struct.pack_into("<HH", rec, 0x7C, part["words"], 0)
        out[at:at + 0x80] = rec
    # counts
    struct.pack_into("<I", out, plan.shift(lay.descriptor + 0x1C), lay.material_count + K)
    shape = plan.shift(lay.shape)
    struct.pack_into("<H", out, shape + 0x54, lay.submesh_count + K)
    struct.pack_into("<H", out, shape + 0x4C, lay.vertex_count + info["added_vertices"])
    grown = bytes(out)
    require(scene_state(key, grown) == "grown", f"{key}: the grown scene does not read back")
    receipt = {"key": key, "size_before": len(d), "size_after": len(grown), "growth": len(grown) - len(d),
               "added_vertices": info["added_vertices"], "push_words": info["words"],
               "parts": [{k: v for k, v in p.items()} for p in info["parts"]],
               "inserts": [{"at": at, "bytes": len(data)} for at, data in plan.inserts]}
    return grown, receipt


def strip_scene(key: str, grown: bytes, document: Mapping[str, Any] | None = None,
                pointer_fields: Sequence[int] | None = None) -> bytes:
    """The exact retail-shaped scene a grown scene came from (the growth removed, every pointer moved back)."""
    document = load_geometry() if document is None else document
    fields = load_pointer_fields()[key] if pointer_fields is None else list(pointer_fields)
    g = bytes(grown)
    require(scene_state(key, g) == "grown", f"{key}: the scene carries no hair growth")
    lay = layout(key, g)
    base = RETAIL[key]
    record_size = sum(s for _o, s in lay.streams)
    added = 0
    words = 0
    from .nfl2k5_modern_helmets import encode_strip
    first = base["vertices"]
    for mesh in MESHES:
        records, strip = _part(document, key, mesh)
        count = len(records) // record_size
        words += len(encode_strip([first + i for i in strip]))
        first += count
        added += count
    require(lay.vertex_count == base["vertices"] + added, f"{key}: the grown vertex count differs from the geometry")
    name_bytes = align(sum(2 * (len(material_name(m)) + 1) for m in MESHES))
    # the insert positions in the grown scene, then in the original
    old_rows = [r for r in lay.submesh_rows[:base["submeshes"]]]
    grown_inserts = [
        (lay.materials + 0x80 * base["materials"], 0x80 * K),
        (lay.submeshes + 0x80 * base["submeshes"], 0x80 * K),
        (max(r["command"] + 4 * r["words"] for r in old_rows if r["command"] is not None), align(4 * words)),
    ]
    for offset, stride in lay.streams:
        grown_inserts.append((offset + base["vertices"] * stride, align(added * stride)))
    grown_inserts.append((len(g) - name_bytes, name_bytes))
    grown_inserts.sort()
    pieces, cursor, removed = [], 0, 0
    original_inserts = []
    for at, size in grown_inserts:
        require(at >= cursor, f"{key}: overlapping growth")
        pieces.append(g[cursor:at])
        original_inserts.append((at - removed, size))
        removed += size
        cursor = at + size
    pieces.append(g[cursor:])
    out = bytearray(b"".join(pieces))
    plan = Plan([(at, b"\0" * size) for at, size in original_inserts])
    for field in fields:
        target_grown = _rel(g, plan.shift(field))
        require(target_grown is not None, f"{key}: pointer field {field:#x} lost")
        struct.pack_into("<i", out, field, _unshift(original_inserts, target_grown) - field + 1)
    descriptor = _rel(out, 0x14)
    struct.pack_into("<I", out, descriptor + 0x1C, base["materials"])
    shape = _rel(out, descriptor + 0x30)
    struct.pack_into("<H", out, shape + 0x54, base["submeshes"])
    struct.pack_into("<H", out, shape + 0x4C, base["vertices"])
    return bytes(out)


def _unshift(inserts: Sequence[tuple[int, int]], grown_offset: int) -> int:
    """Original offset of the byte at ``grown_offset`` of the grown scene (never one of the added bytes)."""
    shift = 0
    for at, size in inserts:
        start = at + shift
        if grown_offset < start:
            break
        require(grown_offset >= start + size, "a pointer targets the added bytes")
        shift += size
    return grown_offset - shift


def retail_shaped(key: str, decoded: bytes) -> bytes:
    """The scene with any hair growth removed (what Modern helmets and the other player-model writers judge)."""
    return strip_scene(key, decoded) if scene_state(key, decoded) == "grown" else bytes(decoded)


# ------------------------------------------------------------------------------------------------ resources

def _chunks(payload: bytes) -> list:
    return _tool("nfl_txtr").parse_chunks(bytes(payload), allow_trailing=True)


def _chunk_span(payload: bytes, chunk) -> bytes:
    return bytes(payload[chunk.offset:chunk.offset + 32 + chunk.stored_size])


def decode_span(span: bytes) -> bytes:
    tx = _tool("nfl_txtr")
    return tx.decode_chunk(bytes(span), tx.parse_chunks(bytes(span), allow_trailing=True)[0])[0]


def compress_scene(template_span: bytes, decoded: bytes) -> bytes:
    """A compressed SCNE resource for ``decoded`` with the template's VC-LZ stream parameters and a proved in-place
    decode scratch (the title reads the stored body at base + decoded + scratch - stored)."""
    tx = _tool("nfl_txtr")
    chunk = tx.parse_chunks(bytes(template_span), allow_trailing=True)[0]
    require(chunk.kind == "SCNE" and chunk.compressed and chunk.video_bytes == 0, "the scene template is not a compressed scene")
    _decoded, info = tx.decode_chunk(bytes(template_span), chunk)
    encoded, _compression = tx.compress_vc_lz(bytes(decoded), stream_tag=info.stream_tag, offset_bits=info.offset_bits)
    stored = (len(encoded) + 15) & ~15
    minimum = tx.minimum_vc_lz_overlap_scratch(encoded, stored, len(decoded))
    scratch = (max(minimum, stored - len(encoded), stored - len(decoded), 0) + 15) & ~15
    raw = tx.HEADER.pack(b"SCNE", stored, len(decoded), 0, tx.COMPRESSED_SENTINEL, scratch, 0, 0)
    raw += encoded + bytes(stored - len(encoded))
    require(decode_span(raw) == bytes(decoded), "the compressed scene does not read back")
    return raw


def compile_texture(key: str, template_span: bytes, rgba: bytes | None = None) -> bytes:
    """A raw (uncompressed) 64 x 64 P8 TXTR resource named ``hair_<key>``, laid out like retail ``dread``."""
    tx = _tool("nfl_txtr")
    rgba = art_rgba(key) if rgba is None else rgba
    require(len(rgba) == 64 * 64 * 4, "the hair art must be 64 x 64 RGBA")
    chunk = tx.parse_chunks(bytes(template_span), allow_trailing=True)[0]
    decoded, _ = tx.decode_chunk(bytes(template_span), chunk)
    texture = tx.parse_texture(decoded, chunk)
    require(texture.name == "dread" and texture.format_name == "P8" and (texture.width, texture.height) == (64, 64)
            and texture.mip_levels == 1 and texture.pixel_offset == 0 and texture.palette_offset == 4096
            and chunk.system_bytes == 128 and chunk.video_bytes == 5120, "the dread texture layout changed")
    system = bytearray(decoded[:128])
    name = texture_name(key)
    raw_name = (name + "\0").encode("utf-16le")
    descriptor_old = texture.descriptor_offset
    descriptor_size = 20
    descriptor = (32 + len(raw_name) + 3) & ~3
    require(descriptor + descriptor_size <= 128, f"{name}: the name is too long for the texture header")
    head = bytes(decoded[descriptor_old:descriptor_old + descriptor_size])
    system[32:128] = bytes(96)
    system[32:32 + len(raw_name)] = raw_name
    system[descriptor:descriptor + descriptor_size] = head
    struct.pack_into("<i", system, 0x10, 32 - 0x10 + 1)
    struct.pack_into("<i", system, 0x14, descriptor - 0x14 + 1)
    colours = sorted({rgba[i:i + 4] for i in range(0, len(rgba), 4)})
    require(len(colours) <= 256, f"{name}: {len(colours)} colours; a P8 texture holds 256")
    index_of = {c: i for i, c in enumerate(colours)}
    palette = bytearray(1024)
    for i, (r, g, b, a) in enumerate(colours):
        palette[4 * i:4 * i + 4] = bytes((b, g, r, a))
    pixels = bytes(index_of[rgba[i:i + 4]] for i in range(0, len(rgba), 4))
    body = bytes(system) + tx.swizzle_2d(pixels, 64, 64, 1) + bytes(palette)
    raw = struct.pack("<4s7I", b"TXTR", len(body), 128, len(body) - 128, 0, 0, 0, 0) + body
    check = tx.parse_chunks(raw)[0]
    out, _ = tx.decode_chunk(raw, check)
    info = tx.parse_texture(out, check)
    require(info.name == name and info.format_name == "P8" and (info.width, info.height) == (64, 64)
            and tx.texture_to_rgba(out, check, info) == bytes(rgba), f"{name}: the texture does not read back")
    return raw


def _texture_spans(payload: bytes) -> dict[str, tuple[int, bytes]]:
    """{texture key: (chunk index, span)} of the hair textures present in outer 3."""
    tx = _tool("nfl_txtr")
    found = {}
    wanted = {texture_name(k): k for k in TEXTURES}
    for chunk in _chunks(payload):
        if chunk.kind != "TXTR" or chunk.compressed or chunk.system_bytes != 128:
            continue
        span = _chunk_span(payload, chunk)
        try:
            out, _ = tx.decode_chunk(span, tx.parse_chunks(span)[0])
            name = tx.parse_texture(out, tx.parse_chunks(span)[0]).name
        except (ValueError, IndexError, struct.error):
            continue
        if name in wanted:
            require(wanted[name] not in found, f"{name} appears twice")
            found[wanted[name]] = (chunk.index, span)
    return found


def collection_status(payload: bytes, pins: Mapping[str, Any] | None = None) -> str:
    """retail / applied / foreign for the hair part of outer 3 (Modern helmets' in-place scene writes accepted).

    applied = both player scenes carry exactly the pinned growth (their retail-shaped bytes are judged by their own
    owners) and the nine textures are the pinned ones, appended after every other resource."""
    pins = load_pins() if pins is None else pins
    try:
        chunks = _chunks(payload)
        states = set()
        for key in KEYS:
            _outer, index = models.parse_model_key(key)
            decoded = decode_span(_chunk_span(payload, chunks[index]))
            state = scene_state(key, decoded)
            if state == "grown":
                base = strip_scene(key, decoded)
                grown, _ = grow_scene(key, base)
                states.add("applied" if grown == decoded else "foreign")
            else:
                states.add(state)
        textures = _texture_spans(payload)
        if not textures:
            states.add("retail")
        else:
            require(set(textures) == set(TEXTURES), "some hair textures are missing")
            indices = sorted(i for i, _s in textures.values())
            require(indices == list(range(len(chunks) - len(TEXTURES), len(chunks))), "the hair textures moved")
            require(all(sha(span) == pins["textures"][key] for key, (_i, span) in textures.items()),
                    "a hair texture differs from its pin")
            states.add("applied")
    except (HairStylesError, ValueError, IndexError, KeyError, struct.error):
        return "foreign"
    return states.pop() if len(states) == 1 else "foreign"


def compile_collection(payload: bytes, *, document: Mapping[str, Any] | None = None,
                       pins: Mapping[str, Any] | None = None) -> tuple[bytes, dict[str, Any]]:
    """Outer 3 with both player scenes grown (recompressed in place, the resources after them move up) and the nine
    hair textures appended at the end. Every other resource keeps its bytes and its order."""
    pins = load_pins() if pins is None else pins
    document = load_geometry() if document is None else document
    state = collection_status(payload, pins)
    require(state in ("retail", "applied"), "the player models and hair textures are not a supported set")
    if state == "applied":
        return bytes(payload), {"status": "already_applied", "growth": 0}
    chunks = _chunks(payload)
    replace: dict[int, bytes] = {}
    receipt: dict[str, Any] = {"scenes": [], "textures": []}
    for key in KEYS:
        _outer, index = models.parse_model_key(key)
        span = _chunk_span(payload, chunks[index])
        grown, rec = grow_scene(key, decode_span(span), document)
        new = compress_scene(span, grown)
        replace[index] = new
        rec.update(chunk=index, span_before=len(span), span_after=len(new), sha256=sha(new))
        receipt["scenes"].append(rec)
    out = bytearray()
    cursor = 0
    for chunk in chunks:
        out += payload[cursor:chunk.offset]
        span = _chunk_span(payload, chunk)
        out += replace.get(chunk.index, span)
        cursor = chunk.offset + len(span)
    tail = bytes(payload[cursor:])
    require(not any(tail), "outer 3 has trailing bytes")
    template = _chunk_span(payload, chunks[DREAD_CHUNK])
    for key in TEXTURES:
        raw = compile_texture(key, template)
        require(sha(raw) == pins["textures"][key], f"hair_{key}: the texture differs from its pin")
        out += raw
        receipt["textures"].append({"name": texture_name(key), "bytes": len(raw), "sha256": sha(raw)})
    result = bytes(out)
    require(collection_status(result, pins) == "applied", "the hair read-back failed")
    receipt.update(status="applied", size_before=len(payload), size_after=len(result),
                   growth=len(result) - len(payload), memory_growth=sum(r["growth"] for r in receipt["scenes"])
                   + sum(r["bytes"] for r in receipt["textures"]))
    return result, receipt


def strip_collection(payload: bytes) -> bytes:
    """Outer 3 with the hair textures removed and both player scenes put back to retail shape, re-encoded with the
    compressor (for owners that judge decoded scene bytes; span hashes of these two scenes are not restored)."""
    chunks = _chunks(payload)
    keep = {i for i, _s in _texture_spans(payload).values()}
    out = bytearray()
    cursor = 0
    for chunk in chunks:
        out += payload[cursor:chunk.offset]
        span = _chunk_span(payload, chunk)
        cursor = chunk.offset + len(span)
        if chunk.index in keep:
            continue
        key = models.model_key(OUTER, chunk.index)
        if key in KEYS:
            decoded = decode_span(span)
            if scene_state(key, decoded) == "grown":
                span = compress_scene(span, strip_scene(key, decoded))
        out += span
    return bytes(out)


def record_pins(outer3: bytes) -> dict[str, Any]:
    """The texture pins from the authored art and the disc's own dread layout (deterministic)."""
    template = _chunk_span(outer3, _chunks(outer3)[DREAD_CHUNK])
    return {"schema": SCHEMA, "textures": {key: sha(compile_texture(key, template)) for key in TEXTURES},
            "art_sha256": {key: sha((ART_DIR / f"{key}.png").read_bytes()) for key in TEXTURES},
            "geometry_sha256": sha(GEOMETRY_PATH.read_bytes()),
            "pointer_fields_sha256": sha(POINTERS_PATH.read_bytes())}


# ------------------------------------------------------------------------------------------------ executable

OWNER = "nfl2k5_hair_styles"
CODE_SIZE = 768
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
#: the player builder's dreads block (0x8F5B9..0x8F5E5): test the Dreads bit, bind 'dread' to the dreads material
HOOK_VA, HOOK_END = 0x8F5B9, 0x8F5E6
HOOK_RETAIL = bytes.fromhex(
    "f6431801" "7427" "8b4510" "8d0446" "8d0c40" "8b4508" "6bc03e" "0fb6802d53b600" "c1e107"
    "8b91a455b600" "52" "8bcf" "e80aeeffff")
DREADS_BLOCK = HOOK_RETAIL[6:-5]           # 0x8F5BF..0x8F5E0: the texture-set handle and the cache index
SET_DREADS_TEXTURE = 0x8E3F0                 # (eax = material index, ecx = instance, [esp+4] = texture) ret 4
FIND_RESOURCE = 0x449E0                      # (ecx = container or 0, edx = type, [esp+4] = wide name) ret 4
TXTR = 0x52545854
TABLE_OFFSET = 0x100                         # style table: 8 bytes per style (mesh slot, 3 pad, name pointer)
NAMES_OFFSET = TABLE_OFFSET + 8 * (MAX_STYLE + 1)
#: model rows of the player builder (0x4EEAC0: lo_body, hi_body, hi_head) and their grown material counts
ROWS = {0: RETAIL[LO]["materials"] + K, 2: RETAIL[HI]["materials"] + K}


def code_for(code_va: int) -> bytes:
    """The owned cave (CODE_SIZE bytes, int3-padded): code, the style table and the texture names (UTF-16)."""
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(code_va)
    table = code_va + TABLE_OFFSET
    a.b("0fb6430d")                  # movzx eax, byte [ebx+0x0D]     (hair style byte of the roster record)
    a.b("83e00f")                    # and eax, 0x0F
    a.j32("0f84", "retail")          # 0: retail (the Dreads bit decides)
    a.b("83f801")                    # cmp eax, 1
    a.j32("0f84", "dreads")          # 1: the retail dreads
    a.b("83f8" + f"{NONE_STYLE:02x}")  # cmp eax, NONE_STYLE
    a.j32("0f84", "done")            # 13: no hair model, whatever the Dreads bit says
    a.b("83f8" + f"{MAX_STYLE:02x}")  # cmp eax, MAX_STYLE
    a.j32("0f87", "retail")          # reserved styles behave like style 0
    a.b("8b4d08")                    # mov ecx, [ebp+8]               (model row)
    a.b("8b571c")                    # mov edx, [edi+0x1C]            (the instance's material count)
    a.b("85c9")                      # test ecx, ecx
    a.j8("75", "row2")
    a.b("81fa" + struct.pack("<I", ROWS[0]).hex())   # cmp edx, lo_body grown count
    a.j32("0f85", "done")
    a.j8("eb", "lookup")
    a.label("row2")
    a.b("83f902")                    # cmp ecx, 2 (hi_head; hi_body has no hair)
    a.j32("0f85", "done")
    a.b("81fa" + struct.pack("<I", ROWS[2]).hex())   # cmp edx, hi_head grown count
    a.j32("0f85", "done")
    a.label("lookup")
    a.b("50")                        # push eax                       (keep the style)
    a.b("8b14c5" + struct.pack("<I", table + 4).hex())   # mov edx, [eax*8 + table+4]  (texture name)
    a.b("52")                        # push edx
    a.b("ba" + struct.pack("<I", TXTR).hex())            # mov edx, 'TXTR'
    a.b("31c9")                      # xor ecx, ecx                   (every resident container: global.iff)
    a.call(FIND_RESOURCE)            # eax = texture handle (pops the name)
    a.b("59")                        # pop ecx                        (the style)
    a.b("85c0")                      # test eax, eax
    a.j32("0f84", "done")
    a.b("50")                        # push eax                       (texture handle)
    a.b("0fb604cd" + struct.pack("<I", table).hex())     # movzx eax, byte [ecx*8 + table]  (mesh slot)
    a.b("8b4f1c")                    # mov ecx, [edi+0x1C]
    a.b("83e9" + f"{K:02x}")         # sub ecx, K
    a.b("01c8")                      # add eax, ecx                   (material index of HAIR_<mesh>)
    a.b("8bcf")                      # mov ecx, edi
    a.call(SET_DREADS_TEXTURE)       # show it with the texture (pops the handle)
    a.j32("e9", "done")
    a.label("retail")
    a.b("f6431801")                  # test byte [ebx+0x18], 1        (the Dreads bit)
    a.j32("0f84", "done")
    a.label("dreads")
    a.items.append(DREADS_BLOCK)     # the retail block, unchanged
    a.call(SET_DREADS_TEXTURE)
    a.label("done")
    a.jmp_abs(HOOK_END)
    code = bytearray(a.assemble())
    require(len(code) <= TABLE_OFFSET, "the hair styles cave outgrew its code budget")
    code += b"\xcc" * (TABLE_OFFSET - len(code))
    names = bytearray()
    pointers = {}
    for key in TEXTURES:
        pointers[key] = code_va + NAMES_OFFSET + len(names)
        names += (texture_name(key) + "\0").encode("utf-16le")
    table_bytes = bytearray(8 * (MAX_STYLE + 1))
    for style in STYLES:
        struct.pack_into("<B3xI", table_bytes, 8 * style.index, MESHES.index(style.mesh), pointers[style.texture])
    code += table_bytes
    require(len(code) == NAMES_OFFSET, "style table misplaced")
    code += names
    require(len(code) <= CODE_SIZE, "the hair styles names outgrew the owner")
    return bytes(code).ljust(CODE_SIZE, b"\xcc")


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    after = b"\xe9" + struct.pack("<i", code_va - (HOOK_VA + 5))
    return [("dreads_block", HOOK_VA, HOOK_RETAIL, after.ljust(len(HOOK_RETAIL), b"\x90"))]


def _space():
    from . import nfl2k5_xbe_space as space
    return space


def allocation(payload: bytes) -> dict | None:
    space = _space()
    if space.status(payload) != "applied":
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    require(len(rows) == 1 and rows[0]["kind"] == "code" and rows[0]["size"] == CODE_SIZE, "foreign hair styles allocation")
    return rows[0]


def _xbe_state(payload: bytes) -> tuple[str, dict | None]:
    from . import nfl2k5_rdata_sites as rdata
    from .nfl2k5_cave_oracle import XbeImage
    space = _space()
    require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    found = allocation(payload)
    if found is None:
        require(rdata.status(payload, sites(0x14DA000)) == "retail", "the dreads block changed without an allocation")
        return "retail", None
    image = XbeImage(payload)
    code = image.read(found["va"], CODE_SIZE)
    if code == b"\xcc" * CODE_SIZE:
        require(rdata.status(payload, sites(found["va"])) == "retail", "the dreads block changed with an empty owner")
        return "retail", found
    require(code == code_for(found["va"]), "foreign hair styles code")
    require(rdata.status(payload, sites(found["va"])) == "applied", "mixed hair styles hook")
    return "applied", found


def status(payload: bytes) -> str:
    """retail / applied / foreign for default.xbe."""
    try:
        return _xbe_state(payload)[0]
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError):
        return "foreign"


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in _space().reservations(payload) if r["owner"] == OWNER]
    found = allocation(payload)
    edits = sites(found["va"] if found else 0x14DA000)
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in edits]


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install the owner (a late allocator owner, after every other) and the hook. Idempotent."""
    from . import nfl2k5_rdata_sites as rdata
    space = _space()
    state, found = _xbe_state(payload)
    common = {"owner": OWNER, "experimental": True, "owner_bytes": CODE_SIZE, "styles": len(STYLES)}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    before = payload
    if found is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        found = allocation(payload)
    require(found is not None, "reserve the hair styles allocation first")
    installed, code_receipt = space.install_code(payload, OWNER, code_for(found["va"]))
    result, site_receipt = rdata.apply(installed, sites(found["va"]), OWNER)
    require(status(result) == "applied", "hair styles postcondition failed")
    changed = sum(a != b for a, b in zip(before, result)) + abs(len(result) - len(before))
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(found["va"]), "changed_bytes": changed,
                    "before_sha256": sha(before), "after_sha256": sha(result)}


# ------------------------------------------------------------------------------------------------ disc image

OUTER_ID = 2397695725


def _archive():
    from . import nfl2k5_music_archive as archive
    return archive


def _outer3(disc) -> tuple[Any, bytes]:
    entry = disc.archive_entries[OUTER]
    require(entry.name_id == OUTER_ID and entry.size <= 8 * 1024 * 1024, "the common player collection changed")
    return entry, disc.read_entry_range(entry, 0, entry.size)


def image_status(path: Path | str) -> str:
    """retail / applied / foreign for the disc's outer 3 and default.xbe together."""
    archive = _archive()
    try:
        with archive.Disc(Path(path), descriptors=()) as disc:
            _entry, collection = _outer3(disc)
            x = disc.entries["default.xbe"]
            require(x.size <= 16 * archive.BLOCK, "oversized XBE")
            resources = collection_status(collection)
            xbe = status(disc.read(x.size, x.byte_offset))
    except (OSError, ValueError, KeyError, IndexError, struct.error):
        return "foreign"
    if resources == xbe:
        return resources
    return "partial" if {resources, xbe} <= {"retail", "applied"} else "foreign"


def resource_status(path: Path | str) -> str:
    archive = _archive()
    try:
        with archive.Disc(Path(path), descriptors=()) as disc:
            return collection_status(_outer3(disc)[1])
    except (OSError, ValueError, KeyError, IndexError, struct.error):
        return "foreign"


def apply_to_image(path: Path | str, *, progress: Callable[[str, int, int], None] | None = None) -> dict[str, Any]:
    """Build step (resources): grow outer 3 on a disposable output image. Pack 0 is rewritten at the end of the image
    through the shared growth writer (the path the Guardian overlay and the Anniversary packs use); the outer table's
    later entries move by the growth; nothing else changes. The executable hook is the separate owner (``apply``)."""
    from . import nfl2k5_resource_growth as growth
    from . import nfl2k5_depth_chart_storage as storage
    from . import platform_compat as io
    import os
    archive = _archive()
    say = progress or (lambda message, done, total: None)
    path = Path(path).resolve()
    say("Hair styles: player models and hair textures", 0, 1)
    with archive.Disc(path, descriptors=()) as disc:
        identity = archive.identity(path)
        entry, before = _outer3(disc)
        after, receipt = compile_collection(before)
        if receipt.get("status") == "already_applied":
            say("Hair styles: already in place", 1, 1)
            return {"label": LABEL, "status": "already_applied", "evidence": EVIDENCE, "image_growth": 0}
        p = disc.pack_extents["0"]
        read_pack = lambda n, at: disc.read(n, p.byte_offset + at)  # noqa: E731
        plan = growth.plan_pack0(read_pack, p.size, OUTER, OUTER_ID, after, padding_bytes=(0, 0x9F))
        require(plan.start == entry.virtual_offset, "the common collection is not in pack 0")
        old_size = disc.image_size
        node = disc.nodes["0"][0]
        old_node = struct.pack("<II", p.sector, p.size)
        require(archive.identity(path) == identity, "the image changed during the hair styles preflight")
        with path.open("r+b") as writer:
            fd = writer.fileno()
            try:
                offset = archive.align_up(old_size)
                if offset > old_size:
                    require(io.pwrite(fd, bytes(offset - old_size), old_size) == offset - old_size, "short write")
                transport = growth.write_pack0(fd, read_pack, plan, offset)
                new_node = struct.pack("<II", (offset - p.base_offset) // 2048, plan.size_after)
                require(io.pwrite(fd, new_node, node) == 8, "short node write")
                os.fsync(fd)
            except Exception:
                io.pwrite(fd, old_node, node)
                os.ftruncate(fd, old_size)
                os.fsync(fd)
                raise
            image_growth = os.fstat(fd).st_size - old_size
    require(resource_status(path) == "applied", "hair styles: the image read-back is not applied")
    say("Hair styles: done", 1, 1)
    receipt.update(label=LABEL, evidence=EVIDENCE, runtime_witnessed=False, pack_transport=transport,
                   image_growth=image_growth)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_hair_styles", description=LABEL)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="retail / applied / partial / foreign for a disc image").add_argument("image")
    lab = sub.add_parser("apply-lab", help="lab only: add the hair styles to a disposable disc image copy")
    lab.add_argument("image")
    rp = sub.add_parser("record-pins", help="record the texture pins from a retail outer 3")
    rp.add_argument("outer3")
    args = parser.parse_args(argv)
    if args.command == "status":
        print(image_status(args.image))
        return 0
    if args.command == "apply-lab":
        receipt = apply_to_image(args.image, progress=lambda m, d, t: print(f"  {m}", flush=True))
        print(json.dumps({k: v for k, v in receipt.items() if k != "scenes"}, indent=1, default=str))
        return 0
    pins = record_pins(Path(args.outer3).read_bytes())
    PINS_PATH.write_text(json.dumps(pins, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print("PINS_OK", PINS_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
