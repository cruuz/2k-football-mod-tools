"""Inspect the prepared builder and its immutable plan; do not call main/build."""
from pathlib import Path
import ast,dataclasses,hashlib,importlib.util,json
p=Path(__file__).with_name('build_testdisc71.py')
ast.parse(p.read_text())
spec=importlib.util.spec_from_file_location('prepared_s5_builder',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
plan=m.plan_for_disc()
assert m.NAME=='NFL 2K5 MOD TEST 2026-09-15m (sprite scorebug + everything)'
assert all(getattr(plan,k) for k in m.OPTIONS)
assert 'scorebug-sprite-v1' in p.read_text()
result=dict(builder_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),name=m.NAME,plan=dataclasses.asdict(plan),builder_run=False,disc_built=False)
p.with_name('prepared-builder.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
