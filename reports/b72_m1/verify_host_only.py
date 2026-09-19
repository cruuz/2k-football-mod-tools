"""Prove b72-m1 changes no default XBE bytes; derive a gate-only source repin.

No release manifest is edited. The gate copy retains all spans and allocation
receipts, updating only source pins proved here to emit the same XBE bytes.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BASE = '088e3f41'
from mod_editor.core import nfl2k5_my_career as career
from mod_editor.core import nfl2k5_my_career_prospects as prospects
from mod_editor.core import nfl2k5_my_career_mode as mode
from tests.nfl2k5_my_career_fixture import XBE


def base_module(name):
    path = 'mod_editor/core/' + name + '.py'
    module = types.ModuleType('mod_editor.core.' + name + '_base_probe')
    module.__package__ = 'mod_editor.core'
    source = subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)
    exec(compile(source, path, 'exec'), module.__dict__)
    return module


def main():
    old = base_module('nfl2k5_my_career')
    old_prospects = base_module('nfl2k5_my_career_prospects')
    retail = XBE.read_bytes()
    before = old.apply(retail)[0]
    after = career.apply(retail)[0]
    assert before == after, 'MyCareer XBE output changed'
    # The native menu compiler reads the prospects policy. Exercise it with
    # both versions, not merely the same already-imported policy twice.
    package = sys.modules['mod_editor.core']
    sys.modules['mod_editor.core.nfl2k5_my_career_prospects'] = old_prospects
    package.nfl2k5_my_career_prospects = old_prospects
    try:
        mode_before = mode.apply(retail)[0]
    finally:
        sys.modules['mod_editor.core.nfl2k5_my_career_prospects'] = prospects
        package.nfl2k5_my_career_prospects = prospects
    mode_after = mode.apply(retail)[0]
    assert mode_before == mode_after, 'MyCareer mode XBE output changed'
    budget_path = 'tools/mycareer_mode/b69_budget.json'
    budget = (ROOT/budget_path).read_bytes()
    assert budget == subprocess.check_output(['git', 'show', BASE + ':' + budget_path], cwd=ROOT)
    path = ROOT/'data/nfl2k5_cave_reservations.json'
    document = json.loads(path.read_bytes())
    changed = {}
    allowed = {'mod_editor/core/nfl2k5_my_career.py', 'mod_editor/core/nfl2k5_my_career_prospects.py'}
    for name, digest in document['source_sha256'].items():
        current = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        if current == digest:
            continue
        assert name in allowed, name
        baseline = subprocess.check_output(['git', 'show', BASE + ':' + name], cwd=ROOT)
        assert hashlib.sha256(baseline).hexdigest() == digest, name
        changed[name] = {'before': digest, 'after': current}
        document['source_sha256'][name] = current
    result = {'base': BASE, 'mycareer_xbe_byte_identical': True, 'mode_xbe_byte_identical': True,
              'mycareer_xbe_sha256': hashlib.sha256(after).hexdigest(),
              'mode_xbe_sha256': hashlib.sha256(mode_after).hexdigest(),
              'b69_budget_byte_identical': True, 'b69_budget_sha256': hashlib.sha256(budget).hexdigest(),
              'parent_manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'source_pin_changes': changed, 'reservation_spans_unchanged': True}
    output = ROOT/'.scratch/b72-m1-gate-manifest.json'
    output.write_bytes((json.dumps(document, indent=2) + '\n').encode('utf-8'))
    (ROOT/'reports/b72_m1/host_only.json').write_bytes((json.dumps(result, indent=2) + '\n').encode('utf-8'))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
