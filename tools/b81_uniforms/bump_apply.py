#!/usr/bin/env python3
"""Put prototype relief maps into a COPY of a disc (the Studio's own fixed-span bump writer; only the exact spans change).
bump_apply.py SOURCE_DISC TARGET_COPY SELECTOR=bump_jersey.png[,bump_sleeve.png] ..."""
import sys, json, hashlib
from pathlib import Path
WT = Path('/home/noah/2k-worktrees/b81-uniforms'); sys.path[:0] = [str(WT), str(WT / 'tools')]
from mod_editor.core import nfl2k5_bump_texture_writer as bw
from PIL import Image
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
ex = {s['selector']: s for s in json.load(open('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/work/v09/export.json'))['sets']}
out = []
for spec in sys.argv[3:]:
    sel, files = spec.split('=')
    for name, png in zip(('bump_jersey', 'bump_sleeve'), files.split(',')):
        if not png: continue
        r = bw.import_bump(src, dst, ex[sel]['outer_index'], name, png)
        rgba = Image.open(png).convert('RGBA').tobytes()
        v = bw.verify_write(dst, ex[sel]['outer_index'], name, rgba)
        keep = {k: r.get(k) for k in ('logical_name', 'chunk_name', 'changed_byte_count', 'stored_size', 'compressed_size', 'span_offset') if k in r}
        out.append(dict(selector=sel, slot=name, png=png, png_sha256=hashlib.sha256(Path(png).read_bytes()).hexdigest(), result=keep,
                        verify={k: v.get(k) for k in list(v)[:8]}))
        print(sel, name, keep, {k: v.get(k) for k in list(v)[:6]}, flush=True)
json.dump(out, open(dst.with_suffix('.bump_receipt.json'), 'w'), indent=1, default=str)
