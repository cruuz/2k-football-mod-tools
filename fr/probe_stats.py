"""PROVED OFFLINE: native season lookup and career sums after MyNFL init."""
import collections
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr, nfl2k5_career_stats as cs
from mod_editor.core import nfl2k5_franchise_economy as econ
from tests.nfl2k5_supersim_draft_fixture import retail_bytes
from tools.franchise_economy.probe import start,finances
from tools.franchise_economy.contracts import charges,FIELDS
from fr.generate import MAP,FG_ATTEMPTS


def run(body,spec):
    doc=rr.RosterDocument(body,reference_year=2026)
    by={(p.pool,p.index):p for p in doc.players}
    m=start(body,econ.apply(retail_bytes())[0])
    financial=finances(m)
    for row in financial:
        expected=sum(charges({k:p.record.values[k] for k in FIELDS})[0]*4000
                     for p in doc.players if row['team'] in p.teams)
        assert row['payroll_real_dollars']==expected,(row['name'],row['payroll_real_dollars'],expected)
        assert row['cap_game_thousands']*4000==301200000 and row['cap_pass']
    cells=0;rows=0;examples=[]
    for ident in spec['players']:
        p=by[ident['pool'],ident['index']];address=m.ARENA+0x300+p.offset
        school=m.get(m.get(address))
        label=bytes(m.uc.mem_read(school,256)).decode('utf-16-le').split('\0')[0]
        assert label==p.college,(p.display,label,p.college)
        totals=collections.Counter()
        for s in ident['seasons']:
            totals.update(s['stats'])
            slot=p.record.values['years_pro']-(2026-s['year'])
            ptr=m.call(0x14EE20,ecx=address,edx=0,args=(slot,))
            assert ptr and (m.get(ptr)&65535)==s['stats']['games'],(p.display,s['year'],'games slot')
            ptr=m.call(0x14EE20,ecx=address,edx=87,args=(slot,))
            assert ptr and (m.get(ptr)&65535)==s['team_index']+1,(p.display,s['year'],'TEAM')
            rows+=1
        for name in list(MAP)+list(FG_ATTEMPTS):
            field=cs.BY_NAME[name]
            got=m.call(0x14EE60,ecx=address,edx=field.id)
            if got>=2**31:got-=2**32
            assert got==totals[name]*field.units,(p.display,name,got,totals[name])
            cells+=1
        count=p.record.values['years_pro']
        assert m.call(0x14EE20,ecx=address,edx=0,args=(count,))==0,(p.display,'dirty current season')
        if p.display in ('Josh Allen','Patrick Mahomes','Brock Purdy','Aaron Rodgers','Saquon Barkley','Derrick Henry','Justin Jefferson'):
            examples.append(dict(name=p.display,index=p.index,career=dict(totals),last=next((s for s in ident['seasons'] if s['year']==2025),None)))
    return dict(evidence='PROVED OFFLINE',body_sha256=hashlib.sha256(body).hexdigest(),players=len(spec['players']),
                native_career_cells=cells,native_games_and_team_rows=rows,native_college_labels=len(spec['players']),native_finances=financial,current_slots_clean=len(spec['players']),
                examples=examples,substituted_routines=m.leaves,
                limitation='Native getters after bounded initialization, without rendering a MyNFL screen or simulating rollover.')

if __name__=='__main__':
    out=Path('/media/noah/Storage/.b76-research/fr')
    spec=json.loads((out/'league_roster_edits_candG_fr.json').read_text())['franchise_history']
    report=run((out/'g_body.bin').read_bytes(),spec)
    (out/'native_stats.json').write_text(json.dumps(report,indent=2)+'\n')
    print({k:v for k,v in report.items() if k not in ('examples','native_finances')})
