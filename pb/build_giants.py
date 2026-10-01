#!/usr/bin/env python3
"""DESIGN: deterministic modern Giants offense, no game execution or image write.

PROVED OFFLINE: recipe uses stock personnel and supported PLAY grammar. See
CONCEPTS.md for the difference between encodable assignments and football AI.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_play_codec as c
from mod_editor.core import nfl2k5_play_library as l
from mod_editor.core import nfl2k5_playbook_inspector as i
from mod_editor.core import nfl2k5_playbook_pack as p
from mod_editor.core.nfl2k5_complete_offense import ordinary_indices
from nfl2k5_playbook_pack import _resource_from_image

YD = l.YD

# DESIGN: all slots below use the stock Kings/Ace/Pro role order. TE1 is slot 6.
# PROVED OFFLINE: two eligible LOS ends; covered tight ends are avoided.
SHAPES = [
    ('Gun Trips', 4, -5, [(-5,0), (8,-1.5), (12,-1.5), (18,0), (-2.5,-5)]),
    ('Gun Bunch', 4, -5, [(-5,0), (6,-1.5), (8,0), (10,-1.5), (-2.5,-5)]),
    ('Gun Empty', 4, -5, [(6,-1.5), (-18,0), (-9,-1.5), (18,0), (12,-1.5)]),
    ('Singleback Ace', 2, -2, [(-5,0), (-16,-1.5), (16,-1.5), (5,0), (0,-7)]),
    ('Ace Wing', 2, -2, [(5,0), (-16,0), (16,-1.5), (6.5,-1.5), (0,-7)]),
    ('Pistol Ace', 2, -4, [(-5,0), (-16,-1.5), (16,-1.5), (5,0), (0,-7)]),
    ('Gun Doubles', 4, -5, [(7,-1.5), (-18,0), (-9,-1.5), (18,0), (-2.5,-5)]),
    ('Gun Y Trips', 2, -5, [(7,-1.5), (-18,0), (18,0), (11,-1.5), (-2.5,-5)]),
    ('Gun Wing', 2, -5, [(-5,0), (-16,-1.5), (16,0), (6,-1.5), (2.5,-5)]),
    ('Ace Bunch', 2, -2, [(-5,0), (10,-1.5), (8,0), (6,-1.5), (0,-7)]),
    ('Pistol Wing', 2, -4, [(5,0), (-16,0), (16,-1.5), (6.5,-1.5), (0,-7)]),
    ('UC Tight', 2, -2, [(-5,0), (-8,-1.5), (8,-1.5), (5,0), (0,-7)]),
    ('Pistol Strong', 3, -4, [(5,0), (-16,0), (16,-1.5), (3,-4.5), (0,-7)]),
]

PASS = ['Mesh', 'Stick', 'Levels', 'Y Cross', 'Dagger', 'Flood', 'Drive', 'TE Seam', 'TE Drag', 'RB Slip']
RUN = ['Inside Zone', 'Outside Zone', 'Counter', 'Downhill', 'End Around']


def route(*segments):
    return [l.start(3), *(l.seg(kind, distance) for kind, distance in segments)]


def assignments(concept, positions, codes, variant):
    """DESIGN: formation-aware combinations with TE1 progressions."""
    kind = [v & 31 for v in codes]
    gun = positions[0][1] <= c.SHOTGUN_DEPTH_THRESHOLD_CM
    wr = sorted((s for s in range(6,11) if kind[s] == l.WR), key=lambda s: positions[s][0])
    te, hb = 6, 10
    side = 1 if variant % 2 == 0 else -1
    out = [l.qb_pass_chain(gun)] + [l.center_chain(0,'pass',False) if s == 3 else l.blocker_chain('pass',0,False) for s in range(1,6)]
    out += [route((0,20)) for _ in range(5)]
    out[hb] = route((5,5))
    if kind[9] == l.FB:
        out[9] = l.blocker_chain('pass',0,False)
    primary = te
    depth = 10 + 2*(variant % 3)
    if concept in RUN:
        if concept == 'End Around':
            receiver = min(wr,key=lambda s:abs(positions[s][0]))
            side = -1 if positions[receiver][0]>0 else 1
        out[0] = l.qb_handoff_chain(hb,0)
        for s in range(1,6):
            # PROVED OFFLINE: native zone OL is type 8/group 2, not type 0.
            if concept in ('Inside Zone','Outside Zone','End Around'):
                dx = side if concept != 'Inside Zone' else 0
                leg = l.leg(8,dx,1,turn=0 if side>0 else 1,group=2)
                out[s] = [l.start(2 if s==3 else 3), *([(2,[0])] if s==3 else []), leg]
            else:
                out[s] = l.center_chain(0,'straight',True) if s==3 else l.blocker_chain('straight',0,True)
        for s in range(6,11):
            out[s] = l.stalk_block_chain() if kind[s]==l.WR else l.blocker_chain('straight',side,True)
        aim = {'Inside Zone': 2, 'Outside Zone':7, 'Counter':3, 'Downhill':1, 'End Around':9}[concept]*side
        out[hb] = l.carrier_chain(l.handoff_hole_for_x(aim*YD), (0,aim,2,2))
        if concept == 'Counter':
            pull = min((s for s in (4,5)), key=lambda s:side*positions[s][0])
            out[pull] = l.blocker_chain('pull-right' if side>0 else 'pull-left',side,True)
            out[0] = l.qb_handoff_chain(hb,5)
        if concept == 'End Around':
            # PROVED OFFLINE: retail direct WR transfer idiom (NYG 228).
            # DESIGN: post-snap end around; no automatic pre-snap jet motion.
            out[0] = l.qb_handoff_chain(receiver,2)
            out[receiver] = l.carrier_chain(l.handoff_hole_for_x(side*10*YD),(0,side*10,-4,2))
            out[hb] = l.lead_block_chain(side*5,1)
        return 'run', out, None
    if concept == 'Mesh':
        other = max(wr, key=lambda s:abs(positions[s][0]-positions[te][0]))
        out[te] = route((0,3),(4,abs(positions[te][0]/YD)+9))
        out[other] = route((0,4),(4,abs(positions[other][0]/YD)+7))
        for s in wr:
            if s != other: out[s]=route((0,depth),(6,8))
    elif concept == 'Stick':
        out[te]=route((0,6),(7,1))
        if kind[9] == l.TE: out[9]=route((5,5))
    elif concept == 'Levels':
        out[te]=route((0,3),(4,15))
        out[wr[0]]=route((0,6),(4,12))
        out[wr[-1]]=route((0,depth),(4,14))
    elif concept == 'Y Cross':
        out[te]=route((0,10),(3,20))
        out[wr[0]]=route((0,18),(2,10))
        out[wr[-1]]=route((0,14),(7,2))
    elif concept == 'Dagger':
        out[te]=route((0,25))
        out[wr[-1]]=route((0,depth+4),(4,15))
        out[wr[0]]=route((0,3),(4,15))
    elif concept in ('Flood','PA Boot'):
        high = max(wr,key=lambda s:side*positions[s][0])
        flood_side = 1 if positions[high][0]>=0 else -1
        te_side = 1 if positions[te][0]>=0 else -1
        out[te]=route((0,10),(5 if flood_side==te_side else 4,15))
        out[high]=route((0,25))
        # A same-side flat pairs with the TE out; move the HB route laterally
        # toward that side using inside/outside relative to his alignment.
        hb_side = 1 if positions[hb][0]>=0 else -1
        out[hb]=route((5 if flood_side==hb_side else 4,8))
    elif concept == 'Drive':
        same_side = [s for s in wr if positions[s][0]*positions[te][0]>0]
        shallow = te if same_side else min(wr,key=lambda s:abs(positions[s][0]))
        out[shallow]=route((0,3),(4,16))
        same = min(same_side or [s for s in wr if s!=shallow],key=lambda s:abs(positions[s][0]-positions[shallow][0]))
        out[same]=route((0,depth),(4,15))
        primary=shallow
        out[hb]=l.blocker_chain('pass',0,False)
    elif concept == 'TE Seam':
        out[te]=route((0,24+variant%3*2))
        out[wr[0]]=route((0,12),(4,12))
        out[wr[-1]]=route((0,18),(6,8))
        if kind[9]==l.TE:out[9]=route((0,3),(4,12))
    elif concept == 'TE Drag':
        out[te]=route((0,3),(4,18))
        out[wr[0]]=route((0,20),(2,10))
        out[wr[-1]]=route((0,depth),(4,12))
    elif concept == 'RB Slip':
        # DESIGN: pre-author level D to avoid extra nodes in the complete book.
        settings=l.ScreenPreset('HB',hb,side,0.8,7,0.6)
        out[0]=l.screen_qb_chain(settings)
        out[hb]=l.screen_receiver_chain(side)
        release=[3]+[max((s for s in range(1,6) if kind[s]==k),key=lambda s:side*positions[s][0]) for k in (l.T,l.G)]
        for s in release:
            out[s]=l.screen_blocker_chain(kind[s],settings,0)
        for s in (6,9):
            if kind[s] in (l.TE,l.FB):out[s]=l.blocker_chain('pass',0,False)
        primary=hb
    else:
        raise ValueError(concept)
    play_type='pa_pass' if concept=='PA Boot' else 'pass'
    if play_type=='pa_pass':
        out[0]=[l.start(4),(3,[0]),(0x14,[hb,1]),(4,[1,side*5*YD,-5*YD,0]),(6,[0,te-5,2,3,4,0.0])]
        out[hb]=l.fake_carrier_chain(0,l.blocker_chain('pass',0,False))
        # Use the second TE/slot for the boot flat, leaving the back in protection.
        flat_side = 1 if positions[9][0]>=0 else -1
        out[9]=route((5 if flat_side==flood_side else 4,8))
    elif concept != 'RB Slip':
        others=[s-5 for s in range(6,11) if s!=primary][:3]
        out[0][-1]=(6,[0,primary-5,*others,0.0])
    return play_type,out,primary


def build(resource):
    book=i.parse_playbook_resource(resource)
    body=resource[32:]
    forms, plays=ordinary_indices(book,body)
    assert len(forms)==26 and len(plays)==148
    formations, authored, menus, catalog=[],[],[],[]
    targets=iter(sorted(plays))
    for ordinal, fi in enumerate(sorted(forms)):
        name,cat,qbz,skills=SHAPES[ordinal//2]
        mirror=-1 if ordinal%2 else 1
        positions=[(0,round(qbz*YD)),(302,0),(-302,0),(0,0),(155,0),(-155,0)]
        positions += [(round(x*YD*mirror),round(z*YD)) for x,z in skills]
        codes=tuple(l.category_positions(body,cat))
        donors=[f.index for f in book.formations if l.formation_category(body,f.index)==cat and f.index in forms]
        # PROVED OFFLINE: use a gun donor when available; writer sets snap flag from depth.
        donor=donors[0]
        fid=f'f{fi:02d}'
        formation=p.PackFormation(fid,name+(' L' if mirror<0 else ' R'),tuple(positions),codes,
                  p.PackDonor(donor,book.formations[donor].name.strip()),fi,book.formations[fi].name.strip(),cat)
        formations.append(formation)
        count=6 if ordinal<18 else 5
        if name=='Gun Empty':
            concepts=['Mesh','Stick','Levels','Y Cross','TE Seam','TE Drag']
        else:
            concepts=['Inside Zone' if ordinal%2==0 else 'Outside Zone',
                      ['Counter','Downhill','End Around'][ordinal%3],
                      'TE Seam' if ordinal%2==0 else 'TE Drag',
                      PASS[(ordinal+2)%len(PASS)],
                      'PA Boot' if qbz>-3 else PASS[(ordinal+5)%len(PASS)],
                      PASS[(ordinal+8)%len(PASS)]][:count]
            # DESIGN: no duplicate concept label within a formation menu.
            for n in range(len(concepts)):
                if concepts[n] in concepts[:n]:
                    concepts[n]=next(x for x in PASS if x not in concepts)
        ids=[]
        for index,concept in enumerate(concepts):
            pi=next(targets)
            play_type,chains,primary=assignments(concept,positions,codes,ordinal)
            donor,flags=l.reference_play_for(book,body,play_type)
            pid=f'p{pi:03d}'
            label=f'{fi+1:02d} '+('RB Screen' if concept=='RB Slip' else concept)
            authored.append(p.PackPlay(pid,label,play_type,tuple(tuple(ch) for ch in chains),
                p.PackDonor(donor,book.plays[donor].name.strip(),book.plays[donor].flags_or_id,l.qb_signature(l.play_chains(body,donor)[1][0][1])),
                flags,pi,book.plays[pi].name.strip(),concept))
            ids.append(pid)
            catalog.append(dict(status='DESIGN',play_index=pi,name=label,formation_index=fi,
                                formation=formation.custom_name,concept=concept,play_type=play_type,
                                personnel='12' if cat==2 else ('21' if cat==3 else '11'),
                                primary_slot=primary,te1_slot=6,menu_slot=index,
                                opcodes=sorted({f'0x{n[0]:02X}' for ch in chains for n in ch})))
        menus.append((fid,tuple(ids)))
    assert next(targets,None) is None
    pack=p.PlaybookPack(p.PackBook('NYG','NFL 2K28 Giants Modern','SOFTDRINK / Astra','0.1.0','CC0-1.0',
        notes='DESIGN: Giants lab candidate. TE1 featured. No RPO/read option. Automatic jet motion, middle screens and guaranteed duo combos excluded. PROVED OFFLINE status requires attached receipt; gameplay awaits main.'),
        p.PackBase(p.book_fingerprint(body),len(book.formations),len(book.plays),book.node_count),
        tuple(formations),tuple(authored),p.OFFENSE_SCHEMA,tuple(menus))
    return pack,catalog


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image',type=Path,required=True)
    ap.add_argument('--output',type=Path,default=ROOT/'data/playbooks/softdrink_giants_modern.2k5book')
    args=ap.parse_args()
    pack,catalog=build(_resource_from_image(args.image,'NYG'))
    p.save_pack(pack,args.output)
    (ROOT/'pb/catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    print(json.dumps(dict(formations=len(pack.formations),plays=len(pack.plays),
                         concepts=dict(Counter(x['concept'] for x in catalog)))))


if __name__=='__main__':main()
