"""Inspect the prepared builder without executing/importing it; compare code ownership."""
from pathlib import Path
import ast,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s,nfl2k5_scorebug_runtime as owner
OUT=Path(__file__).resolve().parent
before=ast.parse((ROOT/'reports/b71_s6/build_testdisc71.py').read_text())
after=ast.parse((OUT/'build_testdisc71.py').read_text())
def function(tree,name):return ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name))
assert function(before,'plan_for_disc')==function(after,'plan_for_disc')
assign={n.targets[0].id:n.value for n in after.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)}
assert ast.literal_eval(assign['NAME'])=='NFL 2K5 MOD TEST 2026-09-16p (down label fix)'
assert ast.literal_eval(assign['OPTIONS'])==('scorebug','scorebug_runtime','modern_color','modern_arrowhead','widescreen')
compile(after,str(OUT/'build_testdisc71.py'),'exec')
paths=['mod_editor/core/nfl2k5_scorebug_runtime.py','tools/scorebug_sprite/runtime.c','mod_editor/core/nfl2k5_scorebug_ingame.py','mod_editor/core/nfl2k5_scorebar_v3.py']
unchanged={}
for path in paths:
 old=subprocess.check_output(['git','show','02bbadd1:'+path],cwd=ROOT);now=(ROOT/path).read_bytes();assert old==now;unchanged[path]=hashlib.sha256(now).hexdigest()
# Generated owner source/module are unchanged too; pin the actual relocatable machine code.
code,labels=owner.code_for(0,0)
result=dict(builder_prepared_only=True,builder_name=ast.literal_eval(assign['NAME']),plan_function_identical_to_disc_n=True,options=list(ast.literal_eval(assign['OPTIONS'])),unchanged_sources=unchanged,owner_bytes=len(code),owner_sha256=hashlib.sha256(code).hexdigest(),owner_labels=labels,volume=s.probe_sizes(),native_gpu_unwitnessed=True)
(OUT/'delivery_inputs.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
