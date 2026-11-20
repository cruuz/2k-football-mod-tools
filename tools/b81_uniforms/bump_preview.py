#!/usr/bin/env python3
"""Render a kit with relief maps on the player model (preview only; the emulator shows the game's own shading).
bump_preview.py OUT LABEL=KITDIR:BUMP_JERSEY.png[:BUMP_SLEEVE.png]:STRENGTH ..."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import render_kits as R
R.SCRIPT = Path(__file__).parent / 'u1_blender_bump.py'
VIEWS = [("bf", 0, 6, 2.3, [0, 0, 0.42], [700, 660]), ("bq", 40, 10, 2.3, [0, 0, 0.42], [700, 660]),
         ("bb", 180, 6, 2.3, [0, 0, 0.42], [700, 660])]
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True); items = []
for spec in sys.argv[2:]:
    label, rest = spec.split('=', 1); f = rest.split(':')
    kit, bj = f[0], f[1]; bs = f[2] if len(f) > 3 else ''; strength = float(f[-1])
    bump = {}
    if bj: bump['UNIF_jersey'] = bj
    if bs: bump['UNIF_sleeve'] = bs
    it = R.item(label, Path(kit), '#808080', 8, out, VIEWS, bump or None, strength)
    it['light'] = {"ambient": 0.45, "sun": 3.2, "sun_cam": [35, -50], "rim": 0.6, "cloth_roughness": 0.45, "cloth_specular": 0.5}
    for v in it['views']: v['samples'] = 32
    items.append(it)
print('seconds', round(R.run(items, out, 'bp')))
