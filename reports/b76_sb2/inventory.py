"""PROVED OFFLINE: canonicalize the OCR readings without discarding the raw scan."""
import json,re
from pathlib import Path
OUT=Path(__file__).resolve().parent

def main():
 rows=json.loads((OUT/'scan.json').read_text())['rows'];groups={}
 for row in rows:
  if not row['present']:continue
  s=row.get('ocr','').replace('Ist','1st').replace('Ath','4th').replace('end','2nd').replace('srd','3rd')
  s=re.sub(r'\s*&\s*',' & ',s)
  s=s.replace(' & il',' & 11').replace(' & l1',' & 11').replace(' & i',' & 1').replace(' & l',' & 1')
  if row['plate_kind'] in ('ESPN','FLAG'):s=row['plate_kind']
  if not re.fullmatch(r'(?:[1-4](?:st|nd|rd|th) (?:& (?:[0-9]+|GOAL)|Down)|ESPN|FLAG)',s):continue
  groups.setdefault((row['plate_kind'],s),[]).append(row['t'])
 (OUT/'inventory.json').write_text(json.dumps(dict(classification='PROVED OFFLINE',method='one-second bin OCR, normalized ordinal/1 confusions; raw OCR in scan.json; counts include cut repeats, not broadcast dwell time',states=[dict(plate=k[0],label=k[1],count=len(v),times=v) for k,v in sorted(groups.items())]),indent=2)+'\n')
if __name__=='__main__':main()
