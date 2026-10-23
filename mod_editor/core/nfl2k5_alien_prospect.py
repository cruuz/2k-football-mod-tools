"""The once-in-a-century gray alien prospect (jobs b778-ee1/ee2, Noah 2026-10-22/23). EXPERIMENTAL.

Noah: "you should make this happen very rarely. Very, very, very rarely. Like less than 1% of the time. And it should
never show up again. It only has a chance of showing up once throughout an entire franchise over 100 seasons. But one
of the headshots should straight up be a gray alien, and the player should have gray skin in the game and a gray alien
face scan. He can be any position, but very, very rarely, once in a 100-year period, a random prospect will literally
be a gray alien."

How it works
------------
* The roll. Every prospect the franchise class loop (0x2BE940, 380 prospects a class) makes runs the generator
  FUN_000E6780 from FUN_002BE6F0's call at 0x2BE7CE; that call now goes through a short wrapper that runs the generator
  and then the roll: one draw of the game's own RNG (0x48B50, 32-bit) per prospect with p = 1 - (149/150)^(1/380), so a
  380-prospect class holds him one time in 150 (0.67 % a season, 48 % over 99 rollover classes). On a hit the prospect
  becomes him: photo id 1947, bare hands, no hair model (style 13), no Dreads, eye black or visor, generic face shape 0,
  7'11" (95 inches) and 150 lb (weight raw 0: the game stores pounds - 150 in an unsigned byte and every reader adds
  150 again, so 150 is the lightest representable weight; the weight profile clamps at the same floor), body type 0
  (the thinnest of the four weight profiles). Name, position, ratings, college and age are the generator's own, so he
  is drafted, signed, played, developed, saved and retired like anybody else. The game scales a player's model by
  height (0x918B0: height * 0.0129275 is stored as the entity scale at +8 and applied to the transform's +0x48), so
  95 inches makes him 22.8 % taller than the 77.35-inch reference. The four weight profiles (0x93850) only scale each
  bone's girth perpendicular to its SKEL axis; there is no per-bone length table. The same postprocessor receives all
  25 low and 62 high current bone matrices, and ee3's arm/spine hook lengthens both arm chains 1.16x about the
  shoulders and lowers the thorax and everything above it 4 model units, so the arms read long and the legs
  proportionally longer. The hook saves the caller's ESI before reusing it as the matrix base (the loader's render
  walker keeps its entity in ESI and reads [ESI+0x30] after the call; the old order caused an access violation at
  0x1D2D70). It only acts when the roster record is photo 1947, so no other player's matrices change. What ships
  additionally is the profile override: a visual 100 lb so the mesh is thinner than the record's 150 lb floor (the
  save field cannot hold 100).
* Once per franchise. The flag is bit 0 of byte +0x0F of draft template record 2 (``[[0xB72918]+0x0C] + 0xB7``): the
  template table travels inside the roster arena, so the franchise save carries it with no save hook. No code of the
  game reads or writes that byte (the templates are only read by FUN_002BD200/FUN_002BD230 for the generator, which
  reads other offsets; the serializer converts only pointer fields); it is 0 on the disc roster and in every franchise
  save checked (18 real saves). Set on the hit, it blocks him for the rest of that franchise.
* Never in the main roster, Quick Game or MyCareer's creation: the class loop only runs at franchise creation and at
  the preseason-to-season step. The first class of a franchise (year 0, which is also MyCareer's own creation) never
  rolls; at its first prospect the flag is cleared, because a new franchise may start from a reused copy of the roster
  in memory.
* His look, ADDED, nothing replaced:
  - portrait 1947 in the rookie-faces portrait record (Portrai2.iff), framed like the other draft headshots;
  - live face f1947 in a new face-texture record and aggregate (igface2.iff / igface2.cdf: every retail face copied plus
    his, hash-sorted; the record name string at 0xE62E78 points at it, the rookie-faces recipe for portraits), and a new
    close-up package pf1947.iff (h1947 helmet-off face, n1947 bald gray skull and neck, s1947 = the generic face
    shape s9001);
  - gray arms, hands and neck: three new textures (alien_arm, alien_hand, alien_neck: the retail Lightest arm, bare hand
    and neck images with a gray palette, made on the user's own disc) added to the common player collection (outer 3,
    before any hair-style textures), and three 7-byte lookups in the player builder (0x8ED1F hands, 0x8EDDE arms,
    0x8F2FC neck) that hand a player with photo id 1947 the gray texture. Every other player gets the retail texture.
  - gray far face and gray sideline bench body (ee2): alien_sf, the alien's own portrait cut to the 32 x 32 P8
    placeholder-face layout, and alien_sideline, a 128 x 128 P8 skin in the retail sideline-skin layout, both added to
    outer 3. Two more 7-byte lookups, keyed on photo id 1947: 0x8F152 (the player builder's far-LOD sf0..sf5 face,
    record in EBX) and 0x119B35 (the sideline-person builder's sideline_skin_00..05 body, record in EDI).
  - a thin body (ee2 follow-up): a 9-byte hook at 0x93859 gives the weight profile 100 lb instead of the record's
    150, and a 2-byte NOP at 0x938BD lets that value past the retail 150 lb floor, so the four weight-profile girth
    matrices treat him as a 100 lb player. A 6-byte jump at 0x93850 runs the arm/spine length hook on the current
    bone matrices (arms 1.16x about the shoulders, upper body lowered 4 units); the hook checks photo 1947 first and
    for anyone else reproduces the retail prologue exactly. It preserves every register: the caller's ESI is saved
    by pushad before the hook reuses it as the low-matrix base (the earlier version reused ESI first and the
    loader's entity-list walker read [ESI+0x30] from the matrices, an access violation at 0x1D2D70 with the loader
    stuck at "LOADING"). The engine has no per-bone length table, so the current matrices are the length lever.
* Space: none from the allocator. The seventeen "copy a field from the low or the high template on a coin" blocks of
  FUN_000E6780 (0xE696E..0xE6D15, 935 bytes) are rewritten as one table loop that makes the same 17 calls of the float
  rand in the same order with the same compares (bit for bit the same prospect, proved under Unicorn on the retail
  bytes); the bytes it frees hold the wrapper, the roll, the five lookups and the record fields.
* Test build: ``apply(payload, test=True)`` (or ``tools/nfl2k5_alien_prospect.py test-build``) makes every class roll
  hit, the first class included, so the once-only flag and the look can be shown in a new franchise. Never shipped.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
import zlib
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
OWNER = "nfl2k5_alien_prospect"
UI_LABEL = BUILD_CAPTION = "Alien prospect (once in a hundred seasons)"
HELP_TEXT = ("EXPERIMENTAL. Very rarely (one draft class in 150, and never again in that franchise once he has appeared) "
             "a generated prospect is a 7'11\", 150 lb gray alien: his own draft headshot, an alien face, gray skin, and "
             "a gray far face and sideline body. He is otherwise an ordinary prospect of any position. Needs Rookie "
             "faces and a disc image.")
EVIDENCE = "EXPERIMENTAL"
DATA_DIR = ROOT / "data" / "nfl2k5_alien_prospect"
ART = {"portrait": "portrait.png", "f": "face_f.png", "h": "face_h.png", "n": "face_n.png"}
ALIEN_ID = 1947
ALIEN_NAME = f"{ALIEN_ID:04d}"

# ------------------------------------------------------------------------------------------------ the executable
CODE_VA = 0xE696E             # FUN_000E6780's 17 coin blocks
CODE_END = 0xE6D15
THRESH = 75657                # 2^32 * (1 - (149/150) ** (1/380)), rounded
CLASS_SIZE = 380              # the class loop asks for 0x17C prospects (0x13EF08, 0x2BF942)
ODDS = 150

CALL_SITE = 0x2BE7CE          # FUN_002BE6F0: call FUN_000E6780
CALL_RETAIL = bytes.fromhex("e8ad7fe2ff")
HAND_SITE, ARM_SITE, NECK_SITE = 0x8ED1F, 0x8EDDE, 0x8F2FC
HAND_RETAIL = bytes.fromhex("8b04952854b600")      # mov eax,[edx*4+0xB65428]
ARM_RETAIL = bytes.fromhex("8b048d2854b600")       # mov eax,[ecx*4+0xB65428]
NECK_RETAIL = bytes.fromhex("8b04952055b600")      # mov eax,[edx*4+0xB65520]
SF_SITE, SIDE_SITE = 0x8F152, 0x119B35
SF_RETAIL = bytes.fromhex("8b0c850855b600")        # mov ecx,[eax*4+0xB65508]  (far face sf0..sf5)
SIDE_RETAIL = bytes.fromhex("8b04858082ba00")      # mov eax,[eax*4+0xBA8280]  (sideline_skin_00..05)
SKEL_SITE, GIRTH_SITE, GIRTH_NOP_SITE = 0x93850, 0x93859, 0x938BD
SKEL_RESUME = 0x93856         # 0x93850's retail body starts here (sub esp,0x74); a 6-byte jump must leave it intact
SKEL_SPAN = SKEL_RESUME - SKEL_SITE
SKEL_RETAIL = bytes.fromhex("558bec83e4f0")        # 0x93850: push ebp; mov ebp,esp; and esp,-16
GIRTH_RETAIL = bytes.fromhex("0fb6412a0596000000")  # movzx eax,[ecx+0x2A]; add eax,150
GIRTH_NOP_RETAIL = bytes.fromhex("7511")           # jne 0x938D0: the weight floor 150 (the alien uses 100)
HEIGHT_INCHES = 95            # 7'11"; the card formats [0x2B] / 12 and % 12, and 0x918B0 scales the model by it
WEIGHT_RAW = 0                # the record stores pounds - 150 unsigned: 0 = 150 lb, the smallest the game reads/shows
WEIGHT_LB = WEIGHT_RAW + 150
BODY_TYPE = 0                 # the record's +0x18 bits 3-4: weight profile 0, the thinnest of the four
VISUAL_WEIGHT = 100           # 0x93850's input weight for photo 1947 (the mesh; the record keeps the 150 lb floor)
# The 0x93850 matrix hook (applied; see the docstring).
ARM_SCALE = 1.16              # each arm chain scales about its shoulder in 0x93850's current matrices
SPINE_DROP = 4.0              # the upper body is lowered this many model units at the waist
FACES_STRING_VA = 0xE62E78    # UTF-16 "igfaces.iff": the FaceTextures registry's record file (read at 0x73F45, 0x749C8)
RETAIL_RECORD = "igfaces.iff"
RECORD_NAME = "igface2.iff"   # same length
CDF_NAME = "igface2.cdf"
PF_NAME = f"pf{ALIEN_NAME}.iff"
SHAPE_SOURCE = "pf9001.iff"   # the generic face shape the alien's record selects (skin 0, face 0) and its package
GRAY_TEXTURES = (("alien_arm", "arm_00_00"), ("alien_hand", "hand_00_01"), ("alien_neck", "neck_00_00"))
SF_TEXTURE = "alien_sf"           # the 32 x 32 P8 far-LOD face (the alien portrait quantised onto the sf0 layout)
SIDE_TEXTURE = "alien_sideline"   # the 128 x 128 P8 sideline bench body (flat gray, the arm texture's layout)
SF_SOURCE = "sf0"                 # the retail far face whose raw TXTR layout alien_sf reuses
SIDE_SOURCE = "arm_00_00"         # the retail TSET whose 128 x 128 5-mip P8 layout alien_sideline reuses
# The alien skin (CIE L*a*b*, OpenCV 8-bit scale), measured on his headshot's de-lit cheeks; the arms, hands and neck
# are mapped onto it with the retail Lightest texture's own light-dark range.
BASE_LAB = (132.0, 130.0, 132.0)

FLAG_RECORD, FLAG_BYTE, FLAG_BIT = 2, 0x0F, 0x01

TEST_NOTE = "test build: every class rolls a hit (first class included); never ship"


class AlienProspectError(ValueError):
    """A foreign layout, an unexpected disc or a failed read-back."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AlienProspectError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# The code (assembled from tools/b77/ee1_alien_prospect.S, linked at CODE_VA) and its symbol addresses live in one JSON
# next to the art, written by tools/b77/ee1_build_code.py, so the bytes, the two points the test build patches and the
# four entry points can never disagree.
def _load_code() -> dict[str, Any]:
    doc = json.loads((DATA_DIR / "code.json").read_text(encoding="utf-8"))
    require(doc.get("schema") == "nfl2k5_alien_prospect_code/v1" and doc["va"] == CODE_VA, "unknown alien code document")
    code = bytes.fromhex(doc["code"])
    require(sha(code) == doc["sha256"] and len(code) <= CODE_END - CODE_VA, "the alien code does not match its pin")
    return doc


_CODE_DOC = _load_code()
CODE = bytes.fromhex(_CODE_DOC["code"])
SYMBOLS = {k: int(v, 16) for k, v in _CODE_DOC["symbols"].items()}
OFF_FIRST_SEASON_JMP = SYMBOLS["first_season"] - CODE_VA
OFF_THRESH = _CODE_DOC["thresh_imm_offset"]
WRAP_VA, HAND_VA, ARM_VA, NECK_VA, SF_VA, SIDE_VA = (SYMBOLS[k] for k in ("wrap", "hand", "arm", "neck", "sf", "side"))
SKEL_VA, GIRTH_VA = SYMBOLS["skel"], SYMBOLS["weight"]
RETAIL_CODE_SHA256 = _CODE_DOC["retail_region_sha256"]
require(CODE[OFF_FIRST_SEASON_JMP] == 0xEB and struct.unpack_from("<I", CODE, OFF_THRESH)[0] == THRESH,
        "the alien code's patch points moved")


def code_bytes(test: bool = False) -> bytes:
    out = bytearray(CODE)
    if test:
        out[OFF_FIRST_SEASON_JMP:OFF_FIRST_SEASON_JMP + 2] = b"\x90\x90"
        struct.pack_into("<I", out, OFF_THRESH, 0xFFFFFFFF)
    return bytes(out) + b"\xcc" * (CODE_END - CODE_VA - len(out))


def _rel(site: int, target: int, size: int = 7, opcode: bytes = b"\xe8") -> bytes:
    return (opcode + struct.pack("<i", target - (site + 5))).ljust(size, b"\x90")


def _spans(test: bool = False) -> list[tuple[int, bytes, str]]:
    return [(CODE_VA, code_bytes(test), "FUN_000E6780 coin blocks -> table loop + alien roll + gray lookups"),
            (CALL_SITE, _rel(CALL_SITE, WRAP_VA, 5), "FUN_002BE6F0 generator call -> wrapper (generator, then the roll)"),
            (HAND_SITE, _rel(HAND_SITE, HAND_VA), "hand texture lookup -> gray for photo 1947"),
            (ARM_SITE, _rel(ARM_SITE, ARM_VA), "arm texture lookup -> gray for photo 1947"),
            (NECK_SITE, _rel(NECK_SITE, NECK_VA), "neck texture lookup -> gray for photo 1947"),
            (SF_SITE, _rel(SF_SITE, SF_VA), "far-face sf0..sf5 lookup -> alien_sf for photo 1947"),
            (SIDE_SITE, _rel(SIDE_SITE, SIDE_VA), "sideline_skin_00..05 lookup -> alien_sideline for photo 1947"),
            (SKEL_SITE, _rel(SKEL_SITE, SKEL_VA, SKEL_SPAN, b"\xe9"),
             "player matrix postprocessor -> lanky arms, shorter torso"),
            (GIRTH_SITE, _rel(GIRTH_SITE, GIRTH_VA, 9), "weight profile -> visual 100 lb for photo 1947"),
            (GIRTH_NOP_SITE, b"\x90\x90", "let the visual 100 lb weight past the retail 150 lb floor"),
            (FACES_STRING_VA, RECORD_NAME.encode("utf-16-le"), "FaceTextures record file name")]


def _retail() -> dict[int, bytes]:
    return {CALL_SITE: CALL_RETAIL, HAND_SITE: HAND_RETAIL, ARM_SITE: ARM_RETAIL, NECK_SITE: NECK_RETAIL,
            SF_SITE: SF_RETAIL, SIDE_SITE: SIDE_RETAIL, SKEL_SITE: SKEL_RETAIL, GIRTH_SITE: GIRTH_RETAIL,
            GIRTH_NOP_SITE: GIRTH_NOP_RETAIL, FACES_STRING_VA: RETAIL_RECORD.encode("utf-16-le")}


def _section_map(payload: bytes) -> list[tuple[int, int, int, int]]:
    require(payload[:4] == b"XBEH", "not an XBE")
    base = struct.unpack_from("<I", payload, 0x104)[0]
    count, table_va = struct.unpack_from("<II", payload, 0x11C)
    out = []
    for i in range(count):
        h = table_va - base + i * 56
        _flags, va, _vsize, raw, rsize = struct.unpack_from("<IIIII", payload, h)
        out.append((va, raw, rsize, h))
    return out


def _offset(payload: bytes, va: int, size: int = 1) -> int:
    for sva, raw, rsize, _h in _section_map(payload):
        if sva <= va and va + size <= sva + rsize:
            return raw + va - sva
    raise AlienProspectError(f"0x{va:x} is not file-backed")


def _read(payload: bytes, va: int, size: int) -> bytes:
    off = _offset(payload, va, size)
    return bytes(payload[off:off + size])


def xbe_status(payload: bytes) -> str:
    """retail | applied | test | foreign."""
    try:
        current = {va: _read(payload, va, len(data)) for va, data, _l in _spans()}
    except (AlienProspectError, struct.error):
        return "foreign"
    retail = _retail()
    if sha(current[CODE_VA]) == RETAIL_CODE_SHA256 and all(current[va] == retail[va] for va in retail):
        return "retail"
    for test, state in ((False, "applied"), (True, "test")):
        if all(current[va] == data for va, data, _l in _spans(test)):
            return state
    return "foreign"


def apply(payload: bytes, *, test: bool = False) -> tuple[bytes, dict[str, Any]]:
    """The executable half (in place, zero allocator bytes). ``test`` = every class rolls a hit (proof builds only)."""
    state = xbe_status(payload)
    require(state in ("retail", "applied", "test"), f"the alien prospect's executable bytes are {state}, not retail")
    buf = bytearray(payload)
    touched, changed = set(), 0
    for va, data, _label in _spans(test):
        off = _offset(payload, va, len(data))
        changed += sum(1 for x, y in zip(buf[off:off + len(data)], data) if x != y)
        buf[off:off + len(data)] = data
        for _sva, raw, rsize, h in _section_map(payload):
            if raw <= off < raw + rsize:
                touched.add((raw, rsize, h))
    for raw, rsize, h in touched:
        buf[h + 36:h + 56] = hashlib.sha1(struct.pack("<I", rsize) + bytes(buf[raw:raw + rsize])).digest()  # nosec B324
    out = bytes(buf)
    want = "test" if test else "applied"
    require(xbe_status(out) == want, "alien prospect executable read-back failed")
    return out, {"state": want, "changed_bytes": changed, "sections_repinned": len(touched),
                 "edits": [{"va": hex(va), "bytes": len(d), "label": label} for va, d, label in _spans(test)],
                 **({"note": TEST_NOTE} if test else {})}


def reservations(payload: bytes) -> list[dict[str, Any]]:
    require(xbe_status(payload) in ("applied", "test"), "the alien prospect is not applied")
    return [{"start": hex(va), "size": len(d), "owner": OWNER, "basis": "declared edit: " + label}
            for va, d, label in _spans()]


# ------------------------------------------------------------------------------------------------ the roll (offline)
def per_prospect_probability() -> float:
    return THRESH / 2 ** 32


def per_class_probability(class_size: int = CLASS_SIZE) -> float:
    return 1.0 - (1.0 - per_prospect_probability()) ** class_size


# ------------------------------------------------------------------------------------------------ art
def _art_doc() -> dict[str, Any]:
    doc = json.loads((DATA_DIR / "art.json").read_text(encoding="utf-8"))
    require(doc.get("schema") == "nfl2k5_alien_prospect_art/v1", "unknown alien art document")
    return doc


def art_rgb(key: str) -> tuple[int, int, bytes]:
    """(width, height, RGB) of one shipped picture, checked against its pin."""
    from PIL import Image  # noqa: PLC0415
    data = (DATA_DIR / ART[key]).read_bytes()
    require(sha(data) == _art_doc()["sha256"][key], f"{ART[key]} does not match its pin")
    im = Image.open(io.BytesIO(data)).convert("RGB")
    return im.width, im.height, im.tobytes()


def available() -> bool:
    try:
        doc = _art_doc()
        return all(sha((DATA_DIR / name).read_bytes()) == doc["sha256"][key] for key, name in ART.items())
    except (OSError, ValueError, KeyError):
        return False


def portrait_face() -> tuple[int, bytes]:
    """(portrait id, 128x128 RGB with at most 256 colours) for the rookie-faces portrait record."""
    w, h, rgb = art_rgb("portrait")
    require((w, h) == (128, 128), "the alien portrait must be 128 x 128")
    return ALIEN_ID, rgb


# ------------------------------------------------------------------------------------------------ textures
def _tx():
    from tools import nfl_txtr as tx  # noqa: PLC0415 - tools is a namespace package next to mod_editor
    return tx


def _mips(rgba: bytes, size: int, levels: int) -> list[bytes]:
    """Box-filtered mip chain ((a+b+c+d+2)//4 per channel, the live-face importer's rule), integer only."""
    import numpy as np  # noqa: PLC0415
    out = [rgba]
    cur = np.frombuffer(rgba, np.uint8).reshape(size, size, 4).astype(np.int32)
    for _ in range(1, levels):
        cur = (cur[0::2, 0::2] + cur[0::2, 1::2] + cur[1::2, 0::2] + cur[1::2, 1::2] + 2) // 4
        out.append(cur.astype(np.uint8).tobytes())
    return out


def _dxt1(rgba: bytes, size: int) -> bytes:
    from tools.nfl_dxt1 import encode_dxt1_opaque  # noqa: PLC0415
    return encode_dxt1_opaque(rgba, size, size)[0]


def _rgba(rgb: bytes) -> bytes:
    out = bytearray(len(rgb) // 3 * 4)
    out[0::4], out[1::4], out[2::4] = rgb[0::3], rgb[1::3], rgb[2::3]
    out[3::4] = b"\xff" * (len(rgb) // 3)
    return bytes(out)


def _rename(system: bytearray, old: str, new: str) -> None:
    a, b = old.encode("utf-16-le"), new.encode("utf-16-le")
    require(len(a) == len(b) and system.count(a) == 1, f"the name {old} is not where a resource name belongs")
    at = system.index(a)
    system[at:at + len(b)] = b


def face_slot(template: bytes, template_name: str, rgb256: bytes) -> bytes:
    """An f#### slot of the face aggregate: the template slot's wrapper, the new name and 6 DXT1 mips of ``rgb256``."""
    tx = _tx()
    chunk = tx.parse_chunks(template, allow_trailing=True)[0]
    require(chunk.kind == "TXTR" and not chunk.compressed, "the face template is not a raw texture")
    decoded, _ = tx.decode_chunk(template, chunk)
    t = tx.parse_texture(decoded, chunk)
    require(t.name == template_name and t.format_name == "DXT1" and (t.width, t.height, t.mip_levels) == (256, 256, 6),
            "the face template is not a 256 x 256 DXT1 face with 6 mips")
    out = bytearray(template)
    body = 32
    system = bytearray(out[body:body + chunk.system_bytes])
    _rename(system, template_name, "f" + ALIEN_NAME)
    out[body:body + chunk.system_bytes] = system
    pixels = b"".join(_dxt1(m, 256 >> k) for k, m in enumerate(_mips(_rgba(rgb256), 256, 6)))
    at = body + chunk.system_bytes + t.pixel_offset
    require(at + len(pixels) <= body + chunk.system_bytes + chunk.video_bytes, "the face does not fit its slot")
    out[at:at + len(pixels)] = pixels
    check = tx.parse_chunks(bytes(out), allow_trailing=True)[0]
    d2, _ = tx.decode_chunk(bytes(out), check)
    require(tx.parse_texture(d2, check).name == "f" + ALIEN_NAME, "the alien face slot does not read back")
    return bytes(out)


def _compressed(template_span: bytes, decoded: bytes) -> bytes:
    """A compressed resource for ``decoded`` with the template's VC-LZ parameters and a proved in-place scratch."""
    tx = _tx()
    chunk = tx.parse_chunks(template_span, allow_trailing=True)[0]
    _d, info = tx.decode_chunk(template_span, chunk)
    require(info is not None, "the template is not compressed")
    encoded, _ = tx.compress_vc_lz(bytes(decoded), stream_tag=info.stream_tag, offset_bits=info.offset_bits)
    stored = (len(encoded) + 15) & ~15
    minimum = tx.minimum_vc_lz_overlap_scratch(encoded, stored, len(decoded))
    scratch = (max(minimum, stored - len(encoded), stored - len(decoded), 0) + 15) & ~15
    raw = tx.HEADER.pack(chunk.kind.encode("ascii"), stored, chunk.system_bytes, chunk.video_bytes,
                         tx.COMPRESSED_SENTINEL, scratch, 0, 0) + encoded + bytes(stored - len(encoded))
    check = tx.parse_chunks(raw)[0]
    require(tx.decode_chunk(raw, check)[0] == bytes(decoded), "a compressed resource does not read back")
    return raw


def pf_package(template_pf: bytes, h_rgb: bytes, n_rgb: bytes) -> bytes:
    """pf1947.iff: the generic package's layout (h, n, SHAP) with the alien's h and n and the shape renamed s1947."""
    tx = _tx()
    chunks = tx.parse_chunks(template_pf, allow_trailing=True)
    require([c.kind for c in chunks] == ["TXTR", "TXTR", "SHAP"], "the face package template changed")
    out = b""
    src_id = SHAPE_SOURCE[2:6]
    for c, (family, rgb) in zip(chunks[:2], (("h", h_rgb), ("n", n_rgb))):
        span = template_pf[c.offset:c.offset + 32 + c.stored_size]
        decoded, _ = tx.decode_chunk(span, tx.parse_chunks(span)[0])
        t = tx.parse_texture(decoded, c)
        require(t.name == family + src_id and t.format_name == "DXT1" and t.mip_levels == 1, "face package texture")
        new = bytearray(decoded)
        system = bytearray(new[:c.system_bytes])
        _rename(system, family + src_id, family + ALIEN_NAME)
        new[:c.system_bytes] = system
        px = _dxt1(_rgba(rgb), 256)
        new[c.system_bytes + t.pixel_offset:c.system_bytes + t.pixel_offset + len(px)] = px
        out += _compressed(span, bytes(new))
    shap = chunks[2]
    span = bytearray(template_pf[shap.offset:shap.offset + 32 + shap.stored_size])
    _rename(span, "s" + src_id, "s" + ALIEN_NAME)
    out += bytes(span)
    names = [_resource_name(out, c) for c in tx.parse_chunks(out, allow_trailing=True)]
    require(names == ["h" + ALIEN_NAME, "n" + ALIEN_NAME, "s" + ALIEN_NAME], f"the alien package reads {names}")
    return out


def _resource_name(data: bytes, chunk) -> str:
    tx = _tx()
    decoded, _ = tx.decode_chunk(data, chunk)
    name_at = struct.unpack_from("<I", decoded, 0x10)[0] + 0x0F
    end = name_at
    while decoded[end:end + 2] != b"\0\0":
        end += 2
    return decoded[name_at:end].decode("utf-16-le")


def gray_palette(palette_bgra: bytes, pixels: bytes) -> bytes:
    """The Lightest skin palette mapped onto the alien gray: each entry keeps its lightness offset from the texture's
    median skin lightness (x0.9) around BASE_LAB's L, and takes BASE_LAB's colour (plus 20 % of its own)."""
    import numpy as np  # noqa: PLC0415
    import cv2  # noqa: PLC0415
    pal = np.frombuffer(palette_bgra, np.uint8).reshape(256, 4)
    rgb = pal[:, [2, 1, 0]][None].copy()
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)[0]
    used = np.bincount(np.frombuffer(pixels, np.uint8), minlength=256)
    order = np.argsort(lab[:, 0])
    cum = np.cumsum(used[order])
    med = lab[order[np.searchsorted(cum, cum[-1] / 2)], 0]
    out_lab = np.empty_like(lab)
    out_lab[:, 0] = BASE_LAB[0] + (lab[:, 0] - med) * 0.9
    out_lab[:, 1] = BASE_LAB[1] + (lab[:, 1] - np.median(lab[used > 0, 1])) * 0.2
    out_lab[:, 2] = BASE_LAB[2] + (lab[:, 2] - np.median(lab[used > 0, 2])) * 0.2
    out_rgb = cv2.cvtColor(np.clip(out_lab, 0, 255).astype(np.uint8)[None], cv2.COLOR_LAB2RGB)[0]
    out = np.empty((256, 4), np.uint8)
    out[:, 0], out[:, 1], out[:, 2], out[:, 3] = out_rgb[:, 2], out_rgb[:, 1], out_rgb[:, 0], pal[:, 3]
    return out.tobytes()


def _gray_ramp() -> bytes:
    """256 BGRA entries, a neutral 96..159 ramp (the flat sideline skin's albedo)."""
    out = bytearray(1024)
    for i in range(256):
        v = 96 + (i * 63) // 255
        out[4 * i:4 * i + 4] = bytes((v, v, v, 255))
    return bytes(out)


def gray_texture(outer3: bytes, name: str, source: str, template_span: bytes, *,
                 flat: int | None = None) -> bytes:
    """A raw TXTR ``name``: the TSET texture ``source``'s own pixels (every mip, as stored) with a gray palette, in
    the raw-resource layout of the retail ``dread`` texture (hair styles' recipe). ``flat`` replaces every pixel with
    that palette index (the sideline skin: a neutral albedo the model's own lighting shades)."""
    from . import nfl2k5_modern_officials as officials  # noqa: PLC0415 - tset_refs
    tx = _tx()
    for c in tx.parse_chunks(outer3, allow_trailing=True):
        if c.kind != "TSET":
            continue
        span = outer3[c.offset:c.offset + 32 + c.stored_size]
        decoded, _ = tx.decode_chunk(span, tx.parse_chunks(span)[0])
        refs = {r["name"]: r for r in officials.tset_refs(decoded)}
        if source in refs:
            ref = refs[source]
            break
    else:
        raise AlienProspectError(f"outer 3 has no {source}")
    require(ref["format_code"] == 0x0B, f"{source} is not P8")
    video = decoded[c.system_bytes:]
    w, h, mips = ref["width"], ref["height"], ref["mip_levels"]
    pixel_bytes = sum(max(1, w >> k) * max(1, h >> k) for k in range(mips))
    pixels = video[ref["pixel_offset"]:ref["pixel_offset"] + pixel_bytes]
    palette = video[ref["palette_offset"]:ref["palette_offset"] + 1024]
    require(len(pixels) == pixel_bytes and len(palette) == 1024, f"{source} is truncated")
    if flat is not None:
        pixels, gray = bytes([flat & 0xFF]) * pixel_bytes, _gray_ramp()
    else:
        gray = gray_palette(palette, pixels[:w * h])
    # the descriptor words of the TSET entry (format, mips, size) with the raw layout's offsets
    desc_at = None
    for index in range(struct.unpack_from("<I", decoded, 4)[0]):
        base = 0x18 + index * 0x24
        at = base + 8 + struct.unpack_from("<i", decoded, base + 8)[0] - 1
        n_at = base + 4 + struct.unpack_from("<i", decoded, base + 4)[0] - 1
        end = n_at
        while decoded[end:end + 2] != b"\0\0":
            end += 2
        if decoded[n_at:end].decode("utf-16-le") == source:
            desc_at = at
    require(desc_at is not None, f"{source}: descriptor not found")
    u0, _pix, _pal, packed, packed_size, flags = struct.unpack_from("<6I", decoded, desc_at)
    t_chunk = tx.parse_chunks(template_span)[0]
    t_dec, _ = tx.decode_chunk(template_span, t_chunk)
    tt = tx.parse_texture(t_dec, t_chunk)
    require(tt.name == "dread" and t_chunk.system_bytes == 128, "the dread texture layout changed")
    system = bytearray(t_dec[:128])
    system[32:128] = bytes(96)
    raw_name = (name + "\0").encode("utf-16-le")
    descriptor = (32 + len(raw_name) + 3) & ~3
    require(descriptor + 24 <= 128, f"{name}: the name is too long")
    system[32:32 + len(raw_name)] = raw_name
    pal_at = (pixel_bytes + 127) & ~127
    struct.pack_into("<6I", system, descriptor, u0, 0, pal_at, packed, packed_size, flags)
    struct.pack_into("<i", system, 0x10, 32 - 0x10 + 1)
    struct.pack_into("<i", system, 0x14, descriptor - 0x14 + 1)
    body = bytes(system) + pixels + bytes(pal_at - pixel_bytes) + gray
    raw = struct.pack("<4s7I", b"TXTR", len(body), 128, len(body) - 128, 0, 0, 0, 0) + body
    check = tx.parse_chunks(raw)[0]
    out, _ = tx.decode_chunk(raw, check)
    info = tx.parse_texture(out, check)
    require(info.name == name and info.format_name == "P8" and (info.width, info.height, info.mip_levels) == (w, h, mips),
            f"{name}: the gray texture does not read back")
    return raw


# ------------------------------------------------------------------------------------------------ records (CACR)
RECORD_COUNT, RECORD_SLOT, RECORD_HASHES, RECORD_NAME_AT = 0x60, 0x64, 0x68, 0x20


def member_hash(name: str) -> int:
    return zlib.crc32(name.encode("utf-16le")) & 0xFFFFFFFF


def name_id(name: str) -> int:
    return zlib.crc32(name.upper().encode("utf-16le")) & 0xFFFFFFFF


def parse_record(record: bytes) -> tuple[int, int, list[int]]:
    require(record[:4] == b"CACR", "the face record is not a CACR")
    count, slot = struct.unpack_from("<II", record, RECORD_COUNT)
    hashes = list(struct.unpack_from(f"<{count}I", record, RECORD_HASHES))
    require(hashes == sorted(hashes) and len(set(hashes)) == count, "the face record hashes are not sorted")
    return count, slot, hashes


def grow_record(record: bytes, cdf: bytes, additions: Mapping[str, bytes], cdf_name: str) -> tuple[bytes, bytes]:
    """(new record naming ``cdf_name``, new aggregate): every existing slot plus ``additions`` {member: slot}."""
    count, slot, hashes = parse_record(record)
    require(len(cdf) == count * slot, "the face aggregate does not match its record")
    slots = {h: cdf[i * slot:(i + 1) * slot] for i, h in enumerate(hashes)}
    for member, data in additions.items():
        h = member_hash(member)
        require(h not in slots, f"{member} already exists in the face record")
        require(len(data) == slot, f"{member}: a slot is {slot} bytes")
        slots[h] = data
    order = sorted(slots)
    new = bytearray(record[:RECORD_HASHES])
    struct.pack_into("<I", new, RECORD_COUNT, len(order))
    new[RECORD_NAME_AT:RECORD_NAME_AT + 0x40] = cdf_name.encode("utf-16-le").ljust(0x40, b"\0")
    new += struct.pack(f"<{len(order)}I", *order) + bytes(20)
    struct.pack_into("<I", new, 4, len(new) - 32)
    return bytes(new), b"".join(slots[h] for h in order)


# ------------------------------------------------------------------------------------------------ the image
def _archive(path):
    from tools.nfl2k5_playbook_position_recode import OuterImage  # noqa: PLC0415
    return OuterImage(Path(path))


def _outer(archive, name: str):
    wanted = name_id(name)
    for entry in archive.entries:
        if entry.name_id == wanted:
            return entry
    return None


def _read_outer(archive, name: str) -> bytes:
    entry = _outer(archive, name)
    require(entry is not None, f"the image has no {name}")
    return archive.read(entry.virtual_offset, entry.size)


def template_flags(path: Path | str) -> list[int]:
    """The flag byte of draft template record 2 in every ROST resource on the image (all must be 0)."""
    from . import nfl2k5_roster_records as rr  # noqa: PLC0415
    out = []
    with _archive(path) as archive:
        for entry in archive.entries:
            if entry.size < 0x100 or archive.read(entry.virtual_offset, 4) != b"ROST":
                continue
            body = archive.read(entry.virtual_offset, entry.size)[0x20:]
            try:
                doc = rr.RosterDocument(body, base=0)
            except Exception:  # noqa: BLE001 - foreign ROST resources are judged by their own owners
                continue
            pool = doc.by_pool("secondary")
            if len(pool) > FLAG_RECORD:
                out.append(body[pool[FLAG_RECORD].offset + FLAG_BYTE])
    return out


def plan(path: Path | str) -> dict[str, Any]:
    """Everything the image half writes, read from the image (nothing written)."""
    from . import nfl2k5_rookie_faces as rf  # noqa: PLC0415
    require(available(), "the alien prospect art is missing or does not match its pins")
    used = rf.roster_photo_ids(path)
    require(ALIEN_ID not in used, f"a roster on this image already uses photo id {ALIEN_ID}")
    require(not any(f & FLAG_BIT for f in template_flags(path)), "a roster on this image has the alien flag set")
    with _archive(path) as archive:
        record = _read_outer(archive, RETAIL_RECORD)
        cdf_name = record[RECORD_NAME_AT:RECORD_NAME_AT + 0x40].decode("utf-16-le").split("\0")[0]
        cdf = _read_outer(archive, cdf_name)
        template_pf = _read_outer(archive, SHAPE_SOURCE)
        present = {e.name_id for e in archive.entries}
    for name in (RECORD_NAME, CDF_NAME, PF_NAME):
        require(name_id(name) not in present, f"the image already has {name}")
    count, slot, hashes = parse_record(record)
    i = hashes.index(member_hash("f9001"))
    template = cdf[i * slot:(i + 1) * slot]
    _w, _h, f_rgb = art_rgb("f")
    _w, _h, h_rgb = art_rgb("h")
    _w, _h, n_rgb = art_rgb("n")
    face = face_slot(template, "f9001", f_rgb)
    new_record, new_cdf = grow_record(record, cdf, {"f" + ALIEN_NAME: face}, CDF_NAME)
    return {"record": new_record, "cdf": new_cdf, "pf": pf_package(template_pf, h_rgb, n_rgb),
            "faces_before": count, "slot": slot}


def appended(path: Path | str) -> list[tuple[str, bytes]]:
    """The new outers (face record, face aggregate, close-up package), for rookie faces' single archive rewrite."""
    p = plan(path)
    return [(RECORD_NAME, p["record"]), (CDF_NAME, p["cdf"]), (PF_NAME, p["pf"])]


def _raw_txtr(decoded: bytes, chunk, name: str, video: bytes) -> bytes:
    """A raw TXTR copying ``decoded``'s system buffer (with ``name`` moved into it) and a caller-supplied video."""
    tx = _tx()
    t = tx.parse_texture(decoded, chunk)
    system = bytearray(decoded[:chunk.system_bytes])
    raw_name = (name + "\0").encode("utf-16-le")
    name_at = 0x20
    desc_at = (name_at + len(raw_name) + 3) & ~3
    require(desc_at + 0x18 <= chunk.system_bytes, f"{name}: the name is too long")
    descriptor = bytes(decoded[t.descriptor_offset:t.descriptor_offset + 0x18])
    system[name_at:desc_at] = bytes(desc_at - name_at)
    system[name_at:name_at + len(raw_name)] = raw_name
    system[desc_at:desc_at + 0x18] = descriptor
    struct.pack_into("<I", system, 0x10, name_at - 0x0F)
    struct.pack_into("<I", system, 0x14, desc_at - 0x13)
    body = bytes(system) + bytes(video)
    raw = struct.pack("<4s7I", b"TXTR", len(body), chunk.system_bytes, len(body) - chunk.system_bytes, 0, 0, 0, 0) + body
    check = tx.parse_chunks(raw)[0]
    out, _ = tx.decode_chunk(raw, check)
    info = tx.parse_texture(out, check)
    require(info.name == name and info.format_name == t.format_name
            and (info.width, info.height, info.mip_levels) == (t.width, t.height, t.mip_levels),
            f"{name}: the raw texture does not read back")
    return raw


def portrait_sf_texture(outer3: bytes) -> bytes:
    """alien_sf: the alien's own portrait (128 x 128) cut to the retail sf0 far-face layout (32 x 32 P8, one mip).
    The far face is a front-facing picture on the low-LOD head, not a UV atlas, so the headshot is the right source."""
    tx = _tx()
    for c in tx.parse_chunks(outer3, allow_trailing=True):
        if c.kind != "TXTR" or c.compressed:
            continue
        span = outer3[c.offset:c.offset + 32 + c.stored_size]
        decoded, _ = tx.decode_chunk(span, tx.parse_chunks(span)[0])
        t = tx.parse_texture(decoded, c)
        if t.name != SF_SOURCE:
            continue
        require(t.format_name == "P8" and (t.width, t.height, t.mip_levels) == (32, 32, 1),
                "the far-face template changed")
        video = bytearray(decoded[c.system_bytes:])
        require(len(video) == 2048 and t.pixel_offset + 1024 <= len(video) and t.palette_offset + 1024 <= len(video),
                "the far-face template is truncated")
        from PIL import Image  # noqa: PLC0415
        w, h, rgb = art_rgb("portrait")
        im = Image.frombytes("RGB", (w, h), rgb).resize((32, 32), Image.LANCZOS)
        q = im.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette() or []
        idx = tx.swizzle_2d(q.tobytes(), 32, 32, 1)
        require(len(idx) == 1024, "the far face does not quantise to 32 x 32")
        palette = bytearray(1024)
        for i in range(256):
            r, g, b = (pal[3 * i], pal[3 * i + 1], pal[3 * i + 2]) if 3 * i + 3 <= len(pal) else (0, 0, 0)
            palette[4 * i:4 * i + 4] = bytes((b, g, r, 255))
        video[t.pixel_offset:t.pixel_offset + 1024] = idx
        video[t.palette_offset:t.palette_offset + 1024] = palette
        return _raw_txtr(decoded, c, SF_TEXTURE, bytes(video))
    raise AlienProspectError(f"outer 3 has no {SF_SOURCE}")


def gray_collection(outer3: bytes) -> tuple[bytes, dict[str, Any]]:
    """Outer 3 with the five gray textures added after every resource except trailing hair-style textures."""
    from . import nfl2k5_hair_styles as hair  # noqa: PLC0415
    tx = _tx()
    chunks = tx.parse_chunks(outer3, allow_trailing=True)
    names = {}
    for c in chunks:
        if c.kind == "TXTR" and not c.compressed:
            try:
                names[c.index] = _resource_name(outer3, c)
            except (ValueError, IndexError, struct.error):
                pass
    require(not any(n.startswith("alien_") for n in names.values()), "outer 3 already has the gray textures")
    hair_names = {hair.texture_name(k) for k in hair.TEXTURES}
    insert = len(chunks)
    while insert > 0 and names.get(insert - 1) in hair_names:
        insert -= 1
    template = outer3[chunks[hair.DREAD_CHUNK].offset:chunks[hair.DREAD_CHUNK].offset + 32
                      + chunks[hair.DREAD_CHUNK].stored_size]
    new = [gray_texture(outer3, name, source, template) for name, source in GRAY_TEXTURES]
    new.append(portrait_sf_texture(outer3))
    new.append(gray_texture(outer3, SIDE_TEXTURE, SIDE_SOURCE, template, flat=128))
    at = chunks[insert].offset if insert < len(chunks) else chunks[-1].offset + 32 + chunks[-1].stored_size
    out = bytes(outer3[:at]) + b"".join(new) + bytes(outer3[at:])
    require(gray_status(out) == "applied", "the gray textures do not read back")
    labels = [n for n, _s in GRAY_TEXTURES] + [SF_TEXTURE, SIDE_TEXTURE]
    return out, {"textures": [{"name": n, "bytes": len(d), "sha256": sha(d)} for n, d in zip(labels, new)],
                 "inserted_before_chunk": insert, "growth": len(out) - len(outer3)}


def gray_status(outer3: bytes) -> str:
    tx = _tx()
    found = set()
    for c in tx.parse_chunks(outer3, allow_trailing=True):
        if c.kind == "TXTR" and not c.compressed:
            try:
                n = _resource_name(outer3, c)
            except (ValueError, IndexError, struct.error):
                continue
            if n.startswith("alien_"):
                found.add(n)
    if not found:
        return "retail"
    want = {n for n, _s in GRAY_TEXTURES} | {SF_TEXTURE, SIDE_TEXTURE}
    return "applied" if found == want else "foreign"


def apply_collection_to_image(path: Path | str, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Grow outer 3 with the gray textures on a disposable output image (pack 0 rewritten at the image end through
    the shared growth writer, the hair styles' path)."""
    from . import nfl2k5_hair_styles as hair  # noqa: PLC0415
    from . import nfl2k5_resource_growth as growth  # noqa: PLC0415
    from . import nfl2k5_music_archive as archive  # noqa: PLC0415
    from . import platform_compat as pio  # noqa: PLC0415
    import os  # noqa: PLC0415
    say = progress or (lambda _m: None)
    path = Path(path).resolve()
    say("Alien prospect: gray skin textures")
    with archive.Disc(path, descriptors=()) as disc:
        identity = archive.identity(path)
        entry, before = hair._outer3(disc)
        after, receipt = gray_collection(before)
        p = disc.pack_extents["0"]
        read_pack = lambda n, at: disc.read(n, p.byte_offset + at)  # noqa: E731
        lay = growth.plan_pack0(read_pack, p.size, hair.OUTER, hair.OUTER_ID, after, padding_bytes=(0, 0x9F))
        require(lay.start == entry.virtual_offset, "the common collection is not in pack 0")
        old_size = disc.image_size
        node = disc.nodes["0"][0]
        old_node = struct.pack("<II", p.sector, p.size)
        require(archive.identity(path) == identity, "the image changed during the alien prospect preflight")
        with path.open("r+b") as writer:
            fd = writer.fileno()
            try:
                offset = archive.align_up(old_size)
                if offset > old_size:
                    require(pio.pwrite(fd, bytes(offset - old_size), old_size) == offset - old_size, "short write")
                transport = growth.write_pack0(fd, read_pack, lay, offset)
                new_node = struct.pack("<II", (offset - p.base_offset) // 2048, lay.size_after)
                require(pio.pwrite(fd, new_node, node) == 8, "short node write")
                os.fsync(fd)
            except Exception:
                pio.pwrite(fd, old_node, node)
                os.ftruncate(fd, old_size)
                os.fsync(fd)
                raise
            receipt["image_growth"] = os.fstat(fd).st_size - old_size
    receipt["pack_transport"] = transport
    require(collection_image_status(path) == "applied", "alien prospect: the gray textures did not read back")
    return receipt


def collection_image_status(path: Path | str) -> str:
    from . import nfl2k5_hair_styles as hair  # noqa: PLC0415
    from . import nfl2k5_music_archive as archive  # noqa: PLC0415
    try:
        with archive.Disc(Path(path), descriptors=()) as disc:
            return gray_status(hair._outer3(disc)[1])
    except (OSError, ValueError, KeyError, IndexError, struct.error):
        return "foreign"


def image_status(path: Path | str, read_xbe: Callable[[Path], bytes]) -> str:
    """retail | applied | test | foreign: executable, gray textures, face record + aggregate, package, portrait."""
    from . import nfl2k5_rookie_faces as rf  # noqa: PLC0415
    state = xbe_status(read_xbe(Path(path)))
    gray = collection_image_status(path)
    with _archive(path) as archive:
        rec, cdf, pf = _outer(archive, RECORD_NAME), _outer(archive, CDF_NAME), _outer(archive, PF_NAME)
        if state == "retail":
            return "retail" if gray == "retail" and rec is None and cdf is None and pf is None else "foreign"
        if state not in ("applied", "test") or gray != "applied" or None in (rec, cdf, pf):
            return "foreign"
        record = archive.read(rec.virtual_offset, rec.size)
        count, slot, hashes = parse_record(record)
        if cdf.size != count * slot or member_hash("f" + ALIEN_NAME) not in hashes:
            return "foreign"
        if record[RECORD_NAME_AT:RECORD_NAME_AT + 2 * len(CDF_NAME)] != CDF_NAME.encode("utf-16-le"):
            return "foreign"
        prec = _outer(archive, rf.RECORD_NAME)
        if prec is None or rf.member_hash(ALIEN_NAME) not in rf.parse_record(
                archive.read(prec.virtual_offset, prec.size))[2]:
            return "foreign"
    return state


def apply_to_image(path: Path | str, read_xbe: Callable[[Path], bytes], write_xbe: Callable[[Path, bytes], None], *,
                   test: bool = False, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """The second half, after rookie faces added the portrait and the appended outers (``appended``): the gray
    textures in outer 3, then the executable."""
    path = Path(path)
    payload = read_xbe(path)
    require(xbe_status(payload) == "retail", f"the alien prospect's executable bytes are {xbe_status(payload)}")
    receipt = {"collection": apply_collection_to_image(path, progress=progress)}
    patched, receipt["xbe"] = apply(payload, test=test)
    write_xbe(path, patched)
    state = image_status(path, read_xbe)
    require(state == ("test" if test else "applied"), f"alien prospect read-back: {state}")
    receipt.update(state=state, photo_id=ALIEN_ID, odds_per_class=f"1 in {ODDS}", threshold=THRESH)
    return receipt
