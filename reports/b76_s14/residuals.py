"""The s10/s11 player-scale residuals for NYG-LAR, DEN-KC and LV-HOU on the current data folder.

NYG-LAR is reports/b76_s12/player_scale.py (q1 and q4, both aspects) and DEN-KC plus LV-HOU is
reports/b72_s11/player_scale.py on the two reference frames s11 recorded (sha256 checked against
reports/b72_s11/final_measurements.json). Each module's own draw(), reference() and metrics() are used unchanged,
so every number is directly comparable with the s10, s11 and s12 rows. Renders are the offline native HUD with the
Lanczos display approximation; no in-game result is measured or claimed.

Usage: python3 reports/b76_s14/residuals.py --tag before|after [--save-renders]
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


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--tag', required=True)
    p.add_argument('--save-renders', action='store_true', help='Keep the player-scale renders for the sheets')
    a = p.parse_args(argv)
    start = time.time()
    s12 = load(ROOT / 'reports/b76_s12/player_scale.py', 'b76_s12_player_scale')
    s11 = load(ROOT / 'reports/b72_s11/player_scale.py', 'b72_s11_player_scale')
    recorded = json.loads((ROOT / 'reports/b72_s11/final_measurements.json').read_text())['provenance']
    preview = s12.sprite.NativePreview()
    result = dict(tag=a.tag, metric='mean player pixels over both states or matchups and both aspects; the logo '
                                     'and wing proxies overlap and must not be summed', rows=[])
    for label, module in (('NYG_LAR', s12), ('DEN_KC_LV_HOU', s11)):
        rows = []
        for name, (path, state) in module.CASES.items():
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            if module is s11 and digest != recorded[name]['sha256']:
                raise SystemExit('The s11 reference frame changed: ' + str(path))
            reference = module.reference(path)
            for wide in (False, True):
                image, _receipt = module.draw(preview, state, wide)
                aspect = '169' if wide else '43'
                if a.save_renders:
                    image.save(OUT / ('render_%s_%s_%s.png' % (a.tag, name, aspect)))
                rows.extend(dict(case=name, aspect=aspect, reference=Path(path).name, reference_sha256=digest,
                                 **{k: r[k] for k in ('feature', 'visible_area_px', 'rgb_diagnostic_px')})
                            for r in module.metrics(image, reference))
        result[label] = {feature: round(sum(r['visible_area_px'] for r in rows if r['feature'] == feature)
                                        / sum(1 for r in rows if r['feature'] == feature), 2)
                         for feature in module.REGIONS}
        result['rows'].extend(dict(group=label, **r) for r in rows)
    result['seconds'] = round(time.time() - start, 1)
    (OUT / ('residuals_%s.json' % a.tag)).write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8',
                                                     newline='\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=1))


if __name__ == '__main__':
    main()
