"""Restore only absent inherited evidence, checking the prior job's hashes."""
import hashlib
import json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
rows=json.loads((root/'reports/b71_apf3/hydration.json').read_text())
restored=[]
for row in rows:
    target=root/row['path']
    if target.exists():
        continue
    source=Path(row['source_read_only'])
    payload=source.read_bytes()
    assert len(payload)==row['bytes'] and hashlib.sha256(payload).hexdigest()==row['sha256'],row['path']
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(payload)
    restored.append(row)
(root/'reports/b71_apf5/hydration.json').write_text(json.dumps(restored,indent=2)+'\n')
print('Restored',len(restored),'unchanged inherited evidence files; total bytes',sum(r['bytes'] for r in restored))
