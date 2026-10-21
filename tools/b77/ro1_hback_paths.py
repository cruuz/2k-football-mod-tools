"""Native auto-depth, ownership and contract checks on an integrated fresh save.

Requires the private XBE, ROST and fresh MyCareer save produced by the probe.
No disc copy, graphics, prepared league outcomes or substitute roster routines.
"""
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.b77.ro1_native_fixture import Machine
from mod_editor.core import nfl2k5_hback as hb


def probe(xbe,body,save,plan,output):
    payload=Path(xbe).read_bytes();roles=json.loads(Path(plan).read_text())
    if hb.status(payload)!='applied':raise ValueError('Installed H-back image required')
    result=dict(complete=False,graphics_witnessed=False,teams=[],transactions=[])
    with Machine(payload) as m:
        m.cold(Path(body).read_bytes(),Path(save).read_bytes())
        root=m.get(0xB72918);pool=m.get(root+4)
        def members(team):return [m.get(team+i*4) for i in range(m.uc.mem_read(team+0x11c,1)[0])]
        def free():return [m.get(m.get(root+0x3c)+i*4) for i in range(m.get(root+0x38))]
        def position(p):return m.uc.mem_read(p+53,1)[0]
        m.put(0xE60140,1);m.call(0x2BDCF0,budget=100000000)
        for i,name in enumerate(hb.TEAMS):
            team=m.get(0xE5786C+4*i);active=members(team)
            m.put(0xC1749C,team);m.put(0xC174B8,0)
            view=m.call(0x243AE0,ecx=2)
            abbreviation=bytes(m.uc.mem_read(view,10)).decode('utf-16le').split('\0')[0]
            role=next(r['role'] for r in roles['teams'] if r['team']==name)
            assert abbreviation==('H-B' if role=='H-B' else 'FB'),(name,abbreviation)
            assert len(active)==len(set(active)),name
            views={}
            for pos in (8,9):
                views[pos]=[m.call(0x242AE0,edx=team,args=(rank,pos,0)) for rank in range(8)]
                views[pos]=[p for p in views[pos] if p]
                assert len(views[pos])==len(set(views[pos])),(name,pos)
                assert all(p in active and position(p)==pos for p in views[pos]),(name,pos)
            assert not set(views[8])&set(views[9]),name
            result['teams'].append(dict(team=name,depth_abbreviation=abbreviation,fb_ids=[(p-pool)//84 for p in views[8]],te_ids=[(p-pool)//84 for p in views[9]]))
        print('AUTO_DEPTH 32 teams: native FB and TE rows have unique identities and correct positions',flush=True)
        print('NATIVE_TEAM_LABELS',','.join(t['team'] for t in result['teams']
            if t['depth_abbreviation']=='H-B'),'H-B; other native teams FB',flush=True)
        for role in roles['teams']:
            if role['role']!='H-B':continue
            team=m.get(0xE5786C+4*hb.TEAMS.index(role['team']));p=pool+84*role['player_index']
            assert p in members(team) and position(p)==8
            before=members(team)
            assert m.call(0xC3EB0,ecx=team,edx=p)==1
            assert m.call(0x242560,ecx=root+0x38,edx=p)==1
            assert free().count(p)==1 and p not in members(team)
            assert m.call(0x2425C0,ecx=root+0x38,edx=p)==1
            m.call(0x325B50,ecx=p,edx=team,args=(0,))
            assert members(team).count(p)==1 and p not in free() and position(p)==8
            assert set(before)==set(members(team))
            # Exercise the native accepted-contract path as a re-sign offer.
            offer=m.OUT+0x100;status=m.OUT+0x200
            m.put(offer,p);m.put(offer+4,team)
            m.put(offer+8,(1<<26)|(1<<16));m.put(offer+12,10)
            accepted=m.call(0x323D80,ecx=offer,edx=status,args=(1,m.manager),budget=10000000)
            assert accepted==1,(role['team'],m.get(status))
            assert members(team).count(p)==1 and p not in free() and position(p)==8
            result['transactions'].append(dict(team=role['team'],player=role['player'],release=True,one_fa_reference=True,native_signing=True,resign=True))
            print('TRANSACTION',role['team'],role['player'],'release, one FA reference, signing, re-sign passed',flush=True)
        # Two accepted one-year offers above give a balanced native trade input.
        # Offseason capacity permits the native sequential transfer's spare slot.
        first,second=(next(r for r in roles['teams'] if r['team']==t) for t in ('CIN','HOU'))
        a,b=(m.get(0xE5786C+4*hb.TEAMS.index(r['team'])) for r in (first,second))
        p,q=(pool+84*r['player_index'] for r in (first,second))
        trade=m.OUT+0x400;m.uc.mem_write(trade,bytes(60))
        m.put(trade+8,a);m.put(trade+12,p);m.put(trade+32,b);m.put(trade+36,q)
        m.put(0xE576A4,1)
        accepted=m.call(0x2BC670,ecx=trade,edx=0,args=(0,),budget=10000000)
        assert accepted==1,('trade refused',m.events[-3:])
        assert members(a).count(q)==1 and p not in members(a)
        assert members(b).count(p)==1 and q not in members(b)
        assert p not in free() and q not in free() and position(p)==position(q)==8
        result['native_trade']=dict(from_team='CIN',to_team='HOU',unique_owners=True,position=8)
        print('TRADE native CIN/HOU exchange: one owner per identity, enum 8 preserved',flush=True)
        result['complete']=True
    Path(output).write_text(json.dumps(result,indent=2)+'\n',newline='\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('xbe','body','save','plan','output'):ap.add_argument('--'+name,required=True,type=Path)
    a=ap.parse_args();probe(a.xbe,a.body,a.save,a.plan,a.output)
