#!/usr/bin/env python3
"""mk_after.py DECODED_DIR OUT_ROOT : per kit named in DECODED_DIR (<SEL>_<texture>.png, the compiled level-0 pictures of the
uniform pass), build OUT_ROOT/<SEL>/ = the v0.9 decoded kit folder with those textures replaced (links for the rest)."""
import sys, os, shutil
from pathlib import Path
V09 = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/work/v09/uniforms')
def fname(tex):
    if tex == 'jersey00': return 'torso.png'
    if tex == 'pants00': return 'pants.png'
    if tex == 'sleeve00': return 'sleeve.png'
    if tex == 'socks00': return 'socks00.png'
    for p, n in (('hn', 'digit_helmet'), ('an', 'digit_arm'), ('', 'digit_jersey')):
        d = tex[len(p):]
        if tex.startswith(p) and d.isdigit(): return f'{n}_{int(d) - 48}.png'
    raise ValueError(tex)
dec, out = Path(sys.argv[1]), Path(sys.argv[2])
kits = {}
for p in sorted(dec.glob('*_*.png')):
    sel, tex = p.stem.split('_', 1); kits.setdefault(sel, {})[fname(tex)] = p
for sel, over in kits.items():
    d = out / sel
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    for f in (V09 / sel).iterdir():
        if f.name in over: shutil.copy(over[f.name], d / f.name)
        else: os.symlink(f, d / f.name)
    print(sel, sorted(over))
