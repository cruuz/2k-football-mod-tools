"""ESPN broadcast glyphs painted into the retail HUD fonts (FONT4 and FONT8).

The two retail fonts keep their names, metrics, glyph cells, advances and
spans; only the mask pixels inside the chosen glyph cells change, so every
HUD text that used those fonts keeps its layout and shows the broadcast
digit shapes. The glyph sources are masks sampled from a 2026 Monday Night
Football broadcast capture (data/nfl2k5_scorebug_mnf/espn_glyphs.png), not a
font file. EXPERIMENTAL / UNWITNESSED in game.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "nfl2k5_scorebug_mnf"
SHEET = DATA / "espn_glyphs.png"
SHEET_JSON = DATA / "espn_glyphs.json"
# outer 3 of pack 0 (sector 416): (chunk offset, stored bytes, atlas width, glyph height slack)
FONT_OUTER_SECTOR = 416
FONTS = {3: dict(name="font4", offset=32096, stored=7184, width=128, restyle="0123456789", levels=(0, 15)),
         7: dict(name="font8", offset=74336, stored=13280, width=256, restyle="0123456789", levels=(0, 5, 10, 15))}
# Applied masks are pinned so status() never needs the retail bytes; apply() refuses a drifted build.
APPLIED_DECODED_SHA256 = {3: 'fe44009fcbaaa9bd7482b2314173dab296149938a6eecb6816f9870ee742a71e', 7: '87adbb008e7039456ff21c6175e7d4f98f3bf99cfd7e7b885abc39b1c104ee78'}
MASK_LEVELS = 15  # the retail mask stores alpha as one 0..15 level per byte
DASH_CHAR = "~"   # repainted as a short thick dash for the timeout marks
PALETTE_TAIL = 1024
RETAIL_DECODED_SHA256 = {
    3: "60cc66a63ca3ae443b2c38e6ff7abaecfbfb484866433394be151106474afa7e",
    7: "b775bc02454ab2e39fd4b39f0ff400c4af14848b4fccc429861abc2faec4f15f",
}


class FontError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pack_offset(slot: int) -> int:
    return FONT_OUTER_SECTOR * 2048 + FONTS[slot]["offset"]


def span_size(slot: int) -> int:
    return 32 + FONTS[slot]["stored"]


def _glyph_sources():
    from PIL import Image
    meta = json.loads(SHEET_JSON.read_text(encoding="utf-8"))
    sheet = Image.open(SHEET).convert("L")
    out = {}
    for char, row in meta.items():
        x0, y0, x1, y1 = row["box"]
        out[char] = sheet.crop((x0, y0, x1, y1))
    return out


def _records(decoded: bytes):
    """Yield (codepoint, record offset) for every glyph record of the FONT object."""
    obj = 48
    count = struct.unpack_from("<I", decoded, obj + 4)[0]
    ranges = obj + 8 + struct.unpack_from("<I", decoded, obj + 8)[0] - 1
    for i in range(count):
        first, last, relative = struct.unpack_from("<HHI", decoded, ranges + 8 * i)
        glyphs = ranges + 8 * i + 4 + relative - 1
        for cp in range(first, last + 1):
            yield cp, glyphs + 96 * (cp - first)


def _cell(decoded: bytes, record: int, width: int):
    u0, v0, u1, v1 = struct.unpack_from("<4f", decoded, record + 80)
    return (round(u0 * width), round(v0 * width), round(u1 * width), round(v1 * width))



def _paint(decoded, slot, width, sources):
    from PIL import Image
    import numpy as np
    from . import nfl2k5_scorebug_ingame as r
    system_bytes = _system_bytes(decoded)
    video = decoded[system_bytes:]
    linear = bytearray(r.tx.unswizzle_2d(video[:width * width], width, width, 1))
    plane = np.frombuffer(bytes(linear), dtype=np.uint8).reshape(width, width).copy()
    cells = {chr(cp): _cell(decoded, rec, width) for cp, rec in _records(decoded)
             if chr(cp) in FONTS[slot]["restyle"]}
    painted = []
    for char, (x0, y0, x1, y1) in cells.items():
        cw, ch = x1 - x0, y1 - y0
        if cw <= 0 or ch <= 0:
            continue
        if char == DASH_CHAR:
            glyph = Image.new("L", (cw, ch), 0)
            bar_h = max(2, round(ch * 0.34))
            top = (ch - bar_h) // 2
            for y in range(top, top + bar_h):
                for x in range(max(0, cw // 8), cw - max(0, cw // 8)):
                    glyph.putpixel((x, y), 255)
        elif char == ":":
            glyph = Image.new("L", (cw, ch), 0)
            dot = max(1, round(min(cw, ch) * 0.28))
            for cy in (round(ch * 0.30), round(ch * 0.72)):
                for y in range(cy - dot // 2, cy - dot // 2 + dot):
                    for x in range((cw - dot) // 2, (cw - dot) // 2 + dot):
                        if 0 <= x < cw and 0 <= y < ch:
                            glyph.putpixel((x, y), 255)
        else:
            source = sources.get(char)
            if source is None:
                continue
            # Fit the sampled glyph inside the retail cell: match the cell height
            # (digits and capitals share the cap height), then centre horizontally.
            sw, sh = source.size
            scale = ch / sh
            new_w = max(1, round(sw * scale))
            if new_w > cw:
                scale = cw / sw
                new_w = cw
            new_h = max(1, round(sh * scale))
            fitted = source.resize((new_w, new_h), Image.Resampling.LANCZOS)
            glyph = Image.new("L", (cw, ch), 0)
            glyph.paste(fitted, ((cw - new_w) // 2, ch - new_h))
        # Quantise to a few alpha levels: the retail masks compress into fixed
        # spans because they are nearly two-level; smooth ramps do not fit.
        ladder = FONTS[slot]["levels"]
        raw = np.asarray(glyph, dtype=np.float32) / 255.0
        cuts = [(i + 0.5) / (len(ladder) - 1) for i in range(len(ladder) - 1)]
        levels = np.zeros(raw.shape, dtype=np.uint8) + ladder[0]
        for cut, value in zip(cuts, ladder[1:]):
            levels[raw >= cut] = value
        plane[y0:y1, x0:x1] = levels
        painted.append(char)
    swizzled = r.tx.swizzle_2d(plane.tobytes(), width, width, 1)
    return decoded[:system_bytes] + swizzled + video[width * width:], painted


def _system_bytes(decoded: bytes) -> int:
    # The FONT object header records its own system size at +8 of the chunk header;
    # the decoded buffer starts with the 32-byte chunk header copy.
    return struct.unpack_from("<I", decoded, 8)[0]



def status(span: bytes, slot: int) -> str:
    from . import nfl2k5_scorebug_ingame as r
    try:
        chunk, decoded, _ = r.decode(span)
    except Exception:  # noqa: BLE001
        return "foreign"
    if chunk.kind != "FONT" or len(span) != span_size(slot):
        return "foreign"
    if digest(decoded) == RETAIL_DECODED_SHA256[slot]:
        return "retail"
    if digest(decoded) == APPLIED_DECODED_SHA256[slot] and span[:32] == _retail_wrapper(slot):
        return "applied"
    return "foreign"


RETAIL_WRAPPERS = {3: "464f4e54101c00000025000000440000efbeedfe100000000000000000000000",
                   7: "464f4e54e03300008025000000040100efbeedfe100000000000000000000000"}


def _retail_wrapper(slot: int) -> bytes:
    return bytes.fromhex(RETAIL_WRAPPERS[slot])


def _expected(retail_span: bytes, slot: int) -> bytes:
    """The applied span for a retail span (deterministic, fixed span, wrapper kept)."""
    from . import nfl2k5_scorebug_ingame as r
    chunk, decoded, _ = r.decode(retail_span)
    if digest(decoded) != RETAIL_DECODED_SHA256[slot]:
        # Recover the retail span from the applied one is impossible; callers pass retail.
        raise FontError("expected a retail FONT span")
    rebuilt, painted = _paint(decoded, slot, FONTS[slot]["width"], _glyph_sources())
    if not painted:
        raise FontError("no glyph cells were painted")
    last = None
    for encoder in ("greedy", "optimal"):
        try:
            result, info = r.fill.rebuild_fixed_span_filled(retail_span, rebuilt, encoder=encoder)
            break
        except r.tx.TxtrError as exc:
            last = exc
    else:
        raise FontError(f"{FONTS[slot]['name']}: the ESPN glyphs do not fit the retail font span ({last})")
    if result[:32] != retail_span[:32] or len(result) != len(retail_span) or r.decode(result)[1] != rebuilt:
        raise FontError("font fixed-span round trip failed")
    if APPLIED_DECODED_SHA256[slot] is not None and digest(rebuilt) != APPLIED_DECODED_SHA256[slot]:
        raise FontError(f"{FONTS[slot]['name']}: the generated glyph mask differs from the pinned build")
    return result


def apply(span: bytes, slot: int) -> tuple[bytes, dict]:
    before = status(span, slot)
    if before == "foreign":
        raise FontError(f"{FONTS[slot]['name']}: foreign or mixed bytes; rebuild from a supported base")
    if before == "applied":
        return span, {"font": FONTS[slot]["name"], "status": "already_applied", "changed_bytes": 0}
    result = _expected(span, slot)
    from . import nfl2k5_scorebug_ingame as r
    _, decoded, _ = r.decode(result)
    _, painted = _paint(r.decode(span)[1], slot, FONTS[slot]["width"], _glyph_sources())
    return result, {"font": FONTS[slot]["name"], "status": "applied", "painted": "".join(painted),
                    "span_size": len(result), "wrapper_identical": result[:32] == span[:32],
                    "sha256_before": digest(span), "sha256_after": digest(result),
                    "experimental": True, "witnessed": False}


def preview(slot: int, out: Path) -> Path:
    """Render the restyled atlas beside the retail one (development aid)."""
    from PIL import Image
    import numpy as np
    from . import nfl2k5_scorebug_ingame as r, nfl2k5_scorebug_fonts as fonts
    import os
    index = os.environ.get("NFL2K5_RETAIL_INDEX") or str(Path(__file__).resolve().parents[2] / "extracted" / "ESPN NFL 2K5 (USA)" / "vc_53450030" / "0")
    pack = Path(index).read_bytes()[:4 * 1024 * 1024]
    span = fonts.source_spans(pack)[slot]
    width = FONTS[slot]["width"]
    _, decoded, _ = r.decode(span)
    new, _ = apply(span, slot)
    _, new_decoded, _ = r.decode(new)
    sysb = _system_bytes(decoded)
    a = np.frombuffer(r.tx.unswizzle_2d(decoded[sysb:sysb + width * width], width, width, 1), dtype=np.uint8).reshape(width, width)
    b = np.frombuffer(r.tx.unswizzle_2d(new_decoded[sysb:sysb + width * width], width, width, 1), dtype=np.uint8).reshape(width, width)
    sheet = Image.new("L", (width * 2 + 8, width), 40)
    sheet.paste(Image.fromarray(a * 17), (0, 0))
    sheet.paste(Image.fromarray(b * 17), (width + 8, 0))
    sheet.save(out)
    return out


# ---------------------------------------------------------------- the ESPN clock font
# One FONT appended to the runtime collection and bound by the owner to the quarter, game
# clock and play clock records. Built the way the beta 69 private fonts were (they drew in
# game): the retail font4 chunk copied whole, including the object tail the loader fills at
# registration, under a new name; every glyph record's advance and quad scaled so the digits
# come out about 11 HUD units tall and condensed; the clock characters' cells repainted from
# the broadcast glyph sheet at all sixteen alpha levels (the chunk is appended uncompressed,
# so nothing has to fit a fixed span).
CLOCK_FONT_NAME = "FirstPersonComic"      # the free tenth boot name, so the owner needs no new data for the lookup
QUARTER_FONT_NAME = "core_bug"            # an existing UTF-16 literal (a FONT and a TXTR may share a name); the quarter label's smaller build
QUARTER_FONT_SCALE = (0.50, 0.72)         # compact grey capitals beside the clock
CLOCK_FONT_CHARS = "0123456789:stndrhOSTNDRH&GoalANDIcew"   # repainted cells; every other cell keeps the retail shape
CLOCK_FONT_SUFFIX = {"S": "s", "T": "t", "N": "n", "D": "d", "R": "r", "H": "h"}  # the game uppercases "1st" before drawing: the capitals carry the small broadcast suffix
CLOCK_FONT_SCALE = (0.80, 0.92)           # (advance/x, y): retail font4 digits are 8 x 12, the clock wants about 6.4 x 11
CLOCK_FONT_DONOR = 3


def _fit_source(char, cw, ch, sources):
    """The broadcast glyph fitted into a retail cell (same rule as _paint), or None."""
    from PIL import Image
    if char == ":":
        glyph = Image.new("L", (cw, ch), 0)
        dot = max(1, round(min(cw, ch) * 0.28))
        for cy in (round(ch * 0.30), round(ch * 0.72)):
            for y in range(cy - dot // 2, cy - dot // 2 + dot):
                for x in range((cw - dot) // 2, (cw - dot) // 2 + dot):
                    if 0 <= x < cw and 0 <= y < ch:
                        glyph.putpixel((x, y), 255)
        return glyph
    source = sources.get(char)
    if source is None:
        return None
    sw, sh = source.size
    scale = ch / sh
    new_w = max(1, round(sw * scale))
    if new_w > cw:
        scale = cw / sw
        new_w = cw
    new_h = max(1, round(sh * scale))
    fitted = source.resize((new_w, new_h), Image.Resampling.LANCZOS)
    glyph = Image.new("L", (cw, ch), 0)
    glyph.paste(fitted, ((cw - new_w) // 2, ch - new_h))
    return glyph


def clock_font(donor_span: bytes, *, name: str = CLOCK_FONT_NAME, scale: tuple = CLOCK_FONT_SCALE) -> tuple[bytes, dict]:
    import numpy as np
    from . import nfl2k5_scorebug_ingame as r
    chunk, source, _ = r.decode(donor_span)
    if (chunk.kind, chunk.system_bytes, chunk.video_bytes) != ("FONT", 9472, 17408) or digest(source) != RETAIL_DECODED_SHA256[CLOCK_FONT_DONOR]:
        raise FontError("clock font donor must be the retail font4 span")
    width = FONTS[CLOCK_FONT_DONOR]["width"]
    system_size, old_object = chunk.system_bytes, 48
    body = bytearray(source[:32] + (name + "\0").encode("utf-16le"))
    body.extend(b"\xff" * (-len(body) % 16))
    obj = len(body)
    body.extend(source[old_object:system_size])
    body.extend(b"\xff" * (-len(body) % 128))
    system = len(body)
    struct.pack_into("<I", body, 20, obj - 20 + 1)   # field-relative object pointer; the name pointer at +16 is unchanged
    sx, sy = scale
    video = bytearray(source[system_size:])
    plane = np.frombuffer(bytes(r.tx.unswizzle_2d(video[:width * width], width, width, 1)), dtype=np.uint8).reshape(width, width).copy()
    if name == CLOCK_FONT_NAME:
        # Twice the donor's mask density, with the complete donor object retained.
        plane=np.repeat(np.repeat(plane,2,axis=0),2,axis=1)
        video=bytearray(plane.tobytes()+video[width*width:]);width*=2
        struct.pack_into("<I",body,obj+40,width*width)
        struct.pack_into("<I",body,obj+44,0x08810b29)
    sources = _glyph_sources()
    from PIL import Image
    import json
    label_sheet=Image.open(DATA/"painted_label_2x.png").convert("L")
    label_sources={ch:label_sheet.crop(box) for ch,box in json.loads((DATA/"painted_label_2x.json").read_text())["boxes"].items()}
    cells = {chr(cp): _cell(source, rec, width) for cp, rec in _records(source) if chr(cp) in CLOCK_FONT_CHARS}
    painted, narrow = [], {}
    digit_h = sources["0"].height
    for char, (x0, y0, x1, y1) in cells.items():
        cw, ch = x1 - x0, y1 - y0
        if cw <= 0 or ch <= 0:
            continue
        if char in label_sources:
            glyph=label_sources[char].resize((cw,ch),Image.Resampling.LANCZOS)
            levels=(np.asarray(glyph,dtype=float)*15/255+.5).astype(np.uint8)
            plane[y0:y1,x0:x1]=np.clip(levels,0,15)
            painted.append(char)
            continue
        if char in CLOCK_FONT_SUFFIX:
            # Small suffix letters at the digits' scale, on the baseline, centred in the capital's cell.
            from PIL import Image
            src = sources.get(CLOCK_FONT_SUFFIX[char])
            if src is None:
                continue
            scale = ch / digit_h
            new_w, new_h = max(1, round(src.width * scale)), max(1, round(src.height * scale))
            if new_w > cw or new_h > ch:
                continue
            glyph = Image.new("L", (cw, ch), 0)
            glyph.paste(src.resize((new_w, new_h), Image.Resampling.LANCZOS), (0, ch - new_h))
            narrow[char] = new_w
        else:
            glyph = _fit_source(char, cw, ch, sources)
        if glyph is None:
            continue
        levels = (np.asarray(glyph, dtype=np.float32) * MASK_LEVELS / 255.0 + 0.5).astype(np.uint8)
        plane[y0:y1, x0:x1] = np.clip(levels, 0, MASK_LEVELS)
        painted.append(char)
    video[:width * width] = r.tx.swizzle_2d(plane.tobytes(), width, width, 1)
    # Records: every advance and quad scaled to the clock size; the suffix capitals narrowed to
    # their painted width (UV cell and quad), so "1ST" sets tight like the broadcast "1st".
    ranges = obj + 8 + struct.unpack_from("<I", body, obj + 8)[0] - 1
    count = struct.unpack_from("<I", body, obj + 4)[0]
    for i in range(count):
        rec = ranges + 8 * i
        first, last, relative = struct.unpack_from("<HHI", body, rec)
        glyphs = rec + 4 + relative - 1
        for cp in range(first, last + 1):
            off = glyphs + 96 * (cp - first)
            char = chr(cp)
            advance = struct.unpack_from("<I", body, off)[0]
            pos = list(struct.unpack_from("<16f", body, off + 16))
            u0, v0, u1, v1 = struct.unpack_from("<4f", body, off + 80)
            if char in narrow:
                x0, _y0, x1, _y1 = cells[char]
                fraction = narrow[char] / (x1 - x0)
                u1 = u0 + (u1 - u0) * fraction
                pos[4] = pos[12] = pos[0] + (pos[4] - pos[0]) * fraction
                advance = round(advance * fraction) + 1
                struct.pack_into("<4f", body, off + 80, u0, v0, u1, v1)
            for j in range(4):
                pos[4 * j] *= sx
                pos[4 * j + 1] *= sy
            struct.pack_into("<I", body, off, round(advance * sx))
            struct.pack_into("<16f", body, off + 16, *pos)
    # Native quads tightly bound the authored ink, at measured source-frame sizes.
    for i in range(count):
        rec=ranges+8*i;first,last,relative=struct.unpack_from("<HHI",body,rec)
        glyphs=rec+4+relative-1
        for cp in range(first,last+1):
            ch=chr(cp)
            if ch not in label_sources: continue
            off=glyphs+96*(cp-first);src=label_sources[ch]
            if name==QUARTER_FONT_NAME:
                height=19 if ch.isdigit() else 13
                ink_width=16 if ch.isdigit() else 13
                advance=6 if ch.isdigit() else 4
                top=0
            else:
                height=23*src.height/46
                ink_width=1.12*23*src.width/46
                advance=7 if ch.isdigit() else 4 if ch in 'rst' else 7 if ch=='&' else 5
                top=23-height
                if ch==':': height=19;ink_width=4;top=4;advance=2
            pp=list(struct.unpack_from("<16f",body,off+16))
            for j,(xx,yy) in enumerate(((0,0),(1,0),(0,1),(1,1))):
                pp[j*4]=xx*ink_width/3;pp[j*4+1]=(top+yy*height)*448/1080
            struct.pack_into("<16f",body,off+16,*pp)
            struct.pack_into("<I",body,off,advance)
    for off, scale in ((12, sx), (16, sy), (20, sy), (24, sy), (28, sy)):
        value = struct.unpack_from("<i", body, obj + off)[0]
        struct.pack_into("<i", body, obj + off, round(value * scale))
    if name == CLOCK_FONT_NAME:
        from PIL import Image
        # The private U+0080..U+0089 cells are a second size of 0..9.
        # Retail/global fonts and every existing ASCII glyph stay intact.
        records = {}
        for i in range(count):
            rec = ranges + 8 * i
            first, last, relative = struct.unpack_from("<HHI", body, rec)
            glyphs = rec + 4 + relative - 1
            records.update((cp, glyphs + 96 * (cp-first)) for cp in range(first, last+1))
        # Append one isolated range, retaining all existing ASCII glyphs.
        old_ranges = [(struct.unpack_from("<HH", body, ranges+8*i),
                       ranges+8*i+4+struct.unpack_from("<I",body,ranges+8*i+4)[0]-1)
                      for i in range(count)]
        new_ranges = len(body)
        body.extend(bytes(8*(count+4)))
        struct.pack_into("<II",body,obj+4,count+4,new_ranges-(obj+8)+1)
        for i,((first,last),glyphs) in enumerate(old_ranges):
            at=new_ranges+8*i
            new_glyphs = glyphs
            struct.pack_into("<HHI",body,at,first,last,(new_glyphs-(at+4)+1)&0xffffffff)
            records.update((cp,new_glyphs+96*(cp-first)) for cp in range(first,last+1))
        digits_at=len(body)
        at=new_ranges+8*count
        struct.pack_into("<HHI",body,at,0x80,0x89,digits_at-(at+4)+1)
        body.extend(bytes(3840))
        at=new_ranges+8*(count+1)
        struct.pack_into("<HHI",body,at,0x90,0x99,digits_at+960-(at+4)+1)
        for extra,base in enumerate((0xb0,0xc0),2):
            at=new_ranges+8*(count+extra)
            struct.pack_into("<HHI",body,at,base,base+9,digits_at+960*extra-(at+4)+1)
        struct.pack_into("<H",body,obj+2,0xc9)
        occupied = np.zeros((width,width),dtype=bool)
        for cp,off in records.items():
            x0,y0,x1,y1 = _cell(body,off,width)
            occupied[y0:y1,x0:x1] = True
        for digit in range(10):
            src, dst = records[48+digit], digits_at+96*digit
            body[dst:dst+96] = body[src:src+96]
            # Pack sharper score masks into unused atlas cells. Existing ASCII
            # masks remain disjoint, and the 128x128 video allocation is unchanged.
            cw,ch = 26,48
            cell = next(((x,y) for y in range(width-ch+1) for x in range(width-cw+1)
                         if not occupied[y:y+ch,x:x+cw].any()),None)
            if cell is None: raise FontError("score glyph cells exceed the spare atlas area")
            x,y=cell; occupied[y:y+ch,x:x+cw]=True
            mask=sources[str(digit)].point(lambda p: max(0,min(255,(p-140)*255//80))).resize((cw,ch),Image.Resampling.LANCZOS)
            mask=np.asarray(mask,dtype=float)
            # Close the sampled score face's weak interior; preserve antialiased edges.
            mask=np.maximum.reduce((mask,np.pad(mask[:,1:],((0,0),(0,1)),mode='edge'),np.pad(mask[:,:-1],((0,0),(1,0)),mode='edge')))
            plane[y:y+ch,x:x+cw]=np.clip((mask*15/255+.5).astype(np.uint8),0,15)
            pos = list(struct.unpack_from("<16f", body, dst+16))
            x0,y0=pos[0],pos[1];w0,h0=pos[4]-x0,pos[9]-y0
            for j in range(4):
                pos[j*4]=(pos[j*4]-x0)*(40/3)/w0
                pos[j*4+1]=(pos[j*4+1]-y0)*(53*448/1080)/h0
            struct.pack_into("<16f",body,dst+16,*pos)
            struct.pack_into("<4f",body,dst+80,x/width,y/width,(x+cw)/width,(y+ch)/width)
            struct.pack_into("<I",body,dst,14)
            # Multi-digit scores reuse those masks with narrower metrics so
            # even three digits remain outside the possession plate.
            compact=dst+960
            body[compact:compact+96]=body[dst:dst+96]
            for j in range(4):pos[j*4]*=25/40
            struct.pack_into("<16f",body,compact+16,*pos)
            struct.pack_into("<I",body,compact,8)
            for extra,w,h,advance in ((2,25/3,27*448/1080,8),(3,15/3,19*448/1080,5)):
                target=dst+extra*960;body[target:target+96]=body[dst:dst+96]
                pp=list(struct.unpack_from("<16f",body,target+16))
                for j,(xx,yy) in enumerate(((0,0),(1,0),(0,1),(1,1))):
                    pp[j*4]=xx*w;pp[j*4+1]=yy*h
                struct.pack_into("<16f",body,target+16,*pp)
                struct.pack_into("<I",body,target,advance)
        off = records[ord("~")]
        x0,y0,x1,y1 = _cell(body, off, width)
        plane[y0:y1,x0:x1] = 15
        pos = list(struct.unpack_from("<16f", body, off+16))
        for j,(x,y) in enumerate(((0,0),(1,0),(0,1),(1,1))):
            pos[j*4] = x*(20/3)
            pos[j*4+1] = y*(7*448/1080)
        struct.pack_into("<16f",body,off+16,*pos)
        struct.pack_into("<I",body,off,7)
        # A 3-unit space gives three 6.4-unit ticks a 26.4-unit overall width.
        struct.pack_into("<I",body,obj+12,3)
        video[:width*width] = r.tx.swizzle_2d(plane.tobytes(),width,width,1)
    body.extend(b"\xff" * (-len(body) % 128))
    system = len(body)
    body.extend(video)
    header = struct.pack("<4s7I", b"FONT", len(body), system, len(video), 0, 0, 0, 0)
    result = header + bytes(body)
    check, again, _ = r.decode(result)
    if check.kind != "FONT" or again != bytes(body):
        raise FontError("clock font round trip failed")
    return result, dict(name=name, donor="font4", scale=scale, painted="".join(painted),
                        object_offset=obj, system_bytes=system, video_bytes=len(video), span_size=len(result),
                        sha256=digest(result))
