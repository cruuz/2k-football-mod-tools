"""Audit existing capability identity, explicit paths and private delivery bounds."""
import hashlib
import json
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[2]
base=Path(__file__).with_name('base.txt').read_text().strip()
git=['git','--git-dir=.scratch/git','--work-tree=.']
old=json.loads(subprocess.check_output([*git,'show',base+':mod_editor/capabilities/registry.v1.json']))
new=json.loads((root/'mod_editor/capabilities/registry.v1.json').read_text())
ids=lambda value: sorted(r['id'] for r in value['capabilities'])
assert ids(old)==ids(new)
paths=subprocess.check_output([*git,'diff','--name-only',base],text=True).splitlines()
allowed=json.loads(Path(__file__).with_name('implementation_paths.json').read_text())
assert all(p in allowed or p in {'ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md'} or p.startswith('reports/b71_apf6/') for p in paths), paths
assert (root/'tools/apf_h7a_optimal').stat().st_mode & 0o777 == 0o755
scratch_bytes=sum(p.stat().st_size for p in (root/'.scratch').rglob('*') if p.is_file() and not p.is_symlink())
assert scratch_bytes < 200*1024*1024, scratch_bytes
for path in (root/'reports/b71_apf6').rglob('*'):
 if path.is_file(): assert path.suffix in {'.py','.txt','.log','.json','.jsonl','.png'}, path
row=next(r for r in new['capabilities'] if r['id']=='apf2k8.playbooks.cpu_playcalling')
assert row['runtime']['status']=='not-tested'
assert {'tests/mod_editor/test_apf_b71_editor_workflow.py','tests/mod_editor/test_apf_b71_editor_workflow_qt.py'} <= set(row['evidence'])
receipt={'base':base,'total_capabilities':len(ids(new)), 'apf_capabilities':sum(r['game']=='apf2k8_xbox360' for r in new['capabilities']),
         'new_rows':0,'capability_id_set_sha256':hashlib.sha256('\n'.join(ids(new)).encode()).hexdigest(),
         'scratch_bytes':scratch_bytes,'h7a_mode':'0755','changed_paths':paths,'gameplay':'UNWITNESSED'}
Path(__file__).with_name('delivery_audit.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
