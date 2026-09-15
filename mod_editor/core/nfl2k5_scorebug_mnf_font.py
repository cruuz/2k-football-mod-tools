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
