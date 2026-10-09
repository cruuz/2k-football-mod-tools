"""Refresh all observed schedules from pinned current nflverse Parquet.

DESIGN: absent schedules retain F's explicitly modeled targets; they do not
become observed contracts. Exact cash is outside the five-field model.
"""
import collections
import copy
import json
import sys
from .generate import ROOT,readcsv,dump
from mod_editor.core import nfl2k5_roster_records as rr
from tools.franchise_economy.contracts import fit_schedule,fit_minimum,charges,FIELDS
from tools.franchise_economy.import_contracts import cap_schedule,normalize,read_pinned_parquet


def update(result,doc,fa,out,pins):
    sys.path.insert(0,str(fa/'vendor'))
    rows=read_pinned_parquet(fa/'data/historical_contracts.parquet',pins['historical_contracts.parquet'],active_only=True)
    bygsis=collections.defaultdict(list);byotc=collections.defaultdict(list);byname=collections.defaultdict(list)
    for r in rows:
        bygsis[r['gsis_id']].append(r);byotc[str(r['otc_id'])].append(r);byname[normalize(r['player'])].append(r)
    old={(r['pool'],r['index']):r for r in json.loads((ROOT/'fc/data/contract_audit.json').read_text())['ledger']}
    reviews={(r['pool'],r['index']):r for r in json.loads((ROOT/'fc/data/identity_review.json').read_text())['entries']}
    ids={(r['pool'],r['index']):r for r in result['franchise_history']['players']}
    ledger=[];edits=[];changed=[]
    for p in doc.players:
        if not any(t<32 for t in p.teams):continue
        key=(p.pool,p.index);prev=old[key];ident=ids[key];review=reviews.get(key,{})
        cand=bygsis.get(ident['gsis_id'],[]) or byotc.get(str(prev['otc_id']),[]) or byname.get(normalize(p.display),[])
        if len(cand)>1 and 'active_value_millions' in review:
            cand=[r for r in cand if r['value']==review['active_value_millions']]
        assert len(cand)<=1,(p.display,len(cand))
        r=cand[0] if cand else None
        try:
            if r is None:raise ValueError('no active source contract')
            schedule,excluded=cap_schedule(r)
            fit=fit_schedule(schedule,opening_priority=True);kind='observed';fallback=None
        except (ValueError,TypeError) as exc:
            if prev['schedule_kind']=='modeled':
                fit=copy.deepcopy(prev['fit']);fallback=copy.deepcopy(prev['fallback'])
            else:
                # Owen Pappoe has no active row in the current release. A prior
                # observed deal cannot be silently relabeled as still current.
                minimums=json.loads((ROOT/'data/nfl2k5_franchise_economy.json').read_text())['minimums']['dollars']
                pro=min(rr.accrued_seasons(p.record.values['years_pro']),7)
                fit=fit_schedule([minimums[pro]],opening_priority=True)
                fallback=dict(evidence='DESIGN',rule='one-year active-roster CBA minimum',
                              experience_proxy=pro,reason=str(exc),previous_observed_expired=True)
            kind='modeled';excluded=[]
        if fallback and fallback['rule']=='one-year active-roster CBA minimum':
            fit=fit_minimum(fit['source_cap_dollars'][0])
        assert set(fit['fields'])==FIELDS
        team=next(t for t in p.teams if t<32)
        item=dict(pool=p.pool,index=p.index,name=p.display,team=team,gsis_id=ident['gsis_id'],
            otc_id=r['otc_id'] if r else prev['otc_id'],source='historical_contracts.parquet',
            schedule_kind=kind,fallback=fallback,fit=fit,excluded_years=excluded,
            source_row=r,old_fields=prev['fit']['fields'],old_source_cap=prev['fit']['source_cap_dollars'])
        ledger.append(item)
        edits.append(dict(pool=p.pool,index=p.index,first=p.first,last=p.last,fields=fit['fields']))
        if kind=='observed' and fit['source_cap_dollars']!=prev['fit']['source_cap_dollars']:
            changed.append({k:item[k] for k in ('index','name','team','gsis_id','fit','old_fields','old_source_cap')})
    assert len(ledger)==1696
    assert len(changed)==24,len(changed)
    totals=[]
    for t in doc.teams[:32]:
        entries=[r for r in ledger if r['team']==t.index]
        payroll=sum(r['fit']['represented_cap_dollars'][0] for r in entries)
        totals.append(dict(team=t.abbreviation,players=len(entries),payroll=payroll,cap=301200000,
                           room=301200000-payroll,within_cap=payroll<=301200000,
                           observed=sum(r['schedule_kind']=='observed' for r in entries)))
    report=dict(evidence='PROVED OFFLINE',source=pins['historical_contracts.parquet'],ledger=ledger,
        observed=sum(r['schedule_kind']=='observed' for r in ledger),modeled=sum(r['schedule_kind']=='modeled' for r in ledger),
        changed_schedules=changed,teams=totals,
        design='Unavailable schedules retain previously modeled targets. Only observed source schedules are refreshed. Five-field cap liability, not cash.')
    result['edits'].extend(edits)
    result['fr_contracts']=dict(source=pins['historical_contracts.parquet'],observed=report['observed'],modeled=report['modeled'])
    dump(out/'contract_audit.json',report)
    dump(out/'contract_fragment.json',dict(schema=result['schema'],edits=edits))
    print('contracts',report['observed'],report['modeled'],'changed',len(changed),'cap',sum(r['within_cap'] for r in totals))
