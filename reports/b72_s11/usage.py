"""Aggregate only this job's retained MCP usage receipts."""
from pathlib import Path
import json

OUT = Path(__file__).resolve().parent
rows = []
for name in ('jev_proof_review.json', 'own_gate_call.json', 'handoff_call.json'):
    path = OUT/name
    if not path.exists():
        continue
    call = json.loads(path.read_text())
    result = json.loads(call['response']['structuredContent']['result'])
    meta = result.get('meta', result.get('totals'))
    rows.append(dict(source=name, **meta))
total = round(sum(row['cost_usd'] for row in rows), 8)
assert total < 1.0
value = dict(cap_usd=1.0, total_cost_usd=total, tool_calls=len(rows),
    input_tokens=sum(row['input_tokens'] for row in rows), rows=rows)
(OUT/'JEV_USAGE.json').write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')
print(json.dumps(value, indent=2))
