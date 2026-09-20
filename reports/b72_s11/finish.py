"""Summarize measured receipts and assert the retained s10 contracts."""
from pathlib import Path
import hashlib
import json
import re

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def read(name):
    return json.loads((OUT/name).read_text())


def put(name, text):
    (OUT/name).write_text(text, encoding='utf-8', newline='\n')


def main():
    s9 = json.loads((ROOT/'reports/b72_s10/baseline_measurements.json').read_text())
    s10 = json.loads((ROOT/'reports/b72_s10/final_measurements.json').read_text())
    baseline, final = read('baseline_measurements.json'), read('final_measurements.json')
    assert baseline['rows'] == s10['rows']
    assert baseline['ranked'] == s10['ranked']
    maps = [{r['feature']: r['visible_area_px'] for r in data['ranked']} for data in (s9, s10, final)]
    for name in ('logo', 'wing_colour', 'score'):
        assert maps[2][name] <= maps[1][name], name
    metrics = []
    for name in ('logo', 'wing_colour', 'score', 'housing_rim', 'down_capsule', 'pill'):
        a, b, c = [m[name] for m in maps]
        metrics.append(dict(feature=name, s9=a, s10=b, s11=c,
            s10_gain_percent=round(100*(a-b)/a, 1), s11_gain_percent=round(100*(a-c)/a, 1)))
    put('residual_comparison.json', json.dumps(metrics, indent=2)+'\n')
    table = '\n'.join(f"| {r['feature']} | {r['s9']:.2f} | {r['s10']:.2f} | {r['s11']:.2f} | {r['s10_gain_percent']:.1f}% | {r['s11_gain_percent']:.1f}% |" for r in metrics)
    put('GAPS.md', '''# b72-s11 residual comparison

Fresh s10 renders reproduce every recorded s10 row and ranked residual exactly. S11 uses the same reference frames, same scoreboard values, same two aspects, same 617-pixel bar, same ROIs and same 2-by-2 player-pixel core threshold.

| Feature | S9 residual px | S10 residual px | S11 residual px | S10 reduction vs S9 | S11 reduction vs S9 |
|---|---:|---:|---:|---:|---:|
'''+table+'''

The required logo and score gains are retained exactly. The wing residual improves further. Housing pixels in this proxy also change when logo ink moves across the overlapping rim ROI; the housing artwork itself is unchanged. Every residual remains nonzero. The logo metric measures white-ink occupancy, whereas the separate crop proof counts the complete source alpha of every colour. These are overlapping feature proxies, not perceptual identity scores, and must not be added. No in-game outcome or exact broadcast match is claimed.
''')
    ink, labels = read('ink_retention.json'), read('readability.json')
    assert len(ink) == 64 and len(labels) == 104
    assert all(r['passed'] and r['source']['ink_fraction'] == r['texture']['ink_fraction'] == 1 for r in ink)
    assert all(p['ink_fraction'] == p['binary_fraction'] == 1 for r in ink for p in r['projected'])
    assert len({tuple(r['transformed_size']) for r in ink}) == 21
    old_labels = json.loads((ROOT/'reports/b72_s10/readability.json').read_text())
    assert labels == old_labels
    by_name = {r['team']: {} for r in ink}
    for row in ink:
        by_name[row['team']][row['aspect']] = row
    table = []
    for name, aspects in sorted(by_name.items()):
        row = aspects['43']
        width, height = row['transformed_size']
        table.append(f"| {name} | {row['category']} | {row['before']['source']['ink_fraction']*100:.4f}% | 100% | 100% | {width}x{height} |")
    put('INK_RETENTION.md', '''# b72-s11 per-team ink survival

All 32 primary marks retain exactly 100 percent of both alpha-weighted and binary source ink in 4:3 and 16:9, at both ends of the executed native bar. All 64 team/aspect checks also retain 100 percent of the complete filtered mark before the native clipping paste. Allowed crop is zero for every class, including symmetric enclosures and circles. A fractional coverage count is not rounded up to pass.

The before column counts the full s10 source artwork mapped into the wing, including the texture-window limit and rounded corners. It is identical across aspects because the native projection is affine. The after columns use the actual executed quads in each aspect. `ink_retention.json` retains integer denominators, surviving counts, weighted and binary fractions, original PNG hashes/bounds/aspects, transformed sizes, and actual native/player boxes. `FIDELITY.md` specifies the method and its rendering limits.

| Team | Mark class | S10 source ink retained | S11 4:3 | S11 16:9 | Complete texture mark px |
|---|---|---:|---:|---:|---:|
'''+ '\n'.join(table)+'''

The all-team contact sheets additionally render the 20 existing historical/all-star/user fallback slots. Those slots have no authored primary-logo PNG in this package. Their treatment is unchanged and all 104 native label measurements are exactly equal to s10. The 32 artwork-derived transforms produce 21 distinct texture sizes; each team is checked individually, including all faint nonzero source-alpha footprints.
''')
    sequences = read('native_sequences/sequences.json')
    old_sequences = json.loads((ROOT/'reports/b72_s10/native_sequences/sequences.json').read_text())
    assert sequences == old_sequences
    assert sequences['frames_per_aspect'] == 675
    budget = read('budgets.json')
    assert (budget['rx_used'], budget['rx_reserved'], budget['rw_reserved']) == (4086, 4096, 128)
    assert all(v['appended_bytes'] == 325216 for v in budget['aspects'].values())
    checks, closures, aux = read('checks/results.json'), read('closures.json'), read('aux_checks.json')
    assert len(checks) == 36 and all(r['exit_code'] == 0 for r in checks)
    assert len(closures) == 6 and all(r['exit_code'] == 0 for r in closures)
    cases = skips = 0
    for row in checks:
        log = (OUT/'checks'/(Path(row['file']).stem+'.log')).read_text()
        cases += int(re.findall(r'Ran (\d+) tests?', log)[-1])
        found = re.findall(r'skipped=(\d+)', log)
        skips += int(found[-1]) if found else 0
    aux_table = '\n'.join(f"| `{r['file']}` | {'PASS' if r['exit_code']==0 else 'INCOMPLETE: timeout' if r['exit_code']==124 else 'FAIL'} | {r['seconds']:.2f} |" for r in aux)
    put('VALIDATION.md', f'''# b72-s11 validation

All {len(checks)} default standalone files pass: {cases} test cases, {cases-skips} executed and {skips} existing skips. Each file runs with plain Python, `PYTHONPATH` set to this checkout, `QT_QPA_PLATFORM=offscreen`, one worker and a 150-second bound. The set includes every scorebug suite, the new full-mark regression, provider integrity, replication pins and standalone packaging checks. Named logs and `checks/results.json` retain the exact results.

The all-team audit passes 64 primary-team/aspect containment checks at both ends, with exact 100 percent weighted and binary source-ink retention. All 104 native label measurements equal s10. Both full contact sheets and six player-scale before/after sheets are retained. The 1,350 retained event-frame records are identical to the parsed s10 records, covering pre-snap, punt/hang-time, after-play, FLAG, FUMBLE and down-label recovery. This is bounded native CPU and software-raster evidence only.

Both product closures pass all three steps: temporary staging, release inventory/integrity validation, and isolated runtime validation. Temporary stages are removed. The release inventories, provider counts, PNG catalogue, release checkers, runtime sources, palette fields and template PNG remain unchanged. Repin refreshes only the existing team-accent metadata digest. Appended size remains 325,216 bytes in both aspects, RX remains 4,086/4,096 bytes, and RW remains 128 bytes. Every component retains its byte size. Native runtime regeneration passes `build_runtime.py --check`.

The focused scorebug owner scan checks writable destinations, RX/RW permissions, idempotence and hook ownership, plus the 31 relevant owner-composition pairs in both orders. The source-manifest audit separately reports the inherited stale `nfl2k5_scorebug_exact.py` fingerprint. The protected manifest and all runtime owner sources are unchanged. Integration still requires the manifest regeneration documented in `../../WIRING.md`.

Broader auxiliary suites are bounded separately at 420 seconds each. These results are not counted as default-suite passes:

| Auxiliary suite | Result | Seconds |
|---|---|---:|
{aux_table}

The cave-oracle suite completes 29 tests: 27 pass and two error on the same inherited stale source fingerprint, reported by `nfl2k5_cave_oracle.py:217`. The failing callers are `test_nfl2k5_cave_oracle.py:382` and `:395`. These are source-manifest freshness errors, not new runtime writes. No manifest-freshness pass is claimed.

The original sprite aspect test failure is retained in `sprite_old_cropped_aspect.log`: its expected Chiefs ratio described the cropped mark. The final test expects the complete silhouette, with the same tolerance and minimum aspect. The original cropped Washington, Texans, Raiders and Steelers fits are negative controls in the new regression. No integrity check or label threshold was weakened.

Exact command orchestration is in `validate.py`, `run_checks.py`, `run_closures.py`, `run_aux.py` and their progress receipts. The core reproduction commands are:

```bash
python3 reports/b72_s11/fit.py
python3 packaging/repin.py --apply
python3 reports/b72_s11/validate.py baseline final audit sheets events checks owner closures
python3 reports/b72_s11/run_aux.py
python3 tools/scorebug_sprite/build_runtime.py --check
python3 reports/b72_s11/finish.py
python3 reports/b72_s11/scan.py
```

No emulator, disc image build, publish, push or release action ran. A disposable product closure is validation only. GPU/display calibration and a played retest remain unwitnessed.
''')
    put('contract_comparison.json', json.dumps(dict(s10_residuals_reproduced=True,
        label_measurements_equal=True, labels=104, event_records_equal=True, event_frames=1350,
        primary_aspect_checks=64, projected_end_checks=128, permitted_crop=0,
        appended_bytes=325216, rx_used=4086, rx_reserved=4096, rw_reserved=128,
        default_files=len(checks), default_cases=cases, existing_skips=skips), indent=2)+'\n')
    print('PASS: s10 residuals, labels, events and budgets compared; final evidence summarized.')


if __name__ == '__main__':
    main()
