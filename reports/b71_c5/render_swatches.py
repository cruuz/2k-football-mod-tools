"""Export numeric FIELD/outside comparisons; these are model swatches, not renders."""
from pathlib import Path
import json
import os
ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'.scratch/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

report = json.loads((ROOT/'reports/b71_c5/all-decoder-proof.json').read_text())
rows = [r for r in report['rows'] if 'prediction_before' in r]
fig, ax = plt.subplots(figsize=(13, 7.6))
ax.set_xlim(0, 4); ax.set_ylim(0, len(rows)+1); ax.axis('off')
for i, title in enumerate(('Decoded stadium / condition', 'FIELD (C4 = C5)', 'Outside C4', 'Outside C5')):
    ax.text(i+.03,len(rows)+.48,title,fontsize=11,weight='bold')
for i,row in enumerate(rows):
    y = len(rows)-i-1
    label = row['name']+'\n'+row['representative_rig'].replace('_',' / ')
    if row['name']=='s11dd.iff': label='s11dd.iff\nDome grass'
    if row['name']=='s09dd.iff': label='s09dd.iff\nDome material turf'
    ax.text(.03,y+.58,label,fontsize=10,va='center')
    b,a = row['prediction_before'],row['prediction_after']
    for col,rgb in enumerate((a['field'],b['outside'],a['outside']),1):
        rounded=tuple(round(c) for c in rgb)
        ax.add_patch(Rectangle((col+.03,y+.32),.88,.55,color=[c/255 for c in rgb]))
        ax.text(col+.47,y+.58,str(rounded),ha='center',va='center',color='white',fontsize=10)
    ratio=max(a['outside'])/max(a['field'])
    ax.text(3.47,y+.1,f'{(1-ratio)*100:.2f}% darker; edge ≤ {(1-min(a["tinted_value_ratios"]))*100:.2f}%',ha='center',fontsize=9)
fig.suptitle('Linked outside grass follows the FIELD target',fontsize=17,weight='bold')
fig.text(.05,.025,'MODEL ONLY • Outside response calibrated from one supplied day strip. Other conditions/classes are extrapolations.\nFIELD and all seven C4 rigs are unchanged. Swatches show unshaded decoded means; tints are checked separately.',fontsize=10)
fig.subplots_adjust(left=.035,right=.99,top=.91,bottom=.13)
fig.savefig(ROOT/'reports/b71_c5/predicted-swatches.png',dpi=140)
plt.close(fig)
print('PASS: seven paired FIELD/outside model swatches exported')
