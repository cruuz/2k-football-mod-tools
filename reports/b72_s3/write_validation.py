"""Summarize retained validation receipts without converting failures to passes."""
from pathlib import Path
import json
import re
ROOT=Path(__file__).resolve().parents[2]
REPORT=Path(__file__).resolve().parent
rows=json.loads((REPORT/'checks/results.json').read_text())
lines=['# b72-s3 validation','', 'The reconstruction and rebuild gates remain FAILED. Green diagnostic checks do not make this a repaired scorebug.','', '| File | Result | Wall seconds | 100-second target |','| --- | --- | --- | --- |']
for row in rows:
 code=row['exit_code'];status='PASS' if code==0 else 'TIMEOUT at 420 s' if code==124 else 'FAIL, exit '+str(code)
 lines.append('| '+row['file']+' | '+status+' | '+str(row['seconds'])+' | '+('PASS' if row['seconds']<100 else 'FAIL')+' |')
lines.extend(['',f"Completed {len(rows)} files: {sum(r['exit_code']==0 for r in rows)} passed; {sum(r['exit_code']!=0 for r in rows)} failed/timed out. {sum(r['seconds']>=100 for r in rows)} files exceeded 100 seconds.",'', 'Standalone invocation: `PYTHONPATH=<repo> QT_QPA_PLATFORM=offscreen python3 <test-file>`. The report runner enforces the 420-second ceiling per file. All logs remain in `reports/b72_s3/checks/`.','', 'The allocator diagnostic with a 600-second outer limit is recorded separately in `beta61_extended.log`. It cannot override the 420-second timeout result.','', '| Other check | Result |','| --- | --- |','| New replication regression file | 12 tests passed; see replication_test.log |','| ESPN matcher, rendered fresh | 95 pass / 0 fail / 9 impossible |','| New source pin audit | 0 pending pin updates |','| Existing generated runtime | build_runtime.py --check; see runtime_build_check.log |','| Native submission order | Plate before label at both aspects; GPU boundaries remain |'])
for row in json.loads((REPORT/'closures.json').read_text()):
 lines.append(f"| {row['app']} closure step {row['step']} | {'PASS' if row['exit_code']==0 else 'FAIL'} ({row['seconds']} s) |")
lines.extend(['','Closure steps: 0 stages an allowlist in a temporary directory, 1 checks the release file closure, 2 imports/checks the staged runtime. The runner removes each temporary stage.','', 'Commands:','', '```text','python3 reports/b72_s3/run_checks.py','python3 reports/b72_s3/run_closures.py','python3 tools/scorebug_sprite/match_espn.py --frames FRAMES --output reports/b72_s3/match','python3 tools/scorebug_sprite/native.py --output submission.json','python3 packaging/repin.py','```',''])
(ROOT/'VALIDATION.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
