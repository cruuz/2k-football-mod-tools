"""Survey: how much of each team mark stands out from that team's own wing tint.

A mark drawn in its team's primary on a wing tinted with the same primary nearly
vanishes; that was the Giants and Rams problem this job fixed from broadcast
evidence. This lists, for all 32 marks, the share of opaque mark texels whose
contrast against the team's wing tint is at least 3:1 (WCAG relative luminance),
lowest first. It changes nothing: other teams need their own broadcast evidence
before any recolour. Output: reports/b76_s12/mark_contrast.json.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def luminance(rgb):
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c @ np.array([0.2126, 0.7152, 0.0722])


def main():
    import sys
    sys.path[:0] = [str(ROOT)]
    from mod_editor.core.nfl2k5_scorebug_assets import TEAM_FILES
    accents = json.loads((ROOT / 'data/nfl2k5_scorebug_sprite/team_accents.json').read_text())['teams']
    rows = []
    for team, stem in sorted(TEAM_FILES.items()):
        mark = np.asarray(Image.open(ROOT / 'data/nfl2k5_scorebug_mnf/logos' / (stem + '.png')).convert('RGBA'))
        ink = mark[..., :3][mark[..., 3] > 128].astype(np.float64)
        wing = [int(accents[team]['wing'][i:i + 2], 16) for i in (1, 3, 5)]
        lw = luminance(wing)
        li = luminance(ink)
        ratio = (np.maximum(li, lw) + 0.05) / (np.minimum(li, lw) + 0.05)
        rows.append(dict(team=team, wing=accents[team]['wing'],
                         mark_median_rgb=[int(v) for v in np.median(ink, axis=0)],
                         median_contrast=round(float(np.median(ratio)), 2),
                         share_at_least_3_to_1=round(float((ratio >= 3).mean()), 3)))
    rows.sort(key=lambda r: r['share_at_least_3_to_1'])
    (OUT / 'mark_contrast.json').write_text(json.dumps(dict(
        method='Opaque mark texels (alpha > 128) against the team wing tint, WCAG relative luminance contrast',
        note='Survey only. No mark other than NYG and LAR was changed; the others need broadcast evidence first.',
        rows=rows), indent=1) + '\n', encoding='utf-8', newline='\n')
    for r in rows:
        print('%-4s %s share>=3:1 %.3f median %.2f' % (r['team'], r['wing'], r['share_at_least_3_to_1'], r['median_contrast']))


if __name__ == '__main__':
    main()
