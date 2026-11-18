"""One before/after image per team for Noah: left = the card as the released build shows it, right = the new card as the
game will store it (the Studio's own 256-colour compile), 3x."""
import sys, json; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, final, make_cards
from PIL import Image, ImageDraw
SHOW = C.WORK.parent / 'showcase'
def card_pair(name, crop, s=3):
    b = final.card(name)
    p = make_cards.FILES / f'b81art_{name}.png'
    a = C.quantize(C.load(p)) if p.exists() else b
    y0, y1, x0, x1 = crop
    return C.up(C.over(b)[y0:y1, x0:x1], s), C.up(C.over(a)[y0:y1, x0:x1], s)
def team(code):
    styles = sorted({int(n.split('_')[2]) for n in C.index() if n.split('_')[1][1:] == code})
    rows = []
    for style in styles:
        for fam, side, crop, label in (('helm', 'h', (0, 160, 0, 256), 'Team Select helmet, home'), ('helm', 'a', (0, 160, 0, 256), 'Team Select helmet, away'),
                                       ('unif', 'h', (96, 256, 0, 256), 'Team Select uniform card, home')):
            if style != 0 and (fam, side) != ('helm', 'h'): continue
            name = f'{fam}_{side}{code}_{style}_256'
            if not (make_cards.FILES / f'b81art_{name}.png').exists() and style != 0: continue
            b, a = card_pair(name, crop)
            row = C.hstack([b, a], gap=12, bg=(20, 20, 20))
            bar = np.zeros((22, row.shape[1], 3), np.uint8); bar[:] = (20, 20, 20)
            im = Image.fromarray(bar); d = ImageDraw.Draw(im)
            d.text((6, 4), f"{C.TEAMS[code]}  {label}  style {style}      BEFORE (v0.9 / v0.10 candidate)", fill=(255, 255, 255))
            d.text((b.shape[1] + 18, 4), "AFTER (beta 81 art cleanup)", fill=(120, 255, 120))
            rows += [np.asarray(im), row]
    if not rows: return None
    W = max(r.shape[1] for r in rows)
    img = np.concatenate([np.pad(r, ((0, 0), (0, W - r.shape[1]), (0, 0))) for r in rows], axis=0)
    SHOW.mkdir(exist_ok=True)
    out = SHOW / f'{C.TEAMS[code]}_before_after.png'
    Image.fromarray(img).save(out)
    return out
if __name__ == '__main__':
    for code in sys.argv[1:]:
        print(team(code))
