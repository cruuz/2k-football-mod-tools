"""All Team Select cards from the cleaned helmets + receipts + a repointed league project."""
import sys, json, hashlib, os; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, final, compose
from PIL import Image
from pathlib import Path
OUT = C.WORK.parent / 'out'
FILES = OUT / 'assets' / 'files'
def sha(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def save(rgba, path):
    Image.fromarray(np.ascontiguousarray(rgba), 'RGBA').save(path, optimize=False, compress_level=9)
    assert (C.load(path) == rgba).all()
#: kits whose stored cards showed palette specks after the cleanup (the Studio's 256-colour median cut ran short of
#: the shell's greys where the old flag had been, and gave them a reddish grey): their PNGs ship already mapped to that
#: palette refined by k-means, which the Studio then stores as it is (at most 256 colours)
REFINE_PALETTE = {('27', '6')}
def refine_palette(rgba, iters=12):
    """The Studio's own 256-entry median-cut palette of this card, refined by Lloyd (k-means) passes over the card's
    RGBA colours (each pass can only lower the total error), and the card mapped to it."""
    from scipy.spatial import cKDTree
    sys.path.insert(0, str(C.WT / 'tools'))
    import nfl_tset_png_import as pt
    h, w = rgba.shape[:2]
    pal, _idx, _q = pt.quantize_levels([pt.MipLevel(0, w, h, np.ascontiguousarray(rgba).tobytes())])
    P = np.array(pal, float); cols, inv, cnt = np.unique(rgba.reshape(-1, 4).astype(float), axis=0, return_inverse=True, return_counts=True)
    for _ in range(iters):
        lab = cKDTree(P).query(cols)[1]
        for k in range(len(P)):
            m = lab == k
            if m.any(): P[k] = (cols[m] * cnt[m, None]).sum(0) / cnt[m].sum()
    P = np.clip(np.round(P), 0, 255); lab = cKDTree(P).query(cols)[1]
    out = P[lab][inv.ravel()].reshape(h, w, 4).astype(np.uint8)
    assert (C.quantize(out) == out).all()          # the Studio stores it unchanged
    return out
def kits():
    return sorted({(n.split('_')[1][1:], n.split('_')[1][0], n.split('_')[2]) for n in C.index()})
def ready(code, s, style):
    sel = f"{code}{s.upper()}{style}"
    return all((compose.R / k / f'{sel}_{v}.png').exists() for k in ('old', 'new') for v in ('helm', 'unif'))
def one(args):
    code, s, style = args
    receipt = {}
    if True:
        for fam in ('helm', 'unif'):
            n256 = f'{fam}_{s}{code}_{style}_256'
            new, st = compose.compose(n256)
            base = compose.base_card(n256)
            todo = [(n256, base, new, st)]
            if fam == 'helm':
                n128 = f'helm_{s}{code}_{style}_128'
                h = compose.half(n128, new); b128 = compose.base_card(n128)
                todo.append((n128, b128, h, dict(derived_from=n256)))
            for name, before, after, info in todo:
                changed = int((before != after).any(axis=2).sum())
                assert (before[..., 3] == after[..., 3]).all(), name
                if changed and (code, style) in REFINE_PALETTE:
                    after = refine_palette(after); changed = int((before != after).any(axis=2).sum())
                fn = f'b81art_{name}.png'
                if changed: save(after, FILES / fn)
                q = C.quantize(after)
                receipt[name] = dict(info, changed_pixels=changed, file=fn if changed else None,
                                     source_png=os.path.basename(C.index()[name]), source_rgba_sha256=sha(C.cur(name)),
                                     built_before_rgba_sha256=sha(final.card(name)), base='built card' if compose.base_card(name) is not None and f'{code}_{style}' in compose.PASS_CARDS else 'project png',
                                     new_rgba_sha256=sha(after), new_file_sha256=hashlib.sha256((FILES / fn).read_bytes()).hexdigest() if changed else None,
                                     stored_rgba_sha256=sha(q),
                                     visible_change_vs_built=int((np.abs(q.astype(int) - final.card(name).astype(int)).max(axis=2) > 12).sum()))
    return receipt
def run(only=None, procs=14):
    import multiprocessing as mp
    FILES.mkdir(parents=True, exist_ok=True)
    rec_path = OUT / 'card_receipt.json'
    receipt = json.load(open(rec_path)) if rec_path.exists() else {}
    todo = [k for k in kits() if (not only or k[0] in only) and ready(*k)]
    with mp.Pool(procs) as pool:
        for part in pool.imap_unordered(one, todo, chunksize=1):
            receipt.update(part)
    json.dump(receipt, open(rec_path, 'w'), indent=1, sort_keys=True)
    return receipt
if __name__ == '__main__':
    r = run(set(sys.argv[1:]) or None)
    print(len(r), 'cards in receipt;', sum(1 for v in r.values() if v['changed_pixels']), 'changed')
