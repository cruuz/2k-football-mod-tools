"""Index every A2b-added hunk, including merge resolutions and evidence files."""
from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess

OUT = Path('reports/b69_a1b')
patch = subprocess.check_output(['git', 'diff', '--find-renames', 'b5949335', 'c2489fca'], text=True)
(OUT / 'integration-full.patch').write_text(patch)
descriptions = {
 'mod_editor/core/mod_build.py': [
  'J5 five BuildPlan fields, False/17/60/Retail defaults',
  'J4 climate path and haze boolean', 'J4/J5 wants_xbe_patch: haze/rules, climate data only',
  'J4/J5 BASIC explicitly Off/Retail', 'J4/J5 ADVANCED explicitly Off/Retail',
  'J4/J5 EXPERIMENTAL explicitly Off/Retail', 'J4 module availability',
  'J5 module/allocator availability', 'J5 inspect states and installed settings',
  'J4 climate requires image default', 'J4 bounded ROST inspect', 'J4 haze status inspect',
  'J4 strict weather types and stripped path', 'J5 preflight allocator predicate',
  'J3 generic/prepared tier enables depth locks',
  'J5 full source settings check before deferred copy/project work',
  'J4 climate validation/frozen final-pass document and haze source checks',
  'J4/J5 defer haze and allocation-dependent rules in initial pass',
  'J5 final allocator predicate', 'J4 haze after helmet, before composed inspect, Off restores',
  'J4 climate after final ESPN/resource pass; reparse before publication'],
 'mod_editor/core/nfl2k5_throw_tuning.py': [
  'J5 imports', 'J5 three space and five runtime keys',
  'J5 explicit Retail enum deferral and validator signature', 'J5 option domains',
  'J5 selection signature and validator forwarding', 'J5 complete REQUESTS union',
  'J5 allocator adapter signature/forwarding/scaleout', 'J5 clock adapter and status/settings helper',
  'J5 grown status projection', 'J5 extracted complete-plan installed-settings check',
  'J5 _apply_all settings signature', 'J5 private deferred-settings flag',
  'J5 defer only intermediate installed-setting validation', 'J5 final allocation predicate',
  'J5 install coin, clock, scrambles immediately after accelerated clock',
  'J5 bare-XBE entrypoint signature', 'J5 bare-XBE work predicate',
  'J5 image entrypoint signature', 'J5 explain complete-plan preflight before partial pass',
  'J5 image work predicate', 'J5 complete-plan preflight and unchanged intermediate replay'],
 'mod_editor/gui/build_panel_qt.py': [
  'J5 cutoff and Retail/Modern selectors, defaults, accessible labels',
  'J4 climate choose/editor/status and reversible haze controls',
  'J4 source gates, climate reset and installed haze projection',
  'J5 preset reset of cutoff and scramble selectors', 'J4 boolean/path control map',
  'J4 plan path/haze fields', 'J5 plan cutoff/enum values', 'J4/J5 has_work predicates',
  'J4/J5 selected labels, cutoff values and explicit haze restoration', 'J4 climate blocker',
  'J5 installed settings lock and enum source gating; source-reset omission D1',
  'J4 editor launch/save signal and bounded climate preflight helper', 'J4 confirmation plan basename'],
 'mod_editor/gui/gameplay_patches_panel_qt.py': [
  'J4/J5 rows; climate path and scramble enum are informational, never booleans',
  'J4/J5 exact captions/help', 'J4/J5 full-disc gates', 'J4 weather navigation signal',
  'J4/J5 weather editor action and Retail/Modern enum', 'J5 cutoff selectors',
  'J4 reversible haze source state', 'J5 plan cutoff/enum projection',
  'J4/J5 installed locks, source gating and has_work; source-reset omission D1',
  'J4/J5 selection helpers and standalone weather-editor fallback',
  'J4/J5 actionable selection/confirmation including restoration and cutoff'],
 'mod_editor/gui/my_career_panel_qt.py': [
  'J3 prospects import', 'J3 honest MyCareer page description',
  'J3 tier/prototype controls and tier-owned starting depth place',
  'J3 saved caller choices, retail default and help', 'J3 prototype aliases/Pocket default',
  'J3 load caller and Supersim together', 'J3 capture caller on export',
  'J3 one signed write_settings export', 'J3 disable caller while working',
  'J3 restore caller availability after work', 'J3 pass prospect tier to creation'],
 'mod_editor/gui/gameplay_project_ui.py': [
  'J5 restore cutoff/enum', 'J4 restore climate path', 'J5 bidirectional combo signals',
  'J5 bidirectional combo values'],
 'mod_editor/core/nfl2k5_cave_manifest.py': [
  'J4 reserve all four coefficient bytes including unchanged bytes',
  'J4/J5 recorder imports', 'J4/J5 recorder module closure',
  'J5 dormant complete allocation union', 'J4/J5 dormant writer applications',
  'J4/J5 synthetic replay list', 'J4/J5 status verification list', 'J4/J5 extra owner list'],
 'mod_editor/core/providers.py': ['J3/J5 eight added dependency pins',
  'J5 dispatcher pin', 'J4/J5 saved settings pin', 'J3/J4/J5 mod_build pin'],
 'packaging/check_2k5_mod_studio_runtime.py': ['J4 studio source pin',
  'J3/J4/J5 separate weather/UI/tool runtime pins',
  'J3/J4/J5 executable runtime contract: pins/defaults/controls',
  'J3/J4/J5 fourteen additional imports', 'J3/J4/J5 execute runtime contract',
  'J3/J4/J5 shared registry 172 and 2K5 catalog 99 assertions',
  'J3/J4/J5 printed shared registry/catalog pins'],
 'tests/nfl2k5_allocator_stack.py': ['J4 haze import', 'J4 haze composed owner',
  'J4 full four-byte reservation only after other-owner overlap refusal'],
 'tests/mod_editor/test_product_catalog.py': ['J3/J4/J5 exact seven new IDs',
  'J3/J4/J5 99 unique rows', 'J3/J4/J5 stadium/menu/gameplay section totals',
  'J3/J4/J5 total tuple (99,77,8,1,0,10,3)', 'J3/J4/J5 provider binding count'],
}
exact_files = {
 'mod_editor/gui/my_career_panel_qt.py', 'mod_editor/core/providers.py',
 'mod_editor/gui/beta62_options.py', 'packaging/release-allowlist.txt',
 'packaging/check_apf2k8_mod_studio_runtime.py', 'tests/mod_editor/test_phase1_packaging.py',
 'tests/mod_editor/test_apf_studio_installer.py', 'tests/mod_editor/test_provider_integrity.py',
 'tests/mod_editor/test_product_catalog.py', 'tests/nfl2k5_allocator_stack.py',
 'tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py',
 'mod_editor/core/nfl2k5_cave_manifest.py',
}
special = {
 'mod_editor/core/nfl2k5_build_settings.py': 'J4/J5 explicit FEATURE_KEYS; actual serializer requires this beyond the J4 dataclass assumption',
 'mod_editor/gui/beta62_options.py': 'J5 exact two boolean captions/help; CPU scrambles remains an enum',
 'mod_editor/gui/studio_qt.py': 'J4 existing Gameplay weather signal opens Build weather editor',
 'packaging/release-allowlist.txt': 'J3/J4/J5 ten core sources, four tools, two research docs; no compiler/emulator dependency',
 'packaging/check_apf2k8_mod_studio_runtime.py': 'J3/J4/J5 shared registry 172; APF product unchanged',
 'tests/mod_editor/test_apf_studio_installer.py': 'J3/J4/J5 shared registry 172',
 'tests/mod_editor/test_phase1_packaging.py': 'J3/J4/J5 shared registry 172 and 2K5 catalog 99',
 'tests/mod_editor/test_provider_integrity.py': 'J3/J5 combined exact unified closure 280',
 'tests/mod_editor/test_nfl2k5_my_career_panel.py': 'J3 four QB labels sharing three native styles, Pocket default',
 'tests/mod_editor/test_nfl2k5_my_career_b69_wiring.py': 'J3 run integrated panel/build source, preserve original proposed-panel generator',
 'tests/mod_editor/test_b69_a2b_game_wiring.py': 'J3/J4/J5 additional compact image, option, replay, refusal and UI evidence',
 'tests/mod_editor/test_nfl2k5_simulated_windows_build.py': 'J3/J4/J5 additional existing non-POSIX shim/Experimental composition proof',
 'tests/mod_editor/test_gameplay_patches_panel_qt.py': 'J4/J5 align row/caption/foreign-source expectations',
 'tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py': 'J4 haze added to pair matrix',
 'tests/mod_editor/test_nfl2k5_playbook_pair_manifest.py': 'J5 common helper excluded from double attribution; calling owner still recorded',
 'mod_editor/capabilities/registry.v1.json': 'J3/J4/J5 canonical rows and existing MyCareer evidence; exact field differences in registry-deviations.json',
 'tools/mycareer_mode/b69_registry_rows.json': 'J3 handoff paths/integration wording match renamed report and applied UI',
}
rows, counts = [], defaultdict(int)
path = ''
for line, text in enumerate(patch.splitlines(), 1):
    if text.startswith('+++ b/'):
        path = text[6:]
    if not text.startswith('@@ '):
        continue
    counts[path] += 1
    n = counts[path]
    desc = descriptions.get(path, [])[n - 1] if path in descriptions else special.get(path)
    verdict = 'applied exactly' if path in exact_files else 'documented deviation'
    if path in ('mod_editor/core/mod_build.py', 'mod_editor/core/nfl2k5_throw_tuning.py', 'mod_editor/gui/build_panel_qt.py'):
        verdict = 'applied exactly'
    if (path == 'mod_editor/core/mod_build.py' and n == 16) or (
        path == 'mod_editor/core/nfl2k5_throw_tuning.py' and n in (10, 12, 13, 19, 21)):
        verdict = 'documented deviation'
    if desc and 'omission D1' in desc:
        verdict = 'wrong'
    if path.startswith('reports/'):
        desc = 'J3/J4/J5 generated A2b evidence/log/patch artifact; historical observations, independently rerun by A1b'
    if path.startswith(('WIRING_', 'ASTRA_B69_J')):
        desc = 'Job handoff report/wiring links retargeted after rename; original handoff status retained'
    if path == 'ASTRA_B69_A2B_REPORT.md':
        desc = 'A2b integration handoff; clear-button claim exceeds actual controls (D5), other results independently checked'
        verdict = 'wrong'
    assert desc, path
    job = '/'.join(j for j in ('J3', 'J4', 'J5') if j in desc) or 'J3/J4/J5'
    rows.append(dict(id=f'H{len(rows)+1:03}', job=job, file=path, file_hunk=n,
                     diff_line=line, hunk=text, verdict=verdict, review=desc))
for path, values in descriptions.items():
    assert counts[path] == len(values), (path, counts[path], len(values))
(OUT / 'integration-hunks.json').write_text(json.dumps(rows, indent=2) + '\n')
lines = ['# Independent A2b hunk ledger', '',
 'Diff base `b5949335` is the completed J4/J3/J5 merge union. Final A2b head is `c2489fca`.',
 'Every hunk below links to its full before/after diff. Merge-only resolutions are separately recorded in',
 '`j3/j4/j5-merge-resolution.patch`; job-owned final deltas are in `j3/j4/j5-job-to-stack.patch`.',
 '“Applied exactly” means the WIRING behavior is preserved, including mechanically forwarded parameters.',
 '“Documented deviation” identifies A2b adapters/evidence needed by the actual integrated tree.',
 '“Wrong” rows have findings in ASTRA_REPORT.md. Missing hunks (old pins/fixtures) appear there too.', '',
 '| ID | Job | File / hunk | Verdict | Review |', '| --- | --- | --- | --- | --- |']
for row in rows:
    lines.append(f"| {row['id']} | {row['job']} | [{row['file']} #{row['file_hunk']}](integration-full.patch#L{row['diff_line']}) | {row['verdict']} | {row['review']} |")
(OUT / 'integration-hunks.md').write_text('\n'.join(lines) + '\n')
print('Indexed', len(rows), 'hunks in', len(counts), 'files')
