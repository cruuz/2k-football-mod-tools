"""Produce the cleaned final helmet textures for all 344 slots (H == A except Carolina) + stats."""
import sys, json, hashlib; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, final, fixtex, fixtex2
from PIL import Image
OUT = C.WORK.parent / 'out' / 'helmets'
def sha(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stats = {}; cache = {}
    extra = json.load(open(C.WORK / 'extra_kits.json'))
    names = sorted(C.hindex()) + [f'{fam}_{sel}' for sel in extra for fam in ('helmet00', 'helmet02')]
    for name in names:
        T = final.helmet(name)
        fam = name.split('_')[0]; entry = fixtex2.OVERRIDES.get(f"{name[9:11]}_{name[12:]}:{fam}")
        # an extra kit whose Standard shell keeps its placement takes the older steps (as its main kit's texture had)
        older = name[9:] in extra and fam == 'helmet00' and bool((entry or {}).get('keep_placement'))
        # the result depends on the texture, the club and the kit's own reviewed entry
        key = sha(T) + fam + name[9:11] + json.dumps(entry, sort_keys=True)
        if name.startswith('helmet00') and (final.OUT / 'helmets' / ('helmet02_' + name[9:] + '.png')).exists():
            # a Standard-shell result also depends on its modern-shell counterpart (the logo is rebuilt from it)
            key += sha(final.helmet('helmet02_' + name[9:]))
        if key in cache:
            res, st = cache[key]
        else:
            if name[9:] in extra and not older:
                # retail-art or composed throwback kits: only the painted vent twins go (helmet02); helmet00 stays
                res, masks = fixtex.cleanup(name, tex=T, foot=np.zeros((256, 256), bool)) if name.startswith('helmet02') else (T.copy(), {})
                d = dict(left=np.zeros((256, 256), bool), paint=np.zeros((256, 256), bool), panels={})
            else:
                T2, res, d, masks = fixtex2.cleanup(name)
            vents = masks.get('vents', np.zeros((256, 256), bool))
            st = dict(vents=int((vents & (res != T).any(axis=2)).sum()), diamond=int((masks.get('diamond', vents * 0).astype(bool) & (res != T).any(axis=2)).sum()),
                      old=int((d['left'] & ~vents).sum()), old_painted=int((d['paint'] & ~vents & (res != T).any(axis=2)).sum()),
                      keyline=int((masks.get('keyline', vents * 0).astype(bool) & (res != T).any(axis=2)).sum()),
                      registered=d['panels'], changed=int((res != T).any(axis=2).sum()),
                      transferred=int(np.asarray(masks.get('transferred', 0)).sum()))
            cache[key] = (res, st)
        assert (res[..., 3] == T[..., 3]).all()
        Image.fromarray(res, 'RGBA').save(OUT / (name + '.png'))
        stats[name] = dict(st, before_rgba_sha256=sha(T), after_rgba_sha256=sha(res))
    json.dump(stats, open(OUT.parent / 'helmet_stats.json', 'w'), indent=1, sort_keys=True)
    tot = {k: sum(s.get(k, 0) for s in stats.values()) for k in ('vents', 'diamond', 'old', 'keyline', 'changed')}
    print(len(stats), tot, 'unique', len(cache))
main()
