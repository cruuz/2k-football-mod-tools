"""PROVED OFFLINE: execute the complete native eleven-slot lineup resolver.

Synthetic healthy eligibility, no saved formation substitutions, empty lineup.
The real 0xe89f0 establishes slot order and invokes the real duplicate checks.
Source books are normalized by C's existing depth-role pass; the full-build
finisher supplies actual final books instead. No game routine is substituted.
"""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dc.native_probe import Probe,minimal_xbe,OUT,sha
from dc.import_depth import ALIASES
from mod_editor.core import nfl2k5_depth_roles as roles,nfl2k5_playbook_inspector as insp,nfl2k5_play_library as lib
RETAIL=Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')

def run(xbe=None,body=None,books=None,output=ROOT/'dc/proof/lineups.json'):
    xbe=minimal_xbe() if xbe is None else xbe
    body=(OUT/'candidate_C_dc.rost').read_bytes() if body is None else body
    source='final_disc_books' if books is not None else 'retail_books_with_existing_depth_role_normalizer'
    if books is None:books={k:roles.normalise(raw).replacement for k,raw in roles._resources(RETAIL).items()}
    probe=Probe(xbe,body);m=probe.m
    teams={t.abbreviation:t for t in probe.doc.teams[:32]}
    category=m.ARENA+0x160000
    forms=[]
    for key,raw in books.items():
        book=roles._parse(raw)
        team=teams.get(book.book_name)
        if team is None:continue
        selected=probe.picks(team.index)
        for f in book.formations:
            record=lib.formation_record(raw[32:],f.index)
            if record.type_code not in (8,9,10,11,12,13):continue
            group=lib.formation_category(raw[32:],f.index)
            codes=lib.category_positions(raw[32:],group)
            at=32+insp.CATEGORY_BASE+group*insp.CATEGORY_SIZE
            m.uc.mem_write(category,raw[at:at+insp.CATEGORY_SIZE])
            m.uc.mem_write(probe.assigned,bytes(44))
            m.call(0xe89f0,ecx=probe.context,edx=0,args=(category,0,probe.assigned),budget=1000000)
            players=[probe.info(m.get(probe.assigned+slot*4)) for slot in range(11)]
            assert all(players)
            assert len({p['index'] for p in players})==11,(team.abbreviation,f.name)
            specialists=[]
            for slot,code in enumerate(codes):
                kind,ordinal=code&31,code>>5
                role={1:'P',2:'K',3:'H'}.get(kind)
                if kind==4:role='PR' if ordinal&1 else 'KR1' if ordinal==0 else 'KR2'
                if kind==6 and ordinal==1 and record.type_code in (10,12):role='LS'
                if role:
                    expected=selected[role]
                    same=players[slot]['index']==expected['index']
                    used=expected['index'] in {p['index'] for p in players[:slot]}
                    assert same or used or (team.abbreviation=='NO' and role=='LS'),(team.abbreviation,f.name,role,players[slot],expected)
                    # Ordinary KR/KR2 and punt return slots precede blockers.
                    # Onside uses KR and PR together: a shared identity must
                    # be deduplicated to the next native return-list entry.
                    if (record.type_code==11 and slot==0) or (record.type_code==9 and codes[:2]==[4,68] and slot<2):
                        assert same,(team.abbreviation,f.name,role)
                    specialists.append({'slot':slot,'role':role,'player':players[slot], 'matches_isolated_pick':same,
                                        'selection_reason':'designated' if same else 'designated_player_already_used' if used else 'short_list_fallback'})
            forms.append({'team':ALIASES.get(team.abbreviation,team.abbreviation),'book':book.book_name,'book_sha256':sha(raw),
                          'formation':f.name,'type':record.type_code,'group':group,'codes':codes,'specialists':specialists,
                          'lineup':[p['name'] for p in players]})
    assert len({f['team'] for f in forms})==32
    result={'evidence':'PROVED OFFLINE','source':source,'boundary':__doc__,'substituted_routines':[],
            'xbe_sha256':sha(xbe),'roster_sha256':sha(body),'formations':forms,
            'formation_count':len(forms),'team_count':32}
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(f'PROVED OFFLINE: {len(forms)} full native special-teams lineups across 32 clubs',flush=True)
    return result
if __name__=='__main__':run()
