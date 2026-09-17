"""Parse the prepared build, without importing or running it."""
import ast
from pathlib import Path
p=Path(__file__).with_name('build_testdisc71.py');before=p.parents[1]/'b71_s9/build_testdisc71.py'
a=ast.parse(before.read_text());b=ast.parse(p.read_text())
plan=lambda tree:next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='plan_for_disc')
assert ast.dump(plan(a))==ast.dump(plan(b))
name=next(ast.literal_eval(n.value) for n in b.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NAME' for t in n.targets))
assert name=='NFL 2K5 MOD TEST 2026-09-16q (down label cause fix)'
compile(b,str(p),'exec')
print('Prepared only; not imported or run. Plan AST unchanged from S9. '+name)
