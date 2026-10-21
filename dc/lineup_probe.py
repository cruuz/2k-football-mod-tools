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

# ---------------------------------------------------------------------------------------------------------------
# b776-de1: the defensive formations (types 4, 5, 7).  Same native 0xe89f0, same synthetic healthy eligibility.
# The slot's intended role comes from the category code's kind (12 DE = EDGE pool, 13 DT = interior pool, 14 ILB and
# 15 OLB = the LB pool under position_pools, 16-18 = FS / SS / CB); the player's role is his roster position code
# read through the one-pool scheme (16 EDGE, 15 DT, 11 LB, 10 retired OLB).
DEFENSE_TYPES=(4,5,7)
KIND_ROLE={12:'EDGE',13:'DT',14:'LB',15:'LB',16:'FS',17:'SS',18:'CB'}
ENUM_ROLE={16:'EDGE',15:'DT',11:'LB',10:'LB',5:'FS',6:'SS',4:'CB'}
SLOT_NAME={12:'DE',13:'DT',14:'ILB',15:'OLB',16:'FS',17:'SS',18:'CB'}

def slot_rows(probe,raw,f,record,team_index):
    """One defensive formation through the native resolver: [{slot, code, intended, player, roster, role, ok}]"""
    m=probe.m;category=m.ARENA+0x160000
    group=lib.formation_category(raw[32:],f.index)
    codes=lib.category_positions(raw[32:],group)
    at=32+insp.CATEGORY_BASE+group*insp.CATEGORY_SIZE
    m.uc.mem_write(category,raw[at:at+insp.CATEGORY_SIZE])
    m.uc.mem_write(probe.assigned,bytes(44))
    m.call(0xe89f0,ecx=probe.context,edx=0,args=(category,0,probe.assigned),budget=1000000)
    rows=[]
    for slot,code in enumerate(codes):
        p=probe.info(m.get(probe.assigned+slot*4))
        assert p,(team_index,f.name,slot)
        enum=probe.doc.by_offset[m.get(probe.assigned+slot*4)-probe.base].record.get('position')
        kind=code&31
        intended=KIND_ROLE[kind]
        role=ENUM_ROLE.get(enum,'?')
        rows.append({'slot':slot,'code':f"{SLOT_NAME[kind]}{code>>5}",'intended':intended,'player':p['name'],
                     'enum':enum,'role':role,'rank':p['depth_rank'],'ok':role==intended})
    return {'type':record.type_code,'formation':f.name,'group':group,'slots':rows,
            'distinct':len({r['player'] for r in rows})==11,
            'bad':[f"{r['code']}:{r['player']}({r['role']})" for r in rows if not r['ok']]}

def defense_lineups(xbe,body,books,*,teams=None,types=DEFENSE_TYPES,clubs=32,team_index=None):
    """Native defensive lineups. books = {key: raw PLAY resource}. By default every club in the roster for the book
    named like it; ``team_index`` pins one roster team to every given book (a classic or moment one-team file)."""
    probe=Probe(xbe,body,clubs=clubs)
    clubs_by_abbr={t.abbreviation:t for t in probe.doc.teams[:clubs]}
    out=[]
    for key,raw in books.items():
        book=roles._parse(raw)
        t=probe.doc.teams[team_index] if team_index is not None else clubs_by_abbr.get(book.book_name)
        if t is None or (teams and t.abbreviation not in teams):continue
        probe.picks(t.index)
        for f in book.formations:
            record=lib.formation_record(raw[32:],f.index)
            if record.type_code not in types:continue
            row=slot_rows(probe,raw,f,record,t.index)
            row.update(team=t.abbreviation,book=book.book_name,book_key=key,book_sha256=sha(raw))
            out.append(row)
    return out

def format_table(rows):
    lines=[]
    for r in rows:
        mark='' if not r['bad'] else '   <-- '+', '.join(r['bad'])
        lines.append(f"{r['team']:<6} book {r['book_key']:<5} {r['formation']:<18} t{r['type']}{mark}")
        lines.append('   '+' | '.join(f"{s['code']}={s['player']}[{s['role']}]" for s in r['slots']))
    return '\n'.join(lines)

def drop_audit(raw,types=DEFENSE_TYPES):
    """Play level companion of the slot table: for every defensive formation of one PLAY resource, how often each
    EDGE / DT / LB slot rushes, drops into zone or covers a man across the effective (front, coverage) calls the game
    pairs (``lib.defense_pairs`` plus full plays). {formation: {(role, slot): {action: count}}}. Static, no emulation."""
    from collections import Counter
    book=insp.parse_playbook_resource(raw);body=raw[32:]
    names={12:'EDGE',13:'DT',14:'LB',15:'LB'}
    out={}
    for f in book.formations:
        rec=lib.formation_record(body,f.index)
        if rec.type_code not in types:continue
        codes=lib.category_positions(body,lib.formation_category(body,f.index))
        entries={p.index:lib.decoded_chains(body,p.index) for p in book.plays_for_formation(f.index) if p.family_id==1}
        calls=[lib.effective_defense(entries.get(a) or lib.decoded_chains(body,a),entries.get(b) or lib.decoded_chains(body,b))
               for a,b in lib.defense_pairs(book,body,f.index)]
        calls+=[c for c in entries.values() if lib.defense_component(c)=='full']
        stat=Counter()
        for chains in calls:
            for slot,chain in enumerate(chains):
                role=names.get(codes[slot]&31)
                if not role:continue
                op=next((n[0] for n in chain if n[0] in (0x0B,0x0D,0x0E)),None)
                stat[(role,slot,{0x0B:'rush',0x0D:'zone',0x0E:'man',None:'none'}[op])]+=1
        table={}
        for (role,slot,action),n in stat.items():table.setdefault((role,slot),{})[action]=n
        out[f.name]=dict(calls=len(calls),slots=table)
    return out

if __name__=='__main__':run()
