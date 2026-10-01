"""The s10/s11 player-scale residuals with the week-2 records on the Giants at Rams states.

Same metric as reports/b76_s14/residuals.py: reports/b76_s12/player_scale.py (NYG-LAR q1 and q4, both aspects) and
reports/b72_s11/player_scale.py (DEN-KC and LV-HOU guard frames), each module's own draw(), reference() and
metrics() unchanged. One difference, and only where the tree supports it: the NYG-LAR states carry the records the
broadcast shows on those frames (Giants 1-0, Rams 0-1, a week-2 Franchise game). The guard states stay as they are:
DEN-KC is week 1 and LV-HOU a preseason game, and ESPN draws no record on either.

    python3 reports/b76_s15/residuals.py --tag before --root <a checkout of the base commit>
    python3 reports/b76_s15/residuals.py --tag after

Renders are the offline native HUD with the Lanczos display approximation; no in-game result is measured or claimed.
Set B76_S12_FRAMES to the read-only Giants at Rams frames.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
RECORDS = dict(away_record=[1, 0, 0], home_record=[0, 1, 0])


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--tag', required=True)
    p.add_argument('--root', type=Path, default=OUT.parents[1])
    p.add_argument('--save-renders', action='store_true')
    a = p.parse_args(argv)
    root = a.root.resolve()
    sys.path[:0] = [str(root), str(root / 'tools')]
    start = time.time()
    s12 = load(root / 'reports/b76_s12/player_scale.py', 'b76_s12_player_scale')
    s11 = load(root / 'reports/b72_s11/player_scale.py', 'b72_s11_player_scale')
    recorded = json.loads((root / 'reports/b72_s11/final_measurements.json').read_text())['provenance']
    supports_records = 'home_record' in s12.sprite.STANDARD_STATE
    preview = s12.sprite.NativePreview()
    result = dict(tag=a.tag, root=str(root), records_on_nyg_lar=supports_records,
                  metric='mean player pixels over both states or matchups and both aspects; the logo and wing '
                         'proxies overlap and must not be summed', rows=[])
    for label, module in (('NYG_LAR', s12), ('DEN_KC_LV_HOU', s11)):
        rows = []
        for name, (path, state) in module.CASES.items():
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            if module is s11 and digest != recorded[name]['sha256']:
                raise SystemExit('The s11 reference frame changed: ' + str(path))
            if module is s12 and supports_records:
                state = dict(state, **RECORDS)
            reference = module.reference(path)
            for wide in (False, True):
                image, _receipt = module.draw(preview, state, wide)
                aspect = '169' if wide else '43'
                if a.save_renders:
                    image.save(OUT / f'render_{a.tag}_{name}_{aspect}.png', optimize=True)
                rows.extend(dict(matchup=name, aspect=aspect, **r) for r in module.metrics(image, reference))
        features = sorted({r['feature'] for r in rows})
        summary = {f: round(sum(r['visible_area_px'] for r in rows if r['feature'] == f) /
                            sum(1 for r in rows if r['feature'] == f), 2) for f in features}
        result['rows'].append(dict(group=label, mean_player_px=summary, detail=rows))
    result['seconds'] = round(time.time() - start, 1)
    (OUT / f'residuals_{a.tag}.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    for group in result['rows']:
        print(group['group'], json.dumps(group['mean_player_px']))


if __name__ == '__main__':
    raise SystemExit(main())
