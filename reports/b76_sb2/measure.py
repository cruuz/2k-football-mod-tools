"""PROVED OFFLINE: reproduce SB2 measurements from local, read-only video.

Run under taskset -c 24-31, OPENBLAS_NUM_THREADS=1, OMP_THREAD_LIMIT=1.
Coordinates are half-open source 1920x1080 pixels. PNG crops retain x=400,y=820.
ffmpeg fps=1 selects a representative in each one-second output bin. Times are
bin times, not exact source frame PTS. No measurement comes from the sheet view.
"""
from pathlib import Path
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, label, find_objects

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
SCRATCH=Path('/media/noah/Storage/.b76-research/sb/sb2')
X,Y=400,820

def region(a,box):
    x0,y0,x1,y1=box
    return a[y0-Y:y1-Y,x0-X:x1-X]

def med(a):return np.median(a.reshape(-1,3),axis=0).round(2).tolist()
def box(mask,origin=(0,0),min_area=3):
    ids,n=label(mask); keep=np.zeros(mask.shape,bool)
    for i,s in enumerate(find_objects(ids),1):
        if s is not None and (ids[s]==i).sum()>=min_area:keep[s]|=ids[s]==i
    yy,xx=np.where(keep)
    return None if not len(xx) else [int(xx.min()+origin[0]),int(yy.min()+origin[1]),int(xx.max()+origin[0]+1),int(yy.max()+origin[1]+1)]

def ink(a,b,dark=False,threshold=160):
    p=region(a,b)
    mask=p.max(-1)<80 if dark else p.min(-1)>threshold
    return dict(box=box(mask,b[:2]),pixels=int(mask.sum()))

def measure(a):
    pill=region(a,(850,1005,1010,1030)).mean()
    tray=region(a,(800,996,823,1040)).mean()
    present=bool(pill>145 and tray<85)
    p=region(a,(845,953,1075,979)).astype(float)
    keep=~binary_dilation(p.min(-1)>150,iterations=2)
    plate=np.median(p[keep],axis=0) if keep.any() else np.zeros(3)
    r,g,b=plate
    typ='FLAG' if r>120 and g>120 and b<70 else 'ESPN' if max(plate)<42 else 'CHI' if r>g*1.6 and r>b*1.6 else 'PHI' if g>r*1.4 and b>r*1.4 else 'transition'
    c={s:float(region(a,bb).mean()) for s,bb in {'away':(740,948,770,955),'home':(1145,948,1175,955)}.items()}
    return dict(present=present,plate_kind=typ,plate_rgb=plate.round(2).tolist(),chevrons=c,
      wing={s:med(region(a,bx)) for s,bx in {'PHI':(442,975,454,1020),'CHI':(1466,975,1478,1020)}.items()},
      red=bool((region(a,(1024,1006,1036,1030)).mean((0,1))*[1,-1,0]).sum()>100))

def plate_ocr(im,row):
    a=np.array(im.crop((844-X,953-Y,1078-X,983-Y)))
    mask=a.max(-1)<85 if row['plate_kind']=='FLAG' else a.min(-1)>160
    return Image.fromarray(np.where(mask,0,255).astype('uint8')).convert('RGB')

def ocr(rows):
    """OCR stacked plate crops; preserve the row index using TSV line boxes."""
    for start in range(0,len(rows),80):
        group=rows[start:start+80]; page=Image.new('RGB',(600,100*len(group)),'#ffffff')
        for j,row in enumerate(group):
            im=Image.open(SCRATCH/'frames'/row['frame'])
            page.paste(plate_ocr(im,row).resize((544,84)),(28,j*100+8))
        path=SCRATCH/'ocr_page.png';page.save(path)
        p=subprocess.run(['tesseract',str(path),'stdout','--psm','6','tsv'],capture_output=True,text=True,env=dict(os.environ,OMP_THREAD_LIMIT='1'),check=True)
        by={i:[] for i in range(len(group))}
        for w in csv.DictReader(io.StringIO(p.stdout),delimiter='\t'):
            if w.get('text','').strip() and float(w['conf'])>=0:
                i=min(len(group)-1,(int(w['top'])+int(w['height'])//2)//100)
                by[i].append(w['text'])
        for i,row in enumerate(group):row['ocr']=' '.join(by[i])
        print('OCR',start+len(group),'/',len(rows),flush=True)

def main():
    rows=[]
    for p in sorted((SCRATCH/'frames').glob('nfl_*.png')):
        a=np.array(Image.open(p).convert('RGB')); m=measure(a)
        rows.append(dict(frame=p.name,t=int(p.stem.split('_')[1])-1,**m))
    accepted=[r for r in rows if r['present']]
    ocr(accepted)
    (OUT/'scan.json').write_text(json.dumps(dict(classification='PROVED OFFLINE',rows=rows),indent=1)+'\n')
    summary={}
    for kind in ('PHI','CHI','ESPN','FLAG'):
        rr=[r for r in accepted if r['plate_kind']==kind]
        if not rr:continue
        summary[kind]=dict(count=len(rr),plate_rgb=np.median([r['plate_rgb'] for r in rr],axis=0).tolist(),
          labels=sorted(set(r['ocr'] for r in rr)), examples=[r['t'] for r in rr[::max(1,len(rr)//10)]])
        use=rr[::max(1,len(rr)//50)][:60]
        composite=np.median(np.stack([np.array(Image.open(SCRATCH/'frames'/r['frame'])) for r in use]),axis=0).astype('uint8')
        Image.fromarray(composite).save(SCRATCH/(kind+'_median.png'))
        profiles={s:region(composite,b).mean(1).round(2).tolist() for s,b in {'PHI':(442,940,454,1056),'CHI':(1466,940,1478,1056)}.items()}
        summary[kind]['wing_row_profiles']=profiles
    (OUT/'measurements.json').write_text(json.dumps(dict(classification='PROVED OFFLINE',coordinates='half-open 1920x1080 source pixels',source_crop=[400,820,1500,1060],frames=len(rows),accepted=len(accepted),states=summary),indent=1)+'\n')
    print({k:{p:v[p] for p in ('count','plate_rgb','labels')} for k,v in summary.items()})

if __name__=='__main__':main()
