"""PROVED OFFLINE: thresholded source geometry and every recognized plate-label footprint."""
from pathlib import Path
import json,sys
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parent))
from measure import region,box,ink,med,SCRATCH,OUT,measure

def bbox_color(a,b,kind):
 p=region(a,b).astype(int);r,g,bl=p[:,:,0],p[:,:,1],p[:,:,2]
 masks={'yellow':(r>150)&(g>150)&(bl<80),'red':(r>140)&(g<70)&(bl<115),'light':p.min(-1)>170,
        'colour':np.ptp(p,axis=-1)>35,'dark':p.max(-1)<32}
 return box(masks[kind],b[:2],min_area=10)

def main():
 a=np.array(Image.open(SCRATCH/'CHI_median.png'))
 out={'classification':'PROVED OFFLINE','coordinates':'half-open 1920x1080; thresholds include antialiasing/compression, not mathematical vector edges'}
 out['bar']=dict(left_rail_edge_cluster=[434,442],right_rail_edge_cluster=[1478,1488],top_rim_edge_cluster=[941,950],bottom_edge_cluster=[1052,1055],evidence='details.json pooled RGB derivative peaks; no single threshold fully describes the beveled edge')
 out['plate_slices']={}
 for kind in ('PHI','CHI','FLAG','ESPN'):
  a=np.array(Image.open(SCRATCH/(kind+'_median.png')))
  out['plate_slices'][kind]=[]
  for y in (948,951,954,967,977,981,984):
   b=(810,y,1110,y+1);p=region(a,b).astype(int)
   mask=p.max(-1)<32 if kind=='ESPN' else np.ptp(p,axis=-1)>35
   cols=np.where(mask[0])[0]
   out['plate_slices'][kind].append(dict(y=y,span=None if not len(cols) else [int(cols.min()+810),int(cols.max()+811)]))
 out['cells']={}
 for name,t in [('white',69),('red',70),('flag',245)]:
  a=np.array(Image.open(SCRATCH/'frames'/f'nfl_{t+1:04d}.png'))
  out['cells'][name]=dict(bin=t,box=bbox_color(a,(1010,995,1090,1045),'red') if name=='red' else bbox_color(a,(810,945,1110,990),'yellow') if name=='flag' else bbox_color(a,(830,995,1090,1045),'light'),
    interior_rgb=med(region(a,(1024,1005,1038,1034))) if name!='flag' else med(region(a,(846,956,880,977))))
 # Observed high-contrast logo ink, excluding rails and record boxes. Silhouette
 # under a record overlay is unobservable; do not claim a complete-vector bbox.
 a=np.array(Image.open(SCRATCH/'CHI_median.png'));out['logo_visible_ink']={}
 for team,b in [('PHI',(450,946,655,1050)),('CHI',(1275,946,1465,1050))]:
  p=region(a,b).astype(int);mask=(p.min(-1)>140)&(np.ptp(p,axis=-1)<45)
  yy,xx=np.indices(mask.shape);xx+=b[0];yy+=b[1]
  mask[(yy>=1022)&((xx<492) if team=='PHI' else (xx>1430))]=False
  out['logo_visible_ink'][team]=dict(box=box(mask,b[:2],min_area=10),method='neutral ink >140; y946:1050; record overlay excluded; a lower bound on full silhouette')
 inventory=json.loads((OUT/'inventory.json').read_text())['states'];rows=[]
 for st in inventory:
  if st['plate']=='transition':continue
  times=st['times'];t=times[len(times)//2];a=np.array(Image.open(SCRATCH/'frames'/f'nfl_{t+1:04d}.png'))
  rows.append(dict(plate=st['plate'],label=st['label'],count=st['count'],sample_bin=t,ink=ink(a,(844,953,1078,983),st['plate']=='FLAG'),plate_rgb=measure(a)['plate_rgb']))
 out['all_labels']=rows
 # Second encode: compare the 720p snippet over its first ten settled seconds.
 second=[]
 for t in range(10):
  a=Image.new('RGB',(1280,720));a.paste(Image.open(SCRATCH/'frames'/f'espn_{t+1:04d}.png'),(264,546))
  a=np.array(a.resize((1920,1080),Image.Resampling.BILINEAR))[820:1060,400:1500]
  second.append(measure(a))
 out['espn_720_crosscheck']=dict(bins=list(range(10)),plate_rgb=np.median([r['plate_rgb'] for r in second],axis=0).tolist(),wing={k:np.median([r['wing'][k] for r in second],axis=0).tolist() for k in ('PHI','CHI')},method='720p source inserted at its crop origin, scaled 1.5x with bilinear filter; no full-HD edge claim')
 (OUT/'geometry.json').write_text(json.dumps(out,indent=2)+'\n');print({k:v for k,v in out.items() if k not in ('all_labels','plate_slices')})
if __name__=='__main__':main()
