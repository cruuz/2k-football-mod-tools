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

def check(job):
    name, span = job
    raw = transform(mc, span)
    before = transform(old, span)
    info, _, allowed = decoded(span, raw_override=raw)
    changes = {i for i, (a, b) in enumerate(zip(raw, before)) if a != b}
    assert changes <= allowed, (name, 'scope')
    assert info['materials'][mc.OUTSIDE_MATERIAL] == ('ffffffff', 'ffffffff'), name
    if info['rgb'][mc.OUTSIDE_MATERIAL] is not None:
        try:
            check_model(info)
        except AssertionError as exc:
            raise AssertionError((name, info, str(exc))) from exc
    else:
        assert not changes, (name, 'non-green outside must stay C4 exact')
    return name


def main():
    from concurrent.futures import ProcessPoolExecutor
    jobs = {}
    with mc._outer_image()(SOURCE/'vc_53450030') as archive:
        for p in mc._pins()['bundles']:
            e = archive.entries[p['outer']]
            data = archive.read(e.virtual_offset, e.size)
            span = mc.field_span(data)
            jobs.setdefault(mc.sha(span), (p['name'], span))
    with ProcessPoolExecutor(max_workers=8) as pool:
        for name in pool.map(check, jobs.values()):
            print('PASS', name, flush=True)
    print('PASS', len(jobs), 'distinct field scenes before compression; no refit/pin claim')


if __name__ == '__main__':
    main()
