"""Cards that differ from a render of their own league-project helmet (art only the card has): pixels on the open shell
where the shipped card is far from the old render, outside the zones the cleanup already replaces."""
import sys, json; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, post, compose, final
from scipy import ndimage
def shell_interior(view, side):
    pid, u, v = compose.uv(view, side)
    full = ((pid == 0) | (pid == 1)).reshape(256, 4, 256, 4).all(axis=(1, 3))
    return ndimage.binary_erosion(full, iterations=1)
def measure(name):
    fam, code, side, style, res = C.parse(name)
    S = 'H' if side == 'home' else 'A'; sel = f'{code}{S}{style}'; view = 'helm' if fam == 'helm' else 'unif'
    old = compose.base_card(name); P = compose.premul(old)
    Ro = post.layer256(compose.R / 'old' / f'{sel}_{view}.png')
    E = np.abs(P[..., :3] - Ro[..., :3]).max(axis=2)
    m = shell_interior(view, S) & (Ro[..., 3] > 0.98)
    if fam == 'helm': m[compose.BAR_TOP:] = False
    M = ndimage.binary_dilation(compose.card_mask(sel, view, S), iterations=3)
    big = m & ~M & (E > 30.0 / 255.0)
    big = ndimage.binary_opening(big, structure=np.ones((2, 2), bool))
    return int(big.sum()), big
if __name__ == '__main__':
    rows = []
    for n in sorted(C.index()):
        if not n.endswith('_256'): continue
        try: k, _ = measure(n)
        except FileNotFoundError: continue
        rows.append((n, k))
    rows.sort(key=lambda r: -r[1])
    json.dump(rows, open(C.WORK.parent / 'out' / 'card_only_art.json', 'w'), indent=1)
    print(len(rows), 'cards measured; top:', rows[:40])
    print('cards over 60 px:', sum(1 for r in rows if r[1] > 60))
