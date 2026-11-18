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
        key = sha(T) + name.split('_')[0] + name[9:11]
        if key in cache:
            res, st = cache[key]
        else:
            if name[9:] in extra:
                # retail-art or composed throwback kits: only the painted vent twins go (helmet02); helmet00 stays
                res, masks = fixtex.cleanup(name, tex=T, foot=np.zeros((256, 256), bool)) if name.startswith('helmet02') else (T.copy(), {})
                d = dict(left=np.zeros((256, 256), bool), paint=np.zeros((256, 256), bool), panels={})
            else:
                T2, res, d, masks = fixtex2.cleanup(name)
            vents = masks.get('vents', np.zeros((256, 256), bool))
            st = dict(vents=int((vents & (res != T).any(axis=2)).sum()), diamond=int((masks.get('diamond', vents * 0).astype(bool) & (res != T).any(axis=2)).sum()),
                      old=int((d['left'] & ~vents).sum()), old_painted=int((d['paint'] & ~vents & (res != T).any(axis=2)).sum()),
                      keyline=int((masks.get('keyline', vents * 0).astype(bool) & (res != T).any(axis=2)).sum()),
                      registered=d['panels'], changed=int((res != T).any(axis=2).sum()))
            cache[key] = (res, st)
        assert (res[..., 3] == T[..., 3]).all()
        Image.fromarray(res, 'RGBA').save(OUT / (name + '.png'))
        stats[name] = dict(st, before_rgba_sha256=sha(T), after_rgba_sha256=sha(res))
    json.dump(stats, open(OUT.parent / 'helmet_stats.json', 'w'), indent=1, sort_keys=True)
    tot = {k: sum(s.get(k, 0) for s in stats.values()) for k in ('vents', 'diamond', 'old', 'keyline', 'changed')}
    print(len(stats), tot, 'unique', len(cache))
main()
