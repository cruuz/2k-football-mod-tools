"""Private indicator FONT from a coverage atlas and per-glyph metrics.

No font artwork is embedded. The placeholder exporter derives test pixels from
the user's retail FONT4. HUD writes retain the exact sprite-scene span size.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import string
import struct

from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_bump_strength import _sections, section_digest

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FOLDER = ROOT / "data/nfl2k5_indicator_names"
SCHEMA = "nfl2k5_indicator_names/v1"
CHARACTERS = string.ascii_uppercase + string.digits + "'-. "
ATLAS = (256, 128)
NAME, NAME_VA = "icon_controller_star", 0xE6C16C
HOOK, HOOK_END = 0xF9FE5, 0xFA012
HOOK_BEFORE = bytes.fromhex(
    "b903000000c705d851a900c0c0c0ffe85758ffff8bf085f67507a3a84ea900eb0c8bcee8c3f3f4ffa3a84ea900")
HOOK_RETAIL_SHA = hashlib.sha256(HOOK_BEFORE).hexdigest()
DONOR_SHA = "60cc66a63ca3ae443b2c38e6ff7abaecfbfb484866433394be151106474afa7e"


def require(ok, message):
    if not ok:
        raise ValueError("indicator names: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _tools():
    from .nfl2k5_scorebug_ingame import tx, fill
    return tx, fill


def load_atlas(folder=None):
    from PIL import Image
    folder = Path(folder or DEFAULT_FOLDER)
    raw = (folder / "metrics.json").read_bytes()
    require(len(raw) <= 64 * 1024, "metrics exceed 64 KiB")
    spec = json.loads(raw)
    require(spec.get("schema") == SCHEMA and spec.get("atlas") == list(ATLAS)
            and spec.get("texture") == "atlas.png", "unknown atlas contract")
    require(type(spec.get("placeholder")) is bool and isinstance(spec.get("provenance"), str)
            and spec["provenance"], "missing artwork provenance")
    require(spec.get("outline") == 1, "v1 requires a one-pixel baked outline")
    for key in ("cap_height", "line_advance", "baseline"):
        require(type(spec.get(key)) is int and 1 <= spec[key] <= 32, "invalid " + key)
    require(set(spec.get("glyphs", {})) == set(CHARACTERS), "supply exactly the 40 required glyphs")
    png = (folder / "atlas.png").read_bytes()
    require(len(png) <= 512 * 1024, "atlas file exceeds 512 KiB")
    with Image.open(folder / "atlas.png") as src:
        require(src.format == "PNG" and src.mode == "RGBA" and src.size == ATLAS,
                "atlas must be 256x128 RGBA PNG")
        image = src.copy()
    occupied = []
    for char, glyph in spec["glyphs"].items():
        rect, quad, advance = glyph.get("rect"), glyph.get("quad"), glyph.get("advance")
        require(isinstance(rect, list) and len(rect) == 4 and all(type(v) is int for v in rect), "invalid rect")
        require(isinstance(quad, list) and len(quad) == 4
                and all(type(v) in (int, float) and math.isfinite(v) and -32 <= v <= 64 for v in quad), "invalid quad")
        require(type(advance) is int and 1 <= advance <= 32, "invalid advance")
        if char == " ":
            require(rect == quad == [0, 0, 0, 0], "space must have no quad")
            continue
        x0, y0, x1, y1 = rect
        require(0 <= x0 < x1 <= 256 and 0 <= y0 < y1 <= 128 and x1-x0 <= 32 and y1-y0 <= 24,
                "glyph rect outside atlas or exceeds 32x24")
        require((quad[2]-quad[0], quad[3]-quad[1]) == (x1-x0, y1-y0), "quad must be one texel per HUD pixel")
        require(not any(a < x1 and x0 < c and b < y1 and y0 < d for a,b,c,d in occupied), "overlapping glyph rectangles")
        occupied.append(rect)
        crop = image.crop(rect)
        require(all((r,g,b) == (255,255,255) for r,g,b,a in crop.getdata() if a), "source glyphs must be white coverage")
        bounds = crop.getchannel("A").getbbox()
        require(bounds is not None and bounds[0] >= 1 and bounds[1] >= 1
                and bounds[2] < crop.width and bounds[3] < crop.height, "glyph needs one transparent pixel on every edge")
    return spec, image, dict(metrics_sha256=sha(raw), atlas_sha256=sha(png), placeholder=spec["placeholder"])


def compile_font(folder=None):
    from PIL import Image, ImageFilter
    tx, _ = _tools()
    spec, image, receipt = load_atlas(folder)
    indices = Image.new("L", ATLAS, 0)
    for char, glyph in spec["glyphs"].items():
        if char == " ":
            continue
        alpha = image.crop(glyph["rect"]).getchannel("A")
        ring = alpha.filter(ImageFilter.MaxFilter(3))
        values = bytes((a * 15 + 127) // 255 or (15 + (r * 15 + 127) // 255 if r >= 9 else 0)
                       for a, r in zip(alpha.tobytes(), ring.tobytes()))
        indices.paste(Image.frombytes("L", alpha.size, values), tuple(glyph["rect"][:2]))
    body = bytearray(32)
    body[12:16] = b"FONT"
    body += (NAME + "\0").encode("utf-16le")
    body += b"\xff" * (-len(body) % 16)
    obj = len(body)
    ranges, records = obj + 0xC0, obj + 0xD0
    struct.pack_into("<II", body, 16, 17, obj - 20 + 1)
    body += struct.pack("<HHIIIIIiI", 32, 126, 1, ranges-(obj+8)+1,
                        spec["glyphs"][" "]["advance"], spec["line_advance"],
                        spec["cap_height"], -3, spec["baseline"])
    body += struct.pack("<8I", 0, 0, 256*128, 0x07810B29, 0, 0x80000000, 0x1FFFF, 0)
    body += bytes(128)
    require(len(body) == ranges, "FONT header layout")
    body += struct.pack("<HHI", 32, 126, records-(ranges+4)+1) + b"\xff"*8
    for cp in range(32, 127):
        glyph = spec["glyphs"].get(chr(cp).upper(), spec["glyphs"][" "])
        x0,y0,x1,y1 = glyph["quad"]
        u0,v0,u1,v1 = glyph["rect"]
        body += struct.pack("<I", glyph["advance"]) + b"\xff"*12
        body += struct.pack("<16f", x0,y0,0,0,x1,y0,0,0,x0,y1,0,0,x1,y1,0,0)
        body += struct.pack("<4f", u0/256,v0/128,u1/256,v1/128)
    body += b"\xff" * (-len(body) % 128)
    system = len(body)
    palette = bytes(4) + b"".join(bytes((255,255,255,17*i)) for i in range(1,16))
    palette += b"".join(bytes((16,16,16,17*i)) for i in range(1,16))
    palette += bytes(1024-len(palette))
    video = tx.swizzle_2d(indices.tobytes(), *ATLAS, 1) + palette
    decoded = bytes(body) + video
    result = struct.pack("<4s7I", b"FONT", len(decoded), system, len(video), 0,0,0,0) + decoded
    return result, dict(receipt, font_sha256=sha(result), system_bytes=system, video_bytes=len(video),
                        cap_height=spec["cap_height"], outline=1, resource_name=NAME)


def _name(decoded):
    start = 16 + struct.unpack_from("<I", decoded, 16)[0] - 1
    units = []
    for i in range(128):
        unit = decoded[start+2*i:start+2*i+2]
        if unit == b"\0\0":
            return b"".join(units).decode("utf-16le")
        require(len(unit) == 2, "truncated resource name")
        units.append(unit)
    raise ValueError("unterminated resource name")


def _compressed(raw, span_size=None):
    tx, fill = _tools()
    kind, _, system, video, magic, _, r0, r1 = struct.unpack_from("<4s7I", raw)
    require(magic == 0 and len(raw) == 32 + system + video, "expected raw resource")
    decoded = raw[32:]
    encoded, _ = tx.compress_vc_lz(decoded, stream_tag=1, offset_bits=10, verify_roundtrip=True)
    stored = ((len(encoded)+15)//16*16) if span_size is None else span_size-32
    require(stored % 16 == 0 and len(encoded) <= stored, "FONT does not fit the fixed scene span")
    filled, _ = fill.fill_stream(encoded, decoded, stored, slack=16)
    scratch = max(16, (tx.minimum_vc_lz_overlap_scratch(filled, stored, len(decoded))+15)//16*16)
    result = struct.pack("<4s7I", kind, stored, system, video, tx.COMPRESSED_SENTINEL, scratch, r0, r1)
    result += filled + bytes(stored-len(filled))
    require(tx.decode_chunk(result, tx.parse_chunks(result)[0])[0] == decoded, "compressed roundtrip failed")
    return result


def _scene_slot(hud):
    tx, _ = _tools()
    chunks = tx.parse_chunks(hud)
    candidates = []
    for i, chunk in enumerate(chunks):
        if chunk.kind != "SCNE":
            continue
        decoded, _ = tx.decode_chunk(hud, chunk)
        if _name(decoded) == "score_bug" and len(decoded) > 16512:
            # Sprite-specific marker, not a retail score_bug clone.
            from .nfl2k5_scorebug_sprite import MAGIC, MARKER_OFFSET
            if struct.unpack_from("<I", decoded, MARKER_OFFSET)[0] == MAGIC:
                candidates.append((i, chunk, decoded))
    require(len(candidates) == 1, "requires exactly one appended sprite scorebug scene")
    i, chunk, decoded = candidates[0]
    raw = struct.pack("<4s7I", b"SCNE", len(decoded), chunk.system_bytes, chunk.video_bytes, 0,0,0,0)+decoded
    end = chunk.offset + len(raw)
    font = None
    if chunk.compression_magic:
        require(i+1 < len(chunks), "compressed scene has no private FONT")
        next_chunk = chunks[i+1]
        require(next_chunk.kind == "FONT" and next_chunk.offset + 32 + next_chunk.stored_size == end,
                "private FONT does not fill the original scene span")
        font, _ = tx.decode_chunk(hud, next_chunk)
        require(_name(font) == NAME, "foreign FONT after scorebug")
    else:
        require(hud[chunk.offset:end] == raw, "unknown raw scene wrapper")
    return chunk.offset, end, raw, font


def canonical_hud(hud):
    """Recover the byte-identical uncompressed scene for composition checks."""
    start, end, raw, _ = _scene_slot(hud)
    return hud[:start] + raw + hud[end:]


def apply_hud(hud, folder=None):
    start, end, scene, old_font = _scene_slot(hud)
    font, receipt = compile_font(folder)
    scene_packed = _compressed(scene)
    font_packed = _compressed(font, end-start-len(scene_packed))
    replacement = scene_packed + font_packed
    require(len(replacement) == end-start, "fixed span length changed")
    if old_font is not None:
        require(old_font == font[32:], "different atlas already installed; rebuild from the base")
    result = hud[:start] + replacement + hud[end:]
    require(canonical_hud(result) == canonical_hud(hud), "decoded scorebug or other resources changed")
    return result, dict(receipt, start=start, end=end, scene_decoded_sha256=sha(scene[32:]),
                        scene_bytes_unchanged=True, state="applied" if result == hud else "repaired",
                        changed_bytes=sum(a != b for a,b in zip(hud,result)))


def hook_bytes():
    # Preserve wind/charge material initialization, then do the private typed
    # lookup in the original initializer's space. ESI remains the FONT object,
    # EAX is its graphics descriptor (or null), as in the original path.
    code = bytearray.fromhex("c705d851a900c0c0c0ff")
    code += b"\x68" + struct.pack("<I", NAME_VA)
    code += b"\xbaFONT\x31\xc9"
    at = HOOK + len(code)
    code += b"\xe8" + struct.pack("<i", 0x449E0-at-5)
    code += bytes.fromhex("89c685c0740383c040a3a84ea900")
    require(len(code) <= HOOK_END-HOOK, "initializer overflow")
    return bytes(code) + b"\x90"*(HOOK_END-HOOK-len(code))


def apply_xbe(payload):
    image = XbeImage(payload)
    require(image.read(NAME_VA, len((NAME+"\0").encode("utf-16le"))) == (NAME+"\0").encode("utf-16le"), "resource name changed")
    new = hook_bytes()
    before = image.read(HOOK, HOOK_END-HOOK)
    require(before in (HOOK_BEFORE,new), "unknown indicator initializer")
    buf = bytearray(payload)
    at = image.offset(HOOK, len(new))
    buf[at:at+len(new)] = new
    for section in _sections(buf):
        if section.virtual_address <= HOOK < section.virtual_address + section.raw_size:
            buf[section.header_offset+36:section.header_offset+56] = section_digest(buf,section)
    return bytes(buf), dict(state="applied" if before == new else "repaired", va=hex(HOOK), size=len(new),
                            changed_bytes=sum(a != b for a,b in zip(payload,buf)))


def export_placeholder(donor_span, folder):
    """Mechanical retail FONT4 repack; private test output only, no font download."""
    from PIL import Image
    tx, _ = _tools()
    chunk = tx.parse_chunks(donor_span)[0]
    decoded, _ = tx.decode_chunk(donor_span, chunk)
    require(chunk.kind == "FONT" and sha(decoded) == DONOR_SHA, "not the pinned retail indicator FONT4")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    obj = 20 + struct.unpack_from("<I", decoded, 20)[0] - 1
    ranges = obj+8 + struct.unpack_from("<I", decoded, obj+8)[0] - 1
    first,last,relative = struct.unpack_from("<HHI", decoded,ranges)
    records = ranges+4+relative-1
    src = Image.frombytes("L", (128,128), tx.unswizzle_2d(decoded[chunk.system_bytes:chunk.system_bytes+128*128],128,128,1))
    # The donor's first sixteen palette entries have alpha 0,17,...255.
    palette = decoded[chunk.system_bytes+128*128:chunk.system_bytes+128*128+1024]
    alpha = src.point([palette[i*4+3] for i in range(256)])
    canvas = Image.new("RGBA", ATLAS, (255,255,255,0))
    glyphs = {}
    for index,char in enumerate(CHARACTERS):
        if char == " ":
            glyphs[char] = dict(rect=[0,0,0,0],quad=[0,0,0,0],advance=4)
            continue
        require(first <= ord(char) <= last, "donor lacks required glyph")
        at = records+96*(ord(char)-first)
        advance = struct.unpack_from("<I",decoded,at)[0]
        pos = struct.unpack_from("<16f",decoded,at+16)
        uv = struct.unpack_from("<4f",decoded,at+80)
        mask = alpha.crop(tuple(round(v*128) for v in uv))
        x,y = index%8*32,index//8*24
        rect = [x,y,x+mask.width+2,y+mask.height+2]
        canvas.paste(Image.new("RGBA",mask.size,(255,255,255,255)),(x+1,y+1),mask)
        glyphs[char] = dict(rect=rect,quad=[min(pos[0::4])-1,min(pos[1::4])-1,max(pos[0::4])+1,max(pos[1::4])+1],advance=advance)
    spec = dict(schema=SCHEMA,atlas=list(ATLAS),texture="atlas.png",placeholder=True,
                provenance="PLACEHOLDER: mechanically repacked retail FONT4; donor decoded SHA256 "+DONOR_SHA,
                cap_height=11,line_advance=17,baseline=15,outline=1,glyphs=glyphs)
    canvas.save(folder/"atlas.png")
    (folder/"metrics.json").write_text(json.dumps(spec,indent=2)+"\n",encoding="utf-8",newline="\n")
    load_atlas(folder)
    return spec


def image_plan(stream, folder=None):
    """Prepare all fixed spans without writing, using the current disc extents."""
    from . import xdvdfs_compact as xd
    from .nfl2k5_scorebug_ingame import tx  # also establishes the bundled tools path
    import nfl_outer as outer
    layout = xd.read_layout(stream)
    pack, executable = layout.entries["vc_53450030/0"], layout.entries["default.xbe"]
    stream.seek(pack.byte_offset + outer.HEADER_SIZE + 346*12)
    identity, size, sector = struct.unpack("<3I", stream.read(12))
    require(identity == 0xB6926C and 32 <= size <= 4*1024*1024, "unknown HUD outer")
    hud_offset = pack.byte_offset + sector*2048
    require(sector*2048+size <= pack.size, "HUD exceeds pack extent")
    stream.seek(hud_offset)
    hud = stream.read(size)
    stream.seek(executable.byte_offset)
    xbe = stream.read(executable.size)
    fixed_hud, hr = apply_hud(hud, folder)
    fixed_xbe, xr = apply_xbe(xbe)
    start, end = hr["start"], hr["end"]
    edits = [(hud_offset+start, hud[start:end], fixed_hud[start:end], "private FONT and lossless scorebug scene")]
    image = XbeImage(xbe)
    at = image.offset(HOOK, HOOK_END-HOOK)
    edits.append((executable.byte_offset+at, xbe[at:at+45], fixed_xbe[at:at+45], "indicator FONT binding"))
    section = next(s for s in _sections(xbe) if s.virtual_address <= HOOK < s.virtual_address+s.raw_size)
    at = section.header_offset+36
    edits.append((executable.byte_offset+at, xbe[at:at+20], fixed_xbe[at:at+20], "derived .text SHA1"))
    require(len(hud) == len(fixed_hud) and len(xbe) == len(fixed_xbe), "disc file grew")
    return edits, dict(schema="nfl2k5_indicator_names_write/v1", font=hr, xbe=xr,
                       xbe_before_sha256=sha(xbe), xbe_after_sha256=sha(fixed_xbe),
                       hud_before_sha256=sha(hud), hud_after_sha256=sha(fixed_hud),
                       disc_layout_unchanged=True)


def apply_to_image(path, *, folder=None, progress=None):
    """Studio final-stage writer. The caller owns its writable output image."""
    fd = os.open(path, os.O_RDWR | getattr(os,"O_BINARY",0))
    with os.fdopen(fd,"r+b") as stream:
        edits, receipt = image_plan(stream,folder)
        written = 0
        for offset, before, after, label in edits:
            if before == after:
                continue
            stream.seek(offset)
            require(stream.read(len(before)) == before, "input changed after planning")
            stream.seek(offset)
            require(stream.write(after) == len(after), "short write")
            written += len(after)
        stream.flush()
        os.fsync(stream.fileno())
        for offset, before, after, label in edits:
            stream.seek(offset)
            require(stream.read(len(after)) == after, "readback mismatch: " + label)
    return dict(receipt, bytes_written=written, state="repaired" if written else "applied",
                spans=[dict(offset=o,size=len(b),purpose=l) for o,b,a,l in edits])
