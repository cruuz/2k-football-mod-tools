"""Modern head coaches: the 2026 head coach of every club on the sideline and in the Coach Matchup / VIP pictures.

Every club's head coach is one model, ``cNN.iff`` (NN = the club's 2K5 asset code, the coach record's ``+0x18`` body
id: ``c00.iff`` Arizona ... ``c30.iff`` Cleveland, ``c37.iff`` Houston), chunk 0, scene ``coach``: three shapes
(``coachBodyGrp1``, ``coachLodGrp1``, ``coachHeadGrp1``) and nine embedded P8 textures. Five of them carry the look
this option changes, each refit in place at its retail size and format (full mip chain, one 256-entry palette):

* ``shirtShader1`` (128x128): the polo / quarter-zip in the 2026 top colour, thin trims in the accent; the cap the
  capped coaches wear (``hatShader1``) samples the patch u 0.83-0.99, v 0.00-0.17 of this texture, painted in the
  cap colour. Fabric folds keep the retail shading.
* ``jacketShader1`` (128x128): the full-zip sideline jacket in the same colours.
* ``shirtLogoShader1`` / ``jacketLogoShader1`` (one 64x64 texture): the chest mark becomes the club's 2026 logo
  (the 2004 maker mark is gone). The other chest logo and the cap logo (``teamLogoShader1``, ``hatLogoShader1``)
  have no embedded texture: the game binds them at run time and this option does not touch them.
* ``accessoriesShader1`` (128x64): the headset half (x < 64) becomes an unbranded matte black headset (the 2004
  earcup and band marks are gone). Only that half ships (``headset.png``, 64x64). The shoe and clipboard half
  (x >= 64) is derived at build time from the user's own disc texture (``derive_accessories``: the same 4x bicubic
  master round trip the art was authored through, in integer arithmetic), so no retail pixels ship and the disc
  bytes are those of the earlier full-atlas PNG.
* ``headShader1`` (256x128): the 2026 coach's face, painted from his official headshot onto the coach head layout
  (landmark warp, his skin tone over the whole head, his hair colour or a shaved head).

The sideline staff (the ``coach_asst`` people along the sideline, gamedata.iff; one material ``SIDELINE`` with no
embedded texture) wear the club's ``coachshirt`` texture, a standalone 256x256 P8 TXTR chunk (six mips) in each of the
club's eight team packages (``{code}{h,a}{d,r}{n,s}.iff``): the polo in the d packages, the jacket in the r packages.
Each is refit in place in the same colours as the head coach.

The geometry, the skin, the animations, the other four textures, the wrapper and every byte outside chunk 0's span
are retail; each scene is refit into its retail stored span with the 32-byte wrapper identical and the in-place
decode inside the retail scratch allowance (the stream is filled to within six bytes of the stored body).

The pictures: the Coach Matchup screen and the VIP viewer draw the PORTRAIT texture named by the decimal of the
coach record's ``+0x40``. The 2026 portraits of 30 coaches ride with the 2026 league art (the team projects); Dallas
(7007) and Washington (7029) have no such texture on the disc, so the game shows ``nophoto``. This option writes the
2026 Dallas and Washington head coaches into two retail portrait slots no roster record uses (7031 and 7034, P8
128x128, raw fixed spans) and points those two coach records' ``+0x40`` at them (two 16-bit writes in the main
roster). A roster whose Dallas or Washington coach already names another picture keeps it. The two pictures are
authored renders of the game's own coach (b77 co3; see the data README), and a slot that holds the earlier picture
(``superseded_sha256``) is rewritten in place.

The bodies (b77 co2): the game builds the coach archive name from the coach record's ``+0x18`` (``swprintf``
``L"c%02d.iff"`` over its low 16 bits, home and away, for the sideline coach and every cutscene coach). Where another
retail body fits the 2026 coach better, this option points the club's record at it: the 32 club models are permuted
(``body_code`` per club; a 16-bit write at ``+0x18`` of the coach record, nothing else in the record changes) and each
model's textures are authored for its new occupant. Kansas City's Andy Reid wears the retail 2004 Reid model (``c21``,
Philadelphia's in 2004): its own body, head mesh and face texture, his hair and moustache moved to white and grey and
his glasses painted on (the model has no glasses geometry). That face is derived at build time from the disc's own
texture (an authored weight mask and glasses overlay, integer arithmetic), so no retail pixels ship.

Coach models (b77 cm1): where the 2004 model cannot reach the 2026 coach by texture alone, ``<club>/geometry.json``
moves the scene's own vertices (``apply_geometry``: integer positions and normals of the vertices that move, refused on
any mesh but the one each shape was authored on). Washington's Dan Quinn has a bald head (the 2004 hair volume off the
scalp; the headset band and the low-detail head follow); eight lean coaches (CIN, CAR, GB, TEN, LAR, SF, MIN, JAX) wear
the lean body of a leaner retail coach. The vertex count, triangles, skin weights, skeleton and animations
are retail. Their heads, and those of DAL, NYJ, TB, MIA, DET, CLE, NE, ATL and NYG, are painted on the head mesh in
3D (one skin tone, painted hair and facial hair).

EXPERIMENTAL and UNWITNESSED: proved offline (decoded textures, byte receipts, renders from the data); the look in
the game is for Noah's eyes.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import struct
import sys
from typing import Any

OWNER = "nfl2k5_modern_coaches"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_KEY = "modern_coaches"
BUILD_CAPTION = "2026 head coaches (sideline look and faces)"
HELP_TEXT = (
    "Dresses every club's head coach on the sideline in his 2026 look: the club's 2026 colours on his polo, jacket "
    "and cap, the 2026 logo on his chest, a modern black headset, and his own face from his official headshot, "
    "blended onto the game's coach head. Each coach stands on the game's coach body closest to his build (lean "
    "coaches on a lean body), Washington's Dan Quinn has a bald head, and Kansas City's Andy Reid wears the game's own 2004 Andy Reid model with today's white hair and glasses. His "
    "sideline staff wear the same 2026 colours. Dallas and Washington also get their 2026 head coach's picture on "
    "the Coach Matchup screen (the 2004 disc has none for them). The animations are the game's own. Experimental: "
    "not yet seen in the game by the SOFTDRINK tester."
)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_modern_coaches"
PINS_PATH = DATA_DIR / "pins.json"
PINS_SCHEMA = "nfl2k5_modern_coaches_pins/v1"
# texture file -> the material whose embedded texture it replaces
TEXTURES = (("shirt", "shirtShader1"), ("jacket", "jacketShader1"), ("logo", "shirtLogoShader1"),
            ("headset", "accessoriesShader1"), ("head", "headShader1"))
# b77-co3: the accessories atlas (128x64): the authored headset half ships (headset.png, 64x64); the shoe and clipboard
# half is derived from the disc's own texture at build time (derive_accessories)
HEADSET_WIDTH = 64
ACCESSORIES_SIZE = (128, 64)
# the sideline staff (coach_asst, material SIDELINE) wear the club's coachshirt texture from its eight team packages
SIDELINE = (("d", "sideline_dry"), ("r", "sideline_rain"))
PACKAGES = tuple(f"{side}{weather}{light}" for side in "ha" for weather in "dr" for light in "ns")
ART_NAMES = tuple(name for name, _m in TEXTURES) + tuple(name for _w, name in SIDELINE)
# b77-co2: a head derived at build time from the model's own retail head texture (Reid on c21): an authored weight mask
# (R = weight 0..255, G = class * 80) and an authored RGBA overlay ship instead of head.png
HEAD_RECIPE_FILES = ("head_mask", "head_overlay")
# the coach record field that names the coach model (``c%02d.iff`` of its low 16 bits)
BODY_FIELD = 0x18
FILL_SLACKS = (0, 1, 2, 4, 6)
# Six 2004 coach models wear glasses on the body mesh (z_eyeShadowShader1 primitives on coachBodyGrp1: GB, KC, LAR,
# LAC, SEA, WAS); the head mesh's own z_eyeShadowShader1 strip samples only u 0.01-0.04 of the same 64x64 texture.
# The 2026 coaches of GB (LaFleur), LAR (McVay), SEA (Macdonald) and WAS (Quinn) do not wear glasses: their texture
# keeps its first GLASSES_KEEP_COLUMNS columns (the head strip) and is clear everywhere else, derived at build time
# from the disc's own texture (no retail pixels ship). Reid (KC) and Harbaugh (LAC) keep theirs.
GLASSES_MATERIAL = "z_eyeShadowShader1"
GLASSES_KEEP_COLUMNS = 4
# palette sizes tried in turn by record_pins when a coach's new art does not fit its retail span at 256 colours; the
# chosen size is pinned per club (``palette_max``) so a build compiles it directly
PALETTE_LADDER = (256, 192, 128, 96, 64)
PORTRAIT_HEADER = 0x20
# b77 cm1: a club whose look the 2004 model cannot reach by texture alone ships authored vertex edits for its coach
# scene (``<club>/geometry.json``): new fixed-point positions and shading normals for the vertices that move, on the
# scene's own shapes (same vertex count, same triangles, same skin and animations; nothing is added or removed)
GEOMETRY_SCHEMA = "nfl2k5_coach_geometry/v1"
GEOMETRY_FILE = "geometry.json"
GEOMETRY_SHAPES = ("coachBodyGrp1", "coachLodGrp1", "coachHeadGrp1")


class ModernCoachesError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ModernCoachesError(message)


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


def name_id(name: str) -> int:
    return _mm().name_id(name)


# --- pins and art -----------------------------------------------------------------------------------------------

_PINS: dict | None = None


def _check_pins(document: dict) -> dict:
    require(isinstance(document, dict) and document.get("schema") == PINS_SCHEMA, "unsupported modern coach pins")
    teams = document.get("teams")
    require(isinstance(teams, list) and len(teams) == 32, "the modern coach pins must name all 32 clubs")
    for row in teams:
        require(set(row) >= {"team", "code", "archive", "retail_sha256", "applied_sha256", "span_offset", "span_size",
                             "art"}, f"modern coach pin row incomplete: {row.get('team')}")
        require(set(row["art"]) == set(art_names(row)), f"{row['team']}: the art set is incomplete")
        require(str(row.get("team_code", "")).isdigit() and str(row.get("body_code", "")).isdigit()
                and row["archive"] == f"c{row['body_code']}.iff", f"{row['team']}: the coach body is not named")
        require(len(row.get("sideline", ())) == len(PACKAGES), f"{row['team']}: the sideline packages are incomplete")
        require("geometry" not in row or (isinstance(row["geometry"], str) and len(row["geometry"]) == 64),
                f"{row['team']}: the geometry pin is malformed")
    bodies = [row["body_code"] for row in teams]
    require(len(set(bodies)) == len(bodies), "two clubs name the same coach body")
    for row in document.get("portraits", ()):
        require(set(row) >= {"team", "portrait_id", "retail_photo_id", "outer_index", "chunk_offset", "span_size",
                             "retail_sha256", "applied_sha256", "png", "png_sha256"}, "modern coach portrait pin incomplete")
    return document


def pins() -> dict:
    global _PINS
    if _PINS is None:
        require(PINS_PATH.is_file(), "the modern coach pins are missing from this build")
        _PINS = _check_pins(json.loads(PINS_PATH.read_text(encoding="utf-8")))
    return _PINS


def art_names(row: dict) -> tuple[str, ...]:
    """The PNG names a pin row ships: the standard set, or the head recipe files in place of head.png."""
    if row.get("head_recipe"):
        return tuple(n for n in ART_NAMES if n != "head") + HEAD_RECIPE_FILES
    return ART_NAMES


def derive_head(retail_rgba, mask_rgb, classes: dict, overlay_rgba=None):
    """A head texture derived from the model's own retail head (integer arithmetic only, so every platform builds the
    same bytes): in each masked pixel the colour moves toward ``base + (luma - ref) * gain16 // 16 + tint`` of its class
    (the 2004 strands and shading are kept, only the colour changes), weighted by the mask; then the authored overlay
    is composited by its alpha."""
    import numpy as np
    src = np.asarray(retail_rgba, np.int64)
    rgb = src[..., :3]
    luma = (rgb[..., 0] * 299 + rgb[..., 1] * 587 + rgb[..., 2] * 114 + 500) // 1000
    m = np.asarray(mask_rgb, np.int64)
    weight = m[..., 0]
    cls = (m[..., 1] + 40) // 80
    target = rgb.copy()
    for key, (base, ref, gain16, tint) in sorted(classes.items(), key=lambda kv: int(kv[0])):
        sel = cls == int(key)
        grey = int(base) + ((luma - int(ref)) * int(gain16)) // 16
        for k in range(3):
            target[..., k] = np.where(sel, np.clip(grey + int(tint[k]), 0, 255), target[..., k])
    out = (rgb * (255 - weight[..., None]) + target * weight[..., None] + 127) // 255
    if overlay_rgba is not None:
        ov = np.asarray(overlay_rgba, np.int64)
        alpha = ov[..., 3:4]
        out = (out * (255 - alpha) + ov[..., :3] * alpha + 127) // 255
    return np.uint8(np.concatenate([out, src[..., 3:4]], axis=-1))


# --- the accessories atlas: authored headset, shoe and clipboard from the user's disc -----------------------------
#
# The art was authored at 4x (co1_coach_art.py): the retail atlas upscaled with a bicubic filter (Pillow's: a = -0.5,
# support 2, coefficients normalised and rounded to 22-bit fixed point, horizontal pass then vertical pass, each
# rounded and clamped to 8 bits), the headset half painted over, then every 4x4 block averaged (round half to even).
# derive_accessories reproduces the shoe and clipboard half of that round trip from the disc's own texture with
# Python floats for the coefficients (one IEEE operation at a time, in Pillow's order) and integers for the pixels,
# so every platform builds the same bytes without Pillow's resampler.

_FIXED_BITS = 22
_UPSCALE = 4


def _bicubic(x: float) -> float:
    a = -0.5
    if x < 0.0:
        x = -x
    if x < 1.0:
        return ((a + 2.0) * x - (a + 3.0)) * x * x + 1
    if x < 2.0:
        return (((x - 5) * x + 8) * x - 4) * a
    return 0.0


def _bicubic_coefficients(in_size: int, out_size: int) -> list[tuple[int, list[int]]]:
    """Per output index: (first input index, fixed-point weights), as Pillow's precompute_coeffs and
    normalize_coeffs_8bpc compute them for an upscale (filter scale 1)."""
    scale = float(in_size) / out_size
    filterscale = max(scale, 1.0)
    support = 2.0 * filterscale
    rows = []
    for xx in range(out_size):
        center = (xx + 0.5) * scale
        ss = 1.0 / filterscale
        xmin = max(int(center - support + 0.5), 0)
        xmax = min(int(center + support + 0.5), in_size) - xmin
        weights = [_bicubic((x + xmin - center + 0.5) * ss) for x in range(xmax)]
        total = 0.0
        for w in weights:                       # sequential, as the C loop (not Python's compensated sum())
            total += w
        if total != 0.0:
            weights = [w / total for w in weights]
        rows.append((xmin, [int(-0.5 + w * (1 << _FIXED_BITS)) if w < 0 else int(0.5 + w * (1 << _FIXED_BITS))
                            for w in weights]))
    return rows


def _resample_rows(pixels, coefficients):
    """One 8-bit resampling pass along axis 1 of an (H, W, C) int64 array."""
    import numpy as np
    out = np.empty((pixels.shape[0], len(coefficients), pixels.shape[2]), np.int64)
    for xx, (xmin, weights) in enumerate(coefficients):
        acc = np.full((pixels.shape[0], pixels.shape[2]), 1 << (_FIXED_BITS - 1), np.int64)
        for j, w in enumerate(weights):
            acc += pixels[:, xmin + j, :] * w
        out[:, xx, :] = np.clip(acc >> _FIXED_BITS, 0, 255)
    return out


def bicubic_upscale(rgba, factor: int = _UPSCALE):
    """An opaque RGBA texture upscaled ``factor`` times with Pillow's bicubic filter, in integers."""
    import numpy as np
    src = np.asarray(rgba, np.int64)
    height, width = src.shape[:2]
    wide = _resample_rows(src, _bicubic_coefficients(width, width * factor))
    tall = _resample_rows(wide.transpose(1, 0, 2), _bicubic_coefficients(height, height * factor))
    return tall.transpose(1, 0, 2)


def block_mean(master, factor: int = _UPSCALE):
    """Every ``factor`` x ``factor`` block averaged, rounded half to even (the art's area downscale of opaque art)."""
    import numpy as np
    m = np.asarray(master, np.int64)
    h, w = m.shape[0] // factor, m.shape[1] // factor
    total = m.reshape(h, factor, w, factor, m.shape[2]).sum(axis=(1, 3))
    n = factor * factor
    q, r = np.divmod(total, n)
    return np.uint8(q + ((2 * r > n) | ((2 * r == n) & (q % 2 == 1))))


def derive_accessories(retail_rgba, headset_rgba):
    """The 128x64 accessories atlas: the authored headset (x < 64) beside the shoe and clipboard (x >= 64) derived from
    the model's own retail atlas through the 4x round trip the art was authored with."""
    import numpy as np
    retail = np.asarray(retail_rgba, np.uint8)
    headset = np.asarray(headset_rgba, np.uint8)
    width, height = ACCESSORIES_SIZE
    require(retail.shape == (height, width, 4), "the coach accessories texture is not the retail 128x64 atlas")
    require(headset.shape == (height, HEADSET_WIDTH, 4), "the authored headset is not 64x64")
    require(int(retail[..., 3].min()) == 255, "the coach accessories texture is not the opaque retail atlas")
    derived = block_mean(bicubic_upscale(retail))
    return np.concatenate([headset, derived[:, HEADSET_WIDTH:]], axis=1)


def art_path(team: str, name: str) -> Path:
    return DATA_DIR / team / f"{name}.png"


def geometry_path(team: str) -> Path:
    return DATA_DIR / team / GEOMETRY_FILE


# --- authored geometry: new positions and normals for the vertices that move --------------------------------------
#
# ``<club>/geometry.json`` (b77 cm1): {"schema", "archive", "shapes": [{"name", "vertex_count", "lanes_sha256",
# "positions": [[vertex, x, y, z], ...], "normals": [[vertex, word], ...]}]}. ``x y z`` are the shape's NORMSHORT3
# lane values (its retail scale and offset at record +0x10 / +0x20 are kept) and ``word`` its NORMPACKED3 normal.
# ``lanes_sha256`` is the digest of the shape's retail position and normal lanes (every vertex, in order: six position
# bytes then four normal bytes), so an edit only ever lands on the mesh it was authored for. The values are integers:
# every platform writes the same bytes, and only the listed vertices change.

def _geometry_lanes(rec: dict, decoded, name: str):
    from . import nfl2k5_models as models
    shapes = [s for s in rec["shapes"] if str(s["name"]) == name and int(s["vertex_count"]) > 0]
    require(len(shapes) == 1, f"the coach scene has no single shape {name}")
    shape = shapes[0]
    lanes = models._shape_lanes(rec, shape, bytes(decoded))
    require(lanes.position_format == "NORMSHORT3" and lanes.normal is not None,
            f"{name}: not the retail NORMSHORT3 / NORMPACKED3 lane layout")
    position_base = models._stream_base({}, shape, lanes.position_stream)
    normal_base = models._stream_base({}, shape, lanes.normal[0])

    def position_at(vertex: int) -> int:
        return position_base + vertex * lanes.position_stride + lanes.position_offset

    def normal_at(vertex: int) -> int:
        return normal_base + vertex * lanes.normal[2] + lanes.normal[1]
    return lanes, position_at, normal_at


def geometry_lanes_digest(rec: dict, decoded, name: str) -> str:
    """SHA-256 of one shape's position and normal lanes (every vertex in order: 6 position bytes, 4 normal bytes)."""
    lanes, position_at, normal_at = _geometry_lanes(rec, decoded, name)
    h = hashlib.sha256()
    for vertex in range(lanes.vertex_count):
        h.update(bytes(decoded[position_at(vertex):position_at(vertex) + 6]))
        h.update(bytes(decoded[normal_at(vertex):normal_at(vertex) + 4]))
    return h.hexdigest()


def load_geometry(row: dict) -> dict:
    path = geometry_path(row["team"])
    require(path.is_file(), f"{row['team']}: the coach geometry is missing from this build")
    payload = path.read_bytes()
    require(sha(payload) == row["geometry"], f"{row['team']}: the coach geometry differs from its pin")
    document = json.loads(payload.decode("utf-8"))
    require(document.get("schema") == GEOMETRY_SCHEMA and document.get("archive") == row["archive"],
            f"{row['team']}: the coach geometry is not for {row['archive']}")
    return document


def apply_geometry(edited: bytearray, rec: dict, document: dict) -> dict:
    """Write the authored positions and normals of ``document`` into the decoded coach scene ``edited`` (in place).
    Refuses a shape whose vertex count or retail lanes differ from the ones the edit was authored on."""
    require(document.get("schema") == GEOMETRY_SCHEMA, "unsupported coach geometry")
    detail = {}
    for item in document["shapes"]:
        name = str(item["name"])
        require(name in GEOMETRY_SHAPES, f"the coach geometry names an unknown shape {name}")
        lanes, position_at, normal_at = _geometry_lanes(rec, edited, name)
        require(lanes.vertex_count == int(item["vertex_count"]), f"{name}: the vertex count differs from the edit's")
        require(geometry_lanes_digest(rec, edited, name) == item["lanes_sha256"],
                f"{name}: the mesh is not the one the coach geometry was authored on")
        seen = set()
        for vertex, x, y, z in item["positions"]:
            require(0 <= vertex < lanes.vertex_count and vertex not in seen
                    and all(-32768 <= int(v) <= 32767 for v in (x, y, z)), f"{name}: bad position row {vertex}")
            seen.add(vertex)
            struct.pack_into("<3h", edited, position_at(vertex), int(x), int(y), int(z))
        seen = set()
        for vertex, word in item["normals"]:
            require(0 <= vertex < lanes.vertex_count and vertex not in seen and 0 <= int(word) <= 0xFFFFFFFF,
                    f"{name}: bad normal row {vertex}")
            seen.add(vertex)
            struct.pack_into("<I", edited, normal_at(vertex), int(word))
        detail[name] = dict(positions=len(item["positions"]), normals=len(item["normals"]),
                            vertex_count=lanes.vertex_count)
    return detail


def available() -> bool:
    """The pins load and every shipped texture matches its pin."""
    try:
        document = pins()
        for row in document["teams"]:
            for name, digest in row["art"].items():
                path = art_path(row["team"], name)
                if not path.is_file() or sha(path.read_bytes()) != digest:
                    return False
            if row.get("geometry"):
                path = geometry_path(row["team"])
                if not path.is_file() or sha(path.read_bytes()) != row["geometry"]:
                    return False
        for row in document.get("portraits", ()):
            path = DATA_DIR / row["png"]
            if not path.is_file() or sha(path.read_bytes()) != row["png_sha256"]:
                return False
        return True
    except (OSError, ValueError):
        return False


def _rgba(path: Path, width: int, height: int):
    import numpy as np
    from PIL import Image
    require(path.is_file(), f"modern coach art is missing: {path.name}")
    with Image.open(io.BytesIO(path.read_bytes())) as image:
        require(image.size == (width, height), f"{path.name} is {image.size}, the texture needs {width}x{height}")
        return np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()


# --- the coach scene ---------------------------------------------------------------------------------------------

def _refit(template_span: bytes, decoded: bytes) -> tuple[bytes, dict]:
    """Recompress ``decoded`` into the retail stored span of ``template_span``, wrapper identical, filled to within a
    few bytes of the stored body so the in-place decode stays inside the retail scratch word (nfl_vc_lz_fill's own
    16-byte slack leaves the coach scenes 8 to 10 bytes over it)."""
    tx, fill = _tools()
    fields = tx.HEADER.unpack_from(template_span)
    _kind, stored, system, video, magic, scratch, _r0, _r1 = fields
    require(magic == tx.COMPRESSED_SENTINEL and len(decoded) == system + video, "the coach scene is not the retail layout")
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
                        "the refit coach scene failed its independent decode")
                return rebuilt, dict(encoder=encoder, slack=slack, stream_bytes=len(filled), stored_size=stored,
                                     padding_bytes=padding, scratch_needed=need, scratch_retail=scratch,
                                     matches_expanded=expanded)
    raise ModernCoachesError(f"the coach scene does not fit its retail span ({last})")


def compile_archive(raw: bytes, row: dict) -> tuple[bytes, dict]:
    """The coach archive ``raw`` (retail bytes) with the 2026 textures of ``row`` refit into chunk 0."""
    import numpy as np  # noqa: F401
    tx, _fill = _tools()
    mm = _mm()
    chunks = tx.parse_chunks(raw)
    chunk = chunks[0]
    require(chunk.kind == "SCNE" and chunk.offset == row["span_offset"]
            and 0x20 + chunk.stored_size == row["span_size"], f"{row['archive']}: not the retail coach layout")
    rec, decoded = mm._scene(raw, chunk)
    require(rec.get("name") == "coach", f"{row['archive']}: chunk 0 is not the coach scene")
    system = int(rec["system_bytes"])
    edited = bytearray(decoded)
    rows = {}
    for tex in rec["embedded_textures"]:
        for material in tex.get("mapped_material_names") or ():
            rows.setdefault(material, tex)
    detail = {}
    for name, material in TEXTURES:
        tex = rows.get(material)
        require(tex is not None and tex.get("format_name") == "P8", f"{row['archive']}: no P8 texture for {material}")
        if name == "head" and row.get("head_recipe"):
            width, height = int(tex["width"]), int(tex["height"])
            retail_head, _palette = mm.read_p8(decoded, system, tex)       # the model's own retail head (this disc)
            recipe = row["head_recipe"]
            rgba = derive_head(retail_head, _rgba(art_path(row["team"], "head_mask"), width, height)[..., :3],
                               recipe["classes"], _rgba(art_path(row["team"], "head_overlay"), width, height))
            colours = mm.write_p8(edited, system, tex, rgba, maximum=int(row.get("palette_max", 256)))
            detail[name] = dict(palette_max=int(row.get("palette_max", 256)), material=material,
                                texture_index=int(tex["index"]), size=[width, height], mip_levels=int(tex["mip_levels"]),
                                palette_entries=int(colours), derived=recipe["kind"])
            continue
        if name == "headset":
            retail_atlas, _palette = mm.read_p8(decoded, system, tex)    # the model's own retail atlas (this disc)
            rgba = derive_accessories(retail_atlas, _rgba(art_path(row["team"], name), HEADSET_WIDTH,
                                                          int(tex["height"])))
        else:
            rgba = _rgba(art_path(row["team"], name), int(tex["width"]), int(tex["height"]))
        colours = mm.write_p8(edited, system, tex, rgba, maximum=int(row.get("palette_max", 256)))
        detail[name] = dict(palette_max=int(row.get("palette_max", 256)), material=material, texture_index=int(tex["index"]), size=[int(tex["width"]), int(tex["height"])],
                            mip_levels=int(tex["mip_levels"]), palette_entries=int(colours))
        if name == "headset":
            detail[name]["derived"] = "shoe_and_clipboard_from_disc"   # x >= 64 from the user's own atlas
    if row.get("hide_glasses"):
        import numpy as np
        tex = rows.get(GLASSES_MATERIAL)
        require(tex is not None and tex.get("format_name") == "P8", f"{row['archive']}: no glasses texture")
        rgba, _palette = mm.read_p8(decoded, system, tex)
        clear = np.array(rgba, dtype=np.uint8)
        clear[:, GLASSES_KEEP_COLUMNS:, :] = 0
        mm.write_p8(edited, system, tex, clear, maximum=int(row.get("palette_max", 256)))
        detail["glasses"] = dict(material=GLASSES_MATERIAL, hidden=True, kept_columns=GLASSES_KEEP_COLUMNS)
    if row.get("geometry"):
        detail["geometry"] = apply_geometry(edited, rec, load_geometry(row))
    span = raw[chunk.offset:chunk.offset + 0x20 + chunk.stored_size]
    rebuilt, fit = _refit(span, bytes(edited))
    out = raw[:chunk.offset] + rebuilt + raw[chunk.offset + len(rebuilt):]
    require(len(out) == len(raw), "the coach archive changed size")
    return out, dict(textures=detail, fit=fit)


# --- the sideline staff -----------------------------------------------------------------------------------------

def compile_sideline(span: bytes, rgba, palette_max: int = 256) -> tuple[bytes, dict]:
    """A team package's coachshirt TXTR chunk span recoloured to ``rgba`` through its palette only: every retail index
    (all six mips) is kept and each of the 256 palette entries becomes the mean authored colour of the base-level
    pixels that use it, so the compressed stream keeps the retail size (re-quantised new pixels do not fit the retail
    spans; the 2004 shirts are a few flat palette ramps). ``palette_max`` is accepted for the pin format and unused."""
    import numpy as np
    tx, _fill = _tools()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    decoded, _info = tx.decode_chunk(span, chunk)
    texture = tx.parse_texture(decoded, chunk)
    require(chunk.kind == "TXTR" and texture.name == "coachshirt" and texture.format_name == "P8"
            and (texture.width, texture.height) == (256, 256), "not the retail coachshirt texture")
    system = chunk.system_bytes
    w, h = texture.width, texture.height
    pixel = system + texture.pixel_offset
    palette_at = system + texture.palette_offset
    indices = np.frombuffer(tx.unswizzle_2d(bytes(decoded[pixel:pixel + w * h]), w, h, 1), np.uint8).reshape(h, w)
    old = np.frombuffer(bytes(decoded[palette_at:palette_at + 1024]), np.uint8).reshape(256, 4)   # BGRA
    target = np.asarray(rgba, dtype=np.float64).reshape(h, w, 4)
    counts = np.bincount(indices.ravel(), minlength=256)
    new = old.copy()
    used = 0
    for channel, bgra in ((0, 2), (1, 1), (2, 0)):
        sums = np.bincount(indices.ravel(), weights=target[..., channel].ravel(), minlength=256)
        mean = np.where(counts > 0, sums / np.maximum(counts, 1), old[:, bgra])
        new[:, bgra] = np.clip(np.rint(mean), 0, 255).astype(np.uint8)
    used = int((counts > 0).sum())
    edited = bytearray(decoded)
    edited[palette_at:palette_at + 1024] = new.tobytes()          # alpha (and unused entries) stay retail
    rebuilt, fit = _refit(span, bytes(edited))
    return rebuilt, dict(method="palette", palette_entries_used=used, fit=fit)


def _package_span(archive, entries, package: str, chunk_index: int):
    """(virtual offset, span) of chunk ``chunk_index`` of a team package, through its own chunk table."""
    tx, _fill = _tools()
    entry = entries.get(name_id(package))
    require(entry is not None, f"{package} is not on this disc")
    raw = archive.read(entry.virtual_offset, entry.size)
    chunks = tx.parse_chunks(raw)
    require(len(chunks) > chunk_index, f"{package} has no chunk {chunk_index}")
    chunk = chunks[chunk_index]
    return entry.virtual_offset + chunk.offset, raw[chunk.offset:chunk.offset + 0x20 + chunk.stored_size]


# --- the two portraits -------------------------------------------------------------------------------------------

def portrait_span(retail_span: bytes, rgba) -> bytes:
    """A raw (uncompressed) 128x128 P8 portrait span with new pixels: wrapper and system bytes retail."""
    tx, _fill = _tools()
    import nfl_tset_png_import as palette_tools  # noqa: E402
    chunk = tx.parse_chunks(retail_span, allow_trailing=True)[0]
    decoded, info = tx.decode_chunk(retail_span, chunk)
    texture = tx.parse_texture(decoded, chunk)
    require(info is None and not chunk.compressed and texture.format_name == "P8" and texture.width == texture.height == 128
            and texture.mip_levels == 1, "the portrait slot is not a raw 128x128 P8 texture")
    level = palette_tools.MipLevel(0, 128, 128, bytes(rgba.tobytes()))
    palette, index_levels, _quality = palette_tools.quantize_levels([level])
    swizzled = tx.swizzle_2d(index_levels[0], 128, 128, 1)
    payload = palette_tools.palette_bytes(palette)
    require(len(swizzled) + len(payload) == chunk.video_bytes, "the portrait video allocation changed")
    system = chunk.system_bytes
    out = retail_span[:tx.HEADER.size] + decoded[:system] + swizzled + payload
    out = out + retail_span[len(out):]
    require(len(out) == len(retail_span), "the portrait span changed size")
    back, _ = tx.decode_chunk(out, tx.parse_chunks(out, allow_trailing=True)[0])
    require(back[:system] == decoded[:system], "the portrait system bytes changed")
    return out


# --- the disc ----------------------------------------------------------------------------------------------------

def _roster(archive):
    from . import nfl2k5_roster_records as rr
    entry = rr._entry(archive)
    resource = archive.read(entry.virtual_offset, entry.size)
    doc = rr.RosterDocument(resource[rr.RESOURCE_HEADER_SIZE:], base=0, source="image",
                            resource_header=resource[:rr.RESOURCE_HEADER_SIZE])
    return entry.virtual_offset + rr.RESOURCE_HEADER_SIZE, doc


# the roster's club abbreviations where they differ from the 2026 ones (the 2004 abbreviations stay in the records)
ROSTER_ABBREVIATIONS = {"WAS": ("WAS", "WSH"), "ARI": ("ARI", "ARZ"), "LAC": ("LAC", "SD"), "LAR": ("LAR", "STL"),
                        "LV": ("LV", "OAK")}


def _coach_field_site(archive, team: str, field: int) -> tuple[int, int]:
    """(virtual offset of the u16 at the club's coach record + ``field``, its value)."""
    base, doc = _roster(archive)
    want = ROSTER_ABBREVIATIONS.get(team, (team,))
    clubs = [t for t in doc.teams if t.index < 32 and t.abbreviation in want and t.coach_offset is not None]
    require(len(clubs) == 1, f"the roster has no single {team} club with a coach record")
    at = clubs[0].coach_offset + field
    return base + at, struct.unpack_from("<H", doc.body, at)[0]


def _coach_photo_site(archive, team: str) -> tuple[int, int]:
    """(virtual offset of the u16 at the club's coach record +0x40, its value)."""
    return _coach_field_site(archive, team, 0x40)


def _coach_body_site(archive, team: str) -> tuple[int, int]:
    """(virtual offset of the u16 at the club's coach record +0x18, its value): the coach model number."""
    return _coach_field_site(archive, team, BODY_FIELD)


def _parts(archive, document: dict) -> list[dict]:
    """Every owned span with its retail and applied digests and its current state."""
    entries = {e.name_id: e for e in archive.entries}
    out = []
    for row in document["teams"]:
        entry = entries.get(name_id(row["archive"]))
        require(entry is not None, f"{row['archive']} is not on this disc")
        at = entry.virtual_offset + row["span_offset"]
        span = archive.read(at, row["span_size"])
        digest = sha(span)
        state = ("retail" if digest == row["retail_sha256"] else "applied" if digest == row["applied_sha256"]
                 else "previous" if digest in row.get("superseded_sha256", ()) else "foreign")
        out.append(dict(kind="coach", team=row["team"], at=at, size=row["span_size"], state=state, row=row))
        if row["body_code"] != row["team_code"]:
            site, value = _coach_body_site(archive, row["team"])
            state = ("retail" if value == int(row["team_code"]) else "applied" if value == int(row["body_code"])
                     else "kept")
            out.append(dict(kind="body_id", team=row["team"], at=site, size=2, state=state, row=row, value=value))
        for pkg in row["sideline"]:
            at, span = _package_span(archive, entries, pkg["package"], pkg["chunk_index"])
            digest = sha(span)
            state = ("retail" if digest == pkg["retail_sha256"] else "applied" if digest == pkg["applied_sha256"]
                     else "foreign")
            out.append(dict(kind="sideline", team=f"{row['team']}:{pkg['package']}", at=at, size=len(span),
                            state=state, row=dict(pkg, team=row["team"], palette_max=row.get("palette_max", 256))))
    for row in document.get("portraits", ()):
        entry = archive.entries[row["outer_index"]]
        require(entry.name_id == int(row["outer_id"], 16), "the portrait aggregate moved")
        at = entry.virtual_offset + row["chunk_offset"]
        span = archive.read(at, row["span_size"])
        digest = sha(span)
        state = ("retail" if digest == row["retail_sha256"] else "applied" if digest == row["applied_sha256"]
                 else "previous" if digest in row.get("superseded_sha256", ()) else "foreign")
        out.append(dict(kind="portrait", team=row["team"], at=at, size=row["span_size"], state=state, row=row))
        site, value = _coach_photo_site(archive, row["team"])
        state = ("retail" if value == row["retail_photo_id"] else "applied" if value == int(row["portrait_id"])
                 else "kept")
        out.append(dict(kind="photo_id", team=row["team"], at=site, size=2, state=state, row=row, value=value))
    return out


def resource_states(source, *, document: dict | None = None) -> dict[str, str]:
    document = pins() if document is None else _check_pins(document)
    with _outer_image()(source) as archive:
        return {f"{p['kind']}:{p['team']}": p["state"] for p in _parts(archive, document)}


def image_status(source, *, document: dict | None = None) -> str:
    """'retail', 'applied', 'mixed' (some parts each) or 'foreign' (a coach span or portrait is neither)."""
    states = resource_states(source, document=document)
    values = {v for v in states.values() if v != "kept"}
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
            require(archive.read(at, len(before)) == before, "a coach span changed after preflight")
            require(archive.write(at, after) == len(after), "short coach write")
            written.append((at, before))
            require(archive.read(at, len(after)) == after, "coach read-back differs")
    except BaseException:
        for at, before in reversed(written):
            archive.write(at, before)
        raise


def _retail_archive(retail, name: str) -> bytes:
    with _outer_image()(retail) as archive:
        entry = {e.name_id: e for e in archive.entries}.get(name_id(name))
        require(entry is not None, f"{name} is not on the retail image")
        return archive.read(entry.virtual_offset, entry.size)


def plan_image(source, *, document: dict | None = None, progress=None, retail=None) -> tuple[list, list[dict]]:
    """Compile every retail part of ``source`` (read only): ([(virtual offset, before, after)], receipt rows).
    A coach model that holds an earlier version of this option (``previous``) is compiled from ``retail`` (the user's
    retail USA image) when it is given, and refused otherwise."""
    document = pins() if document is None else _check_pins(document)
    say = progress or (lambda message, done, total: None)
    plan, rows = [], []
    with _outer_image()(source) as archive:
        parts = _parts(archive, document)
        require(all(p["state"] != "foreign" for p in parts),
                "a coach model or portrait is neither the retail nor the 2026 bytes; rebuild from a supported USA source")
        require(retail is not None or all(p["state"] != "previous" for p in parts if p["kind"] == "coach"),
                "a coach model holds an earlier version of the 2026 coaches; rebuild from a supported USA source")
        entries = {e.name_id: e for e in archive.entries}
        for index, part in enumerate(parts):
            row = part["row"]
            out = dict(kind=part["kind"], team=part["team"], virtual_offset=part["at"], size=part["size"],
                       state_before=part["state"])
            if part["state"] in ("retail", "previous") and part["kind"] == "coach":
                say(f"2026 head coaches: {part['team']}", index, len(parts))
                entry = entries[name_id(row["archive"])]
                raw = archive.read(entry.virtual_offset, entry.size)
                if part["state"] == "previous":
                    template = _retail_archive(retail, row["archive"])
                    require(len(template) == len(raw) and sha(template[row["span_offset"]:row["span_offset"]
                                                                       + row["span_size"]]) == row["retail_sha256"],
                            f"{row['archive']}: the retail image does not hold the retail coach")
                    require(template[:row["span_offset"]] == raw[:row["span_offset"]]
                            and template[row["span_offset"] + row["span_size"]:]
                            == raw[row["span_offset"] + row["span_size"]:],
                            f"{row['archive']}: bytes outside the coach span differ from retail")
                    compiled, detail = compile_archive(template, row)
                else:
                    compiled, detail = compile_archive(raw, row)
                before = raw[row["span_offset"]:row["span_offset"] + row["span_size"]]
                after = compiled[row["span_offset"]:row["span_offset"] + row["span_size"]]
                require(compiled[:row["span_offset"]] == raw[:row["span_offset"]]
                        and compiled[row["span_offset"] + row["span_size"]:] == raw[row["span_offset"] + row["span_size"]:],
                        f"{row['archive']}: bytes outside the coach span changed")
                require(sha(after) == row["applied_sha256"], f"{row['archive']}: the compiled coach differs from its pin")
                plan.append((part["at"], before, after))
                out.update(written=True, archive=row["archive"], before_sha256=sha(before), after_sha256=sha(after),
                           changed_bytes=sum(a != b for a, b in zip(before, after)), **detail)
            elif part["state"] == "retail" and part["kind"] == "sideline":
                before = archive.read(part["at"], part["size"])
                after, detail = compile_sideline(before, _rgba(art_path(row["team"], row["design"]), 256, 256),
                                                 int(row.get("sideline_palette_max", 256)))
                require(sha(after) == row["applied_sha256"], f"{row['package']}: the compiled coachshirt differs from its pin")
                plan.append((part["at"], before, after))
                out.update(written=True, package=row["package"], before_sha256=sha(before), after_sha256=sha(after),
                           changed_bytes=sum(a != b for a, b in zip(before, after)), **detail)
            elif part["state"] in ("retail", "previous") and part["kind"] == "portrait":
                # b77 co3: an earlier picture (co1's photo crop) is replaced in place: a portrait span keeps the retail
                # wrapper, system bytes and tail, so the new span compiles the same from either
                before = archive.read(part["at"], part["size"])
                after = portrait_span(before, _rgba(DATA_DIR / row["png"], 128, 128))
                require(sha(after) == row["applied_sha256"], f"portrait {row['portrait_id']}: differs from its pin")
                plan.append((part["at"], before, after))
                out.update(written=True, portrait_id=row["portrait_id"], before_sha256=sha(before), after_sha256=sha(after),
                           changed_bytes=sum(a != b for a, b in zip(before, after)))
            elif part["state"] == "retail" and part["kind"] == "body_id":
                before = struct.pack("<H", int(row["team_code"]))
                after = struct.pack("<H", int(row["body_code"]))
                plan.append((part["at"], before, after))
                out.update(written=True, body_before=int(row["team_code"]), body_after=int(row["body_code"]),
                           archive=row["archive"], changed_bytes=sum(x != y for x, y in zip(before, after)))
            elif part["state"] == "retail" and part["kind"] == "photo_id":
                before = struct.pack("<H", row["retail_photo_id"])
                after = struct.pack("<H", int(row["portrait_id"]))
                plan.append((part["at"], before, after))
                out.update(written=True, photo_id_before=row["retail_photo_id"], photo_id_after=int(row["portrait_id"]),
                           changed_bytes=sum(x != y for x, y in zip(before, after)))
            else:
                out.update(written=False, changed_bytes=0, value=part.get("value"))
            rows.append(out)
    return plan, rows


def apply_to_image(target, *, document: dict | None = None, progress=None, retail=None) -> dict[str, Any]:
    """Build-only: ``target`` is the caller's disposable output image. Retail or already-2026 parts only (an earlier
    version of this option only with ``retail``, the user's retail USA image)."""
    document = pins() if document is None else _check_pins(document)
    plan, rows = plan_image(target, document=document, progress=progress, retail=retail)
    with _outer_image()(target, writable=True) as archive:
        _write_all(archive, plan)
    state = image_status(target, document=document)
    require(state == "applied", f"the 2026 head coaches failed their read-back on the copy ({state})")
    return dict(label=LABEL, option=BUILD_KEY, state=state, runtime_witnessed=False, parts=rows, written=len(plan),
                already_applied=len(rows) - len(plan), changed_bytes=sum(r["changed_bytes"] for r in rows))


def verify(source, *, enabled: bool = True, document: dict | None = None) -> dict[str, Any]:
    state = image_status(source, document=document)
    require(state == ("applied" if enabled else "retail"), "the 2026 head coaches do not match the request")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False)


# --- pins (development) ------------------------------------------------------------------------------------------

def record_pins(retail_image, teams: dict, portraits: list[dict], superseded: dict | None = None) -> dict:
    """The pin document from a retail USA image and the shipped art: retail and compiled digests of every part.
    ``teams``: {club: {"team_code": "13", "body_code": "21", "hide_glasses": bool, "head_recipe": dict | None}};
    ``superseded``: {archive: [applied SHA-256 of earlier versions of this option]}."""
    rows = []
    superseded = superseded or {}
    with _outer_image()(retail_image) as archive:
        entries = {e.name_id: e for e in archive.entries}
        tx, _fill = _tools()
        for team, spec in teams.items():
            code, body = spec["team_code"], spec["body_code"]
            name = f"c{body}.iff"
            entry = entries[name_id(name)]
            raw = archive.read(entry.virtual_offset, entry.size)
            chunk = tx.parse_chunks(raw)[0]
            row = dict(team=team, team_code=code, body_code=body, code=body, archive=name, outer_index=entry.index,
                       outer_size=entry.size, span_offset=chunk.offset, span_size=0x20 + chunk.stored_size,
                       retail_sha256=sha(raw[chunk.offset:chunk.offset + 0x20 + chunk.stored_size]),
                       hide_glasses=bool(spec.get("hide_glasses")))
            if spec.get("head_recipe"):
                row["head_recipe"] = spec["head_recipe"]
            row["art"] = {n: sha(art_path(team, n).read_bytes()) for n in art_names(row)}
            if geometry_path(team).is_file():
                row["geometry"] = sha(geometry_path(team).read_bytes())
            if body != code:
                _site, value = _coach_body_site(archive, team)
                require(value == int(code), f"{team}: the retail coach record names body {value}, not {code}")
            for size in PALETTE_LADDER:
                try:
                    compiled, _detail = compile_archive(raw, dict(row, applied_sha256="", palette_max=size))
                except ModernCoachesError:
                    continue
                row["palette_max"] = size
                break
            else:
                raise ModernCoachesError(f"{team}: the 2026 art does not fit {name} at any palette size")
            row["applied_sha256"] = sha(compiled[chunk.offset:chunk.offset + row["span_size"]])
            row["superseded_sha256"] = [d for d in superseded.get(name, ()) if d not in (row["applied_sha256"],
                                                                                          row["retail_sha256"])]
            row["fit"] = _detail["fit"]
            row["sideline"] = []
            for variant in PACKAGES:
                package = f"{code}{variant}.iff"
                pentry = entries[name_id(package)]
                praw = archive.read(pentry.virtual_offset, pentry.size)
                index = None
                for k, c in enumerate(tx.parse_chunks(praw)):
                    if c.kind == "TXTR":
                        dec, _ = tx.decode_chunk(praw, c)
                        if tx.parse_texture(dec, c).name == "coachshirt":
                            index = k
                            pchunk = c
                require(index is not None, f"{package} has no coachshirt")
                span = praw[pchunk.offset:pchunk.offset + 0x20 + pchunk.stored_size]
                design = dict(SIDELINE)[variant[1]]
                for size in PALETTE_LADDER:
                    try:
                        after, sdetail = compile_sideline(span, _rgba(art_path(team, design), 256, 256), size)
                    except ModernCoachesError:
                        continue
                    break
                else:
                    raise ModernCoachesError(f"{package}: the sideline art does not fit at any palette size")
                row["sideline"].append(dict(package=package, design=design, chunk_index=index,
                                            chunk_offset=pchunk.offset, span_size=len(span), retail_sha256=sha(span),
                                            applied_sha256=sha(after), sideline_palette_max=size,
                                            scratch_needed=sdetail["fit"]["scratch_needed"],
                                            scratch_retail=sdetail["fit"]["scratch_retail"]))
            rows.append(row)
        prows = []
        for p in portraits:
            entry = archive.entries[p["outer_index"]]
            span = archive.read(entry.virtual_offset + p["chunk_offset"], p["span_size"])
            require(sha(span) == p["retail_sha256"], f"portrait {p['portrait_id']} is not retail on this image")
            after = portrait_span(span, _rgba(DATA_DIR / p["png"], 128, 128))
            prows.append(dict(p, outer_id=f"0x{entry.name_id:08x}", applied_sha256=sha(after),
                              png_sha256=sha((DATA_DIR / p["png"]).read_bytes())))
            _site, value = _coach_photo_site(archive, p["team"])
            require(value == p["retail_photo_id"], f"{p['team']}: the retail coach record names {value}")
    return _check_pins(dict(schema=PINS_SCHEMA, label=LABEL, teams=rows, portraits=prows))


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="2026 head coaches: status or apply on a disc image copy")
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
