"""Require every requested final check and a frozen product before delivery."""
from pathlib import Path
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));R=ROOT/'reports/b71_a6'
rows=[json.loads(s) for s in (R/'commands.jsonl').read_text().splitlines()];latest={r['label']:r for r in rows}
expected=set()
for kind in ('fast','gates','presentation','apf'):
 expected|={'final-'+Path(p).stem for p in json.loads((R/(kind+'-suite-paths.json')).read_text())}
expected|={'final-scorebug-layout','final-scorebug-project','final-colour-all-pins'}
expected|={'stage-2k5-final','release-2k5-final','runtime-2k5-final','stage-apf-final','release-apf-final','runtime-apf-final','registry-final','registry-plan-list','integration-audit','owner-size-audit','apf-cross-owner'}
expected|={'composition-s13'+t+w+'.iff' for t in 'dan' for w in 'drs'}
missing=sorted(expected-set(latest));failed=sorted(k for k in expected&set(latest) if latest[k]['exit_code'])
assert not missing,('missing final results',missing)
assert not failed,('failed final results',failed)
from mod_editor.core.nfl2k5_cave_manifest import source_fingerprints
manifest=json.loads((ROOT/'data/nfl2k5_cave_reservations.json').read_text())
assert manifest['source_sha256']==source_fingerprints()
assert manifest['b71_a6_projection']['release_manifest'] is False
assert manifest['b71_a6_projection']['production_regeneration_required'] is True
assert latest['manifest-production']['exit_code']!=0
assert not (R/'build-receipt').exists(), 'builder must remain unexecuted'
skips={};cases=0
for label in sorted(expected):
 log=(ROOT/latest[label]['log']).read_text()
 matches=re.findall(r'Ran (\d+) tests? in',log)
 if matches:cases+=int(matches[-1])
 skipped=re.findall(r'OK \(skipped=(\d+)\)',log)
 if skipped:skips[label]=int(skipped[-1])
size=sum(p.stat().st_size for p in (ROOT/'.scratch').rglob('*') if p.is_file())
assert size<200*1024*1024
result=dict(required_completed=len(expected),all_requested_suites_and_closures_exit_zero=True,unit_cases_reported=cases,skipped_cases=skips,manifest_source_seals_match=True,production_manifest_blocked=True,builder_executed=False,scratch_bytes=size)
(R/'final-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
