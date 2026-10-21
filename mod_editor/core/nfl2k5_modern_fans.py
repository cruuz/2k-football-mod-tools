"""Modern fans: the close-up crowd people of the fan-reaction cutaways in 2025-26 fan wear with the 2026 marks.

The fan-reaction cutaways are the cutscene archives whose scenes ``crowda`` .. ``crowdf``, ``crowdn``, ``crowdv3``,
``crowdbald``, ``crowddrink``, ``crowdsleep``, ``crowdticket``, ``crowdusher`` and ``propscrowdsign`` hold the
close-up crowd people (not the stadium seating-band billboards). Those people carry almost no texture of their own:
their ``tshirt``, ``jersey``, ``sweatshirt``, ``varsity``, ``puffyjacket``, ``hardhat``, ``face`` (``head0N``),
``noshirtns``, ``crowdsign`` and the like materials are bound at run time, by name, to the textures of the club's
crowd texture sets. Every club (85 asset codes, in code order) has four of them, standalone P8 TXTR chunks (one
level, one 256-entry palette) in four archive families of 85 outers each:

* set ``A`` (outers 1822 + i): the everyday crowd: tshirt, jersey, sweatshirt, varsity, hardhat, eight heads, the
  digits 0-9 for the replica jerseys and signs, cement and chair;
* set ``B`` (1907 + i): the same plus the puffy jacket (cold weather);
* set ``ns`` (``nsNN.iff``, 2162 + i): the sign holders and painted-chest fans: crowdsign, foamfinger, boxlogo,
  noshirtns01-08 (one letter of the club name each), puffy jacket, tshirt, hard hat, heads, digits;
* set ``tg`` (``tgNN.iff``, 2247 + i): the tailgate: fanplate (licence plate, nickname, cloth, logo), puffy jacket,
  tshirt, hard hat, heads.

A club's texture of one name is the same picture in every set it appears in. This option writes, for the 32 clubs of
2026, the authored picture of each changed name into every set copy, each refit in place at its retail size and
format into the retail stored span (wrapper identical, the stream filled to within a few bytes of the stored body so
the in-place decode stays inside the retail scratch word). The 2004 logos, wordmarks, maker marks and chants are
gone; the clothing is the club's 2026 colours with the retail fabric folds. Six painted faces carried a retired or
outdated mark (Washington ``head01`` and ``head03``, Detroit, Miami and the Jets ``head03``, Seattle ``head01``): they
become the club's 2026 colours split down the face with a small 2026 logo (a paint layer laid over the disc's own
head texture). No retail pixel ships: the few retail details the art keeps (``KEEP_RECTS``) are taken from the
disc's own texture at Build time. The other heads, the digits, cement, chair
and the other 53 asset codes (classic and special teams) keep their retail bytes.

Three close-up scenes carry their own embedded textures that this option also replaces, each scene refit in its
retail span: the Kansas City and Washington superfans (``crowds13``, ``crowds29``) wore a feathered headdress: its
feathers become clear and its band a plain club-colour headband with the 2026 logo; the drinking fan's cup
(``crowddrink``) loses its 2004 sports-drink brand and becomes a plain stadium cup.

EXPERIMENTAL and UNWITNESSED: proved offline (decoded textures, byte receipts) and in emulator frames; the look in the
game is for Noah's eyes.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import struct
import sys
from typing import Any

OWNER = "nfl2k5_modern_fans"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_KEY = "modern_fans"
BUILD_CAPTION = "2026 fans in the crowd cutaways"
HELP_TEXT = (
    "Dresses the close-up fans of the crowd-reaction cutaways in 2025-26 fan wear: every club's shirts, replica "
    "jerseys, hoodies, varsity and puffy jackets and hard hats in its 2026 colours with the 2026 logo, the 2004 logos "
    "and maker marks gone, and new signs, foam fingers and tailgate plates with the 2026 nickname and a harmless "
    "chant. The fans' shapes and animations are the game's own. Experimental: not yet seen in the game by the "
    "SOFTDRINK tester."
)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_modern_fans"
PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_modern_fans_pins/v1"
SETS = {"A": 1822, "B": 1907, "ns": 2162, "tg": 2247}
FILL_SLACKS = (0, 1, 2, 4, 6)
# No retail pixel ships: where the 2026 art keeps a retail detail, the shipped PNG holds a flat grey there and the
# Build takes those pixels from the disc's own texture: the t-shirt's sneaker and the swatches beside the cap, the
# hard hat's corner swatches, the tailgate plate's grey bar.
KEEP_RECTS = {"tshirt": ((158, 0, 192, 74), (192, 48, 256, 74)), "hardhat": ((0, 0, 10, 10), (114, 0, 128, 8)),
              "fanplate": ((118, 44, 128, 86),)}
# The face paints ship as a paint layer (RGBA, alpha = paint coverage) laid over the disc's own head texture, so the
# fan's hair, ears, eyes and mouth are the game's own pixels.
OVERLAY_PREFIX = "head"
PALETTE_LADDER = (256, 192, 128, 96, 64, 48, 32, 24, 16)


class ModernFansError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ModernFansError(message)


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


def _outer_image():
    from . import nfl2k5_roster_records as rr
    return rr._outer_image()


# --- pins and art -----------------------------------------------------------------------------------------------

_PINS: dict | None = None


def _check_pins(document: dict) -> dict:
    require(isinstance(document, dict) and document.get("schema") == PINS_SCHEMA, "unsupported modern fan pins")
    parts = document.get("parts")
    require(isinstance(parts, list) and parts, "the modern fan pins name no parts")
    teams = {p.get("team") for p in parts}
    require(len(teams) == 32, "the modern fan pins must name all 32 clubs")
    seen = set()
    for p in parts:
        require(set(p) >= {"team", "set", "name", "art", "art_sha256", "outer_index", "outer_id", "chunk_index",
                           "chunk_offset", "span_size", "width", "height", "retail_sha256", "applied_sha256",
                           "palette_max"}, f"modern fan pin incomplete: {p.get('team')} {p.get('name')}")
        require(p["set"] in SETS, f"{p['team']} {p['name']}: unknown crowd set {p['set']}")
        key = (p["outer_id"], p["chunk_index"])
        require(key not in seen, f"{p['team']} {p['name']}: a texture is pinned twice")
        seen.add(key)
    for sc in document.get("scenes", ()):
        require(set(sc) >= {"scene", "outer_index", "outer_id", "chunk_index", "chunk_offset", "span_size",
                            "retail_sha256", "applied_sha256", "palette_max", "textures"}, "modern fan scene pin incomplete")
        for t in sc["textures"]:
            require(set(t) >= {"material", "art", "art_sha256", "width", "height"}, "modern fan scene texture incomplete")
    return document


def pins() -> dict:
    global _PINS
    if _PINS is None:
        _PINS = _check_pins(json.loads(PINS_PATH.read_text(encoding="utf-8")))
    return _PINS


def art_path(part: dict) -> Path:
    return DATA_DIR / part["art"]


def available() -> bool:
    try:
        document = pins()
        for p in list(document["parts"]) + [t for sc in document.get("scenes", ()) for t in sc["textures"]]:
            path = art_path(p)
            if not path.is_file() or sha(path.read_bytes()) != p["art_sha256"]:
                return False
        return True
    except (OSError, ValueError):
        return False


def _rgba(path: Path, width: int, height: int):
    import numpy as np
    from PIL import Image
    require(path.is_file(), f"modern fan art is missing: {path.name}")
    with Image.open(io.BytesIO(path.read_bytes())) as image:
        require(image.size == (width, height), f"{path.name} is {image.size}, the texture needs {width}x{height}")
        return np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()


# --- compile ------------------------------------------------------------------------------------------------------

def _refit(template_span: bytes, decoded: bytes) -> tuple[bytes, dict]:
    """Recompress ``decoded`` into the retail stored span of ``template_span``: wrapper identical, the stream filled
    to within a few bytes of the stored body so the in-place decode stays inside the retail scratch word."""
    tx, fill = _tools()
    fields = tx.HEADER.unpack_from(template_span)
    _kind, stored, system, video, magic, scratch, _r0, _r1 = fields
    require(magic == tx.COMPRESSED_SENTINEL and len(decoded) == system + video, "the crowd texture is not the retail layout")
    chunk = tx.parse_chunks(template_span, allow_trailing=True)[0]
    _tdec, tinfo = tx.decode_chunk(template_span, chunk)
    stream = template_span[tx.HEADER.size:tx.HEADER.size + tinfo.consumed_bytes]
    tag, bits = struct.unpack_from("<I", stream, 4)[0], stream[8]
    candidates = []
    try:
        candidates.append(("greedy", tx.compress_vc_lz(decoded, stream_tag=tag, offset_bits=bits, max_encoded_size=stored,
                                                       verify_roundtrip=True)[0]))
    except tx.TxtrError:
        pass
    last = "no encoder fits the stored body"
    for encoder in ("greedy", "optimal"):
        if encoder == "optimal":
            compressed = fill.compress_optimal(decoded, stream_tag=tag, offset_bits=bits)
            if len(compressed) > stored:
                break
            candidates.append(("optimal", compressed))
        for name, compressed in candidates:
            if name != encoder:
                continue
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
                        "the refit crowd texture failed its independent decode")
                return rebuilt, dict(encoder=encoder, slack=slack, stream_bytes=len(filled), stored_size=stored,
                                     padding_bytes=padding, scratch_needed=need, scratch_retail=scratch,
                                     matches_expanded=expanded)
    raise ModernFansError(f"the crowd texture does not fit its retail span ({last})")


def compose(name: str, rgba, retail_rgba):
    """The texture the Build writes: the shipped art with the retail details of ``KEEP_RECTS`` and, for a face-paint
    layer, the retail head under it, both taken from the disc's own texture (``retail_rgba()``, base level RGBA)."""
    import numpy as np
    if name not in KEEP_RECTS and not name.startswith(OVERLAY_PREFIX):
        return rgba
    retail = np.asarray(retail_rgba(), dtype=np.uint8)
    require(retail.shape == rgba.shape, f"{name}: the retail texture is {retail.shape}, the art {rgba.shape}")
    out = np.array(rgba, dtype=np.uint8)
    if name.startswith(OVERLAY_PREFIX):
        a = out[..., 3:4].astype(np.float64) / 255.0
        mixed = out[..., :3].astype(np.float64) * a + retail[..., :3].astype(np.float64) * (1.0 - a)
        out[..., :3] = np.clip(np.rint(mixed), 0, 255).astype(np.uint8)
        out[..., 3] = retail[..., 3]
        return out
    for x0, y0, x1, y1 in KEEP_RECTS[name]:
        out[y0:y1, x0:x1] = retail[y0:y1, x0:x1]
    return out


def compile_texture(span: bytes, rgba, palette_max: int = 256, *, name: str | None = None) -> tuple[bytes, dict]:
    """A crowd texture TXTR chunk span with ``rgba`` quantised into its own P8 allocation (one level, one palette)
    and refit into the retail stored span."""
    tx, _fill = _tools()
    mm = _mm()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    decoded, _info = tx.decode_chunk(span, chunk)
    texture = tx.parse_texture(decoded, chunk)
    require(chunk.kind == "TXTR" and texture.format_name == "P8" and texture.mip_levels == 1
            and (name is None or texture.name == name), f"not the retail crowd texture {name}")
    row = dict(width=texture.width, height=texture.height, mip_levels=1, pixel_offset=texture.pixel_offset,
               palette_offset=texture.palette_offset, mapped_material_names=[texture.name])
    rgba = compose(texture.name, rgba, lambda: mm.read_p8(decoded, chunk.system_bytes, row)[0])
    edited = bytearray(decoded)
    colours = mm.write_p8(edited, chunk.system_bytes, row, rgba, maximum=int(palette_max))
    require(bytes(edited[:chunk.system_bytes]) == bytes(decoded[:chunk.system_bytes]), "the texture header changed")
    rebuilt, fit = _refit(span, bytes(edited))
    return rebuilt, dict(texture=texture.name, texture_size=[texture.width, texture.height], palette_max=int(palette_max),
                         palette_entries=int(colours), fit=fit)


def compile_scene(span: bytes, pin: dict) -> tuple[bytes, dict]:
    """A close-up crowd scene's SCNE chunk span with the authored embedded textures of ``pin`` written in and refit
    into the retail stored span."""
    tx, _fill = _tools()
    mm = _mm()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    rec, decoded = mm._scene(span, chunk)
    require(chunk.kind == "SCNE" and rec.get("name") == pin["scene"], f"{pin['scene']}: not the retail crowd scene")
    rows = {}
    for tex in rec["embedded_textures"]:
        for material in tex.get("mapped_material_names") or ():
            rows.setdefault(material, tex)
    edited = bytearray(decoded)
    detail = {}
    for t in pin["textures"]:
        tex = rows.get(t["material"])
        require(tex is not None and tex.get("format_name") == "P8" and (int(tex["width"]), int(tex["height"]))
                == (int(t["width"]), int(t["height"])), f"{pin['scene']}: no {t['material']} texture of the pinned size")
        colours = mm.write_p8(edited, chunk.system_bytes, tex, _rgba(art_path(t), int(t["width"]), int(t["height"])),
                              maximum=int(pin["palette_max"]))
        detail[t["material"]] = dict(texture_index=int(tex["index"]), palette_entries=int(colours))
    rebuilt, fit = _refit(span, bytes(edited))
    return rebuilt, dict(scene=pin["scene"], palette_max=int(pin["palette_max"]), textures=detail, fit=fit)


def compile_part(span: bytes, part: dict) -> tuple[bytes, dict]:
    rgba = _rgba(art_path(part), int(part["width"]), int(part["height"]))
    return compile_texture(span, rgba, int(part["palette_max"]), name=part["name"])


# --- the disc ----------------------------------------------------------------------------------------------------

def _locate(archive, entries: dict, part: dict, cache: dict) -> tuple[int, bytes]:
    """(virtual offset, span) of a pinned crowd texture, through the copy's own outer and chunk tables."""
    tx, _fill = _tools()
    outer_id = int(part["outer_id"], 16)
    if outer_id not in cache:
        entry = entries.get(outer_id)
        require(entry is not None, f"crowd texture set {part['outer_id']} ({part['team']} {part['set']}) is not on this disc")
        raw = archive.read(entry.virtual_offset, entry.size)
        cache[outer_id] = (entry, raw, tx.parse_chunks(raw))
    entry, raw, chunks = cache[outer_id]
    require(len(chunks) > part["chunk_index"], f"{part['team']} {part['set']}: the crowd set has no chunk {part['chunk_index']}")
    chunk = chunks[part["chunk_index"]]
    require(chunk.kind == "TXTR" and chunk.offset == part["chunk_offset"]
            and 0x20 + chunk.stored_size == part["span_size"], f"{part['team']} {part['set']} {part['name']}: not the retail layout")
    return entry.virtual_offset + chunk.offset, raw[chunk.offset:chunk.offset + part["span_size"]]


def _locate_scene(archive, entries: dict, pin: dict, cache: dict) -> tuple[int, bytes]:
    tx, _fill = _tools()
    outer_id = int(pin["outer_id"], 16)
    if outer_id not in cache:
        entry = entries.get(outer_id)
        require(entry is not None, f"crowd cutscene {pin['outer_id']} ({pin['scene']}) is not on this disc")
        raw = archive.read(entry.virtual_offset, entry.size)
        cache[outer_id] = (entry, raw, tx.parse_chunks(raw))
    entry, raw, chunks = cache[outer_id]
    require(len(chunks) > pin["chunk_index"], f"{pin['scene']}: the cutscene has no chunk {pin['chunk_index']}")
    chunk = chunks[pin["chunk_index"]]
    require(chunk.kind == "SCNE" and chunk.offset == pin["chunk_offset"]
            and 0x20 + chunk.stored_size == pin["span_size"], f"{pin['scene']}: not the retail layout")
    return entry.virtual_offset + chunk.offset, raw[chunk.offset:chunk.offset + pin["span_size"]]


def _parts(archive, document: dict) -> list[dict]:
    entries = {e.name_id: e for e in archive.entries}
    cache: dict = {}
    out = []
    for pin in document.get("scenes", ()):
        at, span = _locate_scene(archive, entries, pin, cache)
        digest = sha(span)
        state = "retail" if digest == pin["retail_sha256"] else "applied" if digest == pin["applied_sha256"] else "foreign"
        out.append(dict(kind="scene", key=f"scene:{pin['scene']}:{pin['outer_index']}", at=at, size=len(span),
                        state=state, row=pin, span=span))
    for part in document["parts"]:
        at, span = _locate(archive, entries, part, cache)
        digest = sha(span)
        state = "retail" if digest == part["retail_sha256"] else "applied" if digest == part["applied_sha256"] else "foreign"
        out.append(dict(kind="texture", key=f"{part['team']}:{part['set']}:{part['name']}", at=at, size=len(span),
                        state=state, row=part, span=span))
    return out


def resource_states(source, *, document: dict | None = None) -> dict[str, str]:
    document = pins() if document is None else _check_pins(document)
    with _outer_image()(source) as archive:
        return {p["key"]: p["state"] for p in _parts(archive, document)}


def image_status(source, *, document: dict | None = None) -> str:
    """'retail', 'applied', 'mixed' (some parts each) or 'foreign' (a crowd texture is neither)."""
    values = set(resource_states(source, document=document).values())
    if "foreign" in values:
        return "foreign"
    if values == {"retail"}:
        return "retail"
    if values == {"applied"}:
        return "applied"
    return "mixed"


def _write_all(archive, plan: list[tuple[int, bytes, bytes]]) -> None:
    written: list[tuple[int, bytes]] = []
    try:
        for at, before, after in plan:
            require(archive.read(at, len(before)) == before, "a crowd texture changed after preflight")
            # fx1 (review pr69 nit): record the span before writing it, so a short or failing write is restored too
            written.append((at, before))
            require(archive.write(at, after) == len(after), "short crowd texture write")
            require(archive.read(at, len(after)) == after, "crowd texture read-back differs")
    except BaseException:
        # best effort per span: one failed restore neither stops the others nor hides the first error
        for at, before in reversed(written):
            try:
                archive.write(at, before)
            except Exception:  # noqa: BLE001 - the original error is the one raised
                pass
        raise


def plan_image(source, *, document: dict | None = None, progress=None) -> tuple[list, list[dict]]:
    """Compile every retail part of ``source`` (read only): ([(virtual offset, before, after)], receipt rows)."""
    document = pins() if document is None else _check_pins(document)
    say = progress or (lambda message, done, total: None)
    plan, rows = [], []
    compiled: dict = {}
    with _outer_image()(source) as archive:
        parts = _parts(archive, document)
        require(all(p["state"] != "foreign" for p in parts),
                "a crowd texture is neither the retail nor the 2026 bytes; rebuild from a supported USA source")
        for index, part in enumerate(parts):
            row = part["row"]
            out = dict(kind=part["kind"], key=part["key"], team=row.get("team"), set=row.get("set"),
                       name=row.get("name", row.get("scene")), virtual_offset=part["at"], size=part["size"],
                       state_before=part["state"])
            if part["state"] == "retail" and part["kind"] == "scene":
                before = part["span"]
                after, detail = compile_scene(before, row)
                require(sha(after) == row["applied_sha256"], f"{part['key']}: the compiled scene differs from its pin")
                plan.append((part["at"], before, after))
                out.update(written=True, before_sha256=sha(before), after_sha256=sha(after),
                           changed_bytes=sum(a != b for a, b in zip(before, after)), **detail)
            elif part["state"] == "retail":
                if index % 64 == 0:
                    say(f"2026 fans: {row['team']}", index, len(parts))
                before = part["span"]
                # identical retail spans compile identically: reuse the compile for the other set copies
                memo = (row["retail_sha256"], row["art_sha256"], int(row["palette_max"]))
                if memo not in compiled:
                    compiled[memo] = compile_part(before, row)
                after, detail = compiled[memo]
                require(sha(after) == row["applied_sha256"], f"{part['key']}: the compiled texture differs from its pin")
                plan.append((part["at"], before, after))
                out.update(written=True, before_sha256=sha(before), after_sha256=sha(after),
                           changed_bytes=sum(a != b for a, b in zip(before, after)), **detail)
            else:
                out.update(written=False, changed_bytes=0)
            rows.append(out)
    return plan, rows


def apply_to_image(target, *, document: dict | None = None, progress=None) -> dict[str, Any]:
    """Build-only: ``target`` is the caller's disposable output image. Retail or already-2026 parts only."""
    document = pins() if document is None else _check_pins(document)
    plan, rows = plan_image(target, document=document, progress=progress)
    with _outer_image()(target, writable=True) as archive:
        _write_all(archive, plan)
    state = image_status(target, document=document)
    require(state == "applied", f"the 2026 fans failed their read-back on the copy ({state})")
    return dict(label=LABEL, option=BUILD_KEY, state=state, runtime_witnessed=False, written=len(plan),
                already_applied=len(rows) - len(plan), changed_bytes=sum(r["changed_bytes"] for r in rows),
                parts=len(rows))


def verify(source, *, enabled: bool = True, document: dict | None = None) -> dict[str, Any]:
    state = image_status(source, document=document)
    require(state == ("applied" if enabled else "retail"), "the 2026 fans do not match the request")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False)


# --- pins (development) ------------------------------------------------------------------------------------------

def record_pins(retail_image, art_dir: Path, codes: dict, order: list, *, progress=None) -> dict:
    """The pin document from a retail USA image and the shipped art: every set copy of every authored texture, its
    retail and compiled digests, and the largest palette (from PALETTE_LADDER) whose compile fits the retail span."""
    tx, _fill = _tools()
    say = progress or (lambda message: None)
    parts = []
    memo: dict = {}
    with _outer_image()(retail_image) as archive:
        for team, code in codes.items():
            index = order.index(code)
            names = sorted(p.stem for p in (art_dir / team).glob("*.png"))
            for set_name, base in SETS.items():
                entry = archive.entries[base + index]
                raw = archive.read(entry.virtual_offset, entry.size)
                for chunk in tx.parse_chunks(raw):
                    if chunk.kind != "TXTR":
                        continue
                    span = raw[chunk.offset:chunk.offset + 0x20 + chunk.stored_size]
                    decoded, _info = tx.decode_chunk(span, tx.parse_chunks(span, allow_trailing=True)[0])
                    texture = tx.parse_texture(decoded, tx.parse_chunks(span, allow_trailing=True)[0])
                    if texture.name not in names:
                        continue
                    art = f"{team}/{texture.name}.png"
                    rgba = _rgba(DATA_DIR / art, texture.width, texture.height)
                    key = (sha(span), sha((DATA_DIR / art).read_bytes()))
                    if key not in memo:
                        last = None
                        for palette_max in PALETTE_LADDER:
                            try:
                                memo[key] = (palette_max,) + compile_texture(span, rgba, palette_max, name=texture.name)
                                break
                            except ModernFansError as exc:
                                last = exc
                        else:
                            raise ModernFansError(f"{team} {set_name} {texture.name}: no palette fits ({last})")
                    palette_max, after, detail = memo[key]
                    parts.append(dict(team=team, code=code, set=set_name, name=texture.name, art=art,
                                      art_sha256=sha((DATA_DIR / art).read_bytes()), outer_index=entry.index,
                                      outer_id=f"0x{entry.name_id:08x}", outer_size=entry.size,
                                      chunk_index=chunk.index, chunk_offset=chunk.offset, span_size=len(span),
                                      width=texture.width, height=texture.height, retail_sha256=sha(span),
                                      applied_sha256=sha(after), palette_max=palette_max,
                                      palette_entries=detail["palette_entries"], fit=detail["fit"]))
                    say(f"{team} {set_name} {texture.name} palette {palette_max}")
    return dict(schema=PINS_SCHEMA, sets=SETS, parts=parts)


def record_scene_pins(retail_image, scene_specs: list[dict]) -> list[dict]:
    """Pins for the scenes with embedded textures: ``scene_specs`` rows {scene, team, textures: [{material, art}]};
    every retail copy of the scene (all cutscene archives that hold it) is pinned."""
    tx, _fill = _tools()
    mm = _mm()
    out = []
    with _outer_image()(retail_image) as archive:
        for entry in archive.entries:
            if not (2500 <= entry.index <= 2950):   # the cutscene archives of the crowd reactions
                continue
            raw = archive.read(entry.virtual_offset, entry.size)
            try:
                chunks = tx.parse_chunks(raw)
            except Exception:  # noqa: BLE001 - not a chunked archive
                continue
            for chunk in chunks:
                if chunk.kind != "SCNE":
                    continue
                spec = None
                span = raw[chunk.offset:chunk.offset + 0x20 + chunk.stored_size]
                try:
                    rec, _decoded = mm._scene(span, tx.parse_chunks(span, allow_trailing=True)[0])
                except Exception:  # noqa: BLE001
                    continue
                spec = next((s for s in scene_specs if s["scene"] == rec.get("name")), None)
                if spec is None:
                    continue
                textures = []
                rows = {}
                for tex in rec["embedded_textures"]:
                    for material in tex.get("mapped_material_names") or ():
                        rows.setdefault(material, tex)
                for t in spec["textures"]:
                    tex = rows[t["material"]]
                    textures.append(dict(material=t["material"], art=t["art"],
                                         art_sha256=sha((DATA_DIR / t["art"]).read_bytes()),
                                         width=int(tex["width"]), height=int(tex["height"])))
                pin = dict(scene=spec["scene"], team=spec.get("team"), outer_index=entry.index,
                           outer_id=f"0x{entry.name_id:08x}", chunk_index=chunk.index, chunk_offset=chunk.offset,
                           span_size=len(span), retail_sha256=sha(span), textures=textures)
                last = None
                for palette_max in PALETTE_LADDER:
                    try:
                        after, detail = compile_scene(span, dict(pin, palette_max=palette_max))
                        break
                    except ModernFansError as exc:
                        last = exc
                else:
                    raise ModernFansError(f"{spec['scene']} in outer {entry.index}: no palette fits ({last})")
                out.append(dict(pin, palette_max=palette_max, applied_sha256=sha(after), fit=detail["fit"]))
    return out


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="2026 fans in the crowd cutaways: inspect a disc image (read only)")
    parser.add_argument("image")
    args = parser.parse_args(argv)
    print(json.dumps(dict(state=image_status(args.image)), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
