"""Read-only broadcast measurement and glyph tracing for the s9 art revision.

No font engine or font file is used. Inputs are the supplied broadcast crops
and their code/OCR labels. Traces, sample identities and rejected reads remain
in the report so uncertain reconstruction is not disguised as a measurement.
"""
from pathlib import Path
import argparse
from collections import defaultdict, Counter
import hashlib
import json
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
BOXES = dict(scoreA=(700,958,820,1024), scoreH=(1100,958,1220,1024),
             clock=(906,1002,1014,1034), small=(1022,1004,1076,1031),
             label=(840,950,1080,984), quarter=(846,1003,902,1033))


def write(path, data):
    path.write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8', newline='\n')


def pieces(mask, minimum=3):
    columns = np.flatnonzero(mask.any(0))
    if not len(columns):
        return []
    groups = np.split(columns, np.flatnonzero(np.diff(columns)>1)+1)
    result = []
    for xs in groups:
        ys = np.flatnonzero(mask[:,xs].any(1))
        box = (int(xs[0]), int(ys[0]), int(xs[-1]+1), int(ys[-1]+1))
        if box[3]-box[1]>=minimum and box[2]-box[0]>=2:
            result.append(box)
    return result


def trace(samples):
    # Alignment by ink box precedes temporal median. Separate glyphs are
    # never averaged in their original, shifting screen positions.
    shapes = [s[0].shape for s in samples]
    height = int(np.median([s[0] for s in shapes]))
    width = int(np.median([s[1] for s in shapes]))
    aligned = [cv2.resize(s[0], (width*4,height*4), interpolation=cv2.INTER_LINEAR)
               for s in samples]
    median = np.median(aligned, axis=0).astype('uint8')
    contours, hierarchy = cv2.findContours((median>=128).astype('uint8'), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    canvas = np.zeros_like(median)
    # Even-odd fill keeps counters in 0, 6, 8, 9 and the ampersand.
    cv2.drawContours(canvas, contours, -1, 255, cv2.FILLED, hierarchy=hierarchy)
    return Image.fromarray(canvas), dict(width=width, height=height, samples=len(samples),
        contours=[c.reshape(-1,2).tolist() for c in contours],
        hierarchy=hierarchy.tolist() if hierarchy is not None else [],
        sources=[s[1] for s in samples])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('broadcast',type=Path)
    parser.add_argument('raiders',type=Path)
    args=parser.parse_args()
    glyphs=defaultdict(list);reject=Counter();medians=defaultdict(list);wm=[]
    seconds=[json.loads(l) for l in (args.broadcast/'grammar/seconds.jsonl').read_text().splitlines()]
    selected=[d for d in seconds if d['layout']=='full_bar' and d['settled'] and not d['banner']]
    corpus=[]
    for d in selected:
        t=d['t']
        if t%3:
            continue
        path=args.broadcast/'crops'/f'bar_{t:05d}.png'
        a=np.asarray(Image.open(path).convert('RGB'))
        if d['plate']=='FLAG' and len(glyphs['flag'])<100:
            crop=a[20:54,405:645,:3]
            mask=crop.max(2)<105
            bs=pieces(mask,12)
            if len(bs)==4 and bs[0][0]>5 and bs[-1][2]<235:
                x,y,r,b=min(bb[0] for bb in bs),min(bb[1] for bb in bs),max(bb[2] for bb in bs),max(bb[3] for bb in bs)
                glyphs['flag'].append((mask[y:b,x:r].astype('uint8')*255,dict(t=t,crop=path.name,box=[840+x,950+y,840+r,950+b])))
        if d['kind']=='down_distance' and len(medians[d['possS']])<100:
            medians[d['possS']].append(a)
        used=False
        for role,box in BOXES.items():
            x,y,r,b=box;crop=a[y-930:b-930,x-435:r-435]
            if role.startswith('score'):
                value=d['sA' if role=='scoreA' else 'sH'];group='score'
                mask=crop.min(2)>160;minimum=32
            elif role=='clock':
                value=d['clock'];group='clock';minimum=16
                value=None if value is None else f'{value//60}:{value%60:02d}'
                mask=crop.max(2)<110
            elif role=='small':
                value=d['pc'];group='small';minimum=15
                if d['pc_red']:
                    continue
                mask=crop.max(2)<110
            elif role=='quarter':
                q=d['qS'];value=None if q not in (1,2,3,4) else str(q)+('ST','ND','RD','TH')[q-1]
                group='quarter';minimum=8;mask=crop.max(2)<110
            else:
                value=d['plate'] if re.fullmatch(r'[1-4](st|nd|rd|th) & (\d+|GOAL)',d['plate']) else None
                group='label';minimum=11;mask=crop.min(2)>170
            if value is None:
                continue
            text=str(value).replace(' ','')
            if group=='clock':
                text=text.replace(':','')
            bs=pieces(mask,minimum)
            # Discard plate edges and a separator intersecting the crop.
            bs=[bb for bb in bs if bb[0]>0 and bb[2]<crop.shape[1] and bb[3]-bb[1]<crop.shape[0]]
            if group=='clock':
                bs=[bb for bb in bs if bb[2]-bb[0]>8 or bb[3]-bb[1]>22]
            if group=='label' and text.endswith('GOAL') and len(bs)>=5:
                # The capital word often touches after video compression.
                # Its first four components are down, ordinal pair and &.
                tail=bs[4:]
                bs=bs[:4]+[(min(b[0] for b in tail),min(b[1] for b in tail),
                            max(b[2] for b in tail),max(b[3] for b in tail))]
                text=list(text[:4])+['GOAL']
            if len(bs)!=len(text):
                reject[group]+=1;continue
            for ch,bb in zip(text,bs):
                key=group+'_'+ch
                if len(glyphs[key])>=100:
                    continue
                xx,yy,rr,bbot=bb
                alpha=mask[yy:bbot,xx:rr].astype('uint8')*255
                glyphs[key].append((alpha,dict(t=t,box=[x+xx,y+yy,x+rr,y+bbot],
                    crop=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),read=str(value))))
                used=True
            if group=='clock':
                dots=pieces(mask,3)
                for bb in dots:
                    xx,yy,rr,bbot=bb
                    if 3<=rr-xx<=8 and 10<=bbot-yy<=25 and len(glyphs['clock_:'])<100:
                        glyphs['clock_:'].append((mask[yy:bbot,xx:rr].astype('uint8')*255,
                            dict(t=t,box=[x+xx,y+yy,x+rr,y+bbot],crop=path.name)))
        if used:corpus.append(t)
    folder=OUT/'glyphs';folder.mkdir(exist_ok=True)
    metrics={}
    for name,samples in sorted(glyphs.items()):
        im,row=trace(samples)
        filename=name.replace(':','colon').replace('&','amp')+'.png'
        im.save(folder/filename);row['file']=filename;metrics[name]=row
    for name,arrays in medians.items():
        Image.fromarray(np.median(arrays,axis=0).astype('uint8')).save(OUT/f'broadcast_{name}_median.png')
    # Stable corner marks: temporal median of the lower envelope across
    # disjoint windows removes moving footage while retaining the letterforms.
    for tag,base,pattern in [('mnf',args.broadcast,'wm_{:05d}.png'),('nfl',args.raiders,'wm_{:06d}.png')]:
        paths=sorted((base/'crops').glob('wm_*.png'))
        if tag=='mnf':
            visible={d['t'] for d in seconds if d['wm'] and d['settled']}
            paths=[p for p in paths if int(p.stem.split('_')[1]) in visible]
        arrays=[np.asarray(Image.open(p).convert('RGB')) for p in paths[::max(1,len(paths)//600)]]
        low=np.percentile(arrays,5,axis=0)
        grey=low.mean(2)
        mask=grey>80
        n,labels,stats,_=cv2.connectedComponentsWithStats(mask.astype('uint8'))
        valid=np.zeros(mask.shape,bool)
        for _,(x,y,w,h,area) in enumerate(stats[1:],1):
            if h>=10 and area>=18:valid[labels==_]=True
        ys,xs=np.where(valid)
        if not len(xs):
            raise ValueError('No stable watermark for '+tag)
        box=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]
        x,y,r,b=box;alpha=np.clip((grey[y:b,x:r]-8)/(.72*255),0,1)
        # Remove background islands outside the established connected marks.
        expanded=cv2.dilate(valid.astype('uint8'),np.ones((3,3),np.uint8))
        alpha*=expanded[y:b,x:r]
        mark=Image.new('RGBA',(r-x,b-y),'white');mark.putalpha(Image.fromarray(np.rint(alpha*255).astype('uint8')))
        mark.save(OUT/f'watermark_{tag}.png')
        metrics['watermark_'+tag]=dict(box_in_crop=box,crop_size=list(arrays[0].shape[:2]),samples=len(arrays),
            method='5th percentile luminance, connected static letterforms; alpha normalized by measured 0.72 opacity',
            opacity=.72,source_files=[p.name for p in paths[::max(1,len(paths)//600)]])
    write(OUT/'harvest.json',dict(glyphs=metrics,rejected=dict(reject),seconds=corpus,
        method='Settled full-bar seconds at 3-second stride; segmentation count agrees with supplied OCR/code labels; aligned binary masks, temporal median, contour trace at 4x.'))
    print('Harvested', {k:v['samples'] for k,v in metrics.items()},flush=True)


if __name__=='__main__':main()
