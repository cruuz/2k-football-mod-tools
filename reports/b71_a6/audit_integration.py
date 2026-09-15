from pathlib import Path
import ast,collections,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
registry=json.loads((ROOT/'mod_editor/capabilities/registry.v1.json').read_text())
rows={r['id']:r for r in registry['capabilities']}
heads=['a142739b','464423f0','4819ab5b','c6b0ce23','0edcb323']
union=set();inputs={}
for rev in heads:
 d=json.loads(subprocess.check_output(['git','show',rev+':mod_editor/capabilities/registry.v1.json'],cwd=ROOT)); ids={r['id'] for r in d['capabilities']};union|=ids;inputs[rev]=len(ids)
assert set(rows)==union and len(rows)==176
for rev,key in [('464423f0','nfl2k5.scorebug_presentation.runtime'),('c6b0ce23','apf2k8.playbooks.cpu_playcalling'),('0edcb323','apf2k8.playbooks.fourth_down')]:
 d=json.loads(subprocess.check_output(['git','show',rev+':mod_editor/capabilities/registry.v1.json'],cwd=ROOT));assert rows[key]==next(r for r in d['capabilities'] if r['id']==key),key
c5=json.loads((ROOT/'reports/b71_c5/registry-metadata.json').read_text());row=rows[c5['id']]
assert row['input_constraints'][3:5]==c5['input_constraints'][3:5]
assert row['runtime']['scope']==c5['runtime']['scope'] and row['selectors']['notes']==c5['selectors']['notes']
# Verify the prepared script without importing or invoking it.
p=ROOT/'reports/b71_a6/build_testdisc71.py';tree=ast.parse(p.read_text());values={}
for node in ast.walk(tree):
 if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='replace':
  for kw in node.keywords:
   if kw.arg in ('scorebug','scorebug_runtime','modern_color','modern_arrowhead','widescreen'):values[kw.arg]=ast.literal_eval(kw.value)
assert values==dict(scorebug=True,scorebug_runtime=True,modern_color=True,modern_arrowhead=True,widescreen=True)
from mod_editor.core.mod_build import BuildPlan
assert set(values)<=set(BuildPlan.__dataclass_fields__)
s=p.read_text();assert "'softdrink_advanced'" in s and 'while len(images) >= 3:' in s and 'patches_before' in s
assert 'NFL 2K5 MOD TEST 2026-09-15i (everything: scorebug v3 + colour + day tuning + modern Arrowhead + widescreen)' in s
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
from mod_editor.core import nfl2k5_modern_arrowhead as arrowhead
assert runtime.CODE_SIZE==1408 and runtime.DATA_SIZE==128 and arrowhead.REQUESTS==()
result=dict(registry_total=len(rows),registry_inputs=inputs,all_input_capability_ids_preserved=True,c5_prose_exact=True,s3_registry_exact=True,apf4_registry_exact=True,apf5_registry_exact=True,builder_prepared_not_executed=True,options=values,builder_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),owner_requests=runtime.REQUESTS)
(ROOT/'reports/b71_a6/integration-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
