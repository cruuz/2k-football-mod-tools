"""Reconcile the completed apf phase with the corrected CLI invocation."""
from pathlib import Path
import json
OUT = Path(__file__).resolve().parent
rows = json.loads((OUT / 'apf-results.json').read_text())
assert [r['path'] for r in rows if r['exit_code']] == ['tests/mod_editor/test_apf_studio_installer.py']
receipts = []
for row in rows:
    name = ('delivery-' if row['exit_code'] else 'final-') + Path(row['path']).stem
    receipt = json.loads((OUT / (name + '.result.json')).read_text())
    assert receipt['exit_code'] == 0, name
    receipts.append(dict(path=row['path'], receipt=name + '.result.json', exit_code=0))
assert 'Ran 16 tests' in (OUT / 'delivery-test_apf_studio_installer.log').read_text()
(OUT / 'apf-delivery-results.json').write_text(json.dumps(receipts, indent=2) + '\n')
print('All', len(receipts), 'apf suites have passing final receipts; original CLI error retained.')
