from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];out=ROOT/'reports/b71_s4'
names=['render','no_den','flag','score','hang_time','ball_on','live_clock_hidden','scores_100','all_events']
w,h=1065,145
sheet=Image.new('RGB',(w*2,h*len(names)),(24,24,24));d=ImageDraw.Draw(sheet)
for row,name in enumerate(names):
 for col,aspect in enumerate(('43','wide')):
  p=out/(name+'_'+aspect+'.png')
  if not p.exists():continue
  im=Image.open(p).convert('RGB').crop((50 if aspect=='wide' else 0,16,590 if aspect=='wide' else 640,464)).resize((1920,1080),Image.Resampling.LANCZOS).crop((425,933,1490,1060))
  sheet.paste(im,(col*w,row*h+18));d.text((col*w+5,row*h+3),name+' '+aspect+(' DIAGNOSTIC ONLY' if name=='all_events' else ''),fill='white')
sheet.save(out/'states_contact_sheet.png')
