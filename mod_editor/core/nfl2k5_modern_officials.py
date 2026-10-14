"""Modern officials: the game's NFL officials in the 2025-26 uniform.

All seven officials are one model, the scene ``referee`` in ``gamedata.iff`` (outer 346): two shapes (``ref_high``
drawn close up, ``ref_low`` at distance), 25 joints, six materials. Only ``shirt`` and ``pants`` carry an embedded
texture (256x256 P8, six mips); the game binds the others at run time per official (the executable's string table
beside the referee loader): ``numbers`` takes ``ref_R``, ``ref_U``, ``ref_HL``, ``ref_LJ``, ``ref_FJ``, ``ref_SJ`` or
``ref_BJ`` (standalone 128x128 P8 TXTR chunks of gamedata.iff), ``hat`` takes ``rhat_white`` (the referee) or
``rhat_black`` (the other six; one TSET chunk, both 64x64 with four mips sharing one index image and two palettes),
``face`` and ``hand`` take ``rface_00``/``rface_02`` and ``rhand_00``/``rhand_02`` (kept).

The retail officials wore the 2004 uniform: two-inch stripes on long sleeves, white knickers over black-and-white
hooped socks, white letters and numbers on black patches (the role letters and number on the front chest, the
number on the back), and ``HL`` for the head linesman. This option dresses them in the 2025-26 uniform:

* ``shirt``: the shirt the league has used since 2006 (wide white and thin black stripes that flare over the
  shoulders into a black yoke, a black collar and centre placket, a white panel across the upper back for the role
  letter and number, the NFL shield on the wearer's left chest, long black sleeves with one white stripe down the
  outside of the arm and a black cuff, the cold-weather cut, since the model has long sleeves and the shirt texture
  is shared by both skin tones); black shoes with a white midsole line;
* ``pants``: black long pants with a thin white stripe down the outside of each leg, a black belt with a silver
  buckle, a small NFL shield on the wearer's right hip. The model keeps its retail knicker cut (the silhouette
  narrows a little below the knee): no position or skin is changed;
* ``ref_*``: black role letters above a black number on the white back panel; the head linesman's ``HL`` becomes
  ``DJ`` (the position was renamed down judge in 2017). The numbers are the game's own;
* the caps: the referee's white cap and the others' black cap with white piping on the panel seams. All six crown
  panels share one UV island, so a front emblem would repeat on every panel: the caps carry none;
* three UV-only edits in the scene (positions, normals, skin and topology stay retail): the 2004 front-chest number
  patch (``ref_high`` vertices 1433-1441, ``ref_low`` 418-421 of the ``numbers`` material) samples the clear top rows
  of the number texture, so it no longer shows; and the high LOD collar ring and front collar points (``ref_high``
  shirt vertices 1291-1302 and 1317-1352, a closed set used by no other triangle) sample one texel inside a black
  area of the new shirt instead of the retail black square that the back of the shirt behind the number also
  samples (that square is now part of the white number panel).

Every part is refit in place at its retail size and format into its retail stored span (wrapper identical, the
stream filled to within a few bytes of the stored body so the in-place decode stays inside the retail scratch
word). Only authored pixels ship; no retail pixel is copied into the art.

EXPERIMENTAL and UNWITNESSED: proved offline (decoded textures, renders from the data, byte receipts) and in
emulator frames; the look in the game is for Noah's eyes.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import struct
import sys
from typing import Any

OWNER = "nfl2k5_modern_officials"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_KEY = "modern_officials"
BUILD_CAPTION = "2025-26 NFL officials' uniform"
HELP_TEXT = (
    "Dresses the game's seven officials in today's NFL uniform: the modern striped shirt with the black collar, "
    "shoulder yoke and the NFL shield on the chest, the white back panel with the role letter above the number, black "
    "long pants with the white side stripe in place of the 2004 white knickers and striped socks, black shoes, the "
    "referee's white cap and the black caps with white piping. The head linesman's HL becomes DJ (down judge). The "
    "officials' shapes and animations are the game's own. Experimental: not yet seen in the game by the SOFTDRINK "
    "tester."
)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_modern_officials"
PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_modern_officials_pins/v1"
ARCHIVE = "gamedata.iff"
SCENE = "referee"
# embedded scene textures: art name -> material
SCENE_TEXTURES = (("shirt", "shirt"), ("pants", "pants"))
# the run-time number textures (standalone TXTR chunks): texture name -> art file
NUMBERS = ("ref_R", "ref_U", "ref_HL", "ref_LJ", "ref_FJ", "ref_SJ", "ref_BJ")
HATS = ("rhat_white", "rhat_black")
HAT_ART = {"rhat_white": "hat_white", "rhat_black": "hat_black"}
# UV-only geometry plan: (shape, material, vertices, target uv). The targets are texel centres of the new art.
FRONT_PATCH_UV = (0.5, 0.15)
COLLAR_UV = (0.490234375, 0.396484375)
UV_EDITS = (
    ("ref_high", "numbers", tuple(range(1433, 1442)), FRONT_PATCH_UV),
    ("ref_low", "numbers", tuple(range(418, 422)), FRONT_PATCH_UV),
    ("ref_high", "shirt", tuple(range(1291, 1303)) + tuple(range(1317, 1353)), COLLAR_UV),
)
FILL_SLACKS = (0, 1, 2, 4, 6)
PALETTE_LADDER = (256, 192, 128, 96, 64)


class ModernOfficialsError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ModernOfficialsError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def _tools():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import nfl_txtr as tx  # noqa: E402
    import nfl_vc_lz_fill as fill  # noqa: E402
    return tx, fill


def _mm():
    from . import nfl2k5_modern_metlife as mm
    return mm


def _models():
    from . import nfl2k5_models as models
    return models


def _stw():
    from . import nfl2k5_stadium_texture_writer as stw
    return stw


def _outer_image():
    from . import nfl2k5_roster_records as rr
    return rr._outer_image()


def name_id(name: str) -> int:
    return _mm().name_id(name)


# --- pins and art -----------------------------------------------------------------------------------------------

_PINS: dict | None = None
ART = tuple(name for name, _m in SCENE_TEXTURES) + tuple(HAT_ART[h] for h in HATS) + tuple(f"numbers/{n}" for n in NUMBERS)
ART_SIZES = {"shirt": (256, 256), "pants": (256, 256), "hat_white": (64, 64), "hat_black": (64, 64),
             **{f"numbers/{n}": (128, 128) for n in NUMBERS}}


def _check_pins(document: dict) -> dict:
    require(isinstance(document, dict) and document.get("schema") == PINS_SCHEMA, "unsupported modern officials pins")
    require(document.get("archive") == ARCHIVE and set(document.get("art", {})) == set(ART),
            "the modern officials pins name another archive or art set")
    parts = document.get("parts")
    require(isinstance(parts, list) and sorted(p.get("part") for p in parts) == sorted(
        ["scene:referee", "tset:rhat"] + [f"txtr:{n}" for n in NUMBERS]), "the modern officials pins are incomplete")
    for row in parts:
        require(set(row) >= {"part", "kind", "name", "chunk_index", "span_size", "retail_sha256", "applied_sha256",
                             "palette_max"}, f"modern officials pin row incomplete: {row.get('part')}")
    return document


def pins() -> dict:
    global _PINS
    if _PINS is None:
        require(PINS_PATH.is_file(), "the modern officials pins are missing from this build")
        _PINS = _check_pins(json.loads(PINS_PATH.read_text(encoding="utf-8")))
    return _PINS


def art_path(name: str) -> Path:
    return DATA_DIR / f"{name}.png"


def available() -> bool:
    """The pins load and every shipped texture matches its pin."""
    try:
        document = pins()
        for name, digest in document["art"].items():
            path = art_path(name)
            if not path.is_file() or sha(path.read_bytes()) != digest:
                return False
        return True
    except (OSError, ValueError):
        return False


def _rgba(name: str):
    import numpy as np
    from PIL import Image
    path = art_path(name)
    width, height = ART_SIZES[name]
    require(path.is_file(), f"modern officials art is missing: {name}.png")
    with Image.open(io.BytesIO(path.read_bytes())) as image:
        require(image.size == (width, height), f"{name}.png is {image.size}, the texture needs {width}x{height}")
        return np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()


# --- refit -------------------------------------------------------------------------------------------------------

def _refit(template_span: bytes, decoded: bytes) -> tuple[bytes, dict]:
    """Recompress ``decoded`` into the retail stored span of ``template_span``: wrapper identical, the stream filled to
    within a few bytes of the stored body so the in-place decode stays inside the retail scratch word."""
    tx, fill = _tools()
    _kind, stored, system, video, magic, scratch, _r0, _r1 = tx.HEADER.unpack_from(template_span)
    require(magic == tx.COMPRESSED_SENTINEL and len(decoded) == system + video, "the chunk is not the retail layout")
    chunk = tx.parse_chunks(template_span, allow_trailing=True)[0]
    _tdec, tinfo = tx.decode_chunk(template_span, chunk)
    stream = template_span[tx.HEADER.size:tx.HEADER.size + tinfo.consumed_bytes]
    tag, bits = struct.unpack_from("<I", stream, 4)[0], stream[8]
    candidates = []
    try:
        candidates.append(("greedy", tx.compress_vc_lz(decoded, stream_tag=tag, offset_bits=bits,
                                                       max_encoded_size=stored, verify_roundtrip=True)[0]))
    except tx.TxtrError:
        pass
    compressed = fill.compress_optimal(decoded, stream_tag=tag, offset_bits=bits)
    if len(compressed) <= stored:
        candidates.append(("optimal", compressed))
    last = "no encoder fits the stored body"
    for name, compressed in candidates:
        for slack in FILL_SLACKS:
            filled, expanded = fill.fill_stream(compressed, decoded, stored, slack=slack)
            padding = stored - len(filled)
            need = tx.minimum_vc_lz_overlap_scratch(filled, stored, len(decoded))
            if padding > scratch or need > scratch:
                last = f"padding {padding}, needs {need}, retail scratch {scratch}"
                continue
            rebuilt = template_span[:tx.HEADER.size] + filled + bytes(padding)
            back, binfo = tx.decode_chunk(rebuilt, chunk)
            require(back == decoded and len(rebuilt) == len(template_span) and binfo.consumed_bytes == len(filled),
                    "the refit chunk failed its independent decode")
            return rebuilt, dict(encoder=name, slack=slack, stream_bytes=len(filled), stored_size=stored,
                                 padding_bytes=padding, scratch_needed=need, scratch_retail=scratch,
                                 matches_expanded=expanded)
    raise ModernOfficialsError(f"the chunk does not fit its retail span ({last})")


# --- the referee scene -------------------------------------------------------------------------------------------

def _scene_parts(span: bytes):
    """(chunk, parsed scene, decoded bytes) of a lone SCNE span."""
    tx, _fill = _tools()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    rec, decoded = _mm()._scene(span, chunk)
    return chunk, rec, decoded


def uv_edit_lanes(rec: dict, decoded: bytes) -> list[dict]:
    """Every UV lane the plan writes: shape, vertex, byte offset, retail lane value, new lane value. The vertex sets
    are closed (no triangle outside the plan's material uses them; the test proves it on the retail scene's export),
    and the retail lane values are pinned, so a scene whose lanes differ compiles to bytes that miss the pin."""
    models = _models()
    shapes = {str(s["name"]): s for s in rec["shapes"]}
    materials = [str(m.get("name")) for m in rec["materials"]]
    out = []
    for shape_name, material, vertices, target in UV_EDITS:
        shape = shapes.get(shape_name)
        require(shape is not None, f"the referee has no shape {shape_name}")
        lanes = models._shape_lanes(rec, shape, decoded)
        require(lanes.texcoord is not None, f"{shape_name} has no texture coordinate lane")
        require(max(vertices) < lanes.vertex_count, f"{shape_name} has fewer vertices than the plan")
        base = models._stream_base({}, shape, lanes.texcoord[0])
        qu, qv = models.uv_from_gltf(target[0], target[1], lanes.uv_scale, lanes.uv_offset)
        for vertex in vertices:
            at = base + vertex * lanes.texcoord[2] + lanes.texcoord[1]
            out.append(dict(shape=shape_name, material=material, vertex=vertex, at=at,
                            retail=list(struct.unpack_from("<2h", decoded, at)), applied=[qu, qv]))
    return out


def compile_scene(span: bytes, palette_max: int = 256) -> tuple[bytes, dict]:
    """The referee scene span with the 2025-26 shirt and pants and the UV plan, refit in its retail span."""
    mm = _mm()
    chunk, rec, decoded = _scene_parts(span)
    require(rec.get("name") == SCENE, "the chunk is not the referee scene")
    system = int(rec["system_bytes"])
    rows = mm.texture_rows(rec)
    edited = bytearray(decoded)
    detail = {}
    for name, material in SCENE_TEXTURES:
        row = rows.get(material)
        require(row is not None and (int(row["width"]), int(row["height"])) == ART_SIZES[name],
                f"the referee has no 256x256 P8 texture for {material}")
        colours = mm.write_p8(edited, system, row, _rgba(name), maximum=palette_max)
        detail[name] = dict(material=material, texture_index=int(row["index"]), mip_levels=int(row["mip_levels"]),
                            palette_entries=int(colours))
    lanes = uv_edit_lanes(rec, decoded)
    for lane in lanes:
        struct.pack_into("<2h", edited, lane["at"], *lane["applied"])
    detail["uv_lanes"] = len(lanes)
    detail["uv_lanes_changed"] = sum(1 for lane in lanes if lane["retail"] != lane["applied"])
    rebuilt, fit = _refit(span, bytes(edited))
    return rebuilt, dict(textures=detail, fit=fit)


# --- the number textures and the caps ----------------------------------------------------------------------------

def _texture_row(texture, mips: int | None = None) -> dict:
    return dict(width=texture.width, height=texture.height, mip_levels=texture.mip_levels if mips is None else mips,
                pixel_offset=texture.pixel_offset, palette_offset=texture.palette_offset,
                mapped_material_names=[texture.name])


def compile_txtr(span: bytes, art: str, palette_max: int = 256) -> tuple[bytes, dict]:
    """A standalone P8 TXTR chunk span with new pixels (full mip chain, one palette), refit in its retail span."""
    tx, _fill = _tools()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    decoded, _info = tx.decode_chunk(span, chunk)
    texture = tx.parse_texture(decoded, chunk)
    require(chunk.kind == "TXTR" and texture.format_name == "P8"
            and (texture.width, texture.height) == ART_SIZES[art], f"{art}: not the retail texture layout")
    edited = bytearray(decoded)
    colours = _mm().write_p8(edited, chunk.system_bytes, _texture_row(texture), _rgba(art), maximum=palette_max)
    rebuilt, fit = _refit(span, bytes(edited))
    return rebuilt, dict(texture=texture.name, palette_entries=int(colours), fit=fit)


def _rel(data: bytes, field: int) -> int | None:
    value = struct.unpack_from("<i", data, field)[0]
    return None if value == 0 else field + value - 1


def tset_refs(decoded: bytes) -> list[dict]:
    """The texture references of a decoded TSET: name, descriptor, pixel and palette offsets, size, mips."""
    version, count = struct.unpack_from("<II", decoded, 0)
    require(version == 0x0D and 0 < count < 64, "not a TSET")
    out = []
    for index in range(count):
        base = 0x18 + index * 0x24
        require(decoded[base:base + 4] == b"TXTR", "the TSET reference is not a texture")
        name_at, desc_at = _rel(decoded, base + 4), _rel(decoded, base + 8)
        require(name_at is not None and desc_at is not None, "the TSET reference is incomplete")
        end = name_at
        while decoded[end:end + 2] != b"\0\0":
            end += 2
        _u0, pixel, palette, packed, packed_size, _flags = struct.unpack_from("<6I", decoded, desc_at)
        width = packed_size & 0xFFFF if packed_size else 1 << ((packed >> 20) & 0xF)
        height = packed_size >> 16 if packed_size else 1 << ((packed >> 24) & 0xF)
        out.append(dict(name=decoded[name_at:end].decode("utf-16le"), pixel_offset=pixel, palette_offset=palette,
                        format_code=(packed >> 8) & 0xFF, mip_levels=(packed >> 16) & 0xF, width=width, height=height))
    return out


def joint_quantize(levels_a, levels_b, maximum: int = 256):
    """One shared index image for two pictures of identical structure (the white and the black cap): a deterministic
    median cut over the colour PAIRS of every mip level. Returns (indices per level, palette a, palette b)."""
    import numpy as np
    pairs = np.concatenate([np.concatenate([np.frombuffer(a, np.uint8).reshape(-1, 4),
                                            np.frombuffer(b, np.uint8).reshape(-1, 4)], 1)
                            for a, b in zip(levels_a, levels_b)]).astype(np.int64)
    unique, inverse, counts = np.unique(pairs, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    boxes = [np.arange(len(unique))]
    while len(boxes) < maximum:
        best, best_span = None, 0
        for k, box in enumerate(boxes):
            if len(box) < 2:
                continue
            span = int((unique[box].max(0) - unique[box].min(0)).max())
            if span > best_span:
                best, best_span = k, span
        if best is None:
            break
        box = boxes.pop(best)
        values = unique[box]
        axis = int(np.argmax(values.max(0) - values.min(0)))
        order = box[np.argsort(values[:, axis], kind="stable")]
        weights = np.cumsum(counts[order])
        cut = int(np.searchsorted(weights, weights[-1] / 2.0))
        cut = min(max(cut, 1), len(order) - 1)
        boxes[best:best] = [order[:cut], order[cut:]]
    label = np.zeros(len(unique), np.int64)
    palette = np.zeros((len(boxes), 8), np.int64)
    for k, box in enumerate(boxes):
        label[box] = k
        w = counts[box][:, None]
        palette[k] = (unique[box] * w).sum(0) // w.sum() if len(box) > 1 else unique[box][0]
    indices = label[inverse].astype(np.uint8)
    out, at = [], 0
    for a in levels_a:
        n = len(a) // 4
        out.append(indices[at:at + n].tobytes())
        at += n
    return out, palette[:, :4], palette[:, 4:]


def _palette_payload(palette_rgba) -> bytes:
    import numpy as np
    full = np.zeros((256, 4), np.uint8)
    full[:len(palette_rgba)] = np.asarray(palette_rgba, np.uint8)
    return full[:, [2, 1, 0, 3]].tobytes()


def compile_tset(span: bytes) -> tuple[bytes, dict]:
    """The caps TSET span: both caps written as one shared index chain (four mips) and two palettes."""
    import numpy as np
    tx, _fill = _tools()
    stw = _stw()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    decoded, _info = tx.decode_chunk(span, chunk)
    refs = {r["name"]: r for r in tset_refs(decoded)}
    require(set(refs) == set(HATS), "the TSET is not the caps")
    white, black = refs["rhat_white"], refs["rhat_black"]
    require(white["pixel_offset"] == black["pixel_offset"] and white["format_code"] == black["format_code"] == 0x0B
            and (white["width"], white["height"], white["mip_levels"]) == (64, 64, 4)
            == (black["width"], black["height"], black["mip_levels"]), "the caps are not the retail layout")
    dims = stw._mip_dimensions(64, 64, 4)
    mips = {}
    for hat in HATS:
        mips[hat] = [level.rgba for level in stw._generate_dynamic_mips(
            np.ascontiguousarray(_rgba(HAT_ART[hat])).tobytes(), dims)]
    indices, pal_white, pal_black = joint_quantize(mips["rhat_white"], mips["rhat_black"])
    swizzled = b"".join(tx.swizzle_2d(chain, w, h, 1) for chain, (w, h) in zip(indices, dims))
    system = chunk.system_bytes
    pixel = system + white["pixel_offset"]
    require(len(swizzled) == sum(w * h for w, h in dims) and pixel + len(swizzled) <= system + white["palette_offset"],
            "the cap index chain does not fit its allocation")
    edited = bytearray(decoded)
    edited[pixel:pixel + len(swizzled)] = swizzled
    for hat, palette in (("rhat_white", pal_white), ("rhat_black", pal_black)):
        at = system + refs[hat]["palette_offset"]
        edited[at:at + 1024] = _palette_payload(palette)
    rebuilt, fit = _refit(span, bytes(edited))
    return rebuilt, dict(palette_entries=int(len(pal_white)), fit=fit)


# --- the disc ----------------------------------------------------------------------------------------------------

def _archive_bytes(archive) -> tuple[Any, bytes]:
    entry = {e.name_id: e for e in archive.entries}.get(name_id(ARCHIVE))
    require(entry is not None, f"{ARCHIVE} is not on this disc")
    return entry, archive.read(entry.virtual_offset, entry.size)


def _chunk_name(raw: bytes, chunk) -> str | None:
    tx, _fill = _tools()
    try:
        if chunk.kind == "SCNE":
            return str(_mm()._scene(raw, chunk)[0].get("name"))
        decoded, _info = tx.decode_chunk(raw, chunk)
        if chunk.kind == "TXTR":
            return tx.parse_texture(decoded, chunk).name
        if chunk.kind == "TSET":
            names = sorted(r["name"] for r in tset_refs(decoded))
            return "rhat" if names == sorted(HATS) else "+".join(names)
    except Exception:  # noqa: BLE001 - an unreadable chunk is simply not one of ours
        return None
    return None


def _find_chunk(raw: bytes, row: dict):
    """The archive chunk of one pin row: at its retail index when it still holds that name, else by kind and name."""
    tx, _fill = _tools()
    chunks = tx.parse_chunks(raw, allow_trailing=True)
    kind = row["kind"]
    if row["chunk_index"] < len(chunks):
        chunk = chunks[row["chunk_index"]]
        if chunk.kind == kind and 0x20 + chunk.stored_size == row["span_size"] and _chunk_name(raw, chunk) == row["name"]:
            return chunk
    hits = [c for c in chunks if c.kind == kind and 0x20 + c.stored_size == row["span_size"]
            and _chunk_name(raw, c) == row["name"]]
    require(len(hits) == 1, f"{ARCHIVE} has no single {kind} {row['name']}")
    return hits[0]


def _parts(archive, document: dict) -> list[dict]:
    entry, raw = _archive_bytes(archive)
    out = []
    for row in document["parts"]:
        chunk = _find_chunk(raw, row)
        span = raw[chunk.offset:chunk.offset + row["span_size"]]
        digest = sha(span)
        state = "retail" if digest == row["retail_sha256"] else "applied" if digest == row["applied_sha256"] else "foreign"
        out.append(dict(part=row["part"], at=entry.virtual_offset + chunk.offset, size=row["span_size"],
                        chunk_index=chunk.index, state=state, row=row))
    return out


def resource_states(source, *, document: dict | None = None) -> dict[str, str]:
    document = pins() if document is None else _check_pins(document)
    with _outer_image()(source) as archive:
        return {p["part"]: p["state"] for p in _parts(archive, document)}


def image_status(source, *, document: dict | None = None) -> str:
    """'retail', 'applied', 'mixed' (some parts each) or 'foreign' (a part is neither)."""
    values = set(resource_states(source, document=document).values())
    if "foreign" in values:
        return "foreign"
    if values == {"retail"}:
        return "retail"
    if values == {"applied"}:
        return "applied"
    return "mixed"


def compile_part(row: dict, span: bytes) -> tuple[bytes, dict]:
    if row["kind"] == "SCNE":
        return compile_scene(span, int(row["palette_max"]))
    if row["kind"] == "TSET":
        return compile_tset(span)
    return compile_txtr(span, f"numbers/{row['name']}", int(row["palette_max"]))


def _write_all(archive, plan: list[tuple[int, bytes, bytes]]) -> None:
    written: list[tuple[int, bytes]] = []
    try:
        for at, before, after in plan:
            require(archive.read(at, len(before)) == before, "an officials span changed after preflight")
            require(archive.write(at, after) == len(after), "short officials write")
            written.append((at, before))
            require(archive.read(at, len(after)) == after, "officials read-back differs")
    except BaseException:
        for at, before in reversed(written):
            archive.write(at, before)
        raise


def plan_image(source, *, document: dict | None = None, progress=None) -> tuple[list, list[dict]]:
    """Compile every retail part of ``source`` (read only): ([(virtual offset, before, after)], receipt rows)."""
    document = pins() if document is None else _check_pins(document)
    say = progress or (lambda message, done, total: None)
    plan, rows = [], []
    with _outer_image()(source) as archive:
        parts = _parts(archive, document)
        require(all(p["state"] != "foreign" for p in parts),
                "an officials texture or the referee scene is neither the retail nor the 2025-26 bytes; rebuild from "
                "a supported USA source")
        for index, part in enumerate(parts):
            row = part["row"]
            out = dict(part=part["part"], chunk_index=part["chunk_index"], virtual_offset=part["at"], size=part["size"],
                       state_before=part["state"])
            if part["state"] == "retail":
                say(f"2025-26 officials: {part['part']}", index, len(parts))
                before = archive.read(part["at"], part["size"])
                after, detail = compile_part(row, before)
                require(sha(after) == row["applied_sha256"], f"{part['part']}: the compiled bytes differ from the pin")
                plan.append((part["at"], before, after))
                out.update(written=True, before_sha256=sha(before), after_sha256=sha(after),
                           changed_bytes=sum(a != b for a, b in zip(before, after)), **detail)
            else:
                out.update(written=False, changed_bytes=0)
            rows.append(out)
    return plan, rows


def apply_to_image(target, *, document: dict | None = None, progress=None) -> dict[str, Any]:
    """Build-only: ``target`` is the caller's disposable output image. Retail or already-2025-26 parts only."""
    document = pins() if document is None else _check_pins(document)
    plan, rows = plan_image(target, document=document, progress=progress)
    with _outer_image()(target, writable=True) as archive:
        _write_all(archive, plan)
    state = image_status(target, document=document)
    require(state == "applied", f"the 2025-26 officials failed their read-back on the copy ({state})")
    return dict(label=LABEL, option=BUILD_KEY, state=state, runtime_witnessed=False, parts=rows, written=len(plan),
                already_applied=len(rows) - len(plan), changed_bytes=sum(r["changed_bytes"] for r in rows))


def verify(source, *, enabled: bool = True, document: dict | None = None) -> dict[str, Any]:
    state = image_status(source, document=document)
    require(state == ("applied" if enabled else "retail"), "the 2025-26 officials do not match the request")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False)


# --- pins (development) ------------------------------------------------------------------------------------------

def record_pins(retail_image) -> dict:
    """The pin document from a retail USA image and the shipped art: retail and compiled digests of every part."""
    tx, _fill = _tools()
    art = {name: sha(art_path(name).read_bytes()) for name in ART}
    rows = []
    with _outer_image()(retail_image) as archive:
        entry, raw = _archive_bytes(archive)
        wanted = [("SCNE", SCENE, "scene:referee"), ("TSET", "rhat", "tset:rhat")] + [("TXTR", n, f"txtr:{n}") for n in NUMBERS]
        chunks = tx.parse_chunks(raw, allow_trailing=True)
        for kind, name, part in wanted:
            hits = [c for c in chunks if c.kind == kind and _chunk_name(raw, c) == name]
            require(len(hits) == 1, f"the retail {ARCHIVE} has no single {kind} {name}")
            chunk = hits[0]
            span = raw[chunk.offset:chunk.offset + 0x20 + chunk.stored_size]
            row = dict(part=part, kind=kind, name=name, outer_index=entry.index, outer_id=f"0x{entry.name_id:08x}",
                       chunk_index=chunk.index, chunk_offset=chunk.offset, span_size=len(span), retail_sha256=sha(span))
            for size in PALETTE_LADDER:
                try:
                    after, detail = compile_part(dict(row, palette_max=size), span)
                except ModernOfficialsError:
                    if kind == "TSET":
                        raise
                    continue
                row.update(palette_max=size, applied_sha256=sha(after), fit=detail["fit"])
                if kind == "SCNE":
                    _chunk, rec, decoded = _scene_parts(span)
                    row["uv_lanes"] = [{k: v for k, v in lane.items() if k != "at"} for lane in uv_edit_lanes(rec, decoded)]
                break
            else:
                raise ModernOfficialsError(f"{part}: the new art does not fit at any palette size")
            rows.append(row)
    return _check_pins(dict(schema=PINS_SCHEMA, label=LABEL, archive=ARCHIVE, art=art, parts=rows))


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="2025-26 NFL officials: status or apply on a disc image copy")
    ap.add_argument("command", choices=("status", "apply"))
    ap.add_argument("image")
    args = ap.parse_args(argv)
    if args.command == "status":
        print(image_status(args.image))
        for key, value in sorted(resource_states(args.image).items()):
            print(f"  {key}: {value}")
        return 0
    receipt = apply_to_image(args.image, progress=lambda m, d, t: print(m, flush=True))
    print(json.dumps({k: v for k, v in receipt.items() if k != "parts"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
