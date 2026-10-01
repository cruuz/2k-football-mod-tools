"""PROVED OFFLINE: semantic preservation and independently decoded differences."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fr.generate import F,FA,OUT,dump,digest
from mod_editor.core import nfl2k5_roster_records as rr,nfl2k5_career_stats as cs
from tests.nfl2k5_supersim_draft_fixture import retail_roster
from tools.franchise_economy.contracts import FIELDS,charges

G=Path('/media/noah/Storage/.b76-research/main/freeze/candG/league_roster_edits_candG_fr.json')

def run():
    f=json.loads(F.read_text());g=json.loads(G.read_text())
    assert g['edits'][:len(f['edits'])]==f['edits']
    assert all(g[k]==v for k,v in f.items() if k!='edits')
    old_body,_=rr.apply_body(retail_roster(),f)
    body,receipt=rr.apply_body(retail_roster(),g);assert not receipt['log']
    assert body==(OUT/'g_body.bin').read_bytes()
    old=rr.RosterDocument(old_body,reference_year=2026);new=rr.RosterDocument(body,reference_year=2026)
    before={(p.pool,p.index):p for p in old.players}
    after={(p.pool,p.index):p for p in new.players}
    fa_keys={(r['pool'],r['index']) for r in g['free_agent_pool']}
    history_keys={(r['pool'],r['index']) for r in g['franchise_history']['players']}
    changed_college={(r['pool'],r['index']) for r in g['college_updates']}
    intentional=collections.defaultdict(set)
    for e in g['edits'][len(f['edits']):]:intentional[e['pool'],e['index']].update(e['fields'])
    equal=0;changes=[]
    for key,p in before.items():
        q=after[key]
        for field,value in p.record.values.items():
            if field in rr.POINTER_FIELDS:continue
            if field not in intentional[key]:
                assert q.record.values[field]==value,(key,field)
                equal+=1
            elif q.record.values[field]!=value:
                changes.append(dict(pool=p.pool,index=p.index,name=q.display,field=field,before=value,after=q.record.values[field]))
        assert key in fa_keys or (p.first,p.last)==(q.first,q.last)
        assert key in changed_college or p.college==q.college
        assert p.teams==q.teams
    for a,b in zip(old.teams,new.teams):
        assert old_body[a.offset:a.offset+rr.TEAM_SIZE]==body[b.offset:b.offset+rr.TEAM_SIZE],a.index
    old_hist=cs.decode_body(old_body);new_hist=cs.decode_body(body)
    unrelated=0
    for key in before:
        if key not in history_keys:
            assert old_hist.history_words[key]==new_hist.history_words[key]
            unrelated+=1
    assert len(new.free_agents)==len(fa_keys)==236
    assert all((new.by_offset[o].pool,new.by_offset[o].index) in fa_keys for o in new.free_agents)
    contract=json.loads((OUT/'contract_audit.json').read_text())
    minimums=[r for r in contract['ledger'] if r['fallback'] and r['fallback']['rule']=='one-year active-roster CBA minimum']
    assert all(r['fit']['represented_cap_dollars'][0]>=r['fit']['source_cap_dollars'][0] for r in minimums)
    assert all(r['within_cap'] for r in contract['teams'])
    assert all(abs(r['fit']['errors_dollars'][0])<=20000 for r in contract['ledger'] if r['schedule_kind']=='observed')
    initial=json.loads((ROOT/'fc/data/contract_audit.json').read_text())['ledger']
    old_min={r['index'] for r in initial if r['fallback'] and r['fallback']['rule']=='one-year active-roster CBA minimum'}
    current={r['index']:r for r in contract['ledger']}
    original_min_review=[dict(index=i,name=current[i]['name'],current_kind=current[i]['schedule_kind'],
                       floor=current[i]['fit']['source_cap_dollars'][0],charge=current[i]['fit']['represented_cap_dollars'][0]) for i in sorted(old_min)]
    report=dict(evidence='PROVED OFFLINE',f_sha256=digest(F),g_sha256=digest(G),body_sha256=hashlib.sha256(body).hexdigest(),
        unchanged_original_edits=len(f['edits']),unchanged_original_metadata_keys=[k for k in f if k!='edits'],
        unchanged_named_field_values=equal,unexpected_named_field_changes=0,
        all_52_team_record_bytes_equal=True,special_teams_entries_unchanged=len(f['special_teams']),
        unrelated_history_streams_preserved=unrelated,replaced_history_players=len(history_keys),
        pool=receipt['franchise_history'],unsigned_members=236,retired_historical_fa_aliases=len(g['fr_free_agents']['retired_fa_aliases']),
        colleges_changed=len(changed_college),minimum_fallbacks=len(minimums),minimum_below_floor=0,
        original_50_fallbacks_review=original_min_review,team_totals=contract['teams'],changed_fields=changes)
    dump(OUT/'preservation.json',report)
    b=json.loads((FA/'results/summary.json').read_text());a=json.loads((OUT/'audit_g/summary.json').read_text())
    rows=[]
    for field in sorted(set(b['fields'])|set(a['fields'])):
        x=b['fields'].get(field,{});y=a['fields'].get(field,{})
        rows.append(dict(field=field,before_mismatch=x.get('mismatch'),before_checked=x.get('checked'),
                         after_mismatch=y.get('mismatch'),after_checked=y.get('checked'),category=y.get('category',x.get('category'))))
    extra_names=['defensive_tackles','field_goals_attempted_1_29','field_goals_attempted_30_39',
                 'field_goals_attempted_40_49','field_goals_attempted_50_plus']
    extra=collections.defaultdict(lambda:dict(before_mismatch=0,after_mismatch=0,checked=0))
    for ident in g['franchise_history']['players']:
        key=(ident['pool'],ident['index']);p=after[key]
        if not any(t<32 for t in p.teams):continue
        for scope in ('last','career'):
            seasons=[s for s in ident['seasons'] if scope=='career' or s['year']==2025]
            if not seasons:continue
            for name in extra_names:
                field=cs.BY_NAME[name]
                expected=sum(s['stats'][name] for s in seasons)
                actual=[]
                for h in (old_hist,new_hist):
                    actual.append(sum(float(cs.Word(w).value(field)) for w in h.history_words[key]
                        if cs.Word(w).field==field.id and not cs.Word(w).deleted and cs.Word(w).phase=='regular'
                        and (scope=='career' or (not cs.Word(w).folded and cs.Word(w).slot==p.record.values['years_pro']-1))))
                r=extra[scope+'_'+name];r['checked']+=1
                r['before_mismatch']+=actual[0]!=expected;r['after_mismatch']+=actual[1]!=expected
                assert actual[1]==expected,(p.display,name,scope)
    for field,r in sorted(extra.items()):
        rows.append(dict(field=field,before_mismatch=r['before_mismatch'],before_checked=r['checked'],
                         after_mismatch=r['after_mismatch'],after_checked=r['checked'],
                         category='supplemental_combined_tackle_policy' if 'tackles' in field else 'supplemental_distance_attempts'))
    with (OUT/'before_after.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    dump(OUT/'before_after.json',dict(fields=rows,before_meta=b['meta'],after_meta=a['meta']))
    print({k:v for k,v in report.items() if k not in ('changed_fields','team_totals','original_50_fallbacks_review','unchanged_original_metadata_keys')})

if __name__=='__main__':run()
