"""PROVED OFFLINE: compare SM footprints to the stack head, without repinning a release manifest."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import nfl2k5_lineman_rating as lineman
from mod_editor.core import nfl2k5_scorebug_ingame as scorebar
from mod_editor.core import nfl2k5_scorebug_exact as exact
from test_nfl2k5_scorebug_runtime import XBE

BASE = '6bd9b3d66'
document = json.loads((ROOT / 'data/nfl2k5_cave_reservations.json').read_text())


def parent(name):
    path = 'mod_editor/core/' + name + '.py'
    code = subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)
    assert hashlib.sha256(code).hexdigest() == document['source_sha256'][path]
    module = types.ModuleType('mod_editor.core.sm_parent_' + name)
    module.__package__ = 'mod_editor.core'
    module.__file__ = str(ROOT / path)
    exec(compile(code, module.__file__, 'exec'), module.__dict__)
    return module


def covered(start, end):
    cursor = start
    for lo, hi in sorted((int(r['start'], 0), int(r['end'], 0)) for r in document['spans']):
        if lo <= cursor < hi:
            cursor = hi
    return cursor >= end


old_line = parent('nfl2k5_lineman_rating')
old_exact = parent('nfl2k5_scorebug_exact')
new_specs = scorebar.xbe_specs()
with patch.object(scorebar, 'exact', old_exact):
    old_specs = scorebar.xbe_specs()
assert [(va, old) for va, old, new, label in new_specs] == [(va, old) for va, old, new, label in old_specs]
changed = [hex(va) for (va, old, new, label), (_, _, was, _) in zip(new_specs, old_specs) if new != was]
assert changed == ['0xe6c4c4']
assert all(len(old) == len(new) and covered(va, va + len(new)) for va, old, new, label in new_specs)
assert [(label, va, old) for label, va, old, new in lineman.sites()] == [
    (label, va, old) for label, va, old, new in old_line.sites()]
assert all(covered(va, va + len(new)) for label, va, old, new in lineman.sites())
retail = XBE.read_bytes()
before, after = old_line.apply(retail)[0], lineman.apply(retail)[0]
assert len(before) == len(after)
assert lineman.revert(after)[0] == retail
stale = [p for p, h in document['source_sha256'].items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h]
assert set(stale) == {'mod_editor/core/nfl2k5_lineman_rating.py',
                      'mod_editor/core/nfl2k5_scorebug_exact.py',
                      'mod_editor/core/nfl2k5_scorebug_resources.py'}
result = dict(evidence='PROVED OFFLINE', base=BASE, release_manifest_regenerated=False,
              reservations_covered=True, allocation_requests_added=0,
              lineman_code_bytes=lineman.CODE_BYTES, lineman_cave_bytes=lineman.CAVE_SIZE,
              lineman_spans=[dict(label=l, va=hex(v), size=len(a)) for l, v, b, a in lineman.sites()],
              scorebar_changed_xbe_sites=changed, scorebar_site_extents_unchanged=True,
              stale_sources=stale, main_action='Regenerate the release cave manifest after integration; no disc build was run here.')
(Path(__file__).parent / 'reservations.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
