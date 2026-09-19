"""Combine retained baseline/focused receipts without erasing earlier failures."""
from pathlib import Path
import json
import re

OUT=Path(__file__).resolve().parent
rows={}
for receipt,folder in [('checks/results.json','checks'),('checks_final/results.json','checks_final'),
                        ('remaining_checks_results.json','checks_final'),('artwork_final_results.json','checks_final'),('source_final_results.json','checks_final')]:
    for row in json.loads((OUT/receipt).read_text()):
        if row['file'] not in rows and receipt!='checks/results.json':continue
        rows[row['file']]={**row,'log':folder+'/'+Path(row['file']).stem+'.log'}
resource=json.loads((OUT/'resources_final_result.json').read_text())
rows[resource['file']]={**resource,'log':'checks_final/'+Path(resource['file']).stem+'.log'}
for row in rows.values():
    text=(OUT/row['log']).read_text()
    match=re.search(r'Ran (\d+) tests? in',text)
    row['tests']=int(match.group(1)) if match else None
    row['skipped']=sum(map(int,re.findall(r'skipped=(\d+)',text)))
result={'required_files':len(rows),'all_exit_codes_zero':all(r['exit_code']==0 for r in rows.values()),
        'all_default_paths_under_100_seconds':all(r['seconds']<100 for r in rows.values()),
        'rows':sorted(rows.values(),key=lambda r:r['file'])}
(OUT/'validation_final.json').write_text(json.dumps(result,indent=2)+'\n')
lines=['# b72-s5 validation', '',
       '**The GPU reproduction gate fails. No cause-specific dark-label fix or in-game witness is claimed.**', '',
       f"Required inventory: {len(rows)} standalone test files; exit-code gate {'PASS' if result['all_exit_codes_zero'] else 'FAIL'}; default-path timing gate {'PASS' if result['all_default_paths_under_100_seconds'] else 'FAIL'} (<100 seconds per file).",
       'There are 298 collected cases: 290 execute and eight retain existing skips. Five skips cover superseded beta-69 private-font tests, one disc transaction cannot write its external scratch directory, and two source-art comparisons lack developer copies. Verbose reasons are retained in `checks_final/skip_detail_*.log`. No new skip was added.', '',
       'The inventory includes all scorebug files, the five sprite suites, provider integrity, replication pins and both portability scans. Default commands are `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 <file>`; no speed switch or reduced scenario set is used.', '',
       '| File | Tests | Skipped | Exit | Seconds | Log |','|---|---:|---:|---:|---:|---|']
for r in result['rows']:
    name=Path(r['file']).name
    lines.append(f"| {name} | {r['tests']} | {r['skipped']} | {r['exit_code']} | {r['seconds']:.2f} | [log]({r['log']}) |")
lines += ['', 'Results combine the full first run with later focused runs after performance changes. Earlier over-budget runs remain in `checks/results.json`, `checks_final/results.json` and progress logs. Only the latest applicable receipt is used above. [Performance changes and byte-equivalence evidence](PERFORMANCE.md) explain the optimizations.', '',
          'Both application closures are audited in disposable temporary directories. Staging below is solely for closure checks; no installer, playable test disc or release is produced.', '',
          '| Product | Check | Exit | Seconds |','|---|---|---:|---:|']
for r in json.loads((OUT/'closures.json').read_text()):
    lines.append(f"| {r['app']} | {['temporary stage','release closure','runtime closure'][r['step']]} | {r['exit_code']} | {r['seconds']:.2f} |")
lines += ['', 'The native runtime rebuild check passes. Appended data is 324,832 / 400,000 bytes; RX is 4,086 / 4,096 bytes; RW reservation is 128 bytes. Only 10 RX bytes remain. [Budget receipt](budgets.json), [build check](build_runtime_final.log).', '',
          'Auxiliary audits are reported separately:', '',
          '- XBE space tests: PASS, 28.86 seconds.',
          '- Cave oracle: FAIL, 29 tests with two stale reservation-source errors, 351.49 seconds including startup. Both errors first identify `mod_editor/core/nfl2k5_scorebug_ingame.py`. No manifest was regenerated, as instructed. The integrator must refresh reservations and rerun this audit after integration. [Log](checks_final/test_nfl2k5_cave_oracle.log).',
          '- Allocator integration: the 420-second runner timed out; its longer retry is recorded below. This auxiliary file is outside the requested scorebug timing inventory. [Original timeout log](checks_final/test_beta61_allocator_integration.log).']
retry=OUT/'allocator_retry.json'
if retry.exists():
    r=json.loads(retry.read_text())
    lines.append(f"- Allocator retry with a {r['timeout']}-second outer limit: exit {r['exit_code']}, {r['seconds']:.2f} seconds. [Log](checks_final/test_beta61_allocator_integration_retry.log). The retry does not erase the first timeout.")
else:lines.append('- Allocator retry is still pending; this document must be regenerated when it finishes.')
lines += ['', '[24 quantizer and 264 panel differential comparisons](performance_equivalence.log) pass against `ec5d68d4`. The new GPU/palette suite checks packet decoding, the observed combiner, neutral masks, palette rejection, byte counters, cache invalidation, pinned logo isolation, all 52 native tint slots at both possessions/aspects and independent texture decode.', '',
          'New modules are declared in the release allowlist and pinned via `packaging/repin.py --apply`. Provider closure is 301 entries. The template PNG catalog updates only the changed template hash/size and its digest pin. The supplied official colour dataset and cave manifest are unchanged.', '',
          'The unavailable `/home/noah/ai-stack/jev/recipes/jev_diff_gate.py` was not run; the integrator owns that check. Hunk whitespace, added em dashes and Python syntax are checked separately. No cross-time ctime comparisons were added.', '',
          '[GPU findings](GPU_FINDINGS.md), [calibration errors](calibration.json), [team-colour review](TEAM_COLOURS.md), [Jev requests and receipts](accents/responses.json).']
(OUT/'VALIDATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print({k:v for k,v in result.items() if k!='rows'})
