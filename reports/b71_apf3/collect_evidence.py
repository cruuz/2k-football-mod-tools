"""Collect derived native receipts without copying any game image bytes."""
import ast
import json
from pathlib import Path

folder = Path(__file__).parent
log = folder / 'native-final-pointer-check.log'
text = log.read_text()
assert 'Ran 30 tests' in text and text.rstrip().endswith('OK')
receipts, tuples = [], []
for line in text.splitlines():
    if 'PROVED full native depth/lineup receipts' in line:
        receipts.extend(json.loads(line.split('bounded): ', 1)[1]))
    if 'PROVED APF-2 tuple extended: ' in line:
        receipts.append(json.loads(line.split('PROVED APF-2 tuple extended: ', 1)[1]))
    if 'Full tuples under categories 3/6/7 follow;' in line:
        tuples = ast.literal_eval(line.split('branches: ', 1)[1])
assert len(receipts) == 16 and len(tuples) == 138
assert sum(row['selected_te_depth_players'] for row in receipts) == 8
assert all(row['tuple_before'] == row['tuple_after'] for row in receipts)
output = {
    'source_log': log.as_posix(),
    'scope': 'PROVED bounded native with synthetic depth charts; gameplay UNWITNESSED',
    'rating_comparisons': 4832,
    'minimum_native_rating_weight': 0.10000000149011612,
    'ordinary_component_queries': 138,
    'shared_exclusion_buffers': 46,
    'full_call_tuples': tuples,
    'lineup_receipts': receipts,
}
(folder / 'native_receipt.json').write_bytes((json.dumps(output, indent=2) + '\n').encode())
print('Collected 138 call tuples and 16 complete native lineup receipts; no retail bytes.')
