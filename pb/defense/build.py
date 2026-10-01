#!/usr/bin/env python3
"""DESIGN: fit modern split-component menus to sourced defensive coverage rates.
PROVED OFFLINE: emitted v2 packs target each exact phase-2 compiled resource.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import random
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_playbook_pack as pk, nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_inspector as ip, nfl2k5_match_coverage as match
from pb.verify_league import OuterImage,BOOK_ENTRIES

# DESIGN: explicit encodable subset. Complete modern route-distribution policies are excluded.
CONCEPTS={
 'Zero':('Cover 0','COVER_0',1),
 'One Heat':('Cover 1','COVER_1',1),
 'One Robber':(match.MATCH_PRESETS[4],'COVER_1',0),
 'Two Man':('Cover 2 Man','2_MAN',0),
 'Two Hard':('Cover 2 Hard','COVER_2',0),
 'Two Soft':('Cover 2 Soft','COVER_2',0),
 'Two Heat':('Cover 2 Soft','COVER_2',1),
 'Three Sky':('Cover 3','COVER_3',0),
 'Three Sky X':(match.MATCH_PRESETS[0],'COVER_3',0),
 'Three Cloud X':(match.MATCH_PRESETS[1],'COVER_3',0),
 'Three Cloud':('Cover 3','COVER_3',0),
 'Four Spot':('Cover 4 Quarters (spot)','COVER_4',0),
 'Four Exchange':(match.MATCH_PRESETS[2],'COVER_4',0),
 'Tampa Drop':('Tampa 2 Drop EXPERIMENTAL','COVER_2',0),
 'Six Split':('Cover 6 Split Field','COVER_6',0),
 'Fire Three':('Fire 3 Replacement (5 rush)','COVER_3',1),
 'Creeper Three':('Replacement 3 (4 rush)','COVER_3',0),
 'Sim Two':('Cover 2 Soft','COVER_2',0),
}
ORDINARY={'4-3','3-4','Nickel','Dime','Bear'}

def eligible(book,body):
    forms=[f for f in book.formations if f.name in ORDINARY]
    protected={p.index for f in book.formations if f not in forms for p in book.plays_for_formation(f.index)}
    users={}
    for f in forms:
        for p in book.plays_for_formation(f.index):
            if p.index not in protected and p.family_id==1:
                users.setdefault(p.index,[]).append(f.index)
    return forms,users


def scored_flags(flags,front_flags):
    # PROVED OFFLINE: native bits 9-11 control the curve, then the score is cubed.
    # DESIGN: keep pressure-tagged donor weights near other calls at matchup=.5.
    band=3 if flags&0x10000 and not front_flags&0x10000 else 2
    return (flags&~0xe00)|(band<<9)


def choose(book,body,forms,users,baseline,seed):
    """DESIGN: minimize squared rate error in every formation, honoring shared indices.
    This is menu allocation, not a claim that native matchup scores are uniform.
    """
    import numpy as np
    names=list(CONCEPTS); slots=sorted(p for p in users if lib.defense_component(lib.decoded_chains(body,p))=='coverage')
    covs=['COVER_0','COVER_1','2_MAN','COVER_2','COVER_3','COVER_4','COVER_6']
    counts=baseline['coverage_counts']; total=sum(counts.get(c,0) for c in covs)+counts.get('COVER_9',0)
    target=np.array([(counts.get(c,0)+(counts.get('COVER_9',0) if c=='COVER_6' else 0))/total for c in covs]+[baseline['rates']['blitz']/100])
    attrs=np.array([[int(cov==c) for c in covs]+[pressure] for _,cov,pressure in CONCEPTS.values()],dtype=float)
    incidence=np.array([[int(f.index in users[p]) for p in slots] for f in forms],dtype=float)
    # PROVED OFFLINE: 0x203F20 header curve and 0x203440 cube under matchup=.5.
    # Front factors cancel here because all authored front headers use one donor.
    cache={}; lottery=np.zeros((len(slots),len(names)))
    for j,p in enumerate(slots):
        fi=min(users[p],key=lambda i:(book.formations[i].name!='Nickel',i))
        front,_=lib.defense_donors(book,body,fi);ff=book.plays[front].flags_or_id
        for k,name in enumerate(names):
            try:d=design_for(book,body,fi,name,cache)
            except ValueError:continue # e.g. Tampa needs a native MLB.
            flags=scored_flags(book.plays[d.donor_play_index].flags_or_id,ff)
            curve=(2,1.4,1,.5,.1)[min(4,(flags>>9)&7)]
            lottery[j,k]=(curve*(1.525 if (flags|ff)&0x10000 else 1))**3
    # DESIGN: replacement-pressure availability increases with measured blitz use.
    # This is explicitly a design allocation, not a charted creeper rate.
    target=np.append(target,[baseline['rates']['man']/100,baseline['rates']['blitz']/200,baseline['rates']['split_family']/100])
    attrs=np.column_stack((attrs,[int(v[1] in ('COVER_0','COVER_1','2_MAN')) for v in CONCEPTS.values()],
                           [int(n in ('Creeper Three','Sim Two')) for n in names],
                           [int(v[1] in ('COVER_2','2_MAN','COVER_4','COVER_6')) for v in CONCEPTS.values()]))
    weights=np.array([6,2,1,1,1,1,1,8,8,.3,8],dtype=float)
    rng=random.Random(seed)
    valid=[list(np.flatnonzero(lottery[j])) for j in range(len(slots))]
    assignment=np.array([rng.choice(v) for v in valid]); w=lottery[np.arange(len(slots)),assignment]
    sums=incidence@(attrs[assignment]*w[:,None]);denominators=incidence@w
    def loss(v,d):return float((((v/d[:,None]-target)**2)*weights).sum())
    cost=loss(sums,denominators)
    for step in range(40000):
        j=rng.randrange(len(slots));old=assignment[j];new=rng.choice(valid[j])
        oldw,neww=lottery[j,old],lottery[j,new]
        proposed=sums+incidence[:,j,None]*(attrs[new]*neww-attrs[old]*oldw)
        den=denominators+incidence[:,j]*(neww-oldw)
        value=loss(proposed,den);temp=.008*(1-step/40000)**3
        if value<cost or (temp>0 and rng.random()<pow(2.718281828,-min(700,(value-cost)/temp))):
            assignment[j]=new;sums=proposed;denominators=den;cost=value
    return {p:names[int(v)] for p,v in zip(slots,assignment)},dict(loss=cost,
        target=dict(zip(covs+['blitz','man','replacement_design','split_family'],target.tolist())),
        scope='DESIGN weighted fit to native header curve under neutral matchup; not live CPU rates')



def design_for(book,body,fi,name,cache):
    if (fi,name) not in cache:
        preset=CONCEPTS[name][0]
        maker=match.make_match_design if preset in match.MATCH_PRESETS else lib.make_defense_design
        d=maker(book,body,fi,preset)
        if name=='Three Cloud':
            # DESIGN: right corner in flat, strong safety takes outside third.
            d.chains[8]=copy.deepcopy(d.chains[9]);d.chains[9]=copy.deepcopy(d.chains[6])
            d.chains[8][0]=(0x1B,[0,0,0,0,17,0]);d.chains[9][0]=(0x1B,[0,0,0,0,17,0])
            d.chains[9][1][1][:2]=[16*lib.YD,5*lib.YD];d.chains[9][1][1][4:]=[5,0,0]
        if name=='Three Cloud X':
            # DESIGN: left safety exchanges with LB6; left corner owns the flat.
            d.chains[8]=copy.deepcopy(d.chains[10])
            d.chains[10]=copy.deepcopy(d.chains[4])
            d.chains[10][1][1][:2]=[-16*lib.YD,5*lib.YD]
            d.chains[10][1][1][4:]=[5,0,0]
            for op,v in d.chains[6]:
                if op==0x0E:v[5]=8
            assert not match.analyze_chains(d.chains)['unresolved']
        if name in ('Two Heat','Sim Two'):
            slot=5
            _,rush=lib.defense_slot_donor(book,body,fi,slot,0x0B)
            d.chains[slot]=rush
            if name=='Sim Two':
                start=copy.deepcopy(d.front_chains[2][0]);zone=copy.deepcopy(d.chains[4][1])
                d.chains[2]=[start,zone]
        cache[fi,name]=d
    return copy.deepcopy(cache[fi,name])


def build(resource,team,profile,baseline):
    book=ip.parse_playbook_resource(resource);body=resource[32:]
    forms,users=eligible(book,body)
    choices,fit=choose(book,body,forms,users,baseline,int.from_bytes(team.encode(),'little'))
    # DESIGN: one situational call, not an invented season Spy frequency.
    # Evidence and the explicit empty-record policy: pb/research/SPY.md.
    spy_target=None
    if team=='KC':
        for p in sorted(choices):
            fi=min(users[p],key=lambda i:(book.formations[i].name!='Nickel',i))
            if choices[p] in ('Three Sky','Three Cloud','Two Soft','Four Spot') and any(c&31==lib.MLB for c in lib.defense_personnel(book,body,fi)['codes']):
                spy_target=p
                break
        if spy_target is None:raise ValueError('KC needs a native MLB spot-zone Spy destination')
    cache={}; plays=[];catalog=[];formations=[]
    # DESIGN: front geometry only; native personnel and compatibility types remain intact.
    geom={}
    for f in forms:
        info=lib.defense_personnel(book,body,f.index)
        rec=lib.formation_record(body,f.index)
        xy=[(s.x[0],s.z[0]) for s in rec.slots];label=f.name
        lbs=[s for s,c in enumerate(info['codes']) if c&31 in (lib.MLB,lib.OLB) and s>=4]
        if f.name=='Nickel' and baseline['rates']['blitz']>=30 and len(lbs)>=2:
            xy=lib.double_a_positions(book,body,f.index);label='Nickel Mug'
        elif f.name in ('4-3','3-4'):
            if profile['base_front_inferred']=='odd':
                for s,x in ((1,137),(2,-137),(3,0)):xy[s]=(x,46)
                xy[0]=(365,46);label=f.name+' Tite Look'
            else:
                xy[0]=(411,46);xy[1]=(-411,46);label=f.name+' Wide'
        if xy!=[(s.x[0],s.z[0]) for s in rec.slots]:
            formations.append(pk.PackFormation('f'+str(f.index),label,tuple(xy),tuple(info['codes']),pk.PackDonor(f.index,f.name),f.index,f.name,info['category_index']))
        geom[f.index]=dict(name=label,positions=xy,native_personnel=info['labels'],category_code=info['category_code'])
    for p in sorted(users):
        spy_slots=()
        fi=min(users[p],key=lambda i:(book.formations[i].name!='Nickel',i))
        component=lib.defense_component(lib.decoded_chains(body,p))
        if component=='full':raise ValueError('Unexpected full defense destination')
        if component=='front':
            front,_=lib.defense_donors(book,body,fi)
            chains=lib.decoded_chains(body,front);donor=book.plays[front]
            name='Front '+str(p)
            # Keep the proved front mask, change lane rush geometry per unique record.
            for s in lib.defense_active(chains):
                chains[s][0]=(0x1B,[0,0,0,0,17,0])
                for op,v in chains[s]:
                    if op==0x0B:v[1]=max(0,min(16,int(v[1])+(p%3)-1))
            cov=None
        else:
            name=choices[p];d=design_for(book,body,fi,name,cache)
            if p==spy_target:
                slot=next(s for s,c in enumerate(lib.defense_personnel(book,body,fi)['codes']) if c&31==lib.MLB)
                d.set_assignment(book,body,slot,'spy',depth_yd=4)
                spy_slots=tuple(sorted(d.spy_slots))
            chains=d.chains;front=d.front_index;donor=book.plays[d.donor_play_index];cov=CONCEPTS[name][1]
            # DESIGN: small legal depth variants give distinct calls without duplicate links.
            for s,chain in enumerate(chains):
                if s in lib.defense_active(chains):
                    if s not in spy_slots:
                        chain[0]=(0x1B,[0,0,0,0,17,0])
                    for op,v in chain:
                        if op==0x0D and v[1]>=15*lib.YD:v[1]+=(p%3)*lib.YD
        for c in chains:pk.codec.validate_defense_operands(c)
        if p==0:
            # Keep the first pool chain referenced: the native inspector requires node zero.
            donor=book.plays[0]
            original=lib.decoded_chains(body,0)
            if (0 in lib.defense_active(original)) != (0 in lib.defense_active(chains)):
                raise ValueError('Node-zero keeper changes active mask')
            chains[0]=None
        flags=scored_flags(donor.flags_or_id,book.plays[front].flags_or_id) if component=='coverage' else donor.flags_or_id
        label=name.split()[0]+' Spy' if spy_slots else name
        plays.append(pk.PackPlay('d'+str(p),'PB '+label+' '+str(p) if component!='front' else 'PB '+name,
            'defense',pk._freeze_chains(chains),pk.PackDonor(donor.index,donor.name,donor.flags_or_id,lib.defense_signature(body,donor.index)),
            flags,p,book.plays[p].name,concept=name,defense_formation=book.formations[fi].name,
            front_index=front,component=component,spy_slots=spy_slots))
        catalog.append(dict(play=p,concept=name,coverage=cov,component=component,formations=users[p],preview_front=front,donor=donor.index,spy_slots=list(spy_slots)))
    notes='DESIGN: '+profile['dc']+'; '+profile['family']+'. 2025 baseline '+str(profile['baseline_team'])+'. '+profile['baseline_role']+'. PROVED OFFLINE: exact offense source required; retail special menus retained. No RPO/read option. Custom CPU score bands use proved bits 9-11. Bounded native exchanges and Tampa landmarks only; complete match/Tampa policies excluded. KC situational Spy uses the existing runtime intent; see pb/research/SPY.md. Other teams emit empty Spy records.'
    pack=pk.PlaybookPack(pk.PackBook(team,'NFL 2K28 '+team+' Defense','SOFTDRINK / Astra','0.3.0','CC0-1.0',(),notes),
        pk.PackBase(pk.book_fingerprint(body),len(book.formations),len(book.plays),book.node_count),tuple(formations),tuple(plays),pk.DEFENSE_SCHEMA)
    return pack,dict(team=team,status='DESIGN',fit=fit,formations=geom,plays=catalog)


def semantic(pack):
    return hashlib.sha256(json.dumps(dict(forms=[(f.slot_positions,f.position_codes) for f in pack.formations],plays=[(p.replace_index,p.assignments,p.play_flags) for p in pack.plays]),sort_keys=True).encode()).hexdigest()


def build_team(job):
    row,profile,baseline=job;t=row['team']
    with OuterImage(Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')) as image:
        source=pk.apply_pack_to_resource(image.read_entry(BOOK_ENTRIES[t]),pk.load_pack(ROOT/row['pack']),xbe=image.path).replacement
    pack,catalog=build(source,t,profile,baseline)
    check=pk.check_pack(pack,book=ip.parse_playbook_resource(source),body=source[32:],xbe=image.path)
    if not check.ok:raise ValueError(t+' '+check.text())
    result=pk.apply_pack_to_resource(source,pack,xbe=image.path)
    dest=ROOT/f'data/playbooks/softdrink_{t.lower()}_defense.2k5book';pk.save_pack(pack,dest)
    (ROOT/f'pb/defense/{t}.json').write_text(json.dumps(catalog,indent=2)+'\n')
    keys=('schema','source_sha256','replacement_sha256','old_node_count','new_node_count',
          'old_formation_count','new_formation_count','old_play_count','new_play_count',
          'replaced_formation_indices','replaced_play_indices')
    receipt=dict(team=t,pack=str(dest.relative_to(ROOT)),semantic_sha256=semantic(pack),plays=len(pack.plays),
        formations=len(pack.formations),compile={k:result.report[k] for k in keys if k in result.report})
    print(t,len(pack.plays),result.report['new_node_count'],flush=True)
    return receipt

def main():
    from concurrent.futures import ProcessPoolExecutor
    ap=argparse.ArgumentParser();ap.add_argument('--team',default='');ap.add_argument('--workers',type=int,default=4);args=ap.parse_args()
    profiles=json.loads((ROOT/'pb/research/defense_profiles.json').read_text());rates=json.loads((ROOT/'pb/research/defense_tendencies_2025.json').read_text())['teams']
    league=json.loads((ROOT/'pb/league_manifest.json').read_text())['teams'];jobs=[]
    for row in league:
        t=row['team']
        if args.team and t!=args.team:continue
        profile=profiles[t];jobs.append((row,profile,rates[profile['baseline_team'] or profile['design_fallback_team']]))
    if len(jobs)==1:manifest=[build_team(jobs[0])]
    else:
        # DESIGN: independent resources; only the parent writes the league manifest.
        with ProcessPoolExecutor(max_workers=args.workers) as pool:manifest=list(pool.map(build_team,jobs))
    if not args.team:(ROOT/'pb/defense_manifest.json').write_text(json.dumps(dict(status='PROVED OFFLINE',teams=manifest),indent=2)+'\n')
if __name__=='__main__':main()
