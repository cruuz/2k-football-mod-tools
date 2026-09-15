"""Copy the C3 inventory's missing evidence documents read-only; never retail payloads."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
inventory = json.loads((ROOT/'reports/b71_c3/evidence-hydration.json').read_text())
source = Path(inventory['source'])
rows = []
for row in inventory['files']:
    relative = Path(row['path'])
    assert not relative.is_absolute() and '..' not in relative.parts
    dest = ROOT / relative
    if dest.exists():
        continue
    original = source / relative
    assert original.suffix in ('.md', '.json', '.gltf')
    assert original.stat().st_size < 2_000_000
    data = original.read_bytes()
    # JSON/GLTF metadata only; no inline buffers or retail payload.
    if original.suffix != '.md':
        doc = json.loads(data)
        assert not (isinstance(doc, dict) and any('data:' in str(b.get('uri', '')) for b in doc.get('buffers', [])))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    rows.append(dict(path=str(relative), bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
(ROOT/'reports/b71_c5/evidence-hydration.json').write_text(json.dumps(dict(operation='read-only document copies, excluded from commits',files=rows),indent=2)+'\n')
print('Hydrated',len(rows),'evidence documents')
