#!/usr/bin/env python3
"""One before/after image per kit for Noah: reference frame crops (this season's highlights, reference only), the kit
as the released build holds it, and the corrected kit, rendered on the game's player model from the same cameras.
showcase.py OUT.png "TITLE" --ref FRAME:X:Y:W:H ... --before RENDERDIR:SEL --after RENDERDIR:SEL [--views front,back,left,tq]
            [--note "text"] ... [--zoom view:x:y:w:h ...]  (zoom boxes are in render pixels of that view; shown under the rows)"""
import sys, argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
REFS = Path('/home/noah/Projects/2K5-8 Editors/refs/uniforms_2026')
def font(size):
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'):
        if Path(p).exists(): return ImageFont.truetype(p, size)
    return ImageFont.load_default()
def flat(p, bg=(58, 62, 74)):
    im = Image.open(p).convert('RGBA'); b = Image.new('RGBA', im.size, bg + (255,)); b.alpha_composite(im); return b.convert('RGB')
def fit_h(im, h): return im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)
def row(ims, h, gap=8, bg=(24, 24, 28)):
    ims = [fit_h(i, h) for i in ims]; W = sum(i.width for i in ims) + gap * (len(ims) - 1)
    out = Image.new('RGB', (W, h), bg); x = 0
    for i in ims: out.paste(i, (x, 0)); x += i.width + gap
    return out
p = argparse.ArgumentParser(); p.add_argument('out'); p.add_argument('title')
p.add_argument('--ref', action='append', default=[]); p.add_argument('--before', required=True); p.add_argument('--after', required=True)
p.add_argument('--views', default='front,back,left,tq'); p.add_argument('--note', action='append', default=[])
p.add_argument('--zoom', action='append', default=[]); p.add_argument('--height', type=int, default=560)
a = p.parse_args()
refs = []
for r in a.ref:
    f = r.split(':'); path = Path(f[0]) if f[0].startswith('/') else REFS / f[0]
    im = Image.open(path).convert('RGB')
    if len(f) >= 5: x, y, w, h = map(int, f[1:5]); im = im.crop((x, y, x + w, y + h))
    refs.append(im)
views = a.views.split(',')
def renders(spec):
    d, sel = spec.rsplit(':', 1); return [flat(Path(d) / f'{sel}_{v}.png') for v in views]
def zooms(spec):
    d, sel = spec.rsplit(':', 1); out = []
    for z in a.zoom:
        v, x, y, w, h = z.split(':'); x, y, w, h = map(int, (x, y, w, h))
        out.append(flat(Path(d) / f'{sel}_{v}.png').crop((x, y, x + w, y + h)))
    return out
H = a.height
rows = [('REAL: 2026 game highlights (reference only)', row(refs, H) if refs else None),
        ('BEFORE: the released game (v0.9)', row(renders(a.before) + zooms(a.before), H)),
        ('AFTER: this pass', row(renders(a.after) + zooms(a.after), H))]
rows = [r for r in rows if r[1] is not None]
W = max(r[1].width for r in rows) + 32
f1, f2, f3 = font(34), font(22), font(18)
notes_h = 28 * len(a.note) + (12 if a.note else 0)
total = 64 + notes_h + sum(r[1].height + 44 for r in rows) + 16
sheet = Image.new('RGB', (W, total), (24, 24, 28)); d = ImageDraw.Draw(sheet)
d.text((16, 12), a.title, fill=(255, 255, 255), font=f1); y = 64
for n in a.note:
    d.text((16, y), n, fill=(210, 214, 222), font=f3); y += 28
y += 12 if a.note else 0
for label, im in rows:
    d.text((16, y + 8), label, fill=(255, 214, 90), font=f2); y += 44
    sheet.paste(im, (16, y)); y += im.height
sheet.save(a.out); print(a.out, sheet.size)
