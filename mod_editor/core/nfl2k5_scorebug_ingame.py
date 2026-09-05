"""Experimental, unwitnessed reference scorebug, with fixed-span resource transactions.

Runtime team selection and new event hooks are specified in the accompanying report.
This module installs the neutral fallback and retains retail score rotation. It never
installs a fixed matchup into a generic game image. Disc artwork is derived locally.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys

from .nfl2k5_scorebug_resources import RESOURCES, TEAM_LOGOS, PATCHED_SHA256, XBE_GUARDS

TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_txtr as tx
import nfl_vc_lz_fill as fill
import nfl2k5_scorebug_layout as layout
from . import nfl2k5_bump_strength as bs

VERSION = "espn-reference-v7"
PACK_SIZE = 193710080
ROOT = (320.0, 424.0)
FRAME = (-240.0, -5.0, 240.0, 43.0)
PANELS = {"away": (-236.0, -3.0, -66.0, 41.0), "home": (66.0, -3.0, 236.0, 41.0)}
PILL = (-59.0, 23.0, 53.0, 41.0)  # native slide adds 0..6 units
STRIP = (-59.0, -3.0, 59.0, 18.0)
WATERMARK = (188.0, 367.0, 284.0, 391.0)
REGIONS = {"frame": (0, 0, 64, 16), "panel": (0, 16, 64, 32),
           "down": (0, 32, 64, 40), "strip": (0, 40, 64, 48), "mark": (0, 48, 64, 64)}
ANCHORS = {"away_city": (-218, 14, -64), "home_city": (127, 14, -64),
           "away_score": (-91, 10, -59), "home_score": (91, 10, -59),
           "quarter": (-42, 2, -4), "clock_a": (26, 2, -4), "clock_b": (26, 2, -4),
           "drop_down": (-3, 27, -4), "drop_clock": (44, 2, -4)}


class ScorebugError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode(span: bytes):
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    decoded, info = tx.decode_chunk(span, chunk)
    return chunk, decoded, info


def pinned(span: bytes, record: dict) -> bytes:
    if len(span) != record["span_size"] or digest(span) != record["span_sha256"]:
        raise ScorebugError("retail resource identity changed")
    decoded = decode(span)[1]
    if digest(decoded) != record["decoded_sha256"]:
        raise ScorebugError("retail decoded identity changed")
    return decoded


def texture_image(span: bytes, record: dict):
    from PIL import Image
    decoded = pinned(span, record)
    chunk = decode(span)[0]
    texture = tx.parse_texture(decoded, chunk)
    return Image.frombytes("RGBA", (texture.width, texture.height), tx.texture_to_rgba(decoded, chunk, texture))


def atlas(inputs: dict[str, bytes]):
    """Rasterize the design roles into 64x64, sampling literal retail brand art.

    The original SVG badges are placeholders. ESPN comes from outer 346/31 espn1,
    NFL from 346/32 nflShield1. No font approximation of either mark is used.
    """
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (64, 64))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, 63, 15), 2, fill=(19, 20, 25, 255), outline=(122, 124, 132, 255))
    d.line((3, 1, 60, 1), fill=(190, 190, 196, 255))
    for x in range(64):
        value = round(75 * (1 - x / 63) + 17 * x / 63)
        d.line((x, 16, x, 31), fill=(value, value, value + 5, 255))
    # Decorative until timeout state is bound. Never described as a live counter.
    for x in (48, 53, 58):
        d.line((x, 30, x + 2, 30), fill=(230, 230, 232, 255))
    d.rounded_rectangle((0, 32, 63, 39), 2, fill=(208, 2, 27, 255), outline=(239, 47, 69, 255))
    d.rounded_rectangle((0, 40, 63, 47), 3, fill=(248, 248, 248, 255), outline=(143, 143, 151, 255))
    # White glyph coverage is extracted from the red ESPN source, not its pill.
    espn = texture_image(inputs["espn1"], RESOURCES["espn1"])
    mask = Image.new("L", espn.size)
    mask.putdata([max(0, min(255, (min(g, b)-96)*255//159)) if r > 150 else 0 for r, g, b, a in espn.getdata()])
    bbox = mask.getbbox()
    if bbox is None:
        raise ScorebugError("literal ESPN source has no wordmark")
    mark = Image.new("RGBA", (46, 12), (255, 255, 255, 0))
    mark.putalpha(mask.crop(bbox).resize((46, 12), Image.Resampling.LANCZOS))
    # Dark backing protects white lettering against field lines.
    d.rounded_rectangle((0, 49, 63, 63), 2, fill=(10, 12, 16, 220))
    im.alpha_composite(mark, (1, 51))
    nfl = texture_image(inputs["nflShield1"], RESOURCES["nflShield1"])
    nfl.thumbnail((13, 15), Image.Resampling.LANCZOS)
    im.alpha_composite(nfl, (50, 49))
    return im


def encode_atlas(template: bytes, image) -> tuple[bytes, dict]:
    """Reuse the existing bounded P8 quantizer and exact VC-LZ filler."""
    import nfl_tset_png_import as palettes
    chunk, decoded, info = decode(template)
    def candidate(palette, levels):
        return decoded[:128] + tx.swizzle_2d(levels[0], 64, 64, 1) + palettes.palette_bytes(palette)
    attempts = []
    for maximum in (256, 128, 96, 64, 48, 32, 16):
        palette, levels, _ = palettes.quantize_levels([palettes.MipLevel(0, 64, 64, image.tobytes())], maximum)
        rebuilt = candidate(palette, levels)
        for encoder in ("greedy", "optimal"):
            try:
                result, receipt = fill.rebuild_fixed_span_filled(template, rebuilt, encoder=encoder)
            except tx.TxtrError as exc:
                if "cannot keep the retail scratch" not in str(exc) and "more than" not in str(exc) and "exceed" not in str(exc):
                    raise
                attempts.append({"colors": len(palette), "encoder":encoder, "refused":str(exc)})
                continue
            break
        else:
            continue
        attempts.append({"colors":len(palette),"encoder":encoder,"result":"fit"})
        break
    else:
        raise ScorebugError("atlas cannot fit the retail wrapper at usable color depth")
    if result[:32] != template[:32] or len(result) != len(template) or decode(result)[1] != rebuilt:
        raise ScorebugError("atlas fixed-span round trip failed")
    return result, {"palette_attempts": attempts, "filled_bytes": receipt.filled_bytes,
                    "wrapper_identical": receipt.wrapper_identical}


def uv(region, x, y):
    a, b, c, d = REGIONS[region]
    return ((a + .5 + x * (c - a - 1)) / 32 - 1, (b + .5 + y * (d - b - 1)) / 32 - 1)


def mesh(retail: bytes):
    m = layout.Mesh(retail)
    original = [p[:] for p in m.pos]
    layout.legacy_espn_layout(m)
    for v, (x, y, z) in enumerate(original):
        ti, mat = m.group(v)
        if mat in ("yscore_buga", "yscore_buga1"):
            nx = m.pos[v][0]
            ny = layout._lin(m.pos[v][1], layout.ROW_BOTTOM, layout.ROW_TOP, -5, 43)
            m.pos[v] = [nx, ny, z]
            m.uv_edit[v] = uv("frame", (nx + 240) / 480, (43 - ny) / 48)
        elif ti in (23, 26):
            side = "away" if ti == 23 else "home"
            x0, y0, x1, y1 = PANELS[side]
            left, right = -32.733, 2.367
            bottom, top = (-4.449, 16.14) if ti == 23 else (-26.052, -6.126)
            u = min(1, max(0, (x - left) / (right - left)))
            vv = min(1, max(0, (top - y) / (top - bottom)))
            m.pos[v] = [x0 + u * (x1 - x0), y1 - vv * (y1 - y0), z]
            m.uv_edit[v] = uv("panel", u if side == "away" else 1 - u, vv)
        elif ti in (11, 15):
            box = PILL if ti == 11 else STRIP
            group = [p for i, p in enumerate(original) if m.tindex[i] == ti]
            xs, ys = [p[0] for p in group], [p[1] for p in group]
            u, vv = (x - min(xs)) / (max(xs) - min(xs)), (max(ys) - y) / (max(ys) - min(ys))
            m.pos[v] = [box[0] + u * (box[2] - box[0]), box[3] - vv * (box[3] - box[1]), -3]
            m.uv_edit[v] = uv("down" if ti == 11 else "strip", u, vv)
        elif mat.startswith("zz_ESPN_bug"):
            # Two independent triangles in each layer; both direction modes need a copy.
            corners = ((0, 1), (0, 0), (1, 0), (0, 1), (1, 0), (1, 1))
            u, vv = corners[(v - 262) % 6]
            a, b, c, d = WATERMARK
            m.pos[v] = [a + u * (c - a), d - vv * (d - b), -64]
            m.uv_edit[v] = uv("mark", u, vv)
            if (v - 262) % 12 < 6:  # collapse the duplicate shadow; backing lives in the atlas
                m.pos[v] = [a, d, -63.5]
        elif ti in (13, 17, 19, 21):
            m.pos[v] = [-300, -150, z]
    for name, xyz in ANCHORS.items():
        i = layout.T[name]
        leaf = layout.T.get(name + "_l")
        delta = [b-a for a,b in zip(m.world[i], m.world[leaf])] if leaf is not None else None
        m.world[i] = list(xyz)
        if leaf is not None:
            m.world[leaf] = [a+b for a,b in zip(xyz, delta)]
    return m


def serialize(m) -> bytes:
    # The top-right mark needs a wider quantization interval than the old bar.
    # Repack the existing position/UV streams and transform fields directly,
    # without changing the legacy writer's global quantization constants.
    buf = bytearray(m.buf)
    scale, offset = 420.0, (-20.0, 100.0, -29.5)
    struct.pack_into("<f", buf, layout.SHAPE + 0x10, scale)
    struct.pack_into("<3f", buf, layout.SHAPE + 0x20, *offset)
    for v, p in enumerate(m.pos):
        q = [round((c-o) / scale * 32767) for c,o in zip(p, offset)]
        if any(abs(n) > 32767 for n in q):
            raise ScorebugError("reference vertex exceeds quantization range")
        struct.pack_into("<3h", buf, layout.S0 + v*6, *q)
    for v, pair in m.uv_edit.items():
        struct.pack_into("<2h", buf, layout.S1 + v*10 + 4, *(round(c*32767) for c in pair))
    for i,w in enumerate(m.world):
        parent = m.parent[i]
        local = w if parent < 0 else [a-b for a,b in zip(w,m.world[parent])]
        struct.pack_into("<3f", buf, layout.TBASE+i*0x70+0x40, *w)
        struct.pack_into("<3f", buf, layout.TBASE+i*0x70+0x50, *local)
    return bytes(buf)


def status(payload: bytes, resource: str) -> str:
    if resource not in ("score_bug", "score_buga"):
        raise ScorebugError("unsupported writable scorebug resource")
    if digest(payload) == RESOURCES[resource]["span_sha256"]:
        return "retail"
    if digest(payload) == PATCHED_SHA256.get(resource):
        return "applied"
    return "foreign"


def apply(payload: bytes, resource: str, *, inputs: dict[str, bytes] | None = None) -> tuple[bytes, dict]:
    before = status(payload, resource)
    if before == "foreign":
        raise ScorebugError(f"{resource}: foreign edits")
    detail = {}
    result = payload
    if before == "retail":
        decoded = pinned(payload, RESOURCES[resource])
        if resource == "score_bug":
            result, info = layout.refit(payload, serialize(mesh(decoded)))
            detail["filled_bytes"] = info.filled_bytes
        else:
            result, detail = encode_atlas(payload, atlas(inputs or {}))
        if PATCHED_SHA256 and digest(result) != PATCHED_SHA256[resource]:
            raise ScorebugError(f"{resource}: generated bytes differ from the pinned build")
    return result, {"resource": resource, "state_before": before, "span_size": len(result),
                    "sha256_before": digest(payload), "sha256_after": digest(result),
                    "wrapper_identical": result[:32] == payload[:32], **detail}


def xbe_specs():
    """Pinned existing allocation and in-place fields only. No new cave or state."""
    sp = layout.sbpos
    specs = [(sp.X_SLOT, sp.RETAIL_SLOTS, struct.pack("<ff", *ROOT), "reserved position floats")]
    for va, target in sp.X_SITES:
        specs.append((va, b"\xd8\x05" + struct.pack("<I", target), b"\xd8\x05" + struct.pack("<I", sp.X_SLOT), "root x"))
    specs.append((sp.Y_SITES[0], sp.RETAIL_Y, b"\xd8\x05" + struct.pack("<I", sp.Y_SLOT), "root y"))
    for va, retail in layout.PERSIST_SITES.items():
        specs.append((va, retail, b"\x90"*5, "persistent bug"))
    colors = {0xA95894:(0xFFC0C0C0,0xFFFFFFFF), 0xA958BC:(0xFFC0C0C0,0xFFFFFFFF),
              0xA95958:(0xFF000000,0xFFFFFFFF), 0xA95990:(0xFF000000,0xFFFFFFFF),
              0xA959D8:(0xFF000000,0xFFFFFFFF), 0xA95A48:(0xFFC0C0C0,0xFF111118),
              0xA9590C:(0xFFC0C0C0,0xFF111118), 0xA95910:(0xFFC0C0C0,0xFF111118),
              0xA95934:(0xFFC0C0C0,0xFF111118), 0xA95938:(0xFFC0C0C0,0xFF111118)}
    for va,(old,new) in colors.items():
        specs.append((va,struct.pack("<I",old),struct.pack("<I",new),"text contrast"))
    for i,name in enumerate(layout.ELEMENT_NAMES):
        # The down pill slides six HUD units as its native visibility ramp runs.
        direction = (.2,0.,0.) if i == 0 else (0.,0.,0.)
        specs.append((layout.ELEMENT_RECORDS+i*0x70+0x18,layout.RETAIL_ELEMENT_DIR,struct.pack("<3f",*direction),name+" direction"))
    specs.append((0xA959F0,struct.pack("<f",.5),struct.pack("<f",.2),"down slide duration"))
    # Both mark materials use our frame atlas. Replay/presentation shield_espn stays retail.
    for va in (0xA95CAC,0xA95CB4):
        specs.append((va,struct.pack("<I",0xE6C768),struct.pack("<I",0xE6C6E8),"literal corner mark atlas"))
    return specs


def xbe_status(payload: bytes) -> str:
    try:
        for va,size,sha,label in XBE_GUARDS:
            off = layout.sbpos.va_to_off(payload,va)
            if digest(payload[off:off+size]) != sha:
                return "foreign"
        states = set()
        for va,old,new,_ in xbe_specs():
            off = layout.sbpos.va_to_off(payload,va)
            have = payload[off:off+len(old)]
            states.add("retail" if have == old else "applied" if have == new else "foreign")
        return states.pop() if len(states) == 1 else "foreign"
    except (ValueError, struct.error, SystemExit):
        return "foreign"


def apply_xbe(payload: bytes) -> tuple[bytes, dict]:
    before = xbe_status(payload)
    if before == "foreign":
        raise ScorebugError("scorebug XBE fields are mixed or foreign")
    from . import nfl2k5_hud_layout as hud, nfl2k5_boot_logo as boot
    # The neighbours are shared owners; their recognized patched state composes.
    hs = hud.status(payload)
    if hs["kick_meter_margin"] not in ("retail",str(hud.DEFAULT_KICK_MARGIN)) or hs["lineup_insert"] not in ("retail","off"):
        raise ScorebugError("HUD neighbours are foreign")
    result, hr = payload, {"already_applied":True}
    if "retail" in hs.values():
        result, hr = hud.apply(payload, kick_margin=hud.DEFAULT_KICK_MARGIN if hs["kick_meter_margin"] == "retail" else None,
                              lineup_insert_off=hs["lineup_insert"] == "retail")
    buf = bytearray(result)
    edits, touched = [], set()
    sections = bs._sections(payload)
    for va,old,new,label in xbe_specs():
        off = layout.sbpos.va_to_off(payload,va)
        if before == "retail":
            buf[off:off+len(new)] = new
            if va >= 0x11000:
                touched.add(bs._section_for_offset(sections,off).index)
        edits.append({"va":hex(va),"size":len(new),"label":label,"before":payload[off:off+len(old)].hex(),"after":new.hex()})
    for section in sections:
        if section.index in touched:
            off = section.header_offset+36
            buf[off:off+20] = bs.section_digest(bytes(buf),section)
    result, br = boot.apply(bytes(buf))
    return result, {"state_before":before,"edits":edits,"hud_layout":dict(hr),"boot_logo":dict(br),
                    "sha256_before":digest(payload),"sha256_after":digest(result)}


def animation_catalogue(payload: bytes) -> dict:
    """Read actual file-backed driver parameters; no runtime witness is implied."""
    if xbe_status(payload) == "foreign":
        raise ScorebugError("animation driver is foreign")
    def read(va,fmt):
        return struct.unpack_from(fmt,payload,layout.sbpos.va_to_off(payload,va))
    records=[]
    for i,name in enumerate(layout.ELEMENT_NAMES):
        va=layout.ELEMENT_RECORDS+i*0x70
        records.append({"name":name,"record_va":hex(va),"callback_va":hex(read(va+4,"<I")[0]),
                        "direction":read(va+0x18,"<3f"),"duration_seconds":read(va+0x28,"<f")[0],
                        "closed_position":read(va+0x2c,"<f")[0],"open_position":read(va+0x30,"<f")[0],
                        "root_shift":read(va+0x34,"<I")[0],"text_color":hex(read(va+0x10,"<I")[0])})
    return {"evidence":"PROVED file data and pinned native code; UNWITNESSED in game",
            "elements":records,"score_phase_rate":read(0x4f6964,"<f")[0],
            "score_phase_words":["0xa95978","0xa959b0"],"score_rotation_code":["0xfd2f0","0xfd416"],
            "score_flash_color":False,"down_refresh_each_new_down":False,"timeout_dimming":False,
            "under_5_color":False,"drop_yellow_label":"FLAG","drop_red_label":"FUMBLE"}


def image_plan(fd: int, size: int):
    from . import nfl2k5_throw_tuning as tt
    base, length = layout.xc.pack_extent(fd,size,"0")
    if length != PACK_SIZE:
        raise ScorebugError("pack 0 size changed")
    current = {n:layout._pread(fd,r["span_size"],base+r["pack_offset"]) for n,r in RESOURCES.items() if n != "shield_espn"}
    xoff,xlen = tt.image_xbe_extent(fd,size)
    xbe = layout._pread(fd,xlen,xoff)
    states = [status(current[n],n) for n in ("score_bug","score_buga")] + [xbe_status(xbe)]
    if "foreign" in states or len(set(states)) != 1:
        raise ScorebugError("scorebug resources are mixed or foreign")
    new_xbe, xr = apply_xbe(xbe)
    jobs, receipts = [(xoff,xbe,new_xbe)], []
    for n in ("score_bug","score_buga"):
        new,rec = apply(current[n],n,inputs=current)
        absolute = base+RESOURCES[n]["pack_offset"]
        jobs.append((absolute,current[n],new))
        receipts.append({"absolute":absolute,**rec})
    return jobs, {"layout":VERSION,"experimental":True,"witnessed":False,"state_before":states[0],
                  "root":list(ROOT),"textures":["score_buga"],"resources":receipts,"xbe":xr,
                  "wrapper_identical":all(r["wrapper_identical"] for r in receipts),
                  "runtime_team_logos":False,"timeout_dimming":False,"under_5_color":False,
                  "animation":"retail score rotation and visibility-triggered down slide"}


def image_status(path: Path) -> str:
    try:
        with Path(path).open("rb") as stream:
            _,receipt = image_plan(stream.fileno(),os.fstat(stream.fileno()).st_size)
        return receipt["state_before"]
    except (OSError,ValueError,struct.error,SystemExit,KeyError):
        return "foreign"


def apply_in_place(path: Path) -> dict:
    """For the build's output copy. Preflight every span, then write/read back.

    The journal remains in memory until readback succeeds; an I/O exception attempts
    restoration of every touched span. A process crash is outside this guarantee.
    """
    with Path(path).open("r+b") as stream:
        fd = stream.fileno()
        jobs,receipt = image_plan(fd,os.fstat(fd).st_size)
        touched = []
        try:
            for off,before,after in jobs:
                if layout._pread(fd,len(before),off) != before:
                    raise ScorebugError("image changed after scorebug preflight")
            for off,before,after in jobs:
                if before == after:
                    continue
                touched.append((off,before))
                stream.seek(off)
                if stream.write(after) != len(after):
                    raise ScorebugError("short scorebug write")
                stream.flush()
                if layout._pread(fd,len(after),off) != after:
                    raise ScorebugError("scorebug readback failed")
            os.fsync(fd)
        except BaseException:
            for off,before in reversed(touched):
                stream.seek(off)
                if stream.write(before) != len(before):
                    raise ScorebugError("scorebug rollback write failed")
            stream.flush()
            os.fsync(fd)
            raise
    return receipt


def stage_team_panel(span: bytes, team: str, *, side: str = "away") -> tuple[bytes, dict]:
    """Data for a future per-team material, 128x32 RGBA8, not installed globally.

    Artwork occupies the outer third and a primary-to-black gradient protects scores.
    Mirroring panel UVs is insufficient for text/logos; provide distinct home/away
    material instances in the future hook. The right panel mirrors the background only.
    """
    from PIL import Image, ImageDraw
    if side not in ("away","home"):
        raise ScorebugError("panel side must be away or home")
    r = TEAM_LOGOS[team]
    logo = texture_image(span, r)
    im = Image.new("RGBA", (128, 32))
    d = ImageDraw.Draw(im)
    primary = tuple(bytes.fromhex(r["primary"][1:]))
    for x in range(128):
        t = min(1, (x if side == "away" else 127-x)/88)
        color = tuple(round(c*(1-t)+16*t) for c in primary)+(255,)
        d.line((x,0,x,31), fill=color)
    logo.thumbnail((38,30),Image.Resampling.LANCZOS)
    im.alpha_composite(logo,((2 if side == "away" else 88)+(38-logo.width)//2,(32-logo.height)//2))
    for x in (103,112,121):
        dx=x if side=="away" else 127-x
        d.line((dx,30,dx+4,30),fill=(230,230,232,255))
    data = im.tobytes()
    return data, {"schema":"nfl2k5_scorebug_team_panel/v1","team":team,"side":side,"source":r,
                  "width":128,"height":32,"format":"RGBA8","sha256":digest(data),
                  "runtime_bound":False,"experimental":True,"witnessed":False}


def stage_binding_scene(span: bytes) -> tuple[bytes, dict]:
    """Fixed-span scene data for the specified future binding hook, never auto-installed.

    zscore_buga becomes away-only. The unused hscore_buga material becomes the
    home panel, on root matrix 0. A hook must disable element record 2's material
    visibility updates, bind two texture objects and clear the material hide bits.
    These contracts are deliberately absent from the neutral fallback installer.
    """
    retail=pinned(span,RESOURCES["score_bug"])
    original=layout.Mesh(retail)
    m=mesh(retail)
    home=[original.pos[v] for v in range(80,96)]
    xmin,xmax=min(p[0] for p in home),max(p[0] for p in home)
    ymin,ymax=min(p[1] for p in home),max(p[1] for p in home)
    for v in range(layout.VCOUNT):
        if m.tindex[v] == 26:
            m.pos[v]=[-300,-150,-61]
        if m.tindex[v] == 23:
            x,y,z=m.pos[v];a,b,c,d=PANELS["away"]
            m.uv_edit[v]=(-1+2*(x-a)/(c-a),-1+2*(d-y)/(d-b))
            struct.pack_into("<I",m.buf,layout.S1+v*10,0xffffffff)
        if 80 <= v < 96:
            x,y,z=original.pos[v];u=(x-xmin)/(xmax-xmin);vv=(ymax-y)/(ymax-ymin)
            a,b,c,d=PANELS["home"]
            m.pos[v]=[a+u*(c-a),d-vv*(d-b),-61]
            m.uv_edit[v]=(-1+2*u,-1+2*vv)
            struct.pack_into("<I",m.buf,layout.S1+v*10,0xffffffff)
            struct.pack_into("<h",m.buf,layout.S1+v*10+8,0)
    result,info=layout.refit(span,serialize(m))
    return result,{"schema":"nfl2k5_scorebug_binding_scene/v1","runtime_bound":False,
                   "requires_hook":True,"sha256":digest(result),"wrapper_identical":info.wrapper_identical,
                   "filled_bytes":info.filled_bytes,"away_material":"zscore_buga","home_material":"hscore_buga",
                   "disable_element":2,"experimental":True,"witnessed":False}


def preview_data(source: Path):
    with Path(source).open("rb") as stream:
        fd=stream.fileno()
        base,size=layout.xc.pack_extent(fd,os.fstat(fd).st_size,"0")
        if size != PACK_SIZE:
            raise ScorebugError("pack 0 size changed")
        spans={n:layout._pread(fd,r["span_size"],base+r["pack_offset"]) for n,r in RESOURCES.items()}
    # Preview requires the retail scene to construct transformed positions.
    m=mesh(pinned(spans["score_bug"],RESOURCES["score_bug"]))
    replacement,_=apply(spans["score_buga"],"score_buga",inputs=spans)
    chunk,decoded,_=decode(replacement)
    from PIL import Image
    tex=tx.parse_texture(decoded,chunk)
    image=Image.frombytes("RGBA",(64,64),tx.texture_to_rgba(decoded,chunk,tex))
    return m,image
