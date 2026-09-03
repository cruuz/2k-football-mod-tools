#!/usr/bin/env python3
"""Replace any P8 texture of the NFL 2K5 field resource pack (outer 346) inside a modified XISO.

Generalises the strict scorebug importer to every single-mip P8 TXTR chunk of outer 346
(``vc_53450030/0`` at XISO byte offset 1,631,188,992; outer 346 at pack offset 109,895,680).
The PNG is quantized to the chunk's own palette budget, swizzled, and refit into the chunk's
fixed VC-LZ span with the chunk's own stream parameters; the descriptor bytes never change.
Writes in place and only when the span still holds the retail bytes (or already this image).

usage: nfl2k5_fieldpack_texture_into_xiso.py XISO --chunk 34 --png NAVTEXTURE_modern.png [--chunk 24 --png chiclet.png]
       nfl2k5_fieldpack_texture_into_xiso.py --list           (names/sizes of the P8 chunks)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os


def _pread(fd: int, count: int, offset: int) -> bytes:
    """Positional read; Windows has no os.pread, so seek/read/restore there."""
    if hasattr(os, "pread"):
        return os.pread(fd, count, offset)
    here = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        return os.read(fd, count)
    finally:
        os.lseek(fd, here, os.SEEK_SET)


def _pwrite(fd: int, data: bytes, offset: int) -> int:
    """Positional write; Windows has no os.pwrite, so seek/write/restore there."""
    if hasattr(os, "pwrite"):
        return os.pwrite(fd, data, offset)
    here = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        return os.write(fd, data)
    finally:
        os.lseek(fd, here, os.SEEK_SET)
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import nfl_txtr as t  # noqa: E402
import nfl_tset_png_import as palette_tools  # noqa: E402
from nfl_outer import parse_archive, read_entry_range  # noqa: E402

INDEX = Path(os.environ.get("NFL2K5_RETAIL_INDEX", "retail-packs/0"))   # extracted pack index, developer machines only
XISO_PACK_BYTE_OFFSET = 1_631_188_992
OUTER_346_PACK_OFFSET = 109_895_680


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def field_pack():
    arch = parse_archive(INDEX)
    entry = arch.entries[346]
    data = read_entry_range(arch, entry, 0, entry.size)
    return data, t.parse_chunks(data, allow_trailing=True)


def texture_chunks(data, chunks):
    out = []
    for c in chunks:
        if c.kind != "TXTR":
            continue
        span = data[c.offset: c.offset + 0x20 + c.stored_size]
        cc = t.parse_chunks(span, allow_trailing=True)[0]
        try:
            dec, info = t.decode_chunk(span, cc)
            tex = t.parse_texture(dec, cc)
        except Exception:  # noqa: BLE001
            continue
        out.append((c, cc, span, dec, info, tex))
    return out


def build_replacement(span: bytes, cc, dec: bytes, info, tex, png: Path) -> tuple[bytes, dict]:
    width, height = tex.width, tex.height
    if str(getattr(tex, "format_name", getattr(tex, "format", ""))) != "P8":
        raise SystemExit(f"{tex.name}: only P8 textures are supported ({getattr(tex, 'format_name', '?')})")
    expected = 128 + width * height + 1024
    if len(dec) != expected:
        raise SystemExit(f"{tex.name}: decoded layout {len(dec)} is not header+indices+palette ({expected})")
    got_w, got_h, rgba = palette_tools.decode_rgba_png(png.read_bytes(), (width, height))
    if (got_w, got_h) != (width, height):
        raise SystemExit(f"PNG must be {width}x{height}, got {got_w}x{got_h}")
    level = palette_tools.MipLevel(0, width, height, rgba)

    def candidate(palette, levels):
        return dec[:128] + t.swizzle_2d(levels[0], width, height, 1) + palette_tools.palette_bytes(palette)

    bounded = palette_tools.quantize_levels_to_vc_lz_bound(
        [level], candidate, stream_tag=int(info.stream_tag), offset_bits=int(info.offset_bits),
        max_encoded_size=int(cc.stored_size))
    new_dec = bounded.decoded
    import nfl_vc_lz_fill
    new_span, rinfo = nfl_vc_lz_fill.rebuild_fixed_span_filled(span, new_dec)   # wrapper stays retail
    back, _ = t.decode_chunk(new_span, t.parse_chunks(new_span, allow_trailing=True)[0])
    if back != new_dec or len(new_span) != len(span) or new_span[:0x20] != span[:0x20]:
        raise SystemExit("fixed-span rebuild did not round-trip with a retail wrapper")
    return new_span, {"palette_entries": len(bounded.palette), "quantization": bounded.quantization,
                      "filled_bytes": rinfo.filled_bytes, "padding_bytes": rinfo.padding_bytes,
                      "scratch_bytes": rinfo.scratch_bytes, "stored_size": cc.stored_size}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xiso", nargs="?")
    ap.add_argument("--chunk", type=int, action="append", default=[])
    ap.add_argument("--png", action="append", default=[])
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    data, chunks = field_pack()
    texes = texture_chunks(data, chunks)
    if args.list:
        for c, cc, span, dec, info, tex in texes:
            print(f"chunk {c.index:3d} {tex.name!r:20s} {tex.width}x{tex.height} {getattr(tex, 'format_name', getattr(tex, 'format', '?'))} span {len(span)} decoded {len(dec)}")
        return 0
    if not args.xiso or len(args.chunk) != len(args.png) or not args.chunk:
        raise SystemExit("need XISO and matching --chunk/--png pairs")
    by_index = {c.index: (c, cc, span, dec, info, tex) for c, cc, span, dec, info, tex in texes}
    fd = os.open(args.xiso, os.O_RDWR | getattr(os, "O_BINARY", 0))
    receipts = []
    try:
        for index, png in zip(args.chunk, args.png):
            c, cc, span, dec, info, tex = by_index[index]
            new_span, rec = build_replacement(span, cc, dec, info, tex, Path(png))
            absolute = XISO_PACK_BYTE_OFFSET + OUTER_346_PACK_OFFSET + c.offset
            current = _pread(fd, len(span), absolute)
            if current == span:
                state = "retail"
            elif current == new_span:
                state = "already"
            else:
                raise SystemExit(f"chunk {index} ({tex.name}) at {absolute:#x} is neither retail nor this replacement")
            if state == "retail":
                _pwrite(fd, new_span, absolute)
                if _pread(fd, len(span), absolute) != new_span:
                    raise SystemExit("readback failed")
            receipts.append({"chunk": index, "name": tex.name, "png": str(png), "absolute": absolute, "state_before": state,
                             "span_sha256_after": sha(new_span), **{k: v for k, v in rec.items() if k != "quantization"},
                             "palette_reduced": bool(getattr(rec["quantization"], "palette_was_reduced", False))
                             if not isinstance(rec["quantization"], dict) else rec["quantization"].get("palette_was_reduced")})
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps(receipts, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
