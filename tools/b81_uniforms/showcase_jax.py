#!/usr/bin/env python3
"""The Jaguars name plate image: the letters the game stores, set as a name, before and after the nameplate pass applies."""
from PIL import Image, ImageDraw, ImageFont
import numpy as np
U = '/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/'
F = lambda n: ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', n)
def word(names_png, text, bg, scale=5):
    a = Image.open(names_png).convert('RGBA'); arr = np.asarray(a); parts = []
    for ch in text:
        x0 = 96 + 32 * (ord(ch) - 65); cols = np.flatnonzero(arr[:, x0:x0 + 32, 3].max(0) > 40)
        parts.append(a.crop((x0 + cols.min(), 0, x0 + cols.max() + 1, 32)))
    W = sum(p.width for p in parts) + 2 * (len(parts) - 1) + 16
    im = Image.new('RGBA', (W, 40), bg + (255,)); x = 8
    for p in parts: im.alpha_composite(p, (x, 4)); x += p.width + 2
    return im.convert('RGB').resize((W * scale, 40 * scale), Image.NEAREST)
teal, white = (4, 124, 140), (250, 250, 250)
rows = [('BEFORE (released v0.9): home', word(U + 'work/v09/uniforms/12H0/names.png', 'LAWRENCE', teal)), ('AFTER: home', word(U + 'work/jaxfix/uniforms/12H0/names.png', 'LAWRENCE', teal)),
        ('BEFORE (released v0.9): road and Bold City', word(U + 'work/v09/uniforms/12A0/names.png', 'BROWN', white)), ('AFTER: road and Bold City', word(U + 'work/jaxfix/uniforms/12A0/names.png', 'BROWN', white))]
r = Image.open('/home/noah/Projects/2K5-8 Editors/refs/uniforms_2026/JAX/2026-10-04_CIN_primary-away/helmet_back_0330.jpg').crop((520, 380, 1140, 760))
W = 1500; H = 142 + r.height + 16 + sum(im.height + 44 for _, im in rows) + 16
s = Image.new('RGB', (W, H), (24, 24, 28)); d = ImageDraw.Draw(s)
d.text((16, 12), 'Jaguars name plates (12H0, 12A0, 12H6): letters with open counters', fill=(255, 255, 255), font=F(32))
for i, line in enumerate(('Noah asked for readable Jaguars names on 10/22. That fix never reached a build: its step skipped itself every time (it compared',
                          "'12H0' with '12H0.IFF'). One-line repair, with a test. These are the letters the game stores, set as a name (5x).",
                          'Real 2026 road plate below (reference only). Still open: the real road letters are lighter than the 10/22 design; say if you want them thinned.')):
    d.text((16, 58 + 26 * i), line, fill=(210, 214, 222), font=F(17))
y = 142; s.paste(r, (16, y)); y += r.height + 8
for label, im in rows:
    d.text((16, y + 10), label, fill=(255, 214, 90), font=F(20)); y += 44; s.paste(im, (16, y)); y += im.height
s.save(U + 'showcase/JAX_nameplates_before_after.png'); print(s.size)
