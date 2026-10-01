"""Audit all nine source banner selectors from sn's verified occurrence ledger."""
import json,gzip
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];B=ROOT.parent;SN=B.parent/'sn'
keys={'banner_home_player','banner_home_team','banner_away_team'}
checks=[]
for prefix in ['s00','s01','s03','s07','s10','s11','s12','s14','s15','s20','s23','s24','s25']:
 for tod in 'dan':
  for weather in 'drs':
   name=f'{prefix}{tod}{weather}.iff';path=next((SN/'retail.occurrences').glob(name+'*'))
   rows=[json.loads(s) for s in gzip.decompress(path.read_bytes()).splitlines()]
   found=[]
   for key in sorted(keys):
    matches=[r for r in rows if r['scene']=='stadium' and key in r['names']]
    assert len(matches)==1,(name,key,len(matches))
    r=matches[0];assert r['format']=='P8' and r['studio_verified']
    found.append(dict(key=key,texture=r['texture'],size=[r['width'],r['height']],format='P8'))
   checks.append(dict(name=name,textures=found))
(B/'evidence/fan_variant_selectors.json').write_text(json.dumps(dict(evidence='PROVED OFFLINE',source='sn descriptor-verified retail.occurrences',bundles=checks),indent=2)+'\n')
print('PROVED',len(checks),'bundles;',sum(len(r['textures']) for r in checks),'exact-name P8 fan selectors')
