#!/usr/bin/env python3
"""Prepare ht's private candidate B runner and explicit requested/diagnostic recipes.

PROVED OFFLINE: only output locations change in the canonical helper. Source
assets stay read-only. This script neither builds a disc nor starts an emulator.
"""
import argparse
import json
from pathlib import Path

HUB = Path('/home/noah/Desktop/2K5-8 Editors/ultimate')
BUILD = Path('/media/noah/Storage/.b76-research/ht/astra-build')
PROJECT_COPY = '''    # ht sandbox: the service puts its compile cache beside the project JSON.
    # Keep a byte-identical copy here; all frozen asset paths must be absolute.
    frozen_bytes = args.project.read_bytes()
    frozen_project = json.loads(frozen_bytes)
    for edit in frozen_project["edits"]:
        for key in ("png", "clean_png"):
            if key in edit and not Path(edit[key]).is_absolute():
                raise ValueError(f"ht requires an absolute frozen asset path: {key}")
    private_project = HERE / "league_project_k2_v52_frozen.json"
    private_project.write_bytes(frozen_bytes)
    if private_project.read_bytes() != frozen_bytes:
        raise ValueError("ht private project copy differs from the frozen input")
    args.project = private_project
'''


def prepared_files():
    runner = (HUB/'build_ultimate_teams2026.py').read_text()
    old = '    cache = Nfl2k5SourceCache().index(Path(args.source))\n'
    if runner.count(old) != 1:
        raise ValueError('Canonical runner changed; review its cache handling before adapting it')
    runner = runner.replace(old, PROJECT_COPY +
                            '    cache = Nfl2k5SourceCache(HERE / "source-cache").index(Path(args.source))\n')
    outputs = {'build_ultimate.py': (HUB/'build_ultimate.py').read_bytes(),
               'build_ultimate_teams2026.py': runner.encode()}
    original = json.loads((HUB/'ULTIMATE_BUILD_RECIPE_2026-09-25_candidate_B.json').read_text())
    for suffix, enabled in [('requested', True), ('accessibility_diagnostic', False)]:
        recipe = json.loads(json.dumps(original))
        recipe['overrides']['historic_teams_quick_game'] = True
        recipe['overrides']['historic_rosters_2026'] = enabled
        if enabled:
            for key in ('historic_stock_books','espn25_more_moments','espn25_named_previews','espn25_era_rules'):
                recipe['overrides'][key] = True
        assert recipe['overrides']['espn25_rosters'] and recipe['overrides']['modern_helmets']
        outputs[f'candidate_B_ht_{suffix}.json'] = (json.dumps(recipe, indent=2)+'\n').encode()
    return outputs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true', help='Compare prepared files without writing')
    args = ap.parse_args()
    outputs = prepared_files()
    if not args.check:
        BUILD.mkdir(parents=True, exist_ok=True)
    for name, data in outputs.items():
        path = BUILD/name
        if args.check:
            assert path.read_bytes() == data, f'Prepared file differs: {path}'
        elif not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)
        print('PROVED OFFLINE:', 'identical' if args.check else 'prepared', path)


if __name__ == '__main__':
    main()
