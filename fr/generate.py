"""DESIGN: reproduce G from F and the dated CC-BY nflverse source cache."""
import argparse
import collections
import copy
import datetime as dt
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_franchise_history as fh
from mod_editor.core import nfl2k5_team_history as th
from tests.nfl2k5_supersim_draft_fixture import retail_roster

F = Path('/media/noah/Storage/.b76-research/main/freeze/candF/league_roster_edits_candE_dc.json')
FA = Path('/media/noah/Storage/.b76-research/fa')
OUT = Path('/media/noah/Storage/.b76-research/fr')
MAP = {'games':['games'],'rushing_attempts':['carries'],'rushing_yards':['rushing_yards'],'rushing_touchdowns':['rushing_tds'],
 'passing_attempts':['attempts'],'passing_completions':['completions'],'passing_yards':['passing_yards'],
 'passing_touchdowns':['passing_tds'],'passing_interceptions':['passing_interceptions'],'receptions':['receptions'],
 'receiving_yards':['receiving_yards'],'receiving_touchdowns':['receiving_tds'],'defensive_sacks':['def_sacks'],
 'defensive_interceptions':['def_interceptions'],'forced_fumbles':['def_fumbles_forced'],'interception_return_yards':['def_interception_yards'],
 'defensive_tackles':['def_tackles_solo','def_tackles_with_assist','def_tackle_assists'],
 'extra_points_made':['pat_made'],'extra_points_attempted':['pat_att'],'punts':['pt_att'],'punting_yards':['pt_yards'],
 'punts_inside_20':['pt_inside_20'],'punt_touchbacks':['pt_touchback'],
 'field_goals_made_1_29':['fg_made_0_19','fg_made_20_29'],'field_goals_made_30_39':['fg_made_30_39'],
 'field_goals_made_40_49':['fg_made_40_49'],'field_goals_made_50_plus':['fg_made_50_59','fg_made_60_']}

FG_ATTEMPTS = ('field_goals_attempted_1_29','field_goals_attempted_30_39',
               'field_goals_attempted_40_49','field_goals_attempted_50_plus')


def attempts_by_distance(row):
    """nflfastR stat IDs 69/70/71: misses, makes, blocks are disjoint attempts."""
    buckets=dict.fromkeys(FG_ATTEMPTS,0)
    total=0
    for kind in ('made','missed','blocked'):
        distances=[int(v) for v in row['fg_'+kind+'_list'].split(';') if v]
        assert len(distances)==int(row['fg_'+kind]),(row['player_id'],kind)
        for distance in distances:
            assert 0 <= distance <= 99
            at=0 if distance<30 else 1 if distance<40 else 2 if distance<50 else 3
            buckets[FG_ATTEMPTS[at]]+=1
            total+=1
    assert total==int(row['fg_att'])
    return buckets

def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def readcsv(p):
    with Path(p).open() as f:return list(csv.DictReader(f))

def dump(p,obj):
    Path(p).write_text(json.dumps(obj,indent=2,ensure_ascii=True)+'\n')

def sources(fa):
    manifest=json.loads((fa/'source_manifest.json').read_text())
    for a in manifest['assets']:
        assert digest(fa/a['file'])==a['sha256'],a['file']
    return {Path(a['file']).name:a for a in manifest['assets']}

def team_code(code):
    return th.TEAM_ALIASES.get(code, {'LA':'STL'}.get(code,code))


def histories(doc,ids,fa,pins):
    current=collections.defaultdict(list)
    for r in readcsv(fa/'data/roster_2026.csv'):current[r['gsis_id']].append(r)
    annual=collections.defaultdict(list)
    for path in sorted((fa/'data').glob('roster_*.csv')):
        for r in readcsv(path):annual[r['gsis_id'],int(r['season'])].append(r)
    stats=collections.defaultdict(list)
    wanted={i['gsis'] for i in ids}
    for path in sorted((fa/'data').glob('stats_player_reg_*.csv')):
        year=int(path.stem[-4:])
        if year>=2026:continue
        for r in readcsv(path):
            if r['player_id'] not in wanted:continue
            values={k:sum(float(r[c]) for c in cols) for k,cols in MAP.items()
                    if all(r.get(c) not in ('',None,'NA','NaN') for c in cols)}
            if values.get('games',0)<=0:continue
            values.update(attempts_by_distance(r))
            annual_rows=annual[r['player_id'],year]
            assert annual_rows,(r['player_id'],year)
            week=max(int(float(a['week'] or 0)) for a in annual_rows)
            choices={team_code(a['team']) for a in annual_rows if int(float(a['week'] or 0))==week}
            recent=team_code(r['recent_team'])
            selected=next(iter(choices)) if len(choices)==1 else recent
            assert selected in choices,(r['player_id'],year,choices,recent)
            stats[r['player_id']].append(dict(year=year,source=path.name,stats=values,
                team_index=th.RETAIL_TEAM_INDEX[selected],team_source=f'roster_{year}.csv',
                team_selection=dict(week=week,candidates=sorted(choices),selected=selected,
                                    tie_break='stats recent_team' if len(choices)>1 else None)))
    identity_cache={}
    players=[]
    by={(p.pool,p.index):p for p in doc.players}
    for ident in ids:
        p=by[ident.get('pool','primary'),int(ident['index'])]
        assert p.display==ident['name']
        identity_source=ident.get('identity_source','roster_2026.csv')
        if identity_source not in identity_cache:identity_cache[identity_source]=readcsv(fa/'data'/identity_source)
        candidates=[r for r in identity_cache[identity_source] if r['gsis_id']==ident['gsis']
                    and r['birth_date']==p.record.birth_date.isoformat()]
        assert candidates,(p.display,ident['gsis'])
        players.append(dict(pool=p.pool,index=p.index,first=p.first,last=p.last,
            birth_date=p.record.birth_date.isoformat(),gsis_id=ident['gsis'],identity_source=identity_source,
            seasons=stats[ident['gsis']]))
    return dict(schema=fh.SCHEMA,base_year=2026,attribution='nflverse contributors, CC-BY-4.0',
                team_policy='Latest week in annual GSIS roster; tied clubs use stats recent_team only if present in annual candidates. No donor inference.',
                tackle_policy='DESIGN: combined tackle participation = solo + primary assisted tackle + tackle assist; source categories disjoint. Native gameplay assist-credit equivalence is unverified.',
                fg_attempt_policy='Made, missed and blocked distance lists; counts validated against each component and fg_att.',
                comparison='Completed regular seasons through 2025; source games, not credited seasons; missing source is unverified.',
                sources=pins,players=players)

POSITION = {p:i for i,p in enumerate(rr.POSITIONS)}
POSITION.update(RB=7,MLB=11,LB=11,NT=15,DB=4,LS=12)


def free_agents(result,doc,ids,fa,out):
    used={i['gsis'] for i in ids}
    annual=readcsv(fa/'data/roster_2026.csv')
    # Reserve/development players are documented, not falsely made unsigned.
    reserves=[r for r in annual if r['gsis_id'] not in used and r['status'] in ('RES','DEV','EXE')]
    dump(out/'reserve_snapshot.json',dict(source='roster_2026.csv',policy='excluded from unsigned FA pool',rows=reserves))
    older={}
    for path in sorted((fa/'data').glob('roster_*.csv')):
        if path.name=='roster_2026.csv':continue
        for r in readcsv(path):
            for field in ('birth_date','height','college'):
                if r.get(field):older[r['gsis_id'],field]=(r[field],path.name)
    for r in annual:
        r['bio_sources']={}
        for field in ('birth_date','height','college'):
            if not r.get(field) and (r['gsis_id'],field) in older:
                r[field],r['bio_sources'][field]=older[r['gsis_id'],field]
    candidates=[r for r in annual if r['gsis_id'] and r['gsis_id'] not in used and r['status']=='CUT'
                and all(r.get(k) for k in ('birth_date','height','weight','years_exp','first_name','last_name'))]
    assert len({r['gsis_id'] for r in candidates})==len(candidates)
    # Match donor positions first to retain a reasonable gameplay template.
    # Ratings/equipment are DESIGN templates, not nflverse ratings/appearance.
    donors=sorted((p for p in doc.players if p.group=='free_agent'),key=lambda p:p.index)
    ledger=[]
    for p in donors:
        available=[r for r in candidates if r['gsis_id'] not in used]
        def rank(r):
            return (POSITION[r['depth_chart_position']] != p.record.values['position'],
                    -int(float(r['years_exp'])),r['gsis_id'])
        r=min(available,key=rank);used.add(r['gsis_id'])
        born=dt.date.fromisoformat(r['birth_date']);yy=born.year%100
        first=r['football_name'] or r['first_name'];last=r['last_name']
        fields=dict(birth_month=born.month,birth_day=born.day,birth_year_low=yy&7,birth_year_high=yy>>3,
            height=int(float(r['height'])),weight_raw=int(float(r['weight']))-150,years_pro=int(float(r['years_exp'])),
            position=POSITION[r['depth_chart_position']],jersey=int(float(r['jersey_number'] or 0)),
            contract_value=0,contract_remaining=0,contract_length=0,contract_bonus=0,contract_type=2,
            injured_reserve=0,photo_id=0,pbp_id=0,star_tag=0)
        result['edits'].append(dict(pool=p.pool,index=p.index,first=p.first,last=p.last,
                                   fields=fields,names=dict(first=first,last=last)))
        ids.append(dict(pool=p.pool,index=p.index,name=first+' '+last,gsis=r['gsis_id'],
                        identity_source=r['bio_sources'].get('birth_date','roster_2026.csv')))
        ledger.append(dict(pool=p.pool,index=p.index,first=first,last=last,gsis_id=r['gsis_id'],
                           donor=p.display,bio_sources=r['bio_sources'],source_status=r['status'],source_team=r['team'],source='roster_2026.csv'))
    result['free_agent_pool']=[{k:r[k] for k in ('pool','index','first','last')} for r in ledger]
    result['fr_free_agents']=dict(date='2026-09-29',source='roster_2026.csv',selected=len(ledger),
        policy='CUT only, exclude all existing 53-man identities; prefer matching positions then experience then GSIS ID; unsigned contracts zero.',
        reserve_policy='RES/DEV/EXE are dated in reserve_snapshot.json and excluded from unsigned membership.',
        retired_fa_aliases=[dict(pool=doc.by_offset[o].pool,index=doc.by_offset[o].index,name=doc.by_offset[o].display)
                           for o in doc.free_agents if doc.by_offset[o].group!='free_agent'])
    dump(out/'free_agents.json',ledger)
    return ids

def generate(f=F,fa=FA,out=OUT,*,college_reference_image=None):
    out.mkdir(exist_ok=True,parents=True)
    assert digest(f)=='35d855af3921c42f93e4c525a2868a2294fbd6e5cc717eaf9f6b141a43ea8e2c'
    pins=sources(fa)
    pins["nflverse_calculate_stats.R"]=json.loads((ROOT/"fr/stat_semantics_source.json").read_text())
    source=json.loads(f.read_text());result=copy.deepcopy(source)
    body,receipt=rr.apply_body(retail_roster(),source)
    assert not receipt['log'],receipt['log']
    doc=rr.RosterDocument(body,reference_year=2026)
    ids=readcsv(ROOT/'fr/identities.csv')
    ids=free_agents(result,doc,ids,fa,out)
    body,receipt=rr.apply_body(retail_roster(),result)
    assert not receipt['log'],receipt['log']
    doc=rr.RosterDocument(body,reference_year=2026)
    result['franchise_history']=histories(doc,ids,fa,pins)
    from fr.colleges import update as update_colleges
    if college_reference_image is None:
        raise ValueError('supply --college-reference-image for the shared college census')
    from mod_editor.core.nfl2k5_college_refs import external_references
    with rr._outer_image()(college_reference_image) as archive:
        protected = external_references(archive, doc.colleges)
    update_colleges(result,doc,fa,out,protected_slots=protected)
    from fr.contracts import update as update_contracts
    update_contracts(result,doc,fa,out,pins)
    output,receipt=rr.apply_body(retail_roster(),result)
    assert not receipt['log'],receipt['log']
    dump(out/'league_roster_edits_candG_fr.json',result)
    dump(out/'replay.json',receipt)
    (out/'g_body.bin').write_bytes(output)
    print(json.dumps(receipt['franchise_history']))
    return result,output

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--fa',type=Path,default=FA);ap.add_argument('--out',type=Path,default=OUT)
    ap.add_argument('--college-reference-image',type=Path,required=True)
    a=ap.parse_args();generate(fa=a.fa,out=a.out,college_reference_image=a.college_reference_image)
