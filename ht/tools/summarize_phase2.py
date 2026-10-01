#!/usr/bin/env python3
"""Write reviewable worksheets and exhaustive phase 2 decision inventories."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
data=json.loads((ROOT/'data/nfl2k5_historic_rosters/manifest.json').read_text())
ledger=json.loads((ROOT/'ht/evidence/phase2_value_decisions.json').read_text())['values']
columns=['team','season','player','first','last','jersey','position','height','weight','depth','retail_slot']
fields=['player','jersey','position','height','weight','depth','ratings','equipment','game_template','display_name']
columns += [f+'_basis' for f in fields]
with (ROOT/'ht/evidence/phase2_worksheets.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,columns,lineterminator="\n");w.writeheader()
    for t in data['teams']:
        for p in t['players']:
            row={k:p.get(k) for k in columns[:11]};row.update(team=t['name'],season=t['season'])
            row.update({field+'_basis':json.dumps(p['fields'][field],ensure_ascii=False,sort_keys=True) for field in fields})
            w.writerow(row)
teams=[];disagreements=[]
for t in data['teams']:
    for p in t['players']:
        disagreements += [dict(team=t['name'],player=p['player'],**d) for d in p['disagreements']]
    teams.append(dict(team=t['name'],season=t['season'],players=len(t['players']),omitted=len(t['omitted']),
                      retail_ratings=sum(p['retail_rating_preserved'] for p in t['players']),source=t['source_url']))
summary=dict(label='PROVED OFFLINE',teams=teams,players=sum(t['players'] for t in teams),
             previous_blocked_rows=702,current_blocked_rows=sum(len(p['blockers']) for t in data['teams'] for p in t['players']),
             classifications=dict(Counter(d['label'] for d in ledger)),
             decisions_by_field=dict(Counter(d['field'] for d in ledger)),disagreements=disagreements,
             design_numbers=[d for d in ledger if d['field']=='jersey' and d['label']=='DESIGN'],
             uncertain_sizes=[d for d in ledger if d['field'] in ('height','weight')],
             duplicate_source_numbers=[dict(team=t['name'],jersey=number,
                 players=[dict(player=p['player'],basis=p['fields']['jersey']) for p in t['players'] if p['jersey']==number])
                 for t in data['teams'] for number,count in Counter(p['jersey'] for p in t['players']).items() if count>1],
             manifest_sha256=hashlib.sha256((ROOT/'data/nfl2k5_historic_rosters/manifest.json').read_bytes()).hexdigest())
(ROOT/'ht/evidence/phase2_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
lines=['# Phase 2 season selections','',
       '**DESIGN:** Playable active snapshots from each season article, not cumulative season appearances. Every omitted source-union member is retained in the manifest. Every authored field has a per-value basis in the [CSV worksheets](evidence/phase2_worksheets.csv).', '',
       '| Team | Players | Omitted union members | Retail rating vectors | Season article |',
       '| --- | ---: | ---: | ---: | --- |']
for t in teams:
    lines.append(f"| {t['team']} | {t['players']} | {t['omitted']} | {t['retail_ratings']} | [Source]({t['source']}) |")
lines += ['', '**PROVED OFFLINE:** The table counts generated worksheet records. Historical membership claims are sourced per player in the worksheets.','',
          '**DESIGN:** All non-PROVED decisions, including ratings, depth, equipment, display shortening and retained game-template fields, are enumerated in [the decision ledger](evidence/phase2_value_decisions.json).','',
          '## Number and size exceptions','', '**PROVED OFFLINE:** DESIGN jersey count: '+str(len(summary['design_numbers']))+'. Explicit article number 00 is encoded as zero for Jim Otto and Ken Burrough.','',
          '| Team | Player | Field | Game value | Basis |','| --- | --- | --- | ---: | --- |']
for d in summary['design_numbers']+summary['uncertain_sizes']:
    lines.append(f"| {d['team']} | {d['player']} | {d['field']} | {d['value']} | {d['label']}: {d['method']} |")
lines += ['', '**PROVED OFFLINE:** All number, position and size disagreements are listed in [the phase 2 summary](evidence/phase2_summary.json). Measurement thresholds use converted Wikidata values before rounding to game integers.','']
(ROOT/'ht/PHASE2_ROSTERS.md').write_text('\n'.join(lines))
print(json.dumps({k:summary[k] for k in ('players','current_blocked_rows','classifications','decisions_by_field')},indent=2))
