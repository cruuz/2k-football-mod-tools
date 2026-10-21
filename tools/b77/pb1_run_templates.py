"""Extract playside-relative run templates from named retail plays (prints a Python literal).

b776 pb1: the source of ``RUN_TEMPLATES`` in mod_editor/core/nfl2k5_offense_modern.py.
    python3 tools/b77/pb1_run_templates.py BOOKS_DIR   (BOOKS_DIR holds the retail <TEAM>.play extracts)
"""
import sys, pprint
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT), str(ROOT / 'tools')]
BOOKS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
from mod_editor.core import nfl2k5_playbook_inspector as insp, nfl2k5_play_library as lib, nfl2k5_play_codec as codec
FT=codec.FT_CM; YD=codec.YD_CM
PICKS = {
 "Inside Zone": "ARZ:Ace:Weak Zone Cutback", "Outside Zone": "ARZ:Ace:Strong Outside Zone",
 "Stretch": "ARZ:I Wing Jokers:Weak Stretch", "Dive": "ARZ:Ace:Strong Dive", "Iso": "ARZ:I Spread:Strong Iso",
 "Fan Iso": "BUF:Split Pro:Strong Fan Iso", "Power O": "ARZ:Triple:Strong Power", "Belly": "ATL:I Twins:Weak Belly",
 "Counter": "ARZ:I Pro:Strong Counter", "Counter Trey": "BAL:I Wing Jokers:Strong Counter Trap",
 "Trap": "CAR:Pro F Flex:Strong Trap", "Sweep": "ARZ:Split Pro:Strong Sweep",
 "Pin Pull Sweep": "ATL:Split Jokers:Strong Split Sweep", "Lead Stretch": "CHI:Triple Bunch:Strong Lead Stretch",
 "Toss": "ARZ:Ace:Strong Toss", "Draw": "ARZ:Ace:Strong Draw", "Lead Draw": "OAK:I Jokers:Strong Lead Draw",
 "G Iso": "ARZ:I Spread:Weak G-Iso", "Inside Trap": "ATL:Split Twins:Strong Inside Trap", "WB Sweep": "ARZ:I Wing Jokers:Weak WB Sweep",
 "Direct Snap": "BUF:Gun: Trey Right:H Direct Snap", "FB Dive": None,
}
def find(team, form, name):
    raw=(BOOKS / f'{team}.play').read_bytes(); b=insp.parse_playbook_resource(raw); body=raw[32:]
    for f in b.formations:
        if f.name.strip()!=form: continue
        for l in f.play_links:
            p=b.plays[l.play_index]
            if p.name.strip()==name:
                fr=lib.formation_record(body,f.index); codes=lib.category_positions(body,lib.formation_category(body,f.index))
                return p, [(fr.slots[s].x[0], fr.slots[s].z[0]) for s in range(11)], codes, lib.decoded_chains(body,p.index)
    raise SystemExit(f'missing {team} {form} {name}')
def tr(turn,d):
    return 'st' if turn==2 else ('ps' if (turn==1)==(d>0) else 'bs')
def leg(v,d):
    kind,t,rel,end,turn,dx,dy,g=v
    return (int(kind), round(t,2), int(rel), int(end), tr(int(turn),d), round(dx*d/FT), round(dy/FT), int(g))
out={}
for key,spec in PICKS.items():
    if not spec: continue
    team,form,name=spec.rsplit(':',2) if spec.count(':')==2 else (spec.split(':')[0], ':'.join(spec.split(':')[1:-1]), spec.split(':')[-1])
    p,pos,codes,ch=find(team,form,name)
    kinds=[c&31 for c in codes]
    # carrier
    carrier=None; k=None; hole=None
    for s,c in enumerate(ch):
        for op,v,*_ in c:
            if op==0x13 and carrier is None: carrier=int(v[0]); k=int(v[1])
    snap=next(int(v[0]) for op,v,*_ in ch[next(s for s in range(11) if kinds[s]==lib.C)] if op==0x02)
    if carrier is None: carrier=snap
    take=next(((int(v[0]),round(v[1],2),int(v[2])) for op,v,*_ in ch[carrier] if op==0x16),None)
    lat=codec.HANDOFF_HOLE_CM[take[2]] if take else 0
    pth=next((v for op,v,*_ in ch[carrier] if op==0x15),None)
    d = 1 if lat>0.1 else -1 if lat<-0.1 else (1 if pth is None or pth[1]>=0 else -1)
    ol=[s for s in range(11) if kinds[s] in lib.OL_KINDS]
    def role(s):
        x=pos[s][0]*d; kd=kinds[s]
        if kd==lib.C: return 'C'
        return ('P' if x>0 else 'B')+('T' if kd==lib.T else 'G')
    roles={s:role(s) for s in ol}
    t=dict(source=f"{team} {form} / {name}", flags=hex(p.flags_or_id), handoff=k, carrier=kinds[carrier],
           take=(take[0],take[1],round(lat*d/YD,2)) if take else None,
           path=(int(pth[0]),round(pth[1]*d/FT),round(pth[2]/FT),int(pth[3]),roles.get(int(pth[5])) or ('B2' if int(pth[5]) and kinds[int(pth[5])] in (lib.FB,lib.HB,lib.TE) else None) if int(pth[0])==2 else None,int(pth[6])) if pth is not None else None,
           ol={roles[s]:[leg(v,d) for op,v,*_ in ch[s] if op==0x11] for s in ol},
           qb=[(op,[round(x/FT) if isinstance(x,float) and abs(x)>40 else x for x in v]) for op,v,*_ in ch[0] if op not in (0x01,0x03,0x13)],
           others={})
    for s in range(11):
        if s in ol or s==0 or s==carrier: continue
        legs=[leg(v,d) for op,v,*_ in ch[s] if op==0x11]
        side='ps' if pos[s][0]*d>0.3*YD else 'bs' if pos[s][0]*d<-0.3*YD else 'mid'
        back = pos[s][1] < -2.5*YD
        t['others'][f"{codec.position_label(codes[s])}@{'back' if back else ('los' if abs(pos[s][1])<20 else 'off')}:{side}"]=legs
    out[key]=t
pprint.pprint(out,width=160,sort_dicts=False)
