"""Audit capability unions, every count pin, S4 allocation and builder intent."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]

def registry(rev):
    return json.loads(subprocess.check_output(['git', 'show', rev + ':mod_editor/capabilities/registry.v1.json']))['capabilities']

rows = json.loads((ROOT / 'mod_editor/capabilities/registry.v1.json').read_text())['capabilities']
a6, s4 = ({r['id']: r for r in registry(rev)} for rev in ('07c544a2', '7b54e354'))
current = {r['id']: r for r in rows}
assert len(rows) == len(current) == 176
assert set(current) == set(a6) | set(s4)
assert all(r == (s4 if key == 'nfl2k5.scorebug_presentation.runtime' else a6)[key] for key, r in current.items())
pins = {
    'packaging/check_2k5_mod_studio_runtime.py': ['len(registry.capabilities) == 176', 'len(product_catalog.capabilities) == 102', 'registry=176 sections=12 nfl2k5_capabilities=102'],
    'packaging/check_apf2k8_mod_studio_runtime.py': ['len(registry.capabilities) == 176', '== 73', 'len(cards) == 73'],
    'tests/mod_editor/test_b68_a1_audit.py': ['len(registry.capabilities), 176', 'len(catalog.capabilities), 102', 'registry=176 sections=12 nfl2k5_capabilities=102'],
    'tests/mod_editor/test_phase1_packaging.py': ['registry=176 sections=12 nfl2k5_capabilities=102'],
    'tests/mod_editor/test_apf_studio_installer.py': ['len(registry.capabilities) == 176'],
    'tests/mod_editor/test_product_catalog.py': ['(102, 80, 8, 1, 0, 10, 3)', 'nfl2k5.stadiums_fields.modern_arrowhead', 'self.assertEqual(set(first_ids), expected)'],
    'tests/mod_editor/test_provider_integrity.py': ['[288, 10, 8, 9, 8, 9]'],
    'tools/validate_all_mod_editor_capabilities.py': ['EXPECTED_CAPABILITIES = 176', 'EXPECTED_COVERED_CAPABILITIES = 171', 'EXPECTED_DEFERRED_CAPABILITIES = 5', 'EXPECTED_UNIQUE_VALIDATORS = 129'],
}
locations = []
for path, anchors in pins.items():
    lines = (ROOT / path).read_text().splitlines()
    for anchor in anchors:
        hits = [i for i, line in enumerate(lines, 1) if anchor in line]
        assert hits, (path, anchor)
        locations.append(dict(path=path, line=hits[0], anchor=anchor))
evidence = json.loads((ROOT / 'reports/b71_s4/evidence_hydration.json').read_text())
for row in evidence:
    p = ROOT / row['path']
    assert p.stat().st_nlink == 1
    assert len(p.read_bytes()) == row['bytes']
    assert hashlib.sha256(p.read_bytes()).hexdigest() == row['sha256']
b = ROOT / 'reports/b71_a7/build_testdisc71.py'
tree = ast.parse(b.read_bytes()); compile(tree, str(b), 'exec')
values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
          if isinstance(node, ast.Assign) and len(node.targets) == 1
          and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('NAME', 'OPTIONS')}
assert values['NAME'] == 'NFL 2K5 MOD TEST 2026-09-15k (everything + painted bar)'
options = ('scorebug', 'scorebug_runtime', 'modern_color', 'modern_arrowhead', 'widescreen')
assert values['OPTIONS'] == options
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'replace' and isinstance(n.func.value, ast.Name) and n.func.value.id == 'dataclasses']
assert len(calls) == 1
assert {k.arg: ast.literal_eval(k.value) for k in calls[0].keywords} == dict.fromkeys(options, True)
source = b.read_text()
assert "'softdrink_advanced'" in source and "'scorebug-mnf-2026-v4'" in source
assert source.index('NamedTemporaryFile(') < source.index('while len(images) >= 3:')
assert source.index('if disc.exists() or patch.exists():') < source.index('oldest.unlink()')
assert source.index('disc_verified = True') < source.index('modpack.export(')
assert 'for name, identity in patches_before.items():' in source
from mod_editor.core import nfl2k5_scorebug_runtime as owner
assert len(owner.code_for(0, 0)[0].rstrip(b'\xcc')) == 1380
assert (owner.CODE_SIZE, owner.DATA_SIZE) == (1408, 128)
result = dict(registry_total=176, exact_union=True, exact_rows=True,
              pin_locations=locations, evidence_files=len(evidence),
              evidence_bytes=sum(r['bytes'] for r in evidence),
              builder_name=values['NAME'], builder_options=options,
              builder_executed=False, builder_sha256=hashlib.sha256(b.read_bytes()).hexdigest(),
              code_bytes=1380, code_budget=1408, data_bytes=128, requests=owner.REQUESTS)
(ROOT / 'reports/b71_a7/pin-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
