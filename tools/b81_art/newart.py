"""Helmets whose league-project source art is replaced (rebuilt logos need colours the old 256-colour palette does not
hold): copies their finished textures beside the cards as new source PNGs, writes helmet_receipt.json (what apply_art
repoints and the tests pin) and adds them to new_helmet_art.json (what the kit-fix document build imports first)."""
import sys, json, shutil, hashlib; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, compose, assign, numpy as np
from pathlib import Path
OUT = C.WORK.parent / 'out'
RETAIL_INDEX = Path(__import__('os').environ.get('NFL2K5_RETAIL_INDEX', '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))
#: the most any texel may move in the Studio's import (levels per channel); more reads as a speck or a recoloured patch
LOCK_LIMIT = 40
def lock_lost_colours(job, rounds=4):
    """The Studio's importer fits each slot's fixed stored size by stepping its median-cut palette down (256, 128,
    64 entries), so a small logo colour can land on a far entry. Every exact colour the import moves by more than
    LOCK_LIMIT is reserved in the PNG with the importer's own record (nfl2k5_palette_lock) and the import is run again.
    Returns (name, colours locked, worst channel error of the import)."""
    name, path = job
    sys.path[:0] = [str(C.WT), str(C.WT / 'tools')]
    import nfl_live_helmet_txtr_png_import as importer, nfl_live_helmet_txtr_targets as targets, nfl_tset_png_import as pt
    from PIL import Image, PngImagePlugin
    fam, sel = name.split('_'); T = C.load(path); locked = set(); worst = None
    for _ in range(rounds + 1):
        _span, previews, _rep = importer.build_import(RETAIL_INDEX, targets.DEFAULT_REPORT, sel[:2], sel[2], int(sel[3:]), fam, Path(path))
        _w, _h, rgba = pt.decode_rgba_png(previews[0][1], (256, 256))
        err = np.abs(np.frombuffer(rgba, np.uint8).reshape(256, 256, 4)[..., :3].astype(int) - T[..., :3].astype(int)).max(axis=2)
        worst = int(err.max())
        if worst <= LOCK_LIMIT or len(locked) >= 200: break
        locked |= {tuple(int(v) for v in c) for c in T[err > LOCK_LIMIT]}
        meta = PngImagePlugin.PngInfo()
        meta.add_text('nfl2k5_palette_lock', json.dumps({'schema': 'nfl2k5_palette_lock/v1', 'rgba': [list(c) for c in sorted(locked)]}, separators=(',', ':')))
        Image.fromarray(T, 'RGBA').save(path, pnginfo=meta)
    return name, len(locked), worst
def free_names():
    ov = json.load(open(C.WORK / 'overrides.json')); names = []
    for key, v in sorted(ov.items()):
        if isinstance(v, dict) and isinstance(v.get('refine'), dict) and v['refine'].get('free'):
            kit, fam = key.split(':')
            for side in 'HA':
                name = f"{fam}_{kit[:2]}{side}{kit[3:]}"
                if name in C.hindex(): names.append(name)
    # ... and every slot whose assigned texture is a Standard-shell texture rebuilt from the modern shell (make_tex
    # records it; a Carolina slot takes another slot's texture, assign.REASSIGN, so the flag of that texture counts)
    stats = json.load(open(OUT / 'helmet_stats.json'))
    for n in sorted(C.hindex()):
        fam, sel = n.split('_')
        if stats.get(f"{fam}_{assign.REASSIGN.get(sel, sel)}", {}).get('transferred') and n not in names: names.append(n)
    return names
def build():
    files = OUT / 'assets' / 'files'; files.mkdir(parents=True, exist_ok=True)
    # the Carolina slots import their donor's league-project art; a slot with rebuilt art below takes that instead
    rec = {}; art = {sel: {fam: str(C.hindex()[f'{fam}_{donor}']) for fam in ('helmet00', 'helmet02')} for sel, donor in sorted(assign.REASSIGN.items())}
    for name in free_names():
        fam, sel = name.split('_'); src = OUT / 'helmets_assigned' / f'{name}.png'; fn = f'b81art_{name}.png'
        shutil.copyfile(src, files / fn)
        rec[name] = dict(file=fn, source_png=str(C.hindex()[name]).split('/')[-1], source_rgba_sha256=compose.sha(C.load(C.hindex()[name])),
                         new_rgba_sha256=compose.sha(C.load(files / fn)), new_file_sha256=hashlib.sha256((files / fn).read_bytes()).hexdigest())
        art.setdefault(sel, {})[fam] = str(files / fn)
    import multiprocessing as mp
    with mp.Pool(8) as pool:
        for name, n, worst in pool.map(lock_lost_colours, [(n, str(files / r['file'])) for n, r in sorted(rec.items())]):
            fn = files / rec[name]['file']
            assert compose.sha(C.load(fn)) == rec[name]['new_rgba_sha256']           # the lock never changes the picture
            rec[name].update(locked_colours=n, import_max_error=worst, new_file_sha256=hashlib.sha256(fn.read_bytes()).hexdigest())
    json.dump(rec, open(OUT / 'helmet_receipt.json', 'w'), indent=1, sort_keys=True)
    json.dump(art, open(OUT / 'new_helmet_art.json', 'w'), indent=1, sort_keys=True)
    return rec
if __name__ == '__main__':
    r = build(); print('new helmet source art:', len(r), sorted(r))
    print('worst import error:', max(v['import_max_error'] for v in r.values()), 'palette locks:',
          {n: (v['locked_colours'], v['import_max_error']) for n, v in sorted(r.items()) if v['locked_colours']})
