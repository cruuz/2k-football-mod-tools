"""DESIGN: compose Main's lab inputs, refusing an incomplete contract fragment."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr
from tools.franchise_economy.contracts import FIELDS
from tests.nfl2k5_supersim_draft_fixture import retail_roster


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', type=Path, required=True)
    ap.add_argument('--ratings', type=Path, required=True)
    ap.add_argument('--fragment', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    fragment = rr.read_edits(args.fragment)
    meta = fragment.get('fc_economy', {})
    if meta.get('scale') != 4 or meta.get('resolved', meta.get('matched')) != 1696 or meta.get('required') != 1696:
        raise ValueError('Main needs a complete 1:4 contract fragment for all 1696 club players')
    if any(set(row.get('fields', {})) != FIELDS or set(row) - {'pool', 'index', 'first', 'last', 'fields'} for row in fragment['edits']):
        raise ValueError('fc fragment must contain contract fields only')
    retail = retail_roster()
    body, base_receipt = rr.apply_body(retail, args.base)
    if fragment.get('source_body_sha256') != hashlib.sha256(body).hexdigest():
        raise ValueError('fc fragment was not made on this frozen base')
    receipts = [base_receipt]
    # r1 is imported unchanged as a separate input; fc never authors ratings.
    for source in (args.ratings, fragment):
        body, receipt = rr.apply_body(body, source)
        receipts.append(receipt)
    if any(row['log'] for row in receipts):
        raise ValueError('composed roster replay must have zero log lines')
    args.out.mkdir(parents=True, exist_ok=True)
    merged = args.out / 'lab_roster_edits.json'
    merged.write_text(json.dumps(rr.edits_between(retail, body, name='DESIGN: fc lab composition'), indent=2) + '\n')
    recipe = {'schema': 'softdrink_ultimate_recipe/v1', 'title': 'DESIGN: fc fitted-contract display experiment, Main only',
              'job': 'fc', 'preset': 'softdrink_basic', 'pending': {},
              'overrides': {'name': 'DESIGN: fc economy witness', 'author': 'fc',
                            'roster_edits': str(merged.resolve()), 'franchise_economy': True,
                            'season_2026': True, 'modern_naming': True, 'my_career': False}}
    (args.out / 'recipe.json').write_text(json.dumps(recipe, indent=2) + '\n')
    (args.out / 'prepare_receipt.json').write_text(json.dumps({'evidence': 'PROVED OFFLINE',
        'inputs': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.base, args.ratings, args.fragment)},
        'replays': receipts, 'result_body_sha256': hashlib.sha256(body).hexdigest(),
        'representation': 'DESIGN: fitted cap liability, not exact original cash/APY/guarantees',
        'observed_schedules': meta.get('observed_schedules'),
        'modeled_schedules': meta.get('modeled_schedules')}, indent=2) + '\n')


if __name__ == '__main__':
    main()
