#!/usr/bin/env python3
"""Put prototype relief maps into a COPY of a disc, or only measure them (--measure): each slot is a fixed compressed span,
so a map must pack into the kit's own stored size. Uses the Studio's bump resolver and mip chain and the tighter
(optimal-parse) packer the kit passes use; only the exact spans change, each is read back and decoded.
  bump_apply.py [--measure] SOURCE_DISC TARGET_COPY SELECTOR=bump_jersey.png[,bump_sleeve.png[,bump_pants.png]] ..."""
import sys, json, hashlib
from dataclasses import replace
from pathlib import Path
WT = Path('/home/noah/2k-worktrees/b81-uniforms'); sys.path[:0] = [str(WT), str(WT / 'tools')]
from mod_editor.core import nfl2k5_bump_texture_writer as bw
from nfl_txtr import swizzle_2d, decode_chunk, parse_chunks, HEADER
generate_mips = bw.generate_mips
import nfl_vc_lz_fill as fill
args = sys.argv[1:]; measure = args and args[0] == '--measure'
if measure: args = args[1:]
src, dst = Path(args[0]), Path(args[1])
ex = {s['selector']: s for s in json.load(open('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/work/v09/export.json'))['sets']}
def body(resolved, rgba):
    t = resolved.texture
    levels = generate_mips(rgba, t.width, t.height, t.mip_levels)
    levels[0] = replace(levels[0], rgba=rgba)
    def bgra(b):
        o = bytearray(b); o[0::4], o[2::4] = b[2::4], b[0::4]; return bytes(o)
    chain = b''.join(swizzle_2d(bgra(l.rgba), l.width, l.height, 4) for l in levels)
    assert len(chain) == resolved.chunk.video_bytes
    return resolved.decoded[:resolved.chunk.system_bytes] + chain
def packed_size(resolved, decoded):
    tinfo = decode_chunk(resolved.span, parse_chunks(resolved.span, allow_trailing=True)[0])[1]
    stream = resolved.span[HEADER.size:HEADER.size + tinfo.consumed_bytes]
    import struct
    tag = struct.unpack_from('<II', stream, 0)[1]
    return len(fill.compress_optimal(decoded, stream_tag=tag, offset_bits=stream[8]))
out = []
with bw._Image.open(src, writable=False) as source:
    plans = []
    for spec in args[2:]:
        sel, files = spec.split('=')
        for name, png in zip(('bump_jersey', 'bump_sleeve', 'bump_pants'), files.split(',')):
            if not png: continue
            resolved, index, entry = bw._resolve_bump(source, ex[sel]['outer_index'], name)
            rgba = bw._read_authored_png(Path(png), resolved.texture.width, resolved.texture.height)
            decoded = body(resolved, rgba)
            need = packed_size(resolved, decoded)
            row = dict(selector=sel, slot=name, png=png, stored_size=resolved.chunk.stored_size, packed_bytes=need, fits=need <= resolved.chunk.stored_size - 8)
            print(sel, name, 'stored', row['stored_size'], 'needs', need, 'FITS' if row['fits'] else 'NO FIT', flush=True)
            out.append(row)
            if not measure and row['fits']:
                span, info = fill.rebuild_fixed_span_filled(resolved.span, decoded, encoder='optimal')
                assert len(span) == len(resolved.span) and span[:32] == resolved.span[:32]
                assert decode_chunk(span, parse_chunks(span)[0])[0] == decoded
                plans.append((resolved, span, row))
if not measure:
    with bw._Image.open(dst, writable=True) as target:
        for resolved, span, row in plans:
            target.write_segments(resolved.span_segments, span)
            assert target.read_segments(resolved.span_segments) == span
            row['written_sha256'] = hashlib.sha256(span).hexdigest()
    json.dump(out, open(dst.with_suffix('.bump_receipt.json'), 'w'), indent=1)
    print('written', len(plans), 'spans')
