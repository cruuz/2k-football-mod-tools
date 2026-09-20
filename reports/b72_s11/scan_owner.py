"""Focused changed-owner memory, allocation, composition and inventory audit."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes, ReservationManifest, DEFAULT_MANIFEST
from tests.mod_editor import test_nfl2k5_owner_pairwise_composition as pairs

OUT = Path(__file__).resolve().parent
retail = pairs.retail_xbe()
patched, receipt = owner.apply(retail)
assert owner.apply(patched)[0] == patched
code, data = owner.sites(patched)
image = XbeImage(patched)
assert not image.runtime_writable(code['va'], code['size'])
assert image.runtime_writable(data['va'], data['size'])
writes = absolute_writes(patched, [(code['va'], code['va'] + code['size'])])
assert all(w['writable'] for w in writes if w['target'] is not None)
manifest = ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(retail))
for va, old in owner.HOOKS.values():
    assert manifest.overlaps(va, va + len(old))
    assert not manifest.overlaps(va, va + len(old), exclude_owner=owner.OWNER)

unchanged = {}
for folder in ('data/nfl2k5_cave_reservations.json', 'reports/b72_s6', 'reports/b72_s7'):
    changed = subprocess.check_output(['git', 'diff', 'c3b3b53a2', '--', folder], cwd=ROOT)
    assert not changed
    unchanged[folder] = True
stale = None
try:
    ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(retail), source_root=ROOT)
except ValueError as exc:
    stale = str(exc)
result = dict(rx_used=len(owner.code_for(code['va'], data['va'])[0].rstrip(b'\xcc')),
    code=code, data=data, absolute_writes=writes, unchanged=unchanged,
    source_manifest_check=stale or 'PASS', manifest_regeneration_owner='integrator',
    idempotent=True, hook_ownership=True,
    allowlist_entries={p:p in (ROOT/'packaging/release-allowlist.txt').read_text().splitlines() for p in (
        'mod_editor/core/nfl2k5_scorebug_sprite_code.py', 'mod_editor/core/providers.py')},
    development_only=['tools/scorebug_sprite/runtime.c',
                      'tests/mod_editor/test_nfl2k5_scorebug_down_visibility.py'])
assert all(result['allowlist_entries'].values())
(OUT/'owner_scan.json').write_text(json.dumps(result,indent=2)+'\n')
names = [n for n in unittest.defaultTestLoader.getTestCaseNames(pairs.PairwiseCompositionTests)
         if 'scorebug_runtime' in n]
suite = unittest.TestSuite(pairs.PairwiseCompositionTests(n) for n in names)
run = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not run.wasSuccessful())
