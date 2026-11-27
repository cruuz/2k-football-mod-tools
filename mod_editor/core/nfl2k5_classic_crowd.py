"""The classic Seamen's own crowd (job b81-seamen). EXPERIMENTAL / UNWITNESSED.

The owner (2026-11-25, playing the 11/20 private disc): "fans also wearing dolphins gear". Every crowd loader formats
its file name from the team's art code (+0x10C), and the classic Seamen ride the Dolphins' code 14, so the stands
(``14{h,a}{d,r}{n,s}.iff``: the crowd strips and the sideline staff's ``coachshirt``), the fan cutaways (``cgfair14``,
``cgfoul14``, ``ns14``, ``tg14``), the cheerleaders (``ch14``) and the tunnel's inflatable helmet (``ih14``) were the
Dolphins'. No crowd set on the disc is neutral: every code's cutaway sets carry a logo (the clubs', the NFL shield,
the conferences', the created teams', ESPN's).

This owner gives the Seamen their own, in their colours (teal, black, white) with no Dolphins mark:

* fourteen new files under the art code ``SM`` (``SM{h,a}{d,r}{n,s}.iff``, ``cgfairSM``, ``cgfoulSM``, ``nsSM``,
  ``tgSM``, ``chSM``, ``ihSM``), each a copy of the Dolphins' retail file read from the user's own disc, with its
  textures recoloured: the Dolphins' aqua becomes the Seamen teal and their orange (and navy) becomes black, each texel
  keeping its shade (``recolour``; the cheerleaders' uniforms, with no skin, take every orange-red). The clothing,
  sign, plate, foam finger, box and face-paint pictures the 2026 fans art draws for Miami are drawn for the Seamen
  without their marks (``data/nfl2k5_classic_teams/crowd``, tools/b77/ss2_crowd.py: the same recolour, every logo and
  word inpainted to plain cloth); the eight painted chest letters (D-O-L-P-H-I-N-S) and the cheerleaders' logo decal
  are left clear; the inflatable helmet's two dolphin logos and its "Dolphins" plate word are refilled from the helmet
  around them at build time (``paint_out``, on the user's own texels); heads, digits, cement and chairs keep the
  retail bytes;
* after them one filler (``sm1_classic_crowd_end.bin``, 2,048 zero bytes): the archive's last file must end on a
  sector (``nfl2k5_historic_styles.rewrite_plan``), a copy is exactly as long as its retail file, and none of the
  Dolphins' fourteen ends on one (the last copy, ``ihSM.iff``, is the 41,456 bytes of ``ih14.iff``). Without it the
  step was left out of every build (#44, the 11/27 release build: "the last outer must end on a sector");
* the executable is written by the Studio's descriptor writer for built executables
  (``nfl2k5_depth_chart_storage.write_image_xbe``, the one ``mod_build._write_xbe_bytes`` uses), whatever its length
  (#44). The helper page lies past the pool the build's executable stage sizes (a late owner no earlier step reserves;
  in the release build that stage ends at 0x1532000, exactly where the page starts), so installing it adds pages to
  the file, which the fixed-span writer the step first used refuses ("fixed-span writer cannot grow a resource") after
  the archive is already rewritten. That writer also opens the copy buffered, which the build's optional-step journal
  cannot undo: a failure after it stops the build instead of leaving the step out (#44 review F1), so it is not used
  for an executable of the same length either. Whether the copy can take the new executable is checked before
  anything is written;
* the 's' stand packages (picked by venue code 48 alone, 0x62D68: ESPN Stadium, the Seamen's home) carry the classic
  field's own authored end zones (home ``endzone_south_*``, away ``endzone_north_*``, from
  ``data/nfl2k5_classic_teams/field``), because the field swap at 0x9C5DE binds the field's end zones to the first
  loaded textures of those names (review M1);
* a redirect in the executable: six helpers in one fixed allocator page (nfl2k5_xbe_space.CLASSIC_CROWD_VA,
  0x1532000), called at the six places that read the art code for these files (PROVED OFFLINE by static reading of
  the USA executable):

  - 0x12F2EC (``mov edx,[ebx]; mov eax,[edx+0x10C]``): a cutaway's one-argument texture set; ECX holds its format,
    and only ``ns%s.iff`` (0xE76BE4), ``tg%s.iff`` (0xE77FB0), ``ch%s.iff`` (0xE770F4) and ``ih%s.iff`` (0xE7704C)
    move (the trainer set ``tr%s.iff`` and the Super Bowl newspaper ``np%s.iff`` stay);
  - 0x12F304 (``mov eax,[ebx]; mov edx,[eax+0x10C]``): the two-argument ``cg%s%s.iff`` set (0xE76A68);
  - 0x62D86 (``mov eax,[0xB30B64]``) and 0x62DAD (``mov edx,[0xB30970]``): the away (``%sa%c%c.iff``) and home
    (``%sh%c%c.iff``) stand packages, from the match contexts 0xB30A58 and 0xB30864;
  - 0x1257DD (``mov edx,[eax+0x10C]``, after call 0x61C50) and 0x1257FF (``mov ecx,[eax+0x10C]``, after 0x61C60): the
    tunnel's home and away inflatable helmets (``ih%s.iff`` 0xE73AE0).

  Each helper replays the read and, when the team's identity (+0x118, the byte the superfan selector 0x81760 also
  reads) is the Seamen's (230), returns the ``SM`` text instead. Every other team reads its own code as before.

Its own build setting (``classic_crowd``, on in the experimental preset) and optional step, right after the classic
teams, which it needs.
"""
from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART_DIR = ROOT / "data/nfl2k5_classic_teams/crowd"
# b81-seamen review M1: the 's' stand packages are picked by venue code 48 alone (0x62D68: venue file name "48" -> 's'),
# and ESPN Stadium is the Seamen's home. Their end zone textures (home endzone_south_*, away endzone_north_*, P8 256x128,
# five mips) replace the field's end zones by name (the swap at 0x9C5DE binds endzone_S_L -> endzone_south_left ... to the
# first loaded TXTR), so they carry the classic field's own authored strips: the Seamen's end zone in every s48 game.
FIELD_DIR = ROOT / "data/nfl2k5_classic_teams/field"
END_ZONE_PARTS = ("left", "middle", "right")              # 256-texel thirds of the 768x128 strip, as classic_field
OWNER = "nfl2k5_classic_crowd"
CODE = "SM"                                   # the Seamen's own crowd code (file names only)
SOURCE_CODE = "14"                            # the Dolphins' files the Seamen's crowd is drawn from
IDENTITY = 230                                # nfl2k5_classic_teams.own_name_identity()
TEAL = (0, 146, 132)                          # #009284, the Seamen's teal (their kit and logo card)
BLACK = (34, 34, 36)                          # the black cloth at full light
AQUA_REF_VALUE = 151 / 255                    # the Dolphins' aqua (#008E97) at full light
ORANGE_REF_VALUE = 244 / 255                  # the Dolphins' orange (#F4581F)
STANDS = tuple(f"{side}{weather}{event}" for side in "ha" for weather in "dr" for event in "ns")
CUTAWAYS = ("cgfair{}", "cgfoul{}", "ns{}", "tg{}", "ch{}", "ih{}")   # review S1: + the cheerleaders, the tunnel helmet
FILES = tuple([(f"{CODE}{s}.iff", f"{SOURCE_CODE}{s}.iff") for s in STANDS]
              + [(c.format(CODE) + ".iff", c.format(SOURCE_CODE) + ".iff") for c in CUTAWAYS])
# #44 (11/27): packaging only, never loaded. The archive's last file must end on a sector and no copy of a Dolphins
# file does, so the step always closes its fourteen files with this one (as the classic teams, the historic styles and
# the rookie faces close theirs).
FILLER = "sm1_classic_crowd_end.bin"
SECTOR = 2048
PICTURES = ("tshirt", "jersey", "sweatshirt", "varsity", "puffyjacket", "hardhat", "crowdsign", "foamfinger", "boxlogo",
            "fanplate", "head03")
CLEAR = tuple(f"noshirtns{n:02d}" for n in range(1, 9))     # the painted chest letters
DECALS = ("uniformlogo",)
WARM = ("uniformfair", "uniformfoul")          # no skin or lips: recolour(warm=True)                     # the cheerleaders' Dolphins logo decal (on transparency): cleared
RECOLOURED = ("coachshirt", "uniformfair", "uniformfoul") + tuple(f"p{n:03d}" for n in range(1, 17))
# review S1: the tunnel's inflatable helmet (ihSM): recoloured, and its marks painted out from the helmet around them
# (two dolphin logos and the "Dolphins" plate word; boxes in texels of the retail 256x256 texture, each holding the
# whole mark: its saturated texels grown by MARK_GROW are refilled by diffusion from their neighbours)
PAINTED_OUT = {"inflatablehelmet": ((48, 42, 101, 109), (48, 147, 101, 214), (202, 65, 245, 78))}
MARK_GROW = 3
PAINTED_HEADS = ("head01", "head02")          # the Dolphins' face paint (head03 is a picture)
HEAD_FACE_TOP = 32                            # rows above this hold the ear, teeth and lips


class ClassicCrowdError(ValueError):
    """The crowd files or the redirect cannot be made."""


UI_LABEL = "The Seamen's own crowd (classic teams)"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. When the 2006 Seamen play, the fans in the stands, the crowd cutaways, the "
             "cheerleaders and the tunnel's inflatable helmet wear Seamen teal, black and white with no Dolphins marks, "
             "and ESPN Stadium (their home) shows their own end zones, instead of the Dolphins' sets they share a slot "
             "with. Made from your own disc's Dolphins files. Built only with the Classic teams in Quick Game option.")


def require(ok, message):
    if not ok:
        raise ClassicCrowdError("classic crowd: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


# -- colour ---------------------------------------------------------------------------------------------------------

def recolour(rgba, *, warm=False):
    """The Dolphins' aqua becomes the Seamen teal and their orange and navy become black, each texel keeping its shade
    (its HSV value against the colour's full-light value); every other texel (white, greys, skin, the transparent
    key) stays. ``rgba`` is an (h, w, 4) uint8 array; returns a new one. ``warm``: a texture with no skin or lips (the
    cheerleaders' uniforms, review S1) takes every saturated orange-red down to hue 0 and into its shading as well."""
    import numpy as np
    a = np.asarray(rgba, np.uint8)
    rgb = a[..., :3].astype(np.float64) / 255.0
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    value, chroma = mx, mx - mn
    sat = np.where(mx > 0, chroma / np.maximum(mx, 1e-9), 0.0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.zeros_like(mx)
    nz = chroma > 1e-9
    hr = nz & (mx == r)
    hg = nz & (mx == g) & ~hr
    hb = nz & ~hr & ~hg
    hue[hr] = (60 * ((g - b)[hr] / chroma[hr])) % 360
    hue[hg] = 60 * ((b - r)[hg] / chroma[hg]) + 120
    hue[hb] = 60 * ((r - g)[hb] / chroma[hb]) + 240
    aqua = (hue >= 160) & (hue <= 205) & (sat >= 0.30) & (value >= 0.10)
    # bright, fully saturated orange only: red lips (hue < 12), skin and hair in shadow (lower value or saturation) stay
    orange = (hue >= 12) & (hue <= 36) & (sat >= 0.72) & (value >= 0.55)
    if warm:
        orange = ((hue <= 36) | (hue >= 350)) & (sat >= 0.60) & (value >= 0.20)
    navy = (hue > 205) & (hue <= 250) & (sat >= 0.45) & (value < 0.55)
    out = a.copy().astype(np.float64)
    teal = np.asarray(TEAL, np.float64)[None, :]
    black = np.asarray(BLACK, np.float64)[None, :]
    out[aqua, :3] = teal * np.clip(value[aqua] / AQUA_REF_VALUE, 0, 1.6)[:, None]
    out[orange, :3] = black * np.clip(value[orange] / ORANGE_REF_VALUE, 0, 1.4)[:, None]
    out[navy, :3] = black * np.clip(value[navy] / 0.42, 0, 1.4)[:, None]
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


# -- the executable: the redirect ------------------------------------------------------------------------------------

CODE_SIZE = 0x1000                                   # one fixed page (nfl2k5_xbe_space.CLASSIC_CROWD_VA); the pool is RWX
REQUESTS = ((OWNER, "code", CODE_SIZE, CODE_SIZE),)  # = nfl2k5_xbe_space.CLASSIC_CROWD_REQUEST
# A fixed page never advances the pool cursor and every other pool owner steps over it, so installing it at the classic
# teams step moves no owner and no later owner can take it. A code owner in the late order moved v3 addresses, and a
# read-only owner after the classic block pushed v3 sets into the pool (test_nfl2k5_allocator_pool, 11/25).
FORMAT_CG, FORMAT_NS, FORMAT_TG = 0xE76A68, 0xE76BE4, 0xE77FB0     # cg%s%s.iff, ns%s.iff, tg%s.iff (UTF-16)
FORMAT_CH, FORMAT_IH = 0xE770F4, 0xE7704C     # review S1: the cutaway sets ch%s.iff (cheerleaders), ih%s.iff (helmet)
FORMAT_IH_TUNNEL = 0xE73AE0                   # the tunnel loader's own ih%s.iff (0x1257EC, 0x12580E)
HOME_CODE, AWAY_CODE = 0xB30970, 0xB30B64                          # the match contexts' +0x10C (0xB30864, 0xB30A58)
HOME_ID, AWAY_ID = 0xB3097C, 0xB30B70                              # their +0x118
# (name, site VA, retail bytes): each site becomes "call helper" and NOP padding to the retail length
SITES = (("cutaway_set", 0x12F2EC, bytes.fromhex("8b138b820c010000")),    # mov edx,[ebx]; mov eax,[edx+0x10C]
         ("cutaway_cg", 0x12F304, bytes.fromhex("8b038b900c010000")),     # mov eax,[ebx]; mov edx,[eax+0x10C]
         ("stands_away", 0x62D86, bytes.fromhex("a1640bb300")),           # mov eax,[0xB30B64]
         ("stands_home", 0x62DAD, bytes.fromhex("8b157009b300")),         # mov edx,[0xB30970]
         # review S1: the tunnel's inflatable helmets, after call 0x61C50 (home context) / 0x61C60 (away context)
         ("helmet_home", 0x1257DD, bytes.fromhex("8b900c010000")),        # mov edx,[eax+0x10C]
         ("helmet_away", 0x1257FF, bytes.fromhex("8b880c010000")))        # mov ecx,[eax+0x10C]
# The retail formats and context fields the helpers depend on (read once, pinned): the three format strings.
FORMAT_TEXTS = ((FORMAT_CG, "cg%s%s.iff"), (FORMAT_NS, "ns%s.iff"), (FORMAT_TG, "tg%s.iff"), (FORMAT_CH, "ch%s.iff"),
                (FORMAT_IH, "ih%s.iff"), (FORMAT_IH_TUNNEL, "ih%s.iff"))


def _u32(value):
    return struct.pack("<I", value & 0xFFFFFFFF)


def code_for(va):
    """(the page's bytes, {helper name: VA}). Offset 0: "SM" (UTF-16, NUL); then the six helpers (177 B). Each replays the
    site's own read(s) and, when the team's identity byte is the Seamen's, returns the SM text instead; flags are free at
    every site (the next instructions set or ignore them) and no other register changes."""
    text = va
    out = bytearray(CODE.encode("utf-16le") + b"\0\0")
    out = out.ljust(8, b"\0")
    labels = {}

    def helper(name, body):
        labels[name] = va + len(out)
        out.extend(body)

    # cutaway_set: EBX -> team pointer; ECX = the set's format; ns/tg/ch/ih move (the trainer set tr%s and the Super
    # Bowl newspaper np%s stay)
    sub = b"\xb8" + _u32(text) + b"\xc3"                               # mov eax, SM ; ret
    tail = b""
    moved = (FORMAT_NS, FORMAT_TG, FORMAT_CH, FORMAT_IH)
    for k, fmt in enumerate(moved[:-1]):                                 # cmp ecx,fmt ; je sub
        tail += b"\x81\xf9" + _u32(fmt) + b"\x74" + bytes([8 * (len(moved) - 1 - k)])   # over the pairs left
    tail += b"\x81\xf9" + _u32(moved[-1]) + b"\x75" + bytes([len(sub) - 1])   # cmp ecx,ih ; jne ret
    helper("cutaway_set", b"\x8b\x13" + b"\x8b\x82\x0c\x01\x00\x00"     # mov edx,[ebx] ; mov eax,[edx+0x10C]
           + b"\x80\xba\x18\x01\x00\x00" + bytes([IDENTITY])           # cmp byte [edx+0x118], 230
           + b"\x75" + bytes([len(tail) + len(sub) - 1]) + tail + sub)  # jne ret
    # cutaway_cg: EBX -> team pointer; ECX = the format; only cg%s%s moves
    sub = b"\xba" + _u32(text) + b"\xc3"                               # mov edx, SM ; ret
    tail = b"\x81\xf9" + _u32(FORMAT_CG) + b"\x75" + bytes([len(sub) - 1])
    helper("cutaway_cg", b"\x8b\x03" + b"\x8b\x90\x0c\x01\x00\x00"      # mov eax,[ebx] ; mov edx,[eax+0x10C]
           + b"\x80\xb8\x18\x01\x00\x00" + bytes([IDENTITY])           # cmp byte [eax+0x118], 230
           + b"\x75" + bytes([len(tail) + len(sub) - 1]) + tail + sub)
    # stands_away / stands_home: the match contexts' code pointer and identity
    sub = b"\xb8" + _u32(text) + b"\xc3"
    helper("stands_away", b"\xa1" + _u32(AWAY_CODE) + b"\x80\x3d" + _u32(AWAY_ID) + bytes([IDENTITY])
           + b"\x75" + bytes([len(sub) - 1]) + sub)
    sub = b"\xba" + _u32(text) + b"\xc3"
    helper("stands_home", b"\x8b\x15" + _u32(HOME_CODE) + b"\x80\x3d" + _u32(HOME_ID) + bytes([IDENTITY])
           + b"\x75" + bytes([len(sub) - 1]) + sub)
    # review S1: the tunnel's inflatable helmets: EAX is the match context 0x61C50 / 0x61C60 returned
    sub = b"\xba" + _u32(text) + b"\xc3"                               # mov edx, SM ; ret
    helper("helmet_home", b"\x8b\x90\x0c\x01\x00\x00"                  # mov edx,[eax+0x10C]
           + b"\x80\xb8\x18\x01\x00\x00" + bytes([IDENTITY])           # cmp byte [eax+0x118], 230
           + b"\x75" + bytes([len(sub) - 1]) + sub)
    sub = b"\xb9" + _u32(text) + b"\xc3"                               # mov ecx, SM ; ret
    helper("helmet_away", b"\x8b\x88\x0c\x01\x00\x00"                  # mov ecx,[eax+0x10C]
           + b"\x80\xb8\x18\x01\x00\x00" + bytes([IDENTITY])
           + b"\x75" + bytes([len(sub) - 1]) + sub)
    require(len(out) <= 256, "helpers exceed their 256 bytes")
    return bytes(out).ljust(CODE_SIZE, b"\xcc"), labels


def site_bytes(name, labels):
    va, retail = next((v, r) for n, v, r in SITES if n == name)
    call = b"\xe8" + struct.pack("<i", labels[name] - va - 5)
    return call + b"\x90" * (len(retail) - len(call))


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    require(len(rows) == 1 and rows[0]["kind"] == "code" and rows[0]["size"] == CODE_SIZE
            and rows[0]["va"] == space.CLASSIC_CROWD_VA, "the crowd owner is not allocated at its fixed page")
    return rows[0]


def _reserved(payload):
    try:
        allocation(payload)
        return True
    except (ValueError, KeyError):
        return False


def _formats_ok(image):
    for va, text in FORMAT_TEXTS:
        raw = (text + "\0").encode("utf-16le")
        if image.read(va, len(raw)) != raw:
            return False
    return True


def xbe_status(payload):
    """'retail' (every site retail, the owner absent or empty), 'applied' (the helpers in the owner and every site
    calling them), else 'foreign'."""
    from .nfl2k5_cave_oracle import XbeImage
    try:
        image = XbeImage(payload)
        if not _formats_ok(image):
            return "foreign"
        sites = {name: image.read(va, len(retail)) for name, va, retail in SITES}
        if not _reserved(payload):
            return "retail" if all(sites[n] == r for n, _v, r in SITES) else "foreign"
        a = allocation(payload)
        body = image.read(a["va"], CODE_SIZE)
        content, labels = code_for(a["va"])
        if body in (bytes(CODE_SIZE), b"\xcc" * CODE_SIZE):
            return "retail" if all(sites[n] == r for n, _v, r in SITES) else "foreign"
        if body != content:
            return "foreign"
        return "applied" if all(sites[n] == site_bytes(n, labels) for n, _v, _r in SITES) else "foreign"
    except (ValueError, KeyError, IndexError, struct.error):
        return "foreign"


def apply_xbe(payload):
    """Install the helpers (reserving the owner when the first space pass did not) and point the six sites at them.
    Replay is a no-op."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    state = xbe_status(payload)
    require(state in ("retail", "applied"), f"the executable's crowd sites are {state}")
    if state == "applied":
        return payload, dict(status="already_applied", changed_bytes=0)
    before = payload
    reservation = {}
    if not _reserved(payload):
        require(space.is_scaleout(payload), "the classic crowd needs the scale-out allocator")
        payload, reservation = space.extend_scaleout(payload, REQUESTS)
    a = allocation(payload)
    content, labels = code_for(a["va"])
    from . import nfl2k5_classic_teams as classic
    require(classic.executable(payload, a["va"]), "the crowd helper page is not executable")
    payload, _ = space.install_code(payload, OWNER, content)
    image = XbeImage(payload)
    buf = bytearray(payload)
    edits = []
    for name, va, retail in SITES:
        off = image.offset(va, len(retail))
        require(bytes(buf[off:off + len(retail)]) == retail, f"crowd site {va:#x} is not retail")
        new = site_bytes(name, labels)
        buf[off:off + len(retail)] = new
        edits.append(dict(label=name, va=hex(va), before=retail.hex(), after=new.hex()))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(xbe_status(result) == "applied", "classic crowd executable read-back")
    return result, dict(status="applied", owner_va=hex(a["va"]), labels={k: hex(v) for k, v in labels.items()},
                        edits=edits, reservation={k: v for k, v in reservation.items() if k != "allocations"},
                        changed_bytes=sum(x != y for x, y in zip(before, result)) + abs(len(result) - len(before)))


# -- the files -------------------------------------------------------------------------------------------------------

def _palette_recolour(decoded, at, warm=False):
    """The 256-entry B,G,R,A palette at ``decoded[at:at+1024]`` recoloured in place."""
    import numpy as np
    bgra = np.frombuffer(bytes(decoded[at:at + 1024]), np.uint8).reshape(1, 256, 4)
    rgba = recolour(bgra[..., [2, 1, 0, 3]], warm=warm)
    decoded[at:at + 1024] = np.ascontiguousarray(rgba[..., [2, 1, 0, 3]]).tobytes()


_LUT = None


def _a1r5g5b5_lut():
    """{16-bit A1R5G5B5 texel: its recoloured texel} for every value (the alpha bit kept)."""
    global _LUT
    if _LUT is None:
        import numpy as np
        v = np.arange(65536, dtype=np.uint32)
        five = lambda x: ((x << 3) | (x >> 2)).astype(np.uint8)  # noqa: E731
        rgba = np.stack([five((v >> 10) & 31), five((v >> 5) & 31), five(v & 31),
                         np.where(v & 0x8000, 255, 0).astype(np.uint8)], axis=1).reshape(1, 65536, 4)
        out = recolour(rgba).reshape(65536, 4).astype(np.uint32)
        back = lambda x: np.minimum(31, (x * 31 + 127) // 255)  # noqa: E731
        _LUT = ((v & 0x8000) | (back(out[:, 0]) << 10) | (back(out[:, 1]) << 5) | back(out[:, 2])).astype(np.uint16)
    return _LUT


def _end_zone(name):
    """The authored piece for ``endzone_<north|south>_<part>``: its third of the classic field's strip."""
    import numpy as np
    from PIL import Image
    _prefix, end, part = name.split("_")
    require(end in ("north", "south") and part in END_ZONE_PARTS, f"{name}: not an end zone texture")
    with Image.open(FIELD_DIR / f"endzone_{end[0].upper()}.png") as image:
        strip = np.asarray(image.convert("RGBA"), np.uint8)
    require(strip.shape == (128, 768, 4), "end-zone art size")
    k = END_ZONE_PARTS.index(part)
    return strip[:, k * 256:(k + 1) * 256]


def mark_mask(retail, box, grow=MARK_GROW):
    """The texels of the mark in ``box`` (x0, y0, x1, y1): its saturated texels, grown by ``grow`` (the dark outline
    and the anti-aliased edge), inside the box grown by ``grow``."""
    import numpy as np
    rgb = retail[..., :3].astype(np.float64) / 255.0
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0)
    h, w = sat.shape
    x0, y0, x1, y1 = box
    mask = np.zeros((h, w), bool)
    mask[y0:y1, x0:x1] = sat[y0:y1, x0:x1] > 0.35
    for _ in range(grow):
        m = mask.copy()
        m[1:] |= mask[:-1]
        m[:-1] |= mask[1:]
        m[:, 1:] |= mask[:, :-1]
        m[:, :-1] |= mask[:, 1:]
        mask = m
    limit = np.zeros_like(mask)
    limit[max(0, y0 - grow):min(h, y1 + grow), max(0, x0 - grow):min(w, x1 + grow)] = True
    return mask & limit


def paint_out(retail, recoloured, boxes, grow=MARK_GROW, rounds=1500):
    """``recoloured`` with each box's mark (mark_mask of the RETAIL texels) refilled from the texels around it: the
    mean of the ring around the mark, relaxed to the average of each texel's four neighbours (a harmonic fill, the
    helmet's own shading carried in). Plain colour work: nothing is drawn."""
    import numpy as np
    out = recoloured.astype(np.float64).copy()
    h, w = out.shape[:2]
    for box in boxes:
        mask = mark_mask(retail, box, grow)
        ys, xs = np.nonzero(mask)
        if not len(ys):
            continue
        wy0, wy1 = max(0, ys.min() - 2), min(h, ys.max() + 3)
        wx0, wx1 = max(0, xs.min() - 2), min(w, xs.max() + 3)
        win, m = out[wy0:wy1, wx0:wx1, :3], mask[wy0:wy1, wx0:wx1]
        ring = np.zeros_like(m)
        ring[1:] |= m[:-1]
        ring[:-1] |= m[1:]
        ring[:, 1:] |= m[:, :-1]
        ring[:, :-1] |= m[:, 1:]
        ring &= ~m
        win[m] = win[ring].mean(axis=0)
        inner = m[1:-1, 1:-1]
        for _ in range(rounds):
            avg = (win[:-2, 1:-1] + win[2:, 1:-1] + win[1:-1, :-2] + win[1:-1, 2:]) / 4.0
            win[1:-1, 1:-1][inner] = avg[inner]
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def _picture(name):
    import numpy as np
    from PIL import Image
    with Image.open(ART_DIR / f"{name}.png") as image:
        return np.asarray(image.convert("RGBA"), np.uint8)


def _texture_span(span, kind, stands):
    """(new span or None for unchanged, what was done) for one TXTR / TSET chunk span of a crowd file."""
    import numpy as np
    from nfl_txtr import decode_chunk, parse_chunks, parse_texture
    from . import nfl2k5_modern_fans as fans
    from . import nfl2k5_kit_fixes_2026 as fixes
    chunk = parse_chunks(span, allow_trailing=True)[0]
    decoded, _ = decode_chunk(span, chunk)
    edited = bytearray(decoded)
    if kind == "TSET":
        if not stands:
            return None, None                         # the cutaways' TSETs are generic clothes, no club colour
        textures = fixes._tset_textures(bytes(decoded))
        for t in textures:
            _palette_recolour(edited, chunk.system_bytes + t["palette"])
        new, _fit = fans._refit(span, bytes(edited))
        return new, "recolour " + ",".join(t["name"] for t in textures)
    texture = parse_texture(decoded, chunk)
    name = texture.name
    if not stands and name in PAINTED_HEADS:
        # the face paint only: the head atlas keeps its ear, teeth and lips in the top rows, exactly retail
        mm = fans._mm()
        row = dict(width=texture.width, height=texture.height, mip_levels=1, pixel_offset=texture.pixel_offset,
                   palette_offset=texture.palette_offset, mapped_material_names=[name])
        retail = mm.read_p8(decoded, chunk.system_bytes, row)[0]
        rgba = retail.copy()
        rgba[HEAD_FACE_TOP:] = recolour(retail[HEAD_FACE_TOP:])
        for cap in fans.PALETTE_LADDER:
            edited = bytearray(decoded)
            mm.write_p8(edited, chunk.system_bytes, row, rgba, maximum=int(cap))
            try:
                new, _fit = fans._refit(span, bytes(edited))
            except fans.ModernFansError:
                continue
            return new, f"recolour {name} face ({cap} colours)"
        raise ClassicCrowdError(f"classic crowd: {name} does not fit its retail span")
    if not stands and name in PAINTED_OUT:
        # review S1: the user's own helmet texture, recoloured, its marks refilled from the helmet around them
        mm = fans._mm()
        row = dict(width=texture.width, height=texture.height, mip_levels=1, pixel_offset=texture.pixel_offset,
                   palette_offset=texture.palette_offset, mapped_material_names=[name])
        require(texture.format_name == "P8" and texture.mip_levels == 1 and (texture.width, texture.height) == (256, 256),
                f"{name}: not the retail 256x256 one-level P8 texture")
        retail = mm.read_p8(decoded, chunk.system_bytes, row)[0]
        rgba = paint_out(retail, recolour(retail), PAINTED_OUT[name])
        for cap in fans.PALETTE_LADDER:
            edited = bytearray(decoded)
            mm.write_p8(edited, chunk.system_bytes, row, rgba, maximum=int(cap))
            try:
                new, _fit = fans._refit(span, bytes(edited))
            except fans.ModernFansError:
                continue
            return new, f"recolour {name}, marks painted out ({cap} colours)"
        raise ClassicCrowdError(f"classic crowd: {name} does not fit its retail span")
    if not stands and name in (PICTURES + CLEAR + DECALS):
        mm = fans._mm()
        row = dict(width=texture.width, height=texture.height, mip_levels=1, pixel_offset=texture.pixel_offset,
                   palette_offset=texture.palette_offset, mapped_material_names=[name])
        require(texture.format_name == "P8" and texture.mip_levels == 1, f"{name}: not a one-level P8 crowd texture")
        # the 2026 fans art keeps a few retail details (KEEP_RECTS) and lays face paint over the retail head; here those
        # retail pixels are the Dolphins', so they are recoloured first (the fans writer's own compose would keep them)
        retail = recolour(mm.read_p8(decoded, chunk.system_bytes, row)[0])
        if name in CLEAR + DECALS:
            rgba = np.zeros_like(retail)
        else:
            rgba = _picture(name).copy()
            if name.startswith(fans.OVERLAY_PREFIX):
                a = rgba[..., 3:4].astype(np.float64) / 255.0
                rgba[..., :3] = np.clip(np.rint(rgba[..., :3] * a + retail[..., :3] * (1 - a)), 0, 255).astype(np.uint8)
                rgba[..., 3] = retail[..., 3]
            for x0, y0, x1, y1 in fans.KEEP_RECTS.get(name, ()):
                rgba[y0:y1, x0:x1] = retail[y0:y1, x0:x1]
        for cap in fans.PALETTE_LADDER:               # as the 2026 fans art: fewer colours until the retail span holds it
            edited = bytearray(decoded)
            mm.write_p8(edited, chunk.system_bytes, row, rgba, maximum=int(cap))
            try:
                new, _fit = fans._refit(span, bytes(edited))
            except fans.ModernFansError:
                continue
            return new, f"{'picture' if name in PICTURES else 'clear'} {name} ({cap} colours)"
        raise ClassicCrowdError(f"classic crowd: {name} does not fit its retail span")
    if name not in RECOLOURED and not stands:
        return None, None
    if name.startswith("endzone_"):
        if not stands:
            return None, None
        # review M1: the Seamen's own end zone (see FIELD_DIR); the whole mip chain from the authored third
        require(texture.format_name == "P8" and (texture.width, texture.height) == (256, 128),
                f"{name}: not the retail 256x128 P8 end zone")
        mm = fans._mm()
        row = dict(width=texture.width, height=texture.height, mip_levels=texture.mip_levels,
                   pixel_offset=texture.pixel_offset, palette_offset=texture.palette_offset,
                   mapped_material_names=[name])
        piece = np.ascontiguousarray(_end_zone(name))
        for cap in fans.PALETTE_LADDER:
            edited = bytearray(decoded)
            mm.write_p8(edited, chunk.system_bytes, row, piece, maximum=int(cap))
            try:
                new, _fit = fans._refit(span, bytes(edited))
            except fans.ModernFansError:
                continue
            return new, f"end zone {name} ({cap} colours)"
        raise ClassicCrowdError(f"classic crowd: {name} does not fit its retail span")
    if texture.format_name == "P8":
        _palette_recolour(edited, chunk.system_bytes + texture.palette_offset, warm=name in WARM)
    elif texture.format_name == "A1R5G5B5":
        texels = np.frombuffer(bytes(edited[chunk.system_bytes:]), np.uint16)
        edited[chunk.system_bytes:] = _a1r5g5b5_lut()[texels].tobytes()
    else:
        return None, None
    if bytes(edited) == bytes(decoded):
        return None, None
    new, _fit = fans._refit(span, bytes(edited))
    return new, f"recolour {name}"


def compose_file(data, stands):
    """A Dolphins crowd file (retail bytes) made the Seamen's: (bytes, [what was done per chunk])."""
    from nfl_txtr import parse_chunks
    out = bytearray(data)
    done = []
    for c in parse_chunks(data, allow_trailing=True):
        if c.kind not in ("TXTR", "TSET"):
            continue
        span = data[c.offset:c.end_offset]
        new, what = _texture_span(span, c.kind, stands)
        if new is None:
            continue
        require(len(new) == len(span), "a refit changed its span size")
        out[c.offset:c.end_offset] = new
        done.append(what)
    return bytes(out), done


_MEMO = {}


def compose_files(source_get):
    """[(new file name, bytes)] and {name: receipt} from ``source_get(name)`` (the user's retail disc). A build checks
    its install more than once; the same retail bytes are composed once per process."""
    sources = []
    for name, src in FILES:
        data = source_get(src)
        require(data is not None and len(data) > 0, f"{src} is not on the disc")
        sources.append((name, src, data))
    key = tuple(sha((ART_DIR / f"{p}.png").read_bytes()) for p in PICTURES) + tuple(sha(d) for _n, _s, d in sources)
    if key not in _MEMO:
        files, receipts = [], {}
        for name, src, data in sources:
            made, done = compose_file(data, stands=not src.startswith(("cg", "ns", "tg", "ch", "ih")))
            files.append((name, made))
            receipts[name] = dict(source=src, sha256=sha(made), changed=done)
        _MEMO[key] = (files, receipts)
    files, receipts = _MEMO[key]
    return list(files), dict(receipts)


# -- the disc: its own build step after the classic teams -------------------------------------------------------------

def _files(source):
    from . import nfl2k5_historic_styles as hs
    with hs.Source(source) as src:
        return compose_files(src.get)


def appended(files):
    """What the step appends to the archive: the fourteen files in ``FILES`` order, then ``FILLER`` (one sector of zero
    bytes), so the last file always ends on a sector whatever the fourteen sizes are."""
    files = list(files)
    require([name for name, _data in files] == [name for name, _src in FILES], "classic crowd: not the fourteen files")
    return files + [(FILLER, bytes(SECTOR))]


def _present(path, files):
    """{name: True when the disc holds exactly these bytes, False when it holds other bytes}; absent names left out."""
    from . import nfl2k5_historic_styles as hs
    from . import nfl2k5_music_archive as archive
    out = {}
    with archive.Disc(Path(path), descriptors=()) as disc:
        target = hs.Target(disc)
        for name, raw in files:
            if target.has(name):
                out[name] = target.get(name) == raw
    return out


def image_status(path, source):
    """'retail' (no redirect, none of the fourteen files nor their filler), 'applied' (the redirect, the fourteen files,
    each the compile of the user's own retail Dolphins crowd files, and the filler after them), else 'foreign'. Needs
    the classic teams applied first."""
    from . import nfl2k5_classic_teams as classic
    from . import nfl2k5_espn25_rosters as e
    try:
        payload = e.read_xbe(path)
        state = xbe_status(payload)
        wanted = appended(_files(source)[0])
        present = _present(path, wanted)
    except (ValueError, OSError, KeyError, IndexError, struct.error):
        return "foreign"
    if state == "retail" and not present:
        return "retail" if classic.xbe_status(payload) == "applied" else "foreign"
    if state == "applied" and len(present) == len(wanted) and all(present.values()):
        return "applied"
    return "foreign"


def _growing_writer_takes(before, after):
    """Refuse, before any disc write, an executable the Studio's writer (nfl2k5_depth_chart_storage.write_image_xbe)
    would refuse afterwards: it takes a recognised grown executable, of the same length or longer, in place of a
    retail or recognised grown one."""
    from . import nfl2k5_depth_chart_storage as storage
    from . import nfl2k5_xbe_space as space
    require(storage.recognized_grown_xbe(after), "classic crowd: the executable with the redirect is not a recognised one")
    require(len(before) in (storage.RETAIL_FILE_SIZE, storage.FILE_SIZE, *space.accepted_file_sizes())
            and (storage.recognized_grown_xbe(before)
                 or (len(before) == storage.RETAIL_FILE_SIZE and storage.state(before) == "retail")),
            "classic crowd: the copy's executable cannot be replaced")


def _write_xbe(path, before, after):
    """The executable with the redirect onto the copy, by the Studio's writer for built executables: the same length is
    written in place, a longer one (the helper page lies past the image's last page) is appended whole at the image end
    and its directory node switched; either is read back, synced and rolled back on any failure. The copy is opened by
    descriptor only, so the build's optional-step journal sees every write and can leave the step out."""
    from . import nfl2k5_depth_chart_storage as storage
    descriptor = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        written = storage.write_image_xbe(descriptor, after)
    finally:
        os.close(descriptor)
    return dict(writer="write_image_xbe", grown_bytes=len(after) - len(before), **written)


def apply_to_image(path, source):
    """The Seamen's own crowd on a disc whose classic teams are applied: the fourteen files and their filler appended to
    the archive, then the redirect in the executable (its fixed page, the six sites), written by descriptor. Replay is
    a no-op."""
    from . import nfl2k5_classic_teams as classic
    from . import nfl2k5_espn25_rosters as e
    from . import nfl2k5_historic_styles as hs
    state = image_status(path, source)
    if state == "applied":
        return dict(status="already_applied")
    require(state == "retail", f"classic crowd: the disc is {state}")
    payload = e.read_xbe(path)
    require(classic.own_name_identity(classic.Data.load()) == IDENTITY,
            "classic crowd: the Seamen's identity is not the one the redirect names")
    patched, xbe_receipt = apply_xbe(payload)                   # computed before any disc write
    _growing_writer_takes(payload, patched)                     # refused here, not after the archive is rewritten
    files, receipts = _files(source)
    archive_receipt = hs.rewrite_archive(path, {}, appended(files))
    xbe_receipt["write"] = _write_xbe(path, payload, patched)
    require(image_status(path, source) == "applied", "classic crowd: the disc does not read back as applied")
    return dict(status="applied", experimental=True, runtime_witnessed=False, xbe=xbe_receipt, files=receipts,
                filler=FILLER, **archive_receipt)
