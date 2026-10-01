#!/usr/bin/env python3
"""DESIGN: role-aware, deterministic modern team offenses. Never writes a disc."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from pb.build_giants import assignments, SHAPES, PASS, RUN, YD
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_playbook_pack as packs
from mod_editor.core.nfl2k5_complete_offense import ordinary_indices
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES

PROFILES = ROOT / 'pb/research/team_profiles.json'
ALIASES = {'ARZ':'ARI', 'STL':'LA', 'SD':'LAC', 'OAK':'LV'}
CODES = {p: (0,5,37,6,7,39,8,9,41,extra,10) for p,extra in [('11',73),('12',40),('21',11)]}
FAMILIES = {
    'wide_zone': ['Outside Zone','PA Boot','Flood','Y Cross','End Around','RB Slip','TE Drag'],
    'mcvay': ['Downhill','Outside Zone','Dagger','PA Boot','Levels','Y Cross','End Around'],
    'west_coast': ['Inside Zone','Mesh','Stick','Drive','RB Slip','TE Drag','Counter'],
    'vertical': ['Inside Zone','Dagger','Y Cross','TE Seam','Levels','Counter','PA Boot'],
    'spread': ['Inside Zone','Mesh','Levels','Stick','Dagger','RB Slip','Counter'],
    'power': ['Downhill','Counter','Inside Zone','TE Seam','PA Boot','Drive','RB Slip'],
}


def apportioned(total, weights):
    """DESIGN: largest remainder allocation, with no synthetic observed rates."""
    scale = sum(weights.values())
    exact = {k: total*v/scale for k,v in weights.items()}
    out = {k: int(v) for k,v in exact.items()}
    for k in sorted(weights, key=lambda k: (-(exact[k]-out[k]), k))[:total-sum(out.values())]:
        out[k] += 1
    return out


def role_groups(book, body):
    result = {}
    for group, canonical in CODES.items():
        for ci in book.categories:
            codes = tuple(lib.category_positions(body, ci.index))
            if codes[:6] == canonical[:6] and sorted(codes) == sorted(canonical):
                result[group] = (ci.index, codes, tuple(canonical.index(code) for code in codes))
                break
    if not {'11','21'} <= result.keys():
        raise ValueError('Required native personnel missing')
    return result


def move_roles(chains, order):
    """PROVED OFFLINE: native slot operands AND pass eligible ordinals move."""
    moved = [[(op,list(vals)) for op,vals in chain] for chain in packs.permute_assignments(chains, order)]
    inverse = {old:new for new,old in enumerate(order)}
    for chain in moved:
        for op,vals in chain:
            if op == 6:
                for n in range(1,5):
                    ordinal = int(vals[n])
                    if ordinal in range(1,6):
                        vals[n] = inverse[ordinal+5]-5
    return moved


def choose_shapes(n, profile, tendency, available):
    personnel = {p:tendency['p'+p+'_pct'] for p in ('11','12','21')}
    # DESIGN: staff changes use an explicit, disclosed menu adjustment; 2025 is a baseline only.
    for p,bonus in profile.get('personnel_bias',{}).items():
        personnel[p] += bonus
    if '12' not in available:
        personnel['11'] += personnel.pop('12')
    quotas = apportioned(n, personnel)
    gun = max(0, tendency['shotgun_pct'] - tendency['pistol_pct'])
    location = apportioned(n, {'gun':gun, 'pistol':tendency['pistol_pct'], 'uc':100-tendency['shotgun_pct']})
    groups = [p for p,count in sorted(quotas.items()) for _ in range(count)]
    # DESIGN: interleave locations through the personnel blocks, keeping exact totals.
    locations = []
    used = Counter()
    for k in range(n):
        name = max(location, key=lambda v: (location[v]*(k+1)/n-used[v],v))
        locations.append(name); used[name]+=1
    pools = {'gun':[0,1,6,7,8], 'pistol':[5,10,12], 'uc':[3,4,9,11]}
    seen = Counter()
    result=[]
    for ordinal,(group,loc) in enumerate(zip(groups,locations)):
        pool=pools[loc]
        shape=pool[seen[loc] % len(pool)]
        if loc=='gun' and group=='11' and seen[loc] % 6 == 5:
            shape=2
        seen[loc]+=1
        result.append((group,loc,shape,ordinal%2))
    return result


def build(resource, team, profile, tendency):
    book=insp.parse_playbook_resource(resource); body=resource[32:]
    fs,ps=ordinary_indices(book,body)
    groups=role_groups(book,body)
    shapes=choose_shapes(len(fs),profile,tendency,groups)
    forms=[]; plays=[]; menus=[]; rows=[]
    targets=iter(sorted(ps)); counts=Counter()
    priorities = FAMILIES[profile['family']] + profile['emphasis']
    weights={k:1+priorities.count(k)*3 for k in RUN+PASS+['PA Boot']}
    weights['RB Slip'] += 3 if profile['feature_role']=='HB1' else 0
    weights['TE Seam'] += 3 if profile['feature_role']=='TE1' else 0
    weights['TE Drag'] += 3 if profile['feature_role']=='TE1' else 0
    for ordinal,(fi,(group,loc,shape,mirrored)) in enumerate(zip(sorted(fs),shapes)):
        name,_,_,skills=SHAPES[shape]; mirror=-1 if mirrored else 1
        qbz={'uc':-2,'pistol':-4,'gun':-5}[loc]
        skills=list(skills)
        # DESIGN: the auxiliary player stays off the line for 21, preserving eligible ends.
        if group=='21':
            spread=(12,16,20)[ordinal%3]
            name={'gun':'Gun','pistol':'Pistol','uc':'UC'}[loc]+' Pro '+('Tight','Base','Wide')[ordinal%3]
            skills=[(5,0),(-spread,0),(spread,-1.5),(3,-4.5),(-2.5,-5) if loc=='gun' else (0,-7)]
        # DESIGN: family spacing is a declared design parameter, not measured width.
        width=profile['width']
        canonical=[(0,round(qbz*YD)),(302,0),(-302,0),(0,0),(155,0),(-155,0)]
        canonical += [(round(x*YD*mirror*(width if abs(x)>=8 else 1)),round(z*YD)) for x,z in skills]
        ci,codes,order=groups[group]
        positions=tuple(canonical[s] for s in order)
        donors=[f for f in sorted(fs) if lib.formation_category(body,f)==ci]
        donor=(donors or sorted(fs))[0]
        fid=f'f{fi:02d}'
        label=f'{ordinal+1:02d} {name} {group}'+(' L' if mirrored else ' R')
        forms.append(packs.PackFormation(fid,label,positions,codes,packs.PackDonor(donor,book.formations[donor].name.strip()),fi,book.formations[fi].name.strip(),ci))
        count=len(ps)//len(fs)+(ordinal<len(ps)%len(fs))
        allowed=[k for k in weights if not (shape==2 and k in RUN) and not (k=='PA Boot' and loc!='uc')]
        concepts=[]
        # DESIGN: weighted fair distribution plus one native run per non-empty menu.
        if shape!=2:
            run=max(RUN,key=lambda k:(weights[k]/(counts[k]+1),-RUN.index(k)))
            concepts.append(run);counts[run]+=1
        while len(concepts)<count:
            concept=max((k for k in allowed if k not in concepts),key=lambda k:(weights[k]/(counts[k]+1),-list(weights).index(k)))
            concepts.append(concept);counts[concept]+=1
        ids=[]
        for slot,concept in enumerate(concepts):
            pi=next(targets);pid=f'p{pi:03d}';label=f'{ordinal+1:02d} '+('RB Screen' if concept=='RB Slip' else concept)
            variant=ordinal+profile['route_depth_step']*2
            kind,chains,primary=assignments(concept,canonical,CODES[group],variant)
            if kind=='pass' and concept not in ('RB Slip','TE Seam','TE Drag','Y Cross'):
                want={'TE1':6,'WR1':7,'WR2':8,'HB1':10}[profile['feature_role']]
                if any(op==0x12 for op,_ in chains[want]):
                    primary=want
                    other=[s-5 for s in range(6,11) if s!=want and any(op==0x12 for op,_ in chains[s])]
                    other += [v for v in range(1,6) if v!=want-5 and v not in other]
                    chains[0][-1]=(6,[0,want-5,*other[:3],0.0])
            chains=move_roles(chains,order)
            donor,flags=lib.reference_play_for(book,body,kind)
            plays.append(packs.PackPlay(pid,label,kind,tuple(tuple(ch) for ch in chains),
                packs.PackDonor(donor,book.plays[donor].name.strip(),book.plays[donor].flags_or_id,lib.qb_signature(lib.play_chains(body,donor)[1][0][1])),
                flags,pi,book.plays[pi].name.strip(),concept))
            ids.append(pid)
            rows.append(dict(status='DESIGN',team=team,play_index=pi,name=label,formation_index=fi,formation=forms[-1].custom_name,concept=concept,play_type=kind,personnel=group,location=loc,
                primary_slot=order.index(primary) if primary is not None else None,te1_slot=order.index(6),hb1_slot=order.index(10),menu_slot=slot))
        menus.append((fid,tuple(ids)))
    assert next(targets,None) is None
    notes=f"DESIGN: {profile['scheme']}; feature {profile['feature_role']} for {profile['key_players']}. 2025 personnel baseline plus disclosed design bias. No RPO/read option; all gameplay unwitnessed. See pb/research/team_profiles.json."
    pack=packs.PlaybookPack(packs.PackBook(team,f'NFL 2K28 {team} Modern','SOFTDRINK / Astra','0.2.0','CC0-1.0',notes=notes),
        packs.PackBase(packs.book_fingerprint(body),len(book.formations),len(book.plays),book.node_count),tuple(forms),tuple(plays),packs.OFFENSE_SCHEMA,tuple(menus))
    return pack,rows


def semantic_digest(pack):
    """PROVED OFFLINE: identity-free geometry/scripts/menu fingerprint."""
    by_play={p.id:p for p in pack.plays}
    semantic=[(pack.formations_by_id[f].slot_positions,pack.formations_by_id[f].position_codes,
               [(by_play[p].concept,by_play[p].assignments) for p in menu]) for f,menu in pack.menus]
    return hashlib.sha256(json.dumps(semantic,sort_keys=True).encode()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--image',type=Path,required=True)
    args=ap.parse_args(); profiles=json.loads(PROFILES.read_text())['teams']
    tendency={r['team']:r for r in json.loads((ROOT/'pb/research/tendencies_2025.json').read_text())['teams']}
    manifest=[]
    with OuterImage(args.image) as image:
        for team in packs.TEAM_BOOKS:
            path=ROOT/'data/playbooks'/('softdrink_giants_modern.2k5book' if team=='NYG' else f'softdrink_{team.lower()}_modern.2k5book')
            if team=='NYG':
                pack=packs.load_pack(path);rows=json.loads((ROOT/'pb/catalog.json').read_text())
            else:
                pack,rows=build(image.read_entry(BOOK_ENTRIES[team]),team,profiles[team],tendency[ALIASES.get(team,team)])
                check=packs.check_pack(pack)
                if not check.ok: raise ValueError(f'{team}: {check.text()}')
                packs.save_pack(pack,path)
            (ROOT/f'pb/catalogs/{team}.json').write_text(json.dumps(rows,indent=2)+'\n')
            manifest.append(dict(team=team,pack=str(path.relative_to(ROOT)),plays=len(rows),formations=len(pack.formations),semantic_sha256=semantic_digest(pack)))
            print(team,len(pack.formations),len(rows),flush=True)
    assert len({r['semantic_sha256'] for r in manifest})==32
    (ROOT/'pb/league_manifest.json').write_text(json.dumps(dict(status='PROVED OFFLINE',runtime_witness=False,teams=manifest),indent=2)+'\n')

if __name__=='__main__':main()
