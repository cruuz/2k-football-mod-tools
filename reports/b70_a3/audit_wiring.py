"""Check the A3 handoff against the exact input stack without private evidence."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = 'ded9c222a7df40c2e2d9b69c37c6464f72fc8fb4'


def original(path):
    return subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)


def method(source, name):
    tree = ast.parse(source)
    node, = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name]
    return ast.dump(node, include_attributes=False)


brief = (ROOT / 'WIRING_B70_T2.md').read_text()
texts = re.findall(r'```text\n(.*?)\n```', brief, re.S)
old, witness, equipment, evidence, route, stadium = texts[1:]
path = 'mod_editor/capabilities/registry.v1.json'
baseline = json.loads(original(path))
expected = deepcopy(baseline)
for row in expected['capabilities']:
    if row['id'] in ('nfl2k5.textures.all_p8', 'nfl2k5.uniforms.all_visual'):
        row['input_constraints'] = [entry.replace(old, witness) for entry in row['input_constraints']]
        row['input_constraints'].append(equipment)
        row['runtime']['scope'] += ' ' + witness
        for entries in (row['evidence'], row['runtime']['evidence']):
            entries.extend(evidence.splitlines())
    if row['id'] == 'nfl2k5.uniforms.all_visual':
        row['input_constraints'] = [route if entry.startswith('The Stadium texture route accepts an exact 64x64 RGBA8 PNG only')
                                    else entry for entry in row['input_constraints']]
    if row['id'] in ('nfl2k5.uniforms.all_visual', 'nfl2k5.stadiums_fields.blender_textures'):
        row['input_constraints'].append(stadium)
        for entries in (row['evidence'], row['runtime']['evidence']):
            entries.extend(['tests/mod_editor/test_b70_t2_stadium.py', 'reports/b70_t2/stadium-banners.json'])
assert json.loads((ROOT / path).read_text()) == expected
assert len(expected['capabilities']) == len(baseline['capabilities']) == 174

preserved = [
    'mod_editor/core/nfl2k5_uniform_equipment_writer.py', 'mod_editor/core/nfl2k5_equipment_lz.py',
    'mod_editor/studio/facade.py', 'mod_editor/core/build_feedback.py',
    'tools/nfl2k5_visual_mod_project.py', 'WIRING.md',
    'tests/mod_editor/test_b70_t1_build_speed.py',
    'tests/mod_editor/test_phase1_packaging.py', 'tests/mod_editor/test_product_catalog.py',
    'tests/mod_editor/test_b68_a1_audit.py', 'tests/mod_editor/test_apf_studio_installer.py',
    'packaging/check_apf2k8_mod_studio_runtime.py', 'data/nfl2k5_cave_reservations.json',
]
for path in preserved:
    assert (ROOT / path).read_bytes() == original(path), path
for path, name in [('mod_editor/core/nfl2k5_build_service.py', 'summarize_kept_retail'),
                   ('mod_editor/gui/studio_qt.py', '_choose_build_output')]:
    assert method((ROOT / path).read_text(), name) == method(original(path), name)
# The shared runtime checker may change only its SHA-256 literals.
path = 'packaging/check_2k5_mod_studio_runtime.py'
strip_hashes = lambda text: re.sub(r'[0-9a-f]{64}', '<HASH>', text)
assert strip_hashes((ROOT / path).read_text()) == strip_hashes(original(path).decode())
allowlist = 'packaging/release-allowlist.txt'
assert (ROOT / allowlist).read_text() == original(allowlist).decode().replace(
    'mod_editor/core/equipment_palette.py\n', 'mod_editor/core/equipment_palette.py\n' + texts[0] + '\n')

changed = subprocess.check_output(['git', 'diff', BASE, '--name-only'], cwd=ROOT, text=True).splitlines()
for path in changed:
    lower = path.lower()
    assert not any(part in lower for part in ('scorebug', 'scorebar_v3', 'modern_color')), path

def missing(data):
    return sorted({path for row in data['capabilities']
                   for path in row['evidence'] + row['runtime']['evidence']
                   if not (ROOT / path).is_file()})

assert missing(baseline) == missing(expected)
print(json.dumps(dict(
    result='A3_WIRING_AUDIT_PASS', base=BASE, registry_rows=174,
    registry_exact_strings_and_appended_evidence=True, registry_runtime_statuses_preserved=True,
    capability_count_pins_preserved=True, scorebug_modern_color_files_untouched=True,
    preserved_files=preserved, t1_summary_and_completion_consumers_preserved=True,
    missing_baseline_evidence_count=len(missing(expected)),
    missing_baseline_evidence=missing(expected),
    equipment_writer_sha256=hashlib.sha256(original('mod_editor/core/nfl2k5_uniform_equipment_writer.py')).hexdigest(),
    in_game_outcomes='UNWITNESSED'), indent=2))
