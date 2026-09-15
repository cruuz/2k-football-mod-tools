"""Fast model/scope preflight before compression; final proof reparses actual refits."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from reports.b71_c5.prove_sidelines import mc, SOURCE, baseline, decoded, check_model

old = baseline()
class Capture(Exception):
    def __init__(self, raw): self.raw = raw

def capture(span, raw): raise Capture(raw)
def transform(module, span):
    fit = module.fit_fixed_span
    module.fit_fixed_span = capture
    try:
        module.modern_field_scene(span)
    except Capture as ex:
        return ex.raw
    finally:
        module.fit_fixed_span = fit
    return module._scene(span,module._chunks(span)[0])[1]

seen = set()
with mc._outer_image()(SOURCE/'vc_53450030') as archive:
    for p in mc._pins()['bundles']:
        e = archive.entries[p['outer']]
        data = archive.read(e.virtual_offset,e.size)
        span = mc.field_span(data)
        key = mc.sha(span)
        if key in seen: continue
        seen.add(key)
        raw = transform(mc,span)
        before = transform(old,span)
        info, _, allowed = decoded(span,raw_override=raw)
        changes = {i for i,(a,b) in enumerate(zip(raw,before)) if a != b}
        assert changes <= allowed, (p['name'],'scope')
        assert info['materials'][mc.OUTSIDE_MATERIAL] == ('ffffffff','ffffffff'), p['name']
        if info['rgb'][mc.OUTSIDE_MATERIAL] is not None:
            try: check_model(info)
            except AssertionError:
                print('FAIL',p['name'],info,flush=True)
                raise
        else:
            assert p['name'][4] == 's' and not changes, p['name']
        print('PASS',p['name'],flush=True)
print('PASS',len(seen),'distinct field scenes before compression; no refit/pin claim')
