#!/usr/bin/env python3
"""ESPN frame_012001 above, the current sprite bar below, at the same on-screen size.

  python3 make_compare.py <preview_stem_dir> <stem> <out.png>
Uses the preview JSON's display.quads boxes, so the crop is the compiler's own mapping.
"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw

prev, stem, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
FRAME = Path('/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg')
BAR = (437, 930, 1478, 1060)
W, H = BAR[2] - BAR[0], BAR[3] - BAR[1]

rows = [('ESPN frame_012001 (1920x1080)', Image.open(FRAME).convert('RGB').crop(BAR))]
for aspect in ('43', '169'):
    meta = json.loads((prev / f'{stem}_{aspect}.json').read_text())
    disp = meta['display']
    im = Image.open(disp['path']).convert('RGB')
    q = disp['quads']
    left, right = q['body_left'][0], q['body_right'][2]
    top = q['body_left'][1] - (BAR[1] - 942) * (q['body_left'][3] - q['body_left'][1]) / 110
    bottom = top + (BAR[3] - BAR[1]) * (q['body_left'][3] - q['body_left'][1]) / 110
    crop = im.crop((int(round(left)), int(round(top)), int(round(right)), int(round(bottom))))
    rows.append((f"sprite scorebug, beta 71.1 code, {disp['aspect']} display model ({disp['size'][0]}x{disp['size'][1]})",
                 crop.resize((W, H), Image.Resampling.LANCZOS)))

sheet = Image.new('RGB', (W, (H + 18) * len(rows)), (16, 16, 16))
d = ImageDraw.Draw(sheet)
for i, (label, im) in enumerate(rows):
    sheet.paste(im, (0, i * (H + 18) + 18))
    d.text((6, i * (H + 18) + 4), label, fill=(255, 220, 0))
sheet.save(out)
print(out, sheet.size)
