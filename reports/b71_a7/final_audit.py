"""Require complete final gate receipts and unchanged product sources."""
from pathlib import Path
import hashlib
import json
import re
import sys
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
expected = set()
for group in ('fast', 'presentation', 'apf', 'closure_units'):
    prefix = 'delivery-' if group == 'closure_units' else 'final-'
    batch = prefix + group if group == 'closure_units' else group
    expected.update(prefix + Path(p).stem for p in json.loads((OUT / (batch + '-suite-paths.json')).read_text()))
    expected.add(group + '-reconciled' if group in ('presentation', 'apf') else batch + '-suites')
expected.discard('final-nfl2k5_scorebug_layout_test')
expected.add('delivery-scorebug-layout-emulation')
expected.discard('final-test_apf_studio_installer')
expected.add('delivery-test_apf_studio_installer')
expected.discard('final-nfl_uniform_color_patch_test')
expected.add('delivery-nfl_uniform_color_patch_test')
expected.update('final-' + name for name in ('test_nfl2k5_cave_oracle', 'test_nfl2k5_allocator_scaleout', 'test_xbe_patch_memory_writes', 'test_xbe_patch_cave_references', 'test_nfl2k5_owner_pairwise_composition', 'colour-all-pins'))
expected.update(('registry-strict', 'validation-plan', 'pin-audit-delivery', 'volume', 'manifest-projection-provider-closure', 'repin-provider-closure', 'closures'))
expected.update(step + '-' + product + '-final' for product in ('2k5', 'apf') for step in ('stage', 'release', 'runtime'))
results = {p.name.removesuffix('.result.json'): json.loads(p.read_text()) for p in OUT.glob('*.result.json')}
assert not (expected - results.keys()), ('missing', sorted(expected - results.keys()))
failed = {k: results[k]['exit_code'] for k in expected if results[k]['exit_code']}
assert not failed, failed
frozen = json.loads((OUT / 'product-frozen.json').read_text())
changed = [p for p, h in frozen.items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h]
assert not changed, changed
from mod_editor.core.nfl2k5_cave_manifest import source_fingerprints
path = ROOT / 'data/nfl2k5_cave_reservations.json'
manifest = json.loads(path.read_bytes())
assert manifest['source_sha256'] == source_fingerprints()
projection = manifest['b71_a7_projection']
assert projection['release_manifest'] is False and projection['disc_built'] is False
assert projection['runtime_witnessed'] is False and projection['production_regeneration_required'] is True
assert projection['parent_manifest_sha256'] == 'bbc7b1afd93bd4e0c7cabb02452d54e7ac05e6fe6e0d26d4ffdaf381a5368315'
assert len(projection['observed_steps']) == 138
assert path.stat().st_mtime_ns >= max((ROOT / p).stat().st_mtime_ns for p in frozen)
assert not (OUT / 'build-receipt').exists()
assert results['manifest-production']['exit_code'] == 1
assert 'Read-only file system' in (OUT / 'manifest-production.log').read_text()
volume = json.loads((OUT / 'volume.json').read_text())
assert volume['total_appended_bytes'] == 410624
cases = 0
skips = {}
for key in sorted(expected):
    log = (OUT / (key + '.log')).read_text()
    matches = re.findall(r'Ran (\d+) tests? in', log)
    if matches:
        cases += int(matches[-1])
    lines = [line for line in log.splitlines() if ' ... skipped ' in line]
    if lines:
        skips[key] = lines
receipt = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size,
               reservations=len(manifest['spans']), source_count=len(manifest['source_sha256']),
               observed_steps=len(projection['observed_steps']), stack_xbe_sha256=manifest['stack_xbe_sha256'],
               release_manifest=False, disc_built=False, runtime_witnessed=False,
               production_regeneration_required=True,
               scorebug_allocations=[a for a in manifest['allocator_layout']['allocations'] if a['owner'] == 'nfl2k5_scorebug_runtime'])
(OUT / 'manifest-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
summary = dict(required_completed=len(expected), all_requested_suites_and_closures_exit_zero=True,
               unittest_cases=cases, skips=skips, manifest_source_seals_match=True,
               manifest_last_product_change=True, product_paths_frozen=len(frozen),
               builder_executed=False, manifest=receipt)
(OUT / 'final-audit.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
