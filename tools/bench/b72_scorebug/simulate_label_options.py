#!/usr/bin/env python3
"""What the down label would look like under four authoring options.

Read-only simulation of the game's sampler. Writes a contact sheet and prints JSON.
  python3 simulate_label_options.py <out_dir>

Option A  current: 16x23 texel cells, GPU minifies 2.25x (4:3) / 3.0x (16:9)
Option B  same size, cells pre-fit to the 4:3 HUD footprint (area filter)
Option C  cap height 23 -> 28 source px, cells pre-fit to the 16:9 HUD footprint
Option D  cap height 23 -> 30 source px, cells pre-fit to the 16:9 HUD footprint

Score: structural similarity to the ideal (the string area-filtered straight from a
6x master) plus stroke modulation. Higher is better; 1.0 is the ideal itself.
"""
import json, math, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
FONT = Path('/usr/share/fonts/truetype/noto/NotoSansDisplay-Bold.ttf')
Y_SCALE = 448 / 1080
RASTER_X = {'4:3': 640 / 1440, '16:9': 640 / 1920 * 32 / 27 * 27 / 32}   # = 1/3 after the patch
RASTER_X['16:9'] = 640 / 1920                                            # widescreen patch nets 1/3
TOKENS = [('1', 16, 18), ('st', 26, 28), (' ', 0, 11), ('&', 19, 21), (' ', 0, 11), ('1', 16, 18), ('0', 16, 18)]


def master(token, w, h, scale=6):
    """The author's rasteriser, tools/scorebug_sprite/author_default.py:60-65, at `scale`x."""
    f = ImageFont.truetype(str(FONT), h * 6)
    b = f.getbbox(token)
    im = Image.new('L', (b[2] - b[0], b[3] - b[1]))
    ImageDraw.Draw(im).text((-b[0], -b[1]), token, font=f, fill=255)
    im = im.crop(im.getbbox())
    return im.resize((max(1, w * scale), max(1, h * scale)), Image.Resampling.LANCZOS)


def bilinear(a, out_w, out_h):
    h, w = a.shape
    out = np.zeros((out_h, out_w))
    for y in range(out_h):
        ty = (y + .5) / out_h * h - .5; iy = math.floor(ty); fy = ty - iy
        for x in range(out_w):
            tx = (x + .5) / out_w * w - .5; ix = math.floor(tx); fx = tx - ix
            s = 0.
            for dx, dy, wt in ((0,0,(1-fx)*(1-fy)), (1,0,fx*(1-fy)), (0,1,(1-fx)*fy), (1,1,fx*fy)):
                s += a[min(h-1, max(0, iy+dy)), min(w-1, max(0, ix+dx))] * wt
            out[y, x] = s
    return out


def draw_string(cell_of, cap_src, aspect, ideal=False):
    """Lay the string out exactly as tools/scorebug_sprite runtime.c:121-132 does."""
    xs = RASTER_X[aspect]
    total = sum(a for _, _, a in TOKENS) - (TOKENS[-1][2] - TOKENS[-1][1])
    width_px = total * xs * cap_src / 23
    height_px = cap_src * Y_SCALE
    canvas = np.zeros((int(round(height_px)) + 2, int(round(width_px)) + 4))
    pen = 0.
    for token, w_src, adv_src in TOKENS:
        if w_src:
            w = w_src * cap_src / 23 * xs
            h = cap_src * Y_SCALE
            cell = cell_of(token, w_src, aspect, cap_src)
            g = (np.asarray(cell.resize((int(round(w * 8)), int(round(h * 8))), Image.Resampling.BOX), float) / 255.
                 if ideal else bilinear(np.asarray(cell, float) / 255., max(1, int(round(w))), max(1, int(round(h)))))
            if ideal:
                g = np.asarray(Image.fromarray((g * 255).astype('uint8')).resize(
                    (max(1, int(round(w))), max(1, int(round(h)))), Image.Resampling.BOX), float) / 255.
            x0 = int(round(pen)); y0 = 1
            canvas[y0:y0 + g.shape[0], x0:x0 + g.shape[1]] = np.maximum(
                canvas[y0:y0 + g.shape[0], x0:x0 + g.shape[1]], g[:canvas.shape[0] - y0, :canvas.shape[1] - x0])
        pen += adv_src * cap_src / 23 * xs
    return canvas


def cells_current(token, w_src, aspect, cap_src):
    return master(token, w_src, 23, 1)                       # 16x23 etc, as shipped


def cells_prefit_43(token, w_src, aspect, cap_src):
    w = max(1, int(round(w_src * RASTER_X['4:3'])))
    h = max(1, int(round(23 * Y_SCALE)))
    return master(token, w_src, 23, 8).resize((w, h), Image.Resampling.BOX)


def cells_prefit_169(cap):
    def inner(token, w_src, aspect, cap_src):
        w = max(1, int(round(w_src * cap / 23 * RASTER_X['16:9'])))
        h = max(1, int(round(cap * Y_SCALE)))
        return master(token, w_src, 23, 8).resize((w, h), Image.Resampling.BOX)
    return inner


def cells_ideal(token, w_src, aspect, cap_src):
    return master(token, w_src, 23, 8)


def score(sim, ideal):
    a, b = sim, ideal
    h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
    a = a[:h, :w]; b = b[:h, :w]
    if a.std() < 1e-6 or b.std() < 1e-6:
        return 0.
    return float(((a - a.mean()) * (b - b.mean())).mean() / (a.std() * b.std()))


report = {}
sheet_rows = []
options = [('A_current_16x23_gpu_minifies', cells_current, 23),
           ('B_prefit_cells_cap23', cells_prefit_43, 23),
           ('C_prefit_cells_cap28', cells_prefit_169(28), 28),
           ('D_prefit_cells_cap30', cells_prefit_169(30), 30)]
for aspect in ('4:3', '16:9'):
    ideal = draw_string(cells_ideal, 23, aspect, ideal=True)
    for name, fn, cap in options:
        sim = draw_string(fn, cap, aspect)
        ink = sim
        rows = ink.shape[0]
        report.setdefault(aspect, {})[name] = {
            'raster_px': [ink.shape[1], ink.shape[0]],
            'cap_height_hud_px': round(cap * Y_SCALE, 2),
            'structural_similarity_to_ideal': round(score(sim, ideal), 3),
            'mean_alpha': round(float(ink.mean()), 3),
            'peak_alpha': round(float(ink.max()), 3),
            'duty_cycle_above_half_peak': round(float((ink > ink.max() * .5).mean()), 3),
        }
        img = Image.fromarray((np.clip(ink, 0, 1) * 255).astype('uint8'), 'L')
        big = img.resize((img.width * 10, img.height * 10), Image.Resampling.NEAREST)
        sheet_rows.append((f'{aspect} {name}', big))

pad = 8
width = max(im.width for _, im in sheet_rows) + 260
height = sum(im.height + pad for _, im in sheet_rows) + pad
sheet = Image.new('RGB', (width, height), (140, 10, 45))
d = ImageDraw.Draw(sheet)
y = pad
for label, im in sheet_rows:
    sheet.paste(Image.merge('RGB', (im, im, im)), (250, y))
    d.text((8, y + im.height // 2 - 6), label, fill=(255, 255, 255))
    y += im.height + pad
sheet.save(OUT / 'label_options_contact_sheet.png')
report['contact_sheet'] = str(OUT / 'label_options_contact_sheet.png')
print(json.dumps(report, indent=1))
