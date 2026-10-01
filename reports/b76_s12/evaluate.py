"""Measure the current data folder on the s10/s11 residual metric, for one author trial.

The primary metric is reports/b76_s12/player_scale.py (NYG at LAR, q1 and q4, both
aspects). The guard is reports/b72_s11/player_scale.py rendered unchanged against
the two reference frames s11 recorded (DEN at KC and LV at HOU); their sha256 must
match reports/b72_s11/final_measurements.json, and the guard is skipped when they
are absent. Each module's own draw(), reference() and metrics() are used, so every
number is directly comparable with the recorded rows. Nothing is written to reports/.

Trial recipe (reports/b76_s12/AUTHOR_STEPS.json lists every trial that was run):
    python3 reports/b76_s12/author.py --steps marks,fits,wing --params trial.json
    python3 reports/b76_s12/evaluate.py --tag trial
    python3 reports/b76_s12/author.py            # back to the accepted steps
"""
import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guard_frames_present(module):
    recorded = json.loads((ROOT / 'reports/b72_s11/final_measurements.json').read_text())['provenance']
    for name, (path, _state) in module.CASES.items():
        if not Path(path).is_file() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != recorded[name]['sha256']:
            return False
    return True


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--tag', default='trial')
    p.add_argument('--no-guard', action='store_true', help='Skip the s11 DEN-KC / LV-HOU guard')
    a = p.parse_args(argv)
    start = time.time()
    primary = load(OUT / 'player_scale.py', 'b76_s12_player_scale')
    modules = [('s12', primary)]
    if not a.no_guard:
        guard = load(ROOT / 'reports/b72_s11/player_scale.py', 'b72_s11_player_scale')
        if guard_frames_present(guard):
            modules.append(('s11', guard))
    preview = primary.sprite.NativePreview()
    result = dict(tag=a.tag)
    for label, module in modules:
        rows = []
        for name, (path, state) in module.CASES.items():
            reference = module.reference(path)
            for wide in (False, True):
                image, _ = module.draw(preview, state, wide)
                rows.extend(dict(case=name, aspect='169' if wide else '43', **r) for r in module.metrics(image, reference))
        result[label] = {feature: round(sum(r['visible_area_px'] for r in rows if r['feature'] == feature)
                                        / sum(1 for r in rows if r['feature'] == feature), 2)
                         for feature in module.REGIONS}
    result['seconds'] = round(time.time() - start, 1)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
