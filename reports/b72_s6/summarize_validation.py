from pathlib import Path
import json
import re

OUT=Path(__file__).resolve().parent
rows=json.loads((OUT/'checks/results.json').read_text())
for row in rows:
    log=(OUT/'checks'/(Path(row['file']).stem+'.log')).read_text()
    row['cases']=int(re.search(r'Ran (\d+) tests?',log)[1])
    skip=re.search(r'OK \(skipped=(\d+)\)',log)
    row['skips']=int(skip[1]) if skip else 0
assert all(r['exit_code']==0 and r['seconds']<100 for r in rows)
(OUT/'validation.json').write_text(json.dumps(rows,indent=2)+'\n')
lines=['# b72-s6 validation','',
 f'All {len(rows)} required standalone test files pass: {sum(r["cases"] for r in rows)} cases collected, {sum(r["cases"]-r["skips"] for r in rows)} executed and {sum(r["skips"] for r in rows)} existing skips. Every file completed below 100 seconds. Commands use plain python3, PYTHONPATH=<repo> and QT_QPA_PLATFORM=offscreen. See run_checks.py for the exact inventory and bounded subprocess invocation.','',
 '| Test file | Cases | Skips | Seconds | Result |','|---|---:|---:|---:|---|']
for r in rows:
    name=Path(r['file']).stem
    lines.append(f'| [{name}](checks/{name}.log) | {r["cases"]} | {r["skips"]} | {r["seconds"]:.2f} | PASS |')
lines += ['', 'The nine new trace tests cover partial windows, absent indices, upload component/index semantics, resident program rewrites, independent windows, unhandled methods, inside-draw changes, channel separation, truncated RAM and rectangular swizzling. The existing native GPU suite also checks exact independent texture decoding, captured-filter acceptance, unsupported-filter refusal and incomplete-program refusal. Native order, down visibility and all 52 team slots at both possessions and aspects pass. No all-team fixed-output claim is made because reproduction is unresolved.','',
 'Both products were staged only into disposable temporary directories for closure checks. No installer or test disc was produced.','',
 '| Product | Check | Seconds | Exit |','|---|---|---:|---:|']
for r in json.loads((OUT/'closures.json').read_text()):
    lines.append(f'| {r["app"]} | {["stage","release closure","runtime closure"][r["step"]]} | {r["seconds"]:.2f} | {r["exit_code"]} |')
lines += ['',
 'The runtime rebuild check passes (build_runtime.log). Budgets remain 4086/4096 RX, 128 RW and 324832/400000 appended bytes. Runtime owner, generated code, source, layout, template, team accent data and cave manifest are byte-identical to the base (budgets.json). No allocator request or cave write changes in this job.', '',
 'The read-only cave space-proof command passes with no retail mapping or manifest overlaps (space_proof.json). Its source-fingerprint check is separate: ReservationManifest.load(..., source_root=ROOT) fails first at nfl2k5_scorebug_exact.py; the stale-source set is identical to the base (manifest_freshness.log). This job does not regenerate the manifest or hide that failure. The full auxiliary allocator/oracle suites from s5 were not repeated for unchanged runtime code; their prior limitations are not promoted to fresh passes.', '',
 'New live.py is declared in the release allowlist and replication pins. repin.py updated the existing xemu_model.py pins. The exact provider import closure remains 301 entries and its integrity test passes. All declarations are part of this branch; no integrator wiring is required for the diagnostic modules.', '',
 'The installed Jev diff-gate recipe reports zero deterministic findings. Its 13 live MCP hunk judgments flagged two model-extension windows; manual dispositions are in JEV_REVIEW.md. Pin changes were independently verified by the recipe. The full report and raw requests/responses are retained.', '',
 'The in-game reproduction gate fails. The supplied sample has zero sprite atlas draws; the earlier state plus later RAM still predicts bright label cores. No cause-specific runtime change, no new emulator session and no in-game success claim. See GPU_FINDINGS.md and NEXT_CAPTURE.md.', '']
(OUT/'VALIDATION.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
