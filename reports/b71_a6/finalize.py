"""Audit, write the handoff, and commit only explicit delivery paths."""
from pathlib import Path
import datetime,json,shlex,subprocess,time
from run import ROOT,REPORT,run
assert run('final-audit',['python3','reports/b71_a6/final_audit.py'])==0
records=[json.loads(s) for s in (REPORT/'commands.jsonl').read_text().splitlines()]
latest={r['label']:r for r in records}
summary={}
for kind in ('fast','presentation','apf','gates'):
 files=json.loads((REPORT/(kind+'-suite-paths.json')).read_text())
 summary[kind]=[dict(path=f,**latest['final-'+Path(f).stem]) for f in files]
(REPORT/'final-suite-results.json').write_text(json.dumps(summary,indent=2)+'\n')
(ROOT/'ASTRA_LAST_MESSAGE.md').write_text('''# Beta 71 A6 handoff

Integrated C5 metadata, scorebug v3, modern Arrowhead, APF situation masks and fourth-down/Xenia changes on the private branch `astra/b71-a6-integrate`. Fixed the shared colour/Arrowhead field composition and verified all nine variants. All requested suites and both studios' release/runtime closures have passing final results; precise skips, failures before correction, commands and timings are in `ASTRA_REPORT.md`.

Production manifest generation remains BLOCKED by read-only Storage. The committed manifest is an explicitly non-release XBE projection. The exact regeneration script is `reports/b71_a6/manifest_regen.sh`.

The requested Advanced disc builder is `reports/b71_a6/build_testdisc71.py`, PREPARED_NOT_RUN. No disc receipt or gameplay witness is claimed. No push or emulator launch.

Private Git: `.scratch/git-a6`. Bundle: `.scratch/astra-b71-a6.bundle`. Final head/tree, bundle SHA-256, verification and fresh-fetch receipt: `.scratch/astra-b71-a6-delivery.json`.

ASTRA_DONE
''')
commands=[]
def invoke(argv):
 start=time.monotonic();p=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True)
 commands.append(dict(command=shlex.join(argv),exit_code=p.returncode,seconds=round(time.monotonic()-start,3),stdout=p.stdout,stderr=p.stderr))
 (ROOT/'.scratch/astra-b71-a6-final-commit.json').write_text(json.dumps(commands,indent=2)+'\n')
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
 return p.stdout
invoke(['python3','reports/b71_a6/write_report.py'])
paths=sorted({str(p.relative_to(ROOT)) for p in REPORT.iterdir() if p.is_file()}|
             {p.name for p in ROOT.glob('ASTRA_B71_*_REPORT.md')}|
             {p.name for p in ROOT.glob('WIRING_B71_*.md')}|
             {'ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md','WIRING.md'})
(REPORT/'delivery-paths.json').write_text(json.dumps(paths+['reports/b71_a6/delivery-paths.json'],indent=2)+'\n')
paths.append('reports/b71_a6/delivery-paths.json');paths=sorted(set(paths))
g=['git','--git-dir=.scratch/git-a6','--work-tree=.']
invoke(g+['add','-f','--']+paths)
# Check the product change independently of verbatim command-output whitespace.
invoke(g+['diff','a142739b','--check','--','mod_editor','packaging','tests','tools','data','docs/modern_arrowhead'])
invoke(g+['commit','-m','Document beta 71 A6 validation and prepare the combined disc handoff','--']+paths)
print(invoke(g+['log','-1','--oneline']),end='')
