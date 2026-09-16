"""Draw numeric model swatches; this is not an in-game render."""
from pathlib import Path
import json
import os

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.scratch/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

proof=json.loads((ROOT/'reports/b71_c4/daylight-proof.json').read_text())
rigs={r['name']:r for r in proof['rigs']}
fig,ax=plt.subplots(figsize=(11,6.2),dpi=160)
fig.patch.set_facecolor('#f3f4f1');ax.set_facecolor('#f3f4f1')
ax.set_xlim(0,11);ax.set_ylim(0,6.2);ax.axis('off')
ax.text(.15,5.9,'Broadcast daylight tuning',fontsize=19,weight='bold')
ax.text(.15,5.52,'Calibrated turf mean from colour map (181, 216, 102)',fontsize=10,color='#444444')
for j,t in enumerate(['Before (v2.1)','After (C4)','Broadcast reference']):
    ax.text(2.4+j*2.8,5.05,t,fontsize=11,weight='bold')
for y,name,label in [(3.62,'day','Day'),(2.16,'afternoon','Afternoon'),(.70,'night_indoor','Night / dome')]:
    row=rigs[name]
    ax.text(.15,y+.76,label,fontsize=12,weight='bold')
    for j,key in enumerate(['prediction_before','prediction_after','reference']):
        rgb=row[key];x=2.4+j*2.8
        ax.add_patch(Rectangle((x,y+.26),2.5,.85,color=[v/255 for v in rgb]))
        ax.text(x+.08,y+.62,', '.join(map(str,rgb)),fontsize=11,color='white')
    hs=row['hsv']
    ax.text(.15,y+.38,f"After S {hs['saturation']:.3f}\nV {hs['value']:.3f}",fontsize=10,color='#444444')
ax.text(.15,.10,'PREDICTED, not a game screenshot. Afternoon is extrapolated and intentionally below the reference brightness.',fontsize=9,color='#444444')
fig.tight_layout(pad=.5)
fig.savefig(ROOT/'reports/b71_c4/predicted-swatches.png')
print('Saved model-only swatches')
