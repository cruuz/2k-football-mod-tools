"""PROVED OFFLINE: find above-bar text candidates without a vision estimate."""
import json,subprocess,os
import numpy as np
from PIL import Image
from measure import region,SCRATCH,OUT

def main():
 rows=[];last=-100
 for p in sorted((SCRATCH/'frames').glob('nfl_*.png')):
  t=int(p.stem[4:])-1;a=np.array(Image.open(p));flags=[]
  for b in [(460,905,800,939),(1122,905,1462,939)]:
   c=region(a,b);flags.append(bool((c.max(-1)<60).mean()>.60 and (c.min(-1)>150).sum()>100))
  if any(flags) and t-last>=3:
   last=t;top=Image.fromarray(a).crop((40,76,1090,124));tmp=SCRATCH/'tag_ocr.png';top.resize((2100,96)).save(tmp)
   r=subprocess.run(['tesseract',str(tmp),'stdout','--psm','6'],text=True,capture_output=True,env=dict(os.environ,OMP_THREAD_LIMIT='1'),check=True)
   rows.append(dict(bin=t,ocr=r.stdout.strip(),sides=flags))
 (OUT/'tag_inventory.json').write_text(json.dumps(dict(classification='PROVED OFFLINE',method='dark tab and white text predicate, OCR candidates at least 3 seconds apart; OCR is a finding aid, checked examples are in details.json',rows=rows),indent=2)+'\n')
 print(rows)
if __name__=='__main__':main()
