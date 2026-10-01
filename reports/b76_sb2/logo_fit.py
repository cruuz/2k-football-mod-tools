"""DESIGN: fit the existing official mark's horizontal extent/position to neutral ink, without generating art."""
from pathlib import Path
import json,sys
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT)]
from mod_editor.core import nfl2k5_scorebug_exact as exact
OUT=Path(__file__).resolve().parent;S=Path('/media/noah/Storage/.b76-research/sb/sb2')
a=np.array(Image.open(S/'CHI_median.png'))
results={}
for team,x0 in [('PHI',437),('CHI',1248)]:
    observed=a[948-820:1048-820,x0-400:x0-400+230].astype(int)
    mask=(observed.min(-1)>145)&(np.ptp(observed,axis=-1)<45) if team=='PHI' else (observed[:,:,2]>observed[:,:,0]+8)&(observed[:,:,2]>observed[:,:,1]+5)&(observed.max(-1)<90)
    mask[:,:12]=False;mask[:,-12:]=False
    scores=[]
    for width in np.arange(.8,1.301,.02):
      for shift in range(-4,7):
        fit=dict(fill_x=round(float(width),2),height=1.,zoom=.976,shift_x=shift/64,shift_y=0.)
        im=exact.mnf_panel(team,'home',fit=fit).resize((230,110),Image.Resampling.BILINEAR)
        p=np.array(im)[6:106].astype(float);alpha=p[:,:,3]/255
        rgb=p[:,:,:3]*alpha[:,:,None]+37*(1-alpha[:,:,None])
        predicted=(rgb.min(-1)>145)&(np.ptp(rgb,axis=-1)<45) if team=='PHI' else (rgb[:,:,2]>rgb[:,:,0]+8)&(rgb[:,:,2]>rgb[:,:,1]+5)&(rgb.max(-1)<90)
        predicted[:,:12]=False;predicted[:,-12:]=False
        intersect=(predicted&mask).sum();union=(predicted|mask).sum()
        scores.append(dict(fit=fit,iou=round(float(intersect/union),6)))
    scores.sort(key=lambda r:-r['iou']);base=next(r for r in scores if r['fit']['fill_x']==.92 and r['fit']['shift_x']==0)
    results[team]=dict(before=base,after=scores[0],top5=scores[:5],mask_pixels=int(mask.sum()))
(OUT/'logo_fit.json').write_text(json.dumps(dict(classification='DESIGN',method='grid search over official logo width and translation; PHI neutral ink / CHI navy ink IoU in source y948:1048, cropped 12 px at wing ends to remove rails',teams=results),indent=2)+'\n');print(results)
