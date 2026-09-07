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

VERSION = "espn-reference-v9"
PACK_SIZE = 193710080
# FUN_00066670 insets a 720x480 framebuffer by (40,16). The reference
# describes the active 640-column image. Its intended root y=424 therefore
# requires 408 in the scene, before the native +16 viewport translation.
HUD_INSET = (40.0, 16.0)
HUD_SIZE = (640.0, 448.0)
ROOT = (320.0, 424.0 - HUD_INSET[1])
V8_PANELS = {"away": (-236.0, -3.0, -86.0, 41.0), "home": (86.0, -3.0, 236.0, 41.0)}
V8_PILL = (-75.0, 23.0, 69.0, 41.0)
V8_STRIP = (-79.0, -3.0, 79.0, 18.0)
V8_WATERMARK = (188.0, 367.0, 284.0, 391.0)
REGIONS = {"frame": (0, 0, 64, 16), "panel": (0, 16, 64, 32),
           "down": (0, 32, 64, 40), "strip": (0, 40, 64, 48), "mark": (0, 48, 64, 64)}
V8_ANCHORS = {"away_city": (-218, 14, -64), "home_city": (127, 14, -64),
           "away_score": (-101, 10, -59), "home_score": (101, 10, -59),
           "quarter": (-57, 2, -4), "clock_a": (31, 2, -4), "clock_b": (31, 2, -4),
           "drop_down": (-3, 27, -4), "drop_clock": (61, 2, -4)}

# Active 640-column coordinates are (320+x, 424-y). One 476x48 frame;
# the right cell has two text baselines to fit native font1's longest down.
# Text object +30/+34 are shadow offsets, NOT glyph scale.
FRAME = (-236.0, -5.0, 240.0, 43.0)
PANELS = {"away": (-132.0, -3.0, -34.0, 41.0), "home": (-34.0, -3.0, 64.0, 41.0)}
STRIP = (66.0, -3.0, 236.0, 41.0)
PILL = (150.0, 0.0, 150.0, 0.0)  # no separate tab geometry
WATERMARK = (-232.0, 7.0, -136.0, 31.0)  # 96x24 reference art, left cell
FRAME_COLOR = (19, 20, 25, 255)  # literal neutral frame fill in target_NO_MIA
ANCHORS = {"away_city": (-130, 10, -64), "home_city": (-32, 10, -64),
           "away_score": (-52, 10, -59), "home_score": (46, 10, -59),
           "quarter": (84, 20, -4), "clock_a": (180, 20, -4), "clock_b": (180, 20, -4),
           "drop_down": (150, 0, -4), "drop_clock": (214, 20, -4),
           "drop_yellow": (150, 0, -4), "drop_red": (150, 0, -4),
           "drop_ball_on": (110, 20, -4), "drop_hangtime": (150, 0, -4)}
# Static zscore_buga shares one texture for both parents. Future runtime
# selection must split it using the existing staging contract, never bake a team.
TEAM_MATERIAL_HOOK = {"static_material": "zscore_buga", "away_parent": "away_score1",
                      "home_parent": "home_score1", "away_parent_index": 23, "home_parent_index": 26,
                      "future_away_material": "zscore_buga",
                      "future_home_material": "hscore_buga", "runtime_bound": False}


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


def atlas_v8(inputs: dict[str, bytes]):
    """Rasterize the design roles into 64x64, sampling literal retail brand art.

    The original SVG badges are placeholders. ESPN comes from outer 346/31 espn1,
    NFL from 346/32 nflShield1. No font approximation of either mark is used.
    """
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (64, 64))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, 63, 15), 2, fill=(12, 13, 17, 255), outline=(74, 76, 84, 255))
    d.line((3, 1, 60, 1), fill=(152, 154, 162, 255))
    for x in range(64):
        value = round(75 * (1 - x / 63) + 17 * x / 63)
        d.line((x, 16, x, 31), fill=(value, value, value + 5, 255))
    # A distinct dark score cell on the inner side of each mirrored panel.
    d.rectangle((43, 16, 63, 31), fill=(10, 11, 15, 255))
    d.line((43, 17, 43, 29), fill=(91, 93, 100, 255))
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


def atlas(inputs: dict[str, bytes]):
    """Neutral v9 atlas; retain the disc-derived ESPN art at reference size.

    The source-art resolver supplies pinned espn1/nflShield1 from the user's
    disc. Only the existing mark region is retained; no invented glyph artwork.
    """
    from PIL import ImageDraw
    im = atlas_v8(inputs)
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, 63, 47), fill=FRAME_COLOR)
    draw.line((0, 0, 63, 0), fill=(122, 124, 132, 255))
    draw.line((0, 15, 63, 15), fill=(74, 76, 84, 255))
    # Panel, former tab and clock regions are all the reference dark block.
    # In particular row 30 columns 48/53/58 contain no timeout decoration.
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


def mesh_v8(retail: bytes, *, baseline_v7: bool = False):
    # Retain the historical before images and independently pinned runtime scene.
    panels, pill, strip, anchors = V8_PANELS, V8_PILL, V8_STRIP, V8_ANCHORS
    if baseline_v7:
        panels = {"away": (-236,-3,-66,41), "home": (66,-3,236,41)}
        pill, strip = (-59,23,53,41), (-59,-3,59,18)
        anchors = {**V8_ANCHORS, "away_score": (-91,10,-59), "home_score": (91,10,-59),
                   "quarter": (-42,2,-4), "clock_a": (26,2,-4), "clock_b": (26,2,-4),
                   "drop_clock": (44,2,-4)}
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
            x0, y0, x1, y1 = panels[side]
            left, right = -32.733, 2.367
            bottom, top = (-4.449, 16.14) if ti == 23 else (-26.052, -6.126)
            u = min(1, max(0, (x - left) / (right - left)))
            vv = min(1, max(0, (top - y) / (top - bottom)))
            m.pos[v] = [x0 + u * (x1 - x0), y1 - vv * (y1 - y0), z]
            m.uv_edit[v] = uv("panel", u if side == "away" else 1 - u, vv)
        elif ti in (11, 15):
            box = pill if ti == 11 else strip
            group = [p for i, p in enumerate(original) if m.tindex[i] == ti]
            xs, ys = [p[0] for p in group], [p[1] for p in group]
            u, vv = (x - min(xs)) / (max(xs) - min(xs)), (max(ys) - y) / (max(ys) - min(ys))
            m.pos[v] = [box[0] + u * (box[2] - box[0]), box[3] - vv * (box[3] - box[1]), -3]
            m.uv_edit[v] = uv("down" if ti == 11 else "strip", u, vv)
        elif mat.startswith("zz_ESPN_bug"):
            # Two independent triangles in each layer; both direction modes need a copy.
            corners = ((0, 1), (0, 0), (1, 0), (0, 1), (1, 0), (1, 1))
            u, vv = corners[(v - 262) % 6]
            a, b, c, d = V8_WATERMARK
            m.pos[v] = [a + u * (c - a), d - vv * (d - b), -64]
            m.uv_edit[v] = uv("mark", u, vv)
            if (v - 262) % 12 < 6:  # collapse the duplicate shadow; backing lives in the atlas
                m.pos[v] = [a, d, -63.5]
        elif ti in (13, 17, 19, 21):
            m.pos[v] = [-300, -150, z]
    for name, xyz in anchors.items():
        i = layout.T[name]
        leaf = layout.T.get(name + "_l")
        delta = [b-a for a,b in zip(m.world[i], m.world[leaf])] if leaf is not None else None
        m.world[i] = list(xyz)
        if leaf is not None:
            m.world[leaf] = [a+b for a,b in zip(xyz, delta)]
    return m


def mesh(retail: bytes, *, baseline_v7: bool = False):
    if baseline_v7:
        return mesh_v8(retail, baseline_v7=True)
    m = mesh_v8(retail)
    # The native settled rotation reflects Y around these score parents.
    # Put the pivot at the actual panel centre (19), not v8's inherited 5.9.
    # Both score records remain enabled and FD2F0..FD416 is untouched.
    for side, parent in (("away", 23), ("home", 26)):
        box = PANELS[side]
        m.world[parent][0:2] = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
        old = V8_PANELS[side]
        for v in range(layout.VCOUNT):
            if m.tindex[v] == parent:
                x, y, z = m.pos[v]
                m.pos[v] = [layout._lin(x, old[0], old[2], box[0], box[2]), y, z]
                struct.pack_into("<I", m.buf, layout.S1 + v * 10, 0xffffffff)
    # Both frame command streams start with four distinct strip indices.
    # Use the same two triangles, collapse the rest, and retain the commands.
    corners = ((0, 1), (1, 1), (0, 0), (1, 0))
    for first, last in ((96, 165), (166, 229)):
        for v in range(first, last + 1):
            u, vv = corners[min(v - first, 3)]
            a, b, c, d = FRAME
            m.pos[v] = [a + u * (c - a), d - vv * (d - b), 0]
            m.uv_edit[v] = uv("frame", u, vv)
            struct.pack_into("<I", m.buf, layout.S1 + v * 10, 0xffffffff)
    for v in range(layout.VCOUNT):
        ti, material = m.group(v)
        if material == "cscore_buga":
            x, y, _ = m.pos[v]
            a, b, c, d = V8_STRIP
            m.pos[v] = [layout._lin(x, a, c, STRIP[0], STRIP[2]),
                        layout._lin(y, b, d, STRIP[1], STRIP[3]), -3]
            struct.pack_into("<I", m.buf, layout.S1 + v * 10, 0xffffffff)
        elif ti in (11, 13, 17, 19, 21):
            # Keep native text/visibility bindings; omit all detached tab art.
            m.pos[v] = [150, 0, -3]
        elif material.startswith("zz_ESPN_bug"):
            a, b, c, d = WATERMARK
            # Same effective winding as the frame, including strip parity.
            corners = ((0, 1), (1, 0), (0, 0), (0, 1), (1, 1), (1, 0))
            u, vv = corners[(v - 262) % 6]
            m.pos[v] = [a + u * (c - a), d - vv * (d - b), -64]
            m.uv_edit[v] = uv("mark", u, vv)
            if (v - 262) % 12 < 6:
                m.pos[v] = [a, d, -63.5]
    for name, xyz in ANCHORS.items():
        i, leaf = layout.T[name], layout.T[name + "_l"]
        delta = [b - a for a, b in zip(m.world[i], m.world[leaf])]
        m.world[i] = list(xyz)
        m.world[leaf] = [a + b for a, b in zip(xyz, delta)]
    return m


def serialize(m) -> bytes:
    # Retain the shared v8 quantization interval for reproducible historical and
    # runtime spans. V9 repacks only the existing streams and transform fields.
    buf = bytearray(m.buf)
    scale, offset = 420.0, (-20.0, 100.0, -29.5)
    struct.pack_into("<f", buf, layout.SHAPE + 0x10, scale)
    struct.pack_into("<3f", buf, layout.SHAPE + 0x20, *offset)
    for v, p in enumerate(m.pos):
        q = [round((c-o) / scale * (32768 if c < o else 32767)) for c,o in zip(p, offset)]
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
    return result, {"version": VERSION, "resource": resource, "state_before": before, "span_size": len(result),
                    "sha256_before": digest(payload), "sha256_after": digest(result),
                    "wrapper_identical": result[:32] == payload[:32], **detail}


def xbe_specs(*, baseline_v8: bool = False):
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
    if not baseline_v8:
        colors = {va: (old, 0xffffffff) for va, (old, _) in colors.items()}
        colors.update({0xA958E4: (0xff000000, 0xffffffff), 0xA958E8: (0xff000000, 0xffffffff),
                       0xA95AB8: (0xff000000, 0xffffffff), 0xA95B28: (0xff000000, 0xffffffff),
                       0xA95B98: (0xffc0c0c0, 0xffffffff), 0xA95C08: (0xffc0c0c0, 0xffffffff)})
    for va,(old,new) in colors.items():
        specs.append((va,struct.pack("<I",old),struct.pack("<I",new),"text contrast"))
    for i,name in enumerate(layout.ELEMENT_NAMES):
        # v9 retains native formatting/visibility but has no detached sliding tab.
        direction = (.2,0.,0.) if baseline_v8 and i == 0 else (0.,0.,0.)
        specs.append((layout.ELEMENT_RECORDS+i*0x70+0x18,layout.RETAIL_ELEMENT_DIR,struct.pack("<3f",*direction),name+" direction"))
    specs.append((0xA959F0,struct.pack("<f",.5),struct.pack("<f",.2),"down slide duration"))
    # Both mark materials use our frame atlas. Replay/presentation shield_espn stays retail.
    for va in (0xA95CAC,0xA95CB4):
        specs.append((va,struct.pack("<I",0xE6C768),struct.pack("<I",0xE6C6E8),"literal ESPN mark atlas"))
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
    return result, {"version":VERSION,"state_before":before,"edits":edits,"hud_layout":dict(hr),"boot_logo":dict(br),
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
                  "team_material_hook":dict(TEAM_MATERIAL_HOOK),
                  "animation":"retail score rotation and native text visibility; no detached tab"}


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


def stage_binding_scene(span: bytes, *, runtime: bool = False) -> tuple[bytes, dict]:
    """Fixed-span scene data for the specified future binding hook, never auto-installed.

    zscore_buga becomes away-only. The unused hscore_buga material becomes the
    home panel, on root matrix 0. A hook must disable element record 2's material
    visibility updates, bind two texture objects and clear the material hide bits.
    These contracts are deliberately absent from the neutral fallback installer.
    """
    retail=pinned(span,RESOURCES["score_bug"])
    original=layout.Mesh(retail)
    # Preserve the independently pinned runtime collection. Static v9 does not
    # migrate the runtime scene or claim that its entry freeze is repaired.
    m=mesh_v8(retail)
    home=[original.pos[v] for v in range(80,96)]
    xmin,xmax=min(p[0] for p in home),max(p[0] for p in home)
    ymin,ymax=min(p[1] for p in home),max(p[1] for p in home)
    for v in range(layout.VCOUNT):
        if m.tindex[v] == 26:
            m.pos[v]=[-300,-150,-61]
        if m.tindex[v] == 23:
            x,y,z=m.pos[v];a,b,c,d=V8_PANELS["away"]
            m.uv_edit[v]=(-1+2*(x-a)/(c-a),-1+2*(d-y)/(d-b))
            struct.pack_into("<I",m.buf,layout.S1+v*10,0xffffffff)
        if 80 <= v < 96:
            x,y,z=original.pos[v];u=(x-xmin)/(xmax-xmin);vv=(ymax-y)/(ymax-ymin)
            a,b,c,d=V8_PANELS["home"]
            m.pos[v]=[a+u*(c-a),d-vv*(d-b),-61]
            m.uv_edit[v]=(-1+2*u,-1+2*vv)
            struct.pack_into("<I",m.buf,layout.S1+v*10,0xffffffff)
            struct.pack_into("<h",m.buf,layout.S1+v*10+8,0)
    if runtime:
        # Keep the native away abbreviation clear of the real logo's outer third.
        for name in ("away_city", "away_city_l"):
            m.world[layout.T[name]][0] += 43
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
    replacement_scene,_=apply(spans["score_bug"],"score_bug")
    m=layout.Mesh(decode(replacement_scene)[1], static=True)
    replacement,_=apply(spans["score_buga"],"score_buga",inputs=spans)
    chunk,decoded,_=decode(replacement)
    from PIL import Image
    tex=tx.parse_texture(decoded,chunk)
    image=Image.frombytes("RGBA",(64,64),tx.texture_to_rgba(decoded,chunk,tex))
    return m,image


def runtime_image_plan(fd: int, *, with_kickoff: bool = False, extra_requests=(), probe="full"):
    """Preflight both files before any write; use the generalized extent reader."""
    from . import nfl2k5_scorebug_runtime as runtime, nfl2k5_scorebug_resources as resources
    from . import nfl2k5_xbe_space as space, nfl2k5_dynamic_kickoff_relocated as kickoff
    from . import platform_compat as io
    entries, _ = layout.xc.parse_xdvdfs(fd, os.fstat(fd).st_size)
    pack_entry, xbe_entry = entries.get("vc_53450030/0"), entries.get("default.xbe")
    if pack_entry is None or xbe_entry is None:
        raise ScorebugError("missing scorebug disc files")
    _, _, growth = resources.probe_sizes(probe)
    hooks = resources.probe_has_hooks(probe)
    if pack_entry.size not in (PACK_SIZE, PACK_SIZE + growth) or xbe_entry.size not in (
            space.special.RETAIL_FILE_SIZE, space.special.FILE_SIZE, *space.accepted_file_sizes()):
        raise ScorebugError("unknown scorebug disc extents")
    pack = resources.PackView.from_fd(fd, pack_entry.byte_offset, pack_entry.size)
    xbe = io.pread(fd, xbe_entry.size, xbe_entry.byte_offset)
    xs = runtime.status(xbe) if hooks else xbe_status(xbe)
    if not hooks and runtime.status(xbe) != "retail":
        xs = "foreign"
    states = (resources.runtime_pack_status(pack, probe=probe), xs)
    if "foreign" in states or len(set(states)) != 1:
        raise ScorebugError("runtime scorebug files are mixed or foreign; rebuild from base")
    requests = (runtime.REQUESTS if hooks else ()) + (kickoff.REQUESTS if with_kickoff else ()) + tuple(extra_requests)
    prepared = space.apply(xbe, requests)[0] if requests else xbe
    if with_kickoff:
        prepared, _ = kickoff.apply(prepared)
    new_xbe, xr = runtime.apply(prepared) if hooks else apply_xbe(prepared)
    new_pack, pr = resources.compile_runtime_collection(pack, probe=probe)
    return ((pack_entry, pack, new_pack), (xbe_entry, xbe, new_xbe)), dict(
        version=resources.RUNTIME_VERSION, status=states[0], experimental=True,
        probe=probe, hooks_installed=hooks, runtime_witnessed=False,
        runtime_team_logos=hooks and probe in ("full", "pair"), timeout_dimming=hooks and probe != "hooks",
        score_flash=hooks, down_refresh=hooks, under_5_color=hooks, resources=pr, xbe=xr)


def runtime_image_status(path, *, probe="full"):
    """Recognize the complete owned HUD and XBE, resolving current archive offsets."""
    from . import nfl2k5_scorebug_runtime as runtime, nfl2k5_scorebug_resources as resources
    from . import nfl2k5_xbe_space as space, platform_compat as io
    try:
        with Path(path).open("rb") as stream:
            fd = stream.fileno()
            entries, _ = layout.xc.parse_xdvdfs(fd, os.fstat(fd).st_size)
            p, x = entries["vc_53450030/0"], entries["default.xbe"]
            if x.size not in (space.special.RETAIL_FILE_SIZE, space.special.FILE_SIZE,
                              *space.accepted_file_sizes()):
                return "foreign"
            xbe = io.pread(fd, x.size, x.byte_offset)
            hooks = resources.probe_has_hooks(probe)
            xbe_state = runtime.status(xbe) if hooks else xbe_status(xbe)
            if not hooks and runtime.status(xbe) != "retail":
                return "foreign"
            resource_state = "foreign"
            if p.size in (PACK_SIZE, PACK_SIZE + resources.probe_sizes(probe)[2]):
                resource_state = resources.runtime_pack_status(resources.PackView.from_fd(fd, p.byte_offset, p.size), probe=probe)
        if resource_state == "foreign" and xbe_state == "applied" and probe == "full":
            # A later music transaction may move this entire owner. Resolve its
            # current outer range through the validated archive, then retain the
            # exact full HUD and appended-texture pins. No installation gate changes.
            from . import nfl2k5_music_archive as archive
            with archive.Disc(path) as disc:
                entry = disc.archive_entries[resources.HUD_OUTER_INDEX]
                if entry.name_id != 11965036 or entry.size != resources.HUD_SIZE + resources.RUNTIME_APPEND_SIZE:
                    return "foreign"
                hud = disc.read_entry_range(entry, 0, entry.size)
                if (digest(hud[:resources.HUD_SIZE]) == resources.RUNTIME_PINS["hud_after"]
                        and digest(hud[resources.HUD_SIZE:]) == resources.RUNTIME_PINS["appendix"]):
                    resource_state = "applied"
        return resource_state if resource_state == xbe_state else "foreign"
    except (OSError, ValueError, KeyError, IndexError, struct.error, SystemExit):
        return "foreign"


def runtime_apply_in_place(path, *, with_kickoff=False, extra_requests=(), probe="full"):
    """Transactional resource growth and allocator XBE transport on an output copy.

    Pack 0 is appended intact, then its existing XDVDFS node is switched. The
    generalized XBE writer owns its extent. Ordinary failures restore both
    nodes, any same-size XBE write, and the original image length. Power loss
    is outside this guarantee; apply_copy publishes only a closed verified copy.
    """
    from . import nfl2k5_depth_chart_storage as storage, platform_compat as io
    from . import nfl2k5_scorebug_resources as resources
    with Path(path).open("r+b") as stream:
        fd = stream.fileno()
        jobs, receipt = runtime_image_plan(fd, with_kickoff=with_kickoff, extra_requests=extra_requests, probe=probe)
        original_size = os.fstat(fd).st_size
        nodes = []
        for entry, before, _after in jobs:
            node, sector, length = storage.image_file_node(
                lambda count, offset: io.pread(fd, count, offset), entry.base_offset, original_size, entry.path)
            current = resources.PackView.from_fd(fd, entry.byte_offset, entry.size)
            expected = (receipt["resources"]["sha256_before"] if entry is jobs[0][0]
                        and "sha256_before" in receipt["resources"] else resources.pack_digest(before))
            if (sector, length) != (entry.sector, entry.size) or resources.pack_digest(current) != expected:
                raise ScorebugError("disc changed after runtime scorebug preflight")
            nodes.append((node, io.pread(fd, 8, node)))
        if jobs[0][1] is jobs[0][2] and jobs[1][1] == jobs[1][2]:
            return {**receipt, "status": "already_applied", "image_growth": 0}
        def write(data, at):
            if io.pwrite(fd, data, at) != len(data):
                raise ScorebugError("short runtime scorebug write")
        xbe_attempted = False
        try:
            entry, before, after = jobs[0]
            offset = entry.byte_offset
            if before is not after:
                offset = (original_size + 2047) & -2048
                if offset > original_size:
                    write(bytes(offset-original_size), original_size)
                cursor = offset
                for block in resources.pack_blocks(after):
                    write(block, cursor)
                    cursor += len(block)
                if resources.pack_digest(resources.PackView.from_fd(fd, offset, len(after))) != receipt["resources"]["sha256_after"]:
                    raise ScorebugError("runtime pack readback failed")
                write(struct.pack("<II", (offset-entry.base_offset)//2048, len(after)), nodes[0][0])
            xbe_attempted = True
            xbe_entry, old_xbe, new_xbe = jobs[1]
            if len(old_xbe) == len(new_xbe):
                # Resource/transport controls keep a retail-sized executable.
                # The generalized growth writer intentionally rejects that size.
                write(new_xbe, xbe_entry.byte_offset)
                if io.pread(fd, len(new_xbe), xbe_entry.byte_offset) != new_xbe:
                    raise ScorebugError("runtime XBE readback failed")
                xr = dict(status="applied", transport="existing extent", size=len(new_xbe),
                          byte_offset=xbe_entry.byte_offset, sha256=digest(new_xbe))
            else:
                xr = storage.write_image_xbe(fd, new_xbe)
            entries, _ = layout.xc.parse_xdvdfs(fd, os.fstat(fd).st_size)
            if entries["vc_53450030/0"].byte_offset != offset or entries["vc_53450030/0"].size != len(after):
                raise ScorebugError("runtime pack directory readback failed")
            os.fsync(fd)
        except Exception as exc:
            try:
                for node, before in reversed(nodes):
                    write(before, node)
                if xbe_attempted:
                    write(jobs[1][1], jobs[1][0].byte_offset)
                os.ftruncate(fd, original_size)
                os.fsync(fd)
                if any(io.pread(fd, len(before), node) != before for node, before in nodes):
                    raise ScorebugError("runtime rollback directory readback failed")
                if io.pread(fd, len(jobs[1][1]), jobs[1][0].byte_offset) != jobs[1][1]:
                    raise ScorebugError("runtime rollback XBE readback failed")
            except Exception as rollback:
                raise ScorebugError(f"{exc}; rollback failed: {rollback}; discard output copy") from exc
            raise
    return {**receipt, "status": "applied", "image_growth": Path(path).stat().st_size-original_size,
            "pack_offset": offset, "pack_size": len(jobs[0][2]), "xbe_transport": xr}
