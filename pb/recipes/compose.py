#!/usr/bin/env python3
"""DESIGN: copy a production recipe, changing only the three playbook keys."""
import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEYS = {'playbook_packs', 'playbook_pair', 'read_option_runtime'}


def compose(base, fragment):
    changes = fragment['overrides']
    if set(changes) != KEYS:
        raise ValueError('Playbook fragment must change only packs, pair and read option')
    result = copy.deepcopy(base)
    result['overrides'].update(changes)
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('base', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    if args.base.resolve() == args.output.resolve():
        raise ValueError('Copy the production recipe; never edit it in place')
    result = compose(json.loads(args.base.read_text()),
                     json.loads((ROOT/'pb/recipes/final_playbooks.json').read_text()))
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True)+'\n')
