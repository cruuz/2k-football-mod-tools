"""Restore the exact private evidence inventory pinned by APF-3, read-only."""
import hashlib,json,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[2]
rows=json.loads((root/'reports/b71_apf3/hydration.json').read_text())
for row in rows:
 target=root/row['path']
 if not target.is_file():
  source=Path(row['source_read_only'])
  data=source.read_bytes()
  assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'], row['path']
  target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(data)
 assert target.stat().st_nlink==1, row['path']
 assert hashlib.sha256(target.read_bytes()).hexdigest()==row['sha256'],row['path']
print(f'Checked {len(rows)} exact independent evidence copies; sources never written')
