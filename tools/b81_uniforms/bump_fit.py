#!/usr/bin/env python3
"""bump_fit.py DISC SELECTOR SLOT PNG [...more SELECTOR SLOT PNG] : would this relief map fit that kit's fixed span? (read only)"""
import sys, json
from pathlib import Path
WT = Path('/home/noah/2k-worktrees/b81-uniforms'); sys.path[:0] = [str(WT), str(WT / 'tools')]
from mod_editor.core import nfl2k5_bump_texture_writer as bw
from nfl_txtr import rebuild_compressed_chunk_fixed_span
ex = {s['selector']: s for s in json.load(open('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/work/v09/export.json'))['sets']}
disc = Path(sys.argv[1]); a = sys.argv[2:]
with bw._Image.open(disc, writable=False) as image:
    for sel, slot, png in zip(a[0::3], a[1::3], a[2::3]):
        resolved, _i, _e = bw._resolve_bump(image, ex[sel]['outer_index'], slot)
        rgba = bw._read_authored_png(Path(png), resolved.texture.width, resolved.texture.height)
        try:
            span, decoded, stats = bw._build_replacement_span(resolved, rgba)
            print(sel, slot, 'FITS stored', resolved.chunk.stored_size, {k: v for k, v in stats.items() if 'size' in k or 'bytes' in k or 'compress' in k})
        except Exception as exc:
            print(sel, slot, 'NO FIT stored', resolved.chunk.stored_size, str(exc)[:160])
