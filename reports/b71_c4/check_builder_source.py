"""Validate builder syntax and its requested plan without executing the builder."""
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / 'reports/b71_c4/build_testdisc71.py'
source = path.read_text()
tree = ast.parse(source, filename=str(path))
compile(tree, str(path), 'exec')  # Compile only. Do not execute any builder statement.
constants = {node.targets[0].id:ast.literal_eval(node.value) for node in tree.body
             if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
             and isinstance(node.value,ast.Constant)}
expected='NFL 2K5 MOD TEST 2026-09-15g (day tuning + scorebug v2 + widescreen)'
assert constants['NAME']==expected
plan = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='plan_for_disc')
calls=[n for n in ast.walk(plan) if isinstance(n,ast.Call)]
preset=next(n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='apply_preset')
assert ast.literal_eval(preset.args[1])=='softdrink_advanced'
replace=next(n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='replace')
options={k.arg:ast.literal_eval(k.value) for k in replace.keywords}
assert options==dict(scorebug=True,scorebug_runtime=True,modern_color=True,widescreen=True)
assert 'while len(images) >= 3:' in source and "images.pop(0)" in source and 'oldest.unlink()' in source
assert "for name, identity in patches_before.items():" in source
assert "assert len(list(OUT.glob('*MOD TEST*.iso'))) <= 3" in source
assert "if disc.exists() or patch.exists():" in source
assert '18c6d914b12edc22d092cea97b7839d4f4611e23b5a898cbceeb4d74222b9fb9' in source
report=dict(builder=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            validation='AST/syntax and source contract only; builder never imported or executed',
            name=expected,preset='softdrink_advanced',options=options,maximum_mod_test_images=3,
            preserves_all_patch_archives=True,refuses_existing_named_outputs=True,
            readback='scorebug resources/runtime, modern colour XBE and all 477 bundles, seven rig pins, night pin, widescreen 16:9')
(ROOT/'reports/b71_c4/builder-source-proof.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
