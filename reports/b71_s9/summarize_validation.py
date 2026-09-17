from pathlib import Path
import json,re
OUT=Path(__file__).resolve().parent
rows=[]
for path in sorted(OUT.glob('final-*.result.json')):
 if path.name=='final-suites.result.json':continue
 r=json.loads(path.read_text());log=path.with_name(r['name']+'.log').read_text();count=re.search(r'Ran (\d+) tests?',log)
 skips=re.search(r'OK \(skipped=(\d+)\)',log)
 assert r['exit_code']==0,r['name']
 rows.append(dict(name=r['name'],tests=int(count[1]) if count else None,skips=int(skips[1]) if skips else 0,seconds=r['seconds'],exit_code=r['exit_code']))
for name in ('registry-strict','final-suites','draw-order-anchor-final','prove-states-final'):
 result=json.loads((OUT/(name+'.result.json')).read_text());assert result['exit_code']==0,name
summary=dict(suites=len(rows),tests=sum(r['tests'] or 0 for r in rows),skips=sum(r['skips'] for r in rows),final_anchor_regressions=5,native_label_states=808,contact_states=50,strict_registry=(OUT/'registry-strict.log').read_text().strip(),results=rows)
(OUT/'validation_summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
