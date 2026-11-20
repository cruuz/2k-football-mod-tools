#!/usr/bin/env python3
"""b81-uniforms relief rollout (Noah 2026-11-19: "B. Keep new."): level B on every 2026 kit package.

  relief_rollout.py compose BASE MARKS OUT      level B jersey, sleeve and pants map of every kit -> OUT/maps/
  relief_rollout.py split OUT                   one master per map kind + per-kit patches -> OUT/art/, OUT/split.json
  relief_rollout.py document OUT DISC DOC ART   pin every slot against DISC (the v0.10 state after the two other passes):
                                                writes the Studio document DOC and its art folder ART

Stage 1 (relief_marks.py) reads each kit's final colour textures. Here:
  * jersey: bump_true.jersey at level B on the retail 18H0 sculpt with the kit's own collar opening, painted collar
    shield and any maker's mark painted on the torso;
  * sleeve: bump_true.sleeve at level B on the retail 18H0 sleeve with the kit's painted sleeve marks;
  * pants: bump_true.pants at level B on the kit's own pants map with its painted pants mark and shield; outside the
    worked boxes the kit's own bytes stay (keep_exact).
What ships: the jersey and sleeve masters are the most common value of each texel over all 178 composed maps; a kit's
patch is every texel where its map differs from the master (alpha 255 = take the patch, 0 = keep). Pants ship no
master: the Studio reads each kit's own pants map from the disc (it is retail-derived art) and lays the patch over it.
Identical patches are stored once.
"""
import sys, json, hashlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
U = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms')
RETAIL = U / 'work/retail/uniforms/18H0'
LEVEL = 'B'
OLD_PANTS = ((86, 36, 110, 56), (398, 36, 426, 56))
SLOTS = ('bump_jersey', 'bump_sleeve', 'bump_pants')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def bbox(mask):
    ys, xs = np.nonzero(mask)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if len(xs) else None


def kit_masks(marks_dir, sel, row):
    m = np.load(marks_dir / 'masks' / f'{sel}.npz')
    out = dict(opening=m['opening'], shield=m['shield'], torso=np.zeros_like(m['opening']),
               sleeve=np.zeros((128, 128), bool), pants_mark=np.zeros((256, 512), bool), pants_shield=np.zeros((256, 512), bool))
    for mk in row['marks']:
        if mk['box'] is None:
            continue
        mask = m[f"{mk['texture']}__{mk['key']}"]
        if mk['texture'] == 'torso':
            out['torso'] |= mask
        elif mk['texture'] == 'sleeve':
            out['sleeve'] |= mask
        else:
            out[mk['key']] |= mask
    return out


def compose_one(args):
    sel, base, marks_dir, out = (args[0], Path(args[1]), Path(args[2]), Path(args[3]))
    import bump_true as bt
    row = json.load(open(marks_dir / 'marks.json'))[sel]
    k = kit_masks(marks_dir, sel, row)
    torso = base / sel / 'torso.png'
    j = bt.jersey(LEVEL, RETAIL / 'bump_jersey.png', torso, opening=k['opening'], shield=k['shield'], marks=k['torso'])
    s = bt.sleeve(LEVEL, RETAIL / 'bump_sleeve.png', base / sel / 'sleeve.png', marks=k['sleeve'])
    before = base / sel / 'bump_pants.png'
    p = bt.pants(LEVEL, before, base / sel / 'pants.png', old_boxes=OLD_PANTS, marks=(k['pants_mark'], k['pants_shield']),
                 lift='fill')
    worked = list(OLD_PANTS) + [b for b in (bbox(k['pants_mark']), bbox(k['pants_shield'])) if b]
    p = bt.keep_exact(p, before, worked)
    res = {}
    for name, im in (('bump_jersey', j), ('bump_sleeve', s), ('bump_pants', p)):
        im = np.ascontiguousarray(im, np.uint8)
        im[..., 3] = 255
        Image.fromarray(im, 'RGBA').save(out / 'maps' / f'{sel}_{name}.png')
        res[name] = sha(im.tobytes())
    return sel, res


def compose(base, marks_dir, out):
    (out / 'maps').mkdir(parents=True, exist_ok=True)
    kits = list(json.load(open(marks_dir / 'marks.json')))
    with ProcessPoolExecutor(max_workers=14) as pool:
        rows = dict(pool.map(compose_one, [(s, str(base), str(marks_dir), str(out)) for s in kits]))
    (out / 'composed.json').write_text(json.dumps(rows, indent=1))
    for name in SLOTS:
        print(name, 'distinct composed maps', len({r[name] for r in rows.values()}))


def rgba(path):
    return np.asarray(Image.open(path).convert('RGBA'))


def split(out):
    rows = json.load(open(out / 'composed.json'))
    kits = sorted(rows)
    art = out / 'art'; art.mkdir(parents=True, exist_ok=True)
    for old in art.glob('*.png'):
        old.unlink()
    doc = dict(masters={}, patches={}, kits={})
    for name in SLOTS:
        maps = np.stack([rgba(out / 'maps' / f'{s}_{name}.png') for s in kits])
        if name != 'bump_pants':
            # the master: each texel's most common value over the 178 maps (as one 32-bit word)
            words = maps.view('<u4')[..., 0]
            flat = words.reshape(len(kits), -1)
            order = np.sort(flat, axis=0)
            master = np.empty(flat.shape[1], np.uint32)
            # mode per column: runs in the sorted column
            change = np.vstack([np.ones((1, flat.shape[1]), bool), order[1:] != order[:-1]])
            run_id = np.cumsum(change, axis=0)
            for col_block in range(0, flat.shape[1], 8192):
                sl = slice(col_block, col_block + 8192)
                o, r = order[:, sl], run_id[:, sl]
                best = np.zeros(o.shape[1], np.int64); bestv = o[0].copy()
                for run in range(1, int(r.max()) + 1):
                    hit = r == run
                    cnt = hit.sum(0)
                    better = cnt > best
                    if better.any():
                        val = np.where(hit, o, 0).max(0)
                        bestv[better] = val[better]; best[better] = cnt[better]
                master[sl] = bestv
            master_img = master.view(np.uint8).reshape(maps.shape[1:])
            fname = f'master_{name[5:]}.png'
            Image.fromarray(master_img, 'RGBA').save(art / fname, optimize=True)
            doc['masters'][name] = dict(png=fname, sha256=sha((art / fname).read_bytes()),
                                        rgba_sha256=sha(master_img.tobytes()))
        for i, sel in enumerate(kits):
            mine = maps[i]
            if name == 'bump_pants':
                ref = rgba(U / 'work/fix/RELIEF/base' / sel / 'bump_pants.png')
            else:
                ref = master_img
            diff = (mine != ref).any(-1)
            entry = doc['kits'].setdefault(sel, {})
            if not diff.any():
                entry[name] = None
                continue
            x0, y0, x1, y1 = bbox(diff)
            patch = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
            sub = diff[y0:y1, x0:x1]
            patch[sub] = mine[y0:y1, x0:x1][sub]
            patch[sub, 3] = 255
            key = sha(patch.tobytes() + bytes(f'{name}{x0},{y0}', 'ascii'))[:16]
            if key not in doc['patches']:
                fname = f'{name[5:]}_{key}.png'
                Image.fromarray(patch, 'RGBA').save(art / fname, optimize=True)
                doc['patches'][key] = dict(png=fname, sha256=sha((art / fname).read_bytes()), slot=name, x=x0, y=y0,
                                           width=x1 - x0, height=y1 - y0, texels=int(sub.sum()))
            entry[name] = key
    (out / 'split.json').write_text(json.dumps(doc, indent=1))
    sizes = {p.name: p.stat().st_size for p in art.glob('*.png')}
    print('masters', {k: v['png'] for k, v in doc['masters'].items()}, 'patches', len(doc['patches']),
          'files', len(sizes), 'bytes', sum(sizes.values()))
    for name in SLOTS:
        ids = [doc['kits'][s][name] for s in kits]
        print(name, 'kits with a patch', sum(1 for i in ids if i), 'distinct', len({i for i in ids if i}),
              'largest patch texels', max([doc['patches'][i]['texels'] for i in ids if i] or [0]))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'compose':
        compose(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    elif cmd == 'split':
        split(Path(sys.argv[2]))
    elif cmd != 'document':
        raise SystemExit(__doc__)


def document(out, disc, doc_path, art_dir):
    """Pin every slot against ``disc`` (the released disc with this job's two other passes applied) and write the
    Studio document and its art folder."""
    import shutil, time
    sys.path[:0] = [str(HERE.parents[1]), str(HERE.parents[1] / 'tools')]
    from mod_editor.core import nfl2k5_bump_texture_writer as bw
    from mod_editor.core import nfl2k5_relief_2026 as rl
    split_doc = json.load(open(out / 'split.json'))
    composed = json.load(open(out / 'composed.json'))
    art_dir = Path(art_dir); art_dir.mkdir(parents=True, exist_ok=True)
    for old in art_dir.glob('*.png'):
        old.unlink()
    masters, patches = {}, {}
    for name, m in split_doc['masters'].items():
        shutil.copy(out / 'art' / m['png'], art_dir / m['png'])
        w, h = (512, 256) if name == 'bump_jersey' else (128, 128)
        masters[name] = dict(png=m['png'], sha256=m['sha256'], width=w, height=h, rgba_sha256=m['rgba_sha256'])
    for key, p in split_doc['patches'].items():
        shutil.copy(out / 'art' / p['png'], art_dir / p['png'])
        patches[key] = dict(png=p['png'], sha256=p['sha256'], slot=p['slot'], x=p['x'], y=p['y'], width=p['width'],
                            height=p['height'])
    base_rows = {k['selector']: k for k in json.load(open(out / 'base' / 'base.json'))['kits']}
    rows, spans = [], {}
    with bw._Image.open(Path(disc), writable=False) as image:
        index = bw._parsed_index(image)
        entries = {}
        for e in index.entries:
            entries.setdefault(bw.logical_name_for(e.name_id), []).append(e)
        for sel in sorted(composed):
            (e,) = entries[sel + '.IFF']
            raw = image.read_segments(index.sub_extents(e, 0, e.size))
            for name in SLOTS:
                b = base_rows[sel]['bump'][name]
                chunk = rl._chunk_for(raw, b['chunk'])
                span = raw[chunk.offset:chunk.end_offset]
                assert sha(span) == b['span_sha256'], (sel, name)
                rows.append(dict(selector=sel, slot=name, chunk=chunk.index, resource_size=len(raw), offset=chunk.offset,
                                 length=len(span), base='before' if name == 'bump_pants' else 'master',
                                 patch=split_doc['kits'][sel][name], composed_sha256=composed[sel][name],
                                 before_sha256=sha(span), after_sha256=None))
                spans[(sel, name)] = span
    doc = dict(schema=rl.SCHEMA,
               job='b81-uniforms relief rollout (Noah 2026-11-19: "B. Keep new."): level B of tools/b81_uniforms/'
                   'bump_true.py on every SOFTDRINK 2026 kit package; authored by tools/b81_uniforms/relief_marks.py '
                   'and relief_rollout.py',
               level=LEVEL, art=art_dir.name, masters=masters, patches=patches, slots=rows)
    t0 = time.time()
    results = rl.compile_slots(rows, spans, doc)
    seconds = time.time() - t0
    pack = []
    for row in rows:
        new, detail = results[(row['selector'], row['slot'])]
        row['after_sha256'] = sha(new)
        pack.append(dict(selector=row['selector'], slot=row['slot'], **detail))
    Path(doc_path).write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
    rl.spec(doc_path)
    (out / 'pack.json').write_text(json.dumps(dict(seconds=round(seconds, 1), slots=pack), indent=1))
    worst = max(pack, key=lambda r: r['packed_bytes'] / r['stored_size'])
    print('slots', len(rows), 'compile seconds %.1f' % seconds, 'encoders',
          {e: sum(1 for r in pack if r['encoder'] == e) for e in ('greedy', 'optimal')}, 'tightest', worst)


if __name__ == '__main__' and sys.argv[1] == 'document':
    document(Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5])
