import sys, json, time; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, bljob, assign
from pathlib import Path
R = C.WORK / 'bl' / 'r'
def plan(only=None):
    items = []
    kits = sorted({(n.split('_')[1][1:], n.split('_')[1][0].upper(), n.split('_')[2]) for n in C.index()})
    for code, side, style in kits:
        sel = f'{code}{side}{style}'
        if only and not any(sel.startswith(o) for o in only): continue
        old_tex = C.hindex().get(f'helmet02_{sel}') or str(C.WORK / 'final' / 'helmets' / f'helmet02_{sel}.png')
        for kind, tex in (('old', old_tex), ('new', str(assign.new_tex_path('helmet02', sel)))):
            outs = {'helm_card': R / kind / f'{sel}_helm.png', 'helmet': R / kind / f'{sel}_unif.png'}
            if all(Path(p).exists() for p in outs.values()) and kind == 'old': continue
            items.append((sel, kind, bljob.item(tex, side, outs)))
    return items
if __name__ == '__main__':
    only = sys.argv[1:] or None
    items = plan(only)
    (R / 'old').mkdir(parents=True, exist_ok=True); (R / 'new').mkdir(parents=True, exist_ok=True)
    print('items', len(items), flush=True)
    B = 12; t0 = time.time()
    for i in range(0, len(items), B):
        batch = items[i:i+B]
        dt = bljob.run([b[2] for b in batch], f'r{i:04d}', threads=8)
        print(i, len(batch), round(dt, 1), 'elapsed', round(time.time() - t0), flush=True)
    print('done', round(time.time() - t0), flush=True)
