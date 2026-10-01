"""Before and after contact sheets at the 617-pixel player bar, beside the broadcast.

For each aspect (4:3 and 16:9) and each measured Giants at Rams state (q1 and q4)
the sheet stacks: the broadcast frame normalized by reports/b76_s12/player_scale.py's
own reference() (a small crop of read-only evidence, never the frame itself), the
beta 75.1 render (baseline_*.png) and the b76-s12 render (final_*.png). The
renders are the offline native HUD with the Lanczos display approximation; no
in-game result is shown or claimed.

Run after ``player_scale.py baseline`` and ``player_scale.py final``.
"""
from pathlib import Path
import json
import sys

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(OUT)]
import player_scale as P  # noqa: E402

CROP = (425, 930, 1495, 1060)
ROWS = (('broadcast', 'ESPN MNF 2026, Giants at Rams (normalized to the same 617-pixel bar)'),
        ('baseline', 'BEFORE: beta 75.1 sprite bar, offline native render'),
        ('final', 'AFTER: b76-s12 sprite bar, offline native render'))


def bar(image):
    return P.aligned(image).crop(P.box(CROP))


def main():
    receipts = []
    for aspect, label in (('43', '4:3'), ('169', '16:9')):
        tiles = []
        for name, (path, state) in P.CASES.items():
            bar_ref = P.reference(path).crop(P.box(CROP))
            for kind, caption in ROWS:
                if kind == 'broadcast':
                    tile = bar_ref
                else:
                    tile = bar(Image.open(OUT / f'{kind}_{name}_{aspect}.png').convert('RGB'))
                tiles.append((f'{name} | {caption}', tile))
            receipts.append(dict(aspect=label, state=name, reference=str(path.name),
                                 reference_bounds=P.REFERENCE_BOUNDS[path.name]))
        width = max(t.width for _, t in tiles) + 30
        height = 44 + sum(t.height + 26 for _, t in tiles) + 40
        sheet = Image.new('RGB', (width, height), '#252525')
        d = ImageDraw.Draw(sheet)
        d.text((15, 10), f'b76-s12 | NYG at LAR | {label} | 617-pixel player bars | open at 100 percent', fill='white')
        y = 44
        for caption, tile in tiles:
            d.text((15, y), caption, fill='#ffdb88' if 'AFTER' in caption else '#dddddd')
            sheet.paste(tile, (15, y + 18))
            y += tile.height + 26
        d.text((15, y + 4), 'The 4:3 rows reuse the 16:9 broadcast (no 4:3 broadcast exists). No in-game result is claimed.',
               fill='#bbbbbb')
        sheet.save(OUT / f'sheet_NYG_LAR_{aspect}.png', optimize=True)
    (OUT / 'sheet_receipts.json').write_text(json.dumps(receipts, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Wrote sheet_NYG_LAR_43.png and sheet_NYG_LAR_169.png')


if __name__ == '__main__':
    main()
