#!/usr/bin/env python3
"""PROVED OFFLINE: native candidate/score extraction and conditional rate model.
DESIGN: explicit synthetic matchup, neutral profile and category-provider fixture.
"""
from collections import Counter
import itertools
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from pb.defense.selector import Selector,XBE,distribution
from pb.defense.build import CONCEPTS
from mod_editor.core import nfl2k5_play_library as lib

def attrs(body,pair,catalog):
    front=lib.decoded_chains(body,pair['front']);cover=lib.decoded_chains(body,pair['coverage'])
    active=lib.defense_active(front)|lib.defense_active(cover)
    assert active==set(range(11)),pair
    chains=lib.effective_defense(front,cover);counts=lib.defense_counts(chains)
    row=catalog.get(pair['coverage']);concept=row['concept'] if row else 'retail'
    known=row and row['component']=='coverage'
    cov=CONCEPTS[concept][1] if known else None
    # DESIGN: family proxy follows authored intent; mixed exchanges stay zone-family.
    man=cov in ('COVER_0','COVER_1','2_MAN') if cov else any(op==0x0E for ch in chains for op,v in ch)
    split=cov in ('COVER_2','2_MAN','COVER_4','COVER_6') if cov else len(counts['deep']) in (2,4)
    rushers=counts['rushers']
    expected=CONCEPTS[concept][2] if known else None
    assert not known or (len(rushers)>=5)==bool(expected),(concept,pair,rushers)
    if concept in ('Creeper Three','Sim Two'):
        assert len(rushers)==4 and 5 in rushers and 2 not in rushers,(concept,pair,rushers)
    return dict(man=int(man),zone=int(not man),split_family=int(split),blitz=int(len(rushers)>=5),
        cover0=int(cov=='COVER_0'),replacement=int(concept in ('Creeper Three','Sim Two')),modern=int(bool(known)))

def sweep(team,xbe,raw):
    s=Selector(xbe,raw);metadata=json.loads((ROOT/f'pb/defense/{team}.json').read_text());catalog={r['play']:r for r in metadata['plays']}
    ordinary={int(i) for i in metadata['formations']}
    states=[];cache={};native=[];hist=Counter();rates=Counter();den=0
    # DESIGN: distance is recorded but the full 0x20B400 policy is not initialized.
    # Mapping-only fixture exposes this limitation instead of inventing distance weights.
    for down,distance,yardline,offense_code in itertools.product((1,2,3,4),(2,7,15),(1,5,20,50,80,95,99),(0,6,8)):
        code=s.requested_category(offense_code,yardline,down)
        key=str(code)
        if key not in cache:
            data=distribution(s,offense_code,yardline,down)
            native.append(data['fixture']);cache[key]=data
            for pair in data['pairs']:pair['features']=attrs(raw[32:],pair,catalog)
        data=cache[key];state=dict(down=down,distance=distance,yardline=yardline,offense_code=offense_code,category_code=code)
        states.append(state);hist[code]+=1
        for pair in data['pairs']:
            # Compare ordinary modern calls only; retail goal line is reported separately.
            if pair['formation'] in ordinary:
                den+=pair['probability']
                for k,v in pair['features'].items():rates[k]+=v*pair['probability']
    result=dict(status='PROVED OFFLINE',team=team,scope='Conditional native-selector fixture, not live CPU rates',
        state_count=len(states),ordinary_state_equivalents=den,category_counts=dict(hist),
        rates={k:100*v/den for k,v in rates.items()},native_full_selector_witnesses=native,
        states=states,distributions=cache,stub_calls=s.stub_calls,
        limitations=['Full 0x20B400 situational/game-plan policy is replaced with a category fixture.',
            'Distance has no effect in this fixture; native 0x208480 still receives down and field position.',
            'Formation score=1, player matchup=.5, 54-float profile=0, mirror/prevent predicates=false.',
            'Split-family is authored coverage intent, not observed pre-snap two-high.',
            'Native validator and candidate/score/lottery code execute; full-game behavior needs main lab.'])
    return result

def main():
    teams=[r['team'] for r in json.loads((ROOT/'pb/defense_manifest.json').read_text())['teams']];xbe=XBE.read_bytes();allrows={}
    dest=ROOT/'pb/receipts/defense';dest.mkdir(exist_ok=True)
    for t in teams:
        r=sweep(t,xbe,(ROOT/f'.scratch/pb3/compiled/{t}.bin').read_bytes())
        (dest/f'{t}-selector.json').write_text(json.dumps(r,indent=2)+'\n')
        allrows[t]={k:v for k,v in r.items() if k not in ('states','distributions','stub_calls')}
        print(t,{k:round(v,2) for k,v in r['rates'].items()},flush=True)
    (dest/'selector-summary.json').write_text(json.dumps(dict(status='PROVED OFFLINE',teams=allrows),indent=2)+'\n')
if __name__=='__main__':main()
