#!/usr/bin/env python3
"""Why '1st & 10' is not readable: the four labels at the size a player actually sees.

  python3 make_size_proof.py <preview_dir> <out.png>

Row 1  retail ESPN NFL 2K5's own down label, cropped from an xemu window (1132x670)
Row 2  the beta 71.1 sprite label, 4:3, the same 640x448 HUD scaled the same way
Row 3  the beta 71.1 sprite label, 16:9
Row 4  the same string at cap height 28 source px instead of 23, 16:9 (the proposal)
Row 5  ESPN's own broadcast label at 1920x1080, scaled to the same on-screen height
"""
import json, math, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

prev, out = Path(sys.argv[1]), Path(sys.argv[2])
DAY = Path('/home/noah/Desktop/2K5-8 Editors/beta71_evidence/day/ksnip_20260915-154929.png')
FRAME = Path('/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg')
FONT = Path('/usr/share/fonts/truetype/noto/NotoSansDisplay-Bold.ttf')
WINDOW = (1132, 670)                     # Noah's xemu window, fit = scale
SXW, SYW = WINDOW[0] / 640, WINDOW[1] / 480
ZOOM = 3                                 # the whole sheet is magnified equally


def from_preview(stem, aspect, pad=3):
    meta = json.loads((prev / f'{stem}_{aspect}.json').read_text())
    im = Image.open(prev / f'{stem}_{aspect}.png').convert('RGB')
    q = meta['quads']
    xs = [q[k][0] for k in q if k.startswith('down:')] + [q[k][2] for k in q if k.startswith('down:')]
    ys = [q[k][1] for k in q if k.startswith('down:')] + [q[k][3] for k in q if k.startswith('down:')]
    box = (int(min(xs)) - pad, int(min(ys)) - pad, int(max(xs)) + pad + 1, int(max(ys)) + pad + 1)
    crop = im.crop(box)
    return crop.resize((int(round(crop.width * SXW)), int(round(crop.height * SYW))), Image.Resampling.BILINEAR)


def bilinear(a, w, h):
    ih, iw = a.shape
    o = np.zeros((h, w))
    for y in range(h):
        ty = (y + .5) / h * ih - .5; iy = math.floor(ty); fy = ty - iy
        for x in range(w):
            tx = (x + .5) / w * iw - .5; ix = math.floor(tx); fx = tx - ix
            s = 0.
            for dx, dy, wt in ((0,0,(1-fx)*(1-fy)), (1,0,fx*(1-fy)), (0,1,(1-fx)*fy), (1,1,fx*fy)):
                s += a[min(ih-1, max(0, iy+dy)), min(iw-1, max(0, ix+dx))] * wt
            o[y, x] = s
    return o


def proposal(cap=28, xs=1/3.):
    """Cells pre-fit to the HUD footprint, cap height `cap` source px, widescreen raster."""
    toks = [('1', 16, 18), ('st', 26, 28), (' ', 0, 11), ('&', 19, 21), (' ', 0, 11), ('1', 16, 18), ('0', 16, 18)]
    k = cap / 23.
    total = sum(a for _, _, a in toks) - (toks[-1][2] - toks[-1][1])
    W = int(round(total * k * xs)) + 6
    H = int(round(cap * 448 / 1080)) + 6
    canvas = np.zeros((H, W))
    pen = 3.
    for t, w_src, adv in toks:
        if w_src:
            f = ImageFont.truetype(str(FONT), int(cap * 6))
            b = f.getbbox(t)
            g = Image.new('L', (b[2]-b[0], b[3]-b[1]))
            ImageDraw.Draw(g).text((-b[0], -b[1]), t, font=f, fill=255)
            g = g.crop(g.getbbox())
            gw = max(1, int(round(w_src * k * xs))); gh = max(1, int(round(cap * 448 / 1080)))
            cell = np.asarray(g.resize((gw, gh), Image.Resampling.BOX), float) / 255.
            x0 = int(round(pen))
            canvas[3:3+gh, x0:x0+gw] = np.maximum(canvas[3:3+gh, x0:x0+gw], cell)
        pen += adv * k * xs
    plate = np.array([175, 11, 58], float)
    rgb = plate[None, None, :] * (1 - canvas[..., None]) + 255 * canvas[..., None]
    im = Image.fromarray(rgb.astype('uint8'), 'RGB')
    return im.resize((int(round(im.width * SXW)), int(round(im.height * SYW))), Image.Resampling.BILINEAR)


rows = [('retail ESPN NFL 2K5 (cap 11.5 HUD px)', Image.open(DAY).convert('RGB').crop((520, 590, 620, 616))),
        ('sprite beta 71.1, 4:3 (cap 9.5, glyph 7.1 px)', from_preview('b72_first10', '43')),
        ('sprite beta 71.1, 16:9 (cap 9.5, glyph 5.3 px)', from_preview('b72_first10', '169')),
        ('proposal: cap 28 src = 11.6 HUD px, prefit cells, 16:9', proposal(28)),
        ('ESPN broadcast 1080p, scaled to the same height', None)]

espn = Image.open(FRAME).convert('RGB').crop((893, 950, 1026, 983))
h = rows[0][1].height * ZOOM
espn = espn.resize((int(espn.width * h / espn.height), h), Image.Resampling.LANCZOS)
rows[4] = (rows[4][0], espn)

tiles = []
for label, im in rows:
    tiles.append((label, im if im is espn else im.resize((im.width * ZOOM, im.height * ZOOM), Image.Resampling.NEAREST)))

W = max(im.width for _, im in tiles) + 20
H = sum(im.height + 22 for _, im in tiles) + 10
sheet = Image.new('RGB', (W, H), (18, 18, 18))
d = ImageDraw.Draw(sheet)
y = 6
for label, im in tiles:
    d.text((8, y), label, fill=(255, 220, 0))
    sheet.paste(im, (10, y + 14))
    y += im.height + 22
sheet.save(out)
print(out, sheet.size)
