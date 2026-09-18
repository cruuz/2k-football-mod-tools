#!/usr/bin/env python3
"""Region-by-region zoom: ESPN frame_012001 vs the beta 71.1 sprite render.

  python3 make_detail_sheet.py <preview_dir> <stem> <out.png>
"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw

prev, stem, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
FRAME = Path('/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg')
REGIONS = [('plate + capsule', (830, 936, 1092, 1050), 3),
           ('away wing + logo', (430, 936, 700, 1058), 2),
           ('home wing + logo', (1220, 936, 1486, 1058), 2),
           ('top centre pointer', (930, 936, 990, 962), 8)]

espn = Image.open(FRAME).convert('RGB')
metas = {}
for aspect in ('43', '169'):
    meta = json.loads((prev / f'{stem}_{aspect}.json').read_text())['display']
    im = Image.open(meta['path']).convert('RGB')
    q = meta['quads']
    sx = (q['body_right'][2] - q['body_left'][0]) / (1478 - 437)
    ox = q['body_left'][0] - 437 * sx
    sy = (q['body_left'][3] - q['body_left'][1]) / (1052 - 942)
    oy = q['body_left'][1] - 942 * sy
    metas[aspect] = (im, sx, ox, sy, oy, meta['aspect'])

tiles = []
for name, box, zoom in REGIONS:
    w, h = (box[2] - box[0]) * zoom, (box[3] - box[1]) * zoom
    row = [('ESPN ' + name, espn.crop(box).resize((w, h), Image.Resampling.NEAREST))]
    for aspect in ('43', '169'):
        im, sx, ox, sy, oy, label = metas[aspect]
        b = (int(round(box[0]*sx+ox)), int(round(box[1]*sy+oy)), int(round(box[2]*sx+ox)), int(round(box[3]*sy+oy)))
        row.append((f'sprite {label} ' + name, im.crop(b).resize((w, h), Image.Resampling.NEAREST)))
    tiles.append(row)

width = max(sum(im.width for _, im in row) + 12 * len(row) for row in tiles)
height = sum(row[0][1].height + 22 for row in tiles) + 12
sheet = Image.new('RGB', (width, height), (16, 16, 16))
d = ImageDraw.Draw(sheet)
y = 6
for row in tiles:
    x = 6
    for label, im in row:
        d.text((x, y), label, fill=(255, 220, 0))
        sheet.paste(im, (x, y + 14))
        x += im.width + 12
    y += row[0][1].height + 22
sheet.save(out)
print(out, sheet.size)
