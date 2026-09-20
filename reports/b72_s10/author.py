"""Rebuild s10 assets from the immutable s9 art, in measured area order."""
from pathlib import Path
import argparse
import json
import sys
import math

import numpy as np
from PIL import Image, ImageDraw

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'reports/b72_s9')]
from mod_editor.core import nfl2k5_scorebug_resources as resources
from mod_editor.core import nfl2k5_scorebug_teams as teams

ORDER=['wing_colour','housing_rim','down_capsule','logo','pill','score']


def rounded(w,h,r,colour,ends='both'):
    im=Image.new('RGBA',(w*4,h*4),(255,255,255,0));d=ImageDraw.Draw(im)
    d.rounded_rectangle((0,0,w*4-1,h*4-1),r*4,fill=colour)
    if ends=='left':d.rectangle((w*2,0,w*4-1,h*4-1),fill=colour)
    if ends=='right':d.rectangle((0,0,w*2,h*4-1),fill=colour)
    return im.resize((w,h),Image.Resampling.LANCZOS)


def main():
    p=argparse.ArgumentParser();p.add_argument('--through',choices=ORDER,default=ORDER[-1])
    p.add_argument('--wing-decay',type=float,default=65);a=p.parse_args()
    if not 40<=a.wing_decay<=120:raise ValueError('Wing decay outside measured search range')
    steps=ORDER[:ORDER.index(a.through)+1]
    src=ROOT/'.scratch/s10_before';dest=ROOT/'data/nfl2k5_scorebug_sprite'
    spec=json.loads((src/'layout.json').read_text());old=Image.open(src/'template.png').convert('RGBA')
    cells={n:old.crop(r['box']) for n,r in spec['cells'].items()}
    rows={r['name']:r for r in spec['static']};fields={r['name']:r for r in spec['fields']}
    if 'wing_colour' in steps:
        # Team colour covers the entire logo well before a broad soft fade.
        # No foreign hue or text contrast exception is introduced.
        for name in ('wing','home_wing'):
            im=rounded(340,110,8,'white','left');v=np.asarray(im).copy()
            xx=np.arange(340)
            for y in range(110):
                ramp=(.92*np.exp(-xx/a.wing_decay)
                      +.75*np.exp(-y/7)*np.exp(-xx/250)
                      +.38*np.exp(-(109-y)/8)*np.exp(-xx/150))
                v[y,:,3]=np.rint(v[y,:,3]*np.minimum(1,ramp))
            im=Image.fromarray(v).resize((113,45),Image.Resampling.BOX)
            v=np.asarray(im).copy();v[:,-1,3]=0;cells[name]=Image.fromarray(v)
        rows['away_wing']['box']=[437,942,777,1052]
        rows['home_wing']['box']=[1138,942,1478,1052]
    if 'housing_rim' in steps:
        # A one-HUD-row rim and a quiet dark centre; the colour well carries
        # the visual area, rather than a large silver/grey body surround.
        im=rounded(1041,110,8,(37,37,37,255));v=np.asarray(im).copy()
        for y in range(110):
            value=np.interp(y,[0,2,4,7,103,106,108,109],[58,145,74,37,37,62,108,25])
            v[y,:,:3]=round(value)
        cells['body']=Image.fromarray(v).resize((173,45),Image.Resampling.BOX)
        for name in ('away_rim','home_rim'):
            v=np.zeros((110,523,4),dtype='uint8');v[:,:,:3]=255
            for y in range(110):
                edge=min(y,109-y)
                v[y,:,3]=np.rint(255*.68*math.exp(-edge/2.0)*np.linspace(1,.22,523))
            if name=='home_rim':v=v[:,::-1].copy()
            cells[name]=Image.fromarray(v).resize((174,45),Image.Resampling.BOX)
        housing=rounded(252,56,27,(14,14,14,255));d=ImageDraw.Draw(housing)
        d.rounded_rectangle((2,2,249,53),25,outline=(112,112,112,255),width=2)
        d.rounded_rectangle((5,5,246,50),22,outline=(52,52,52,255),width=2)
        cells['housing']=housing.resize((84,23),Image.Resampling.BOX)
        rows['housing']['box']=[834,993,1086,1049]
    if 'down_capsule' in steps:
        plate=Image.new('RGBA',(288*4,46*4),(255,255,255,0));d=ImageDraw.Draw(plate)
        d.polygon([(x*4,y*4) for x,y in [(0,0),(287,0),(278,7),(276,12),(276,34),(269,45),(18,45),(11,34),(11,12),(9,7)]],fill='white')
        plate=plate.resize((288,46),Image.Resampling.BOX);v=np.asarray(plate).copy()
        for y in range(46):v[y,:,:3]=round(255*np.interp(y,[0,3,7,25,39,45],[1,.98,.92,.90,.86,.66]))
        cells['plate']=Image.fromarray(v).resize((96,19),Image.Resampling.BOX)
        rows['plate']['box']=[822,945,1096,987]
        rows['pointer']['box']=[951,942,965,947]
        fields['down'].update(box=[829,950,1089,980],anchor=[959,950])
        # Preserve each event's material, native visibility and binding.
        for row in spec['events']:row['box']=[822,945,1096,987]
    if 'logo' in steps:
        rows['away_logo']['box']=[437,942,667,1052]
        rows['home_logo']['box']=[1248,942,1478,1052]
        fits={}
        for name in resources.TEAM_LOGOS:
            key='wsh' if name=='WAS' else name.lower()
            im=Image.open(ROOT/'data/nfl2k5_scorebug_mnf/logos'/(key+'.png'))
            x,y,r,b=im.getchannel('A').getbbox();ratio=(r-x)/(b-y)
            # Native texture remains 64 square. The new wider quad requires
            # a compensating fit, then team-specific scale/crop, never a
            # shared stretched square. Tall marks bleed top and bottom.
            fits[name]=dict(fill_x=.92 if ratio<1.5 else 1.02,height=1.,
                zoom=1.13 if ratio<1.5 else 1.07,shift_x=0.,shift_y=0.)
        fits.update(
            DEN=dict(fill_x=.86,height=1.,zoom=1.,shift_x=0.,shift_y=.045),
            KC=dict(fill_x=.90,height=1.,zoom=1.10,shift_x=0.,shift_y=0.),
            LV=dict(fill_x=1.00,height=1.,zoom=1.10,shift_x=0.,shift_y=0.),
            HOU=dict(fill_x=1.04,height=1.,zoom=1.25,shift_x=.075,shift_y=0.),
            WAS=dict(fill_x=1.02,height=1.,zoom=1.17,shift_x=-.04,shift_y=0.),
            LAC=dict(fill_x=1.02,height=1.,zoom=1.13,shift_x=.025,shift_y=.015))
        spec['logo_fit']=dict(default=dict(fill_x=.92,height=1.,zoom=1.13),by_team=fits)
    if 'pill' in steps:
        rows['capsule']['box']=[839,999,1019,1039]
        rows['red']['box']=[1019,999,1082,1039]
        # Keep the proven clock, quarter and play-clock anchors, widen the
        # white cushion. The larger 43-row trial visibly overshot ESPN and
        # was rejected. Retain the measured 40-row outer size and source.
    if 'score' in steps:
        # Modest +5.7 percent, supported by the player-size cap difference.
        # Refilter the traced masks at the new HUD cap, not a scaled bitmap.
        for name in ('away_score','home_score'):
            field=fields[name];field['size']=56;field['box'][1]=964;field['box'][3]=1020;field['anchor'][1]=964
        fields['home_score']['box'][0]-=5;fields['home_score']['box'][2]-=5
        fields['home_score']['anchor'][0]-=5
        for token,g in spec['glyph_sets']['score']['glyphs'].items():
            if not token.isdigit():continue
            trace=ROOT/'reports/b72_s9/glyphs'/('score_'+token+'.png')
            if not trace.exists():trace=ROOT/'reports/b72_s9/glyphs'/('clock_'+token+'.png')
            mask=Image.open(trace).convert('L')
            size=(cells[g['cell']].width,max(1,int(56*448/1080)))
            im=Image.new('RGBA',size,'white');im.putalpha(mask.resize(size,Image.Resampling.BOX));cells[g['cell']]=im
    sheet=Image.new('RGBA',(1536,512),(255,255,255,0));x=y=line=0;spec['cells']={}
    for name,im in cells.items():
        if x+im.width+2>sheet.width:x=0;y+=line+2;line=0
        if y+im.height>sheet.height:raise ValueError('Source canvas overflow')
        sheet.paste(im,(x,y));spec['cells'][name]=dict(box=[x,y,x+im.width,y+im.height]);x+=im.width+2;line=max(line,im.height)
    spec['provenance'].update(author='reports/b72_s10/author.py',revision='b72-s10',
        fidelity_report='reports/b72_s10/FIDELITY.md',geometry_steps=steps,wing_decay=a.wing_decay)
    sheet.save(dest/'template.png')
    (dest/'layout.json').write_text(json.dumps(spec,indent=1)+'\n',encoding='utf-8',newline='\n')
    accents=json.loads((src/'team_accents.json').read_text())
    if 'wing_colour' in steps:
        den=accents['teams']['DEN'];parent='#0A2343';vivid='#1E69C9'
        assert parent in den['official'] and vivid in teams.variants(den['official'])
        assert teams.contrast_white(vivid)>=4.5
        candidate=dict(hex=vivid,parent=parent,variant='unclipped_rgb_gain_3',
            contrast_white=round(teams.contrast_white(vivid),4),
            facts=dict(hue='blue',lightness='mid',white_label='pass',signature=True))
        for team in accents['teams'].values():
            if (team['asset_code'],team['kind'])==(den['asset_code'],den['kind']):
                team['candidates']['colour1_vivid']=candidate
                for role in teams.ROLES:team[role]=vivid
    for name,t in accents['teams'].items():
        if name in spec['logo_fit']['by_team']:t['logo_fit']=spec['logo_fit']['by_team'][name]
    (dest/'team_accents.json').write_text(json.dumps(accents,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Authored steps:',steps)


if __name__=='__main__':main()
