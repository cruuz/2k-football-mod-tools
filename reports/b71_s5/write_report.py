"""Assemble the report and exact command ledger from completed run receipts."""
from pathlib import Path
import datetime,hashlib,json,re,shlex,subprocess
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
rows=[]
for path in OUT.glob('*.result.json'):
 row=json.loads(path.read_text())
 if 'argv' in row:rows.append(row)
rows.sort(key=lambda r:r['start_utc'])
latest={}
for row in rows:
 argv=row['argv'];keys=tuple(v for v in argv[1:] if v!='-v')
 latest[keys]=row
checks=[r for r in latest.values() if Path(r['argv'][0]).name.startswith('python') and any('test_' in a or a.endswith('_test.py') or a.endswith('validate_registry') or a.endswith('capabilities.py') for a in r['argv'])]
checks.sort(key=lambda r:r['name'])
counts={}
for r in checks:
 log=(OUT/(r['name']+'.log')).read_text()
 ran=re.findall(r'Ran (\d+) tests?',log)
 skipped=re.findall(r'\bskipped=(\d+)',log)
 counts[r['name']]=dict(exit_code=r['exit_code'],seconds=r['seconds'],tests=int(ran[-1]) if ran else None,skipped=int(skipped[-1]) if skipped else 0)
required=sorted(str(p.relative_to(ROOT)) for p in (ROOT/'tests/mod_editor').glob('test_*.py') if 'scorebug' in p.name or 'scorebar' in p.name)
required += ['tests/nfl2k5_scorebug_layout_test.py','tests/nfl2k5_scorebug_mod_project_test.py']
required += ['tests/mod_editor/test_'+name+'.py' for name in ('provider_integrity','product_catalog','phase1_packaging','mod_build','build_panel_qt','nfl2k5_allocator_scaleout','nfl2k5_xbe_space','xbe_patch_memory_writes','xbe_patch_cave_references','nfl2k5_cave_oracle','nfl2k5_owner_pairwise_composition')]
done={arg for r in checks for arg in r['argv']}
missing=[path for path in required if path not in done]
summary=dict(updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),checks=counts,failed_latest=[r['name'] for r in checks if r['exit_code']],missing_required=missing,required_suites=len(required),tests=sum(r['tests'] or 0 for r in counts.values()),skips=sum(r['skipped'] for r in counts.values()),command_runs=len(rows))
(OUT/'suite-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
text=(OUT/'report_body.md').read_text()
text+='\n## Completed verification results\n\n'
text+='The table below contains the latest completed run of each test/validator command. A pending gate is not counted as passed.\n\n'
text+=f"Required suites: {len(required)}. Latest completed results: {summary['tests']} tests, {summary['skips']} explicit skips. Missing required results: {', '.join(missing) or 'none'}. Failed latest results: {', '.join(summary['failed_latest']) or 'none'}.\n\n"
text+='| Check | Tests | Skips | Seconds | Exit |\n| --- | ---: | ---: | ---: | ---: |\n'
for name,r in counts.items():text+=f"| [{name}](reports/b71_s5/{name}.log) | {r['tests'] if r['tests'] is not None else '—'} | {r['skipped']} | {r['seconds']} | {r['exit_code']} |\n"
text+='\n## Exact command ledger\n\n'
text+='Every detached verification, render, authoring, compiler and repin command run through `run_logged.py` is retained below, including failed and superseded attempts. Times are UTC; seconds are elapsed wall time. Short read-only source inspections were not benchmark runs. Heavy launch form was `setsid nohup python3 reports/b71_s5/run_logged.py NAME COMMAND ... > reports/b71_s5/NAME.launch.log 2>&1 < /dev/null & wait $!`, with log polling. Batch runners use the same recorder for each command.\n\n'
text+='| Run / log | Start UTC | Seconds | Exit | Exact argv |\n| --- | --- | ---: | ---: | --- |\n'
for r in rows:
 command=shlex.join(r['argv']).replace('|','&#124;').replace('\n','\\n')
 text+=f"| [{r['name']}](reports/b71_s5/{r['name']}.log) | {r['start_utc']} | {r['seconds']} | {r['exit_code']} | `{command}` |\n"
text+='\nFailures are retained as evidence: early compiler/fixture bring-up; historical tests assuming the old cave address, FONT-only profiles or small XBE; a projection that detected edits during observation and refused to publish; canonical registry formatting and inherited missing evidence. The final rows record the corrected checks. No native or release gate was weakened to accept foreign bytes, skip registry files, or claim gameplay.\n'
(ROOT/'ASTRA_REPORT.md').write_text(text)
print(json.dumps(summary,indent=2))
