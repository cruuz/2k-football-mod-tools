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
