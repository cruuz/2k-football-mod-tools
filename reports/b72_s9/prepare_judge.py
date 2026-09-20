"""s3 screenshot judge and rubric, with measured dark play-clock ink."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
from PIL import Image

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT))
from tools.scorebug_sprite.jev import descriptors as D,judge,rubric
p=argparse.ArgumentParser();p.add_argument('broadcast',type=Path);p.add_argument('raiders',type=Path);a=p.parse_args()

def desc(path):
    im=Image.open(path).convert('RGB');d=D.describe(im)
    # s3's descriptor assumes white play-clock ink. Live normal ESPN uses
    # dark ink on white. Keep this correction local to the evidence adapter.
    x,y,r,b=D.BOXES['play_clock'];v=np.asarray(im.crop((x,y,r,b)),dtype=float);m=v.max(2)<100
    yy,xx=np.where(m);lum=D.rgb_luma(v)
    d['fields']['play_clock'].update(ink_pixels=int(m.sum()),core_luma=round(float(np.percentile(lum[m],75)),2) if len(xx) else 0.,
        ink_box=[int(xx.min()+x),int(yy.min()+y),int(xx.max()+x+1),int(yy.max()+y+1)] if len(xx) else None)
    return d

states=[];design=[];facts=[]
for match,path in [('LV_HOU',a.raiders/'frames/frame_005000.jpg'),('DEN_KC',a.broadcast/'frames_1s/s_00724.jpg')]:
    for aspect in ('169','43'):
        wanted=desc(path);ours=desc(OUT/(match+'_measured_'+aspect+'.png'))
        q=judge.request(judge.differences(wanted,ours),native_evidence=dict(
            evidence='Offline native CPU/GPU model, not live game. No screenshot calibration.',
            known_limits='Network mark is pinned inward by HUD clipping. Own-palette gray is darker than Raiders broadcast. Label cap raised for readability. Fixed ROIs can contain logos.',
            play_clock='Dark normal ink on white pill, explicitly measured by adapter.'))
        q['state']['case']=match+'_'+aspect;states.append(q['state'])
        r=rubric.request(ours,calibration_verified=False,identity_verified=True,overlap_verified=True)
        r['state']['readable']['play_clock']=ours['fields']['play_clock']['ink_pixels']>0
        r['state']['case']=match+'_'+aspect;r['state']['limitations']='Identity uses official palette, not exact broadcast RGB. All results offline.'
        design.append(r['state']);facts.append(dict(case=match+'_'+aspect,reference=wanted,proposal=ours))
for name,request in [('screenshot',dict(states=states,questions=q['questions'])),
                     ('rubric',dict(states=design,questions=dict(design=dict(type='score',instructions=r['instructions'],criteria=r['levels'])))),
                     ('screenshot_descriptors',facts)]:
    (OUT/(name+'_request.json')).write_text(json.dumps(request,indent=2)+'\n')
print('Prepared four screenshot comparisons and four design rubric states')
