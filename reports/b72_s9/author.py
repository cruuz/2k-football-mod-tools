"""Author the bounded SD sprite cells from broadcast traces and measured ramps.

Uses no installed, retail or third-party font. This is an offline report tool;
the shipped compiler continues to consume the existing PNG/JSON interface.
"""
from pathlib import Path
from copy import deepcopy
import json
import math
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_resources as art
from mod_editor.core import nfl2k5_scorebug_teams as teams


def write(path,value):
    path.write_text(json.dumps(value,indent=1)+'\n',encoding='utf-8',newline='\n')


def rounded(w,h,r,colour,ends='both'):
    im=Image.new('RGBA',(w*4,h*4),(255,255,255,0));d=ImageDraw.Draw(im)
    d.rounded_rectangle((0,0,w*4-1,h*4-1),r*4,fill=colour)
    if ends=='left':d.rectangle((w*2,0,w*4-1,h*4-1),fill=colour)
    if ends=='right':d.rectangle((0,0,w*2,h*4-1),fill=colour)
    return im.resize((w,h),Image.Resampling.LANCZOS)


def main():
    destination=ROOT/'data/nfl2k5_scorebug_sprite'
    source=ROOT/'.scratch/s9_before'
    if not source.exists():
        source.mkdir(parents=True)
        for name in ('layout.json','template.png','team_accents.json','team_colors_official_2026.json'):
            raw=subprocess.check_output(['git','show','42579f4a5:data/nfl2k5_scorebug_sprite/'+name],cwd=ROOT)
            (source/name).write_bytes(raw)
    spec=json.loads((source/'layout.json').read_text())
    old=Image.open(source/'template.png').convert('RGBA')
    cells={k:old.crop(v['box']) for k,v in spec['cells'].items()}
    harvest=json.loads((OUT/'harvest.json').read_text())['glyphs']
    params=json.loads((OUT/'selected_parameters.json').read_text())
    traced={k:Image.open(OUT/'glyphs'/v['file']).convert('L') for k,v in harvest.items() if 'file' in v}
    provenance=[]

    def mask(group,token):
        name=group+'_'+token
        if name in traced:return traced[name],harvest[name]['width'],harvest[name]['height']
        if group=='score' and token in '589':
            # These scores never occur in the supplied live game. Transfer
            # the observed heavy clock contour, not a third-party font.
            m=traced['clock_'+token]
            provenance.append(dict(glyph=name,status='RECONSTRUCTED',source='clock_'+token,
                reason='Digit absent from settled score readouts; same broadcast heavy face scaled to score cap.'))
            return m,49,54
        raise ValueError('Missing broadcast glyph '+name)

    def compose(group,token,height):
        ims=[];width=0
        native_cap=max(mask(group,c)[2] for c in token) if group=='quarter' else 23
        for c in token:
            m,w,h=mask(group,c);scale=height/native_cap
            wh=(max(1,round(w*scale*4)),max(1,round(h*scale*4)))
            m=m.resize(wh,Image.Resampling.LANCZOS);ims.append(m);width+=m.width+8
        out=Image.new('L',(max(1,width-8),round(height*4)))
        x=0
        for m in ims:
            out.paste(m,(x,out.height-m.height));x+=m.width+8
        return out

    # Rare retail strings have no live reference. Derive their missing
    # letters from observed strokes, retaining explicit reconstruction flags.
    legacy_spec=json.loads((ROOT/'data/nfl2k5_scorebug_mnf/espn_glyphs.json').read_text())
    legacy=Image.open(ROOT/'data/nfl2k5_scorebug_mnf/espn_glyphs.png').convert('L')
    def rare_char(ch):
        if 'label_'+ch in traced:return traced['label_'+ch]
        if ch in legacy_spec:return legacy.crop(legacy_spec[ch]['box']).resize((64,92),Image.Resampling.LANCZOS)
        base=traced['label_0'].resize((68,92),Image.Resampling.LANCZOS)
        if ch in 'ce':
            ImageDraw.Draw(base).rectangle((42,27,68,58),fill=0)
            if ch=='e':ImageDraw.Draw(base).rectangle((8,41,64,52),fill=255)
        elif ch in 'ai':
            if ch=='i':
                base=Image.new('L',(24,92));d=ImageDraw.Draw(base);d.rectangle((4,26,19,91),fill=255);d.rectangle((4,3,19,17),fill=255)
            else:ImageDraw.Draw(base).rectangle((51,26,67,91),fill=255)
        elif ch=='I':return traced['quarter_1']
        elif ch=='T':return traced['quarter_T']
        return base

    def rare_word(token):
        chars=[rare_char(c) for c in token]
        result=Image.new('L',(sum(c.width+8 for c in chars)-8,92));x=0
        for c in chars:
            result.paste(c,(x,92-c.height));x+=c.width+8
        provenance.append(dict(glyph=token,status='RECONSTRUCTED',source='observed broadcast strokes and previous broadcast glyph harvest',
            reason='No matching live token. These rare retail words are not claimed 1:1.'))
        return result

    for group,gset in spec['glyph_sets'].items():
        if group=='ticks':continue
        cap=gset['cap_height']
        for token,g in gset['glyphs'].items():
            if token in (' ','~'):continue
            rise=0
            if token.isdigit() or token==':':
                m,w,h=mask(group,token)
                target_h=18 if token==':' else cap
                target_w=w/h*target_h
                if group=='score':target_w*=params['score_scale']
                if token==':':rise=-7
            elif token in ('st','nd','rd','th','ST','ND','RD','TH'):
                suffix_group='quarter' if group=='small' else 'label'
                suffix=token.upper() if group=='small' else token.lower()
                # Suffix contours retain baseline and original relative size.
                target_h=18 if group=='small' else cap
                m=compose(suffix_group,suffix,target_h)
                target_w=m.width/m.height*target_h
                rise=0
            elif token=='&':
                m,w,h=mask('label','&');target_h=cap;target_w=w/h*cap
            elif token in ('Goal','GOAL'):
                m=traced['label_GOAL'];target_h=cap;target_w=m.width/m.height*cap
            else:
                m=rare_word(token);target_h=cap;target_w=m.width/m.height*cap
            g.update(size=[round(target_w,3),target_h],advance=round(target_w+(4 if group=='score' else 2),3),raise_=rise)
            g['raise']=g.pop('raise_')
            # Never let the native sampler minify these masks. Broad counters
            # and one-pixel stem cores survive the 448-line output grid.
            scale={'score':min(1,120/(3*(target_w+4))), 'clock':min(1,108/118)}.get(group,1)
            size=(max(1,int(target_w*scale/3)),max(1,int(target_h*448/1080)))
            rgba=Image.new('RGBA',size,'white');alpha=m.resize(size,Image.Resampling.BOX)
            a=np.asarray(alpha).copy()
            # Full-alpha interiors are preserved; no hue or per-team multiplier.
            a[a>=235]=255
            rgba.putalpha(Image.fromarray(a));cells[g['cell']]=rgba
    # All characters in the clock share the heavy traced face; the play
    # clock and quarter use their own, visibly lighter broadcast contours.
    for f in spec['fields']:
        if f['name'] in ('clock','quarter','play_clock'):f['colour']='#171717'
        if f['name']=='clock':f['box']=[906,1006,1014,1033]
        if f['name']=='down':f['size']=30
    # The quarter has a lighter numeral and a small raised ordinal. Treat
    # each observed ordinal as one traced token so native quantization does
    # not crush the narrow numeral independently of its suffix.
    quarter={}
    for number,suffix in zip('1234',('ST','ND','RD','TH')):
        token=number+suffix;parts=[];width=0
        for ch in token:
            m,w,h=mask('quarter',ch)
            height=22 if ch==number else 14
            part=m.resize((round(w/h*height*4),height*4),Image.Resampling.BOX)
            parts.append(part);width+=part.width+4
        m=Image.new('L',(width-4,88));x=0
        for part in parts:m.paste(part,(x,0));x+=part.width+4
        name='quarter_'+token;w=m.width/4
        # Hint only near-opaque coverage to the native grid, retaining counters.
        coverage=m.resize((max(1,int(w/3)),9),Image.Resampling.BOX)
        values=np.asarray(coverage).copy();values[values>=180]=255
        rgba=Image.new('RGBA',coverage.size,'white');rgba.putalpha(Image.fromarray(values));cells[name]=rgba
        quarter[token]=dict(cell=name,size=[w,22],advance=w+2)
        quarter[number+suffix.lower()]=deepcopy(quarter[token])
    m=rare_word('OT');w=30
    cells['quarter_OT']=Image.new('RGBA',(10,9),'white');cells['quarter_OT'].putalpha(m.resize((10,9),Image.Resampling.BOX))
    quarter['OT']=dict(cell='quarter_OT',size=[w,22],advance=w+2)
    spec['glyph_sets']['quarter']=dict(cap_height=22,glyphs=quarter)
    for f in spec['fields']:
        if f['name']=='quarter':f.update(glyph_set='quarter',size=22,box=[846,1008,900,1030],anchor=[873,1008])

    # Authored source geometry, area-filtered once to the fixed atlas budget.
    body=rounded(1041,110,8,(37,37,37,255));a=np.asarray(body).copy()
    for y in range(110):
        value=np.interp(y,[0,1,3,5,8,18,102,105,108,109],[20,125,210,92,37,37,37,66,115,25])
        a[y,:,:3]=round(value)
    cells['body']=Image.fromarray(a).resize((173,45),Image.Resampling.BOX)
    for name in ('wing','home_wing'):
        im=rounded(233,110,8,'white','left');a=np.asarray(im).copy()
        for x in range(233):
            alpha=params['wing_peak']*max(0,1-max(0,x-13)/220)**params['wing_power']
            a[:,x,3]=np.rint(a[:,x,3]*alpha)
        # Gentle vertical falloff, measured independently of the horizontal ramp.
        for y in range(110):a[y,:,3]=np.rint(a[y,:,3]*np.interp(y,[0,12,50,100,109],[.90,1,.85,.90,.8]))
        a[:,:,:3]=255
        fitted=Image.fromarray(a).resize((77,45),Image.Resampling.BOX)
        arr=np.asarray(fitted).copy();arr[:,-1,3]=0;cells[name]=Image.fromarray(arr)
    for name in ('away_rim','home_rim'):
        a=np.zeros((110,523,4),dtype='uint8');a[:,:,:3]=255
        # Fine, quiet team rim. The neutral foundation supplies specular light.
        for y in range(110):
            edge=min(y,109-y)
            strength=.72*math.exp(-edge/max(1,params['rim_width']))
            a[y,:,3]=np.rint(255*strength*np.linspace(1,.30,523))
        if name=='home_rim':a=a[:,::-1].copy()
        cells[name]=Image.fromarray(a).resize((174,45),Image.Resampling.BOX)
    plate=Image.new('RGBA',(268*4,40*4),(255,255,255,0));draw=ImageDraw.Draw(plate)
    draw.polygon([(x*4,y*4) for x,y in [(0,0),(267,0),(258,6),(256,10),(256,31),(250,39),(17,39),(11,31),(11,10),(9,6)]],fill='white')
    plate=plate.resize((268,40),Image.Resampling.BOX);a=np.asarray(plate).copy()
    for y in range(40):
        gain=np.interp(y,[0,3,7,20,34,39],[1,.96,.92,1-params['gloss'],.94,.86])
        a[y,:,:3]=round(gain*255)
    cells['plate']=Image.fromarray(a).resize((89,16),Image.Resampling.BOX)
    # Dark outline plus restrained neutral sheen around the white pill.
    housing=rounded(246,62,26,(26,26,26,255));draw=ImageDraw.Draw(housing)
    draw.rounded_rectangle((2,4,243,58),23,outline=(95,95,95,255),width=2)
    draw.rounded_rectangle((5,7,240,55),21,outline=(53,53,53,255),width=2)
    cells['housing']=housing.resize((82,25),Image.Resampling.BOX)
    for name,w,ends in [('capsule',180,'left'),('red',63,'right')]:
        im=rounded(w,40,20,(246,246,246,255),ends);draw=ImageDraw.Draw(im)
        if name=='capsule':
            # Quarter / clock separator follows the full live package.
            draw.line((68,5,68,35),fill=(170,170,170,255),width=1)
        else:draw.line((1,4,1,36),fill=(176,176,176,255),width=1)
        cells[name]=im.resize((w//3,16),Image.Resampling.BOX)
    for row in spec['static']:
        if row['name'] in ('capsule','red'):row['tint']='none'
        if row['name']=='red':row['box']=[1019,999,1082,1039]
        if row['name']=='away_logo':row['box']=[440,943,640,1051]
        if row['name']=='home_logo':row['box']=[1276,943,1476,1051]
    tick=Image.new('RGBA',(72,24),(255,255,255,0));ImageDraw.Draw(tick).polygon([(9,0),(71,0),(62,23),(0,23)],fill='white')
    cells['tick']=tick.resize((6,2),Image.Resampling.BOX)
    flag=rounded(246,36,5,(255,204,0,255));m=traced['flag'].resize((80,24),Image.Resampling.BOX)
    flag.paste((20,20,20,255),((246-80)//2,6,(246+80)//2,30),m)
    cells['flag']=flag.resize((89,16),Image.Resampling.BOX)
    for row in spec['brand']:
        tag=row['variant'];m=Image.open(OUT/f'watermark_{tag}.png').convert('RGBA')
        canvas=Image.new('RGBA',(214,29),(255,255,255,0))
        canvas.paste(m,(3,3) if tag=='mnf' else (21,1))
        coverage=canvas.getchannel('A').resize((71,12),Image.Resampling.BOX)
        cells[row['cell']]=Image.new('RGBA',(71,12),'white')
        cells[row['cell']].putalpha(coverage)
        row['opacity']=.72
        row['source']=dict(frames='full Broncos-Chiefs broadcast' if tag=='mnf' else 'Raiders-Texans highlights',
            method=harvest['watermark_'+tag]['method'],estimated_opacity=.72,colour=[255,255,255],
            samples=harvest['watermark_'+tag]['samples'],report='reports/b72_s9/harvest.json')

    # Every team receives an explicit silhouette-based fit. Only the four
    # live-reference teams can be called measured broadcast fits.
    fits={}
    for name in art.TEAM_LOGOS:
        filename='wsh' if name=='WAS' else name.lower()
        logo=Image.open(ROOT/'data/nfl2k5_scorebug_mnf/logos'/(filename+'.png'))
        x,y,r,b=logo.getchannel('A').getbbox();ratio=(r-x)/(b-y)
        fits[name]=dict(fill_x=1.08 if ratio>1.5 else 1.0,height=.94,zoom=1.0,shift_x=0.,shift_y=0.)
    fits.update(DEN=dict(fill_x=1.29,height=.90,zoom=1.0,shift_x=0.,shift_y=-.015),
        KC=dict(fill_x=1.30,height=1.,zoom=1.,shift_x=0.,shift_y=0.),
        LV=dict(fill_x=1.30,height=1.,zoom=1.10,shift_x=0.,shift_y=-.01),
        HOU=dict(fill_x=1.07,height=1.,zoom=1.19,shift_x=0.,shift_y=0.),
        BUF=dict(fill_x=1.14,height=.93,zoom=1.05,shift_x=0.,shift_y=0.))
    spec['logo_fit']=dict(default=dict(fill_x=1.,height=.94),by_team=fits)
    spec['provenance']=dict(font='Broadcast temporal-median contour traces; reconstructed absent glyphs listed in report',
        font_distributed=False,author='reports/b72_s9/author.py',rendered_once=True,
        brand='Direct measured MNF and NFL masks from supplied live broadcasts',
        team_shapes='Neutral masks and white pill; validated official team tints',
        fidelity_report='reports/b72_s9/FIDELITY.md',revision='b72-s9')
    # A narrow score digit can occur beside two wide digits. Bound every cell
    # by the field's worst complete string, not by three copies of that digit.
    longest={'score':list('888'),'clock':list('60:00'),'small':['4','TH'],'quarter':['4TH'],
             'label':['4','th',' ','&',' ','Inch','es'],'ticks':['~','~','~']}
    footprints={}
    for field in spec['fields']:
        gs=spec['glyph_sets'][field['glyph_set']];glyphs=gs['glyphs'];tokens=longest[field['glyph_set']]
        total=sum(glyphs[t]['advance'] for t in tokens)-glyphs[tokens[-1]]['advance']+glyphs[tokens[-1]]['size'][0]
        factor=field['size']/gs['cap_height']
        compression=min(1,(field['box'][2]-field['box'][0])/(total*factor))
        for g in glyphs.values():
            if not all(g['size']):continue
            size=(max(1,int(g['size'][0]*factor*compression/3)),max(1,int(g['size'][1]*factor*448/1080)))
            previous=footprints.get(g['cell'],size)
            footprints[g['cell']]=tuple(min(a,b) for a,b in zip(size,previous))
    for name,size in footprints.items():
        im=cells[name];cells[name]=im.resize(tuple(min(a,b) for a,b in zip(im.size,size)),Image.Resampling.BOX)
    # Keep the source canvas separate from the bounded runtime packer.
    sheet=Image.new('RGBA',(1536,512),(255,255,255,0));x=y=line=0;spec['cells']={}
    for name,im in cells.items():
        if x+im.width+2>sheet.width:x=0;y+=line+2;line=0
        if y+im.height>sheet.height:raise ValueError('Source sheet capacity exceeded')
        sheet.paste(im,(x,y));spec['cells'][name]=dict(box=[x,y,x+im.width,y+im.height])
        x+=im.width+2;line=max(line,im.height)
    sheet.save(destination/'template.png');write(destination/'layout.json',spec)
    accents=json.loads((source/'team_accents.json').read_text())
    receipt=json.loads((OUT/'accent_call.json').read_text());review=[]
    # Explicit review of the low-confidence choices against observed colours.
    measured={'DEN':'colour1_lighter','KC':'colour0_base','LV':'colour0_darker','HOU':'colour1_base','BUF':'colour0_base'}
    for state,result in zip(receipt['request']['states'],receipt['response']['results']):
        name=state['team'];team=accents['teams'][name]
        for role in ('wing','rim','plate'):
            decision=result['answers'][role]
            if name not in measured:continue
            pick=measured[name]
            if decision['choice']==pick and decision['confidence']>=.8:reason='Jev choice accepted'
            else:reason='Manual reference review: nearest valid family from live evidence; low-confidence or competing Jev choice not auto-applied'
            candidate=team['candidates'][pick]
            assert candidate['contrast_white']>=4.5 and candidate['parent'] in team['official']
            team[role]=candidate['hex'];review.append(dict(team=name,role=role,choice=pick,jev=decision,reason=reason))
        team['wash']=team['wing']
    for name,team in accents['teams'].items():
        # Historical aliases share the native identity and must share colors.
        modern=next((t for t in accents['teams'].values() if t['slot']<32 and t['asset_code']==team['asset_code'] and t['kind']==team['kind']),None)
        if modern and team['slot']>=32:
            for role in ('wing','rim','plate','wash'):team[role]=modern[role]
        if name in fits:team['logo_fit']=fits[name]
    (destination/'team_accents.json').write_text(json.dumps(accents,indent=2)+'\n',encoding='utf-8',newline='\n')
    teams.load(destination/'team_accents.json')
    write(OUT/'art_provenance.json',dict(reconstructed_glyphs=provenance,accent_review=review,
        logo_fits={k:dict(parameters=v,status='fitted against live reference; residuals remain' if k in ('DEN','KC','LV','HOU') else 'inferred; no live team reference') for k,v in fits.items()},
        readability_exceptions=[dict(element='down label',broadcast_cap=23,hud_cap=30*448/1080,authored_cap=30,reason='s3 readability floor'),
            dict(element='quarter',broadcast_cap=19,authored_cap=22,reason='whole-token hinting at nine SD scanlines'),
            dict(element='quarter suffix',broadcast_cap=13,authored_cap=14,reason='six SD scanlines within the hinted quarter token')]))
    print('Authored',destination)


if __name__=='__main__':main()
