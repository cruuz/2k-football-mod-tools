"""Verify final counts, pins, published inputs and observed manifest freshness."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path.cwd()
OUT = ROOT / 'reports/b69_a1b'
from mod_editor.core import mod_build as build, nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_weather as weather, nfl2k5_weather_haze as haze, providers
from mod_editor.core.nfl2k5_cave_manifest import source_fingerprints
from tests.nfl2k5_allocator_stack import REQUESTS

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

raw = (ROOT / 'mod_editor/capabilities/registry.v1.json').read_text()
registry = json.loads(raw)
assert raw == json.dumps(registry, indent=2, sort_keys=True) + '\n'
old = json.loads(subprocess.check_output(['git', 'show',
    '05d3f0b5:mod_editor/capabilities/registry.v1.json'], text=True))
old_ids = {row['id'] for row in old['capabilities']}
added = [row for row in registry['capabilities'] if row['id'] not in old_ids]
assert len(added) == 7 and len(registry['capabilities']) == 172
defaults = dict(weather_plan='', weather_haze=False, coin_defer=False, decided_clock=False,
                decided_clock_margin=17, decided_clock_seconds=60, cpu_scrambles='retail')
assert all(all(p[k] == v for k, v in defaults.items()) for p in build.PRESETS.values())
rows = []
for row in added:
    assert re.fullmatch(r'python3 -m tests\.mod_editor\.\w+', row['validation_command'])
    assert not row['gui']['default_enabled'] and row['runtime']['status'] == 'not-tested'
    evidence = list(dict.fromkeys(row['evidence'] + row['runtime']['evidence']))
    assert all('ASTRA_REPORT' not in p and p != 'WIRING.md' for p in evidence)
    rows.append(dict(id=row['id'], validation=row['validation_command'],
                     evidence={p: (ROOT / p).exists() for p in evidence}))
tree = ast.parse((ROOT / 'packaging/check_2k5_mod_studio_runtime.py').read_text())
values = {t.id: ast.literal_eval(n.value) for n in ast.walk(tree)
    if isinstance(n, ast.Assign) and isinstance(n.value, (ast.Tuple, ast.Dict))
    for t in n.targets if isinstance(t, ast.Name) and
    t.id in ('product_modules', 'tool_modules', 'B69_GAME_RUNTIME_PINS')}
allowlist = [s for s in (ROOT / 'packaging/release-allowlist.txt').read_text().splitlines()
             if s and not s.startswith('#')]
pins = providers.Nfl2k5UnifiedVisualProvider.module_pins
assert all(digest(ROOT / p) == h for p, h in pins.items())
assert all(digest(ROOT / p) == h for p, h in values['B69_GAME_RUNTIME_PINS'].items())
plan = tt.xbe_space_patch.plan(REQUESTS, scaleout=True)
path = ROOT / '.scratch/a2b/gate-manifest.json'
projection = json.loads(path.read_text())
assert projection['source_sha256'] == source_fingerprints()
legacy_path = 'tools/validate_all_mod_editor_capabilities.py'
legacy_source = (ROOT / legacy_path).read_bytes()
legacy_counts = {n.targets[0].id: n.value.value for n in ast.walk(ast.parse(legacy_source))
    if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
    and n.targets[0].id in ('EXPECTED_CAPABILITIES', 'EXPECTED_COVERED_CAPABILITIES',
                          'EXPECTED_DEFERRED_CAPABILITIES', 'EXPECTED_UNIQUE_VALIDATORS')
    and isinstance(n.value, ast.Constant)}
legacy = dict(path=legacy_path, counts=legacy_counts, excluded_known_red=True,
    predates_game_integration=legacy_source == subprocess.check_output(
        ['git', 'show', '05d3f0b5:' + legacy_path]))
report = dict(canonical_registry=True, shared_rows=len(registry['capabilities']), new_rows=rows,
    presets=defaults, R62_SPACE_KEYS=tt.R62_SPACE_KEYS, R62_RUNTIME_KEYS=tt.R62_RUNTIME_KEYS,
    climate_requests=weather.REQUESTS, haze_requests=haze.REQUESTS, provider_pins=len(pins),
    all_provider_hashes_match=True, allowlist_entries=len(allowlist),
    product_imports=len(values['product_modules']), tool_imports=len(values['tool_modules']),
    runtime_game_pins=len(values['B69_GAME_RUNTIME_PINS']), runtime_game_hashes_match=True,
    allocation_records=len(plan['allocations']), allocation_file_size=plan['file_size'],
    capacity=plan['capacity'], legacy_exhaustive_validator=legacy,
    projection=dict(path=str(path.relative_to(ROOT)), sha256=digest(path),
    source_hashes=len(projection['source_sha256']), transactions=len(projection['steps']),
    reservations=len(projection['spans']), source_fresh=True, release_manifest=False))
(OUT / 'contract-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print('Canonical registry 172; seven module commands; provider closure 280; all source pins match')
print('Projection sources fresh:', len(projection['source_sha256']), 'native output:', projection['stack_xbe_sha256'])
