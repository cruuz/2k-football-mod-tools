"""Crop the five rows of the ESPN Analytics '2-point breakeven' small multiples (Seth Walder, ESPN, 2022-01 / 2023-01 update).

Usage: python3 -I crop_espn2pt_rows.py nfl_cheat_sheet_1990x2153.jpg OUT_DIR

Writes one PNG per row of six panels (margins -15..-10, -9..-4, -3..+2, +3..+8, +9..+14; margin = score margin after the touchdown, before the try).
The dashed line is the 48% league conversion rate: a curve below it means go for two. The thresholds in build_sources_json.TWO_POINT were read by eye from
these crops and from the article text; an automatic curve extraction was tried and rejected (about 3 px of noise against curves that hug the line).
"""
import sys
from pathlib import Path

from PIL import Image

ROWS = [(215, 520), (578, 882), (938, 1244), (1300, 1606), (1662, 1968)]
LABELS = ["m15_m10", "m9_m4", "m3_p2", "p3_p8", "p9_p14"]
im = Image.open(sys.argv[1]).convert("RGB")
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
for (y0, y1), label in zip(ROWS, LABELS):
    im.crop((100, y0, 1990, y1)).save(out / f"row_{label}.png")
print("wrote", len(ROWS), "row crops to", out)
