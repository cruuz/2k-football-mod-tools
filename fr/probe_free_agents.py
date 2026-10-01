"""PROVED OFFLINE: bounded native initialization and CPU signing on G's bytes.

No xemu or disc build. Calls retail instructions plus existing economy/PS hooks,
without substituting roster membership, selection, contracts or transactions.
"""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_franchise_economy as economy, nfl2k5_practice_squad as squad
from mod_editor.core import nfl2k5_roster_records as rr
from tests.nfl2k5_supersim_draft_fixture import retail_bytes
from tools.franchise_economy.probe import start


def run(body):
    doc=rr.RosterDocument(body,reference_year=2026)
    expected={0x2000000+0x300+o:doc.by_offset[o].display for o in doc.free_agents}
    assert len(expected)==236
    payload=squad.apply(economy.apply(retail_bytes())[0])[0]
    m=start(body,payload)
    def pool():return [m.get(m.get(m.root+0x3C)+i*4) for i in range(m.get(m.root+0x38))]
    initial=pool()
    assert set(initial)==set(expected),('initialization changed FA pool',len(initial))
    m.put(0xE576A0,1);m.put(0xE576A4,3)
    cases=[]
    for pos in range(17):
        team=m.team_base+pos*500
        # DESIGN fixture: remove financial obstruction while keeping all G
        # identities, ratings and the real selection/transaction routines.
        for i in range(m.uc.mem_read(team+0x11C,1)[0]):
            m.uc.mem_write(m.get(team+i*4)+10,b'\0\0')
        m.call(0xC3F00,ecx=team);m.put(0xE3C278,economy.GAME_CAP)
        before=set(pool());count=m.uc.mem_read(team+0x11C,1)[0]
        result=m.call(0x322BB0,args=(team,pos,65535,0),budget=5000000)
        removed=before-set(pool())
        assert removed <= set(expected)
        assert len(removed)==result
        if result:
            p=m.get(team+count*4)
            assert removed=={p}
        cases.append(dict(position=pos,result=result,signed=[expected[p] for p in removed]))
    assert sum(c['result'] for c in cases)>0
    assert not m.leaves
    return dict(evidence='PROVED OFFLINE',body_sha256=hashlib.sha256(body).hexdigest(),
                initial_candidates=len(initial),initial_pool_all_modern=True,cases=cases,
                signed=sum(c['result'] for c in cases),old_players_signed=0,substituted_routines=[],
                limitation='Bounded native start and CPU fill. Full season rollover and UI still require lab captures.')

if __name__=='__main__':
    out=Path('/media/noah/Storage/.b76-research/fr')
    result=run((out/'g_body.bin').read_bytes())
    (out/'cpu_free_agents.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
