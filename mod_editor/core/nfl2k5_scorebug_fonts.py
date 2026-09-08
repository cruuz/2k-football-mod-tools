"""Private native FONT resources for the diagnostic exact scorebug.

All source glyph masks come from pinned FONT4/FONT8 spans. The clones have
private names and metrics; the global font slots and source resources remain
retail. The chevron mask is authored here. EXPERIMENTAL / UNWITNESSED.
"""
from __future__ import annotations
import math
import struct
from functools import lru_cache

# Native resource identity includes the FOURCC. These names already exist as
# scorebug SCNE/TXTR names; no global FONT has any of these names.
NAMES = ('score_bug', 'dscore_buga', 'score_buga', 'zscore_buga', 'hscore_buga', 'core_bug', 'ore_bug')
NAME_VAS = (0xe6c798, 0xe6c5d4, 0xe6c6e8, 0xe6c734, 0xe6c638, 0xe6c79a, 0xe6c79c)
# (FONT donor index, x scale, y scale). A compact score font is selected for
# 100+ scores per side, retaining the photographed single/two-digit cap height.
SCALES = ((3, 0.63, 0.76), (7, 0.375, 0.47), (7, 0.75, 1.14), (7, 0.58, 1.14), (3, 1.0, 1.0), (3, 0.44, 0.57), (3, 0.61, 0.67))
SPAN_SIZES = (27040, 76320, 76320, 76320, 27040, 27040, 27040)
APPEND_SIZE = sum(SPAN_SIZES)
HEAP_BYTES = sum((size + 127) // 128 * 128 for size in SPAN_SIZES)
CHEVRON = True
COMPACT_SCORES = True
WEIGHT = [0, 0, 1, 1, 0, 0, 0]
QUARTER_CAPS = True
CHEVRON_SIZE = (14, 4)
# Native FONT load/completion/unload and descriptor relocation. The resource
# compiler relies on these ABIs in addition to the owner's shared TXTR guards.
CODE_GUARDS = ((0x44b60, 416, 'e449609d313477fca240813a743a81ac758d92530dc3cc1b407668c7eb6b7a70'),
               (0x492c0, 196, 'b4b63f4548b405b27fb3d791a2769e7380ac2b9be9e17b415efc155573c41ecd'),
               (0xfc360, 842, '9170acbe42aa1311f72b7af90c56c4f3f7de0832421eec262e9ddd2d88ea3dcb'))
SOURCE_PINS = {
  3: (32096, 7184, 9472, 17408, '60cc66a63ca3ae443b2c38e6ff7abaecfbfb484866433394be151106474afa7e'),
  7: (74336, 13280, 9600, 66560, 'b775bc02454ab2e39fd4b39f0ff400c4af14848b4fccc429861abc2faec4f15f')}


def source_spans(pack):
    from tools import nfl_outer as outer
    at = outer.HEADER_SIZE + 3 * 12
    identity, size, sector = struct.unpack('<III', pack[at:at + 12])
    if (identity, size) != (0x8ee9eeed, 2387424):
        raise ValueError('private scorebug FONT source outer changed')
    return {slot: pack[sector*2048+off:sector*2048+off+32+stored]
            for slot, (off, stored, *_rest) in SOURCE_PINS.items()}


@lru_cache(maxsize=24)
def compile_font(span, name, slot, sx, sy, weight=0, quarter_caps=False, chevron_size=(8,4)):
    from . import nfl2k5_scorebug_ingame as r
    if name not in NAMES or slot not in SOURCE_PINS or not all(math.isfinite(v) and .2 <= v <= 1.5 for v in (sx, sy)):
        raise ValueError('invalid private scorebug FONT settings')
    if type(weight) is not int or weight not in (-1, 0, 1):
        raise ValueError('invalid private scorebug FONT weight')
    if type(quarter_caps) is not bool:
        raise ValueError('invalid private quarter FONT case')
    if len(chevron_size) != 2 or any(type(v) is not int for v in chevron_size) or not (4 <= chevron_size[0] <= 24 and 2 <= chevron_size[1] <= 8):
        raise ValueError('invalid possession glyph dimensions')
    cw, ch = chevron_size
    chunk, source, _ = r.decode(span)
    _, _, system_size, video_size, pin = SOURCE_PINS[slot]
    if (chunk.kind, chunk.system_bytes, chunk.video_bytes) != ('FONT', system_size, video_size) or r.digest(source) != pin:
        raise ValueError('private scorebug FONT donor identity changed')
    old_object = 48
    body = bytearray(source[:32] + (name + '\0').encode('utf-16le'))
    body.extend(b'\xff' * (64 - len(body)))
    obj = len(body)
    body.extend(source[old_object:system_size])
    body.extend(b'\xff' * (-len(body) % 128))
    system = len(body)
    video = bytearray(source[system_size:])
    struct.pack_into('<I', body, 20, obj - 20 + 1)
    ranges = obj + 8 + struct.unpack_from('<I', body, obj+8)[0] - 1
    count = struct.unpack_from('<I', body, obj+4)[0]
    chevron = name == NAMES[4]
    glyph_offsets, glyph_boxes = {}, set()
    for i in range(count):
        rec = ranges + 8*i
        first, last, relative = struct.unpack_from('<HHI', body, rec)
        glyphs = rec + 4 + relative - 1
        for cp in range(first, last+1):
            off = glyphs + 96*(cp-first)
            glyph_offsets[cp] = off
            glyph_boxes.add(struct.unpack_from('<4f', body, off+80))
            advance = struct.unpack_from('<I', body, off)[0]
            pos = list(struct.unpack_from('<16f', body, off+16))
            for j in range(4):
                pos[4*j] *= sx; pos[4*j+1] *= sy
            struct.pack_into('<I', body, off, round(advance*sx))
            struct.pack_into('<16f', body, off+16, *pos)
            if chevron:
                struct.pack_into('<I', body, off, 0)
                struct.pack_into('<16f', body, off+16, 0,0,0,0, cw,0,0,0, 0,ch,0,0, cw,ch,0,0)
                struct.pack_into('<4f', body, off+80, 0,0,cw/128,ch/128)
    if quarter_caps and name == NAMES[5]:
        # Quarter-only superscript capitals, using the pinned native S/T masks.
        # The callback's UTF-16 "1st" and all other FONT resources stay intact.
        numeral = struct.unpack_from('<16f', body, glyph_offsets[ord('1')]+16)
        top = min(numeral[1::4])
        for lower, upper in (('s','S'), ('t','T')):
            target, source_at = glyph_offsets[ord(lower)], glyph_offsets[ord(upper)]
            positions = list(struct.unpack_from('<16f', body, source_at+16))
            old_top = min(positions[1::4])
            for j in range(4):
                positions[4*j] *= .7
                positions[4*j+1] = top + (positions[4*j+1]-old_top)*.6
            struct.pack_into('<16f', body, target+16, *positions)
            body[target+80:target+96] = body[source_at+80:source_at+96]
            struct.pack_into('<I', body, target, max(1, round(struct.unpack_from('<I',body,source_at)[0]*.7)))
            # The quarter-only callback now emits capitals. Preserve the same
            # fitted superscript metrics for both spellings in this FONT only.
            body[source_at:source_at+96] = body[target:target+96]
    for off, scale in ((12, sx), (16, sy), (20, sy), (24, sy), (28, sy)):
        value = struct.unpack_from('<i', body, obj+off)[0]
        struct.pack_into('<i', body, obj+off, round(value*scale))
    width = 128 if slot == 3 else 256
    if weight or chevron:
        from PIL import Image, ImageFilter
        linear = r.tx.unswizzle_2d(video[:width*width], width, width, 1)
        if chevron:
            linear = bytes(15 if y < ch and math.ceil(y*(cw-2)/(2*(ch-1))) <= x < cw-math.ceil(y*(cw-2)/(2*(ch-1))) else 0
                           for y in range(width) for x in range(width))
            struct.pack_into('<II', body, obj+12, 0, ch)
        else:
            mask = Image.frombytes('L', (width,width), linear)
            adjusted = mask.copy()
            operation = ImageFilter.MaxFilter(3) if weight > 0 else ImageFilter.MinFilter(3)
            # Filter each original glyph window independently so adjacent
            # atlas glyphs cannot grow into one another's sampled rectangles.
            for uv in sorted(glyph_boxes):
                box = tuple(round(v*width) for v in uv)
                if box[2] > box[0] and box[3] > box[1]:
                    original = mask.crop(box)
                    filtered = original.filter(operation)
                    # Thinning must never erase a numeral or punctuation mark.
                    adjusted.paste(filtered if filtered.getbbox() else original, box)
            linear = adjusted.tobytes()
        video[:width*width] = r.tx.swizzle_2d(linear, width, width, 1)
    body.extend(video)
    header = struct.pack('<4s7I', b'FONT', len(body), system, len(video), 0,0,0,0)
    return header + body


def compile_collection(pack, *, scales=None, weight=None):
    scales = SCALES if scales is None else scales
    weight = WEIGHT if weight is None else weight
    if type(weight) is int:
        weights = (weight,) * len(NAMES)
    elif isinstance(weight, (tuple,list)):
        weights = tuple(weight)
    else:
        raise ValueError('invalid private FONT role weights')
    if len(weights) != len(NAMES) or any(type(w) is not int or w not in (-1,0,1) for w in weights):
        raise ValueError('invalid private FONT role weights')
    inputs = source_spans(pack)
    if len(scales) != len(NAMES):
        raise ValueError('private scorebug FONT count changed')
    return tuple(compile_font(inputs[slot], name, slot, sx, sy, weights[i] if i != 4 else 0, QUARTER_CAPS,
                              tuple(CHEVRON_SIZE) if i == 4 else (8,4))
                 for i, (name, (slot,sx,sy)) in enumerate(zip(NAMES,scales)))
