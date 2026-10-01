"""PROVED OFFLINE: numeric edge profiles, text ink and logo contrast boxes."""
from pathlib import Path
import json,sys
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import label,find_objects
sys.path.insert(0,str(Path(__file__).resolve().parent))
from measure import region,ink,box,med,SCRATCH,OUT

STATES=[('chi_interim',28),('chi_first10',41),('phi_first10',113),('fourth1_red5',70),('third16',144),('flag',245),('chi_goal',270),('phi_goal',510),('tags',188),('espn',194),('red2',530),('under_minute',230)]

def biggest(mask,origin):
 ids,n=label(mask);area=np.bincount(ids.ravel());area[0]=0
 return box(ids==area.argmax(),origin) if n else None

def boundaries(a):
 out={}
 # Derivative edge positions from pooled strips, no visually assigned endpoint.
 for name,b,axis in [('bar_top_bottom',(800,920,820,1060),1),('left_rail',(420,980,465,1020),0),('right_rail',(1460,980,1500,1020),0),('plate_x',(810,964,1110,970),0),('pill_x',(820,1015,1095,1020),0)]:
  p=region(a,b).astype(float);v=np.median(p,axis=axis);d=np.linalg.norm(np.diff(v,axis=0),axis=1)
  start=b[1] if axis==1 else b[0];order=np.argsort(d)[-8:][::-1]
  out[name]=dict(strip=b,derivative_peaks=[dict(coordinate=int(i+start+1),rgb_jump=round(float(d[i]),2)) for i in order])
 return out

def main():
 output={'classification':'PROVED OFFLINE','method':'thresholded connected ink components; source pixels, half-open boxes; largest RGB derivative peaks from independent pooled strips','states':{}}
 sheet=Image.new('RGB',(2200,280*((len(STATES)+1)//2)),'#222222');draw=ImageDraw.Draw(sheet)
 for i,(name,t) in enumerate(STATES):
  a=np.array(Image.open(SCRATCH/'frames'/f'nfl_{t+1:04d}.png'))
  record={'bin_time':t,'label':ink(a,(844,953,1078,983),name=='flag'), 'plate_colour':med(region(a,(846,956,880,977))),
    'game_clock':ink(a,(905,1003,1014,1037),True),'play_clock':ink(a,(1030,1004,1070,1035),not name.startswith(('fourth1_red','red'))),
    'quarter':ink(a,(843,1004,899,1034),True),'red_cell_sample':med(region(a,(1023,1007,1034,1028))),
    'edges':boundaries(a)}
  output['states'][name]=record
  x=i%2*1100;y=i//2*280;sheet.paste(Image.fromarray(a),(x,y+30));draw.text((x+5,y+8),f'PROVED OFFLINE {name} / NFL bin {t}s',fill='white')
 # Static geometry from 50-60 frame median: robust to background and compression.
 a=np.array(Image.open(SCRATCH/'CHI_median.png'))
 output['geometry']=boundaries(a)
 output['logos']={}
 for team,b in [('PHI',(457,944,653,1051)),('CHI',(1280,944,1460,1051))]:
  p=region(a,b);mask=(p.min(-1)>140)&(p.max(-1)-p.min(-1)<55)
  output['logos'][team]=dict(threshold='min RGB >140 and chroma <55; component union; includes rail contamination, use geometry.json for the refined box',contrast_ink_box=box(mask,b[:2],min_area=10))
 output['wings']={}
 for team,xo,xi in [('PHI',442,660),('CHI',1466,1260)]:
  output['wings'][team]={'outer':{},'inner':{}}
  for name,x in [('outer',xo),('inner',xi)]:
   for yy in (952,970,997,1020,1040):
    output['wings'][team][name][str(yy)]=med(region(a,(x,yy,x+8,yy+4)))
  output['wings'][team]['horizontal_y997']=[dict(x=x,rgb=med(region(a,(x,997,x+4,1001)))) for x in range(min(xo,xi),max(xo,xi)+1,10)]
 # Detect the player tab's flat dark body and both text rows.
 t=188;a=np.array(Image.open(SCRATCH/'frames'/f'nfl_{t+1:04d}.png'))
 output['player_tags']={}
 for side,b in [('away',(440,880,820,944)),('home',(1100,880,1490,944))]:
  p=region(a,b);dark=p.max(-1)<50
  output['player_tags'][side]={'dark_body_component':biggest(dark,b[:2]),'white_ink':ink(a,b),'name_row':ink(a,(b[0],900,b[2],924)),'stat_row':ink(a,(b[0],924,b[2],942))}
 (OUT/'details.json').write_text(json.dumps(output,indent=2)+'\n');sheet.save(SCRATCH/'selected_states.png')
 print(json.dumps({k:v for k,v in output.items() if k not in ('states','wings')},indent=1))

if __name__=='__main__':main()
