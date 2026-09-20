"""Pixels to measured text. Jev receives only the compact result of compact()."""
from functools import lru_cache
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]

BOXES = dict(away_score=[696,955,816,1024], home_score=[1100,955,1220,1024],
             clock=[915,1003,1009,1036], quarter=[844,1003,897,1036],
             play_clock=[1023,1003,1077,1036], down=[835,950,1085,985],
             plate=[825,947,1093,987], away_wing=[437,950,464,1038],
             home_wing=[1450,950,1478,1038], away_rim=[690,942,810,951],
             home_rim=[1110,942,1235,951], away_timeouts=[710,1028,804,1042],
             home_timeouts=[1114,1028,1208,1042], network=[1655,35,1869,64])
STATES = ('normal','kickoff','first_and_ten','short_yardage','third_and_long',
          'fourth_down','red_zone','goal_to_go','touchdown_banner','field_goal_banner',
          'flag','timeout','two_minute','replay_or_network_bug','end_of_quarter','absent','other')


def rgb_luma(a):
    return a[...,0]*.2126+a[...,1]*.7152+a[...,2]*.0722


def relative_luminance(rgb):
    import numpy as np
    c=np.asarray(rgb,dtype=float)/255
    c=np.where(c<=.04045,c/12.92,((c+.055)/1.055)**2.4)
    return float(c @ [.2126,.7152,.0722])


def contrast(a,b=(255,255,255)):
    x,y=sorted([relative_luminance(a),relative_luminance(b)])
    return (y+.05)/(x+.05)


def hue_name(rgb):
    import colorsys
    h,s,v=colorsys.rgb_to_hsv(*(float(c)/255 for c in rgb))
    if s<.16:return 'neutral'
    return ('red','orange','yellow','green','cyan','blue','purple','pink')[int(h*8)%8]


@lru_cache(maxsize=1)
def templates():
    import numpy as np
    from PIL import Image
    folder=ROOT/'data/nfl2k5_scorebug_mnf'
    image=Image.open(folder/'espn_glyphs.png').convert('L')
    spec=json.loads((folder/'espn_glyphs.json').read_text())
    return {token:np.asarray(image.crop(row['box']))>110 for token,row in spec.items()}


def read_tokens(mask):
    """Column segmentation, normalized binary overlap with ESPN's own glyphs.

    Returns uncertainty rather than inventing text when a connected word or
    transition cannot be segmented. No general OCR or model sees the image.
    """
    import numpy as np
    from PIL import Image
    ink=np.flatnonzero(mask.any(0));out=[];errors=[]
    if not len(ink):return dict(text='',certain=False,error=1.)
    groups=np.split(ink,np.flatnonzero(np.diff(ink)>1)+1)
    for xs in groups:
        part=mask[:,xs[0]:xs[-1]+1];ys=np.flatnonzero(part.any(1))
        if not len(ys) or part.sum()<3:continue
        part=part[ys[0]:ys[-1]+1]
        ranked=[]
        for token,t in templates().items():
            resized=np.asarray(Image.fromarray(part).resize((t.shape[1],t.shape[0]),Image.Resampling.NEAREST),dtype=bool)
            overlap=(resized&t).sum()/max(1,(resized|t).sum())
            ratio=abs(part.shape[1]/part.shape[0]-t.shape[1]/t.shape[0])
            ranked.append((1-overlap+min(.5,ratio)*.3,token))
        error,token=min(ranked);out.append(token if error<.55 else '?');errors.append(error)
    error=float(np.mean(errors)) if errors else 1.
    return dict(text=''.join(out),certain=bool(out) and '?' not in out and error<.32,error=round(error,4))


def describe(image, *, aspect='16:9', light_clock=False):
    import numpy as np
    from PIL import Image
    source=Image.open(image).convert('RGB') if isinstance(image,(str,Path)) else image.convert('RGB')
    # The bar has fixed broadcast dimensions at both aspects, centered.
    width=1920 if aspect=='16:9' else 1440
    scaled=source.resize((width,1080),Image.Resampling.BILINEAR)
    offset=(width-1920)//2
    fields={}
    for name,box in BOXES.items():
        b=[box[0]+offset,box[1],box[2]+offset,box[3]]
        a=np.asarray(scaled.crop(b),dtype=float);lum=rgb_luma(a)
        ink=(a.min(-1)>175)&(a.max(-1)-a.min(-1)<65)
        if name in ('clock','quarter') and not light_clock:ink=a.max(-1)<100
        ys,xs=np.where(ink)
        field=dict(box=b,luma=[round(float(lum.min()),2),round(float(np.median(lum)),2),round(float(lum.max()),2)],
                   rgb=[round(float(v),2) for v in np.median(a.reshape(-1,3),axis=0)],
                   ink_pixels=int(ink.sum()),ink_box=([int(xs.min()+b[0]),int(ys.min()+b[1]),int(xs.max()+b[0]+1),int(ys.max()+b[1]+1)] if len(xs) else None),
                   core_luma=round(float(np.percentile(lum[ink],75)),2) if len(xs) else 0.,
                   ink_style='dark' if name in ('clock','quarter') and not light_clock else 'light')
        if name in ('down','clock','quarter','away_score','home_score','play_clock'):
            field['ocr']=read_tokens(ink)
        fields[name]=field
    # Stable bar samples exclude glyphs and logos. Absence is a measured
    # predicate, not inferred merely because a template returned no tokens.
    body=np.asarray(scaled.crop((1218+offset,994,1238+offset,1025)))
    dark_fraction=float((rgb_luma(body)<75).mean())
    present=dark_fraction>.80 and fields['away_score']['ink_pixels']>20 and fields['home_score']['ink_pixels']>20
    label=fields['down']['ocr'];text=label['text']
    goal='GOAL' in text.upper(); match=re.search(r'([1-4])(?:st|nd|rd|th)?&([0-9]+)',text,re.I)
    down=int(match.group(1)) if match and label['certain'] else None
    distance=int(match.group(2)) if match and label['certain'] else None
    normal_label=label['certain'] and (match is not None or goal or 'Down' in text)
    return dict(schema='scorebug-descriptor/v1',source_size=list(source.size),aspect=aspect,
                present=present,fields=fields,readback=dict(text=text,down=down,distance=distance,goal=goal,
                certainty='confident' if label['certain'] else 'uncertain'),
                banners=dict(flag=bool(np.mean((np.asarray(scaled.crop((825+offset,947,1093+offset,987)))[:,:,:2]>150).all(-1))>.7),
                             touchdown=False if normal_label else 'unresolved',field_goal=False if normal_label else 'unresolved',network=False if normal_label else 'unresolved'),
                limitations=['Template matching can reject connected text and transitions.','Red zone needs field position evidence.'])


def compact(d):
    fields=d['fields']; r=d['readback'];distance=r['distance'];down=r['down']
    return dict(id=d.get('frame'),bar='present' if d['present'] else 'absent',label=r['text'],
                label_readback=r['certainty'],down=('first','second','third','fourth')[down-1] if down else 'unknown',
                distance='unknown' if distance is None else 'short' if distance<=2 else 'ten' if distance==10 else 'long' if distance>=7 else 'medium',
                goal_word=r['goal'],banners=d['banners'],
                fields={k:dict(visible=bool(v['ink_pixels']),core='readable' if v['core_luma']>=200 else 'dim',
                    hue=hue_name(v['rgb'])) for k,v in fields.items() if k in ('down','away_score','home_score','plate')},
                clock=dict(visible=bool(fields['clock']['ink_pixels']),ink=fields['clock'].get('ink_style','dark')))
