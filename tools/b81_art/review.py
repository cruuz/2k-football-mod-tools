"""Review sheets for the coordinator (not for Noah): the 32 home style 0 AFTER logo close-ups, eight per sheet (4 by 2),
and one sheet of the eight alternates or throwbacks the detector still scores worst after the repair."""
import sys, csv; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, make_cards, final
from PIL import Image, ImageDraw
OUT = C.WORK.parent / 'review'
CROP = (20, 140, 40, 210)
def cell(name, label):
    p = make_cards.FILES / f'b81art_{name}.png'
    a = C.quantize(C.load(p)) if p.exists() else final.card(name)
    y0, y1, x0, x1 = CROP
    img = C.up(C.over(a)[y0:y1, x0:x1], 2)
    pad = np.full((img.shape[0] + 20, 360, 3), 20, np.uint8); pad[20:, 10:10 + img.shape[1]] = img
    im = Image.fromarray(pad); ImageDraw.Draw(im).text((10, 4), label, fill=(255, 255, 255))
    return np.asarray(im)
def sheet(cells, path):
    rows = [np.concatenate(cells[i:i + 4], axis=1) for i in range(0, len(cells), 4)]
    W = max(r.shape[1] for r in rows)
    Image.fromarray(np.concatenate([np.pad(r, ((0, 0), (0, W - r.shape[1]), (0, 0))) for r in rows], axis=0)).save(path)
if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    codes = sorted(C.TEAMS, key=lambda c: C.TEAMS[c])
    for i in range(4):
        sheet([cell(f'helm_h{c}_0_256', C.TEAMS[c]) for c in codes[8 * i:8 * i + 8]], OUT / f'after_home_0{i + 1}.png')
    rows = list(csv.DictReader(open(C.WORK.parent / 'out' / 'detector_textures.csv')))
    score = {}
    for r in rows:
        tex = r['texture']; fam, sel = tex.split('_')
        if fam != 'helmet02' or sel[2] != 'H' or sel[3:] == '0': continue
        s = sum(int(float(r[k])) for k in r if k.endswith('_after') and r[k] not in ('', None, 'None'))
        score[sel] = s
    worst = ['02H3'] + [s for s in sorted(score, key=lambda s: -score[s]) if s != '02H3'][:7]     # the redrawn dark alternate always shows
    sheet([cell(f'helm_h{s[:2]}_{s[3:]}_256', f'{C.TEAMS[s[:2]]} style {s[3:]}  (detector residue {score[s]})') for s in worst], OUT / 'worst_alternates.png')
    print('worst', [(C.TEAMS[s[:2]], s[3:], score[s]) for s in worst])
