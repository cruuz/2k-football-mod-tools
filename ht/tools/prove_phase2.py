#!/usr/bin/env python3
"""PROVED OFFLINE: authored compact roster import, export and personnel selection."""
import json
import hashlib
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from mod_editor.core import nfl2k5_historic_rosters as h
from mod_editor.core import nfl2k5_historic_teams_quick_game as h1
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_roster_records as rr
from nfl2k5_historic_quick_game_native import TeamSelectCPU,disc_evidence

RETAIL=Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')


def run():
    data=h.require_build_ready()
    resources,context,ids=disc_evidence(RETAIL)
    payload,_=e.apply_xbe((RETAIL/'default.xbe').read_bytes())
    payload,_=h1.apply(payload)
    payload=h1.enable_season_routing(payload)
    context=dict(context,descriptors=list(context['descriptors']))
    bank=[]
    for i,t in enumerate(data['teams']):
        outer=9000+i
        resources[outer]=h.compile_team(resources[t['outer']],t)
        context['descriptors'].append(dict(filename=t['alias'],outer=outer))
        bank.append(dict(team=t['name'],file=t['alias'],bytes=len(resources[outer]),sha256=e.sha(resources[outer])))
    manifest_sha=hashlib.sha256((h.DATA_DIR/'manifest.json').read_bytes()).hexdigest()
    writer_sha=hashlib.sha256(Path(h.__file__).read_bytes()).hexdigest()
    (ROOT/'ht/evidence/phase2_bank.json').write_text(json.dumps(dict(label='PROVED OFFLINE',
        manifest_sha256=manifest_sha,writer_sha256=writer_sha,aliases=75,entry_cost=76,directory_bytes=912,
        projected_e2_entries=4527,alias_bytes=sum(b['bytes'] for b in bank),
        aligned_alias_bytes=2048+sum((b['bytes']+2047)//2048*2048 for b in bank),
        additional_xbe_allocations=0,code_used=len(h1.assembly.CODE)+len('HTS-h-%s-%d-%s-%d.iff\0'.encode('utf-16le')),
        code_allocation=h1.CODE_SIZE,files=bank),indent=2)+'\n')
    result=[]
    offense=[('QB',0),('HB',0),('FB',0),('WR',0),('WR',1),('TE',0),('T',0),('G',0),('C',0),('G',1),('T',1)]
    defense=[('DE',0),('DT',0),('DT',1),('DE',1),('OLB',0),('ILB',0),('OLB',1),('CB',0),('CB',1),('FS',0),('SS',0)]
    for flow in h1.LOCAL_FLOWS:
        cpu=TeamSelectCPU(payload,resources,context,ids)
        cpu.team_select(cpu.last_resident(),cpu.team(15),flow=flow)
        for t in data['teams']:
            selected=cpu.press('home',1)
            assert selected['loaded']==[t['alias']],selected
            assert selected['home']['players']==len(t['players'])
            assert cpu.pool()['used']==len(t['players'])
            team=cpu.r(0xACF63C)
            observed=[cpu.person(cpu.r(team+4*i)) for i in range(len(t['players']))]
            assert [(p['first'],p['last'],p['jersey']) for p in observed]==[(p['first'],p['last'],p['jersey']) for p in t['players']]
            match=cpu.match()
            assert match['export_players']==len(t['players'])+53,match
            picked=[]
            for formation in (offense,defense):
                assigned=[]
                for pos,ordinal in formation:
                    p=cpu.field_player('home',pos,ordinal,assigned)
                    assert p and p['pointer'] not in assigned,(t['name'],pos,ordinal,p)
                    assigned.append(p['pointer'])
                picked.append(len(assigned))
            result.append(dict(flow=flow,team=t['name'],players=len(t['players']),
                export_players=match['export_players'],distinct_personnel=picked,alias=t['alias']))
            print(f"PROVED OFFLINE: flow {flow} {t['name']} {len(t['players'])}",flush=True)
    # Compact authoring can also exceed retail's 53 slots. Exercise both dynamic
    # sides simultaneously at the actual dataset maximum, including export.
    largest=max(data['teams'],key=lambda t:len(t['players']))
    pairs=[]
    for flow in h1.LOCAL_FLOWS:
        cpu=TeamSelectCPU(payload,resources,context,ids)
        cpu.team_select(cpu.team(0),cpu.team(15),flow=flow)
        for _ in range(75-largest['descriptor']):
            home=cpu.press('home',-1)
        cpu.team_select(cpu.r(0xACF63C),cpu.team(0),flow=flow)
        for _ in range(75-largest['descriptor']):
            away=cpu.press('away',-1)
        assert home['loaded']==away['loaded']==[largest['alias']]
        expected=2*len(largest['players'])
        assert cpu.pool()['used']==expected
        match=cpu.match();assert match['export_players']==expected
        pairs.append(dict(flow=flow,team=largest['name'],players_per_side=len(largest['players']),
                          pool_used=cpu.pool()['used'],export_players=match['export_players']))
    return dict(label='PROVED OFFLINE',manifest_sha256=manifest_sha,writer_sha256=writer_sha,loads=result,
                maximum_pairs=pairs,boundaries=TeamSelectCPU.__doc__,
                limitation='Native importer/exporter/personnel only. No xemu or rendered gameplay.')


if __name__=='__main__':
    result=run()
    (ROOT/'ht/evidence/phase2_native.json').write_text(json.dumps(result,indent=2)+'\n')
