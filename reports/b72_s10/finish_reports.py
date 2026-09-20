"""Summarize retained receipts without converting incomplete gates into passes."""
from pathlib import Path
import json
import re

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def put(name, text):
    (OUT / name).write_text(text, encoding='utf-8', newline='\n')


def usage():
    rows = []
    singles = json.loads((OUT / 'jev_calls.json').read_text())
    calls = [(f'jev_calls.json[{i}]', call) for i, call in enumerate(singles)]
    for name in ('gate_initial_call.json', 'gate_final_call.json', 'handoff_initial_call.json', 'handoff_call.json'):
        if (OUT / name).exists():
            calls.append((name, json.loads((OUT / name).read_text())))
    for source, call in calls:
        result = json.loads(call['response']['structuredContent']['result'])
        meta = result.get('meta', result.get('totals'))
        rows.append(dict(meta, source=source, tool=call['tool']))
    total = round(sum(r['cost_usd'] for r in rows), 8)
    assert total < 1.0
    summary = dict(cap_usd=1.0, total_cost_usd=total, calls=len(rows),
                   input_tokens=sum(r['input_tokens'] for r in rows),
                   model='jev-1.13.0', rows=rows,
                   configuration_probe='Initial jev_status(ping=false) only inspected configuration; no charged inference. Full inference requests and responses are retained in the listed receipts.')
    put('JEV_USAGE.json', json.dumps(summary, indent=2) + '\n')
    return summary


def main():
    cost = usage()
    checks = json.loads((OUT / 'checks/results.json').read_text())
    assert len(checks) == 35 and all(r['exit_code'] == 0 for r in checks)
    cases = skips = 0
    for row in checks:
        log = (OUT / 'checks' / (Path(row['file']).stem + '.log')).read_text()
        cases += int(re.findall(r'Ran (\d+) tests?', log)[-1])
        found = re.findall(r'skipped=(\d+)', log)
        skips += int(found[-1]) if found else 0
    aux = json.loads((OUT / 'aux_checks.json').read_text())
    aux_rows = '\n'.join(f"| `{r['file']}` | {'PASS' if r['exit_code'] == 0 else 'INCOMPLETE: timeout' if r['exit_code'] == 124 else 'FAIL'} | {r['seconds']:.2f} |" for r in aux)
    put('VALIDATION.md', f'''# b72-s10 validation

All 35 default scorebug, provider-integrity and standalone packaging test files pass: {cases} cases, {cases-skips} executed and {skips} existing skips. Each file ran separately with plain Python, `PYTHONPATH` set to this checkout, `QT_QPA_PLATFORM=offscreen`, one worker and an enforced 100-second timeout. The slowest final file is the resource suite at 83.15 seconds. `checks/results.json` and its named logs are the final receipts.

```bash
python3 reports/b72_s10/run_checks.py
python3 reports/b72_s10/audit.py
python3 reports/b72_s10/run_closures.py
python3 reports/b72_s10/scan_owner.py
python3 reports/b72_s10/run_aux.py
python3 reports/b72_s10/scan.py
python3 packaging/repin.py --apply
```

The native raster label audit passes all 104 combinations: 52 current/historical native team slots, both aspects. It checks the preserved text readability floor and contrast, layout footprint and generated resource sizes. This is an offline label result, not a played witness. `readability.json`, `logo_fits.json`, `budgets.json`, and the two all-team grids retain the details. Native long-clock tests cover 9:59, 10:00 and larger clocks.

The retained Unicorn sequence run passes 675 frames per aspect, 1,350 total. Its actual captured material/event records cover pre-snap, punt/hang-time, after-play, FLAG, FUMBLE and down-label recovery. `native_sequences/sequences.json` and `retained_sequences.log` are the receipts. Existing native draw-order tests deliberately break submission order and ensure a hidden label cannot be rescued by a friendly preview. No game or emulator was launched.

The focused native owner scan passes 31 composition pairs in both orders, with writable destinations, RX/RW permissions, idempotence and hook ownership checked. The source manifest freshness check separately reports the inherited stale `nfl2k5_scorebug_exact.py` fingerprint. Native owner files and the protected manifest are byte-identical to base `97d2bf9b2`; source freshness is not claimed. The integrator must regenerate the manifest on the final stack as described in `../../WIRING.md`.

Broader auxiliary suites are separately bounded at 420 seconds each. A timeout is incomplete, not a pass. These suites cover the complete unrelated owner union in multiple installation orders; they are additional coverage beyond the unchanged scorebug owner and its focused 31-pair proof. Final recorded auxiliary results:

| Standalone file | Result | Seconds |
|---|---|---:|
{aux_rows}

The cave-oracle suite finishes 29 tests with two errors, both the inherited stale `nfl2k5_scorebug_exact.py` manifest fingerprint; 27 tests pass. The standalone phase-one packaging suite passes. The memory-write and cave-reference suites time out at 420 seconds, so their partial dot output is not counted as a suite pass. No native game code or these test files changed. The protected manifest remains an explicit integration requirement.

Both 2K5 and APF product closures pass staging, release inventory/integrity checks and isolated runtime checks. Staging directories were removed. `run_closures.py` records the exact commands; `closures.json`, `2k5_closure_*.log` and `apf2k8_closure_*.log` retain their results. APF shipping bytes are unchanged. Existing allowlists already contain every modified shipping path; no inventory entries, dependencies, capability rows or provider-count expectations were added.

The PNG catalogue records the exact final 22,990-byte PNG and SHA-256. The release checker changes only its catalogue hash constant; an AST comparison verifies all other checker logic is identical. Replication and provider pins match final source bytes. Deterministic asset regeneration is byte-identical (`author_roundtrip.json`); native runtime reproducibility passes (`runtime_reproducibility.log`). The append is 325,216 bytes at each aspect, below 400,000. RX remains 4,086 of 4,096 bytes, with 10 spare; RW remains 128 bytes. No native code was added.

`scans.json` verifies existing allowlist membership, unchanged native owners, official palette and provider-count tests, no credential-pattern hits, and no added em dashes. The product closure also performs its retained-byte policy audit. Only development evidence/scripts are added under this report directory.

Failed trials are retained, not erased: the initial wider source plate failed the SD footprint test, the old logo-ratio assertion used the previous well geometry, and closure attempts exposed stale PNG size/catalogue pins. The plate was prefiltered to 91x17, the logo contract now derives the actual quad aspect with unchanged tolerance, and exact catalogue pins were refreshed. `checks_before_sd_fix/`, `checks/sprite_initial.log`, and closure logs with `before_` in their names preserve those failures. Final default tests and closures pass after correction.

The visual metric has no all-clear threshold. Logo, wing, housing/rim and score area decrease; plate and pill show no material closure. `GAPS.md` reports every nonzero residual. The six final comparison sheets use the final corrected SD cell and include genuine supplied disc r before captures.
''')
    put('JEV_REVIEW.md', f'''# b72-s10 Jev review

Jev receives text descriptors and measured feature tables, never pixels. Every inference request and raw response is retained in `jev_calls.json`, `gate_initial_call.json`, `gate_final_call.json`, and the handoff call receipt when present. `JEV_USAGE.json` aggregates current usage: ${cost['total_cost_usd']:.8f}, {cost['calls']} calls, against the $1.00 cap. Requests are bounded before dispatch using a conservative byte-count reserve. The initial configuration-only status probe does not perform inference.

Both phrasings of each ranking ask for the largest measured visible-area gap. The initial raw-RGB order was wing, housing/rim, down capsule, logo, pill, score. Feature occupancy subsequently replaced raw RGB because palette shade differences inflated area without measuring proportion. Jev saw the revised table; measurements retained authority throughout. The final ranking is logo, wing colour, housing/rim, down capsule, pill, score. Both final next-gap calls select logo, with confidence 0.86 and 0.93, matching the measured 1,931.75-pixel residual.

Both recognition phrasings use the same 0-to-4 concrete rubric. Raw-RGB baseline scores were 1.14 and 1.13. The revised occupancy baseline scores were 1.73 and 1.62. An intermediate candidate scored 1.23 and 1.47; these unfavourable answers remain logged. The final corrected SD candidate scores 1.79 and 1.86, with confidence 0.44 and 0.50. These cautious results do not certify that the bar reads as ESPN or establish a quantitative gain across differently worded contexts. They cannot overrule area measurements or a future player verdict. All six measured feature residuals remain nonzero.

The installed diff-gate recipe was run via request capture, actual MCP batch execution and exact-input replay. Its final source review covers base `97d2bf9b2` through implementation commit `73273e596a`. Later changes are report evidence only. Eleven windows, zero provider errors and zero deterministic findings; two model flags remain documented in `own_diff_gate.md`:

| Flag | Probability | Disposition |
|---|---:|---|
| PINNED_VALUE, logo-fit test | 0.91 | Reviewed. The old expected ratio used the 200x107 mapping. The test now derives the actual 230x110 quad aspect and expects the deliberately cropped KC/DEN silhouettes. The 0.12 tolerance and wide-silhouette floor remain. This is a layout contract, not proof of broadcast fidelity. |
| PINNED_VALUE, layout cell coordinates | 0.63 | Reviewed. Coordinates belong to deterministic atlas repacking. Bounds, native sampling, SD footprint, append budgets and regeneration pass; no native table/resource format changes. |

The recipe separately dismisses four hash warnings because every digest matches the HEAD bytes: provider pin, release catalogue hash, PNG identity and replication pins. No inventory-count assertion was changed. The gate returned its flagged status; this report does not present it as an unconditional model pass. The independent release closures, measured art checks and source audit support the reviewed dispositions.

The handoff fact-check uses the installed recipe over the final summary and these job reports. Its receipt and any reviewed flags are recorded separately in `handoff_factcheck.md`. No model output is represented as an in-game witness.
''')
    print(json.dumps(dict(cases=cases, skipped=skips, auxiliary_files_recorded=len(aux), **cost), indent=2))


if __name__ == '__main__':
    main()
