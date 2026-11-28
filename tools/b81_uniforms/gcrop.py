#!/usr/bin/env python3
"""gcrop.py OUT.png [SCALE] RUN:G:X:Y:W:H ... : crops of emulator frames side by side (coordinates in the 1280x720 frame)."""
import sys, glob
from PIL import Image, ImageDraw
out = sys.argv[1]; args = sys.argv[2:]; scale = 1.0
if args and ':' not in args[0]: scale = float(args.pop(0))
E = '/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/emu/emu/'
ims = []
for a in args:
    run, g, x, y, w, h = a.split(':'); x, y, w, h = map(int, (x, y, w, h))
    f = glob.glob(f'{E}{run}/shots/*_{run}_g{int(g):03d}.png')[0]
    im = Image.open(f).convert('RGB').crop((x, y, x + w, y + h))
    if scale != 1: im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    ImageDraw.Draw(im).text((4, 3), f'{run} g{int(g):03d}', fill=(255, 255, 0))
    ims.append(im)
W = sum(i.width for i in ims) + 6 * (len(ims) - 1); H = max(i.height for i in ims)
sheet = Image.new('RGB', (W, H), (0, 0, 0)); x = 0
for i in ims: sheet.paste(i, (x, 0)); x += i.width + 6
sheet.save(out); print(out, sheet.size)
