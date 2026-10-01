"""vb3 D1 (2026-09-23): re-measure the two ESPN watermark masks with the ESPN logo's top slabs kept.

Noah's recording of 2026-09-23 [v1 0:46, v2 9:48]: "the ESPN logo in the top right's cut off". The watermark's
"espn" letters showed only their lower part. The ESPN logo cuts every letter with a thin horizontal line, so each
letter is two connected pieces: a top slab 7 to 8 px tall and the rest below the line. reports/b72_s9/harvest.py
kept only connected components at least 10 px tall (``h>=10 and area>=18``), so it dropped the three top slabs
in both broadcasts and the masks it wrote (watermark_mnf.png, watermark_nfl.png) carry the lower part only.

This script re-runs exactly that measurement on the same recorded crops (harvest.json names every source file),
with one change to the component filter: a smaller component is also kept when it sits directly on top of a kept
letter (sharing its columns, across a gap of at most 4 px), which is where the logo's top slabs sit. With
``--check-retail`` it first proves that the unchanged filter reproduces the shipped masks byte for byte.

Inputs are the user's broadcast reference crops (never distributed); outputs are the two coverage masks.
Usage: python3 reports/vb3_d1/rewatermark.py [--check-retail] [--write]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
HARVEST = ROOT / 'reports/b72_s9'
BASES = {'mnf': Path('/media/noah/Storage/Broadcast refs/espn-2026-broncos-chiefs-full'),
         'nfl': Path('/media/noah/Storage/Broadcast refs/espn-2025-raiders-texans')}


def letterforms(stats):
    """harvest.py's rule: connected static letterforms at least 10 px tall with 18 px of area."""
    return {i for i, (x, y, w, h, area) in enumerate(stats[1:], 1) if h >= 10 and area >= 18}


def with_slabs(stats, kept):
    """The logo's top slabs: area >= 18, sitting on top of a kept letter (sharing its columns) across a cut line
    of at most 4 px. The ESPN logo's cut line is 2 to 3 px in both broadcasts."""
    extra = set()
    for i, (x, y, w, h, area) in enumerate(stats[1:], 1):
        if i in kept or area < 18:
            continue
        for k in kept:
            kx, ky, kw, kh = stats[k][:4]
            if x < kx + kw and kx < x + w and 0 <= ky - (y + h) <= 4:
                extra.add(i)
                break
    return kept | extra


def measure(tag, rule):
    record = json.loads((HARVEST / 'harvest.json').read_text())['glyphs']['watermark_' + tag]
    arrays = [np.asarray(Image.open(BASES[tag] / 'crops' / name).convert('RGB')) for name in record['source_files']]
    low = np.percentile(arrays, 5, axis=0)
    grey = low.mean(2)
    mask = grey > 80
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype('uint8'))
    kept = letterforms(stats)
    if rule == 'slabs':
        kept = with_slabs(stats, kept)
    valid = np.isin(labels, sorted(kept))
    ys, xs = np.where(valid)
    box = [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
    x, y, r, b = box
    alpha = np.clip((grey[y:b, x:r] - 8) / (.72 * 255), 0, 1)
    expanded = cv2.dilate(valid.astype('uint8'), np.ones((3, 3), np.uint8))
    alpha *= expanded[y:b, x:r]
    mark = Image.new('RGBA', (r - x, b - y), 'white')
    mark.putalpha(Image.fromarray(np.rint(alpha * 255).astype('uint8')))
    components = [dict(index=i, box=[int(v) for v in stats[i][:4]], area=int(stats[i][4]), kept=i in kept)
                  for i in range(1, n)]
    return mark, dict(box_in_crop=box, samples=len(arrays), components=components)


def png_bytes(image):
    import io
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-retail', action='store_true', help='prove the unchanged rule reproduces the shipped masks')
    parser.add_argument('--write', action='store_true', help='write the corrected masks over reports/b72_s9/watermark_*.png')
    parser.add_argument('--receipt', type=Path, default=Path(__file__).resolve().parent / 'rewatermark.json')
    args = parser.parse_args(argv)
    receipt = {}
    for tag in ('mnf', 'nfl'):
        shipped = HARVEST / f'watermark_{tag}.png'
        row = {}
        if args.check_retail:
            old, _ = measure(tag, 'retail')
            same = np.array_equal(np.asarray(old), np.asarray(Image.open(shipped).convert('RGBA')))
            row['retail_rule_reproduces_shipped_mask'] = bool(same)
            if not same:
                raise SystemExit(f'{tag}: the unchanged rule does not reproduce {shipped.name}')
        new, info = measure(tag, 'slabs')
        row.update(info)
        row['size'] = list(new.size)
        row['sha256'] = hashlib.sha256(png_bytes(new)).hexdigest()
        if args.write:
            new.save(shipped)
            row['written'] = str(shipped.relative_to(ROOT))
        receipt[tag] = row
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: {kk: v[kk] for kk in ('box_in_crop', 'size') } | {'slabs_kept': sum(c['kept'] for c in v['components'])} for k, v in receipt.items()}, indent=1))


if __name__ == '__main__':
    main()
