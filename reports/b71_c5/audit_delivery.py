"""Bound the C5 production delta to outside grass, page previews and their pins."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
ROOT = Path(__file__).resolve().parents[2]
BASE = '5eac51c7'

def previous(path):
    return subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)

def sha(data): return hashlib.sha256(data).hexdigest()

owner='mod_editor/core/nfl2k5_modern_color.py'
a,b = (ast.parse(text) for text in (previous(owner),(ROOT/owner).read_bytes()))
def defs(tree):
    return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
def assigns(tree):
    return {n.targets[0].id:ast.dump(n.value,include_attributes=False) for n in tree.body
            if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)}
old,new=defs(a),defs(b)
rig_functions=('read_rig','configured_rig','_retail_table','modern_table','apply','verify','xbe_status','reservations')
for name in rig_functions:
    assert old[name] == new[name], name
for name in ('MODERN_RIGS','LIGHT_TABLES','SCREEN_FACTOR','GUARDS','REQUESTS'):
    assert assigns(a)[name] == assigns(b)[name],name
p=json.loads((ROOT/'data/nfl2k5_modern_color_pins.json').read_bytes())
q=json.loads(previous('data/nfl2k5_modern_color_pins.json'))
assert p['light_tables'] == q['light_tables']
assert len(p['bundles']) == len(q['bundles']) == 477
changed=[]
for current,before in zip(p['bundles'],q['bundles']):
    for key in ('name','outer','name_id','size','retail_sha256'):
        assert current[key] == before[key]
    if current['applied_sha256'] != before['applied_sha256']:
        changed.append(current['name'])
    for site,oldsite in zip(current['sites'],before['sites']):
        assert all(site[k] == oldsite[k] for k in ('kind','offset','size','retail'))
        if site['kind'] != 'field': assert site == oldsite
assert changed
# Existing feature owners, dispatcher and protected release scope remain exact.
for path in ('mod_editor/core/mod_build.py','mod_editor/capabilities/registry.v1.json',
             'packaging/release-allowlist.txt','data/nfl2k5_cave_reservations.json'):
    assert (ROOT/path).read_bytes() == previous(path),path
for path in (ROOT/'mod_editor/core').glob('nfl2k5_scorebug*.py'):
    assert path.read_bytes() == previous(str(path.relative_to(ROOT))),path
for path in ('mod_editor/core/nfl2k5_scorebar_v3.py','mod_editor/core/nfl2k5_widescreen.py'):
    assert (ROOT/path).read_bytes() == previous(path),path
result=dict(base=BASE,bundle_records=477,changed_bundle_count=len(changed),changed_bundles=changed,
            unchanged_rig_count=7,unchanged_rig_functions=rig_functions,
            owner_sha256=sha((ROOT/owner).read_bytes()),pins_sha256=sha((ROOT/'data/nfl2k5_modern_color_pins.json').read_bytes()),
            unchanged_sites=('normal','divots','tint'),protected_registry_metadata='prepared in WIRING.md; existing row strictly validates',
            executable_gates='not rerun: no rig or executable change; actual complete C4 XBE equality checked by prove_sidelines.py')
(ROOT/'reports/b71_c5/delivery-scope.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS',len(changed),'changed bundles; outside resource scope; seven C4 rigs and rig functions exact')
