"""Summarize final, bounded default-path checks without counting initial runs."""
from pathlib import Path
import json
import re

OUT = Path(__file__).resolve().parent
rows = json.loads((OUT/'final_checks/results.json').read_text())
assert len(rows) == 35
for row in rows:
    log = (OUT/'final_checks'/(Path(row['file']).stem+'.log')).read_text()
    row['cases'] = int(re.search(r'Ran (\d+) tests?', log)[1])
    skips = re.search(r'OK \(skipped=(\d+)\)', log)
    row['skips'] = int(skips[1]) if skips else 0
assert all(r['exit_code'] == 0 and r['seconds'] < 100 for r in rows)
closures = json.loads((OUT/'closures.json').read_text())
assert len(closures) == 6 and all(r['exit_code'] == 0 for r in closures)
budget = json.loads((OUT/'budgets.json').read_text())
assert (budget['rx_used'], budget['rx_reserved'], budget['rw_reserved']) == (4076,4096,128)
assert {v['appended_bytes'] for v in budget['aspects'].values()} == {324832}
(OUT/'validation.json').write_text(json.dumps(rows,indent=2)+'\n')
lines = ['# b72-s8 final validation', '',
    f'All {len(rows)} required default-path test files pass: {sum(r["cases"] for r in rows)} cases, '
    f'{sum(r["cases"]-r["skips"] for r in rows)} executed and {sum(r["skips"] for r in rows)} existing skips. '
    'Every file finishes below 100 seconds. The final generated owner uses 4076 RX bytes.', '',
    '| File | Cases | Skips | Seconds | Exit |', '|---|---:|---:|---:|---:|']
for row in rows:
    name = Path(row['file']).stem
    lines.append(f'| [{name}](final_checks/{name}.log) | {row["cases"]} | {row["skips"]} | {row["seconds"]:.2f} | {row["exit_code"]} |')
lines += ['', 'Commands use plain python3 with PYTHONPATH=<repo> and QT_QPA_PLATFORM=offscreen. '
    'The unchanged reports/b72_s6/run_checks.py inventory runs with OUT redirected to reports/b72_s8/final_checks. '
    'Each standalone subprocess retains its 100-second timeout. No speed environment switch is needed.', '',
    'The visibility suite now has four tests, including 675 retained frames per aspect, stale flags in both directions, '
    'null bindings and the complete material mapping. Existing GPU tests retain all 52 team slots, both possessions '
    'and both aspects. Provider integrity passes all eight cases with the unchanged 301-entry import closure.', '',
    '| Product | Step | Seconds | Exit |', '|---|---|---:|---:|']
for row in closures:
    lines.append(f'| {row["app"]} | {["temporary stage", "release closure", "runtime closure"][row["step"]]} '
                 f'| {row["seconds"]:.2f} | {row["exit_code"]} |')
lines += ['', 'Closures reuse reports/b72_s6/run_closures.py with __file__ pointing into reports/b72_s8. '
    'Temporary stages are removed. No installer, release archive or disc is produced.', '',
    'Additional offline checks:', '',
    '- `python3 reports/b72_s8/prove.py`: PASS. 1350 retained frames and the rebuilt-owner captured-RAM replay. '
    'Label mean 120.10, white pixels 255, both aspect appendices 324832 bytes. See proof_final.log.',
    '- `python3 reports/b72_s8/check_base_regression.py`: PASS. The exact base owner fails the new stale-visibility '
    'assertion as expected; the final owner passes. See base_regression.log and base_regression.json.',
    '- `python3 reports/b72_s8/scan_owner.py`: PASS for RX/RW permissions, absolute write destinations, hook ownership, '
    'idempotency and all 31 composition pairs involving scorebug_runtime, in both orders. The auxiliary pair sweep '
    'takes 178.24 seconds total; it is separate from the 35 bounded default-path files. '
    'The unrelated full owner matrix was not rerun. See owner_scan.json and owner_scan.log.',
    '- `python3 tools/nfl2k5_cave_oracle.py space-proof "extracted/ESPN NFL 2K5 (USA)/default.xbe" '
    '--json reports/b72_s8/space_proof.json`: PASS for the existing grown-space ownership.',
    '- `python3 tools/scorebug_sprite/build_runtime.py --check`: PASS. RX 4076/4096, 20 spare, RW 128. '
    'No allocator or appended-resource growth.',
    '- `python3 packaging/repin.py --apply`: the generated-code provider digest was updated; final dry verification '
    'reports zero further updates. Both changed shipping files already have allowlist entries. '
    'The C source, tests and reports remain development files, as in the base.', '',
    'The protected cave manifest source check still fails first at nfl2k5_scorebug_exact.py, an inherited stale '
    'fingerprint. It was not edited or represented as a passing freshness check. The integrator must regenerate '
    'the manifest for the final stack, including the changed generated owner. The focused memory/reference checks '
    'above passed; no full all-owner cave/oracle test-suite pass is claimed.', '',
    'Initial candidate logs remain in checks/. At 4096 bytes, two tests correctly rejected insufficient padding. '
    'The final code is smaller, and both original assertions pass. The initial proof.log also records a strict '
    'floating-point equality assertion against luminance 254.99999999999997; the proof now checks actual RGB '
    'white pixels exactly. proof_final.log is the complete final run.', '',
    'Jev reviewed ten final code windows through the installed diff-gate recipe: zero deterministic findings and '
    'one expected PINNED_VALUE flag on regenerated machine bytes. The provider hash matches those bytes. '
    'See JEV_REVIEW.md for code and handoff dispositions.', '',
    's5 team artwork and palettes and s6/s7 diagnostics are byte-identical to c5134e232. '
    'All proof is offline. Noah confirms the in-game result on the requested test disc.', '']
(OUT/'VALIDATION.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
print('Wrote final validation: all 35 default-path files and six closure steps pass.')
