"""Collect final test, source-integrity and Jev receipts without touching the cave manifest."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import re
import subprocess

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
def write(name,v):(OUT/name).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8',newline='\n')
calls=[]
for p in sorted(OUT.rglob('*call*.json')):
    v=json.loads(p.read_text())
    if not isinstance(v,dict) or 'request' not in v or 'response' not in v:continue
    r=v['response'];meta=r.get('totals',r.get('meta',{}))
    if not meta:raise ValueError('Missing usage: '+str(p))
    calls.append(dict(tool='jev_batch',receipt=p.relative_to(OUT).as_posix(),
        sha256=hashlib.sha256(p.read_bytes()).hexdigest(),states=len(v['request'].get('states',[])),**meta))
# Exact metadata from the global MCP usage log for this job's initial ping.
calls.append(dict(ts='2026-09-19T17:12:30',tool='jev_status',model='jev-1.13.0',
    input_tokens=274,output_tokens=20,cost_usd=.00001151,latency_ms=355.3,questions=1,
    provenance='/home/noah/ai-stack/jev/logs/usage.jsonl',request=dict(ping=True)))
(OUT/'jev_calls.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in calls),encoding='utf-8',newline='\n')
cost=sum(v['cost_usd'] for v in calls);assert cost<3
write('JEV_USAGE.json',dict(cost_usd=round(cost,8),cap_usd=3.,mcp_batches=sum(v['tool']=='jev_batch' for v in calls),
    batch_states=sum(v.get('states',0) for v in calls),status_pings=1,errors=sum(v.get('errors',0) for v in calls),
    input_tokens=sum(v.get('input_tokens',0) for v in calls),
    source_grammar_previous_job_cost_usd=1.4173,source_grammar_cost_included=False))
changed=subprocess.check_output(['git','diff','--name-only','42579f4a5','--','data','mod_editor','packaging','tests','tools/scorebug_sprite'],cwd=ROOT,text=True).splitlines()
write('final_source_hashes.json',{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in changed+['data/nfl2k5_cave_reservations.json']})
tests=json.loads((OUT/'checks/results.json').read_text());assert len(tests)==35 and all(r['exit_code']==0 and r['seconds']<100 for r in tests)
cases=skips=0
for r in tests:
    log=(OUT/'checks'/(Path(r['file']).stem+'.log')).read_text()
    n=re.search(r'Ran (\d+) tests?',log);r['cases']=int(n[1]) if n else 0;cases+=r['cases']
    n=re.search(r'OK \(skipped=(\d+)\)',log);r['skips']=int(n[1]) if n else 0;skips+=r['skips']
closures=json.loads((OUT/'closures.json').read_text());assert len(closures)==6 and all(r['exit_code']==0 for r in closures)
owner=(OUT/'owner_scan.log').read_text();assert 'Ran 31 tests' in owner and owner.rstrip().endswith('OK')
seq=json.loads((OUT/'sequences.json').read_text());assert seq['frames_per_aspect']==675
readability=json.loads((OUT/'readability.json').read_text());assert len(readability)==104 and all(r['predicted_pass'] for r in readability)
budget=json.loads((OUT/'budgets.json').read_text());assert max(v['appended_bytes'] for v in budget['aspects'].values())<budget['ceiling']
res=json.loads((OUT/'element_residuals.json').read_text());counts=Counter(r['status'] for r in res)
write('validation_summary.json',dict(test_files=35,test_cases=cases,skips=skips,executed=cases-skips,
    max_default_seconds=max(r['seconds'] for r in tests),closures_passed=6,owner_pairs=31,retained_frames=1350,
    label_slot_aspects=104,residuals=dict(counts),runtime_witnessed=False,calibration_passed=False,strict_fidelity_passed=False))
lines=['# Final offline validation','',
 f'All 35 default test files pass: {cases} cases, {cases-skips} executed and {skips} existing skips. The slowest file takes {max(r["seconds"] for r in tests):.2f} seconds; each subprocess has an enforced 100-second timeout. No performance-only test environment switch is used.','',
 '| Test file | Cases | Skips | Seconds | Exit |','|---|---:|---:|---:|---:|']
lines += [f"| [{Path(r['file']).stem}](checks/{Path(r['file']).stem}.log) | {r['cases']} | {r['skips']} | {r['seconds']:.2f} | {r['exit_code']} |" for r in tests]
lines += ['', '| Product | Closure step | Seconds | Exit |','|---|---|---:|---:|']
lines += [f"| {r['app']} | {['temporary stage','release audit','runtime audit'][r['step']]} | {r['seconds']:.2f} | {r['exit_code']} |" for r in closures]
lines += ['', 'Temporary product stages were removed. These are closure checks, not published release builds. The final artwork changed only the 2K5 stage; the APF closure was already verified against its unchanged bytes.', '',
 'The 31 scorebug owner composition pairs pass in both orders. owner_scan.json records RX/RW permissions, absolute write destinations, idempotence and hook ownership. This auxiliary sweep is separate from the default-file budget. The retained native sequence proof covers 675 frames per aspect, 1,350 total, across pre-snap, punt/hang-time, after-play, FLAG, FUMBLE and label recovery. submission_order.json records both native material submission orders. The default draw-order test deliberately introduces bad ordering and verifies that the native renderer cannot rescue the overdrawn label.', '',
 f"RX is {budget['rx_used']}/{budget['rx_reserved']} bytes with 10 spare, RW is {budget['rw_reserved']} bytes, and GAMEDATA appendices are {budget['aspects']['True']['appended_bytes']} bytes at both aspects against a {budget['ceiling']}-byte ceiling. Compared with disc q, append growth is {budget['append_delta']['True']} bytes. build_runtime.py --check passes. repin_verify.log records no pending source-pin updates.", '',
 'The exact base owner fails the new clock regression at 599.01 seconds, where the formatter rounds to 10:00 and the short formatter returns empty. The final owner selects the complementary retail formatter. Existing invalid-pointer/range guards remain. New regression cases cover fractional rollover, 10:00, 14:54, 15:00, 60:00 and return to 9:59.', '',
 f"The 104 final team/aspect label raster checks all pass core luminance >=200 and contrast >=4.5:1. The independent detailed visual table has {counts['PASS']} PASS and {counts['FAIL']} FAIL rows, including provenance-only rows explicitly identified as such. Thus strict fidelity and screenshot calibration remain failed/unverified. Passing tests are not an in-game witness.", '',
 'The cave reservation manifest and s6/s7 reports are byte-identical to 42579f4a5. Source fingerprint freshness is intentionally not a pass: the integrator must regenerate the cave manifest for the final stack. No all-owner cave/oracle-suite pass is claimed. Existing release allowlists, requirements and provider closure counts were not expanded.', '',
 'The last default run caught the renamed estimated_opacity metadata key in the old test assertion. That assertion was corrected to require the honest key and the affected 22-test file rerun successfully. checks/sprite_before_metadata_correction.log retains the failed run; checks/results.json and the table above contain the final results. Older root-level repin/sprite/evidence logs are exploratory receipts and are superseded by the explicitly final files.', '',
 'The Jev gate returns flagged status with reviewed dispositions, not an unconditional clean pass. See JEV_REVIEW.md. All work is offline; the integrator builds one test disc and Noah provides the next game witness.']
(OUT/'VALIDATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
print('Final receipts:',cases,'cases;',dict(counts),'residuals; Jev USD',round(cost,8))
