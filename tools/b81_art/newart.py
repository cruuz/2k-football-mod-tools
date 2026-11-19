"""Helmets whose league-project source art is replaced (rebuilt logos need colours the old 256-colour palette does not
hold): copies their finished textures beside the cards as new source PNGs, writes helmet_receipt.json (what apply_art
repoints and the tests pin) and adds them to new_helmet_art.json (what the kit-fix document build imports first)."""
import sys, json, shutil, hashlib; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, compose, assign
OUT = C.WORK.parent / 'out'
def free_names():
    ov = json.load(open(C.WORK / 'overrides.json')); names = []
    for key, v in sorted(ov.items()):
        if isinstance(v, dict) and isinstance(v.get('refine'), dict) and v['refine'].get('free'):
            kit, fam = key.split(':')
            for side in 'HA':
                name = f"{fam}_{kit[:2]}{side}{kit[3:]}"
                if name in C.hindex(): names.append(name)
    return names
def build():
    files = OUT / 'assets' / 'files'; files.mkdir(parents=True, exist_ok=True)
    rec = {}; art = {k: v for k, v in json.load(open(OUT / 'new_helmet_art.json')).items() if k in assign.REASSIGN}
    for name in free_names():
        fam, sel = name.split('_'); src = OUT / 'helmets_assigned' / f'{name}.png'; fn = f'b81art_{name}.png'
        shutil.copyfile(src, files / fn)
        rec[name] = dict(file=fn, source_png=str(C.hindex()[name]).split('/')[-1], source_rgba_sha256=compose.sha(C.load(C.hindex()[name])),
                         new_rgba_sha256=compose.sha(C.load(files / fn)), new_file_sha256=hashlib.sha256((files / fn).read_bytes()).hexdigest())
        art.setdefault(sel, {})[fam] = str(files / fn)
    json.dump(rec, open(OUT / 'helmet_receipt.json', 'w'), indent=1, sort_keys=True)
    json.dump(art, open(OUT / 'new_helmet_art.json', 'w'), indent=1, sort_keys=True)
    return rec
if __name__ == '__main__':
    r = build(); print('new helmet source art:', len(r), sorted(r))
