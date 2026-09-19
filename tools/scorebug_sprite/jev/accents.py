"""Contrast-gated team accent proposals from the pinned retail colour table.

Produces a review candidate. Applying it to the shipped layout is a separate
step and must wait for the dark-label reproduction gate.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.scorebug_sprite.jev.descriptors import contrast,hue_name,rgb_luma
from tools.scorebug_sprite.jev.session import write_json
from mod_editor.core.nfl2k5_scorebug_resources import TEAM_LOGOS


def rgb(value):return tuple(int(value[i:i+2],16) for i in (1,3,5))
def hex_rgb(value):return '#'+''.join(f'{int(v):02X}' for v in value)


def game_palettes(xbe,pack):
    """Read only metadata, refusing a foreign native colour table."""
    import nfl_outer
    import nfl_roster as roster
    import nfl2k5_roster_reclassify as records
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    from mod_editor.core.nfl2k5_scorebar_v3 import COLOR_TABLE,GUARDS
    payload=Path(xbe).read_bytes();image=XbeImage(payload);begin,end,stride=COLOR_TABLE
    raw=payload[image.offset(begin):image.offset(end)]
    expected=next(r[2] for r in GUARDS if r[0]==begin)
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Foreign retail team colour table')
    def string(va):
        at=image.offset(va);chars=[]
        while True:
            c=struct.unpack_from('<H',payload,at)[0];at+=2
            if not c:return ''.join(chars)
            chars.append(chr(c))
            if len(chars)>64:raise ValueError('Unbounded team code')
    table={string(struct.unpack_from('<I',raw,i)[0]):['#%06X'%(struct.unpack_from('<I',raw,i+off)[0]&0xffffff) for off in (8,12)] for i in range(0,len(raw),stride)}
    with Path(pack).open('rb') as f:
        f.seek(nfl_outer.HEADER_SIZE+5*12);_,size,sector=struct.unpack('<3I',f.read(12));f.seek(sector*2048)
        resource=records.parse_resource(5,sector*2048,f.read(size))
    codes={r['asset_code']:name for name,r in TEAM_LOGOS.items()};teams={}
    for t in resource.teams:
        _,code=roster.string_pointer(resource.body,t.offset+0x10c,'team asset code')
        name=codes[code] if t.index<32 else t.abbreviation
        custom=t.kind in (2,4);known=code in table and not custom
        colors=table[code] if known else ['#303030','#C0C0C0']
        teams[name]=dict(slot=t.index,name=t.name,asset_code=code,kind=t.kind,official=colors,
            source='pinned retail primary/secondary table' if known else 'neutral custom fallback; supply team colours explicitly',
            custom=custom,known=known,logo_fit=dict(fill_x=1.14,height=1.0))
    return dict(table_sha256=expected,table_va=hex(begin),table_end=hex(end),teams=teams)


def candidates(colors):
    out={}
    for index,color in enumerate(colors):
        value=rgb(color)
        for suffix,gain,lift in [('base',1,0),('dark',.75,0),('darker',.5,0),('light',.85,.15),('lighter',.7,.3)]:
            c=tuple(round(channel*gain+255*lift) for channel in value);key=f'colour{index}_{suffix}'
            ratio=contrast(c)
            out[key]=dict(hex=hex_rgb(c),parent=color,variant=suffix,contrast_white=round(ratio,4),
                facts=dict(hue=hue_name(c),lightness='dark' if max(c)<90 else 'mid' if max(c)<190 else 'light',
                white_label='pass' if ratio>=4.5 else 'fail',plate_separation='unknown_until_paired',signature=index==0))
    return out


def prepare(palettes):
    requests=[];teams={}
    for name,team in palettes['teams'].items():
        choices=candidates(team['official']);teams[name]=dict(team,candidates=choices)
        allowed={k:json.dumps(v['facts'],sort_keys=True) for k,v in choices.items() if v['contrast_white']>=4.5}
        if not allowed:raise ValueError('No readable team candidates: '+name)
        for phrase in (0,1):
            instruction=('Choose this team accent, preserving its signature colour while keeping the white label readable.' if phrase==0 else
                         'Select a readable accent that identifies the named team. Prefer its own signature hue; use only listed passing candidates.')
            requests.append(dict(tool='jev_ask',state=dict(team=name,source=team['source'],phrasing=phrase,candidates={k:v['facts'] for k,v in choices.items()}),
                questions={role:dict(type='choice',instructions=instruction+' Role: '+role+'.',criteria=allowed) for role in ('wing','rim','plate')}))
    return teams,requests


def choose(teams,responses):
    if len(responses)!=len(teams)*2:raise ValueError('Two independent phrasings are required for every team')
    result={};review=[]
    for index,(name,team) in enumerate(teams.items()):
        a,b=responses[index*2:index*2+2];picks={};reasons=[]
        for role in ('wing','rim','plate'):
            one,two=a.get(role,{}),b.get(role,{})
            keys=[r.get('choice') for r in (one,two)];key=keys[0];candidate=team['candidates'].get(key)
            if keys[0]!=keys[1]:reasons.append(role+': phrasing disagreement')
            if min(one.get('confidence',0),two.get('confidence',0))<.6:reasons.append(role+': confidence below 0.6')
            if candidate is None or candidate['contrast_white']<4.5:
                reasons.append(role+': code rejected invalid/low-contrast pick')
                passing=[(k,v) for k,v in team['candidates'].items() if v['contrast_white']>=4.5]
                key,candidate=max(passing,key=lambda kv:(kv[1]['facts']['signature'],kv[1]['contrast_white']))
            picks[role]=candidate['hex']
        result[name]=dict(slot=team['slot'],asset_code=team['asset_code'],source=team['source'],official=team['official'],
            **picks,logo_fit=team['logo_fit'],review_required=bool(reasons),candidates=team['candidates'])
        if reasons:review.append(dict(team=name,reasons=reasons))
    return dict(schema='scorebug-team-accents/v1',status='review candidate; not applied to layout',teams=result,review=review,
        custom_rule='Use the configured team primary and secondary with the same variant/contrast gate. Until supplied, neutral charcoal/silver. Never borrow another team hue.',
        limitation='Existing runtime binds only 32 NFL logos and a neutral fallback. Extra-slot tint binding is not implemented.')


def contact_sheet(result,path):
    from PIL import Image,ImageDraw
    rows=list(result['teams'].items());im=Image.new('RGB',(720,54*((len(rows)+2)//3)),'#242424');d=ImageDraw.Draw(im)
    for i,(name,t) in enumerate(rows):
        x=(i%3)*240;y=(i//3)*54;d.text((x+4,y+3),name+(' REVIEW' if t['review_required'] else ''),fill='white')
        for j,role in enumerate(('wing','rim','plate')):
            d.rectangle((x+j*78+3,y+20,x+j*78+77,y+50),fill=t[role]);d.text((x+j*78+7,y+28),role,fill='white')
    im.save(path)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--xbe',type=Path,required=True);p.add_argument('--pack',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();palettes=game_palettes(a.xbe,a.pack);teams,requests=prepare(palettes)
    write_json(a.output/'palettes.json',palettes);write_json(a.output/'teams.json',teams);write_json(a.output/'requests.json',requests)
    print(len(teams),'team slots;',len(requests),'text-only requests')

if __name__=='__main__':main()
