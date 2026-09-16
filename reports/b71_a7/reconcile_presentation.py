"""Reconcile the completed presentation phase with the corrected CLI invocation."""
from pathlib import Path
import json
OUT = Path(__file__).resolve().parent
rows = json.loads((OUT / 'presentation-results.json').read_text())
assert [r['path'] for r in rows if r['exit_code']] == ['tests/nfl_uniform_color_patch_test.py']
receipts = []
for row in rows:
    name = ('delivery-' if row['exit_code'] else 'final-') + Path(row['path']).stem
    receipt = json.loads((OUT / (name + '.result.json')).read_text())
    assert receipt['exit_code'] == 0, name
    receipts.append(dict(path=row['path'], receipt=name + '.result.json', exit_code=0))
assert 'NFL_UNIFORM_COLOR_PATCH_TEST_PASS cases=6' in (OUT / 'delivery-nfl_uniform_color_patch_test.log').read_text()
(OUT / 'presentation-delivery-results.json').write_text(json.dumps(receipts, indent=2) + '\n')
print('All', len(receipts), 'presentation suites have passing final receipts; original CLI error retained.')
